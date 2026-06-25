-- Observability queries for the Slow AI App Incident Lab.
--
-- The three queries below are written in PostgreSQL dialect (they use
-- PERCENTILE_CONT and window functions) so they map directly onto tools like
-- Datadog, New Relic, BigQuery, ClickHouse or a Postgres-backed log store.
--
-- They also run against the local SQLite database via `scripts/analyze.py`,
-- which re-implements the percentile logic in Python (SQLite has no native
-- PERCENTILE_CONT). Run `python scripts/analyze.py` after a load test to see
-- the results.

-- ============================================================================
-- Query 1: P50 / P95 / P99 latency per endpoint
-- Goal: find which endpoints are slow.
-- ============================================================================
SELECT
  endpoint,
  COUNT(*) AS request_count,
  ROUND(AVG(latency_ms)) AS avg_latency_ms,
  PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
  PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency_ms,
  MAX(latency_ms) AS max_latency_ms
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY endpoint
ORDER BY p95_latency_ms DESC;

-- ============================================================================
-- Query 2: Error rate by status code and endpoint
-- Goal: find where errors originate and classify them (4xx = client/IAM,
-- 5xx = server/upstream/provider).
-- ============================================================================
SELECT
  endpoint,
  status_code,
  COUNT(*) AS total_errors,
  ROUND(
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY endpoint),
    2
  ) AS error_percentage
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
  AND status_code >= 400
GROUP BY endpoint, status_code
ORDER BY total_errors DESC;

-- Overall error rate per endpoint (errors / all requests) for quick triage:
SELECT
  endpoint,
  COUNT(*) AS total_requests,
  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors,
  ROUND(
    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
    2
  ) AS error_rate_pct
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '1 hour'
GROUP BY endpoint
ORDER BY error_rate_pct DESC;

-- ============================================================================
-- Query 3: AI cost and token usage per user / endpoint (cost spikes)
-- Goal: detect abuse, retry loops, or oversized prompts driving cost.
-- ============================================================================
SELECT
  user_id,
  endpoint,
  COUNT(*) AS ai_requests,
  SUM(tokens_used) AS total_tokens,
  ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
  ROUND(AVG(tokens_used), 2) AS avg_tokens_per_request,
  ROUND(AVG(latency_ms), 2) AS avg_latency_ms
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '24 hours'
  AND tokens_used IS NOT NULL
GROUP BY user_id, endpoint
ORDER BY total_cost_usd DESC
LIMIT 20;

-- Cost summary by deployment version - useful to correlate a cost spike with
-- a specific release during a rollback investigation:
SELECT
  deployment_version,
  COUNT(*) AS requests,
  ROUND(SUM(estimated_cost_usd), 4) AS total_cost_usd,
  ROUND(AVG(latency_ms), 2) AS avg_latency_ms,
  ROUND(
    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
    2
  ) AS error_rate_pct
FROM request_logs
WHERE timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY deployment_version
ORDER BY deployment_version;
