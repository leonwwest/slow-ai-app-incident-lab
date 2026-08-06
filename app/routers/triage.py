"""Explainable incident-triage endpoint."""

from fastapi import APIRouter

from app.incident_triage import assess_incident
from app.routers.stats import stats

router = APIRouter(prefix="/api", tags=["incident-automation"])


@router.get("/triage")
async def triage() -> dict:
    """Classify the current one-hour service window without changing service state."""
    return assess_incident(await stats())
