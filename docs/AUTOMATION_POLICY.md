# Incident automation policy

The automation is deterministic and explainable. It consumes the same one-hour statistics that
power `/api/stats`, evaluates published thresholds and returns evidence, severity, confidence,
ranked hypotheses and next actions at `/api/triage`.

## What is automatic

- calculate severity from request count, error rate, worst endpoint P95 and window cost;
- rank AI-provider, database, request-path and cost hypotheses;
- produce a consistent evidence checklist and incident-update input;
- classify sparse windows as `insufficient-data` instead of overreacting.

## What remains a dry run

Restarting, scaling, rollback and credential rotation are named but never executed. Each can
hide evidence or increase impact. A real deployment would put those actions behind a reviewed
workflow with authentication, an audit log, idempotency, blast-radius limits and rollback.

## Severity contract

| Severity | Trigger in the lab | Intended response |
|---|---|---|
| SEV1 | errors >= 20% or worst P95 >= 5 s | immediate incident coordination |
| SEV2 | errors >= 5%, worst P95 >= 2 s or cost >= $5/window | investigate now |
| SEV3 | errors >= 1%, worst P95 >= 1 s or cost >= $1/window | investigate during shift |
| SEV4 | healthy or fewer than 20 samples | monitor / collect more evidence |

Thresholds are lab policy, not universal production defaults.
