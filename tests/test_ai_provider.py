from types import SimpleNamespace

from starlette.requests import Request

from app import ai_provider


def test_provider_failures_can_be_disabled_for_deterministic_checks(monkeypatch) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/chat",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.user_id = "ci"

    monkeypatch.setattr(
        ai_provider,
        "settings",
        SimpleNamespace(
            ai_api_key="",
            enable_provider_failures=False,
            price_input_per_1k=0.01,
            price_output_per_1k=0.03,
        ),
    )
    monkeypatch.setattr(ai_provider.random, "random", lambda: 0.0)
    monkeypatch.setattr(ai_provider.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(ai_provider, "get_tracer", lambda: None)
    monkeypatch.setattr(ai_provider, "record_ai_call", lambda *_args: None)

    result = ai_provider.simulate_provider_call(
        request,
        delay_ms=0,
        timeout_probability=1.0,
        auth_failure_probability=1.0,
    )

    assert result["tokens_used"] > 0
    assert request.state.provider_latency_ms >= 0
