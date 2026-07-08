## HA & multi-region architecture

### Current state (single-region VM)

```
Internet → Caddy (TLS) → uvicorn (127.0.0.1:8001) → SQLite + local Chroma
                    ↓
              systemd (nexus.service)
```

**Single point of failure:** one VM, one SQLite file, one Chroma directory.

**Suitable for:** pilot, demo, early production (< 50 concurrent users).

### Target state — highly available (Milestone 4)

```
                    ┌─────────────┐
   Users ──────────►│  CDN/LB     │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Nexus pod 1  Nexus pod 2  Nexus pod N   (stateless)
              │            │            │
              └────────────┼────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
   PostgreSQL          Redis            Chroma server
   (primary +          (cache +          (or managed
    replica)            task queue)       vector DB)
```

### Stateless application requirements

| Component | Today | HA target |
|-----------|-------|-----------|
| App process | Single uvicorn | N replicas behind load balancer |
| Sessions/JWT | Stateless JWT | Keep stateless JWT |
| SQLite | `data/nexus.db` | **PostgreSQL** with connection pooling |
| Chroma | Local disk | Chroma server URL or Pinecone/Weaviate |
| Cache/queue | In-memory fallback | **Redis** cluster |
| File uploads | Local `data/` | S3-compatible object storage |
| Secrets | `.env` file | Vault or cloud secret manager |

Enable PostgreSQL: set `DATABASE_URL=postgresql://...` in `.env`.  
Enable Chroma server: set `CHROMA_SERVER_URL=http://chroma:8000`.  
Enable Redis: set `REDIS_URL=redis://redis:6379/0`.

Docker Compose profiles in `deploy/docker/` support this topology.

### Multi-region failover (later)

**Active-passive** (recommended first):

1. **Primary region:** full stack (app + Postgres + Redis + Chroma).
2. **Secondary region:** warm standby — Postgres replica, Chroma backup sync, app scaled to 0.
3. **DNS failover:** DuckDNS or Route53 health-checked failover to secondary IP.
4. **RPO:** Postgres streaming replication (< 1 min lag).
5. **RTO:** 15–30 min (DNS TTL + app scale-up).

**Active-active** (advanced):

- Global load balancer + multi-primary Postgres (Citus/Spanner) or region-scoped tenants.
- Chroma/vector data replicated async; accept eventual consistency for KB search.
- Not recommended until single-region HA is proven.

### Failover test procedure (when HA is deployed)

1. Simulate primary failure (stop app or block health check).
2. Confirm LB removes unhealthy target within 30s.
3. Promote Postgres replica (if passive) or verify multi-AZ auto-failover.
4. Run `k6 run scripts/loadtest/k6-smoke.js` against failover endpoint.
5. Document actual RTO/RPO vs targets.

### Migration path from current VM

| Phase | Action |
|-------|--------|
| 1 | Migrate SQLite → PostgreSQL (`pg_dump` / init scripts) |
| 2 | Move Chroma to persistent volume or Chroma server |
| 3 | Add Redis; set `REDIS_URL` |
| 4 | Deploy 2+ app instances behind Caddy or cloud LB |
| 5 | Offsite backups to S3 (cross-region bucket) |
| 6 | Secondary region standby + DNS failover drill |

### Performance at scale

- **Connection pooling:** PgBouncer in front of Postgres.
- **Horizontal scale:** increase uvicorn workers or replica count; no sticky sessions needed (JWT).
- **Voice/WebSocket:** enable sticky sessions on LB for WS routes only.

See also: [ops-dr-runbook.md](./ops-dr-runbook.md), [ops-load-testing.md](./ops-load-testing.md).
