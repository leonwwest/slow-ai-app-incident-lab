"""FastAPI application entrypoint for the Slow AI App Incident Lab."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.logging_setup import setup_logging
from app.middleware import RequestLoggingMiddleware
from app.metrics import setup_metrics
from app.routers import api_router
from app.tracing import setup_tracing


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

# OpenTelemetry must instrument the app before routes/middleware are added so
# it can wrap them. Safe no-op if packages are missing or ENABLE_TRACING=false.
setup_tracing(app)

app.add_middleware(RequestLoggingMiddleware)
app.include_router(api_router)

# Prometheus /metrics endpoint. Safe no-op if package missing or disabled.
setup_metrics(app)


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
            "GET /metrics",
        ],
        "docs": "/docs",
    }
