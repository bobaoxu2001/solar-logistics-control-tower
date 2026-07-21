"""Build the reporting date dimension, apply Power BI views, and export CSVs."""

from __future__ import annotations

import sys

import pandas as pd
from sqlalchemy import text

from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import apply_ddl, replace_table

log = get_logger("export_reporting_tables")
REPORTING = DATA_PROCESSED / "reporting"

REPORT_VIEWS = [
    "rpt_dim_date", "rpt_dim_carrier", "rpt_dim_lane", "rpt_dim_product", "rpt_dim_location",
    "rpt_fact_shipment", "rpt_fact_milestone", "rpt_fact_freight_audit",
    "rpt_fact_data_quality", "rpt_fact_accrual", "rpt_fact_claim",
    "rpt_carrier_scorecard", "rpt_lane_scorecard", "rpt_dq_detection_performance",
]


def build_date_dimension(engine) -> pd.DataFrame:
    bounds = pd.read_sql(
        """SELECT MIN(planned_ship_date) AS min_date,
                  MAX(planned_delivery_date) AS max_date
             FROM analytics_shipment""", engine).iloc[0]
    start = pd.Timestamp(bounds["min_date"]).normalize()
    end = pd.Timestamp(bounds["max_date"]).normalize()
    dates = pd.date_range(start, end, freq="D")
    iso = dates.isocalendar()
    out = pd.DataFrame({"date": dates})
    out["date_key"] = dates.strftime("%Y%m%d").astype(int)
    out["year"] = dates.year
    out["quarter"] = "Q" + dates.quarter.astype(str)
    out["month_number"] = dates.month
    out["month_name"] = dates.strftime("%B")
    out["year_month"] = dates.strftime("%Y-%m")
    out["week_of_year"] = iso.week.astype(int).to_numpy()
    out["day_of_month"] = dates.day
    out["day_name"] = dates.strftime("%A")
    out["week_start_date"] = dates - pd.to_timedelta(dates.weekday, unit="D")
    out["month_end_flag"] = dates.is_month_end.astype(int)
    out["weekend_flag"] = (dates.weekday >= 5).astype(int)
    return out[["date_key", "date", "year", "quarter", "month_number", "month_name",
                "year_month", "week_of_year", "day_of_month", "day_name",
                "week_start_date", "month_end_flag", "weekend_flag"]]


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    engine = create_project_engine(cfg)
    date_dim = build_date_dimension(engine)
    replace_table(engine, date_dim, "reporting_date_dim", schema)
    apply_ddl(engine, "11_power_bi_views.sql", schema)

    REPORTING.mkdir(parents=True, exist_ok=True)
    total = 0
    with engine.connect() as conn:
        for view in REPORT_VIEWS:
            qualified = view if engine.dialect.name == "sqlite" else f"{schema}.{view}"
            df = pd.read_sql(text(f"SELECT * FROM {qualified}"), conn)
            df.to_csv(REPORTING / f"{view}.csv", index=False)
            total += len(df)
            log.info("Exported %-29s %8d rows", view, len(df))
    log.info("Reporting export complete: %d views, %d rows", len(REPORT_VIEWS), total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
