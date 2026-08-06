#!/usr/bin/env python3
"""Run incident classification against an exported /api/stats response."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.incident_triage import assess_incident


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stats_file", type=Path, help="JSON exported from GET /api/stats"
    )
    parser.add_argument(
        "--output", type=Path, help="Optional output path for the report"
    )
    args = parser.parse_args()

    report = assess_incident(json.loads(args.stats_file.read_text(encoding="utf-8")))
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
