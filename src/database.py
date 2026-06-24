"""SQLite persistence for sessions, conversations, and audit logs.

Supports database migrations and optional ChromaDB vector store backup.
"""

import json
import sqlite3
import time
from pathlib import Path
import structlog

from src.config import DATA_DIR

logger = structlog.get_logger()

DB_PATH = DATA_DIR / "nexus.db"

_SCHEMA_VERSION = 3


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return row[0] if row else 0


def _run_migrations(conn: sqlite3.Connection, current: int) -> None:
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


def init_db() -> None:
    with get_connection() as conn:
        current = _get_user_version(conn)
        if current < _SCHEMA_VERSION:
            _run_migrations(conn, current)
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name, slug, settings) VALUES (?, ?, ?, ?)",
            ("default", "Default Tenant", "default", "{}"),
        )


class Database:
    def __init__(self):
        init_db()

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
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [article_id, tenant_id]
        with get_connection() as conn:
            conn.execute(
                f"UPDATE knowledge_articles SET {set_clause} WHERE id = ? AND tenant_id = ?",
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
            except Exception:
                return []


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
            import boto3
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
