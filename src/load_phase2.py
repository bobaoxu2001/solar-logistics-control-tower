"""Phase 2 — apply the enterprise DDL and load the operational dataset.

Clean-vs-exception storage strategy
-----------------------------------
The canonical enterprise tables hold the OPERATIONAL (exception-injected) data,
because that is what a real TMS / freight-settlement database contains and what
Phase 3's audit and data-quality SQL must run against. The CLEAN baseline is
preserved separately as data/processed/clean/*.csv (ground truth), and the
exception manifest records every clean→injected change, so clean-vs-corrupted
comparison needs no duplicate tables.

Because injected exceptions deliberately break referential integrity
(orphan invoices, invalid lane ids, …), the FK *definitions* stay in the DDL
(and are enforced for the clean baseline on PostgreSQL), but FK enforcement is
bypassed for this one intentionally-corrupted bulk load: SQLite does not enforce
FKs by default; on PostgreSQL the loader sets session_replication_role=replica
for the load. This is the single, documented constraint relaxation.

Usage:
    python src/load_phase2.py
"""

from __future__ import annotations

import sys

import pandas as pd
from sqlalchemy import create_engine, text

from common import DATA_PROCESSED, database_url, get_logger, load_config
from gen_common import apply_ddl, load_table

log = get_logger("load_phase2")
CLEAN = DATA_PROCESSED / "clean"
OPER = DATA_PROCESSED / "operational"

# Parent → child load order (satisfies FK inserts on PostgreSQL).
LOAD_ORDER = [
    "dim_location", "dim_location_xref", "dim_hts_code", "dim_product",
    "dim_business_partner", "dim_supplier", "dim_warehouse", "dim_carrier",
    "dim_lane", "dim_rate_card",
    "fact_purchase_order", "fact_shipment", "fact_shipment_milestone",
    "fact_freight_invoice", "fact_invoice_line", "fact_accessorial_charge",
    "fact_proof_of_delivery", "fact_claim", "fact_carrier_capacity",
    "fact_invoice_approval", "fact_accrual",
]
# Reports/manifest load from their canonical location (not corrupted).
REPORTS = {
    "rpt_lane_derivation": CLEAN, "rpt_rate_reconciliation": CLEAN,
    "rpt_phase2_baseline_validation": CLEAN, "meta_exception_manifest": OPER,
}


def _coerce_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        if col.endswith("_date") or col.endswith("_timestamp"):
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_engine(database_url(cfg))
    log.info("Target: %s (%s)", database_url(cfg).split("@")[-1], engine.dialect.name)

    apply_ddl(engine, "20_phase2_enterprise_model.sql", schema)
    log.info("Applied Phase 2 DDL (enterprise model)")

    is_pg = engine.dialect.name == "postgresql"
    if is_pg:
        with engine.begin() as c:
            c.execute(text("SET session_replication_role = 'replica'"))

    total = 0
    for name in LOAD_ORDER:
        df = _coerce_dates(pd.read_csv(OPER / f"{name}.csv"))
        total += load_table(engine, df, name, schema)
    for name, src in REPORTS.items():
        path = src / f"{name}.csv"
        if path.exists():
            df = _coerce_dates(pd.read_csv(path))
            total += load_table(engine, df, name, schema)

    if is_pg:
        with engine.begin() as c:
            c.execute(text("SET session_replication_role = 'origin'"))

    # verification snapshot
    q = "SELECT COUNT(*) FROM {}"
    with engine.connect() as c:
        def n(t):
            t = t if engine.dialect.name == "sqlite" else f"{schema}.{t}"
            return c.execute(text(q.format(t))).scalar()
        log.info("Loaded %d rows across %d tables", total, len(LOAD_ORDER) + len(REPORTS))
        log.info("  fact_shipment=%d | fact_freight_invoice=%d | milestones=%d | manifest=%d",
                 n("fact_shipment"), n("fact_freight_invoice"),
                 n("fact_shipment_milestone"), n("meta_exception_manifest"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
