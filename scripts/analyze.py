"""Run the observability queries against the local SQLite log database.

Usage:
    python scripts/analyze.py            # last 1 hour
    python scripts/analyze.py --hours 24 # last 24 hours

This re-implements the three observability queries from
sql/observability_queries.sql in pure SQLite + Python (SQLite has no native
PERCENTILE_CONT). Output is a plain-text report suitable for pasting into an
incident ticket.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running both as `python scripts/analyze.py` from the repo root and
# as a module. The DB path mirrors app.config.settings default.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402


def percentile(values: list[int], p: float) -> int:
    """Linear-interpolation percentile matching PERCENTILE_CONT semantics."""
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


def fmt_table(rows: list[list], headers: list[str]) -> str:
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    sep = "  ".join("-" * w for w in widths)
    lines = ["  ".join(str(h).ljust(w) for h, w in zip(headers, widths)), sep]
    for r in rows:
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze request_logs.")
    parser.add_argument("--hours", type=float, default=1.0, help="lookback window in hours")
    parser.add_argument("--db", default=settings.db_path, help="path to SQLite db")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[!] Database not found at {db_path}.")
        print("    Start the app and run a load test first (see README.md).")
        return 1

    since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)).isoformat()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM request_logs WHERE timestamp >= ? ORDER BY timestamp",
        (since,),
    ).fetchall()

    if not rows:
        print(f"[!] No request logs in the last {args.hours}h.")
        print("    Run the k6 load test:  k6 run k6/load-test.js")
        return 1

    print(f"\n=== Slow AI App Incident Lab - Observability Report ===")
    print(f"Window: last {args.hours}h  |  rows: {len(rows)}\n")

    # --- Query 1: latency per endpoint ---
    by_endpoint: dict[str, list[int]] = {}
    for r in rows:
        by_endpoint.setdefault(r["endpoint"], []).append(r["latency_ms"])

    q1_rows = []
    for endpoint, lats in sorted(by_endpoint.items(), key=lambda kv: percentile(kv[1], 0.95), reverse=True):
        q1_rows.append([
            endpoint,
            len(lats),
            round(sum(lats) / len(lats)),
            percentile(lats, 0.50),
            percentile(lats, 0.95),
            percentile(lats, 0.99),
            max(lats),
        ])
    print("Query 1 - latency per endpoint (ms):")
    print(fmt_table(q1_rows, ["endpoint", "count", "avg", "p50", "p95", "p99", "max"]))
    print()

    # --- Query 2: error rate per endpoint ---
    q2_rows = []
    for endpoint in sorted(by_endpoint):
        total = len(by_endpoint[endpoint])
        errs = [r for r in rows if r["endpoint"] == endpoint and r["status_code"] >= 400]
        rate = round(len(errs) * 100.0 / total, 2) if total else 0.0
        q2_rows.append([endpoint, total, len(errs), rate])
    q2_rows.sort(key=lambda r: r[3], reverse=True)
    print("Query 2 - error rate per endpoint:")
    print(fmt_table(q2_rows, ["endpoint", "requests", "errors", "error_rate_%"]))
    print()

    # Error breakdown by status code
    status_counts: dict[tuple[str, int], int] = {}
    for r in rows:
        if r["status_code"] >= 400:
            status_counts[(r["endpoint"], r["status_code"])] = status_counts.get((r["endpoint"], r["status_code"]), 0) + 1
    if status_counts:
        q2b_rows = [[ep, sc, c] for (ep, sc), c in sorted(status_counts.items(), key=lambda kv: kv[1], reverse=True)]
        print("Query 2b - errors by endpoint / status code:")
        print(fmt_table(q2b_rows, ["endpoint", "status", "count"]))
        print()

    # --- Query 3: AI cost per user / endpoint ---
    ai = [r for r in rows if r["tokens_used"] is not None]
    cost_map: dict[tuple[str, str], dict] = {}
    for r in ai:
        key = (r["user_id"], r["endpoint"])
        agg = cost_map.setdefault(key, {"requests": 0, "tokens": 0, "cost": 0.0, "latency": 0})
        agg["requests"] += 1
        agg["tokens"] += r["tokens_used"] or 0
        agg["cost"] += r["estimated_cost_usd"] or 0.0
        agg["latency"] += r["latency_ms"]
    if cost_map:
        q3_rows = []
        for (user_id, endpoint), agg in cost_map.items():
            q3_rows.append([
                user_id, endpoint, agg["requests"], agg["tokens"],
                round(agg["cost"], 4),
                round(agg["tokens"] / agg["requests"], 2),
                round(agg["latency"] / agg["requests"], 2),
            ])
        q3_rows.sort(key=lambda r: r[4], reverse=True)
        print("Query 3 - AI cost / tokens per user / endpoint:")
        print(fmt_table(q3_rows, ["user_id", "endpoint", "reqs", "tokens", "cost_usd", "avg_tok", "avg_lat"]))
        print()

    # --- Cost by deployment version (rollback correlation) ---
    ver_map: dict[str, dict] = {}
    for r in rows:
        v = r["deployment_version"] or "unknown"
        agg = ver_map.setdefault(v, {"requests": 0, "cost": 0.0, "latency": 0, "errors": 0})
        agg["requests"] += 1
        agg["cost"] += r["estimated_cost_usd"] or 0.0
        agg["latency"] += r["latency_ms"]
        if r["status_code"] >= 400:
            agg["errors"] += 1
    ver_rows = []
    for v, agg in sorted(ver_map.items()):
        ver_rows.append([
            v, agg["requests"], round(agg["cost"], 4),
            round(agg["latency"] / agg["requests"], 2),
            round(agg["errors"] * 100.0 / agg["requests"], 2),
        ])
    print("Cost / latency / error rate by deployment version:")
    print(fmt_table(ver_rows, ["version", "requests", "cost_usd", "avg_lat", "err_%"]))
    print()

    total_cost = sum(r["estimated_cost_usd"] or 0.0 for r in rows)
    total_errors = sum(1 for r in rows if r["status_code"] >= 400)
    print(f"Totals: requests={len(rows)}  errors={total_errors}  "
          f"error_rate={round(total_errors*100.0/len(rows),2)}%  "
          f"estimated_cost=${round(total_cost,4)}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
