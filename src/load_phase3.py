"""Phase 3 — apply analytics SQL, seed config metadata, materialize detections.

Applies whichever of sql/04..11 exist (so the layer can be built incrementally),
seeds the DQ rule registry + config-driven meta tables from
config/project_config.yaml, then materializes dq_detected_exception from the
v_dq_detected view (adding detected_timestamp, exception_age_days, resolution_status).

Usage:
    python src/load_phase3.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import pandas as pd

from common import DATA_PROCESSED, create_project_engine, database_url, get_logger, load_config
from gen_common import apply_ddl, load_table, replace_table

log = get_logger("load_phase3")
ANALYTICS = DATA_PROCESSED / "analytics"

# Core SQL only.  PostgreSQL resolves view dependencies at CREATE VIEW time,
# so freight audit must precede the scorecard metrics that reference it.
# Root-cause and Power BI views are applied later by run_phase3.py after their
# Python-materialized prerequisite tables exist.
SQL_FILES = [
    "05_logistics_kpis.sql", "07_freight_audit.sql",
    "06_carrier_scorecard.sql", "08_three_way_match.sql", "09_accrual_reporting.sql",
]

# Registry: (rule_id, name, category, target_table, target_column, severity,
#            exception_type, business_description, technical_logic)
DQ_RULES = [
    ("DQ01", "Missing carrier id", "COMPLETENESS", "fact_shipment", "carrier_id", "HIGH",
     "missing_carrier_id", "Every shipment must have an assigned carrier.",
     "carrier_id IS NULL"),
    ("DQ02", "Invalid lane id", "REFERENTIAL", "fact_shipment", "lane_id", "HIGH",
     "invalid_lane", "Shipment lane must exist in the lane master.",
     "lane_id NOT IN (SELECT lane_id FROM dim_lane)"),
    ("DQ03", "Delivery before ship", "TIMELINESS", "fact_shipment", "actual_delivery_date", "CRITICAL",
     "delivery_before_ship", "Delivery cannot occur before the shipment ships.",
     "actual_delivery_date < actual_ship_date"),
    ("DQ04", "Over-delivery", "VALIDITY", "fact_shipment", "delivered_quantity", "MEDIUM",
     "over_delivery", "Delivered quantity cannot exceed the ordered quantity.",
     "delivered_quantity > planned_quantity"),
    ("DQ05", "Partial delivery", "VALIDITY", "fact_shipment", "delivered_quantity", "MEDIUM",
     "partial_delivery", "Short delivery vs the ordered quantity.",
     "delivered_quantity < planned_quantity"),
    ("DQ06", "Missing POD", "PROCESS_COMPLIANCE", "fact_proof_of_delivery", "pod_id", "MEDIUM",
     "missing_pod", "Delivered shipments must have proof of delivery.",
     "delivered shipment with no POD row"),
    ("DQ07", "Shipment without invoice", "PROCESS_COMPLIANCE", "fact_freight_invoice", "invoice_id", "MEDIUM",
     "shipment_without_invoice", "Delivered shipments must be invoiced.",
     "delivered shipment with no invoice row"),
    ("DQ08", "Missing customs documentation", "PROCESS_COMPLIANCE", "fact_shipment_milestone", "milestone_status", "HIGH",
     "missing_customs_doc", "Customs milestone must be completed for customs-required shipments.",
     "milestone_status='MISSED' AND reason='MISSING_CUSTOMS_DOCUMENTATION'"),
    ("DQ09", "Missing HTS code", "COMPLETENESS", "dim_product", "hts_code", "MEDIUM",
     "missing_hts_code", "Every product must carry an HTS classification.",
     "hts_code IS NULL"),
    ("DQ10", "Damage claim requiring action", "PROCESS_COMPLIANCE", "fact_claim", "claim_id", "MEDIUM",
     "damaged_shipment_claim", "Open damage claims must be worked to closure.",
     "claim_type='DAMAGE' AND claim_status='OPEN'"),
    ("DQ11", "Invoice carrier mismatch", "CONSISTENCY", "fact_freight_invoice", "carrier_id", "HIGH",
     "invoice_carrier_mismatch", "Invoice carrier must equal the shipment carrier.",
     "invoice.carrier_id <> shipment.carrier_id"),
    ("DQ12", "Incorrect fuel surcharge", "FINANCIAL_CONTROL", "fact_freight_invoice", "fuel_surcharge", "MEDIUM",
     "incorrect_fuel_surcharge", "Fuel surcharge must equal base x contractual pct.",
     "abs(fuel - base*fuel_pct) beyond audit tolerance"),
    ("DQ13", "Incorrect currency", "FINANCIAL_CONTROL", "fact_freight_invoice", "currency", "MEDIUM",
     "incorrect_currency", "Invoice currency must match the rate-card currency.",
     "invoice.currency <> rate_card.currency"),
    ("DQ14", "Expired rate card", "FINANCIAL_CONTROL", "fact_freight_invoice", "invoice_id", "HIGH",
     "expired_rate_card", "Shipment must ship within the rate card effective window.",
     "ship_date outside applicable rate effective window"),
    ("DQ15", "Duplicate invoice number", "UNIQUENESS", "fact_freight_invoice", "invoice_number", "CRITICAL",
     "duplicate_invoice", "Invoice number must be unique.",
     "invoice_number on >1 record; flag non-canonical copy"),
    ("DQ16", "Duplicate payment risk", "FINANCIAL_CONTROL", "fact_freight_invoice", "invoice_id", "CRITICAL",
     "duplicate_payment_risk", "A shipment must not have multiple PAID invoices.",
     ">1 PAID invoice per shipment; flag non-canonical copy"),
    ("DQ17", "Invoice without valid shipment", "REFERENTIAL", "fact_freight_invoice", "shipment_id", "CRITICAL",
     "invoice_without_shipment", "Invoice must reference an existing shipment.",
     "shipment_id NOT IN fact_shipment"),
    ("DQ18", "Unauthorized accessorial", "FINANCIAL_CONTROL", "fact_accessorial_charge", "contractually_allowed_flag", "HIGH",
     "unauthorized_detention", "Accessorials must be contractually allowed.",
     "contractually_allowed_flag = 0"),
    ("DQ19", "Excessive accessorial", "FINANCIAL_CONTROL", "fact_accessorial_charge", "charge_amount", "HIGH",
     "excessive_demurrage", "Accessorial amount must be within the contractual band.",
     "charge_amount > meta_accessorial_band.max_allowed"),
    ("DQ20", "Paid without approval", "FINANCIAL_CONTROL", "fact_freight_invoice", "approval_status", "CRITICAL",
     "paid_without_approval", "Invoices must be approved before payment.",
     "payment_status='PAID' AND approval_status<>'APPROVED'"),
    ("DQ21", "Invalid milestone sequence", "CONSISTENCY", "fact_shipment_milestone", "actual_timestamp", "HIGH",
     "invalid_milestone_sequence", "Milestone timestamps must be non-decreasing by sequence.",
     "actual_timestamp < prior completed milestone"),
    ("DQ22", "Capacity over 100%", "VALIDITY", "fact_carrier_capacity", "capacity_utilization_pct", "MEDIUM",
     "capacity_over_100", "Capacity utilization must not exceed 100%.",
     "capacity_utilization_pct > 100"),
    ("DQ23", "Broken PO-shipment link", "REFERENTIAL", "fact_shipment", "po_id", "HIGH",
     "broken_po_shipment", "Shipment PO must exist in the PO master.",
     "po_id NOT IN fact_purchase_order"),
    ("DQ24", "Invoice component reconciliation", "FINANCIAL_CONTROL", "fact_freight_invoice", "invoice_total", "HIGH",
     "invoice_component_reconciliation", "Invoice total must equal the sum of components.",
     "abs(total - (base+fuel+accessorial+tax)) > 0.01"),
    ("DQ25", "Missing required delivery milestone", "PROCESS_COMPLIANCE", "fact_shipment_milestone", "milestone_type", "HIGH",
     "missing_required_milestone", "Delivered shipments need a completed delivery milestone.",
     "no completed CUSTOMER_DELIVERY milestone"),
]


def seed_registry(engine, schema, cfg):
    owners = cfg["phase3"]["exception_owners"]
    sla = cfg["phase3"]["resolution_sla_hours"]
    rows = []
    for rid, name, cat, tbl, col, sev, etype, bdesc, tlogic in DQ_RULES:
        rows.append({
            "rule_id": rid, "rule_name": name, "rule_category": cat,
            "target_table": tbl, "target_column": col, "severity": sev,
            "business_description": bdesc, "technical_logic": tlogic,
            "business_owner": owners.get(etype, "Logistics Analytics"),
            "exception_type": etype, "expected_resolution_sla_hours": int(sla.get(sev, 168)),
            "active_flag": 1,
        })
    load_table(engine, pd.DataFrame(rows), "dq_rule", schema)


def seed_meta(engine, schema, cfg):
    p3 = cfg["phase3"]
    load_table(engine, pd.DataFrame(
        [{"severity": k, "weight": v} for k, v in p3["dq_severity_weights"].items()]),
        "meta_dq_severity_weight", schema)
    load_table(engine, pd.DataFrame(
        [{"charge_type": k, "max_allowed": v} for k, v in p3["accessorial_max_allowed"].items()]),
        "meta_accessorial_band", schema)
    load_table(engine, pd.DataFrame(
        [{"context_key": "as_of_date", "context_value": str(p3["as_of_date"])}]),
        "meta_run_context", schema)
    # scorecard weights (Phase 2 created the table empty)
    load_table(engine, pd.DataFrame(
        [{"metric_name": k, "weight": v, "description": "carrier scorecard weight"}
         for k, v in p3["carrier_scorecard"]["weights"].items()]),
        "meta_scorecard_weight", schema)


def materialize_detections(engine, schema, cfg):
    as_of = pd.Timestamp(cfg["phase3"]["as_of_date"])
    tbl = "v_dq_detected" if engine.dialect.name == "sqlite" else f"{schema}.v_dq_detected"
    det = pd.read_sql(f"SELECT * FROM {tbl}", engine)
    det.insert(0, "detected_exception_id", [f"DE-{i:06d}" for i in range(1, len(det) + 1)])
    det["detected_timestamp"] = as_of
    ref = pd.to_datetime(det["reference_date"], errors="coerce")
    det["exception_age_days"] = (as_of - ref).dt.days
    det["resolution_status"] = "OPEN"
    # Persist as a table + CSV
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    cols = ["detected_exception_id", "rule_id", "exception_type", "record_id", "record_type",
            "detected_timestamp", "severity", "exception_description", "business_owner",
            "resolution_status", "exception_age_days", "source_layer"]
    out = det[cols]
    replace_table(engine, out, "dq_detected_exception", schema)
    out.to_csv(ANALYTICS / "dq_detected_exception.csv", index=False)
    return out


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_project_engine(cfg)
    log.info("Target: %s (%s)", database_url(cfg).split("@")[-1], engine.dialect.name)

    from common import SQL_DIR
    # DQ metadata must be seeded and detections materialized before the lane
    # scorecard view can allocate exceptions to lanes. This ordering is also
    # valid on PostgreSQL, which does not allow views over missing relations.
    apply_ddl(engine, "04_data_quality_rules.sql", schema)
    log.info("Applied 04_data_quality_rules.sql")
    seed_registry(engine, schema, cfg)
    seed_meta(engine, schema, cfg)
    det = materialize_detections(engine, schema, cfg)

    for f in SQL_FILES:
        if (SQL_DIR / f).exists():
            apply_ddl(engine, f, schema)
            log.info("Applied %s", f)
    log.info("dq_rule=%d rules | dq_detected_exception=%d rows", len(DQ_RULES), len(det))
    by_sev = det["severity"].value_counts().to_dict()
    log.info("detected by severity: %s", by_sev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
