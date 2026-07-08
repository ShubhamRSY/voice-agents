"""OIDC SSO routes (provider-agnostic).

Works with Auth0 / Okta / Azure AD / Google Workspace by configuring
OIDC issuer + client credentials. Issues the same internal JWT that the
console already uses (stored in localStorage by the callback page).
"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from src.auth import create_jwt, hash_password
from src.config import get_settings
from src.database import db
from src.observability import collector

router = APIRouter()


def _oidc_fail(reason: str) -> RedirectResponse:
    collector.increment("oidc_failures_total")
    db.log_audit("default", None, "auth.oidc.failed", "user", {"reason": reason})
    return RedirectResponse(url=f"/?auth_error={reason}", status_code=302)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _email_domain(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[1].strip().lower()


def _split_csv(value: str) -> set[str]:
    return {v.strip().lower() for v in (value or "").split(",") if v.strip()}


async def _fetch_oidc_metadata(issuer_url: str) -> dict[str, Any]:
    issuer = issuer_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{issuer}/.well-known/openid-configuration", timeout=15)
        resp.raise_for_status()
        return resp.json()


@router.get("/auth/oidc/config")
async def oidc_config() -> dict[str, Any]:
    """Public config so the UI can show/hide SSO button."""
    s = get_settings()
    return {
        "enabled": bool(s.oidc_enabled and s.oidc_issuer_url and s.oidc_client_id and s.oidc_redirect_uri),
        "issuer_url": s.oidc_issuer_url,
    }


@router.get("/auth/oidc/login")
async def oidc_login(request: Request) -> RedirectResponse:
    s = get_settings()
    if not (s.oidc_enabled and s.oidc_issuer_url and s.oidc_client_id and s.oidc_redirect_uri):
        return RedirectResponse(url="/?auth_error=oidc_not_configured", status_code=302)

    meta = await _fetch_oidc_metadata(s.oidc_issuer_url)
    authorization_endpoint = meta["authorization_endpoint"]

    state = uuid.uuid4().hex
    nonce = uuid.uuid4().hex

    # Keep state/nonce in httpOnly cookies to prevent JS tampering.
    # This is a lightweight approach that avoids a server-side session store.
    query = urlencode({
        "response_type": "code",
        "client_id": s.oidc_client_id,
        "redirect_uri": s.oidc_redirect_uri,
        "scope": s.oidc_scopes,
        "state": state,
        "nonce": nonce,
    })
    redirect = RedirectResponse(url=f"{authorization_endpoint}?{query}", status_code=302)
    redirect.set_cookie("oidc_state", state, httponly=True, secure=True, samesite="lax", max_age=600)
    redirect.set_cookie("oidc_nonce", nonce, httponly=True, secure=True, samesite="lax", max_age=600)
    return redirect


@router.get("/auth/oidc/callback")
async def oidc_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> Any:
    s = get_settings()
    if error:
        return _oidc_fail(error)
    if not code or not state:
        return _oidc_fail("oidc_missing_code")

    cookie_state = request.cookies.get("oidc_state")
    cookie_nonce = request.cookies.get("oidc_nonce")
    if not cookie_state or cookie_state != state:
        return _oidc_fail("oidc_bad_state")

    if not (s.oidc_enabled and s.oidc_issuer_url and s.oidc_client_id and s.oidc_client_secret and s.oidc_redirect_uri):
        return _oidc_fail("oidc_not_configured")

    meta = await _fetch_oidc_metadata(s.oidc_issuer_url)
    token_endpoint = meta["token_endpoint"]
    userinfo_endpoint = meta.get("userinfo_endpoint")

    async with AsyncOAuth2Client(client_id=s.oidc_client_id, client_secret=s.oidc_client_secret) as client:
        token = await client.fetch_token(
            token_endpoint,
            code=code,
            redirect_uri=s.oidc_redirect_uri,
            timeout=15,
        )

        claims: dict[str, Any] = {}
        if userinfo_endpoint:
            resp = await client.get(userinfo_endpoint, headers={"Authorization": f"Bearer {token['access_token']}"}, timeout=15)
            if resp.status_code == 200:
                claims = resp.json()

    # Fallback: some providers put identity in id_token; Authlib doesn't decode/verify here
    # to keep this lightweight. We rely on the provider exchange + HTTPS redirect.
    email = _normalize_email(str(claims.get("email") or claims.get("preferred_username") or ""))
    name = str(claims.get("name") or claims.get("given_name") or email.split("@")[0] if email else "User")
    if not email:
        return _oidc_fail("oidc_no_email")

    tenant_id = s.oidc_default_tenant_id or "default"
    db.create_tenant(tenant_id, "Default Tenant", "default")

    user = db.get_user_by_email(email)
    if not user:
        user_id = f"user-{uuid.uuid4().hex[:8]}"
        admin_domains = _split_csv(s.oidc_admin_domains)
        role = "admin" if (db.count_users() == 0 or (_email_domain(email) in admin_domains)) else (s.oidc_default_role or "agent")
        # Password is unused for OIDC users; store a random hash to satisfy schema.
        db.create_user(user_id, tenant_id, email, hash_password(uuid.uuid4().hex), name, role)
        user = db.get_user_by_email(email)

    db.update_last_login(user["id"])
    db.log_audit(user["tenant_id"], user["id"], "auth.oidc.login", "user", {"email": email})
    jwt_token = create_jwt({
        "sub": user["id"],
        "tenant_id": user["tenant_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    })

    # Return a tiny HTML bridge that stores token in localStorage then redirects to /
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta http-equiv="Cache-Control" content="no-store" />
    <meta name="referrer" content="no-referrer" />
    <title>Signing in…</title>
  </head>
  <body>
    <script>
      try {{
        localStorage.setItem('nexus_auth_token', {jwt_token!r});
        localStorage.setItem('nexus_auth_user', JSON.stringify({{
          id: {user["id"]!r},
          email: {user["email"]!r},
          name: {user["name"]!r},
          role: {user["role"]!r},
          tenant_id: {user["tenant_id"]!r},
        }}));
      }} catch (e) {{}}
      window.location.replace('/');
    </script>
    Signing in…
  </body>
</html>"""

    response = HTMLResponse(content=html)
    # Clear state/nonce cookies
    response.delete_cookie("oidc_state")
    response.delete_cookie("oidc_nonce")
    return response

