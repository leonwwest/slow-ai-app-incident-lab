"""Live stats endpoint returning observability summary as JSON.

Useful for external dashboards, Slack bots, or quick curl checks without
running the full SQL analysis script.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter

from app.cache import get_cache
from app.config import settings
from app.rate_limit import get_rate_limiter

router = APIRouter(prefix="/api", tags=["stats"])


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    frac = rank - lo
    return int(xs[lo] + (xs[hi] - xs[lo]) * frac)


@router.get("/stats")
async def stats() -> dict:
    """Return a live observability summary from the request_logs table."""
    db_path = Path(settings.db_path)
    if not db_path.exists():
        return {"error": "database not yet initialized", "rows": 0}

    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM request_logs WHERE timestamp >= ? ORDER BY timestamp",
        (since,),
    ).fetchall()
    conn.close()

    if not rows:
        return {"rows": 0, "message": "no requests in the last hour"}

    by_endpoint: dict[str, list[int]] = {}
    errors = 0
    total_cost = 0.0
    total_tokens = 0

    for r in rows:
        ep = r["endpoint"]
        by_endpoint.setdefault(ep, []).append(r["latency_ms"])
        if r["status_code"] >= 400:
            errors += 1
        total_cost += r["estimated_cost_usd"] or 0.0
        total_tokens += r["tokens_used"] or 0

    total = len(rows)
    endpoints = {}
    for ep, lats in by_endpoint.items():
        ep_errors = sum(1 for r in rows if r["endpoint"] == ep and r["status_code"] >= 400)
        ep_total = len(lats)
        endpoints[ep] = {
            "requests": ep_total,
            "avg_latency_ms": round(sum(lats) / len(lats)),
            "p50_ms": _percentile(lats, 0.50),
            "p95_ms": _percentile(lats, 0.95),
            "p99_ms": _percentile(lats, 0.99),
            "max_ms": max(lats),
            "errors": ep_errors,
            "error_rate_pct": round(ep_errors * 100.0 / ep_total, 2) if ep_total else 0.0,
        }

    result: dict = {
        "window": "1h",
        "rows": total,
        "total_requests": total,
        "total_errors": errors,
        "error_rate_pct": round(errors * 100.0 / total, 2),
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "deployment_version": settings.deployment_version,
        "endpoints": endpoints,
    }

    cache = get_cache()
    if cache:
        result["cache"] = cache.stats()

    limiter = get_rate_limiter()
    result["rate_limiting_enabled"] = limiter is not None

    return result
