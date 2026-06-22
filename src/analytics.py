"""Analytics and metrics aggregation for the dashboard."""

import time
from typing import Any

from src.database import db


class AnalyticsEngine:
    """Aggregates conversation, agent, and customer experience metrics."""

    def get_dashboard(self, tenant_id: str, hours: int = 24) -> dict:
        conv = db.get_conversation_analytics(tenant_id, hours)
        csat = db.get_csat_stats(tenant_id)
        active = db.get_active_sessions(tenant_id)
        recent_logs = db.get_audit_logs(tenant_id, limit=20)

        return {
            "conversations": conv,
            "csat": csat,
            "active_sessions": len(active),
            "recent_activity": recent_logs,
            "period_hours": hours,
        }

    def get_agent_scorecard(self, tenant_id: str, hours: int = 168) -> dict:
        """Per-agent performance metrics over the given period."""
        cutoff = time.time() - (hours * 3600)
        from src.database import get_connection

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    s.agent_id,
                    COUNT(*) as total_sessions,
                    SUM(CASE WHEN s.status = 'ended' THEN 1 ELSE 0 END) as resolved,
                    AVG(CASE WHEN c.score IS NOT NULL THEN c.score ELSE NULL END) as avg_csat,
                    COUNT(DISTINCT c.id) as csat_count
                FROM sessions s
                LEFT JOIN csat_surveys c ON c.session_id = s.id
                WHERE s.tenant_id = ? AND s.created_at >= ?
                GROUP BY s.agent_id
            """, (tenant_id, cutoff)).fetchall()

            return {
                "agents": [
                    {
                        "agent_id": r["agent_id"],
                        "sessions": r["total_sessions"],
                        "resolved": r["resolved"],
                        "containment_rate": round(r["resolved"] / r["total_sessions"], 2) if r["total_sessions"] > 0 else 0,
                        "avg_csat": round(r["avg_csat"], 2) if r["avg_csat"] else 0,
                        "csat_responses": r["csat_count"],
                    }
                    for r in rows
                ],
                "period_hours": hours,
            }

    def get_conversation_timeline(self, tenant_id: str, hours: int = 24) -> list[dict]:
        """Hourly conversation volume for charting."""
        cutoff = time.time() - (hours * 3600)
        from src.database import get_connection

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    strftime('%Y-%m-%dT%H:00:00', created_at, 'unixepoch') as hour,
                    COUNT(*) as count
                FROM sessions
                WHERE tenant_id = ? AND created_at >= ?
                GROUP BY hour
                ORDER BY hour ASC
            """, (tenant_id, cutoff)).fetchall()
            return [dict(r) for r in rows]

    def record_conversation_metric(self, session_id: str, metrics: dict) -> None:
        """Store per-conversation metrics for later analysis."""
        from src.database import get_connection

        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET customer_info = ? WHERE id = ?",
                (metrics.get("customer_info", ""), session_id),
            )


analytics = AnalyticsEngine()
