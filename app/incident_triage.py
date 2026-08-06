"""Deterministic incident classification for live or captured service statistics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def _worst_endpoint(stats: dict[str, Any], field: str) -> tuple[str | None, float]:
    endpoints = stats.get("endpoints", {})
    if not endpoints:
        return None, 0.0
    name, values = max(endpoints.items(), key=lambda item: float(item[1].get(field, 0)))
    return name, float(values.get(field, 0))


def assess_incident(stats: dict[str, Any]) -> dict[str, Any]:
    """Turn observability statistics into an explainable, dry-run decision."""
    rows = int(stats.get("rows", 0))
    error_rate = float(stats.get("error_rate_pct", 0))
    total_cost = float(stats.get("total_cost_usd", 0))
    slowest_endpoint, worst_p95 = _worst_endpoint(stats, "p95_ms")
    error_endpoint, worst_endpoint_error_rate = _worst_endpoint(stats, "error_rate_pct")

    signals = [
        {"name": "sample_size", "value": rows, "unit": "requests"},
        {"name": "error_rate", "value": error_rate, "unit": "percent"},
        {
            "name": "worst_p95_latency",
            "value": worst_p95,
            "unit": "milliseconds",
            "endpoint": slowest_endpoint,
        },
        {"name": "window_cost", "value": total_cost, "unit": "USD"},
    ]

    if rows < 20:
        severity, state = "SEV4", "insufficient-data"
    elif error_rate >= 20 or worst_p95 >= 5000:
        severity, state = "SEV1", "incident"
    elif error_rate >= 5 or worst_p95 >= 2000 or total_cost >= 5:
        severity, state = "SEV2", "incident"
    elif error_rate >= 1 or worst_p95 >= 1000 or total_cost >= 1:
        severity, state = "SEV3", "degraded"
    else:
        severity, state = "SEV4", "healthy"

    hypotheses: list[dict[str, str]] = []
    if slowest_endpoint in {"/chat", "/chat/slow"} and worst_p95 >= 2000:
        hypotheses.append(
            {
                "rank": "high",
                "component": "ai-provider",
                "reason": f"{slowest_endpoint} has the highest P95 latency",
                "next_evidence": "Compare provider spans and provider_latency_ms with total latency",
            }
        )
    if slowest_endpoint == "/db-query" and worst_p95 >= 1000:
        hypotheses.append(
            {
                "rank": "high",
                "component": "database",
                "reason": "The database exercise is the slowest endpoint",
                "next_evidence": "Inspect db_latency_ms and the slow-query SQL report",
            }
        )
    if worst_endpoint_error_rate >= 5:
        hypotheses.append(
            {
                "rank": "medium",
                "component": "request-path",
                "reason": f"{error_endpoint} has a {worst_endpoint_error_rate:.2f}% error rate",
                "next_evidence": "Group structured logs by status and error_message",
            }
        )
    if total_cost >= 1:
        hypotheses.append(
            {
                "rank": "medium",
                "component": "cost-control",
                "reason": f"Observed window cost is ${total_cost:.2f}",
                "next_evidence": "Compare provider calls, tokens, cache hits and retry volume",
            }
        )
    if not hypotheses:
        hypotheses.append(
            {
                "rank": "low",
                "component": "none",
                "reason": "No configured latency, error or cost threshold is breached",
                "next_evidence": "Continue monitoring the rolling window",
            }
        )

    confidence = "low" if rows < 20 else "medium" if rows < 100 else "high"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "window": stats.get("window", "unknown"),
        "decision": {
            "state": state,
            "severity": severity,
            "confidence": confidence,
            "summary": f"{severity} {state}: {rows} requests, {error_rate:.2f}% errors, "
            f"worst P95 {worst_p95:.0f} ms",
        },
        "signals": signals,
        "hypotheses": hypotheses,
        "recommended_actions": [
            "Capture the dashboard window, deployment version and three representative traces",
            "Validate the highest-ranked hypothesis with logs, metrics and traces",
            "Use the runbook decision tree before changing service state",
            "Record the outcome and prevention work in the postmortem template",
        ],
        "automation": {
            "mode": "dry-run",
            "executed_actions": [],
            "safe_actions": ["classify", "collect-evidence", "draft-incident-update"],
            "approval_required": ["restart", "scale", "rollback", "rotate-credentials"],
            "reason": "State-changing remediation requires an operator decision in this lab",
        },
    }
