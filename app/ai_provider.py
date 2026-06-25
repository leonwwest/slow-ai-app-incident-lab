"""Shared AI-provider simulation helpers used by the chat routers."""
import random
import time

from fastapi import HTTPException, Request

from app.config import settings


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (
        input_tokens / 1000.0 * settings.price_input_per_1k
        + output_tokens / 1000.0 * settings.price_output_per_1k
    )
    return round(cost, 6)


def simulate_provider_call(
    request: Request,
    *,
    delay_ms: int,
    timeout_probability: float,
    auth_failure_probability: float,
) -> dict:
    """Simulate an external AI provider request.

    Returns a dict with tokens_used and provider_latency_ms attached to the
    request state. May raise HTTPException for 401 (auth) or 503 (timeout)
    to mirror real provider failure modes.
    """
    # 1. IAM / API-key check - a fraction of calls fail when the key is unset.
    if not settings.ai_api_key and random.random() < auth_failure_probability:
        request.state.error_message = "AI provider 401: missing or invalid api key (AI_API_KEY)"
        raise HTTPException(
            status_code=401,
            detail="AI provider unauthorized: check AI_API_KEY / secret manager",
        )

    # 2. Latency simulation.
    start = time.perf_counter()
    time.sleep(delay_ms / 1000.0)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    # 3. Provider timeout / 503 - more likely on the slow path.
    if random.random() < timeout_probability:
        request.state.provider_latency_ms = elapsed_ms
        request.state.error_message = "AI provider 503: upstream timeout"
        raise HTTPException(status_code=503, detail="AI provider timeout")

    # 4. Success - simulate token usage and cost.
    input_tokens = random.randint(120, 600)
    output_tokens = random.randint(80, 400)
    tokens_used = input_tokens + output_tokens
    cost = estimate_cost(input_tokens, output_tokens)

    request.state.provider_latency_ms = elapsed_ms
    request.state.tokens_used = tokens_used
    request.state.estimated_cost_usd = cost
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tokens_used": tokens_used,
        "estimated_cost_usd": cost,
        "provider_latency_ms": elapsed_ms,
    }
