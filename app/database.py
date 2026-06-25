"""SQLite persistence layer for request logs.

The schema mirrors the one documented in the README so the observability SQL
queries in `sql/observability_queries.sql` map cleanly onto the local data.
SQLite is used for zero-setup local runs; the same schema works on PostgreSQL
by swapping the serial primary key syntax (see sql/schema.sql).
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import settings

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    request_id TEXT NOT NULL,
    user_id TEXT,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    provider_latency_ms INTEGER,
    db_latency_ms INTEGER,
    tokens_used INTEGER,
    estimated_cost_usd REAL,
    error_message TEXT,
    deployment_version TEXT,
    region TEXT
);

CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_logs_endpoint ON request_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_request_logs_status_code ON request_logs(status_code);
"""


def init_db() -> None:
    """Create the database file and schema if they do not yet exist."""
    import os

    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a thread-local SQLite connection.

    A thread-local connection avoids the "SQLite objects created in a thread
    can only be used in that same thread" error under uvicorn workers while
    keeping connection reuse within a single request lifecycle.
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def insert_request_log(record: dict[str, Any]) -> None:
    """Persist a single request log row."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO request_logs (
                timestamp, request_id, user_id, endpoint, method, status_code,
                latency_ms, provider_latency_ms, db_latency_ms, tokens_used,
                estimated_cost_usd, error_message, deployment_version, region
            ) VALUES (
                :timestamp, :request_id, :user_id, :endpoint, :method, :status_code,
                :latency_ms, :provider_latency_ms, :db_latency_ms, :tokens_used,
                :estimated_cost_usd, :error_message, :deployment_version, :region
            )
            """,
            {
                "timestamp": record["timestamp"],
                "request_id": record["request_id"],
                "user_id": record.get("user_id"),
                "endpoint": record["endpoint"],
                "method": record["method"],
                "status_code": record["status_code"],
                "latency_ms": record["latency_ms"],
                "provider_latency_ms": record.get("provider_latency_ms"),
                "db_latency_ms": record.get("db_latency_ms"),
                "tokens_used": record.get("tokens_used"),
                "estimated_cost_usd": record.get("estimated_cost_usd"),
                "error_message": record.get("error_message"),
                "deployment_version": record.get("deployment_version"),
                "region": record.get("region"),
            },
        )
