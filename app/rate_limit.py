"""Per-user token-bucket rate limiting.

Implements a simple in-memory token bucket per user_id. When the bucket is
empty the request is rejected with HTTP 429 and a Retry-After header.

Only applied to AI endpoints (/chat and /chat/slow) to demonstrate the
"add per-user rate limit" recommendation from the runbook.

Disabled in the "broken" deployment (v1.4.0) and enabled in the "fixed"
deployment (v1.3.2) to show before/after behaviour. Override with
ENABLE_RATE_LIMIT env var.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field

from app.config import settings

import logging

log = logging.getLogger("incident_lab.ratelimit")


@dataclass
class TokenBucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def consume(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after_seconds(self, cost: float = 1.0) -> float:
        deficit = cost - self.tokens
        return max(0.1, deficit / self.refill_rate)


class RateLimiter:
    """In-memory per-user rate limiter.

    Not suitable for multi-instance deployments without a shared store
    (Redis), but sufficient for the lab. The limitation is documented in
    the module docstring and the README.
    """

    def __init__(self, capacity: float = 10, refill_per_minute: float = 20):
        self.capacity = capacity
        self.refill_rate = refill_per_minute / 60.0
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(self.capacity, self.refill_rate)
        )

    def allow(self, user_id: str) -> tuple[bool, float]:
        bucket = self._buckets[user_id]
        ok = bucket.consume()
        retry_after = 0.0 if ok else bucket.retry_after_seconds()
        return ok, retry_after


_active: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter | None:
    """Return the shared rate limiter, or None if disabled."""
    global _active
    if _active is not None:
        return _active
    # Enabled in the "fixed" version, or when explicitly set via env.
    enabled = _is_enabled()
    if not enabled:
        return None
    _active = RateLimiter(capacity=10, refill_per_minute=20)
    return _active


def _is_enabled() -> bool:
    import os

    explicit = os.getenv("ENABLE_RATE_LIMIT", "").strip().lower()
    if explicit:
        return explicit in {"1", "true", "yes", "on"}
    # Auto-enable in the "known-good" version (fix scenario).
    return settings.deployment_version == "v1.3.2"
