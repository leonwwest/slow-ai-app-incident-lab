"""Diagnostic endpoints that simulate database slowness and random failures."""
import random
import time
from contextlib import nullcontext

from fastapi import APIRouter, HTTPException, Request

from app.database import get_connection
from app.metrics import record_db_query
from app.tracing import get_tracer

router = APIRouter(tags=["diagnostics"])


@router.get("/random-error")
async def random_error(request: Request) -> dict:
    """Return one of 500/429/401/503 at random to exercise error-rate analysis."""
    status_code = random.choices(
        [500, 429, 401, 503],
        weights=[0.4, 0.25, 0.15, 0.2],
    )[0]
    messages = {
        500: "internal server error: unhandled exception in worker",
        429: "rate limit exceeded: too many requests",
        401: "unauthorized: api key missing or invalid",
        503: "provider unavailable: upstream timeout",
    }
    request.state.error_message = messages[status_code]
    raise HTTPException(status_code=status_code, detail=messages[status_code])


@router.get("/db-query")
async def db_query(request: Request) -> dict:
    """Simulate a slow database query (missing index + large scan).

    Runs a real SQLite recursive-CTE scan (or Postgres equivalent via
    generate_series) and adds a random artificial delay so latency is
    measurable and reproducible under load. db_latency_ms is recorded on
    request.state so it shows up in logs and the DB, plus a Prometheus
    histogram and an OTel span.
    """
    tracer = get_tracer()
    delay_ms = random.randint(300, 1500)
    start = time.perf_counter()

    query_sqlite = """
        WITH RECURSIVE seq(n) AS (
            SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 5000
        )
        SELECT COUNT(*) AS cnt, AVG(n) AS avg_n FROM seq
    """
    query_postgres = """
        SELECT COUNT(*) AS cnt, AVG(n) AS avg_n
        FROM generate_series(1, 5000) AS seq(n)
    """

    span_ctx = (
        tracer.start_as_current_span(
            "db_query", attributes={"endpoint": "/db-query", "delay_ms": delay_ms}
        )
        if tracer
        else nullcontext()
    )

    with span_ctx:
        time.sleep(delay_ms / 1000.0)
        from app.config import settings

        sql = query_postgres if settings.db_backend == "postgres" else query_sqlite
        with get_connection() as conn:
            row = conn.execute(sql).fetchone()

    db_latency_ms = int((time.perf_counter() - start) * 1000)
    request.state.db_latency_ms = db_latency_ms
    request.state.error_message = None
    record_db_query("/db-query", db_latency_ms)
    return {
        "request_id": request.state.request_id,
        "row_count": row["cnt"],
        "avg_n": row["avg_n"],
        "db_latency_ms": db_latency_ms,
        "note": "simulated slow query: recursive scan without benefit of an index",
    }
