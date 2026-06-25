"""Persistence layer for request logs.

Supports two backends selected via `DB_BACKEND`:

* ``sqlite`` (default) - zero-setup local runs. Uses TEXT timestamps and
  AUTOINCREMENT.
* ``postgres`` - Docker Compose / production. Uses TIMESTAMP and SERIAL, and
  the canonical observability queries in ``sql/observability_queries.sql``
  (PERCENTILE_CONT, window functions) run natively.

psycopg2 is imported lazily so SQLite-only users do not need it installed.
The public API (``init_db``, ``get_connection``, ``insert_request_log``) is
identical for both backends.
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from app.config import settings

_local = threading.local()

# --- Schema definitions ----------------------------------------------------

SCHEMA_SQLITE = """
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
CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp  ON request_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_logs_endpoint   ON request_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_request_logs_status_code ON request_logs(status_code);
CREATE INDEX IF NOT EXISTS idx_request_logs_user_id    ON request_logs(user_id);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS request_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    request_id TEXT NOT NULL,
    user_id TEXT,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    provider_latency_ms INTEGER,
    db_latency_ms INTEGER,
    tokens_used INTEGER,
    estimated_cost_usd NUMERIC(10, 6),
    error_message TEXT,
    deployment_version TEXT,
    region TEXT
);
CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp  ON request_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_request_logs_endpoint   ON request_logs(endpoint);
CREATE INDEX IF NOT EXISTS idx_request_logs_status_code ON request_logs(status_code);
CREATE INDEX IF NOT EXISTS idx_request_logs_user_id    ON request_logs(user_id);
"""

_INSERT_SQLITE = """
INSERT INTO request_logs (
    timestamp, request_id, user_id, endpoint, method, status_code,
    latency_ms, provider_latency_ms, db_latency_ms, tokens_used,
    estimated_cost_usd, error_message, deployment_version, region
) VALUES (
    :timestamp, :request_id, :user_id, :endpoint, :method, :status_code,
    :latency_ms, :provider_latency_ms, :db_latency_ms, :tokens_used,
    :estimated_cost_usd, :error_message, :deployment_version, :region
)
"""

# psycopg2 uses %s placeholders instead of :name.
_INSERT_POSTGRES = """
INSERT INTO request_logs (
    timestamp, request_id, user_id, endpoint, method, status_code,
    latency_ms, provider_latency_ms, db_latency_ms, tokens_used,
    estimated_cost_usd, error_message, deployment_version, region
) VALUES (
    %(timestamp)s, %(request_id)s, %(user_id)s, %(endpoint)s, %(method)s, %(status_code)s,
    %(latency_ms)s, %(provider_latency_ms)s, %(db_latency_ms)s, %(tokens_used)s,
    %(estimated_cost_usd)s, %(error_message)s, %(deployment_version)s, %(region)s
)
"""


# --- SQLite backend --------------------------------------------------------

@contextmanager
def _sqlite_connection() -> Iterator[sqlite3.Connection]:
    conn = getattr(_local, "sqlite_conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.sqlite_conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _sqlite_init() -> None:
    import os

    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    with _sqlite_connection() as conn:
        conn.executescript(SCHEMA_SQLITE)


def _sqlite_insert(record: dict[str, Any]) -> None:
    with _sqlite_connection() as conn:
        conn.execute(_INSERT_SQLITE, record)


# --- Postgres backend ------------------------------------------------------

@contextmanager
def _postgres_connection() -> Iterator[Any]:
    """Yield a psycopg2 connection from a thread-local pool."""
    import psycopg2
    from psycopg2 import pool

    pool_ = getattr(_local, "pg_pool", None)
    if pool_ is None:
        pool_ = pool.ThreadedConnectionPool(1, 8, settings.database_url)
        _local.pg_pool = pool_
    conn = pool_.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool_.putconn(conn)


def _postgres_init() -> None:
    with _postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_POSTGRES)


def _postgres_insert(record: dict[str, Any]) -> None:
    with _postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_INSERT_POSTGRES, record)


# --- Unified public API ----------------------------------------------------

def init_db() -> None:
    """Create the database file/schema if it does not yet exist."""
    if settings.db_backend == "postgres":
        _postgres_init()
    else:
        _sqlite_init()


@contextmanager
def get_connection() -> Iterator[Any]:
    """Yield a backend-appropriate connection (SQLite or Postgres)."""
    if settings.db_backend == "postgres":
        with _postgres_connection() as conn:
            yield conn
    else:
        with _sqlite_connection() as conn:
            yield conn


def insert_request_log(record: dict[str, Any]) -> None:
    """Persist a single request log row."""
    row = {
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
    }
    if settings.db_backend == "postgres":
        _postgres_insert(row)
    else:
        _sqlite_insert(row)
