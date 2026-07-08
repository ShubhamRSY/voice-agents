## Monitoring & alerts

### Health endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/health` | Liveness (uptime probes) |
| `GET /api/v1/observability/health` | JSON dashboard: requests, errors, latency p95, auth failures |
| `GET /api/v1/metrics` | Prometheus text format |

### Metrics collected

| Metric | Description |
|--------|-------------|
| `requests_total` | All HTTP requests |
| `http_5xx_total` | Server errors |
| `http_4xx_total` | Client errors |
| `auth_failures_total` | Failed `POST /auth/login` (401) |
| `oidc_failures_total` | OIDC callback errors + HTTP 4xx/5xx on OIDC routes |
| `request_latency_ms` | Per-request latency (avg, p95 in observability health) |

### Recommended alert thresholds

Configure these in UptimeRobot, Grafana, or Datadog:

| Alert | Condition | Severity |
|-------|-----------|----------|
| **Site down** | `/api/v1/health` unreachable for 2 checks | Critical |
| **High 5xx rate** | `http_5xx_total` increase > 5 in 5 min | Critical |
| **High latency** | `request_latency_ms` p95 > 2000 ms for 5 min | Warning |
| **Auth attack / misconfig** | `auth_failures_total` > 20 in 5 min | Warning |
| **SSO failures** | `oidc_failures_total` > 5 in 5 min | Warning |

### UptimeRobot (configured)

- URL: `https://your-domain.com/api/v1/health`
- Interval: 5 minutes
- Alert: email on failure

### Prometheus scrape (optional)

```yaml
scrape_configs:
  - job_name: nexus
    static_configs:
      - targets: ["127.0.0.1:8001"]
    metrics_path: /api/v1/metrics
    scrape_interval: 30s
```

Expose port 8001 only on localhost; scrape via SSH tunnel or sidecar.

### Sentry (optional)

Set `SENTRY_DSN` in `.env` and restart Nexus. Unhandled FastAPI exceptions are reported automatically.

### Logs

```bash
sudo journalctl -u nexus -f
sudo journalctl -u nexus -n 200 --no-pager | grep -E "error|auth|oidc"
```

### In-app dashboard

Signed-in users can open the **Observability** panel in the Nexus console (calls `/api/v1/observability/health`).
