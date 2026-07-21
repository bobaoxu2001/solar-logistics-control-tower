"""Phase 2 — controlled exception injection.

Verifies that configured exceptions are injected, the manifest matches the
records actually changed, the clean baseline is untouched, disabled types are
not injected, and counts are deterministic.
"""

import sys

import pandas as pd
from phase2_fixtures import PROJECT_ROOT, clean, oper, processed

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from common import load_config  # noqa: E402


def test_all_configured_types_injected():
    cfg_types = set(load_config("exception_config.yaml")["exceptions"].keys())
    manifest_types = set(processed("exception_manifest")["exception_type"].unique())
    assert cfg_types == manifest_types


def test_disabled_type_not_injected():
    """late_delivery is deliberately excluded from config (lateness is real),
    so it must not appear in the manifest."""
    manifest_types = set(processed("exception_manifest")["exception_type"].unique())
    assert "late_delivery" not in manifest_types


def test_counts_match_configuration_within_tolerance():
    s = processed("exception_summary")
    assert (abs(s["expected_count"] - s["actual_count"]) <= 2).all()


# --- Manifest exactly matches the records actually changed ------------------
def test_manifest_missing_carrier_matches_operational():
    n_manifest = (processed("exception_manifest")["exception_type"] == "missing_carrier_id").sum()
    n_oper = oper("fact_shipment")["carrier_id"].isna().sum()
    assert n_manifest == n_oper == 100


def test_manifest_invalid_lane_matches_operational():
    n_manifest = (processed("exception_manifest")["exception_type"] == "invalid_lane").sum()
    n_oper = (oper("fact_shipment")["lane_id"] == "LANE_INVALID").sum()
    assert n_manifest == n_oper


def test_manifest_currency_matches_operational():
    n_manifest = (processed("exception_manifest")["exception_type"] == "incorrect_currency").sum()
    n_oper = (oper("fact_freight_invoice")["currency"] != "USD").sum()
    assert n_manifest == n_oper


def test_manifest_missing_hts_matches_operational():
    n_manifest = (processed("exception_manifest")["exception_type"] == "missing_hts_code").sum()
    n_oper = oper("dim_product")["hts_code"].isna().sum()
    assert n_manifest == n_oper


def test_manifest_orphan_invoices_match_operational():
    inv = oper("fact_freight_invoice")
    ship_ids = set(oper("fact_shipment")["shipment_id"])
    orphans = (~inv["shipment_id"].isin(ship_ids)).sum()
    n_manifest = (processed("exception_manifest")["exception_type"] == "invoice_without_shipment").sum()
    assert orphans == n_manifest == 60


def test_manifest_preserves_clean_and_injected_values():
    m = processed("exception_manifest")
    cm = m[m["exception_type"] == "missing_carrier_id"]
    # clean carrier recorded, injected is null
    assert cm["clean_value"].notna().all()
    assert cm["injected_value"].isna().all()


# --- Clean baseline is untouched -------------------------------------------
def test_clean_baseline_has_no_injected_defects():
    ship = clean("fact_shipment")
    assert ship["carrier_id"].notna().all()          # no missing carrier
    assert (ship["lane_id"] != "LANE_INVALID").all()  # no invalid lane
    inv = clean("fact_freight_invoice")
    assert (inv["currency"] == "USD").all()            # no wrong currency
    assert clean("dim_product")["hts_code"].notna().all()
    # every delivered shipment still has exactly one invoice in the clean layer
    delivered = set(ship.loc[ship["shipment_status"] == "DELIVERED", "shipment_id"])
    assert delivered <= set(inv["shipment_id"])


def test_clean_invoice_numbers_unique_operational_has_duplicates():
    assert clean("fact_freight_invoice")["invoice_number"].is_unique
    # operational deliberately contains duplicate invoice_numbers
    onum = oper("fact_freight_invoice")["invoice_number"]
    assert onum.duplicated().sum() >= 100


# --- No unintended overlap among mutually-exclusive edits -------------------
def test_over_and_partial_delivery_disjoint():
    m = processed("exception_manifest")
    over = set(m[m["exception_type"] == "over_delivery"]["record_id"])
    partial = set(m[m["exception_type"] == "partial_delivery"]["record_id"])
    assert not (over & partial)


def test_shipment_level_exceptions_disjoint():
    """No delivered shipment receives two different shipment-level exceptions."""
    m = processed("exception_manifest")
    ship_types = ["missing_carrier_id", "invalid_lane", "delivery_before_ship",
                  "over_delivery", "partial_delivery"]
    sub = m[m["exception_type"].isin(ship_types)]
    assert sub["record_id"].is_unique


# --- Row reconciliation: operational deltas are explained ------------------
def test_operational_invoice_delta_reconciles():
    c = len(clean("fact_freight_invoice"))
    o = len(oper("fact_freight_invoice"))
    # -300 shipment_without_invoice +120 duplicate +50 dup_payment +60 orphan
    assert o - c == -300 + 120 + 50 + 60
