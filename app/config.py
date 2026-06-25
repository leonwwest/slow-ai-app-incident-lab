"""Central configuration for the Slow AI App Incident Lab.

All values can be overridden via environment variables so the same code can
simulate different regions, deployment versions, or pricing without code
changes. The .env file is loaded automatically (real env vars still win).
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()  # load .env if present; real env vars still take precedence


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- Database backend -------------------------------------------------
    # "sqlite" (default, zero-setup) or "postgres" (Docker Compose / prod).
    db_backend: str = os.getenv("DB_BACKEND", "sqlite")
    # SQLite location (relative to repo root; kept out of git).
    db_path: str = os.getenv("INCIDENT_LAB_DB_PATH", "data/incident_lab.db")
    # Postgres DSN used when db_backend == "postgres".
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://incident:incident@localhost:5432/incident_lab",
    )

    # --- Deployment metadata ----------------------------------------------
    # Intentionally set to the "bad" version so the example incident
    # in the runbook reproduces.
    deployment_version: str = os.getenv("DEPLOYMENT_VERSION", "v1.4.0")
    region: str = os.getenv("REGION", "eu-central-1")

    # --- Simulated AI provider pricing (USD per 1K tokens) ----------------
    price_input_per_1k: float = float(os.getenv("PRICE_INPUT_PER_1K", "0.010"))
    price_output_per_1k: float = float(os.getenv("PRICE_OUTPUT_PER_1K", "0.030"))

    # Simulated provider hostname used by the DNS/network runbook section.
    ai_provider_host: str = os.getenv("AI_PROVIDER_HOST", "api.simulated-ai-provider.com")

    # Simulated API key. Left empty by default so a subset of /chat and
    # /slow-chat calls surface realistic 401 IAM failures. Set to any
    # non-empty value to "fix" IAM.
    ai_api_key: str = os.getenv("AI_API_KEY", "")

    # --- Observability toggles -------------------------------------------
    # Prometheus /metrics endpoint.
    enable_metrics: bool = _bool("ENABLE_METRICS", "true")
    # OpenTelemetry tracing -> OTLP (Jaeger/Tempo).
    enable_tracing: bool = _bool("ENABLE_TRACING", "true")
    otel_exporter_otlp_endpoint: str = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "slow-ai-app")


settings = Settings()
