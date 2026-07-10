# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.5.x   | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in Nexus, please report it responsibly:

1. **Do not** open a public GitHub issue for security-sensitive findings.
2. Email the maintainer via the contact listed on the [GitHub profile](https://github.com/ShubhamRSY).
3. Include a clear description, reproduction steps, and impact assessment.

We aim to acknowledge reports within **72 hours** and provide a remediation timeline when possible.

## Production Deployment Checklist

Before exposing Nexus to the public internet, configure:

| Variable | Requirement |
|----------|-------------|
| `APP_ENV` | Set to `production` (disables `/docs`, `/openapi.json`, `/demo/reset`) |
| `AUTH_REQUIRED` | Set to `true` |
| `JWT_SECRET` | Strong random value (`openssl rand -hex 32`) |
| `INTEGRATIONS_ENCRYPTION_KEY` | Fernet key for credential vault |
| `CORS_ORIGINS` | Your domain(s) only — never `*` |
| `DEMO_MODE` | `false` in production |
| `POSTGRES_PASSWORD` | Strong, unique password (required — no default in docker-compose) |
| `REDIS_PASSWORD` | Strong, unique password (required for Redis in docker-compose) |
| `REDIS_URL` | Must include password in production, e.g. `redis://:PASSWORD@redis:6379/0` |
| `SETTINGS_ADMIN_TOKEN` | Required for credential API writes |
| `TWILIO_AUTH_TOKEN` | Required for voice; enables webhook signature validation |

## Security Features

- **JWT authentication** with Argon2 password hashing
- **Twilio webhook signature validation** when `TWILIO_AUTH_TOKEN` is configured
- **WebSocket auth** when `AUTH_REQUIRED=true` (token via query param or `Authorization` header)
- **Encrypted integrations vault** (AES-256-GCM via Fernet)
- **Optional HashiCorp Vault** overlay for secrets
- **Rate limiting** (Redis-backed with in-memory fallback)
- **CORS enforcement** — wildcard `*` rejected when `APP_ENV=production` or `staging`
- **Redis authentication** in Docker Compose stack
- **CI security scanning** — Bandit (SAST) + pip-audit on every PR
- **Staging environment** — `docker-compose.staging.yml` + `develop` branch deploy job
- **Non-root Docker user** (`appuser`)

## Known Development Defaults

These defaults are intentional for local development but **must be changed for production**:

- `AUTH_REQUIRED=false` — API endpoints are open without a token
- `DEMO_MODE=false` — demo users are not seeded unless explicitly enabled
- `CORS_ORIGINS=*` — permissive CORS in development only (rejected at startup in production/staging)
- Auto-generated JWT secret file when `JWT_SECRET` is unset (use a persistent secret in production)

## Dependency Updates

Runtime dependencies are pinned in `pyproject.toml`. Review and update regularly, especially for:

- `cryptography`, `pyjwt`, `passlib`
- `fastapi`, `uvicorn`, `gunicorn`
- `twilio`, `redis`, `psycopg2-binary`

Run `pip install -e ".[dev]"` and `pytest tests/` after upgrading dependencies.

`pip-audit` runs in CI on pinned `pyproject.toml` dependencies. **ChromaDB PYSEC-2026-311** is ignored until a fixed release exists on PyPI — Nexus uses embedded `PersistentClient` (not a public Chroma FastAPI server). Do not expose `CHROMA_SERVER_URL` to the internet without network ACLs.

## Security-Related Endpoints

| Endpoint | Production behavior |
|----------|---------------------|
| `/docs`, `/redoc`, `/openapi.json` | Disabled when `APP_ENV=production` |
| `/api/v1/demo/reset` | Returns 404 when `APP_ENV=production` or `DEMO_MODE=false` |
| `/api/v1/telephony/voice/*` | Requires valid Twilio signature when auth token is set |
| `/api/v1/chat/stream` | Requires JWT when `AUTH_REQUIRED=true` |
