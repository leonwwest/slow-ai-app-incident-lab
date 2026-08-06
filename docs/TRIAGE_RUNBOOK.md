# Automated triage runbook

## Generate a report

Against a running lab:

```bash
curl -s http://localhost:8010/api/triage | python -m json.tool
```

Offline and reproducibly:

```bash
python scripts/triage.py examples/degraded-stats.json --output reports/triage.json
```

## Interpret it

1. Check `sample_size` and confidence before trusting severity.
2. Validate the first hypothesis using at least two telemetry types.
3. Compare the deployment version and incident start time.
4. Select a reversible mitigation from `docs/RUNBOOK.md`.
5. Record the evidence and decision in `docs/POSTMORTEM_TEMPLATE.md`.

The classification is decision support. It never proves root cause by itself.
