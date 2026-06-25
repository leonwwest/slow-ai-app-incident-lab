"""Prometheus metrics setup.

Exposes a ``/metrics`` endpoint with:

* automatic request latency histograms per route (manual prometheus_client
  metrics recorded from middleware)
* custom AI-specific counters/gauges: tokens, cost, provider latency,
  active provider calls, db query latency

Uses ``prometheus_client.make_asgi_app()`` mounted at ``/metrics`` instead of
prometheus-fastapi-instrumentator to avoid lifespan/startup-event conflicts
with FastAPI's async lifespan mode.
"""
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from app.config import settings

# Custom AI / business metrics. Defined at import time so they are
# registered once; ``prometheus_client`` handles the singleton registry.

AI_TOKENS_TOTAL = Counter(
    "ai_tokens_total",
    "Total simulated AI tokens consumed",
    ["endpoint", "user_id"],
)

AI_COST_TOTAL = Counter(
    "ai_cost_usd_total",
    "Total estimated AI cost in USD",
    ["endpoint", "user_id"],
)

AI_PROVIDER_LATENCY = Histogram(
    "ai_provider_latency_ms",
    "Simulated AI provider call latency in milliseconds",
    ["endpoint"],
    buckets=(50, 100, 250, 500, 1000, 2000, 4000, 8000, 16000),
)

AI_PROVIDER_CALLS_ACTIVE = Gauge(
    "ai_provider_calls_active",
    "Number of in-flight simulated AI provider calls",
)

AI_PROVIDER_ERRORS_TOTAL = Counter(
    "ai_provider_errors_total",
    "Total simulated AI provider errors",
    ["endpoint", "status_code"],
)

DB_QUERY_LATENCY = Histogram(
    "db_query_latency_ms",
    "Simulated database query latency in milliseconds",
    ["endpoint"],
    buckets=(50, 100, 250, 500, 1000, 2000, 4000),
)

# Request-level metrics (replaces prometheus-fastapi-instrumentator).
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "handler", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "handler", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


def record_request(method: str, handler: str, status: int, duration_s: float) -> None:
    """Record a completed HTTP request in Prometheus metrics."""
    s = str(status)
    HTTP_REQUESTS_TOTAL.labels(method=method, handler=handler, status=s).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method, handler=handler, status=s
    ).observe(duration_s)


def record_ai_call(
    endpoint: str,
    user_id: str,
    tokens: int | None,
    cost: float | None,
    provider_latency_ms: int | None,
) -> None:
    """Record a successful AI provider call in Prometheus metrics."""
    if tokens:
        AI_TOKENS_TOTAL.labels(endpoint=endpoint, user_id=user_id).inc(tokens)
    if cost is not None:
        AI_COST_TOTAL.labels(endpoint=endpoint, user_id=user_id).inc(cost)
    if provider_latency_ms is not None:
        AI_PROVIDER_LATENCY.labels(endpoint=endpoint).observe(provider_latency_ms)


def record_ai_error(endpoint: str, status_code: int) -> None:
    AI_PROVIDER_ERRORS_TOTAL.labels(
        endpoint=endpoint, status_code=status_code
    ).inc()


def record_db_query(endpoint: str, db_latency_ms: int) -> None:
    DB_QUERY_LATENCY.labels(endpoint=endpoint).observe(db_latency_ms)


def setup_metrics(app) -> bool:
    """Mount the prometheus_client ASGI app at ``/metrics``.

    Returns True if metrics are enabled, False otherwise. Always succeeds
    (prometheus_client is a hard dependency).
    """
    if not settings.enable_metrics:
        return False

    app.mount("/metrics", make_asgi_app())
    return True
