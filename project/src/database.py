"""SQLite persistence for sessions, conversations, and audit logs.

Supports database migrations and optional ChromaDB vector store backup.
"""

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
import structlog
from contextlib import contextmanager

from src.config import DATA_DIR, get_settings
from src.db.sql_helpers import build_set_clause

logger = structlog.get_logger()

DB_PATH = DATA_DIR / "nexus.db"

_SCHEMA_VERSION = 7
_db_engine = None
_pg_pool = None
_db_initialized = False
_db_lock = threading.Lock()


def _adapt_sql_for_pg(sql: str) -> str:
    """Translate SQLite-style SQL to PostgreSQL."""
    text = sql.strip()
    upper = re.sub(r"\s+", " ", text).upper()
    if "INSERT OR IGNORE" in upper:
        text = re.sub(r"(?i)INSERT\s+OR\s+IGNORE", "INSERT", text)
        if " INTO TENANTS " in f" {upper} ":
            text = text.rstrip(";") + " ON CONFLICT (id) DO NOTHING"
        elif " INTO USERS " in f" {upper} ":
            text = text.rstrip(";") + " ON CONFLICT (id) DO NOTHING"
    return text.replace("?", "%s")


def _insert_returns_id(sql: str) -> bool:
    upper = re.sub(r"\s+", " ", sql).upper()
    return (
        upper.startswith("INSERT")
        and "RETURNING" not in upper
        and any(token in upper for token in ("INTO MESSAGES", "INTO KNOWLEDGE_ARTICLES", "INTO CSAT_SURVEYS"))
    )


class _PgExecuteResult:
    """SQLite-compatible result wrapper for PostgreSQL cursors."""

    def __init__(
        self,
        *,
        rowcount: int = 0,
        lastrowid: int | None = None,
        prefetch_one=None,
        prefetch_all: list | None = None,
    ):
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self._prefetch_one = prefetch_one
        self._prefetch_all = prefetch_all
        self._one_consumed = False

    def fetchone(self):
        if self._prefetch_all is not None:
            return self._prefetch_all[0] if self._prefetch_all else None
        if self._one_consumed:
            return None
        self._one_consumed = True
        return self._prefetch_one

    def fetchall(self):
        if self._prefetch_all is not None:
            return self._prefetch_all
        return [self._prefetch_one] if self._prefetch_one is not None else []


