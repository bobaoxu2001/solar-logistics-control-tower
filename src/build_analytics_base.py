"""Phase 3 — materialize the analytics base table `analytics_shipment`.

Date-difference KPIs (delay days, transit days, GIT age) are computed here in
pandas so the downstream SQL KPI views stay portable (no dialect-specific date
functions). Built from the OPERATIONAL layer (the exception-injected canonical
tables) — i.e. the real control-tower view; injected data-quality exceptions
therefore affect these KPIs and are quantified separately by the DQ layer.

Also emits `analytics_shipment_clean` from the clean baseline CSVs so tests can
verify KPI *logic* on uncorrupted data.

Usage:
    python src/build_analytics_base.py
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from common import DATA_PROCESSED, create_project_engine, get_logger, load_config
from gen_common import replace_table

log = get_logger("build_analytics_base")
CLEAN = DATA_PROCESSED / "clean"
ANALYTICS = DATA_PROCESSED / "analytics"


def _enrich(ship, lanes, locs, prods, carriers, pods, invoices, as_of):
    df = ship.copy()
    for c in ["planned_ship_date", "actual_ship_date", "planned_delivery_date", "actual_delivery_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    df = df.merge(lanes[["lane_id", "standard_transit_days"]], on="lane_id", how="left")
    df = df.merge(locs[["location_id", "country", "region"]].rename(
        columns={"location_id": "destination_location_id", "country": "destination_country",
                 "region": "destination_region"}), on="destination_location_id", how="left")
    df = df.merge(prods[["product_id", "product_category"]], on="product_id", how="left")
    df = df.merge(carriers[["carrier_id", "carrier_name"]], on="carrier_id", how="left")

    delivered = df["shipment_status"] == "DELIVERED"
    df["is_delivered"] = delivered.astype(int)

    # OTIF (delivered shipments only; flags NULL for in-transit)
    df["on_time_flag"] = np.where(delivered, (df["actual_delivery_date"] <= df["planned_delivery_date"]).astype("float"), np.nan)
    df["in_full_flag"] = np.where(delivered, (df["delivered_quantity"] >= df["planned_quantity"]).astype("float"), np.nan)
    df["otif_flag"] = np.where(delivered, ((df["on_time_flag"] == 1) & (df["in_full_flag"] == 1)).astype("float"), np.nan)
    df["late_flag"] = np.where(delivered, (df["actual_delivery_date"] > df["planned_delivery_date"]).astype("float"), np.nan)
    df["partial_flag"] = np.where(delivered, (df["delivered_quantity"] < df["planned_quantity"]).astype("float"), np.nan)

    # Delay / transit days
    df["delay_days"] = np.where(delivered, (df["actual_delivery_date"] - df["planned_delivery_date"]).dt.days, np.nan)
    df["planned_transit_days"] = (df["planned_delivery_date"] - df["planned_ship_date"]).dt.days
    df["actual_transit_days"] = np.where(delivered, (df["actual_delivery_date"] - df["actual_ship_date"]).dt.days, np.nan)
    df["transit_variance_days"] = df["actual_transit_days"] - df["planned_transit_days"]
    df["within_standard_flag"] = np.where(
        delivered & df["standard_transit_days"].notna(),
        (df["actual_transit_days"] <= df["standard_transit_days"]).astype("float"), np.nan)

    # Goods in transit as of the reporting date
    git = df["shipment_status"] == "IN_TRANSIT"
    df["git_flag"] = git.astype(int)
    # Phase 2 classifies every post-snapshot delivery as IN_TRANSIT, including
    # planned movements whose modeled ship date is also after the snapshot.
    # Keep that agreed 312-record control-tower population, but never report a
    # nonsensical negative age for a not-yet-departed modeled movement.
    raw_git_age = (as_of - df["actual_ship_date"]).dt.days.clip(lower=0)
    df["git_age_days"] = np.where(git, raw_git_age, np.nan)
    df["overdue_git_flag"] = np.where(git, (df["planned_delivery_date"] < as_of).astype("float"), np.nan)

    # Reporting month (delivery month for delivered, planned for GIT)
    rep = np.where(delivered, df["actual_delivery_date"], df["planned_delivery_date"])
    df["reporting_month"] = pd.to_datetime(rep).to_period("M").astype(str)

    df["has_pod"] = df["shipment_id"].isin(set(pods["shipment_id"])).astype(int)
    df["has_invoice"] = df["shipment_id"].isin(set(invoices["shipment_id"].dropna())).astype(int)
    return df


BASE_COLS = [
    "shipment_id", "source_record_id", "carrier_id", "carrier_name", "lane_id", "product_id",
    "product_category", "origin_location_id", "destination_location_id", "destination_country",
    "destination_region", "warehouse_id", "shipment_mode", "incoterm", "shipment_status",
    "is_delivered", "hazmat_flag", "customs_required_flag", "planned_quantity", "delivered_quantity",
    "shipment_weight_kg", "shipment_value_usd", "planned_ship_date", "actual_ship_date",
    "planned_delivery_date", "actual_delivery_date", "standard_transit_days",
    "on_time_flag", "in_full_flag", "otif_flag", "late_flag", "partial_flag", "delay_days",
    "planned_transit_days", "actual_transit_days", "transit_variance_days", "within_standard_flag",
    "git_flag", "git_age_days", "overdue_git_flag", "reporting_month", "has_pod", "has_invoice",
]


def _read_db(engine, table):
    return pd.read_sql(f"SELECT * FROM {table}", engine)


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    as_of = pd.Timestamp(cfg["phase3"]["as_of_date"])
    engine = create_project_engine(cfg)
    ANALYTICS.mkdir(parents=True, exist_ok=True)

    lanes = _read_db(engine, "dim_lane")
    locs = _read_db(engine, "dim_location")
    prods = _read_db(engine, "dim_product")
    carriers = _read_db(engine, "dim_carrier")

    # OPERATIONAL analytics base (canonical tables = exception-injected)
    op = _enrich(_read_db(engine, "fact_shipment"), lanes, locs, prods, carriers,
                 _read_db(engine, "fact_proof_of_delivery"), _read_db(engine, "fact_freight_invoice"), as_of)
    replace_table(engine, op[BASE_COLS], "analytics_shipment", schema)
    op[BASE_COLS].to_csv(ANALYTICS / "analytics_shipment.csv", index=False)

    # CLEAN analytics base (for KPI-logic tests) from the clean baseline CSVs
    cl = _enrich(pd.read_csv(CLEAN / "fact_shipment.csv"), lanes, locs, prods, carriers,
                 pd.read_csv(CLEAN / "fact_proof_of_delivery.csv"),
                 pd.read_csv(CLEAN / "fact_freight_invoice.csv"), as_of)
    replace_table(engine, cl[BASE_COLS], "analytics_shipment_clean", schema)
    cl[BASE_COLS].to_csv(ANALYTICS / "analytics_shipment_clean.csv", index=False)

    d = op[op["is_delivered"] == 1]
    log.info("analytics_shipment: %d rows (operational) | %d clean", len(op), len(cl))
    log.info("OTIF(op)=%.1f%% on-time=%.1f%% in-full=%.1f%% | GIT=%d | avg delay=%.1fd",
             d["otif_flag"].mean() * 100, d["on_time_flag"].mean() * 100,
             d["in_full_flag"].mean() * 100, int(op["git_flag"].sum()), d["delay_days"].mean())
    return 0


if __name__ == "__main__":
    sys.exit(main())
