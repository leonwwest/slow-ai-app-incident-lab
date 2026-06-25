# Postmortem: [Incident Title]

> Fill in this template after an incident is resolved. Reference:
> `docs/INCIDENT_EXAMPLE.md` for a worked example.

## Summary

One-paragraph executive summary: what happened, who was affected, how long,
and the current status.

## Metadata

| Field              | Value                          |
|--------------------|--------------------------------|
| Severity           | SEV-1 / SEV-2 / SEV-3 / SEV-4 |
| Date               | YYYY-MM-DD                     |
| Start time (UTC)   | HH:MM                          |
| End time (UTC)     | HH:MM                          |
| Duration           | e.g. 47 min                    |
| Authors            | [on-call names]                |
| Status             | resolved / monitoring          |
| Deployment version | e.g. v1.4.0                    |

## Impact

Who was affected, how many users, what functionality was degraded. Quantify
where possible (error rate, P95 latency, revenue impact).

## Root Cause

The underlying technical cause. Be specific: not "the app was slow" but
"v1.4.0 routed /chat/slow to an expensive upstream model without a timeout,
and AI_API_KEY was unset so 401s compounded the failure".

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:00      | Deployment v1.4.0 |
| 09:10      | First elevated P95 on /chat/slow |
| 09:20      | Error rate crosses 3% |
| ...        | ... |

## What went well

- [e.g. Structured logs made triage fast]
- [e.g. Runbook step 6 (IAM check) pinpointed the 401 source]

## What went badly

- [e.g. No alert on P95 > 2s, so detection was user-reported]
- [e.g. No timeout on the AI provider call]

## Detection

How was the incident detected? (alert, user report, dashboard check). If
user-reported, note time between onset and detection.

## Resolution

What fixed it? (rollback, config change, scaling, key rotation). Include the
specific commands / versions used.

## Action items

| # | Action | Owner | Priority | Issue |
|---|--------|-------|----------|-------|
| 1 | Add P95 > 2s alert on /chat/slow | | P1 | #123 |
| 2 | Add provider call timeout (5s) | | P1 | #124 |
| 3 | Provision AI_API_KEY in CI before deploy | | P2 | #125 |
| 4 | Add per-user rate limit | | P2 | #126 |

## Lessons learned

What would have prevented this entirely? What should we monitor next time?

## Appendix

Links to dashboards, logs, traces, SQL queries, related PRs.
