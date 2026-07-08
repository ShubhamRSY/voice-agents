## OIDC SSO with Auth0 (systemd + Caddy)

This guide matches the production deployment at `https://yournexus.duckdns.org/` — Nexus on **systemd**, TLS via **Caddy**, SQLite + Chroma on disk.

### 1. Create an Auth0 application

1. Sign in at [auth0.com](https://auth0.com) and create a tenant (e.g. `yournexus.us.auth0.com`).
2. **Applications → Create Application**
   - Type: **Regular Web Application**
   - Name: `Nexus`
3. **Settings** tab:
   - **Allowed Callback URLs:** `https://your-domain.com/api/v1/auth/oidc/callback`
   - **Allowed Logout URLs:** `https://your-domain.com/`
   - **Allowed Web Origins:** `https://your-domain.com`
4. Copy **Domain**, **Client ID**, and **Client Secret**.

Optional: enable **Google** (or other) connections under **Authentication → Social** or **Enterprise**.

### 2. Configure Nexus `.env`

Edit `config/environment/.env` on the server:

```bash
OIDC_ENABLED=true
OIDC_ISSUER_URL=https://YOUR_TENANT.us.auth0.com/
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
OIDC_REDIRECT_URI=https://your-domain.com/api/v1/auth/oidc/callback
OIDC_SCOPES=openid profile email
OIDC_DEFAULT_TENANT_ID=default
OIDC_DEFAULT_ROLE=agent
OIDC_ADMIN_DOMAINS=yourcompany.com
```

| Variable | Purpose |
|----------|---------|
| `OIDC_DEFAULT_ROLE` | Role assigned to new SSO users (`agent`, `admin`, etc.) |
| `OIDC_ADMIN_DOMAINS` | Comma-separated email domains that receive `admin` on first login |

### 3. Install dependency and restart

```bash
cd ~/voice-agents
source .venv/bin/activate
pip install Authlib==1.7.2
sudo systemctl restart nexus
```

Verify:

```bash
curl -s https://your-domain.com/api/v1/auth/oidc/config
# {"enabled":true,"issuer_url":"https://..."}

curl -sI https://your-domain.com/api/v1/auth/oidc/login | grep -i location
# Should redirect to Auth0 /authorize
```

### 4. User provisioning (automatic)

On first successful SSO login:

1. Nexus reads email/name from Auth0 userinfo.
2. If the user does not exist, a row is created in SQLite.
3. Role rules:
   - First user in the system → `admin`
   - Email domain in `OIDC_ADMIN_DOMAINS` → `admin`
   - Otherwise → `OIDC_DEFAULT_ROLE`
4. An internal JWT is issued (same as password login) and stored in browser `localStorage`.

Audit events: `auth.oidc.login`, `auth.oidc.failed`.

### 5. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Internal Server Error on SSO click | Ensure OIDC metadata uses plain `httpx` (not Authlib client). Check `journalctl -u nexus -n 50`. |
| `oidc_bad_state` | Cookies blocked; ensure HTTPS and `SameSite=lax` cookies reach the callback. |
| `oidc_no_email` | Auth0 connection must return `email` scope; check Auth0 user profile. |
| SSO button hidden | `GET /api/v1/auth/oidc/config` must return `"enabled": true`. |

### Other providers (Okta, Azure AD, Google Workspace)

Set `OIDC_ISSUER_URL` to the provider's issuer (from `/.well-known/openid-configuration`). All other env vars stay the same.
