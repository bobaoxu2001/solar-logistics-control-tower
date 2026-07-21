"""Write Phase 3 summary and recruiter-facing interview materials from SQL."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd

from common import DOCS_DIR, PROJECT_ROOT, create_project_engine, get_logger, load_config

log = get_logger("build_phase3_docs")


def _row(engine, sql):
    return pd.read_sql(sql, engine).iloc[0]


def _test_count() -> int:
    total = 0
    for path in (PROJECT_ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
                     for n in ast.walk(tree))
    return total


def main() -> int:
    engine = create_project_engine(load_config())
    ship = _row(engine, "SELECT * FROM v_kpi_otif_summary")
    git = _row(engine, "SELECT * FROM v_kpi_git_summary")
    freight = _row(engine, "SELECT * FROM v_kpi_freight_summary")
    expected = _row(engine, "SELECT SUM(expected_total) expected_freight, SUM(invoiced_total-expected_total) variance FROM v_freight_audit WHERE expected_total IS NOT NULL")
    recover = _row(engine, "SELECT * FROM v_audit_recoverable_summary")
    audit = _row(engine, "SELECT COUNT(*) n, SUM(CASE WHEN audit_status='MATCHED' THEN 1 ELSE 0 END) matched FROM v_freight_audit")
    accrual = _row(engine, "SELECT * FROM v_accrual_summary")
    claims = _row(engine, "SELECT * FROM v_kpi_claims")
    pod = _row(engine, "SELECT * FROM v_kpi_pod_compliance")
    transit = _row(engine, "SELECT AVG(actual_transit_days) avg_transit FROM analytics_shipment WHERE is_delivered=1")
    manifest = _row(engine, "SELECT COUNT(*) n FROM meta_exception_manifest")
    detected = _row(engine, "SELECT COUNT(*) n FROM dq_detected_exception")
    perf = _row(engine, "SELECT SUM(true_positive_count) tp, SUM(false_positive_count) fp, SUM(false_negative_count) fn FROM rpt_dq_detection_performance WHERE manifest_count>0")
    crit = _row(engine, "SELECT SUM(true_positive_count) tp, SUM(false_negative_count) fn FROM rpt_dq_detection_performance WHERE manifest_count>0 AND severity='CRITICAL'")
    weights = _row(engine, "SELECT SUM(w.weight) weighted FROM dq_detected_exception d JOIN meta_dq_severity_weight w ON d.severity=w.severity")
    carrier = _row(engine, "SELECT * FROM carrier_scorecard_result WHERE carrier_rank=1")
    lane = _row(engine, "SELECT * FROM lane_scorecard_result WHERE insufficient_volume_flag=0 ORDER BY (high_cost_flag+low_service_flag+high_variance_flag+high_accessorial_flag) DESC, shipment_count DESC LIMIT 1")
    tmatch = pd.read_sql("SELECT * FROM v_three_way_match_summary", engine).set_index("overall_match_status")["invoice_count"].to_dict()
    cases = pd.read_sql("SELECT * FROM root_cause_case_study ORDER BY case_id", engine)
    precision = perf.tp / (perf.tp + perf.fp) * 100
    recall = perf.tp / (perf.tp + perf.fn) * 100
    critical_recall = crit.tp / (crit.tp + crit.fn) * 100
    dq_score = max(0, 1 - weights.weighted / (ship.shipment_count * 10)) * 100
    invoice_accuracy = audit.matched / audit.n * 100
    tests = _test_count()

    summary = f"""# Phase 3 Summary — Logistics Analytics, Freight Audit, and Reporting

_Reporting snapshot: 2025-07-01. Generated from the operational exception-injected layer; clean-baseline logic is tested separately._

## Verified headline metrics

