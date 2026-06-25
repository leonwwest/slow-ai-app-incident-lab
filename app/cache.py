"""In-memory prompt cache with TTL.

Caches AI responses by (endpoint, prompt) key so repeated identical prompts
skip the simulated provider call entirely - demonstrating the "add caching
for repeated prompts" recommendation from the runbook.

Disabled in the "broken" deployment (v1.4.0) and enabled in the "fixed"
deployment (v1.3.2). Override with ENABLE_CACHE env var.
"""
import time

from app.config import settings

import logging

log = logging.getLogger("incident_lab.cache")


class TTLCache:
    """Simple dict-based TTL cache. Not thread-safe for multi-worker."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 500):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, dict]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        ts, value = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: str, value: dict) -> None:
        if len(self._store) >= self.max_entries:
            # Evict oldest entry (simple LRU-ish; not perfect but fine for lab).
            oldest = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest]
        self._store[key] = (time.monotonic(), value)

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses, "entries": len(self._store)}


_active_cache: TTLCache | None = None


def get_cache() -> TTLCache | None:
    """Return the shared cache, or None if disabled."""
    global _active_cache
    if _active_cache is not None:
        return _active_cache
    import os

    explicit = os.getenv("ENABLE_CACHE", "").strip().lower()
    enabled = explicit in {"1", "true", "yes", "on"} if explicit else (
        settings.deployment_version == "v1.3.2"
    )
    if not enabled:
        return None
    _active_cache = TTLCache(ttl_seconds=300, max_entries=500)
    return _active_cache
