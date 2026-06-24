"""Feedback loop engine — tracks CSAT trends, compares against targets, and
suggests agent parameter adjustments for continuous improvement."""

import time
from typing import Any

import structlog

from src.config import load_agent_config
from src.database import get_connection

logger = structlog.get_logger()


class FeedbackEngine:
    """Evaluate agent performance over time and generate improvement suggestions.

    The engine:
    1.  Records periodic performance snapshots (containment rate, avg CSAT, latency).
    2.  Compares actual metrics against configured targets from `feedback_loop_config`.
    3.  Generates improvement_suggestions when metrics drift below targets.
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_config(self, agent_id: str) -> dict:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM feedback_loop_config WHERE tenant_id = ? AND agent_id = ?",
                (self.tenant_id, agent_id),
            ).fetchone()
            if row:
                return dict(row)
            return self._default_config(agent_id)

    def _default_config(self, agent_id: str) -> dict:
        agent_config = load_agent_config().get("agents", {}).get(agent_id, {})
        return {
            "id": None,
            "tenant_id": self.tenant_id,
            "agent_id": agent_id,
            "enabled": True,
            "csat_target": 4.0,
            "containment_target": agent_config.get("containment_target", 0.75),
            "adjustment_temperature": agent_config.get("temperature"),
            "adjustment_max_tokens": agent_config.get("max_tokens"),
        }

    def upsert_config(self, agent_id: str, **kwargs) -> dict:
        allowed = {"enabled", "csat_target", "containment_target"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_config(agent_id)

        existing = self.get_config(agent_id)
        merged = {**existing, **updates, "updated_at": time.time()}

        with get_connection() as conn:
            if existing.get("id"):
                set_clause = ", ".join(f"{k} = ?" for k in merged)
                conn.execute(
                    f"UPDATE feedback_loop_config SET {set_clause} WHERE id = ?",
                    [*merged.values(), existing["id"]],
                )
            else:
                merged["created_at"] = time.time()
                conn.execute(
                    """INSERT INTO feedback_loop_config
                       (tenant_id, agent_id, enabled, csat_target, containment_target, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (self.tenant_id, agent_id, merged["enabled"], merged["csat_target"],
                     merged["containment_target"], merged["created_at"], merged["updated_at"]),
                )
        return self.get_config(agent_id)

    # ------------------------------------------------------------------
    # Snapshot recording
    # ------------------------------------------------------------------

    def record_snapshot(self, agent_id: str, hours: int = 24) -> dict:
        """Capture current agent performance metrics and store a trend record."""
        cutoff = time.time() - (hours * 3600)
        snapshot = self._compute_metrics(agent_id, cutoff)

        with get_connection() as conn:
            conn.execute(
                """INSERT INTO agent_performance_trends
                   (tenant_id, agent_id, period_hours, containment_rate, avg_csat,
                    avg_response_time_ms, hallucination_rate, csat_count, sample_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.tenant_id, agent_id, hours, snapshot["containment_rate"],
                 snapshot["avg_csat"], snapshot["avg_response_time_ms"],
                 snapshot["hallucination_rate"], snapshot["csat_count"],
                 snapshot["sample_count"]),
            )
        logger.info("feedback_snapshot_recorded", agent_id=agent_id, metrics=snapshot)
        return snapshot

    def _compute_metrics(self, agent_id: str, cutoff: float) -> dict:
        with get_connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND agent_id = ? AND created_at >= ?",
                (self.tenant_id, agent_id, cutoff),
            ).fetchone()["c"]

            resolved = conn.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE tenant_id = ? AND agent_id = ? AND created_at >= ? AND status = 'ended'",
                (self.tenant_id, agent_id, cutoff),
            ).fetchone()["c"]

            avg_rt = conn.execute("""
                SELECT AVG(CAST(json_extract(metrics, '$.response_time_ms') AS REAL)) as avg
                FROM messages WHERE session_id IN (
                    SELECT id FROM sessions WHERE tenant_id = ? AND agent_id = ? AND created_at >= ?
                )
            """, (self.tenant_id, agent_id, cutoff)).fetchone()["avg"] or 0

            csat_row = conn.execute(
                "SELECT AVG(score) as avg, COUNT(*) as cnt FROM csat_surveys WHERE tenant_id = ? AND session_id IN (SELECT id FROM sessions WHERE agent_id = ? AND created_at >= ?)",
                (self.tenant_id, agent_id, cutoff),
            ).fetchone()

            hallucination_rate = 0.0
            hallucinated = conn.execute("""
                SELECT COUNT(*) as c FROM messages WHERE session_id IN (
                    SELECT id FROM sessions WHERE tenant_id = ? AND agent_id = ? AND created_at >= ?
                ) AND json_extract(metrics, '$.hallucination_risk') = 'high'
            """, (self.tenant_id, agent_id, cutoff)).fetchone()["c"]

            total_msgs = conn.execute("""
                SELECT COUNT(*) as c FROM messages WHERE session_id IN (
                    SELECT id FROM sessions WHERE tenant_id = ? AND agent_id = ? AND created_at >= ?
                )
            """, (self.tenant_id, agent_id, cutoff)).fetchone()["c"]

            if total_msgs > 0:
                hallucination_rate = round(hallucinated / total_msgs, 4)

            return {
                "containment_rate": round(resolved / total, 4) if total > 0 else 0.0,
                "avg_csat": round(csat_row["avg"], 2) if csat_row and csat_row["cnt"] > 0 else 0.0,
                "avg_response_time_ms": round(avg_rt, 1),
                "hallucination_rate": hallucination_rate,
                "csat_count": csat_row["cnt"] if csat_row else 0,
                "sample_count": total,
            }

    # ------------------------------------------------------------------
    # Trend analysis
    # ------------------------------------------------------------------

    def get_trends(self, agent_id: str, limit: int = 30) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM agent_performance_trends
                   WHERE tenant_id = ? AND agent_id = ?
                   ORDER BY recorded_at DESC LIMIT ?""",
                (self.tenant_id, agent_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Improvement suggestions
    # ------------------------------------------------------------------

    def analyze(self, agent_id: str) -> list[dict]:
        """Compare recent performance against targets and return suggestions."""
        config = self.get_config(agent_id)
        if not config.get("enabled"):
            return []

        snapshot = self.record_snapshot(agent_id)
        suggestions: list[dict] = []

        target_containment = config.get("containment_target", 0.75)
        actual_containment = snapshot["containment_rate"]
        if actual_containment < target_containment and snapshot["sample_count"] >= 10:
            gap = round((target_containment - actual_containment) * 100, 1)
            suggestions.append({
                "agent_id": agent_id,
                "category": "containment",
                "title": f"Containment rate {gap}% below target",
                "description": (
                    f"Actual containment rate is {actual_containment:.1%} vs target "
                    f"{target_containment:.0%}. Consider reviewing escalation triggers "
                    "or updating the knowledge base with frequently escalated topics."
                ),
                "suggested_action": "Review escalation logs and add KB articles for top escalation reasons.",
                "metric_before": actual_containment,
                "metric_after": target_containment,
            })

        target_csat = config.get("csat_target", 4.0)
        actual_csat = snapshot["avg_csat"]
        if actual_csat < target_csat and actual_csat > 0 and snapshot["csat_count"] >= 5:
            gap = round(target_csat - actual_csat, 2)
            suggestions.append({
                "agent_id": agent_id,
                "category": "csat",
                "title": f"CSAT score {gap} points below target",
                "description": (
                    f"Average CSAT is {actual_csat}/5 vs target {target_csat}/5. "
                    "Low CSAT may indicate agent tone, resolution quality, or latency issues."
                ),
                "suggested_action": (
                    "Review low-scored conversations, adjust agent temperature or prompt tone, "
                    "and consider reducing max_tokens for terser responses."
                ),
                "metric_before": actual_csat,
                "metric_after": target_csat,
            })

        target_hallucination = 0.15
        hallucination_rate = snapshot["hallucination_rate"]
        if hallucination_rate > target_hallucination and snapshot["sample_count"] >= 10:
            suggestions.append({
                "agent_id": agent_id,
                "category": "hallucination",
                "title": f"Hallucination rate {hallucination_rate:.1%} exceeds threshold",
                "description": (
                    f"Hallucination rate is {hallucination_rate:.1%} vs threshold "
                    f"{target_hallucination:.0%}. Consider tightening RAG score threshold "
                    "or lowering model temperature."
                ),
                "suggested_action": "Lower temperature by 0.1 and reduce top_k to 30 for more deterministic responses.",
                "metric_before": hallucination_rate,
                "metric_after": target_hallucination,
            })

        if snapshot["avg_response_time_ms"] > 2000 and snapshot["sample_count"] >= 10:
            suggestions.append({
                "agent_id": agent_id,
                "category": "latency",
                "title": f"High average response time ({snapshot['avg_response_time_ms']:.0f}ms)",
                "description": (
                    "Response times above 2000ms may degrade customer experience. "
                    "Consider switching to a smaller model or reducing max_tokens."
                ),
                "suggested_action": "Reduce max_tokens by 25% or switch to gpt-4o-mini if using a larger model.",
                "metric_before": snapshot["avg_response_time_ms"],
                "metric_after": 2000,
            })

        self._persist_suggestions(agent_id, suggestions)
        return suggestions

    def _persist_suggestions(self, agent_id: str, suggestions: list[dict]) -> None:
        with get_connection() as conn:
            for s in suggestions:
                conn.execute(
                    """INSERT INTO improvement_suggestions
                       (tenant_id, agent_id, category, title, description, suggested_action,
                        metric_before, metric_after)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (self.tenant_id, agent_id, s["category"], s["title"], s["description"],
                     s["suggested_action"], s["metric_before"], s["metric_after"]),
                )

    def get_suggestions(self, agent_id: str, limit: int = 20) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM improvement_suggestions
                   WHERE tenant_id = ? AND agent_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (self.tenant_id, agent_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def mark_applied(self, suggestion_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE improvement_suggestions SET applied = 1 WHERE id = ?",
                (suggestion_id,),
            )

    def get_feedback_report(self, agent_id: str) -> dict:
        """Aggregated feedback report for dashboard display."""
        config = self.get_config(agent_id)
        recent_trends = self.get_trends(agent_id, limit=10)
        suggestions = self.get_suggestions(agent_id)
        latest = recent_trends[0] if recent_trends else self._compute_metrics(agent_id, time.time() - 86400)

        return {
            "agent_id": agent_id,
            "config": config,
            "current_metrics": latest,
            "recent_trends": recent_trends,
            "improvement_suggestions": suggestions,
            "period_hours": 24,
        }

    def apply_auto_adjustment(self, agent_id: str) -> dict | None:
        """Auto-tune agent parameters based on performance analysis.

        Returns a dict with the adjustments made, or None if no adjustment needed.
        """
        config = self.get_config(agent_id)
        if not config.get("enabled"):
            return None

        snapshot = self.record_snapshot(agent_id)
        adjustments: dict[str, Any] = {}

        if snapshot["hallucination_rate"] > 0.15 and snapshot["sample_count"] >= 10:
            current_temp = config.get("adjustment_temperature")
            if current_temp and current_temp > 0.1:
                adjustments["temperature"] = round(current_temp - 0.1, 2)

        if snapshot["avg_response_time_ms"] > 2000 and snapshot["sample_count"] >= 10:
            current_tokens = config.get("adjustment_max_tokens")
            if current_tokens and current_tokens > 128:
                adjustments["max_tokens"] = max(128, int(current_tokens * 0.75))

        if adjustments:
            logger.info("feedback_auto_adjustment", agent_id=agent_id, adjustments=adjustments)
            # Update the tracked adjustments in the config record
            with get_connection() as conn:
                conn.execute(
                    "UPDATE feedback_loop_config SET adjustment_temperature = ?, adjustment_max_tokens = ?, updated_at = ? WHERE tenant_id = ? AND agent_id = ?",
                    (adjustments.get("temperature", config.get("adjustment_temperature")),
                     adjustments.get("max_tokens", config.get("adjustment_max_tokens")),
                     time.time(), self.tenant_id, agent_id),
                )

        return adjustments if adjustments else None
