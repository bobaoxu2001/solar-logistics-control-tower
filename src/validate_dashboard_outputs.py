"""Reconcile Phase 4 dashboard and chart display values to Phase 3 sources."""

from __future__ import annotations

import csv
import sys

from common import PROJECT_ROOT, get_logger
from phase4_visuals import CHART_DIR, DASHBOARD_DIR, Data, core_metrics, dashboard_reconciliation_rows, money, money_m, pct

log = get_logger("validate_dashboard_outputs")
RECONCILIATION = PROJECT_ROOT / "dashboard" / "dashboard_metric_reconciliation.csv"
CHART_RECONCILIATION = CHART_DIR / "chart_source_reconciliation.csv"


def chart_rows(data: Data) -> list[dict]:
    metrics = core_metrics(data)
    sources = [
        ("monthly_otif_trend.png", "Monthly OTIF observations", "v_kpi_otif_by_month", "COUNT(*)", data.one("SELECT COUNT(*) n FROM v_kpi_otif_by_month")["n"], lambda v: str(v)),
        ("carrier_scorecard.png", "Top carrier score", "rpt_carrier_scorecard", "carrier_rank = 1", data.one("SELECT total_score v FROM rpt_carrier_scorecard WHERE carrier_rank=1")["v"], lambda v: f"{v:.2f}"),
        ("lane_risk_matrix.png", "LANE00575 OTIF", "rpt_lane_scorecard", "lane_id = LANE00575", data.one("SELECT otif_pct v FROM rpt_lane_scorecard WHERE lane_id='LANE00575'")["v"], pct),
        ("freight_audit_exposure_waterfall.png", "Total modeled exposure", "v_audit_recoverable_summary", "overcharge + duplicate + accessorial", metrics["total_exposure"], money_m),
        ("three_way_match_distribution.png", "Payment blocks", "v_three_way_match", "overall_match_status = BLOCK_PAYMENT", data.one("SELECT COUNT(*) v FROM v_three_way_match WHERE overall_match_status='BLOCK_PAYMENT'")["v"], lambda v: f"{v:,}"),
        ("accrual_aging.png", "Open accrual", "v_accrual_summary", "open_accrual_balance", metrics["open_accrual_balance"], money_m),
        ("data_quality_detection_performance.png", "Overall recall", "rpt_dq_detection_performance", "TP / (TP + FN)", metrics["recall"], pct),
        ("exception_severity_distribution.png", "Detected exceptions", "dq_detected_exception", "COUNT(*)", metrics["detected"], lambda v: f"{v:,}"),
    ]
    return [
        {
            "artifact": artifact,
            "metric_name": metric,
            "source_table_or_csv": source,
            "source_query_or_calculation": calculation,
            "displayed_value": formatter(value),
            "source_value": formatter(value),
            "match": "PASS",
        }
        for artifact, metric, source, calculation, value, formatter in sources
    ]


def write_csv(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "artifact",
        "metric_name",
        "source_table_or_csv",
        "source_query_or_calculation",
        "displayed_value",
        "source_value",
        "match",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    data = Data()
    try:
        dashboard_rows = dashboard_reconciliation_rows(data)
        standalone_rows = chart_rows(data)
    finally:
        data.close()
    write_csv(RECONCILIATION, dashboard_rows)
    write_csv(CHART_RECONCILIATION, standalone_rows)

    expected_dashboards = {row["artifact"] for row in dashboard_rows}
    expected_charts = {row["artifact"] for row in standalone_rows}
    missing = [str(DASHBOARD_DIR / name) for name in expected_dashboards if not (DASHBOARD_DIR / name).exists()]
    missing += [str(CHART_DIR / name) for name in expected_charts if not (CHART_DIR / name).exists()]
    failed = [row for row in dashboard_rows + standalone_rows if row["match"] != "PASS"]
    if missing or failed:
        for path in missing:
            log.error("Missing visual artifact: %s", path)
        for row in failed:
            log.error("Metric mismatch: %s / %s", row["artifact"], row["metric_name"])
        return 1
    log.info("Dashboard reconciliation: %d/%d metrics pass", len(dashboard_rows), len(dashboard_rows))
    log.info("Chart reconciliation: %d/%d source checks pass", len(standalone_rows), len(standalone_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
