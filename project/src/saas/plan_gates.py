"""Plan-based feature gates for Nexus Cloud tiers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from src.auth import AuthContext
from src.database import db
from src.saas.provisioning import get_plan

_CHANNEL_ALIASES = {
    "voice": "voice",
    "telephony": "voice",
    "whatsapp": "whatsapp",
    "sms": "sms",
    "messenger": "messenger",
    "instagram": "instagram",
    "chat": "chat",
    "email": "email",
}

_FALLBACK_PLAN: dict[str, Any] = {"name": "Free", "channels": ["chat", "email"]}


def tenant_plan_id(tenant_id: str) -> str:
    sub = db.get_tenant_subscription(tenant_id)
    return str((sub or {}).get("plan_id") or "free")


def _resolve_plan(tenant_id: str) -> dict[str, Any]:
    return get_plan(tenant_plan_id(tenant_id)) or get_plan("free") or _FALLBACK_PLAN


def plan_allows_channel(tenant_id: str, channel: str) -> bool:
    plan = _resolve_plan(tenant_id)
    allowed = {c.lower() for c in plan.get("channels", [])}
    return _CHANNEL_ALIASES.get(channel.lower(), channel.lower()) in allowed


def require_channel(tenant_id: str, channel: str) -> None:
    if plan_allows_channel(tenant_id, channel):
        return
    plan = _resolve_plan(tenant_id)
    raise HTTPException(
        status_code=402,
        detail={
            "code": "plan_upgrade_required",
            "message": f"{channel.title()} is not included on the {plan['name']} plan. Upgrade to unlock.",
            "upgrade_url": "/contact",
        },
    )


def require_channel_for_context(ctx: AuthContext | None, channel: str) -> None:
    """Apply plan gates only when the caller is an authenticated tenant."""
    if ctx is None:
        return
    require_channel(ctx.tenant_id, channel)
