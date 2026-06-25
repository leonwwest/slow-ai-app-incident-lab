"""Central configuration for the Slow AI App Incident Lab.

All values can be overridden via environment variables so the same code can
simulate different regions, deployment versions, or pricing without code
changes.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # SQLite database location (kept out of git via .gitignore)
    db_path: str = os.getenv("INCIDENT_LAB_DB_PATH", "data/incident_lab.db")

    # Deployment metadata - intentionally set to the "bad" version so the
    # example incident in the runbook reproduces.
    deployment_version: str = os.getenv("DEPLOYMENT_VERSION", "v1.4.0")
    region: str = os.getenv("REGION", "eu-central-1")

    # Simulated AI provider pricing in USD per 1K tokens.
    price_input_per_1k: float = float(os.getenv("PRICE_INPUT_PER_1K", "0.010"))
    price_output_per_1k: float = float(os.getenv("PRICE_OUTPUT_PER_1K", "0.030"))

    # Simulated provider hostname used for the DNS/network checklist section.
    ai_provider_host: str = os.getenv("AI_PROVIDER_HOST", "api.simulated-ai-provider.com")

    # Simulated API key. Left empty by default so a subset of /chat and
    # /slow-chat calls can surface realistic 401 "AI provider timeout"-style
    # IAM failures. Set AI_API_KEY to a value to "fix" it.
    ai_api_key: str = os.getenv("AI_API_KEY", "")


settings = Settings()
