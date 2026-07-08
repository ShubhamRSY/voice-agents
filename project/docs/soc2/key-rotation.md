## Key rotation procedures

Rotate secrets on a schedule or immediately after suspected exposure.

### Rotation schedule (recommended)

| Secret | Frequency | Priority |
|--------|-----------|----------|
| `JWT_SECRET` | 90 days | High — invalidates all sessions |
| `OIDC_CLIENT_SECRET` | 90 days | High — rotate in Auth0 + `.env` |
| `INTEGRATIONS_ENCRYPTION_KEY` | Annual | Critical — re-encrypt vault after rotation |
| `OPENAI_API_KEY` | On compromise | Medium |
| SSH host keys | Annual | Low (VM rebuild) |
| TLS certificates | Auto (Let's Encrypt) | Caddy handles renewal |

### JWT_SECRET rotation

1. Generate new secret:
   ```bash
   openssl rand -hex 32
   ```
2. Update `config/environment/.env` on the server.
3. Restart Nexus: `sudo systemctl restart nexus`
4. **Impact:** All users must sign in again.
5. Document rotation date in your compliance log.

### OIDC client secret rotation (Auth0)

1. Auth0 Dashboard → Applications → Nexus → Settings.
2. Rotate client secret; copy new value.
3. Update `OIDC_CLIENT_SECRET` in `.env`.
4. Restart Nexus.
5. Test SSO login end-to-end.

### INTEGRATIONS_ENCRYPTION_KEY rotation

1. Export existing integrations (if API supports).
2. Generate new Fernet key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. Re-encrypt `data/integrations.vault` with new key (or re-enter credentials via UI).
4. Update `.env` and restart.

### OpenAI / third-party API keys

1. Create new key in provider console.
2. Update `.env`.
3. Restart Nexus.
4. Revoke old key in provider console.
5. Verify chat/RAG/voice still work.

### Emergency rotation (secret exposed in chat, commit, or log)

1. Rotate affected secret **immediately** (steps above).
2. Review `audit_log` and access logs for unauthorized use.
3. Force SSO re-auth or session invalidation (JWT rotation covers sessions).
4. Document incident in post-mortem template.

### Evidence for auditors

Maintain a rotation log:

| Date | Secret | Rotated by | Ticket/notes |
|------|--------|------------|--------------|
| YYYY-MM-DD | JWT_SECRET | name | Scheduled quarterly |