class _PgConnectionWrapper:
    """Expose sqlite3-like conn.execute() on psycopg2 connections."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        from psycopg2.extras import RealDictCursor

        adapted = _adapt_sql_for_pg(sql)
        returning = _insert_returns_id(adapted)
        if returning:
            adapted = adapted.rstrip(";") + " RETURNING id"
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(adapted, params or ())
        rowcount = cur.rowcount
        if returning:
            row = cur.fetchone()
            cur.close()
            return _PgExecuteResult(rowcount=rowcount, lastrowid=int(row["id"]) if row else None)
        if adapted.lstrip().upper().startswith("SELECT"):
            rows = cur.fetchall()
            cur.close()
            return _PgExecuteResult(
                rowcount=rowcount,
                prefetch_one=rows[0] if rows else None,
                prefetch_all=rows,
            )
        cur.close()
        return _PgExecuteResult(rowcount=rowcount)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)


def _get_pg_pool():
    """Lazy-init connection pool for PostgreSQL."""
    global _pg_pool
    if _pg_pool is None:
        try:
            import psycopg2.pool
            settings = get_settings()
            _pg_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dsn=settings.database_url,
            )
            logger.info("postgres_pool_initialized", minconn=2, maxconn=10)
        except Exception as exc:
            logger.error("postgres_pool_init_failed", error=str(exc))
            raise
    return _pg_pool


@contextmanager
def _get_connection_unchecked():
    settings = get_settings()
    if settings.database_url:
        pool = _get_pg_pool()
        conn = pool.getconn()
        try:
            conn.autocommit = True
            yield _PgConnectionWrapper(conn)
        finally:
            pool.putconn(conn)
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    yield conn
    conn.close()


@contextmanager
def get_connection():
    _ensure_db()
    with _get_connection_unchecked() as conn:
        yield conn



def _is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _get_user_version(conn) -> int:
    if _is_sqlite(conn):
        row = conn.execute("PRAGMA user_version").fetchone()
        return row[0] if row else 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM _schema_version")
            row = cur.fetchone()
            return row[0] if row else 0
    except Exception as exc:
        logger.debug("schema_version_read_failed", error=str(exc))
        conn.rollback()
        return 0


def _set_pg_user_version(conn, version: int) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER NOT NULL)")
        cur.execute("DELETE FROM _schema_version")
        cur.execute("INSERT INTO _schema_version (version) VALUES (%s)", (version,))
    conn.commit()


def _run_migrations(conn, current: int) -> None:
    if _is_sqlite(conn):
        _run_sqlite_migrations(conn, current)
    else:
        _run_pg_migrations(conn, current)


def _run_sqlite_migrations(conn, current: int) -> None:
    if current < 1:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                settings TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'agent',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                last_login REAL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                agent_id TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'chat',
                customer_info TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                ended_at REAL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tool_calls TEXT DEFAULT '[]',
                metrics TEXT DEFAULT '{}',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS knowledge_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS csat_surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id),
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                score INTEGER NOT NULL CHECK(score >= 1 AND score <= 5),
                feedback TEXT DEFAULT '',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                user_id TEXT,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_articles_tenant ON knowledge_articles(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_csat_session ON csat_surveys(session_id);
            CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id);

            CREATE TABLE IF NOT EXISTS kb_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES knowledge_articles(id),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                version INTEGER NOT NULL DEFAULT 1,
                changed_by TEXT DEFAULT '',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_kb_versions_article ON kb_versions(article_id);

            PRAGMA user_version = 1;
        """)
        logger.info("migration_001_applied")

    if current < 2:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS migrations_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                applied_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                description TEXT DEFAULT ''
            );
            PRAGMA user_version = 2;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (2, "Add migrations_log table for tracking schema history"),
        )
        logger.info("migration_002_applied")

    if current < 3:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback_loop_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                agent_id TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                csat_target REAL NOT NULL DEFAULT 4.0,
                containment_target REAL NOT NULL DEFAULT 0.75,
                adjustment_temperature REAL,
                adjustment_max_tokens INTEGER,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS agent_performance_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                agent_id TEXT NOT NULL,
                period_hours INTEGER NOT NULL DEFAULT 24,
                containment_rate REAL DEFAULT 0.0,
                avg_csat REAL DEFAULT 0.0,
                avg_response_time_ms REAL DEFAULT 0.0,
                hallucination_rate REAL DEFAULT 0.0,
                csat_count INTEGER DEFAULT 0,
                sample_count INTEGER DEFAULT 0,
                recorded_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS improvement_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                agent_id TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                suggested_action TEXT NOT NULL DEFAULT '',
                metric_before REAL DEFAULT 0.0,
                metric_after REAL DEFAULT 0.0,
                applied INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_agent ON feedback_loop_config(tenant_id, agent_id);
            CREATE INDEX IF NOT EXISTS idx_trends_agent ON agent_performance_trends(tenant_id, agent_id);
            CREATE INDEX IF NOT EXISTS idx_suggestions_agent ON improvement_suggestions(tenant_id, agent_id);
            PRAGMA user_version = 3;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (3, "Add feedback loop tables for continuous improvement"),
        )
        logger.info("migration_003_applied")

    if current < 4:
        for col_sql in (
            "ALTER TABLE sessions ADD COLUMN assigned_to TEXT DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN escalation_reason TEXT DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE sessions ADD COLUMN locale TEXT DEFAULT 'en'",
            "ALTER TABLE sessions ADD COLUMN handoff_status TEXT NOT NULL DEFAULT 'ai'",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e):
                    logger.warning("column_already_exists", column=col_sql)
                else:
                    raise

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                session_id TEXT DEFAULT '',
                subject TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                priority TEXT NOT NULL DEFAULT 'normal',
                customer_id TEXT DEFAULT '',
                assigned_to TEXT DEFAULT '',
                external_id TEXT DEFAULT '',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS nps_surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                score INTEGER NOT NULL CHECK(score >= 0 AND score <= 10),
                feedback TEXT DEFAULT '',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS email_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                from_addr TEXT NOT NULL,
                to_addr TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                direction TEXT NOT NULL DEFAULT 'inbound',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS workflow_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                name TEXT NOT NULL,
                trigger_event TEXT NOT NULL,
                conditions TEXT NOT NULL DEFAULT '{}',
                actions TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_handoff ON sessions(tenant_id, handoff_status);
            CREATE INDEX IF NOT EXISTS idx_tickets_tenant ON tickets(tenant_id, status);
            CREATE INDEX IF NOT EXISTS idx_nps_tenant ON nps_surveys(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_email_session ON email_messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_workflows_tenant ON workflow_rules(tenant_id);
            PRAGMA user_version = 4;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (4, "CX platform: handoff, tickets, NPS, email, workflows"),
        )
        logger.info("migration_004_applied")

    if current < 5:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS message_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_msg_feedback_message ON message_feedback(message_id);
            CREATE INDEX IF NOT EXISTS idx_msg_feedback_tenant ON message_feedback(tenant_id);
            PRAGMA user_version = 5;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (5, "Per-message thumbs feedback"),
        )
        logger.info("migration_005_applied")

    if current < 6:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_presence (
                user_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                status TEXT NOT NULL DEFAULT 'offline',
                skills TEXT DEFAULT '',
                last_heartbeat REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS ivr_flows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                name TEXT NOT NULL,
                nodes TEXT NOT NULL DEFAULT '[]',
                edges TEXT NOT NULL DEFAULT '[]',
                entry_node TEXT NOT NULL DEFAULT 'start',
                active INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS quality_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                reviewer_id TEXT NOT NULL,
                overall_score INTEGER NOT NULL CHECK(overall_score >= 1 AND overall_score <= 5),
                rubric TEXT NOT NULL DEFAULT '{}',
                notes TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS cobrowse_sessions (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                customer_token TEXT NOT NULL,
                agent_id TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'waiting',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS supervisor_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL REFERENCES tenants(id),
                supervisor_id TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'monitor',
                message TEXT DEFAULT '',
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS tenant_subscriptions (
                tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),
                plan_id TEXT NOT NULL DEFAULT 'starter',
                status TEXT NOT NULL DEFAULT 'active',
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_presence_tenant ON agent_presence(tenant_id, status);
            CREATE INDEX IF NOT EXISTS idx_ivr_tenant ON ivr_flows(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_qm_tenant ON quality_reviews(tenant_id, status);
            CREATE INDEX IF NOT EXISTS idx_cobrowse_tenant ON cobrowse_sessions(tenant_id);
            PRAGMA user_version = 6;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (6, "Enterprise: agent status, IVR, QM, cobrowse, supervisor, SaaS"),
        )
        logger.info("migration_006_applied")

    if current < 7:
        for col_sql in (
            "ALTER TABLE tenant_subscriptions ADD COLUMN stripe_customer_id TEXT DEFAULT ''",
            "ALTER TABLE tenant_subscriptions ADD COLUMN stripe_subscription_id TEXT DEFAULT ''",
            "ALTER TABLE tenant_subscriptions ADD COLUMN trial_ends_at REAL",
        ):
            try:
                conn.execute(col_sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e):
                    logger.warning("column_already_exists", column=col_sql)
                else:
                    raise

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS saas_signup_pending (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                company_name TEXT NOT NULL,
                admin_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                stripe_session_id TEXT DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );
            PRAGMA user_version = 7;
        """)
        conn.execute(
            "INSERT INTO migrations_log (version, description) VALUES (?, ?)",
            (7, "SaaS signup pending + Stripe subscription fields"),
        )
        logger.info("migration_007_applied")


def _run_pg_migrations(conn, current: int) -> None:
    if current < 1:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    settings TEXT NOT NULL DEFAULT '{}'
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'agent',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    last_login DOUBLE PRECISION
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    agent_id TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'chat',
                    customer_info TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    ended_at DOUBLE PRECISION
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT DEFAULT '[]',
                    metrics TEXT DEFAULT '{}',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_articles (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'general',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS csat_surveys (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    score INTEGER NOT NULL CHECK(score >= 1 AND score <= 5),
                    feedback TEXT DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    details TEXT DEFAULT '{}',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_tenant ON knowledge_articles(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_csat_session ON csat_surveys(session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kb_versions (
                    id SERIAL PRIMARY KEY,
                    article_id INTEGER NOT NULL REFERENCES knowledge_articles(id),
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT 'general',
                    version INTEGER NOT NULL DEFAULT 1,
                    changed_by TEXT DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_versions_article ON kb_versions(article_id)")
        _set_pg_user_version(conn, 1)
        logger.info("migration_001_applied")

    if current < 2:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS migrations_log (
                    id SERIAL PRIMARY KEY,
                    version INTEGER NOT NULL,
                    description TEXT DEFAULT '',
                    applied_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (2, "Add migrations_log table for tracking schema history"),
            )
        _set_pg_user_version(conn, 2)
        logger.info("migration_002_applied")

    if current < 3:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback_loop_config (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    agent_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    csat_target DOUBLE PRECISION NOT NULL DEFAULT 4.0,
                    containment_target DOUBLE PRECISION NOT NULL DEFAULT 0.75,
                    adjustment_temperature DOUBLE PRECISION,
                    adjustment_max_tokens INTEGER,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance_trends (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    agent_id TEXT NOT NULL,
                    period_hours INTEGER NOT NULL DEFAULT 24,
                    containment_rate DOUBLE PRECISION DEFAULT 0.0,
                    avg_csat DOUBLE PRECISION DEFAULT 0.0,
                    avg_response_time_ms DOUBLE PRECISION DEFAULT 0.0,
                    hallucination_rate DOUBLE PRECISION DEFAULT 0.0,
                    csat_count INTEGER DEFAULT 0,
                    sample_count INTEGER DEFAULT 0,
                    recorded_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS improvement_suggestions (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    agent_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    suggested_action TEXT NOT NULL DEFAULT '',
                    metric_before DOUBLE PRECISION DEFAULT 0.0,
                    metric_after DOUBLE PRECISION DEFAULT 0.0,
                    applied INTEGER NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_agent ON feedback_loop_config(tenant_id, agent_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trends_agent ON agent_performance_trends(tenant_id, agent_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_suggestions_agent ON improvement_suggestions(tenant_id, agent_id)")
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (3, "Add feedback loop tables for continuous improvement"),
            )
        _set_pg_user_version(conn, 3)
        logger.info("migration_003_applied")

    if current < 4:
        with conn.cursor() as cur:
            for col in (
                "assigned_to TEXT DEFAULT ''",
                "escalation_reason TEXT DEFAULT ''",
                "priority TEXT NOT NULL DEFAULT 'normal'",
                "locale TEXT DEFAULT 'en'",
                "handoff_status TEXT NOT NULL DEFAULT 'ai'",
            ):
                cur.execute(f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {col}")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    session_id TEXT DEFAULT '',
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'open',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    customer_id TEXT DEFAULT '',
                    assigned_to TEXT DEFAULT '',
                    external_id TEXT DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS nps_surveys (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    score INTEGER NOT NULL CHECK(score >= 0 AND score <= 10),
                    feedback TEXT DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS email_messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    from_addr TEXT NOT NULL,
                    to_addr TEXT NOT NULL,
                    subject TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    direction TEXT NOT NULL DEFAULT 'inbound',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_rules (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    name TEXT NOT NULL,
                    trigger_event TEXT NOT NULL,
                    conditions TEXT NOT NULL DEFAULT '{}',
                    actions TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_handoff ON sessions(tenant_id, handoff_status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_tickets_tenant ON tickets(tenant_id, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_nps_tenant ON nps_surveys(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_email_session ON email_messages(session_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_workflows_tenant ON workflow_rules(tenant_id)")
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (4, "CX platform: handoff, tickets, NPS, email, workflows"),
            )
        _set_pg_user_version(conn, 4)
        logger.info("migration_004_applied")

    if current < 5:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS message_feedback (
                    id SERIAL PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_feedback_message ON message_feedback(message_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_msg_feedback_tenant ON message_feedback(tenant_id)")
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (5, "Per-message thumbs feedback"),
            )
        _set_pg_user_version(conn, 5)
        logger.info("migration_005_applied")

    if current < 6:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_presence (
                    user_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    status TEXT NOT NULL DEFAULT 'offline',
                    skills TEXT DEFAULT '',
                    last_heartbeat DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ivr_flows (
                    id SERIAL PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    name TEXT NOT NULL,
                    nodes TEXT NOT NULL DEFAULT '[]',
                    edges TEXT NOT NULL DEFAULT '[]',
                    entry_node TEXT NOT NULL DEFAULT 'start',
                    active INTEGER NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW())),
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS quality_reviews (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    reviewer_id TEXT NOT NULL,
                    overall_score INTEGER NOT NULL CHECK(overall_score >= 1 AND overall_score <= 5),
                    rubric TEXT NOT NULL DEFAULT '{}',
                    notes TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS cobrowse_sessions (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    customer_token TEXT NOT NULL,
                    agent_id TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'waiting',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS supervisor_actions (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id),
                    supervisor_id TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'monitor',
                    message TEXT DEFAULT '',
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tenant_subscriptions (
                    tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),
                    plan_id TEXT NOT NULL DEFAULT 'starter',
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_presence_tenant ON agent_presence(tenant_id, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ivr_tenant ON ivr_flows(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_qm_tenant ON quality_reviews(tenant_id, status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_cobrowse_tenant ON cobrowse_sessions(tenant_id)")
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (6, "Enterprise: agent status, IVR, QM, cobrowse, supervisor, SaaS"),
            )
        _set_pg_user_version(conn, 6)
        logger.info("migration_006_applied")

    if current < 7:
        with conn.cursor() as cur:
            for col in (
                "stripe_customer_id TEXT DEFAULT ''",
                "stripe_subscription_id TEXT DEFAULT ''",
                "trial_ends_at DOUBLE PRECISION",
            ):
                cur.execute(f"ALTER TABLE tenant_subscriptions ADD COLUMN IF NOT EXISTS {col}")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saas_signup_pending (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    admin_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    stripe_session_id TEXT DEFAULT '',
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at DOUBLE PRECISION NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()))
                )
            """)
            cur.execute(
                "INSERT INTO migrations_log (version, description) VALUES (%s, %s)",
                (7, "SaaS signup pending + Stripe subscription fields"),
            )
        _set_pg_user_version(conn, 7)
        logger.info("migration_007_applied")


def init_db() -> None:
    """Public entry point — also called from main.py lifespan."""
    _ensure_db()


def _ensure_db() -> None:
    """One-shot lazy initialization — called before every connection."""
    global _db_initialized
    if _db_initialized:
        return
    with _db_lock:
        if _db_initialized:
            return
        with _get_connection_unchecked() as conn:
            if not _is_sqlite(conn):
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_try_advisory_lock(802348571)")
                    locked = cur.fetchone()[0]
                if not locked:
                    logger.info("migration_lock_busy")
                    return
                conn.commit()
            try:
                current = _get_user_version(conn)
                if current < _SCHEMA_VERSION:
                    _run_migrations(conn, current)
                if _is_sqlite(conn):
                    conn.execute(
                        "INSERT OR IGNORE INTO tenants (id, name, slug, settings) VALUES (?, ?, ?, ?)",
                        ("default", "Default Tenant", "default", "{}"),
                    )
                else:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO tenants (id, name, slug, settings) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                            ("default", "Default Tenant", "default", "{}"),
                        )
                    conn.commit()
            finally:
                if not _is_sqlite(conn):
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(802348571)")
                    conn.commit()
        _db_initialized = True


