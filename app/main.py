"""FastAPI application entrypoint for the Slow AI App Incident Lab."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.logging_setup import setup_logging
from app.middleware import RequestLoggingMiddleware
from app.routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    yield


app = FastAPI(
    title="Slow AI App Incident Lab",
    description=(
        "A deliberately slow AI/web app for practising production-style "
        "debugging: P95/P99 latency, error-rate investigation, structured "
        "logs, IAM/API-key checks, network/DNS, cost analysis, scaling and "
        "rollback. See README.md and docs/RUNBOOK.md."
    ),
    version="1.4.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(api_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "slow-ai-app-incident-lab",
        "endpoints": [
            "GET /health",
            "POST /chat",
            "POST /chat/slow",
            "GET /random-error",
            "GET /db-query",
        ],
        "docs": "/docs",
    }
