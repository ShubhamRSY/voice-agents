## Access controls

### Authentication methods

1. **Local password** — bcrypt-hashed passwords in SQLite; JWT issued on success.
2. **OIDC SSO** — Auth0 (or Okta/Azure AD/Google Workspace); JIT user provisioning on first login.

### Authorization model

| Role | Capabilities |
|------|--------------|
| `admin` | Full tenant access: KB, integrations, analytics, audit log, user management |
| `agent` | Chat, copilot, read KB, limited settings |

Roles are stored per user and embedded in the JWT. API routes use `require_auth` and role checks.

### Production hardening checklist

- [ ] `AUTH_REQUIRED=true`
- [ ] `ALLOW_REGISTRATION=false` after first admin exists
- [ ] `OIDC_ENABLED=true` for enterprise customers (disable open registration)
- [ ] Strong `JWT_SECRET` (32+ random bytes): `openssl rand -hex 32`
- [ ] `OIDC_ADMIN_DOMAINS` set to your company email domain
- [ ] Caddy TLS with valid certificate
- [ ] SSH: key-only, no password login
- [ ] Firewall: ports 22, 80, 443 only

### Access review procedure (quarterly)

1. Export users: query `users` table or use admin API.
2. Verify each account is active and role-appropriate.
3. Review Auth0/Okta application access and admin users.
4. Remove stale accounts (`DELETE` via admin or direct DB with audit note).
5. Log review in audit trail or external compliance tool.

### Access control policy (template)

> **Policy:** Access to Nexus production systems is granted on least-privilege basis.  
> **Provisioning:** SSO users are auto-provisioned on first login; admins are assigned by domain rule or manual promotion.  
> **Deprovisioning:** Disable user in IdP; remove or deactivate row in Nexus `users` table within 24 hours.  
> **Review:** Quarterly access review by engineering lead.

Customize with legal/compliance before SOC 2 audit.
