"""Request logging middleware.

Wraps every request to:
  * assign a request_id (X-Request-ID) and user_id (X-User-Id),
  * measure end-to-end latency,
  * collect observability extras that routes may attach to request.state
    (provider_latency_ms, db_latency_ms, tokens_used, estimated_cost_usd,
    error_message),
  * emit one structured JSON log line and persist a row to request_logs.
"""
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.database import insert_request_log
from app.logging_setup import setup_logging  # noqa: F401  (ensures logging ready)

import logging

log = logging.getLogger("incident_lab.request")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        user_id = request.headers.get("x-user-id") or f"user_{uuid.uuid4().hex[:4]}"
        # Seed request.state so routes can read/mutate observability extras.
        request.state.request_id = request_id
        request.state.user_id = user_id
        request.state.provider_latency_ms = None
        request.state.db_latency_ms = None
        request.state.tokens_used = None
        request.state.estimated_cost_usd = None
        request.state.error_message = None

        start = time.perf_counter()
        status_code = 500
        error_message = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            # Surface request id on the response for client-side correlation.
            response.headers["x-request-id"] = request_id
            return response
        except Exception as exc:  # noqa: BLE001 - we must still log on crash
            error_message = f"unhandled exception: {exc}"
            raise
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            endpoint = request.url.path
            method = request.method

            # Routes may set their own error message (e.g. HTTPException text).
            route_error = getattr(request.state, "error_message", None)
            record = {
                "timestamp": _now_iso(),
                "request_id": request_id,
                "user_id": user_id,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "provider_latency_ms": getattr(request.state, "provider_latency_ms", None),
                "db_latency_ms": getattr(request.state, "db_latency_ms", None),
                "tokens_used": getattr(request.state, "tokens_used", None),
                "estimated_cost_usd": getattr(request.state, "estimated_cost_usd", None),
                "error_message": route_error or error_message,
                "deployment_version": settings.deployment_version,
                "region": settings.region,
            }

            log.info(
                "request.completed",
                extra={
                    "request_id": record["request_id"],
                    "user_id": record["user_id"],
                    "endpoint": record["endpoint"],
                    "method": record["method"],
                    "status_code": record["status_code"],
                    "latency_ms": record["latency_ms"],
                    "provider_latency_ms": record["provider_latency_ms"],
                    "db_latency_ms": record["db_latency_ms"],
                    "tokens_used": record["tokens_used"],
                    "estimated_cost_usd": record["estimated_cost_usd"],
                    "error_message": record["error_message"],
                    "deployment_version": record["deployment_version"],
                    "region": record["region"],
                },
            )
            try:
                insert_request_log(record)
            except Exception as exc:  # noqa: BLE001 - never break a response over logging
                log.warning("request_log.persist_failed", extra={"error": str(exc)})
