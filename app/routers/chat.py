import random

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.ai_provider import simulate_provider_call
from app.cache import get_cache
from app.config import settings
from app.rate_limit import get_rate_limiter

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    prompt: str = Field(..., examples=["Explain P95 latency in one sentence."])
    user_id: str | None = None


def _check_rate_limit(request: Request) -> None:
    """Reject with 429 if the user has exceeded their token bucket."""
    limiter = get_rate_limiter()
    if limiter is None:
        return
    user_id = getattr(request.state, "user_id", "unknown")
    ok, retry_after = limiter.allow(user_id)
    if not ok:
        request.state.error_message = "rate limit exceeded: per-user token bucket empty"
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {user_id}. Retry in {retry_after:.1f}s.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


def _cache_key(endpoint: str, prompt: str) -> str:
    return f"{endpoint}:{hash(prompt)}"


@router.post("")
async def chat(body: ChatRequest, request: Request) -> dict:
    """Normal AI request: ~250-600ms provider latency, low failure rate."""
    _check_rate_limit(request)

    cache = get_cache()
    key = _cache_key("/chat", body.prompt) if cache else None
    if cache and key:
        cached = cache.get(key)
        if cached is not None:
            cached["cached"] = True
            cached["request_id"] = request.state.request_id
            request.state.provider_latency_ms = 0
            request.state.tokens_used = 0
            request.state.estimated_cost_usd = 0.0
            return cached

    result = simulate_provider_call(
        request,
        delay_ms=random.randint(250, 600),
        timeout_probability=0.02,
        auth_failure_probability=0.01,
    )
    response = {
        "request_id": request.state.request_id,
        "reply": f"[simulated] Response to: {body.prompt[:80]}",
        "model": "simulated-ai-mini",
        "tokens_used": result["tokens_used"],
        "estimated_cost_usd": result["estimated_cost_usd"],
        "provider_latency_ms": result["provider_latency_ms"],
        "deployment_version": settings.deployment_version,
        "cached": False,
    }
    if cache and key:
        cache.set(key, response)
    return response


@router.post("/slow")
async def slow_chat(body: ChatRequest, request: Request) -> dict:
    """Slow AI request: 2-8s provider latency, high P95/P99, frequent 503s.

    This endpoint is the primary suspect in the example incident: it simulates
    an expensive model with a long upstream call and an elevated timeout rate.
    """
    _check_rate_limit(request)

    cache = get_cache()
    key = _cache_key("/chat/slow", body.prompt) if cache else None
    if cache and key:
        cached = cache.get(key)
        if cached is not None:
            cached["cached"] = True
            cached["request_id"] = request.state.request_id
            request.state.provider_latency_ms = 0
            request.state.tokens_used = 0
            request.state.estimated_cost_usd = 0.0
            return cached

    result = simulate_provider_call(
        request,
        delay_ms=random.randint(2000, 8000),
        timeout_probability=0.18,
        auth_failure_probability=0.01,
    )
    response = {
        "request_id": request.state.request_id,
        "reply": f"[simulated, slow path] Response to: {body.prompt[:80]}",
        "model": "simulated-ai-xl",
        "tokens_used": result["tokens_used"],
        "estimated_cost_usd": result["estimated_cost_usd"],
        "provider_latency_ms": result["provider_latency_ms"],
        "deployment_version": settings.deployment_version,
        "cached": False,
    }
    if cache and key:
        cache.set(key, response)
    return response
