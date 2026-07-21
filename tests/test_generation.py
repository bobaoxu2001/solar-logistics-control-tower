"""Phase 2 — generation reproducibility and row reconciliation."""

import hashlib

import pandas as pd
import pytest
from phase2_fixtures import PROJECT_ROOT, clean, oper, processed


def _hash(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


# --- Reproducibility -------------------------------------------------------
def test_regeneration_is_byte_identical():
    """Same seed -> identical generated master + enterprise outputs."""
    import generate_master_data
    import generate_enterprise_data
    target = PROJECT_ROOT / "data" / "processed" / "clean" / "fact_shipment.csv"
    if not target.exists():
        pytest.skip("run src/run_phase2.py first")
    before = _hash(target)
    generate_master_data.main()
    generate_enterprise_data.main()
    assert _hash(target) == before, "regeneration changed fact_shipment — non-deterministic!"


def test_manifest_deterministic_excluding_timestamp():
    """The injection manifest is deterministic apart from its wall-clock stamp."""
    import inject_exceptions
    m1 = processed("exception_manifest").drop(columns=["injection_timestamp"])
    inject_exceptions.main()
    m2 = processed("exception_manifest").drop(columns=["injection_timestamp"])
    h1 = pd.util.hash_pandas_object(m1, index=False).sum()
    h2 = pd.util.hash_pandas_object(m2, index=False).sum()
    assert h1 == h2


def test_no_duplicate_primary_keys_after_rerun():
    """Idempotent: re-running never duplicates rows (PKs stay unique)."""
    for name, pk in [("fact_shipment", "shipment_id"), ("dim_lane", "lane_id"),
                     ("fact_purchase_order", "po_id"), ("dim_rate_card", "rate_id")]:
        df = clean(name)
        assert df[pk].is_unique, f"{name}.{pk} not unique"


# --- Row reconciliation ----------------------------------------------------
def test_shipment_count_matches_phase1():
    stg = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "stg_shipment.csv")
    assert len(clean("fact_shipment")) == len(stg) == 10324


def test_every_shipment_retains_source_lineage():
    stg = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "stg_shipment.csv")
    ship = clean("fact_shipment")
    assert ship["source_record_id"].isin(set(stg["source_record_id"])).all()
    assert ship["source_record_id"].is_unique
    assert set(ship["source_record_id"]) == set(stg["source_record_id"])


def test_public_fields_preserved_from_source():
    """Real (public) shipment fields are copied through unchanged, independent
    of the simulation seed."""
    stg = pd.read_csv(PROJECT_ROOT / "data" / "processed" / "stg_shipment.csv")
    ship = clean("fact_shipment").merge(
        stg[["source_record_id", "line_item_value_usd", "line_item_quantity"]],
        on="source_record_id")
    assert (ship["shipment_value_usd"] == ship["line_item_value_usd"]).all()
    assert (ship["planned_quantity"] == ship["line_item_quantity"]).all()


def test_master_data_expected_shapes():
    assert len(clean("dim_carrier")) == 12
    assert set(clean("dim_product")["product_category"].unique()) == {
        "SOLAR_MODULE", "INVERTER", "BATTERY_ESS", "BOS_COMPONENT"}
    assert len(clean("dim_warehouse")) == 5
    # every lane maps to real origin+destination locations
    lanes = clean("dim_lane")
    locs = set(clean("dim_location")["location_id"])
    assert lanes["origin_location_id"].isin(locs).all()
    assert lanes["destination_location_id"].isin(locs).all()


def test_data_class_provenance_present():
    for name in ["dim_carrier", "dim_lane", "fact_shipment", "fact_freight_invoice"]:
        assert "data_class" in clean(name).columns
        assert clean(name)["data_class"].isin({"PUBLIC", "DERIVED", "SIMULATED"}).all()


def test_battery_products_flagged_hazardous():
    prod = clean("dim_product")
    bess = prod[prod["product_category"] == "BATTERY_ESS"]
    assert (bess["hazardous_material_flag"] == 1).all()
    non = prod[prod["product_category"] != "BATTERY_ESS"]
    assert (non["hazardous_material_flag"] == 0).all()
