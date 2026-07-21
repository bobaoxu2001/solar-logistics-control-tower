"""Phase 2 — financial reconciliation on the clean baseline.

Verifies the freight-rating engine and invoice/accrual arithmetic that Phase 3's
freight audit relies on.
"""

import sys

import pandas as pd
from phase2_fixtures import PROJECT_ROOT, clean

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from common import load_config  # noqa: E402


def _rate_index():
    rc = clean("dim_rate_card")
    return {(r.carrier_id, r.lane_id): r for r in rc.itertuples(index=False)}


def test_invoice_total_equals_components():
    inv = clean("fact_freight_invoice")
    comp = inv["base_charge"] + inv["fuel_surcharge"] + inv["accessorial_charge"] + inv["tax_amount"]
    assert (abs(comp - inv["invoice_total"]) <= 0.01).all()


def test_invoice_lines_sum_to_total():
    inv = clean("fact_freight_invoice").set_index("invoice_id")["invoice_total"]
    lines = clean("fact_invoice_line").groupby("invoice_id")["amount"].sum()
    j = inv.to_frame("total").join(lines.to_frame("lines"))
    assert (abs(j["total"] - j["lines"].fillna(0)) <= 0.01).all()


def test_fuel_surcharge_matches_contractual_pct():
    inv = clean("fact_freight_invoice")
    ship = clean("fact_shipment")[["shipment_id", "carrier_id", "lane_id"]]
    idx = _rate_index()
    m = inv.merge(ship, on="shipment_id", suffixes=("_inv", "_ship"))
    def ok(r):
        rate = idx.get((r["carrier_id_ship"], r["lane_id"]))
        if rate is None:
            return False
        return abs(r["fuel_surcharge"] - r["base_charge"] * float(rate.fuel_percentage)) <= 0.02
    assert m.apply(ok, axis=1).all()


def test_base_charge_within_rate_tolerance():
    """Clean base+fuel is within the configured audit tolerance of the
    contractual rate (i.e., the baseline itself is audit-clean)."""
    thr = load_config("exception_config.yaml")["audit_thresholds"]
    abs_t, pct_t = float(thr["absolute_variance_usd"]), float(thr["variance_pct"]) / 100
    inv = clean("fact_freight_invoice")
    ship = clean("fact_shipment")[["shipment_id", "carrier_id", "lane_id", "shipment_weight_kg"]]
    idx = _rate_index()
    m = inv.merge(ship, on="shipment_id", suffixes=("_inv", "_ship"))
    def within(r):
        rate = idx.get((r["carrier_id_ship"], r["lane_id"]))
        if rate is None:
            return False
        exp_base = max(float(rate.rate_per_kg) * float(r["shipment_weight_kg"]), float(rate.minimum_charge))
        exp = exp_base * (1 + float(rate.fuel_percentage))
        got = r["base_charge"] + r["fuel_surcharge"]
        return abs(got - exp) <= max(abs_t, pct_t * exp)
    assert m.apply(within, axis=1).all()


def test_accessorial_totals_reconcile_to_invoice():
    inv = clean("fact_freight_invoice").set_index("invoice_id")["accessorial_charge"]
    acc = clean("fact_accessorial_charge").groupby("invoice_id")["charge_amount"].sum()
    j = inv.to_frame("inv_acc").join(acc.to_frame("sum_acc"))
    assert (abs(j["inv_acc"] - j["sum_acc"].fillna(0)) <= 0.01).all()


def test_accrual_variance_reconciles_when_invoice_received():
    acc = clean("fact_accrual")
    got = acc[acc["invoice_received_flag"] == 1].copy()
    recomputed = (got["actual_invoice_cost"] - got["expected_freight_cost"]).round(2)
    assert (abs(recomputed - got["accrual_variance"]) <= 0.01).all()


def test_released_accruals_have_received_invoice():
    acc = clean("fact_accrual")
    released = acc[acc["accrual_status"] == "RELEASED"]
    assert (released["invoice_received_flag"] == 1).all()
    assert released["actual_invoice_cost"].notna().all()


def test_rate_reconciliation_close_to_observed():
    """Generated expected freight tracks the real source freight distribution."""
    recon = clean("rpt_rate_reconciliation")
    allrow = recon[recon["reconciliation_scope"] == "ALL"].iloc[0]
    assert 0.7 <= allrow["expected_to_observed_ratio"] <= 1.4
