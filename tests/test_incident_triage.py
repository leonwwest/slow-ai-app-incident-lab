from app.incident_triage import assess_incident


def test_degraded_ai_path_is_classified_and_explained() -> None:
    report = assess_incident(
        {
            "window": "1h",
            "rows": 240,
            "error_rate_pct": 8.75,
            "total_cost_usd": 2.48,
            "endpoints": {
                "/chat/slow": {"p95_ms": 4380, "error_rate_pct": 17.5},
                "/db-query": {"p95_ms": 1310, "error_rate_pct": 0},
            },
        }
    )

    assert report["decision"] == {
        "state": "incident",
        "severity": "SEV2",
        "confidence": "high",
        "summary": "SEV2 incident: 240 requests, 8.75% errors, worst P95 4380 ms",
    }
    assert report["hypotheses"][0]["component"] == "ai-provider"
    assert report["automation"]["mode"] == "dry-run"
    assert report["automation"]["executed_actions"] == []


def test_sparse_window_does_not_trigger_unsafe_remediation() -> None:
    report = assess_incident({"window": "1h", "rows": 3, "endpoints": {}})

    assert report["decision"]["state"] == "insufficient-data"
    assert report["decision"]["confidence"] == "low"
    assert "rollback" in report["automation"]["approval_required"]


def test_healthy_window_stays_low_severity() -> None:
    report = assess_incident(
        {
            "window": "1h",
            "rows": 120,
            "error_rate_pct": 0.2,
            "total_cost_usd": 0.12,
            "endpoints": {"/chat": {"p95_ms": 480, "error_rate_pct": 0.2}},
        }
    )

    assert report["decision"]["state"] == "healthy"
    assert report["decision"]["severity"] == "SEV4"
