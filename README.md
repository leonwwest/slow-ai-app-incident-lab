# Slow AI App Incident Lab

A deliberately slow AI/web app for practising **production-style debugging**:
P95/P99 latency analysis, error-rate investigation, structured logging,
trace-based reasoning, IAM/API-key checks, network/DNS debugging, cloud cost
analysis, scaling review and rollback strategy.

The goal is **not** to build another AI chatbot. The goal is to show you can
systematically analyse *why* a cloud/AI application is slow, expensive or
unstable — the kind of work Cloud Engineers, DevOps and SREs do every day.

---

## Project Overview

This lab simulates an AI web app that suddenly became slow. Users report:

> "The app takes forever to load."
> "Sometimes I get an error."
> "AI answers take much longer than yesterday."
> "Costs suddenly went up."

Your job is to find out:

1. Is the frontend slow or the API?
2. Is the database slow?
3. Is the external AI provider slow?
4. Are there errors from API-key / IAM issues?
5. Are there network or DNS problems?
6. Is the app not scaling?
7. Should we roll back?

The project ships with a running demo app, artificial slowness, simulated
failures, structured JSON logs, a request log database, three observability
SQL queries, a load test and a step-by-step incident runbook.

---

## Architecture

```text
User / Browser
      |
      v
Frontend or API client (k6, curl, browser)
      |
      v
Backend API (FastAPI, port 8010)
  - GET  /health         liveness probe
  - POST /chat           normal AI request
  - POST /chat/slow      slow AI request (2-8s, high P95/P99)
  - GET  /random-error   random 500/429/401/503
  - GET  /db-query       slow database query
      |
      +--> SQLite (request_logs)
      |
      +--> Simulated AI provider (in-process delay + failures)
      |
      +--> Structured JSON logs (stdout)  +  request_logs table
```

All requests flow through `RequestLoggingMiddleware`, which assigns a
`request_id`, measures latency, collects per-call extras
(`provider_latency_ms`, `db_latency_ms`, `tokens_used`,
`estimated_cost_usd`, `error_message`) and persists one row to
`request_logs` while emitting one JSON log line.

---

## Tech Stack

| Layer       | Choice                          | Notes                                  |
|-------------|---------------------------------|----------------------------------------|
| Backend     | FastAPI                         | async, OpenAPI docs at `/docs`         |
| Database    | SQLite (default) / PostgreSQL   | switch via `DB_BACKEND=postgres`       |
| Logs        | JSON to stdout                  | pipe into Loki / jq / any log shipper  |
| Metrics     | Prometheus (`/metrics`)         | custom AI counters + request histograms|
| Dashboard   | Grafana (auto-provisioned)      | `docker compose up` loads dashboard    |
| Tracing     | OpenTelemetry -> Jaeger (OTLP)  | spans for provider + db calls          |
| Load test   | k6                              | mixed-traffic scenarios                |
| Analysis    | `scripts/analyze.py`            | P50/P95/P99, error rate, cost          |
| Observability SQL | `sql/observability_queries.sql` | Postgres dialect, 3 queries     |
| CI          | GitHub Actions                  | lint + smoke test on every push        |
| Container   | Docker Compose                  | app + postgres + prometheus + grafana + jaeger |

---

## How to Run

### Prerequisites

