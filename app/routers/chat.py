import random

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.ai_provider import simulate_provider_call
from app.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    prompt: str = Field(..., examples=["Explain P95 latency in one sentence."])
    user_id: str | None = None


@router.post("")
async def chat(body: ChatRequest, request: Request) -> dict:
    """Normal AI request: ~250-600ms provider latency, low failure rate."""
    result = simulate_provider_call(
        request,
        delay_ms=random.randint(250, 600),
        timeout_probability=0.02,
        auth_failure_probability=0.01,
    )
    return {
        "request_id": request.state.request_id,
        "reply": f"[simulated] Response to: {body.prompt[:80]}",
        "model": "simulated-ai-mini",
        "tokens_used": result["tokens_used"],
        "estimated_cost_usd": result["estimated_cost_usd"],
        "provider_latency_ms": result["provider_latency_ms"],
        "deployment_version": settings.deployment_version,
    }


@router.post("/slow")
async def slow_chat(body: ChatRequest, request: Request) -> dict:
    """Slow AI request: 2-8s provider latency, high P95/P99, frequent 503s.

    This endpoint is the primary suspect in the example incident: it simulates
    an expensive model with a long upstream call and an elevated timeout rate.
    """
    result = simulate_provider_call(
        request,
        delay_ms=random.randint(2000, 8000),
        timeout_probability=0.18,
        auth_failure_probability=0.01,
    )
    return {
        "request_id": request.state.request_id,
        "reply": f"[simulated, slow path] Response to: {body.prompt[:80]}",
        "model": "simulated-ai-xl",
        "tokens_used": result["tokens_used"],
        "estimated_cost_usd": result["estimated_cost_usd"],
        "provider_latency_ms": result["provider_latency_ms"],
        "deployment_version": settings.deployment_version,
    }
