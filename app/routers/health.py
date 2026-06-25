from datetime import datetime, timezone

from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    """Liveness probe. Fast by design - if this is slow, the app itself is down."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deployment_version": settings.deployment_version,
        "region": settings.region,
    }
