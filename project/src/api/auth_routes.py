"""Auth routes: login, register, current user."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from structlog import get_logger

from src.auth import AuthContext, create_jwt, hash_password, require_auth, verify_password
from src.database import db
from src.api.deps import LoginRequest, RegisterRequest

logger = get_logger()
router = APIRouter()


@router.post("/auth/login")
async def login(request: LoginRequest) -> dict[str, Any]:
    from fastapi import HTTPException

    user = db.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        db.log_audit("default", None, "auth.login.failed", "user", {"email": request.email})
        raise HTTPException(status_code=401, detail="Invalid email or password")

    db.update_last_login(user["id"])
    db.log_audit(user["tenant_id"], user["id"], "auth.login.success", "user", {"method": "password"})
    token = create_jwt({
        "sub": user["id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        },
    }


@router.post("/auth/register")
async def register(request: RegisterRequest) -> dict[str, Any]:
    from fastapi import HTTPException

    from src.config import get_settings

    settings = get_settings()
    user_count = db.count_users()
    # Always allow the first account (bootstrap). After that, open signup
    # only when ALLOW_REGISTRATION=true.
    if user_count > 0 and not settings.allow_registration:
        raise HTTPException(
            status_code=403,
            detail="Registration is closed. Ask an admin to create your account.",
        )

    tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"
    user_id = f"user-{uuid.uuid4().hex[:8]}"

    existing = db.get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    db.create_tenant(tenant_id, request.tenant_name, tenant_id)
    db.create_user(user_id, tenant_id, request.email, hash_password(request.password), request.name, "admin")
    db.log_audit(tenant_id, user_id, "tenant.created", "tenant", {"tenant_name": request.tenant_name})

    token = create_jwt({
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": request.email,
        "name": request.name,
        "role": "admin",
    })
    return {"token": token, "tenant_id": tenant_id, "user_id": user_id}


@router.get("/auth/me")
async def me(ctx: AuthContext = Depends(require_auth)) -> dict:
    return {
        "user_id": ctx.user_id,
        "tenant_id": ctx.tenant_id,
        "email": ctx.email,
        "name": ctx.name,
        "role": ctx.role,
        "is_admin": ctx.is_admin(),
    }


@router.get("/auth/demo/config")
async def demo_config() -> dict:
    from src.config import get_settings
    settings = get_settings()
    return {
        "enabled": settings.allow_guest_demo or settings.demo_mode,
        "demo_mode": settings.demo_mode,
        "live_url": settings.twilio_webhook_base_url or "",
    }


@router.post("/auth/demo-login")
async def demo_login() -> dict[str, Any]:
    """One-click sandbox login for try-it-now on the login screen."""
    from fastapi import HTTPException
    from src.config import get_settings
    from src.auth import DEMO_TENANT_ID, DEMO_USERS, seed_demo_data

    settings = get_settings()
    if not settings.allow_guest_demo and not settings.demo_mode:
        raise HTTPException(status_code=403, detail="Guest demo is disabled")

    if settings.demo_mode:
        seed_demo_data()

    demo_user = DEMO_USERS[1]  # agent@acme.com
    user = db.get_user_by_email(demo_user["email"])
    if not user:
        db.create_tenant(DEMO_TENANT_ID, "Acme Demo", "demo-acme")
        db.create_user(
            demo_user["id"], DEMO_TENANT_ID, demo_user["email"],
            hash_password(demo_user["password"]), demo_user["name"], demo_user["role"],
        )
        user = db.get_user_by_email(demo_user["email"])

    if not user:
        raise HTTPException(status_code=500, detail="Demo user could not be provisioned")

    token = create_jwt({
        "sub": user["id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })
    db.log_audit(user["tenant_id"], user["id"], "auth.login.success", "user", {"method": "demo"})
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "name": user["name"],
            "role": user["role"],
            "tenant_id": user["tenant_id"],
        },
        "sandbox": True,
    }
