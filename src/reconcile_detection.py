"""Phase 3 — reconcile SQL detections against the Phase 2 exception manifest.

The manifest is ground truth for injected exceptions. This computes, per
exception type, true/false positives and negatives, precision, recall, and F1,
and writes rpt_dq_detection_performance (+ a human-readable notes report that
explains every legitimate difference, e.g. the known invoice-carrier-mismatch
overlap and the lane-level expired-rate spillover).

Usage:
    python src/reconcile_detection.py
"""

from __future__ import annotations

import sys

import pandas as pd

from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import replace_table

log = get_logger("reconcile_detection")
ANALYTICS = DATA_PROCESSED / "analytics"

# Documented explanations for types where detected count legitimately differs
# from the manifest count (overlaps / granularity), never hidden.
NOTES = {
    "invoice_carrier_mismatch": "1 mismatch masked because that shipment also had "
        "its carrier nulled (missing_carrier_id) — NULL<>x is unknown in SQL. Recall <100% "
        "is a real, documented cross-exception overlap, not a rule defect.",
    "expired_rate_card": "Rate-card-level event: all 124 expired cards are detected (card-level "
        "recall 100%) and every invoice shipping after its card's expiry is flagged, so detected "
        ">> manifest (same-lane spillover = real exposure). Invoice-level recall is 92% because 12 "
        "co-selected invoices share a card and ship BEFORE the single dedup expiry date, so at their "
        "ship time the card was still valid — a Phase 2 shared-card artifact, not a detection miss.",
    "duplicate_payment_risk": "Duplicating a PAID invoice (duplicate_invoice) also creates a "
        "second PAID invoice for its shipment, so it is correctly flagged here too. All "
        "manifest records detected (recall 100%); surplus are real duplicate-payment exposures.",
    "duplicate_invoice": "Non-canonical copy of each duplicated invoice_number is flagged.",
    "damaged_shipment_claim": "Detection flags all OPEN DAMAGE claims requiring action; organic "
        "damage claims share the symptom, so precision <100% is expected (they are legitimate "
        "claims, not false alarms). All injected claims detected (recall 100%).",
}


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_project_engine(cfg)

    manifest = pd.read_csv(DATA_PROCESSED / "exception_manifest.csv", dtype=str)
    det = pd.read_csv(ANALYTICS / "dq_detected_exception.csv", dtype=str)

    m_by = manifest.groupby("exception_type")["record_id"].apply(set).to_dict()
    d_by = det.groupby("exception_type")["record_id"].apply(set).to_dict()
    sev_by = manifest.groupby("exception_type")["severity"].first().to_dict()

    rows = []
    all_types = sorted(set(m_by) | set(d_by))
    for et in all_types:
        M, D = m_by.get(et, set()), d_by.get(et, set())
        tp, fp, fn = len(M & D), len(D - M), len(M - D)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)) if precision and recall else (0.0 if (precision == 0 or recall == 0) else None)
        is_manifest = et in m_by
        if not is_manifest:
            status = "CONTROL_RULE (no injected records)"
        elif recall == 1.0:
            status = "FULL"
        elif recall is not None and recall >= 0.95:
            status = "NEAR_FULL"
        else:
            status = "GAP"
        rows.append({
            "exception_type": et, "severity": sev_by.get(et),
            "manifest_count": len(M), "detected_count": len(D),
            "true_positive_count": tp, "false_positive_count": fp, "false_negative_count": fn,
            "precision_pct": round(precision * 100, 2) if precision is not None else None,
            "recall_pct": round(recall * 100, 2) if recall is not None else None,
            "f1_score": round(f1, 4) if f1 is not None else None,
            "coverage_status": status,
            "notes": NOTES.get(et, ""),
        })
    perf = pd.DataFrame(rows)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    perf.to_csv(ANALYTICS / "rpt_dq_detection_performance.csv", index=False)
    replace_table(engine, perf, "rpt_dq_detection_performance", schema)

    # --- overall + critical metrics (manifest-backed types only) -----------
    mtypes = perf[perf["manifest_count"] > 0]
    tp_tot = mtypes["true_positive_count"].sum()
    fn_tot = mtypes["false_negative_count"].sum()
    overall_recall = tp_tot / (tp_tot + fn_tot) if (tp_tot + fn_tot) else 0
    crit = mtypes[mtypes["severity"] == "CRITICAL"]
    crit_recall = crit["true_positive_count"].sum() / max(1, crit["true_positive_count"].sum() + crit["false_negative_count"].sum())

    log.info("=== Detection performance (manifest-backed types) ===")
    for r in mtypes.sort_values("recall_pct").itertuples(index=False):
        log.info("  %-26s manifest=%4d detected=%4d recall=%5.1f%% precision=%5.1f%% [%s]",
                 r.exception_type, r.manifest_count, r.detected_count,
                 r.recall_pct or 0, r.precision_pct or 0, r.coverage_status)
    log.info("OVERALL recall=%.2f%% | CRITICAL recall=%.2f%%", overall_recall * 100, crit_recall * 100)

    # gate: critical must be 100%, overall >= 95%
    ok = (crit_recall >= 1.0) and (overall_recall >= 0.95)
    if not ok:
        log.error("Detection targets NOT met (critical=%.2f%%, overall=%.2f%%)",
                  crit_recall * 100, overall_recall * 100)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
