"""Phase 2 — generate enterprise master / dimension data from staged shipments.

Deterministic (seeded). Writes clean-baseline CSVs to data/processed/clean/ and
a shared per-shipment resolution (origin/destination/mode/lane/warehouse) to
data/interim/shipment_resolved.csv, which generate_enterprise_data.py reuses so
the two modules never diverge.

Outputs (data/processed/clean/):
  dim_location.csv, dim_location_xref.csv, dim_hts_code.csv, dim_product.csv,
  dim_business_partner.csv, dim_supplier.csv, dim_warehouse.csv,
  dim_carrier.csv, dim_lane.csv, dim_rate_card.csv
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from common import DATA_INTERIM, DATA_PROCESSED, ensure_dirs, get_logger, load_config
from gen_common import (
    DERIVED, PUBLIC, SIMULATED, detect_site_country, record_rng, region_of,
    stream_rng, warehouse_for,
)

log = get_logger("generate_master_data")
CLEAN = DATA_PROCESSED / "clean"


def _load_stg() -> pd.DataFrame:
    return pd.read_csv(
        DATA_PROCESSED / "stg_shipment.csv",
        parse_dates=["po_sent_date", "reporting_scheduled_delivery_date",
                     "reporting_actual_delivery_date"],
    )


# ---------------------------------------------------------------------------
# Locations + xref
# ---------------------------------------------------------------------------
def build_locations(stg: pd.DataFrame, cfg: dict):
    loc_rows, xref_rows = [], []
    seen = {}  # natural_key -> location_id

    def add(loc_id, name, country, region, ltype, data_class, city=None, state=None):
        loc_rows.append({
            "location_id": loc_id, "location_name": name, "city": city,
            "state_or_province": state, "country": country, "region": region,
            "location_type": ltype, "latitude": None, "longitude": None,
            "active_flag": 1, "data_class": data_class,
        })

    # Manufacturing sites (origins) — deterministic IDs by sorted site name.
    sites = sorted(stg["manufacturing_site"].dropna().unique())
    for i, site in enumerate(sites, 1):
        loc_id = f"LOCMFG{i:03d}"
        country, method = detect_site_country(site)
        add(loc_id, site, country, region_of(country), "MANUFACTURING_SITE",
            PUBLIC if country else DERIVED)
        seen[("MFG", site)] = loc_id
        xref_rows.append({"xref_id": f"XR-MFG-{i:03d}", "raw_location_string": site,
                          "raw_field": "manufacturing_site", "location_id": loc_id,
                          "match_method": method, "data_class": DERIVED})

    # Destination countries — one distribution-center location each.
    countries = sorted(stg["destination_country"].dropna().unique())
    for i, ctry in enumerate(countries, 1):
        loc_id = f"LOCDST{i:03d}"
        add(loc_id, f"{ctry} Distribution Center", ctry, region_of(ctry),
            "DISTRIBUTION_CENTER", DERIVED)
        seen[("DST", ctry)] = loc_id
        xref_rows.append({"xref_id": f"XR-DST-{i:03d}", "raw_location_string": ctry,
                          "raw_field": "destination_country", "location_id": loc_id,
                          "match_method": "EXACT", "data_class": DERIVED})

    # Warehouse locations (simulated DC network).
    for wh in cfg["phase2"]["warehouses"]:
        loc_id = f"LOC{wh['warehouse_id']}"
        add(loc_id, wh["warehouse_name"], None, wh["region"], "WAREHOUSE", SIMULATED)
        seen[("WH", wh["warehouse_id"])] = loc_id

    return pd.DataFrame(loc_rows), pd.DataFrame(xref_rows), seen


# ---------------------------------------------------------------------------
# HTS + products
# ---------------------------------------------------------------------------
def build_hts(cfg: dict) -> pd.DataFrame:
    rows = []
    for cat, attrs in cfg["phase2"]["product_category_attrs"].items():
        rows.append({
            "hts_code": f"{attrs['hts_prefix']}.40.{cat[:3]}",
            "product_category": cat,
            "description": f"Illustrative classification for {cat.replace('_', ' ').title()}",
            "effective_start_date": "2015-01-01", "effective_end_date": "2099-12-31",
            "hazardous_material_flag": int(attrs["hazmat"]),
            "customs_document_required_flag": 1,
            "code_type": "SIMULATED_ILLUSTRATIVE", "data_class": SIMULATED,
        })
    return pd.DataFrame(rows)


def build_products(stg: pd.DataFrame, cfg: dict, hts: pd.DataFrame) -> pd.DataFrame:
    p2 = cfg["phase2"]
    n = p2["products_per_category"]
    hts_by_cat = dict(zip(hts["product_category"], hts["hts_code"]))
    labels = cfg["adaptation"]["product_category_labels"]
    prefix = {"SOLAR_MODULE": "SG-PVM", "INVERTER": "SG-INV",
              "BATTERY_ESS": "SG-BES", "BOS_COMPONENT": "SG-BOS"}
    rows = []
    for cat, attrs in p2["product_category_attrs"].items():
        g = stg[stg["product_category"] == cat]
        gw = g[g["weight_kg"].notna() & (g["line_item_quantity"] > 0)]
        med_w = float((gw["weight_kg"] / gw["line_item_quantity"]).median()) if len(gw) else 1.0
        med_v = float((g["line_item_value_usd"] / g["line_item_quantity"]).median())
        rng = stream_rng(f"product:{cat}")
        # 5 SKUs spread deterministically around the observed medians.
        factors = np.linspace(0.8, 1.2, n)
        for i, f in enumerate(factors, 1):
            rows.append({
                "product_id": f"PRD-{cat[:3]}-{i:02d}",
                "product_sku": f"{prefix[cat]}-{int(100+ i*17)}-{i:02d}",
                "product_category": cat,
                "product_description": f"{labels[cat]} — nominal pack unit variant {i}",
                "unit_of_measure": attrs["uom"],
                "unit_weight_kg": round(med_w * f, 4),
                "unit_value_usd": round(med_v * f, 4),
                "hts_code": hts_by_cat[cat],
                "hazardous_material_flag": int(attrs["hazmat"]),
                "temperature_controlled_flag": int(attrs["temp_controlled"]),
                "stackable_flag": int(attrs["stackable"]),
                "active_flag": 1, "data_class": SIMULATED,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Suppliers, warehouses, carriers, business partners
# ---------------------------------------------------------------------------
def build_suppliers(stg: pd.DataFrame, loc_lookup: dict) -> pd.DataFrame:
    rows = []
    vendors = sorted(stg["vendor_name"].dropna().unique())
    for i, v in enumerate(vendors, 1):
        g = stg[stg["vendor_name"] == v]
        # Primary manufacturing site & category by frequency (deterministic).
        site = g["manufacturing_site"].dropna().mode()
        loc_id = loc_lookup.get(("MFG", site.iloc[0])) if len(site) else None
        cat = g["product_category"].mode()
        country = None
        if loc_id:
            country, _ = detect_site_country(site.iloc[0])
        rows.append({
            "supplier_id": f"SUP{i:03d}", "supplier_name": v,
            "supplier_location_id": loc_id,
            "primary_product_category": cat.iloc[0] if len(cat) else None,
            "country": country, "active_flag": 1, "data_class": DERIVED,
        })
    return pd.DataFrame(rows)


def build_warehouses(cfg: dict) -> pd.DataFrame:
    rows = []
    for wh in cfg["phase2"]["warehouses"]:
        rows.append({
            "warehouse_id": wh["warehouse_id"], "warehouse_name": wh["warehouse_name"],
            "location_id": f"LOC{wh['warehouse_id']}", "warehouse_type": wh["warehouse_type"],
            "capacity_weight_kg": wh["capacity_weight_kg"], "capacity_pallets": wh["capacity_pallets"],
            "active_flag": 1, "data_class": SIMULATED,
        })
    return pd.DataFrame(rows)


def build_carriers(cfg: dict) -> pd.DataFrame:
    rows = []
    for c in cfg["phase2"]["carriers"]:
        rows.append({**c, "active_flag": 1,
                     "effective_start_date": "2015-01-01", "effective_end_date": "2099-12-31",
                     "data_class": SIMULATED})
    return pd.DataFrame(rows)


def build_business_partners(suppliers: pd.DataFrame, carriers: pd.DataFrame,
                            stg: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, s in suppliers.iterrows():
        rows.append({"partner_id": f"BP-{s['supplier_id']}", "partner_name": s["supplier_name"],
                     "partner_type": "SUPPLIER", "country": s["country"],
                     "region": region_of(s["country"]), "active_flag": 1, "data_class": DERIVED})
    for _, c in carriers.iterrows():
        ptype = "BROKER" if c["carrier_type"] == "BROKER" else "CARRIER"
        rows.append({"partner_id": f"BP-{c['carrier_id']}", "partner_name": c["carrier_name"],
                     "partner_type": ptype, "country": None,
                     "region": c["operating_region"], "active_flag": 1, "data_class": SIMULATED})
    for i, ctry in enumerate(sorted(stg["destination_country"].dropna().unique()), 1):
        rows.append({"partner_id": f"BP-CUST{i:03d}", "partner_name": f"{ctry} Project Customer",
                     "partner_type": "CUSTOMER", "country": ctry, "region": region_of(ctry),
                     "active_flag": 1, "data_class": SIMULATED})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Per-shipment resolution (mode imputation, origin/dest/warehouse, lane)
# ---------------------------------------------------------------------------
def resolve_shipments(stg: pd.DataFrame, cfg: dict, loc_lookup: dict) -> pd.DataFrame:
    p2 = cfg["phase2"]
    impute = p2["impute_mode_weights"]
    modes, weights = list(impute.keys()), np.array(list(impute.values()), float)
    weights = weights / weights.sum()

    def resolve_mode(row):
        if pd.notna(row["shipment_mode"]):
            return row["shipment_mode"], 0
        rng = record_rng("impute_mode", row["source_record_id"])
        return str(rng.choice(modes, p=weights)), 1

    out = []
    for _, r in stg.iterrows():
        mode, mode_imp = resolve_mode(r)
        origin_loc = loc_lookup.get(("MFG", r["manufacturing_site"])) if pd.notna(r["manufacturing_site"]) else None
        dest_loc = loc_lookup.get(("DST", r["destination_country"])) if pd.notna(r["destination_country"]) else None
        # From RDC shipments route through a regional DC; Direct Drop do not.
        wh = warehouse_for(r["destination_country"]) if r["fulfill_via"] == "From RDC" else None
        out.append({
            "source_record_id": r["source_record_id"],
            "origin_location_id": origin_loc, "destination_location_id": dest_loc,
            "resolved_mode": mode, "mode_imputed_flag": mode_imp, "warehouse_id": wh,
        })
    res = pd.DataFrame(out)
    return res


def build_lanes(res: pd.DataFrame, loc_df: pd.DataFrame, cfg: dict):
    p2 = cfg["phase2"]
    std = p2["transit_standard_days"]
    name_by_loc = dict(zip(loc_df["location_id"], loc_df["location_name"]))
    region_by_loc = dict(zip(loc_df["location_id"], loc_df["region"]))

    combos = (res.dropna(subset=["origin_location_id", "destination_location_id"])
              .groupby(["origin_location_id", "destination_location_id", "resolved_mode"])
              .size().reset_index(name="n"))
    combos = combos.sort_values(["origin_location_id", "destination_location_id", "resolved_mode"]).reset_index(drop=True)
    lane_rows, lane_key = [], {}
    for i, row in combos.iterrows():
        lane_id = f"LANE{i + 1:05d}"
        key = (row["origin_location_id"], row["destination_location_id"], row["resolved_mode"])
        lane_key[key] = lane_id
        lane_rows.append({
            "lane_id": lane_id,
            "origin_location_id": row["origin_location_id"],
            "destination_location_id": row["destination_location_id"],
            "origin_name": name_by_loc.get(row["origin_location_id"]),
            "destination_name": name_by_loc.get(row["destination_location_id"]),
            "transport_mode": row["resolved_mode"],
            "lane_region": region_by_loc.get(row["destination_location_id"]),
            "standard_transit_days": int(std.get(row["resolved_mode"], 10)),
            "estimated_distance": None, "distance_unit": None,
            "transit_derivation_method": "MODE_REGION_STANDARD",
            "active_flag": 1, "data_class": DERIVED,
        })
    lanes = pd.DataFrame(lane_rows)

    # attach lane_id back to the resolution frame
    def lane_of(r):
        return lane_key.get((r["origin_location_id"], r["destination_location_id"], r["resolved_mode"]))
    res = res.copy()
    res["lane_id"] = res.apply(lane_of, axis=1)
    return lanes, res


def build_rate_cards(lanes: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    p2 = cfg["phase2"]
    rc = p2["rate_card"]
    pool = p2["carrier_mode_pool"]
    rows = []
    n = 0
    for _, lane in lanes.iterrows():
        mode = lane["transport_mode"]
        base_kg = rc["per_kg_base"].get(mode, 2.5)
        for carrier_id in pool.get(mode, []):
            rng = record_rng("rate_spread", f"{carrier_id}:{mode}")
            spread = 1 + rng.uniform(-rc["carrier_rate_spread"], rc["carrier_rate_spread"])
            n += 1
            rows.append({
                "rate_id": f"RC{n:06d}", "carrier_id": carrier_id, "lane_id": lane["lane_id"],
                "transport_mode": mode,
                "effective_start_date": rc["effective_start"], "effective_end_date": rc["effective_end"],
                "rate_basis": rc["rate_basis_by_mode"].get(mode, "PER_KG"),
                "base_rate": round(base_kg * spread, 4),
                "rate_per_kg": round(base_kg * spread, 4),
                "rate_per_shipment": None,
                "minimum_charge": rc["min_charge"].get(mode, 200),
                "fuel_percentage": rc["fuel_pct"].get(mode, 0.15),
                "currency": "USD",
                "detention_allowed_flag": 1, "demurrage_allowed_flag": 1, "storage_allowed_flag": 1,
                "data_class": SIMULATED,
            })
    return pd.DataFrame(rows)


def main() -> int:
    cfg = load_config()
    ensure_dirs()
    CLEAN.mkdir(parents=True, exist_ok=True)
    stg = _load_stg()
    log.info("Loaded stg_shipment: %d rows", len(stg))

    loc_df, xref_df, loc_lookup = build_locations(stg, cfg)
    hts = build_hts(cfg)
    products = build_products(stg, cfg, hts)
    suppliers = build_suppliers(stg, loc_lookup)
    warehouses = build_warehouses(cfg)
    carriers = build_carriers(cfg)
    partners = build_business_partners(suppliers, carriers, stg)

    res = resolve_shipments(stg, cfg, loc_lookup)
    lanes, res = build_lanes(res, loc_df, cfg)
    rate_cards = build_rate_cards(lanes, cfg)

    # Persist
    outputs = {
        "dim_location": loc_df, "dim_location_xref": xref_df, "dim_hts_code": hts,
        "dim_product": products, "dim_supplier": suppliers, "dim_warehouse": warehouses,
        "dim_carrier": carriers, "dim_business_partner": partners,
        "dim_lane": lanes, "dim_rate_card": rate_cards,
    }
    for name, df in outputs.items():
        df.to_csv(CLEAN / f"{name}.csv", index=False)
    res.to_csv(DATA_INTERIM / "shipment_resolved.csv", index=False)

    log.info("locations=%d (mfg+dst+wh) | products=%d | suppliers=%d | carriers=%d | partners=%d",
             len(loc_df), len(products), len(suppliers), len(carriers), len(partners))
    log.info("lanes=%d | rate_cards=%d | resolved shipments=%d (mode-imputed=%d)",
             len(lanes), len(rate_cards), len(res), int(res["mode_imputed_flag"].sum()))
    # sanity: every resolvable shipment got a lane
    missing_lane = res["lane_id"].isna().sum()
    log.info("shipments without lane (missing origin/dest): %d", missing_lane)
    return 0


if __name__ == "__main__":
    sys.exit(main())