class Database:
    def __init__(self):
        pass

    def create_tenant(self, tenant_id: str, name: str, slug: str, settings: dict | None = None) -> dict:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (id, name, slug, settings) VALUES (?, ?, ?, ?)",
                (tenant_id, name, slug, json.dumps(settings or {})),
            )
            return {"id": tenant_id, "name": name, "slug": slug}

    def get_tenant(self, tenant_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def get_tenant_by_slug(self, slug: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM tenants WHERE slug = ?", (slug,)).fetchone()
            if row:
                return dict(row)
            return None

    def create_user(self, user_id: str, tenant_id: str, email: str, password_hash: str, name: str, role: str = "agent") -> dict:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (id, tenant_id, email, password_hash, name, role) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, tenant_id, email, password_hash, name, role),
            )
            return {"id": user_id, "email": email, "name": name, "role": role}

    def count_users(self) -> int:
        with get_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
            return int(row["c"] if row else 0)

    def get_user_by_email(self, email: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                return dict(row)
            return None

    def get_user(self, user_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def update_last_login(self, user_id: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (time.time(), user_id))

    def create_session(self, session_id: str, tenant_id: str, agent_id: str, channel: str = "chat", customer_info: str = "") -> dict:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (id, tenant_id, agent_id, channel, customer_info) VALUES (?, ?, ?, ?, ?)",
                (session_id, tenant_id, agent_id, channel, customer_info),
            )
            return {"id": session_id, "tenant_id": tenant_id, "agent_id": agent_id}

    def get_session(self, session_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def end_session(self, session_id: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET status = 'ended', ended_at = ? WHERE id = ?", (time.time(), session_id))

    def get_active_sessions(self, tenant_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE tenant_id = ? AND status = 'active' ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_message(self, session_id: str, role: str, content: str, tool_calls: list | None = None, metrics: dict | None = None) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls, metrics) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, json.dumps(tool_calls or []), json.dumps(metrics or {})),
            )
            return cur.lastrowid

    def get_session_messages(self, session_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_article(self, tenant_id: str, title: str, content: str, tags: str = "", category: str = "general") -> dict:
        with get_connection() as conn:
            now = time.time()
            cur = conn.execute(
                "INSERT INTO knowledge_articles (tenant_id, title, content, tags, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tenant_id, title, content, tags, category, now, now),
            )
            aid = cur.lastrowid
            conn.execute(
                "INSERT INTO kb_versions (article_id, title, content, tags, category, version, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (aid, title, content, tags, category, now),
            )
            return {"id": aid, "title": title}

    def update_article(self, article_id: int, tenant_id: str, **kwargs) -> dict | None:
        allowed = {"title", "content", "tags", "category"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return None
        updates["updated_at"] = time.time()
        set_clause = build_set_clause(updates.keys(), frozenset(allowed | {"updated_at"}))
        vals = list(updates.values()) + [article_id, tenant_id]
        with get_connection() as conn:
            conn.execute(
                "UPDATE knowledge_articles SET " + set_clause + " WHERE id = ? AND tenant_id = ?",  # nosec B608
                vals,
            )
            existing = conn.execute(
                "SELECT title, content, tags, category FROM knowledge_articles WHERE id = ? AND tenant_id = ?",
                (article_id, tenant_id),
            ).fetchone()
            if existing:
                version = conn.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 as v FROM kb_versions WHERE article_id = ?",
                    (article_id,),
                ).fetchone()["v"]
                conn.execute(
                    "INSERT INTO kb_versions (article_id, title, content, tags, category, version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (article_id, existing["title"], existing["content"], existing["tags"], existing["category"], version, time.time()),
                )
            return {"id": article_id, **updates}

    def delete_article(self, article_id: int, tenant_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM knowledge_articles WHERE id = ? AND tenant_id = ?",
                (article_id, tenant_id),
            )
            return cur.rowcount > 0

    def list_articles(self, tenant_id: str, category: str | None = None) -> list[dict]:
        with get_connection() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM knowledge_articles WHERE tenant_id = ? AND category = ? ORDER BY updated_at DESC",
                    (tenant_id, category),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge_articles WHERE tenant_id = ? ORDER BY updated_at DESC",
                    (tenant_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_article(self, article_id: int, tenant_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_articles WHERE id = ? AND tenant_id = ?",
                (article_id, tenant_id),
            ).fetchone()
            if row:
                return dict(row)
            return None

    def save_csat(self, session_id: str, tenant_id: str, score: int, feedback: str = "") -> dict:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO csat_surveys (session_id, tenant_id, score, feedback) VALUES (?, ?, ?, ?)",
                (session_id, tenant_id, score, feedback),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "score": score}

    def get_csat_stats(self, tenant_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT AVG(score) as avg_score, COUNT(*) as total, SUM(CASE WHEN score >= 4 THEN 1 ELSE 0 END) as positive FROM csat_surveys WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
            if row and row["total"]:
                return {"avg_score": round(row["avg_score"], 2), "total": row["total"], "positive": row["positive"]}
            return {"avg_score": 0, "total": 0, "positive": 0}

    def log_audit(self, tenant_id: str, user_id: str | None, action: str, resource: str, details: dict | None = None) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log (tenant_id, user_id, action, resource, details) VALUES (?, ?, ?, ?, ?)",
                (tenant_id, user_id, action, resource, json.dumps(details or {})),
            )

    def get_audit_logs(self, tenant_id: str, limit: int = 100) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY created_at DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_conversation_analytics(self, tenant_id: str, hours: int = 24) -> dict:
        cutoff = time.time() - (hours * 3600)
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND created_at >= ?",
                (tenant_id, cutoff),
            ).fetchone()["c"]

            resolved = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND created_at >= ? AND status = 'ended'",
                (tenant_id, cutoff),
            ).fetchone()["c"]

            avg_messages = conn.execute("""
                SELECT AVG(msg_count) as avg FROM (
                    SELECT COUNT(*) as msg_count FROM messages m
                    JOIN sessions s ON m.session_id = s.id
                    WHERE s.tenant_id = ? AND s.created_at >= ?
                    GROUP BY m.session_id
                )
            """, (tenant_id, cutoff)).fetchone()["avg"] or 0

            avg_csat = conn.execute(
                "SELECT AVG(score) as avg FROM csat_surveys WHERE tenant_id = ? AND created_at >= ?",
                (tenant_id, cutoff),
            ).fetchone()["avg"] or 0

            return {
                "total_conversations": total,
                "resolved": resolved,
                "containment_rate": round(resolved / total, 2) if total > 0 else 0,
                "avg_messages_per_session": round(avg_messages, 1),
                "avg_csat": round(avg_csat, 2),
                "period_hours": hours,
            }

    def get_migration_history(self) -> list[dict]:
        with get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT * FROM migrations_log ORDER BY version ASC"
                ).fetchall()
                return [dict(r) for r in rows]
            except Exception as exc:
                logger.warning("migration_history_read_failed", error=str(exc))
                return []

    def update_session_locale(self, session_id: str, locale: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE sessions SET locale = ? WHERE id = ?", (locale, session_id))

    def escalate_session(self, session_id: str, reason: str, priority: str = "normal") -> dict | None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET handoff_status = 'queued', escalation_reason = ?, priority = ? WHERE id = ?",
                (reason, priority, session_id),
            )
            return self.get_session(session_id)

    def assign_session(self, session_id: str, agent_user_id: str) -> dict | None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET assigned_to = ?, handoff_status = 'human_active' WHERE id = ?",
                (agent_user_id, session_id),
            )
            return self.get_session(session_id)

    def resolve_handoff(self, session_id: str) -> dict | None:
        with get_connection() as conn:
            now = time.time()
            conn.execute(
                "UPDATE sessions SET handoff_status = 'resolved', status = 'ended', ended_at = ? WHERE id = ?",
                (now, session_id),
            )
            return self.get_session(session_id)

    def list_inbox(self, tenant_id: str, status: str | None = None) -> list[dict]:
        with get_connection() as conn:
            if status:
                rows = conn.execute(
                    """SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as message_count
                       FROM sessions s
                       WHERE s.tenant_id = ? AND s.handoff_status = ?
                       ORDER BY s.created_at DESC LIMIT 100""",
                    (tenant_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as message_count
                       FROM sessions s
                       WHERE s.tenant_id = ? AND s.handoff_status IN ('queued', 'human_active')
                       ORDER BY CASE s.handoff_status WHEN 'queued' THEN 0 ELSE 1 END, s.created_at DESC
                       LIMIT 100""",
                    (tenant_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def save_agent_message(self, session_id: str, agent_user_id: str, content: str) -> int:
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET assigned_to = ?, handoff_status = 'human_active' WHERE id = ?",
                (agent_user_id, session_id),
            )
            return self.save_message(session_id, "agent", content)

    def create_ticket(
        self,
        tenant_id: str,
        subject: str,
        description: str,
        session_id: str = "",
        customer_id: str = "",
        priority: str = "normal",
        assigned_to: str = "",
        external_id: str = "",
    ) -> dict:
        now = time.time()
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO tickets
                   (tenant_id, session_id, subject, description, priority, customer_id, assigned_to, external_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tenant_id, session_id, subject, description, priority, customer_id, assigned_to, external_id, now, now),
            )
            return {
                "id": cur.lastrowid,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "subject": subject,
                "status": "open",
                "priority": priority,
                "external_id": external_id,
            }

    def list_tickets(self, tenant_id: str, status: str | None = None) -> list[dict]:
        with get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE tenant_id = ? AND status = ? ORDER BY updated_at DESC LIMIT 100",
                    (tenant_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE tenant_id = ? ORDER BY updated_at DESC LIMIT 100",
                    (tenant_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def update_ticket(self, ticket_id: int, tenant_id: str, **kwargs) -> dict | None:
        allowed = {"status", "priority", "assigned_to", "description", "subject"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return None
        updates["updated_at"] = time.time()
        set_clause = build_set_clause(updates.keys(), frozenset(allowed | {"updated_at"}))
        vals = list(updates.values()) + [ticket_id, tenant_id]
        with get_connection() as conn:
            conn.execute("UPDATE tickets SET " + set_clause + " WHERE id = ? AND tenant_id = ?", vals)  # nosec B608
            row = conn.execute("SELECT * FROM tickets WHERE id = ? AND tenant_id = ?", (ticket_id, tenant_id)).fetchone()
            return dict(row) if row else None

    def save_nps(self, session_id: str, tenant_id: str, score: int, feedback: str = "") -> dict:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO nps_surveys (session_id, tenant_id, score, feedback) VALUES (?, ?, ?, ?)",
                (session_id, tenant_id, score, feedback),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "score": score}

    def get_nps_stats(self, tenant_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT AVG(score) as avg_score, COUNT(*) as total,
                          SUM(CASE WHEN score >= 9 THEN 1 ELSE 0 END) as promoters,
                          SUM(CASE WHEN score <= 6 THEN 1 ELSE 0 END) as detractors
                   FROM nps_surveys WHERE tenant_id = ?""",
                (tenant_id,),
            ).fetchone()
            if row and row["total"]:
                nps = round(((row["promoters"] - row["detractors"]) / row["total"]) * 100, 1)
                return {
                    "avg_score": round(row["avg_score"], 2),
                    "total": row["total"],
                    "promoters": row["promoters"],
                    "detractors": row["detractors"],
                    "nps": nps,
                }
            return {"avg_score": 0, "total": 0, "promoters": 0, "detractors": 0, "nps": 0}

    def save_email_message(
        self, session_id: str, tenant_id: str, from_addr: str, to_addr: str,
        subject: str, body: str, direction: str,
    ) -> dict:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO email_messages (session_id, tenant_id, from_addr, to_addr, subject, body, direction)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, tenant_id, from_addr, to_addr, subject, body, direction),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "direction": direction}

    def list_workflows(self, tenant_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM workflow_rules WHERE tenant_id = ? ORDER BY updated_at DESC",
                (tenant_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["conditions"] = json.loads(d.get("conditions") or "{}")
                d["actions"] = json.loads(d.get("actions") or "[]")
                result.append(d)
            return result

    def save_workflow(self, tenant_id: str, name: str, trigger_event: str, conditions: dict, actions: list, workflow_id: int | None = None) -> dict:
        now = time.time()
        cond_json = json.dumps(conditions or {})
        act_json = json.dumps(actions or [])
        with get_connection() as conn:
            if workflow_id:
                conn.execute(
                    """UPDATE workflow_rules SET name = ?, trigger_event = ?, conditions = ?, actions = ?, updated_at = ?
                       WHERE id = ? AND tenant_id = ?""",
                    (name, trigger_event, cond_json, act_json, now, workflow_id, tenant_id),
                )
                wid = workflow_id
            else:
                cur = conn.execute(
                    """INSERT INTO workflow_rules (tenant_id, name, trigger_event, conditions, actions, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (tenant_id, name, trigger_event, cond_json, act_json, now, now),
                )
                wid = cur.lastrowid
            return {"id": wid, "name": name, "trigger_event": trigger_event, "conditions": conditions, "actions": actions}

    def delete_workflow(self, workflow_id: int, tenant_id: str) -> bool:
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM workflow_rules WHERE id = ? AND tenant_id = ?", (workflow_id, tenant_id))
            return cur.rowcount > 0

    def get_handoff_stats(self, tenant_id: str, hours: int = 24) -> dict:
        cutoff = time.time() - (hours * 3600)
        with get_connection() as conn:
            escalated = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND created_at >= ? AND handoff_status != 'ai'",
                (tenant_id, cutoff),
            ).fetchone()["c"]
            resolved = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND created_at >= ? AND handoff_status = 'resolved'",
                (tenant_id, cutoff),
            ).fetchone()["c"]
            open_tickets = conn.execute(
                "SELECT COUNT(*) as c FROM tickets WHERE tenant_id = ? AND status = 'open'",
                (tenant_id,),
            ).fetchone()["c"]
            return {"escalated": escalated, "resolved_handoffs": resolved, "open_tickets": open_tickets, "period_hours": hours}

    def get_avg_response_time_ms(self, tenant_id: str, hours: int = 24) -> float:
        cutoff = time.time() - (hours * 3600)
        with get_connection() as conn:
            row = conn.execute("""
                SELECT AVG(CAST(json_extract(m.metrics, '$.response_time_ms') AS REAL)) as avg_rt
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.tenant_id = ? AND s.created_at >= ? AND m.role = 'assistant'
                  AND json_extract(m.metrics, '$.response_time_ms') IS NOT NULL
            """, (tenant_id, cutoff)).fetchone()
            return round(row["avg_rt"] or 0, 1)

    def save_message_feedback(self, message_id: int, session_id: str, tenant_id: str, rating: int) -> dict:
        if rating not in (-1, 1):
            raise ValueError("rating must be -1 or 1")
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM message_feedback WHERE message_id = ? AND tenant_id = ?",
                (message_id, tenant_id),
            )
            cur = conn.execute(
                "INSERT INTO message_feedback (message_id, session_id, tenant_id, rating) VALUES (?, ?, ?, ?)",
                (message_id, session_id, tenant_id, rating),
            )
            return {"id": cur.lastrowid, "message_id": message_id, "rating": rating}

    def get_message_feedback_stats(self, tenant_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as positive,
                          SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) as negative
                   FROM message_feedback WHERE tenant_id = ?""",
                (tenant_id,),
            ).fetchone()
            total = row["total"] or 0
            pos = row["positive"] or 0
            return {
                "total": total,
                "positive": pos,
                "negative": row["negative"] or 0,
                "satisfaction_rate": round(pos / total, 2) if total else 0,
            }

    def set_agent_status(self, user_id: str, tenant_id: str, status: str, skills: str = "") -> dict:
        now = time.time()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO agent_presence (user_id, tenant_id, status, skills, last_heartbeat)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET status=excluded.status, skills=excluded.skills, last_heartbeat=excluded.last_heartbeat""",
                (user_id, tenant_id, status, skills, now),
            )
            return {"user_id": user_id, "status": status, "last_heartbeat": now}

    def get_team_presence(self, tenant_id: str, stale_seconds: int = 120) -> list[dict]:
        cutoff = time.time() - stale_seconds
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT p.*, u.name, u.email, u.role FROM agent_presence p
                   JOIN users u ON u.id = p.user_id
                   WHERE p.tenant_id = ? AND p.last_heartbeat >= ?
                   ORDER BY p.status, u.name""",
                (tenant_id, cutoff),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_ivr_flow(self, tenant_id: str, name: str, nodes: list, edges: list, entry_node: str = "start", flow_id: int | None = None, active: bool = False) -> dict:
        now = time.time()
        nodes_json = json.dumps(nodes)
        edges_json = json.dumps(edges)
        with get_connection() as conn:
            if flow_id:
                conn.execute(
                    """UPDATE ivr_flows SET name=?, nodes=?, edges=?, entry_node=?, active=?, updated_at=?
                       WHERE id=? AND tenant_id=?""",
                    (name, nodes_json, edges_json, entry_node, int(active), now, flow_id, tenant_id),
                )
                fid = flow_id
            else:
                cur = conn.execute(
                    """INSERT INTO ivr_flows (tenant_id, name, nodes, edges, entry_node, active, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tenant_id, name, nodes_json, edges_json, entry_node, int(active), now, now),
                )
                fid = cur.lastrowid
            if active:
                conn.execute("UPDATE ivr_flows SET active=0 WHERE tenant_id=? AND id!=?", (tenant_id, fid))
            return {"id": fid, "name": name, "active": active}

    def list_ivr_flows(self, tenant_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM ivr_flows WHERE tenant_id=? ORDER BY updated_at DESC", (tenant_id,)).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["nodes"] = json.loads(d.get("nodes") or "[]")
                d["edges"] = json.loads(d.get("edges") or "[]")
                result.append(d)
            return result

    def get_active_ivr_flow(self, tenant_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ivr_flows WHERE tenant_id=? AND active=1 LIMIT 1", (tenant_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["nodes"] = json.loads(d.get("nodes") or "[]")
            d["edges"] = json.loads(d.get("edges") or "[]")
            return d

    def create_qm_review(self, session_id: str, tenant_id: str, reviewer_id: str, overall_score: int, rubric: dict, notes: str = "", status: str = "completed") -> dict:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO quality_reviews (session_id, tenant_id, reviewer_id, overall_score, rubric, notes, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, tenant_id, reviewer_id, overall_score, json.dumps(rubric), notes, status),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "overall_score": overall_score, "status": status}

    def list_qm_reviews(self, tenant_id: str, status: str | None = None) -> list[dict]:
        with get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM quality_reviews WHERE tenant_id=? AND status=? ORDER BY created_at DESC LIMIT 100",
                    (tenant_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM quality_reviews WHERE tenant_id=? ORDER BY created_at DESC LIMIT 100",
                    (tenant_id,),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["rubric"] = json.loads(d.get("rubric") or "{}")
                out.append(d)
            return out

    def create_cobrowse_session(self, session_id: str, tenant_id: str, customer_token: str) -> dict:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO cobrowse_sessions (id, tenant_id, customer_token, status) VALUES (?, ?, ?, 'waiting')",
                (session_id, tenant_id, customer_token),
            )
            return {"id": session_id, "customer_token": customer_token, "status": "waiting"}

    def join_cobrowse(self, session_id: str, agent_id: str) -> dict | None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE cobrowse_sessions SET agent_id=?, status='active' WHERE id=?",
                (agent_id, session_id),
            )
            row = conn.execute("SELECT * FROM cobrowse_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def get_cobrowse(self, session_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM cobrowse_sessions WHERE id=?", (session_id,)).fetchone()
            return dict(row) if row else None

    def log_supervisor_action(self, session_id: str, tenant_id: str, supervisor_id: str, mode: str, message: str = "") -> dict:
        with get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO supervisor_actions (session_id, tenant_id, supervisor_id, mode, message)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, tenant_id, supervisor_id, mode, message),
            )
            return {"id": cur.lastrowid, "session_id": session_id, "mode": mode}

    def list_supervisor_actions(self, session_id: str) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM supervisor_actions WHERE session_id=? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_tenant_subscription(self, tenant_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM tenant_subscriptions WHERE tenant_id=?", (tenant_id,)).fetchone()
            if row:
                return dict(row)
            return {"tenant_id": tenant_id, "plan_id": "starter", "status": "active"}

    def set_tenant_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str = "active",
        stripe_customer_id: str = "",
        stripe_subscription_id: str = "",
        trial_ends_at: float | None = None,
    ) -> dict:
        now = time.time()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO tenant_subscriptions
                   (tenant_id, plan_id, status, updated_at, stripe_customer_id, stripe_subscription_id, trial_ends_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(tenant_id) DO UPDATE SET
                     plan_id=excluded.plan_id, status=excluded.status, updated_at=excluded.updated_at,
                     stripe_customer_id=excluded.stripe_customer_id,
                     stripe_subscription_id=excluded.stripe_subscription_id,
                     trial_ends_at=excluded.trial_ends_at""",
                (tenant_id, plan_id, status, now, stripe_customer_id, stripe_subscription_id, trial_ends_at),
            )
            return {"tenant_id": tenant_id, "plan_id": plan_id, "status": status}

    def save_signup_pending(
        self, pending_id: str, email: str, company_name: str, admin_name: str,
        password_hash: str, plan_id: str,
    ) -> dict:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO saas_signup_pending
                   (id, email, company_name, admin_name, password_hash, plan_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pending_id, email, company_name, admin_name, password_hash, plan_id),
            )
            return {"id": pending_id, "email": email}

    def update_signup_pending_stripe(self, pending_id: str, stripe_session_id: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE saas_signup_pending SET stripe_session_id=? WHERE id=?",
                (stripe_session_id, pending_id),
            )

    def get_signup_pending(self, pending_id: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM saas_signup_pending WHERE id=?", (pending_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["completed"] = bool(d.get("completed"))
            return d

    def complete_signup_pending(self, pending_id: str) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE saas_signup_pending SET completed=1 WHERE id=?", (pending_id,))

    def update_subscription_by_stripe(self, stripe_subscription_id: str, status: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE tenant_subscriptions SET status=?, updated_at=? WHERE stripe_subscription_id=?",
                (status, time.time(), stripe_subscription_id),
            )

    def portal_lookup_ticket(self, tenant_id: str, ticket_id: int, email: str) -> dict | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM tickets WHERE id=? AND tenant_id=? AND customer_id=?",
                (ticket_id, tenant_id, email),
            ).fetchone()
            return dict(row) if row else None


def backup_chromadb(s3_bucket: str | None = None, s3_prefix: str = "chroma-backup") -> dict:
    """Backup ChromaDB persistent store to local archive or S3."""
    from src.config import get_settings

    settings = get_settings()
    chroma_dir = Path(settings.chroma_persist_dir)
    if not chroma_dir.exists():
        return {"status": "skipped", "reason": "ChromaDB directory not found"}

    backup_name = f"chroma_{int(time.time())}.tar.gz"
    backup_path = DATA_DIR / backup_name

    import tarfile
    with tarfile.open(str(backup_path), "w:gz") as tar:
        tar.add(str(chroma_dir), arcname=chroma_dir.name)

    if s3_bucket:
        try:
            import boto3  # type: ignore[import-not-found]
            s3 = boto3.client("s3")
            s3_key = f"{s3_prefix}/{backup_name}"
            s3.upload_file(str(backup_path), s3_bucket, s3_key)
            backup_path.unlink()
            logger.info("chroma_s3_backup_complete", bucket=s3_bucket, key=s3_key)
            return {"status": "s3_uploaded", "bucket": s3_bucket, "key": s3_key}
        except ImportError:
            logger.warning("boto3 not installed, keeping local backup")
            return {"status": "local", "path": str(backup_path)}
    else:
        logger.info("chroma_local_backup_complete", path=str(backup_path))
        return {"status": "local", "path": str(backup_path)}


db = Database()
