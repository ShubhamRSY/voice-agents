import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8001";
const VUS = Number(__ENV.VUS || 10);
const DURATION = __ENV.DURATION || "30s";

const healthLatency = new Trend("nexus_health_latency_ms", true);
const apiLatency = new Trend("nexus_api_latency_ms", true);
const errorRate = new Rate("nexus_errors");

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    nexus_health_latency_ms: ["p(95)<500"],
    nexus_api_latency_ms: ["p(95)<2000"],
    nexus_errors: ["rate<0.05"],
    http_req_failed: ["rate<0.05"],
  },
};

export default function () {
  const health = http.get(`${BASE_URL}/api/v1/health`);
  healthLatency.add(health.timings.duration);
  const healthOk = check(health, {
    "health status 200": (r) => r.status === 200,
    "health body": (r) => r.json("status") === "healthy",
  });
  errorRate.add(!healthOk);

  const obs = http.get(`${BASE_URL}/api/v1/observability/health`);
  apiLatency.add(obs.timings.duration);
  const obsOk = check(obs, {
    "observability status 200": (r) => r.status === 200,
  });
  errorRate.add(!obsOk);

  const metrics = http.get(`${BASE_URL}/api/v1/metrics`);
  check(metrics, {
    "metrics status 200": (r) => r.status === 200,
    "metrics has nexus_": (r) => r.body.includes("nexus_"),
  });

  sleep(1);
}

export function handleSummary(data) {
  const p95Health = data.metrics.nexus_health_latency_ms?.values?.["p(95)"] ?? "n/a";
  const p95Api = data.metrics.nexus_api_latency_ms?.values?.["p(95)"] ?? "n/a";
  console.log(`\n--- Performance summary ---`);
  console.log(`Health p95: ${p95Health} ms (budget: 500 ms)`);
  console.log(`API p95:    ${p95Api} ms (budget: 2000 ms)`);
  return {
    stdout: JSON.stringify(data, null, 2),
  };
}
