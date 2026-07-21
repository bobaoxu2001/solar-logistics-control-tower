"""Phase 1 tests: cleaning logic (unit) + staged output integrity (integration).

Integration tests run against data/processed/stg_shipment.csv and are skipped
with a clear message if the pipeline has not been run yet.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from clean_shipments import map_product_category, parse_date, resolve_references  # noqa: E402

STG_PATH = PROJECT_ROOT / "data" / "processed" / "stg_shipment.csv"
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "scms_delivery_history_raw.csv"


# --------------------------------------------------------------------------
# Unit tests on small synthetic frames
# --------------------------------------------------------------------------
def test_parse_date_handles_sentinels():
    s = pd.Series(["2-Jun-06", "Date Not Captured", "Pre-PQ Process", None])
    out = parse_date(s, ["Date Not Captured", "Pre-PQ Process"], "%d-%b-%y")
    assert out.iloc[0] == pd.Timestamp("2006-06-02")
    assert out.iloc[1:].isna().all()


def test_resolve_references_one_hop():
    df = pd.DataFrame({
        "ID": ["1", "2", "3", "4"],
        "w": ["100.5", "See DN-9 (ID#:1)", "Weight Captured Separately", "See ASN-7 (ID#:3)"],
    })
    value, source = resolve_references(
        df, "w", {"Weight Captured Separately": "missing_captured_separately"}, r"ID#:\s*(\d+)"
    )
    assert value.iloc[0] == 100.5
    assert value.iloc[1] == 100.5 and source.iloc[1] == "resolved_reference"
    assert pd.isna(value.iloc[2]) and source.iloc[2] == "missing_captured_separately"
    # row 4 references row 3, which is itself a sentinel → unresolved
    assert pd.isna(value.iloc[3]) and source.iloc[3] == "missing_unresolved_reference"


def test_product_category_wildcard_mapping():
    df = pd.DataFrame({
        "Product Group": ["ARV", "ARV", "ANTM"],
        "Sub Classification": ["Adult", "Pediatric", "Malaria"],
    })
    cmap = {"ARV|Adult": "SOLAR_MODULE", "ARV|Pediatric": "INVERTER", "ANTM|*": "BOS_COMPONENT"}
    out = map_product_category(df, cmap)
    assert list(out) == ["SOLAR_MODULE", "INVERTER", "BOS_COMPONENT"]


# --------------------------------------------------------------------------
# Integration tests on the staged output
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def stg() -> pd.DataFrame:
    if not STG_PATH.exists():
        pytest.skip("stg_shipment.csv not built — run src/clean_shipments.py first")
    return pd.read_csv(STG_PATH, parse_dates=[
        "scheduled_delivery_date", "actual_delivery_date",
        "reporting_scheduled_delivery_date", "reporting_actual_delivery_date",
    ])


def test_lineage_key_unique_and_complete(stg):
    assert stg["source_record_id"].is_unique
    assert stg["source_record_id"].notna().all()


def test_row_count_reconciles_to_raw(stg):
    if not RAW_PATH.exists():
        pytest.skip("raw file not present")
    raw_rows = sum(1 for _ in open(RAW_PATH, encoding="utf-8-sig")) and \
        len(pd.read_csv(RAW_PATH, encoding="utf-8-sig", dtype=str))
    rej_path = PROJECT_ROOT / "data" / "processed" / "rejected_records.csv"
    rejected = len(pd.read_csv(rej_path)) if rej_path.exists() and rej_path.stat().st_size > 60 else 0
    assert len(stg) + rejected == raw_rows


def test_mandatory_dates_present(stg):
    assert stg["scheduled_delivery_date"].notna().all()
    assert stg["actual_delivery_date"].notna().all()


def test_quantities_positive(stg):
    assert (stg["line_item_quantity"] > 0).all()


def test_weight_and_freight_provenance_flags(stg):
    allowed_w = {"direct", "resolved_reference", "missing_captured_separately",
                 "missing_unresolved_reference"}
    allowed_f = {"direct", "resolved_reference", "missing_included_in_commodity",
                 "missing_invoiced_separately", "missing_unresolved_reference"}
    assert set(stg["weight_source"].unique()) <= allowed_w
    assert set(stg["freight_cost_source"].unique()) <= allowed_f
    # provenance flag and value must agree
    has_w = stg["weight_kg"].notna()
    assert (stg.loc[has_w, "weight_source"].isin(["direct", "resolved_reference"])).all()
    assert stg.loc[~has_w, "weight_source"].str.startswith("missing").all()


def test_shipment_mode_normalized(stg):
    assert set(stg["shipment_mode"].dropna().unique()) <= {"AIR", "AIR_CHARTER", "TRUCK", "OCEAN"}
    assert (stg["missing_mode_flag"] == stg["shipment_mode"].isna().astype(int)).all()


def test_product_category_fully_mapped(stg):
    assert stg["product_category"].notna().all()
    assert set(stg["product_category"].unique()) <= {
        "SOLAR_MODULE", "INVERTER", "BATTERY_ESS", "BOS_COMPONENT"
    }


def test_reporting_dates_shifted_constant_years(stg):
    delta_years = (
        stg["reporting_scheduled_delivery_date"].dt.year - stg["scheduled_delivery_date"].dt.year
    )
    assert (delta_years == 10).all()
    # month/day preserved
    assert (stg["reporting_scheduled_delivery_date"].dt.month
            == stg["scheduled_delivery_date"].dt.month).all()