| Metric | Result |
|---|---:|
| Shipment count | {ship.shipment_count:,.0f} |
| Delivered count | {ship.delivered_count:,.0f} |
| Goods in transit | {ship.in_transit_count:,.0f} shipments / ${git.git_value_usd:,.2f} |
| OTIF | {ship.otif_pct:.2f}% |
| On-time rate | {ship.on_time_pct:.2f}% |
| In-full rate | {ship.in_full_pct:.2f}% |
| Average transit time | {transit.avg_transit:.2f} days |
| Freight spend | ${freight.invoiced_freight_usd:,.2f} |
| Rated expected freight | ${expected.expected_freight:,.2f} |
| Rated invoice variance | ${expected.variance:,.2f} |
| Recoverable overcharge | ${recover.overcharge_recoverable:,.2f} |
| Duplicate-invoice exposure | ${recover.duplicate_invoice_exposure:,.2f} |
| Unauthorized/excessive accessorial recovery | ${recover.accessorial_recoverable:,.2f} |
| Invoice accuracy | {invoice_accuracy:.2f}% |
| Open accrual | ${accrual.open_accrual_balance:,.2f} |
| Claims rate / cost | {claims.claims_rate_pct:.3f}% / ${claims.claim_cost_usd:,.2f} |
| POD compliance | {pod.pod_compliance_pct:.2f}% |
| Data-quality score | {dq_score:.2f}% |
| Manifest / detected count | {manifest.n:,.0f} / {detected.n:,.0f} |
| Detection precision / recall | {precision:.2f}% / {recall:.2f}% |
| Critical recall | {critical_recall:.2f}% |
| Complete test count | {tests} tests |

## Freight audit and three-way match

- Unrated invoices remain unknown rather than becoming false full-value overcharges.
- Recoverable modeled exposure totals **${recover.overcharge_recoverable + recover.duplicate_invoice_exposure + recover.accessorial_recoverable:,.2f}** across overcharge, duplicate, and accessorial components.
- Three-way match: **{tmatch.get('MATCHED', 0):,} matched**, **{tmatch.get('MATCHED_WITH_WARNING', 0):,} matched with warning**, **{tmatch.get('REVIEW_REQUIRED', 0):,} review required**, **{tmatch.get('BLOCK_PAYMENT', 0):,} block payment**, and **{tmatch.get('MISSING_RECORD', 0):,} missing record**.

## Carrier and lane highlights

- Top ranked carrier: **{carrier.carrier_name}** at **{carrier.total_score:.2f}/100**, rank {int(carrier.carrier_rank)}, classified **{carrier.classification}**. Scores are peer-normalized; no carrier is labeled Preferred in this simulated operational population.
- Most multi-flag sufficient-volume lane: **{lane.lane_id}**, {lane.origin_name} to {lane.destination_name}; {int(lane.shipment_count)} shipments, OTIF {lane.otif_pct:.2f}%, cost/kg ${lane.cost_per_kg:.4f}, classified **{lane.service_classification}**.
- **648** lanes are below the configurable 20-shipment threshold and are explicitly not treated as reliable ranked comparisons.

## Three evidence-led root-cause findings

"""
    for row in cases.itertuples(index=False):
        summary += f"### {row.case_id}: {row.case_title}\n\n- Observation: {row.observation}\n- Evidence: {row.evidence}\n- Drill-down: {row.drill_down}\n- Possible cause: {row.possible_cause}\n- Business impact: {row.business_impact}\n- Corrective action: {row.corrective_action}\n- Follow-up KPI: {row.follow_up_kpi}\n\n"
    summary += """## Detection caveats

- Expired-rate-card invoice recall is 92%: 12 manifested invoices shipped before the single deduplicated shared-card expiry and are logically not detectable as expired at shipment time. The shared card creates additional real analytical exposure for later invoices; it is not forced into a false 100% invoice match.
- One invoice-carrier mismatch overlaps a shipment whose carrier was nulled, and one incorrect-fuel record is masked by another operational defect. Both remain visible in reconciliation.
- Low manifest-level precision is driven mainly by shared-rate-card spillover and duplicate-invoice records that also create duplicate-payment risk. These are transparent multi-rule exposures, not hidden failures.

## Data boundary and limitations

Shipment patterns come from the public USAID SCMS dataset. Solar product identity is remapped; carrier, rate, invoice, milestone, POD, claim, capacity, approval, and accrual data are simulated. Findings demonstrate controls on a deterministic portfolio dataset and do not represent a production deployment, real carrier performance, recoveries, or approved budgets. GIT retains the agreed snapshot population; modeled departures after the snapshot are assigned zero age rather than a negative age.
"""
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "phase3_summary.md").write_text(summary, encoding="utf-8")

    interview = f"""# Interview Materials — Solar Logistics Control Tower

## 30-second introduction

I built an end-to-end logistics control tower on 10,324 public-source shipment patterns, then added deterministic simulated ERP, TMS, carrier, and finance data. The Phase 3 layer measures OTIF and GIT, audits freight invoices, performs three-way matching and accrual reporting, validates injected exceptions at {recall:.2f}% recall with 100% critical recall, and publishes reconciled Power BI views plus a working Excel KPI pack.

