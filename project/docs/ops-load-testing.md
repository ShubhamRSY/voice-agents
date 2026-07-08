## Load testing

### Performance budgets

| Endpoint | p95 budget | Notes |
|----------|------------|-------|
| `GET /api/v1/health` | < 500 ms | Uptime probe |
| `GET /api/v1/observability/health` | < 2000 ms | Ops dashboard |
| `POST /api/v1/chat` (mock) | < 2000 ms | See `config/evaluation/benchmarks.json` |

### Prerequisites

Install [k6](https://k6.io/docs/get-started/installation/):

```bash
# macOS
brew install k6

# Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

### Smoke test (local)

```bash
cd project
k6 run scripts/loadtest/k6-smoke.js
```

### Smoke test (production)

Run from your laptop against the public URL — start with low VUs:

```bash
BASE_URL=https://yournexus.duckdns.org VUS=5 DURATION=30s \
  k6 run scripts/loadtest/k6-smoke.js
```

k6 exits non-zero if thresholds fail.

### Chat load test (authenticated)

For chat endpoints, create a test user and pass a JWT:

```bash
# 1. Register/login and copy token
TOKEN="eyJ..."

# 2. Extend k6 script or use curl loop:
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} %{time_total}\n" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"hello","session_id":"load-test"}' \
    https://your-domain.com/api/v1/chat
done
```

### CI integration (optional)

Add a nightly workflow that runs k6 against a staging URL with `VUS=3` and `DURATION=15s`.

### Interpreting results

- **p95 latency above budget:** check VM CPU/RAM (`htop`), SQLite lock contention, OpenAI API latency.
- **High error rate:** check `journalctl -u nexus` and `/api/v1/observability/health` for `http_5xx`.
- **429 responses:** rate limit hit — increase `RATE_LIMIT_RPM` or reduce VUs.
