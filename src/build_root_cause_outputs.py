"""Select three evidence-led Phase 3 case studies and persist commentary."""

from __future__ import annotations

import sys

import pandas as pd

from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import replace_table

log = get_logger("build_root_cause_outputs")
ANALYTICS = DATA_PROCESSED / "analytics"


def _money(value) -> str:
    return f"${float(value or 0):,.2f}"


def build_cases(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = pd.read_sql("SELECT * FROM v_rca_monthly_otif ORDER BY reporting_month", engine)
    monthly = monthly[monthly["delivered_count"] >= 30].copy()
    monthly["prior_otif_pct"] = monthly["otif_pct"].shift(1)
    monthly["otif_change_pp"] = monthly["otif_pct"] - monthly["prior_otif_pct"]
    deterioration = monthly.dropna(subset=["otif_change_pp"]).sort_values("otif_change_pp").iloc[0]
    month = deterioration["reporting_month"]
    drill = pd.read_sql("SELECT * FROM v_rca_delay_drilldown WHERE reporting_month = :m", engine,
                        params={"m": month})
    drill = drill[drill["delivered_count"] >= 3].sort_values(
        ["late_count", "late_shipment_value_usd"], ascending=False)
    delay_driver = drill.iloc[0]

    freight = pd.read_sql("SELECT * FROM v_rca_freight_pattern", engine)
    freight["recoverable_exposure_usd"] = (
        freight["overcharge_exposure_usd"].fillna(0) + freight["duplicate_exposure_usd"].fillna(0)
    )
    freight_driver = freight.sort_values(
        ["recoverable_exposure_usd", "affected_invoice_count"], ascending=False).iloc[0]

    dq = pd.read_sql("SELECT * FROM v_rca_dq_pattern", engine)
    dq_driver = dq.sort_values(["weighted_exception_points", "detected_count"], ascending=False).iloc[0]

    cases = [
        {
            "case_id": "RCA-01", "case_title": "Monthly OTIF deterioration",
            "problem": f"OTIF declined in {month} versus the preceding reporting month.",
            "observation": f"OTIF moved from {deterioration.prior_otif_pct:.2f}% to {deterioration.otif_pct:.2f}% ({deterioration.otif_change_pp:.2f} pp).",
            "evidence": f"{int(deterioration.late_count)} late shipments; average late delay {deterioration.avg_late_days:.2f} days; late shipment value {_money(deterioration.late_shipment_value_usd)}.",
            "drill_down": f"Largest lane/carrier concentration: {delay_driver.carrier_name}, {delay_driver.origin_name} to {delay_driver.destination_name}, with {int(delay_driver.late_count)} late shipments and {int(delay_driver.claim_count)} claims.",
            "possible_cause": "Service deterioration is concentrated in the identified carrier-lane-month combination; the available data supports concentration, not a definitive causal mechanism.",
            "business_impact": f"Late value on the concentrated segment was {_money(delay_driver.late_shipment_value_usd)}; associated claim cost was {_money(delay_driver.claim_cost_usd)}.",
            "corrective_action": "Transportation Operations should review milestone timestamps and carrier capacity for the concentrated lane, then agree a service-recovery action plan.",
            "follow_up_kpi": "Monthly OTIF, late shipment count, average late days, and claim cost for the identified carrier-lane.",
            "business_owner": "Transportation Operations",
        },
        {
            "case_id": "RCA-02", "case_title": "Freight invoice control exposure",
            "problem": f"{freight_driver.audit_status} is the largest carrier/status recoverable exposure.",
            "observation": f"{int(freight_driver.affected_invoice_count)} invoices for {freight_driver.carrier_name or freight_driver.carrier_id} carry {_money(freight_driver.recoverable_exposure_usd)} of modeled recoverable exposure.",
            "evidence": f"Affected billed amount {_money(freight_driver.invoiced_amount_usd)} across {int(freight_driver.affected_shipment_count)} shipments; shipment value {_money(freight_driver.affected_shipment_value_usd)}.",
            "drill_down": f"Audit status={freight_driver.audit_status}; overcharge component={_money(freight_driver.overcharge_exposure_usd)}; duplicate component={_money(freight_driver.duplicate_exposure_usd)}.",
            "possible_cause": "The pattern is consistent with a billing-control or contractual-rate exception; source records do not prove carrier intent or operational causation.",
            "business_impact": f"Potentially recoverable modeled exposure is {_money(freight_driver.recoverable_exposure_usd)} before dispute validation.",
            "corrective_action": "Accounts Payable should block or dispute flagged invoices, validate supporting rate evidence, and release only after three-way-match clearance.",
            "follow_up_kpi": "Recoverable exposure, disputed invoice count, resolution cycle time, and invoice accuracy.",
            "business_owner": "Accounts Payable",
        },
        {
            "case_id": "RCA-03", "case_title": "Data-quality and rate-card control concentration",
            "problem": f"{dq_driver.rule_name} generates the largest severity-weighted detection population.",
            "observation": f"{int(dq_driver.detected_count)} detections ({dq_driver.severity}) produced {dq_driver.weighted_exception_points:,.0f} weighted exception points.",
            "evidence": f"Manifest={int(dq_driver.manifest_count or 0)}, true positives={int(dq_driver.true_positive_count or 0)}, false negatives={int(dq_driver.false_negative_count or 0)}, recall={float(dq_driver.recall_pct or 0):.2f}%.",
            "drill_down": str(dq_driver.notes or "No additional reconciliation note."),
            "possible_cause": "The concentration is consistent with shared carrier-lane master-data effective dates; detection results identify exposure but do not establish a real-world process cause.",
            "business_impact": "Stale or ambiguous rate coverage increases manual review volume and can prevent reliable expected-freight calculation.",
            "corrective_action": f"{dq_driver.business_owner} should enforce versioned non-overlapping rate windows and pre-expiry renewal alerts.",
            "follow_up_kpi": "Expired-rate detections, rated-invoice percentage, false-negative count, and rate-card renewal lead time.",
            "business_owner": dq_driver.business_owner,
        },
    ]
    evidence = pd.concat([
        monthly.assign(case_id="RCA-01", evidence_level="monthly_trend"),
        drill.assign(case_id="RCA-01", evidence_level="carrier_lane_drilldown"),
        freight.assign(case_id="RCA-02", evidence_level="carrier_audit_status"),
        dq.assign(case_id="RCA-03", evidence_level="dq_rule"),
    ], ignore_index=True, sort=False)
    return pd.DataFrame(cases), evidence


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_project_engine(cfg)
    cases, evidence = build_cases(engine)
    replace_table(engine, cases, "root_cause_case_study", schema)
    replace_table(engine, evidence, "root_cause_evidence", schema)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    cases.to_csv(ANALYTICS / "rpt_root_cause_case_study.csv", index=False)
    evidence.to_csv(ANALYTICS / "rpt_root_cause_evidence.csv", index=False)
    log.info("Root-cause outputs: %d case studies, %d evidence rows", len(cases), len(evidence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
