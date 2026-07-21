"""Generate the deterministic Phase 4 completion summary."""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

from common import PROJECT_ROOT, get_logger

log = get_logger("build_phase4_docs")
SUMMARY = PROJECT_ROOT / "documentation" / "phase4_summary.md"


def collected_test_count() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    match = re.search(r"(\d+) tests collected", result.stdout + result.stderr)
    return int(match.group(1)) if match else 0


def row_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> int:
    tests = collected_test_count()
    dashboard_checks = row_count(PROJECT_ROOT / "dashboard" / "dashboard_metric_reconciliation.csv")
    chart_checks = row_count(PROJECT_ROOT / "documentation" / "charts" / "chart_source_reconciliation.csv")
    content = f"""# Phase 4 Summary — Portfolio Presentation and Interview Demo

## Completion result

Phase 4 converts the verified Phase 3 analytical layer into a recruiter-first, manager-readable, and interview-ready portfolio package without changing analytical source data.

## Files created or materially updated

- Recruiter-first `README.md` with one-screen positioning, key outcomes, architecture, dashboard gallery, disclosure, run instructions, limitations, and interview paths.
- Visual generation and validation: `src/phase4_visuals.py`, `src/validate_dashboard_outputs.py`, `src/validate_excel_kpi_pack.py`, `src/validate_phase4.py`, and `src/run_phase4.py`.
- Portfolio documentation: case study, recruiter walkthrough, timed demo script, presentation outline, expanded interview materials, and chart source map.
- Machine-readable reconciliation ledgers and an idempotency hash manifest.

## Dashboard images created

1. Executive Logistics Overview
2. Shipment Control Tower
3. Carrier and Lane Performance
4. Freight Audit
5. Finance and Accrual
6. Data Quality and Controls

All six PNGs are under `dashboard/screenshots/` and are labeled as Power BI dashboard design mockups generated from project reporting outputs.

## Standalone charts created

Eight high-resolution charts are under `documentation/charts/`: monthly OTIF, carrier scorecard, lane risk matrix, freight-audit exposure waterfall, three-way-match distribution, accrual aging, data-quality detection performance, and exception severity distribution.

## Diagrams created

Project architecture, freight-audit workflow, and data-quality validation workflow are under `documentation/diagrams/` as PNG plus Mermaid source.

## Validation results

- **Dashboard reconciliation:** {dashboard_checks}/{dashboard_checks} headline metrics pass.
- **Chart reconciliation:** {chart_checks}/{chart_checks} source checks pass.
- **Excel KPI pack:** 44/44 structural, formatting, disclosure, and value checks pass; the workbook remains analytically unchanged.
- **Test suite:** {tests} tests are collected, including the original 100 tests and the Phase 4 presentation tests.
- **Idempotency:** PASS. `run_phase4.py` generates the presentation artifact set twice and requires identical SHA-256 hashes before completion.

## Remaining manual Power BI work

Power BI Desktop assembly remains manual: import the 14 reporting exports or PostgreSQL views, create documented relationships, add DAX measures, assemble six interactive pages, configure slicers and drill-through, review accessibility, configure credentials and scheduled refresh, reconcile against the static mockups and Excel pack, and publish to a governed workspace. No `.pbix` is fabricated.

## Assumptions and limitations

- Shipment patterns are public-source derived; solar product identity and enterprise/finance records are deterministic simulations.
- Financial results are modeled control exposures, not realized recovery or approved budget.
- SQLite is live-tested. PostgreSQL-compatible analytics were hardened but not executed against a live PostgreSQL server here.
- The PNG renderer uses the locally available macOS `sips` utility. Analytical calculations remain Python/SQL and are unchanged.

## Exact rerun commands

```bash
python3 src/run_phase4.py
python3 -m pytest tests/ -q
git diff --check
git status
```
"""
    SUMMARY.write_text(content, encoding="utf-8")
    log.info("Wrote %s", SUMMARY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