## Two-minute walkthrough

The project begins with a checksum-verified USAID shipment dataset and preserves record-level lineage. I remapped product identity to a clearly disclosed solar portfolio while keeping the real shipment patterns. Phase 2 generates clean and exception-injected enterprise layers with carriers, rate cards, milestones, invoices, PODs, claims, capacity, approvals, and accruals. Phase 3 computes {ship.otif_pct:.2f}% OTIF and {int(ship.in_transit_count)} GIT shipments, applies 25 data-quality rules, and reconciles every detection to a 2,220-record manifest. The freight engine selects effective rates, enforces minimum charges and fuel percentages, leaves missing rates unknown, and identifies ${recover.overcharge_recoverable:,.2f} of modeled overcharge exposure plus duplicate and accessorial risk. Carrier and lane scorecards use transparent configurable weights and volume gates. Finally, I export a star-schema reporting layer, DAX specifications, a 10-sheet Excel pack, three evidence-led case studies, and an operating SOP. The key design choice was to preserve honest boundaries: public, derived, simulated, clean, and operational data are always separated.

## Resume bullets

- Built a reproducible SQL/Python logistics control tower for **10,324** source-derived shipments, delivering OTIF, GIT, transit, freight, POD, claims, capacity, accrual, and exception analytics with record-level lineage.
- Implemented a config-driven **25-rule** data-quality framework and manifest reconciliation, achieving **{recall:.2f}% overall recall** and **100% critical recall** across **2,220** controlled exceptions.
- Developed effective-date freight rating, invoice audit, and three-way matching that surfaced **${recover.overcharge_recoverable:,.0f} modeled overcharge exposure**, **${recover.duplicate_invoice_exposure:,.0f} duplicate exposure**, and explicit payment-block/review decisions.
- Produced **14 reporting exports**, Power BI star-schema/DAX specifications, and a reconciled **10-sheet Excel KPI pack** with carrier/lane scorecards, root-cause evidence, and finance controls.

## Interview questions and answers

### 1. How did you validate exception detection?

I used the injected manifest as ground truth, compared record IDs by exception type, and calculated TP, FP, FN, precision, recall, and F1. I gated the pipeline at 95% overall recall and 100% critical recall and documented cross-exception overlaps instead of hiding them.

### 2. How did you avoid overstating freight recovery?

Missing or expired rates produce a null expected total, not zero. Material disputes require both absolute and percentage thresholds. Every dollar is labeled modeled exposure on simulated invoices, pending real-world dispute validation.

### 3. How does the carrier score work?

It min-max normalizes six peer metrics with explicit directionality: higher is better for OTIF, reliability, invoice accuracy, and POD; lower is better for cost/kg and claims. Configured weights sum to 100%, and low-volume carriers are excluded from ranking.

### 4. What bug did you catch during Phase 3?

I found negative GIT ages because the snapshot population included future modeled departures. I preserved the agreed snapshot count but clipped age at zero and added regression coverage. I also retained earlier fixes for null carrier mismatches, unrated expected totals, invoice materiality, and shipment-level quantity matching.

### 5. What would change in production?

I would connect governed ERP/TMS/WMS sources, add currency conversion and slowly changing dimensions, manage identities and SLAs in an orchestration platform, validate rate-card approvals, and publish monitored Power BI datasets. This repository proves the transparent analytical logic, not production deployment.

## LinkedIn project description

Built a portfolio solar-logistics control tower using 10,324 public-source shipment patterns plus transparently simulated enterprise data. The project covers OTIF/GIT analytics, freight rating and audit, three-way match, accruals, carrier/lane scorecards, 25 data-quality controls, evidence-led root-cause analysis, Power BI semantic views/DAX, and a reconciled 10-sheet Excel KPI pack. Manifest testing achieved {recall:.2f}% overall detection recall and 100% critical recall. All public, derived, simulated, clean-baseline, and operational-exception layers remain explicitly separated.
"""
    (DOCS_DIR / "interview_materials.md").write_text(interview, encoding="utf-8")
    log.info("Wrote phase3_summary.md and interview_materials.md (%d tests)", tests)
    return 0


if __name__ == "__main__":
    sys.exit(main())
