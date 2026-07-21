"""Phase 2 orchestrator — run the enterprise simulation end to end.

Steps:
  1. Confirm Phase 1 outputs exist.
  2. Generate clean master data.
  3. Generate clean enterprise facts.
  4. Validate the clean baseline (STOP if any CRITICAL check fails).
  5. Inject configured exceptions (separate operational layer + manifest).
  6. Apply Phase 2 DDL and load the operational dataset + manifest.
  7. Write the Phase 2 summary document.

Usage:
    python src/run_phase2.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import pandas as pd

import generate_master_data
import generate_enterprise_data
import validate_phase2
import inject_exceptions
import load_phase2
import build_phase2_docs
from common import DATA_PROCESSED, DOCS_DIR, PROJECT_ROOT, get_logger

log = get_logger("run_phase2")
CLEAN = DATA_PROCESSED / "clean"
OPER = DATA_PROCESSED / "operational"


def _step(name, fn):
    log.info("=" * 70)
    log.info("STEP: %s", name)
    log.info("=" * 70)
    rc = fn()
    if rc:
        log.error("STEP FAILED (%s), rc=%s — aborting Phase 2", name, rc)
        sys.exit(rc)


def write_summary():
    val = pd.read_csv(CLEAN / "rpt_phase2_baseline_validation.csv")
    summary = pd.read_csv(DATA_PROCESSED / "exception_summary.csv")
    manifest = pd.read_csv(DATA_PROCESSED / "exception_manifest.csv")

    clean_tables = sorted(CLEAN.glob("*.csv"))
    oper_tables = sorted(OPER.glob("*.csv"))
    clean_counts = {f.stem: sum(1 for _ in open(f, encoding="utf-8")) - 1 for f in clean_tables}
    oper_counts = {f.stem: sum(1 for _ in open(f, encoding="utf-8")) - 1 for f in oper_tables}

    crit_fail = val[(val["severity"] == "CRITICAL") & (val["status"] == "FAIL")]
    any_fail = val[val["status"] == "FAIL"]

    lines = []
    lines.append("# Phase 2 Summary — Enterprise Logistics Data Simulation\n")
    lines.append(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. "
                 "Deterministic under `random_seed` in config/project_config.yaml._\n")
    lines.append("## Input\n")
    lines.append(f"- Cleaned public shipment lines (Phase 1): **{clean_counts.get('fact_shipment', 0):,}**\n")

    lines.append("\n## Output row counts (clean baseline → operational)\n")
    lines.append("| Table | Clean baseline | Operational (post-injection) |")
    lines.append("|---|--:|--:|")
    order = ["dim_location", "dim_location_xref", "dim_hts_code", "dim_product",
             "dim_business_partner", "dim_supplier", "dim_warehouse", "dim_carrier",
             "dim_lane", "dim_rate_card", "fact_purchase_order", "fact_shipment",
             "fact_shipment_milestone", "fact_freight_invoice", "fact_invoice_line",
             "fact_accessorial_charge", "fact_proof_of_delivery", "fact_claim",
             "fact_carrier_capacity", "fact_invoice_approval", "fact_accrual"]
    for t in order:
        lines.append(f"| {t} | {clean_counts.get(t, 0):,} | {oper_counts.get(t, 0):,} |")

    lines.append("\n## Clean baseline validation\n")
    lines.append(f"- Checks run: **{len(val)}** | Failures: **{len(any_fail)}** | "
                 f"Critical failures: **{len(crit_fail)}**\n")
    lines.append(f"- Overall min pass rate: **{val['pass_rate'].min():.4f}**  "
                 f"({'✓ clean baseline is consistent' if len(crit_fail) == 0 else '✗ CRITICAL FAILURES'})\n")

    lines.append("\n## Injected exceptions (operational layer)\n")
    lines.append(f"- Total injected records: **{len(manifest):,}** across "
                 f"**{summary['exception_type'].nunique()}** types.\n")
    lines.append("| Exception type | Eligible | Configured rate | Expected | Actual | Affected table | Severity |")
    lines.append("|---|--:|--:|--:|--:|---|---|")
    for r in summary.itertuples(index=False):
        lines.append(f"| {r.exception_type} | {r.eligible_records:,} | {r.configured_rate:.3f} | "
                     f"{r.expected_count} | {r.actual_count} | {r.affected_table} | {r.severity} |")

    lines.append("\n## Reproducibility\n")
    lines.append("- All IDs are deterministic; all stochastic draws are seeded per-record. "
                 "Re-running produces byte-identical CSVs and never duplicates rows.\n")
    lines.append("- Clean baseline lives in `data/processed/clean/`; the exception-injected "
                 "operational layer in `data/processed/operational/`; every change is recorded in "
                 "`data/processed/exception_manifest.csv`.\n")

    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "phase2_summary.md").write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote documentation/phase2_summary.md")


def main() -> int:
    if not (DATA_PROCESSED / "stg_shipment.csv").exists():
        log.error("Phase 1 output missing (stg_shipment.csv). Run Phase 1 first.")
        return 1

    _step("Generate master data", generate_master_data.main)
    _step("Generate enterprise facts", generate_enterprise_data.main)
    _step("Validate clean baseline", validate_phase2.main)   # aborts on critical failure
    _step("Inject controlled exceptions", inject_exceptions.main)
    _step("Apply DDL + load operational dataset", load_phase2.main)
    _step("Update Excel documentation", build_phase2_docs.main)

    write_summary()
    log.info("=" * 70)
    log.info("PHASE 2 COMPLETE")
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
