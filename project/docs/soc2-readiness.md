## SOC 2 readiness checklist

This is a **starter evidence pack** for teams pursuing SOC 2 Type I/II. It maps Nexus controls to common Trust Services Criteria (TSC). Process policies require legal/compliance review before an audit.

### CC6 — Logical and physical access

| Control | Status | Evidence |
|---------|--------|----------|
| JWT authentication on API | Implemented | `src/auth.py`, `AUTH_REQUIRED=true` |
| OIDC SSO (Auth0/Okta/Azure AD) | Implemented | `docs/ops-oidc-auth0.md` |
| Role-based access (`admin`, `agent`) | Implemented | User `role` column, `require_auth` deps |
| Registration lock after bootstrap | Implemented | `ALLOW_REGISTRATION=false` |
| Secrets in `.env`, not in git | Required | `.gitignore`, `config/environment/.env` |
| TLS in production | Required | Caddy / reverse proxy |
| SSH key access to VM | Operational | Oracle Cloud console, key-only SSH |

See: [access-controls.md](./soc2/access-controls.md)

### CC7 — System operations

| Control | Status | Evidence |
|---------|--------|----------|
| Health monitoring | Implemented | UptimeRobot + `/api/v1/health` |
| Metrics & error counters | Implemented | `/api/v1/metrics`, `MetricsMiddleware` |
| Structured logs | Implemented | `journalctl -u nexus`, structlog JSON |
| Daily backups | Implemented | `nexus-backup.timer`, `scripts/backup.sh` |
| Restore drill | Implemented | `scripts/restore-drill.sh`, `docs/ops-dr-runbook.md` |
| Load testing | Implemented | `scripts/loadtest/k6-smoke.js` |

See: [ops-monitoring.md](./ops-monitoring.md), [ops-dr-runbook.md](./ops-dr-runbook.md)

### CC8 — Change management

| Control | Status | Evidence |
|---------|--------|----------|
| Version control (Git) | Required | GitHub repository |
| CI tests on PR | Implemented | `.github/workflows` |
| Deployment runbooks | Implemented | `docs/ops-*.md` |
| Audit log for config/KB changes | Implemented | `audit_log` table, `/api/v1/audit` |

### CC9 — Risk mitigation

| Control | Status | Evidence |
|---------|--------|----------|
| Rate limiting | Implemented | `RateLimitMiddleware` |
| Input guardrails | Implemented | Orchestrator guardrails |
| Key rotation procedures | Documented | [key-rotation.md](./soc2/key-rotation.md) |
| Incident response | Documented | `docs/ops-dr-runbook.md` incident checklist |

### Audit log actions (automatic)

| Action | Trigger |
|--------|---------|
| `auth.login.success` / `auth.login.failed` | Password login |
| `auth.oidc.login` / `auth.oidc.failed` | SSO login |
| `tenant.created` | Registration |
| `kb.article.*` | Knowledge base CRUD |
| `integrations.*` | Integration credential changes |
| `chat.message` | Chat messages |

Query: `GET /api/v1/audit?limit=100` (authenticated admin).

### Evidence collection (before audit)

- [ ] Export 90 days of `journalctl -u nexus` logs
- [ ] Export `audit_log` table: `sqlite3 data/nexus.db ".dump audit_log"`
- [ ] Screenshot UptimeRobot monitor history
- [ ] Backup timer status: `systemctl status nexus-backup.timer`
- [ ] Restore drill output: `./scripts/restore-drill.sh`
- [ ] Load test report: `k6 run scripts/loadtest/k6-smoke.js`
- [ ] List of users + roles (redacted export)
- [ ] Auth0/Okta admin access review
- [ ] Signed access-control policy (see access-controls.md template)

### Gaps to close before formal audit

1. **Formal policies** — information security, acceptable use, data retention (legal review).
2. **Vendor management** — Auth0, OpenAI, cloud provider DPAs.
3. **Penetration test** — annual third-party assessment.
4. **Employee training** — security awareness records.
5. **PostgreSQL** — migrate from SQLite for production multi-tenant scale (see HA doc).

### Next review

Schedule quarterly review of this checklist. Update evidence paths when infrastructure changes.