- Python 3.11+ (tested on 3.14)
- [k6](https://k6.io/docs/get-started/installation/) (only for load tests)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. (Optional) Configure environment

```bash
cp .env.example .env
```

Leave `AI_API_KEY` empty to reproduce the example incident's 401 failures, or
set it to any value to "fix" IAM. Set `DB_BACKEND=postgres` to use the
Postgres backend (default is zero-setup SQLite).

### 3. Start the server

```bash
python run.py
# or: uvicorn app.main:app --port 8010
```

The API is now available at `http://localhost:8010` (interactive docs at
`/docs`, Prometheus metrics at `/metrics`). The SQLite database
`data/incident_lab.db` is created on first run.

### 3b. Or: run the full stack with Docker Compose

```bash
docker compose up --build
```

This starts five services:

| Service     | Port | Purpose                          |
|-------------|------|----------------------------------|
| app         | 8010 | FastAPI (Postgres backend)       |
| postgres    | 5432 | request_logs on real Postgres    |
| prometheus  | 9090 | metrics scrape + alerting rules  |
| grafana     | 3000 | auto-provisioned dashboard       |
| jaeger      | 16686| distributed traces (OTLP)        |

Grafana: `http://localhost:3000` (admin / admin). The incident dashboard is
auto-loaded. Jaeger UI: `http://localhost:16686`.

### 4. Smoke test

```bash
curl http://localhost:8010/health
curl -X POST http://localhost:8010/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Explain P95 latency in one sentence."}'
curl http://localhost:8010/db-query
curl http://localhost:8010/random-error   # expect a 4xx/5xx
```

### 5. Run a load test

```bash
k6 run k6/load-test.js
```

This runs four scenarios in parallel (`chat`, `slow-chat`, `random-error`,
`db-query`) for ~60s and produces the data the runbook is designed to analyse.

### 6. Analyse the results

```bash
python scripts/analyze.py            # last 1 hour
python scripts/analyze.py --hours 24 # last 24 hours
```

This prints a plain-text report with the three observability queries
re-implemented for SQLite (P50/P95/P99 per endpoint, error rate, AI cost per
user, cost/latency by deployment version).

The canonical PostgreSQL versions of the same queries live in
`sql/observability_queries.sql` and work as-is in Datadog, New Relic,
BigQuery, ClickHouse or a Postgres-backed log store.

---

## Endpoints

### `GET /health`

Liveness probe. Returns:

```json
{
  "status": "ok",
  "timestamp": "2026-06-25T10:00:00.000000+00:00",
  "deployment_version": "v1.4.0",
  "region": "eu-central-1"
}
```

If `/health` is slow, the app itself is down — check every other explanation
first.

### `POST /chat`

Normal AI request. Body:

```json
{ "prompt": "Explain P95 latency in one sentence.", "user_id": "user_42" }
```

Simulates: ~250-600 ms provider latency, low failure rate, token usage and
cost estimation. `user_id` is optional (a random id is generated if omitted).

### `POST /chat/slow`

Slow AI request. Same body as `/chat`. Simulates: **2-8 seconds** of provider
latency, high P95/P99, ~18 % provider timeout (503), ~1 % auth failure (401).
This is the primary suspect in the example incident.

### `GET /random-error`

Returns one of `500`, `429`, `401`, `503` at random with a matching error
message. Use it to exercise error-rate analysis and status-code triage.

### `GET /db-query`

Simulates a slow database query: a recursive CTE scan plus a random 300-1500
ms delay. Records `db_latency_ms` on the request so it shows up in logs and
the database.

---

## Simulated Failure Modes

| Failure              | Where              | How it manifests                          |
|----------------------|--------------------|-------------------------------------------|
| High P95/P99 latency | `/chat/slow`       | 2-8 s response time                       |
| Provider timeout     | `/chat/slow`       | 503, `provider_latency_ms` in logs        |
| IAM / API-key error  | `/chat`, `/chat/slow` | 401 when `AI_API_KEY` is empty          |
| Rate limit           | `/random-error`    | 429                                       |
| Internal error       | `/random-error`    | 500                                       |
| Provider unavailable | `/random-error`    | 503                                       |
| Slow DB query        | `/db-query`        | elevated `db_latency_ms`                  |
| Cost spike           | `/chat/slow`       | higher tokens + cost per request          |

The current deployment version is `v1.4.0` by default. Set
`DEPLOYMENT_VERSION=v1.3.2` in `.env` to simulate the "known-good" version
before a rollback.

---

## Observability Queries

Three canonical queries live in [`sql/observability_queries.sql`](sql/observability_queries.sql):

1. **P50 / P95 / P99 latency per endpoint** — find which endpoints are slow.
2. **Error rate by status code and endpoint** — find where errors originate
   and classify them (4xx = client/IAM, 5xx = server/upstream/provider).
3. **AI cost and token usage per user / endpoint** — detect abuse, retry
   loops or oversized prompts driving cost. Includes a per-deployment-version
   cost/latency/error summary for rollback correlation.

They are written in PostgreSQL dialect (`PERCENTILE_CONT`, window functions)
and run as-is against Postgres-backed log stores, BigQuery, ClickHouse,
Datadog and New Relic. For the local SQLite database, run
`python scripts/analyze.py` which re-implements the same logic in Python.

---

## Incident Runbook

The full step-by-step runbook is in [`docs/RUNBOOK.md`](docs/RUNBOOK.md) and
covers all ten analysis steps:

1. Incident einordnen
2. P95/P99-Latenz prüfen
3. Error Rate prüfen
4. Logs prüfen
5. Traces prüfen
6. IAM/API-Key prüfen
7. Netzwerk und DNS prüfen
8. Cloud-Kosten prüfen
9. Skalierung prüfen
10. Rollback prüfen

A worked example incident (timeline, findings, recommended actions) is in
[`docs/INCIDENT_EXAMPLE.md`](docs/INCIDENT_EXAMPLE.md).

---

## Example Findings

After a 60s `k6` run against the default configuration you should observe
findings close to:

```text
Finding 1:
P95 latency for /chat/slow reached ~6.5 seconds.
Root cause: simulated AI provider delay (2-8s) plus ~18% timeout rate.

Finding 2:
Error rate for /random-error reached ~100%.
Root cause: intentional random 500/429/401/503.

Finding 3:
401 errors appear on /chat and /chat/slow when AI_API_KEY is unset.
Root cause: IAM / API-key not configured (simulated secret-manager mismatch).

Finding 4:
AI cost simulation shows higher cost per /chat/slow request than /chat.
Root cause: no rate limit and no caching; slow path uses an "expensive" model.

Recommended actions:
- Add request timeout after 5 seconds.
- Add retry limit with exponential backoff.
- Add caching for repeated prompts.
- Add per-user rate limit.
- Add fallback model for high-latency provider responses.
- Add alert for P95 > 2 seconds on /chat/slow.
- Add alert for Error Rate > 1% on any endpoint.
```

---

## Next Improvements

Optional upgrades that make this lab even stronger for a CV:

- Alertmanager service in docker-compose (alerts defined in `prometheus/alerts.yml`)
- Deploy to Render / Railway / Fly.io / Cloudflare Workers
- Feature flags + canary deployment simulation
- Blue-green deployment and rollback via GitHub Action

---

## Project Structure

```text
slow-ai-app-incident-lab/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan + middleware + metrics/tracing wiring
│   ├── config.py            # settings (env-driven, .env support)
│   ├── database.py          # SQLite + Postgres backend abstraction
│   ├── logging_setup.py     # JSON logging
│   ├── middleware.py        # request logging + latency + request_id
│   ├── metrics.py           # Prometheus metrics (custom AI counters/histograms)
│   ├── tracing.py           # OpenTelemetry setup (OTLP -> Jaeger)
│   ├── ai_provider.py       # simulated provider (delay, 401, 503, cost, spans, metrics)
│   └── routers/
│       ├── __init__.py      # api_router aggregation
│       ├── health.py        # GET /health
│       ├── chat.py          # POST /chat, POST /chat/slow
│       └── diagnostics.py   # GET /random-error, GET /db-query
├── scripts/
│   └── analyze.py           # local observability report (P50/P95/P99, errors, cost)
├── sql/
│   ├── schema.sql           # canonical Postgres schema
│   └── observability_queries.sql  # 3 Postgres observability queries
├── k6/
│   ├── load-test.js         # mixed-traffic load test
│   └── curl-format.txt      # curl timing breakdown for DNS/network checks
├── prometheus/
│   ├── prometheus.yml       # scrape config
│   └── alerts.yml           # alerting rules (P95, error rate, cost spike)
├── grafana/
│   ├── provisioning/        # datasource + dashboard provider (auto-load)
│   └── dashboards/
│       └── incident-dashboard.json  # 8-panel dashboard (latency, errors, cost, traces)
├── docs/
│   ├── RUNBOOK.md           # 10-step incident analysis runbook
│   ├── INCIDENT_EXAMPLE.md  # worked example: timeline + findings
│   └── POSTMORTEM_TEMPLATE.md  # blank postmortem template
├── .github/workflows/
│   └── ci.yml               # GitHub Actions: lint + smoke test
├── data/                    # SQLite db + logs (gitignored)
├── .env.example
├── .gitignore
├── Dockerfile               # app container image
├── docker-compose.yml       # app + postgres + prometheus + grafana + jaeger
├── requirements.txt
├── run.py                   # `python run.py` launcher
└── README.md
```

---

## CV Bullet

> Built a mini observability lab for diagnosing slow AI/web applications,
> including P95/P99 latency analysis, error-rate investigation, structured
> logging, tracing concepts, IAM/API-key checks, network/DNS debugging, cost
> analysis, scaling review, rollback strategy and SQL-based observability
> queries.

Deutsch:

> Entwicklung eines Mini-Observability-Labs zur Analyse langsamer AI-/Web-Apps
> mit P95/P99-Latenzanalyse, Error-Rate-Auswertung, strukturierten Logs,
> Tracing-Konzepten, IAM/API-Key-Checks, Netzwerk-/DNS-Debugging,
> Cloud-Kostenanalyse, Skalierungsprüfung, Rollback-Strategie und
> SQL-Abfragen für Observability-Tools.
