"""Build deterministic carrier and lane scorecards from Phase 3 SQL metrics."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import replace_table

log = get_logger("build_scorecards")
ANALYTICS = DATA_PROCESSED / "analytics"


def normalize(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """Min-max normalize a peer group to 0..100 with explicit direction."""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(np.nan, index=series.index, dtype=float)
    lo, hi = numeric.min(), numeric.max()
    if np.isclose(lo, hi):
        return pd.Series(np.where(numeric.notna(), 100.0, np.nan), index=series.index)
    score = (numeric - lo) / (hi - lo) * 100.0
    if not higher_is_better:
        score = 100.0 - score
    return score.round(2)


def build_carrier_scorecard(metrics: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    scfg = cfg["phase3"]["carrier_scorecard"]
    weights = scfg["weights"]
    if not np.isclose(sum(weights.values()), 1.0):
        raise ValueError(f"Carrier scorecard weights must sum to 1.0; got {sum(weights.values()):.6f}")

    out = metrics.sort_values("carrier_id").reset_index(drop=True).copy()
    eligible = out["shipment_count"] >= int(scfg["min_shipments"])
    components = {
        "otif_score": ("otif_pct", True, "otif"),
        "transit_reliability_score": ("transit_reliability_pct", True, "transit_reliability"),
        "cost_competitiveness_score": ("cost_per_kg", False, "cost_competitiveness"),
        "invoice_accuracy_score": ("invoice_accuracy_pct", True, "invoice_accuracy"),
        "pod_compliance_score": ("pod_compliance_pct", True, "pod_compliance"),
        "claims_score": ("claims_rate_pct", False, "claims"),
    }
    for score_col, (metric_col, direction, _weight_key) in components.items():
        out[score_col] = np.nan
        out.loc[eligible, score_col] = normalize(out.loc[eligible, metric_col], direction)

    out["total_score"] = np.nan
    if eligible.any():
        weighted = sum(out.loc[eligible, col] * float(weights[wkey])
                       for col, (_metric, _direction, wkey) in components.items())
        out.loc[eligible, "total_score"] = weighted.round(2)
    out["carrier_rank"] = np.nan
    out.loc[eligible, "carrier_rank"] = (
        out.loc[eligible, "total_score"].rank(method="min", ascending=False).astype(int)
    )

    bands = scfg["classification_bands"]
    def classify(row):
        if row.shipment_count < int(scfg["min_shipments"]):
            return "Insufficient volume"
        if row.total_score >= float(bands["preferred"]):
            return "Preferred"
        if row.total_score >= float(bands["acceptable"]):
            return "Acceptable"
        if row.total_score >= float(bands["improvement"]):
            return "Improvement required"
        return "Critical review"

    out["classification"] = out.apply(classify, axis=1)
    actions = {
        "Preferred": "Prioritize for strategic awards; monitor quarterly",
        "Acceptable": "Maintain allocation; target weakest score component",
        "Improvement required": "Agree a 90-day corrective-action plan",
        "Critical review": "Escalate sourcing review and contingency planning",
        "Insufficient volume": "Collect more volume before ranking",
    }
    out["recommended_action"] = out["classification"].map(actions)
    out["minimum_shipment_threshold"] = int(scfg["min_shipments"])
    out["score_method"] = "Peer min-max; higher OTIF/reliability/accuracy/POD, lower cost/kg/claims"
    return out


def build_lane_scorecard(metrics: pd.DataFrame, analytics: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    out = metrics.sort_values("lane_id").reset_index(drop=True).copy()
    delivered = analytics[analytics["is_delivered"] == 1]
    variability = delivered.groupby("lane_id")["actual_transit_days"].std(ddof=0)
    out["transit_time_variability_days"] = out["lane_id"].map(variability).fillna(0).round(2)

    min_volume = int(cfg["phase3"]["lane_scorecard"]["min_shipments"])
    eligible = out["shipment_count"] >= min_volume
    # Peer-relative thresholds are deterministic and stored on every row for auditability.
    cost_p75 = float(out.loc[eligible, "cost_per_kg"].quantile(0.75))
    variance_p75 = float(out.loc[eligible, "transit_time_variability_days"].quantile(0.75))
    accessorial_p75 = float(out.loc[eligible, "accessorial_rate_pct"].quantile(0.75))
    out["high_cost_flag"] = (eligible & (out["cost_per_kg"] >= cost_p75)).astype(int)
    out["low_service_flag"] = (eligible & (out["otif_pct"] < 80.0)).astype(int)
    out["high_variance_flag"] = (eligible & (out["transit_time_variability_days"] >= variance_p75)).astype(int)
    out["high_accessorial_flag"] = (eligible & (out["accessorial_rate_pct"] >= accessorial_p75)).astype(int)
    out["insufficient_volume_flag"] = (~eligible).astype(int)

    def lane_classification(row):
        if row.insufficient_volume_flag:
            return "Insufficient volume"
        labels = []
        if row.high_cost_flag:
            labels.append("High cost")
        if row.low_service_flag:
            labels.append("Low service")
        if row.high_variance_flag:
            labels.append("High variance")
        if row.high_accessorial_flag:
            labels.append("High accessorial")
        return "; ".join(labels) if labels else "Stable"

    out["service_classification"] = out.apply(lane_classification, axis=1)
    def lane_action(row):
        if row.insufficient_volume_flag:
            return "Monitor until the minimum volume threshold is met"
        actions = []
        if row.high_cost_flag:
            actions.append("benchmark or rebid rate")
        if row.low_service_flag:
            actions.append("carrier service recovery plan")
        if row.high_variance_flag:
            actions.append("review schedule and milestone variability")
        if row.high_accessorial_flag:
            actions.append("audit accessorial root causes")
        return "; ".join(actions).capitalize() if actions else "Maintain and monitor"
    out["recommended_action"] = out.apply(lane_action, axis=1)
    out["minimum_shipment_threshold"] = min_volume
    out["cost_p75_threshold"] = round(cost_p75, 4)
    out["variability_p75_threshold"] = round(variance_p75, 2)
    out["accessorial_p75_threshold"] = round(accessorial_p75, 2)
    return out


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_project_engine(cfg)
    carrier = pd.read_sql("SELECT * FROM v_carrier_metrics", engine)
    lane = pd.read_sql("SELECT * FROM v_lane_metrics", engine)
    analytics = pd.read_sql("SELECT lane_id, is_delivered, actual_transit_days FROM analytics_shipment", engine)

    carrier_out = build_carrier_scorecard(carrier, cfg)
    lane_out = build_lane_scorecard(lane, analytics, cfg)
    replace_table(engine, carrier_out, "carrier_scorecard_result", schema)
    replace_table(engine, lane_out, "lane_scorecard_result", schema)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    carrier_out.to_csv(ANALYTICS / "rpt_carrier_scorecard.csv", index=False)
    lane_out.to_csv(ANALYTICS / "rpt_lane_scorecard.csv", index=False)
    ranked = carrier_out[carrier_out["carrier_rank"].notna()].sort_values("carrier_rank")
    log.info("Carrier scorecard: %d carriers, %d ranked, top=%s (%.2f)",
             len(carrier_out), len(ranked), ranked.iloc[0]["carrier_name"], ranked.iloc[0]["total_score"])
    log.info("Lane scorecard: %d lanes, %d sufficient-volume, %d flagged",
             len(lane_out), int((lane_out["insufficient_volume_flag"] == 0).sum()),
             int((lane_out["service_classification"] != "Stable").sum()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
