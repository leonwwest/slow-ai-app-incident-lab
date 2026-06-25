"""OpenTelemetry tracing setup.

Exports spans via OTLP to a collector (Jaeger/Tempo) when
``ENABLE_TRACING`` is true. Spans are created automatically for every
FastAPI request by FastAPIInstrumentor, plus manual spans in
``ai_provider`` and ``diagnostics`` for the simulated provider/db calls.

The OTLP exporter and instrumentations are imported lazily so the app still
runs without opentelemetry packages installed (tracing is simply disabled).
"""
from typing import Optional

from app.config import settings


def setup_tracing(app) -> Optional[object]:
    """Configure OTLP tracing + FastAPI/requests instrumentation.

    Returns the tracer provider if tracing is enabled and the optional
    packages are available, otherwise ``None``.
    """
    if not settings.enable_tracing:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        # opentelemetry packages not installed - tracing disabled silently.
        return None

    resource = Resource.create(
        {"service.name": settings.otel_service_name}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        )
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    return provider


def get_tracer():
    """Return a tracer, or a no-op if tracing is unavailable."""
    if not settings.enable_tracing:
        return None
    try:
        from opentelemetry import trace

        return trace.get_tracer(__name__)
    except Exception:
        return None
