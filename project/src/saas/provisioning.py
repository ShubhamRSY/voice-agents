"""SaaS plan catalog and multi-tenant workspace provisioning."""

from __future__ import annotations

import re
import time
import uuid

import structlog

from src.auth import create_jwt, hash_password
from src.database import db

logger = structlog.get_logger()

SAAS_PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price_monthly": 0,
        "agents": 2,
        "channels": ["chat", "email"],
        "support": "community",
        "trial_days": 0,
    },
    {
        "id": "starter",
        "name": "Starter",
        "price_monthly": 29,
        "agents": 10,
        "channels": ["chat", "voice", "email"],
        "support": "email",
        "trial_days": 14,
    },
    {
        "id": "growth",
        "name": "Growth",
        "price_monthly": 99,
        "agents": 50,
        "channels": ["chat", "voice", "email", "whatsapp"],
        "support": "priority",
        "trial_days": 14,
    },
]

STARTER_KB = [
    {
        "title": "Welcome to Nexus Cloud",
        "content": "Your workspace is live. Use Chat for AI support, Inbox for human handoffs, and Analytics to track CSAT and containment.",
        "tags": "onboarding",
        "category": "general",
    },
    {
        "title": "Connect your channels",
        "content": "Add Twilio for voice/WhatsApp, SMTP for email, and Meta webhooks for Messenger. Open Integrations in the sidebar.",
        "tags": "onboarding,channels",
        "category": "technical",
    },
    {
        "title": "Invite your team",
        "content": "Share the console URL with agents. Each user signs in with their work email. Admins manage integrations and billing.",
        "tags": "onboarding,team",
        "category": "account",
    },
]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:48] or f"workspace-{uuid.uuid4().hex[:6]}"


def get_plan(plan_id: str) -> dict | None:
    return next((p for p in SAAS_PLANS if p["id"] == plan_id), None)


def seed_workspace_kb(tenant_id: str) -> None:
    for art in STARTER_KB:
        db.create_article(tenant_id, art["title"], art["content"], art["tags"], art["category"])


def provision_workspace(
    *,
    company_name: str,
    admin_name: str,
    email: str,
    password: str = "",
    password_hash: str = "",
    plan_id: str,
    status: str = "trialing",
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
) -> dict:
    """Create tenant, admin user, subscription, and starter KB — shared-cloud provisioning."""
    plan = get_plan(plan_id)
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")

    if db.get_user_by_email(email):
        raise ValueError("Email already registered")

    tenant_id = f"tenant-{uuid.uuid4().hex[:10]}"
    user_id = f"user-{uuid.uuid4().hex[:10]}"
    slug = slugify(company_name)
    trial_days = int(plan.get("trial_days", 14))
    trial_ends = time.time() + (trial_days * 86400)

    db.create_tenant(tenant_id, company_name, slug, {
        "plan": plan_id,
        "provisioned_at": time.time(),
        "saas": True,
        "trial_ends_at": trial_ends,
    })
    db.create_user(
        user_id, tenant_id, email,
        password_hash or hash_password(password),
        admin_name, "admin",
    )
    db.set_tenant_subscription(
        tenant_id, plan_id, status=status,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
        trial_ends_at=trial_ends,
    )
    seed_workspace_kb(tenant_id)

    token = create_jwt({
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "name": admin_name,
        "role": "admin",
    })
    db.log_audit(tenant_id, user_id, "saas.workspace.provisioned", "tenant", {
        "plan_id": plan_id, "status": status, "company": company_name,
    })
    logger.info("saas_workspace_provisioned", tenant_id=tenant_id, plan=plan_id, email=email)

    return {
        "token": token,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "plan_id": plan_id,
        "status": status,
        "trial_ends_at": trial_ends,
        "console_url": "/",
        "user": {
            "id": user_id,
            "email": email,
            "name": admin_name,
            "role": "admin",
            "tenant_id": tenant_id,
        },
    }
