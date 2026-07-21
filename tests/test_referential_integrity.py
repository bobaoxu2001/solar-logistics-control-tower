"""Phase 2 — referential integrity and date/sequence logic on the clean baseline.

The CLEAN baseline must be perfectly consistent. The OPERATIONAL layer
deliberately violates some of these (that is the injected exceptions), so these
checks run against the clean baseline.
"""

import pandas as pd
from phase2_fixtures import clean


def _fk_ok(child, col, parent_ids):
    present = child[col].dropna()
    return present.isin(parent_ids).all()


def test_all_foreign_keys_resolve_in_clean_baseline():
    ship = clean("fact_shipment")
    inv = clean("fact_freight_invoice")
    assert _fk_ok(ship, "carrier_id", set(clean("dim_carrier")["carrier_id"]))
    assert _fk_ok(ship, "lane_id", set(clean("dim_lane")["lane_id"]))
    assert _fk_ok(ship, "product_id", set(clean("dim_product")["product_id"]))
    assert _fk_ok(ship, "po_id", set(clean("fact_purchase_order")["po_id"]))
    locs = set(clean("dim_location")["location_id"])
    assert _fk_ok(ship, "origin_location_id", locs)
    assert _fk_ok(ship, "destination_location_id", locs)
    assert _fk_ok(inv, "shipment_id", set(ship["shipment_id"]))
    assert _fk_ok(clean("fact_invoice_line"), "invoice_id", set(inv["invoice_id"]))
    assert _fk_ok(clean("fact_accrual"), "shipment_id", set(ship["shipment_id"]))
    assert _fk_ok(clean("fact_shipment_milestone"), "shipment_id", set(ship["shipment_id"]))


def test_shipment_date_ordering():
    s = clean("fact_shipment")
    for c in ["booking_date", "planned_ship_date", "actual_ship_date",
              "planned_delivery_date", "actual_delivery_date"]:
        s[c] = pd.to_datetime(s[c])
    assert (s["booking_date"] <= s["actual_ship_date"]).all()
    deliv = s[s["shipment_status"] == "DELIVERED"]
    assert (deliv["actual_ship_date"] <= deliv["actual_delivery_date"]).all()
    assert (s["planned_ship_date"] <= s["planned_delivery_date"]).all()


def test_in_transit_have_no_delivery_or_invoice():
    s = clean("fact_shipment")
    intr = s[s["shipment_status"] == "IN_TRANSIT"]
    assert intr["actual_delivery_date"].isna().all()
    invoiced = set(clean("fact_freight_invoice")["shipment_id"])
    assert not set(intr["shipment_id"]) & invoiced


def test_milestone_sequences_monotonic():
    ms = clean("fact_shipment_milestone").copy()
    ms["actual_timestamp"] = pd.to_datetime(ms["actual_timestamp"])
    comp = ms[ms["milestone_status"] == "COMPLETED"].sort_values(["shipment_id", "milestone_sequence"])
    bad = comp.groupby("shipment_id")["actual_timestamp"].apply(
        lambda x: (x.diff().dt.total_seconds() < 0).any())
    assert not bad.any()


def test_pod_after_delivery():
    pod = clean("fact_proof_of_delivery").copy()
    pod["delivery_timestamp"] = pd.to_datetime(pod["delivery_timestamp"])
    pod["received_timestamp"] = pd.to_datetime(pod["received_timestamp"])
    assert (pod["received_timestamp"] >= pod["delivery_timestamp"]).all()


def test_delivered_quantity_not_exceed_shipped():
    s = clean("fact_shipment")
    dd = s[s["delivered_quantity"].notna()]
    assert (dd["delivered_quantity"] <= dd["shipped_quantity"]).all()


def test_shipped_qty_within_po_qty():
    ship = clean("fact_shipment")
    po = clean("fact_purchase_order")[["po_id", "ordered_quantity"]]
    agg = ship.groupby("po_id")["shipped_quantity"].sum().reset_index().merge(po, on="po_id")
    assert (agg["shipped_quantity"] <= agg["ordered_quantity"]).all()


def test_approval_after_submission():
    ap = clean("fact_invoice_approval").copy()
    ap["submitted_timestamp"] = pd.to_datetime(ap["submitted_timestamp"])
    ap["approved_timestamp"] = pd.to_datetime(ap["approved_timestamp"])
    done = ap[ap["approved_timestamp"].notna()]
    assert (done["approved_timestamp"] >= done["submitted_timestamp"]).all()


def test_paid_invoices_are_approved():
    inv = clean("fact_freight_invoice")
    paid = inv[inv["payment_status"] == "PAID"]
    assert (paid["approval_status"] == "APPROVED").all()


def test_baseline_validation_report_zero_critical():
    val = clean("rpt_phase2_baseline_validation")
    crit = val[(val["severity"] == "CRITICAL") & (val["status"] == "FAIL")]
    assert len(crit) == 0, f"critical baseline failures: {crit['validation_name'].tolist()}"
