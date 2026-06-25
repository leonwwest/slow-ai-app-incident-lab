-- Schema for request_logs.
-- This file is the canonical (PostgreSQL) definition. The running lab uses
-- SQLite (see app/database.py) with identical column names; the only
-- difference is `id SERIAL PRIMARY KEY` becomes
-- `id INTEGER PRIMARY KEY AUTOINCREMENT` and TIMESTAMP becomes TEXT.
-- Both stores support the observability queries in
-- observability_queries.sql (percentile functions differ - see notes there).

CREATE TABLE request_logs (
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

CREATE INDEX idx_request_logs_timestamp  ON request_logs(timestamp);
CREATE INDEX idx_request_logs_endpoint   ON request_logs(endpoint);
CREATE INDEX idx_request_logs_status_code ON request_logs(status_code);
CREATE INDEX idx_request_logs_user_id    ON request_logs(user_id);
