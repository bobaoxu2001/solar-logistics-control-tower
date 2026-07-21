"""Run Phase 3 analytics, controls, reporting, documentation, and validation."""

from __future__ import annotations

import sys

from sqlalchemy import inspect

import build_analytics_base
import build_excel_kpi_pack
import build_phase3_docs
import build_root_cause_outputs
import build_scorecards
import export_reporting_tables
import load_phase3
import reconcile_detection
import validate_phase3
from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import apply_ddl

log = get_logger("run_phase3")


def _step(name, fn):
    log.info("=" * 72)
    log.info("STEP: %s", name)
    log.info("=" * 72)
    rc = fn()
    if rc:
        log.error("STEP FAILED (%s), rc=%s — aborting Phase 3", name, rc)
        raise RuntimeError(f"Phase 3 step failed: {name} (rc={rc})")


def confirm_prerequisites() -> int:
    required_files = [
        DATA_PROCESSED / "stg_shipment.csv",
        DATA_PROCESSED / "exception_manifest.csv",
        DATA_PROCESSED / "clean" / "fact_shipment.csv",
        DATA_PROCESSED / "operational" / "fact_shipment.csv",
    ]
    missing_files = [str(path) for path in required_files if not path.exists()]
    if missing_files:
        log.error("Missing Phase 1/2 outputs: %s", missing_files)
        return 1
    cfg = load_config()
    engine = create_project_engine(cfg)
    required_tables = {"stg_shipment", "fact_shipment", "fact_freight_invoice",
                       "fact_purchase_order", "fact_accrual", "meta_exception_manifest"}
    table_schema = None if engine.dialect.name == "sqlite" else cfg["database"]["schema"]
    existing = set(inspect(engine).get_table_names(schema=table_schema))
    missing_tables = sorted(required_tables - existing)
    if missing_tables:
        log.error("Missing required database tables: %s. Run python src/run_phase2.py", missing_tables)
        return 1
    log.info("Confirmed Phase 1/2 outputs and %d required database tables", len(required_tables))
    return 0


def apply_root_cause_sql() -> int:
    cfg = load_config()
    apply_ddl(create_project_engine(cfg), "10_root_cause_analysis.sql", cfg["database"]["schema"])
    return 0


def main() -> int:
    try:
        _step("Confirm Phase 1 and Phase 2 outputs", confirm_prerequisites)
        _step("Build portable shipment analytics base", build_analytics_base.main)
        _step("Apply core Phase 3 SQL, seed configuration, and detect exceptions", load_phase3.main)
        _step("Reconcile detections to manifest (critical gate)", reconcile_detection.main)
        _step("Build carrier and lane scorecards", build_scorecards.main)
        _step("Apply root-cause evidence SQL", apply_root_cause_sql)
        _step("Generate root-cause case-study outputs", build_root_cause_outputs.main)
        _step("Build Power BI views and export reporting tables", export_reporting_tables.main)
        _step("Generate Excel KPI pack", build_excel_kpi_pack.main)
        _step("Update Phase 3 documentation", build_phase3_docs.main)
        _step("Run Phase 3 validation gate", validate_phase3.main)
    except RuntimeError:
        return 1
    log.info("=" * 72)
    log.info("PHASE 3 COMPLETE")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
