"""Phase 2 — clean-baseline validation.

Proves the generated clean enterprise dataset (data/processed/clean/*.csv) is
internally consistent BEFORE any exception injection. Writes a validation
report (rpt_phase2_baseline_validation.csv) and exits non-zero if any CRITICAL
check fails, so the orchestrator can stop before injecting exceptions.

Usage:
    python src/validate_phase2.py
"""

from __future__ import annotations

import sys

import pandas as pd

from common import DATA_PROCESSED, get_logger, load_config
from gen_common import load_table

log = get_logger("validate_phase2")
CLEAN = DATA_PROCESSED / "clean"

# table -> primary key column
PRIMARY_KEYS = {
    "dim_location": "location_id", "dim_product": "product_id", "dim_carrier": "carrier_id",
    "dim_lane": "lane_id", "dim_supplier": "supplier_id", "dim_warehouse": "warehouse_id",
    "dim_rate_card": "rate_id", "dim_hts_code": "hts_code", "dim_business_partner": "partner_id",
    "fact_purchase_order": "po_id", "fact_shipment": "shipment_id",
    "fact_shipment_milestone": "milestone_id", "fact_freight_invoice": "invoice_id",
    "fact_invoice_line": "invoice_line_id", "fact_accessorial_charge": "accessorial_id",
    "fact_proof_of_delivery": "pod_id", "fact_claim": "claim_id",
    "fact_carrier_capacity": "capacity_id", "fact_invoice_approval": "approval_id",
    "fact_accrual": "accrual_id",
}


class Report:
    def __init__(self):
        self.rows = []

    def check(self, name, tested, failures, severity):
        status = "PASS" if failures == 0 else "FAIL"
        pass_rate = round(1 - failures / tested, 4) if tested else 1.0
        self.rows.append({"validation_name": name, "records_tested": int(tested),
                          "failures": int(failures), "pass_rate": pass_rate,
                          "severity": severity, "status": status})

    def frame(self):
        return pd.DataFrame(self.rows)


def _load():
    d = {t: pd.read_csv(CLEAN / f"{t}.csv") for t in PRIMARY_KEYS}
    d["stg_shipment"] = pd.read_csv(DATA_PROCESSED / "stg_shipment.csv")
    return d


def _fk_failures(child, col, parent_keys):
    present = child[col].dropna()
    return int((~present.isin(parent_keys)).sum())


def run_checks(d: dict, cfg: dict) -> Report:
    rep = Report()
    ship = d["fact_shipment"]
    inv = d["fact_freight_invoice"]
    pool = cfg["phase2"]["carrier_mode_pool"]

    # 1. Primary keys unique
    for t, pk in PRIMARY_KEYS.items():
        df = d[t]
        rep.check(f"pk_unique[{t}]", len(df), len(df) - df[pk].nunique(), "CRITICAL")

    # 2. Required fields populated
    rep.check("required_shipment_carrier", len(ship), ship["carrier_id"].isna().sum(), "CRITICAL")
    rep.check("required_shipment_lane", len(ship), ship["lane_id"].isna().sum(), "CRITICAL")
    rep.check("required_shipment_product", len(ship), ship["product_id"].isna().sum(), "HIGH")
    rep.check("required_invoice_number", len(inv), inv["invoice_number"].isna().sum(), "CRITICAL")

    # 3. Foreign keys valid
    loc_keys = set(d["dim_location"]["location_id"])
    rep.check("fk_shipment_carrier", len(ship),
              _fk_failures(ship, "carrier_id", set(d["dim_carrier"]["carrier_id"])), "CRITICAL")
    rep.check("fk_shipment_lane", len(ship),
              _fk_failures(ship, "lane_id", set(d["dim_lane"]["lane_id"])), "CRITICAL")
    rep.check("fk_shipment_product", len(ship),
              _fk_failures(ship, "product_id", set(d["dim_product"]["product_id"])), "CRITICAL")
    rep.check("fk_shipment_po", len(ship),
              _fk_failures(ship, "po_id", set(d["fact_purchase_order"]["po_id"])), "CRITICAL")
    rep.check("fk_shipment_origin", len(ship), _fk_failures(ship, "origin_location_id", loc_keys), "HIGH")
    rep.check("fk_shipment_destination", len(ship), _fk_failures(ship, "destination_location_id", loc_keys), "HIGH")
    ship_keys = set(ship["shipment_id"])
    inv_keys = set(inv["invoice_id"])
    rep.check("fk_invoice_shipment", len(inv), _fk_failures(inv, "shipment_id", ship_keys), "CRITICAL")
    rep.check("fk_invoice_line_invoice", len(d["fact_invoice_line"]),
              _fk_failures(d["fact_invoice_line"], "invoice_id", inv_keys), "CRITICAL")
    rep.check("fk_accessorial_invoice", len(d["fact_accessorial_charge"]),
              _fk_failures(d["fact_accessorial_charge"], "invoice_id", inv_keys), "HIGH")
    rep.check("fk_pod_shipment", len(d["fact_proof_of_delivery"]),
              _fk_failures(d["fact_proof_of_delivery"], "shipment_id", ship_keys), "CRITICAL")
    rep.check("fk_claim_shipment", len(d["fact_claim"]),
              _fk_failures(d["fact_claim"], "shipment_id", ship_keys), "HIGH")
    rep.check("fk_accrual_shipment", len(d["fact_accrual"]),
              _fk_failures(d["fact_accrual"], "shipment_id", ship_keys), "HIGH")
    rep.check("fk_milestone_shipment", len(d["fact_shipment_milestone"]),
              _fk_failures(d["fact_shipment_milestone"], "shipment_id", ship_keys), "CRITICAL")
    rep.check("fk_approval_invoice", len(d["fact_invoice_approval"]),
              _fk_failures(d["fact_invoice_approval"], "invoice_id", inv_keys), "HIGH")

    # 4. Shipment date ordering
    s = ship.copy()
    for c in ["booking_date", "planned_ship_date", "actual_ship_date", "planned_delivery_date", "actual_delivery_date"]:
        s[c] = pd.to_datetime(s[c])
    rep.check("date_booking_le_ship", len(s), (s["booking_date"] > s["actual_ship_date"]).sum(), "HIGH")
    deliv = s[s["shipment_status"] == "DELIVERED"]
    rep.check("date_ship_le_delivery", len(deliv), (deliv["actual_ship_date"] > deliv["actual_delivery_date"]).sum(), "CRITICAL")
    rep.check("date_planned_ship_le_planned_delivery", len(s),
              (s["planned_ship_date"] > s["planned_delivery_date"]).sum(), "HIGH")

    # 5. Milestone ordering (sequence monotonic in actual timestamp, completed only)
    ms = d["fact_shipment_milestone"].copy()
    ms["actual_timestamp"] = pd.to_datetime(ms["actual_timestamp"])
    comp = ms[ms["milestone_status"] == "COMPLETED"].sort_values(["shipment_id", "milestone_sequence"])
    bad_seq = comp.groupby("shipment_id")["actual_timestamp"].apply(
        lambda x: (x.diff().dt.total_seconds() < 0).sum()).sum()
    rep.check("milestone_timestamp_monotonic", len(comp), int(bad_seq), "HIGH")

    # 6. Shipment quantity <= PO ordered quantity
    po = d["fact_purchase_order"][["po_id", "ordered_quantity"]]
    ship_by_po = ship.groupby("po_id")["shipped_quantity"].sum().reset_index()
    merged = ship_by_po.merge(po, on="po_id", how="left")
    rep.check("shipped_qty_le_po_qty", len(merged),
              (merged["shipped_quantity"] > merged["ordered_quantity"]).sum(), "HIGH")

    # 7. Delivered quantity <= shipped quantity
    dd = ship[ship["delivered_quantity"].notna()]
    rep.check("delivered_le_shipped", len(dd),
              (dd["delivered_quantity"] > dd["shipped_quantity"]).sum(), "MEDIUM")

    # 8. Carrier assignment valid for the lane mode
    lane_mode = dict(zip(d["dim_lane"]["lane_id"], d["dim_lane"]["transport_mode"]))
    def carrier_ok(row):
        return row["carrier_id"] in pool.get(lane_mode.get(row["lane_id"]), [])
    bad_carrier = (~ship.apply(carrier_ok, axis=1)).sum()
    rep.check("carrier_in_lane_mode_pool", len(ship), int(bad_carrier), "HIGH")

    # 9. Lane assignment valid (already covered by fk_shipment_lane); mode match
    rep.check("shipment_mode_matches_lane", len(ship),
              (ship["shipment_mode"] != ship["lane_id"].map(lane_mode)).sum(), "MEDIUM")

    # 10. Every delivered shipment has an invoice (applicable rate existed)
    delivered_ids = set(ship.loc[ship["shipment_status"] == "DELIVERED", "shipment_id"])
    invoiced_ids = set(inv["shipment_id"])
    rep.check("delivered_shipment_has_invoice", len(delivered_ids),
              len(delivered_ids - invoiced_ids), "CRITICAL")

    # 11. Rate effective dates cover shipment date
    rc = d["dim_rate_card"]
    rc_span = {(r.carrier_id, r.lane_id): (pd.Timestamp(r.effective_start_date), pd.Timestamp(r.effective_end_date))
               for r in rc.itertuples(index=False)}
    def rate_covers(row):
        span = rc_span.get((row["carrier_id"], row["lane_id"]))
        if span is None:
            return False
        return span[0] <= pd.Timestamp(row["actual_ship_date"]) <= span[1]
    rep.check("rate_covers_ship_date", len(ship), int((~ship.apply(rate_covers, axis=1)).sum()), "HIGH")

    # 12. Invoice carrier matches shipment carrier
    ic = inv.merge(ship[["shipment_id", "carrier_id"]], on="shipment_id", suffixes=("_inv", "_ship"))
    rep.check("invoice_carrier_matches_shipment", len(ic),
              (ic["carrier_id_inv"] != ic["carrier_id_ship"]).sum(), "HIGH")

    # 13. Invoice total = sum of components
    comp_sum = (inv["base_charge"] + inv["fuel_surcharge"] + inv["accessorial_charge"] + inv["tax_amount"])
    rep.check("invoice_total_reconciles", len(inv),
              (abs(comp_sum - inv["invoice_total"]) > 0.01).sum(), "CRITICAL")

    # 13b. Invoice lines sum to invoice total
    line_sum = d["fact_invoice_line"].groupby("invoice_id")["amount"].sum()
    it = inv.set_index("invoice_id")["invoice_total"]
    joined = it.to_frame("total").join(line_sum.to_frame("lines"))
    rep.check("invoice_lines_sum_to_total", len(joined),
              (abs(joined["total"] - joined["lines"].fillna(0)) > 0.01).sum(), "HIGH")

    # 14. Invoice base+fuel within audit tolerance of the contractual rate
    thr = load_config("exception_config.yaml")["audit_thresholds"]
    abs_t, pct_t = float(thr["absolute_variance_usd"]), float(thr["variance_pct"]) / 100
    rate_by = {(r.carrier_id, r.lane_id): r for r in rc.itertuples(index=False)}
    def within_tol(row):
        rc_row = rate_by.get((row["carrier_id"], row["lane_id"]))
        sw = ship.loc[ship["shipment_id"] == row["shipment_id"], "shipment_weight_kg"]
        if rc_row is None or sw.empty:
            return False
        exp_base = max(float(rc_row.rate_per_kg) * float(sw.iloc[0]), float(rc_row.minimum_charge))
        exp = exp_base * (1 + float(rc_row.fuel_percentage))
        got = row["base_charge"] + row["fuel_surcharge"]
        return abs(got - exp) <= max(abs_t, pct_t * exp)
    # sample-safe: vectorize via merge for speed
    inv_w = inv.merge(ship[["shipment_id", "shipment_weight_kg", "carrier_id", "lane_id"]],
                      on="shipment_id", suffixes=("", "_s"))
    def tol_fast(r):
        rc_row = rate_by.get((r["carrier_id_s"], r["lane_id"]))
        if rc_row is None:
            return False
        exp_base = max(float(rc_row.rate_per_kg) * float(r["shipment_weight_kg"]), float(rc_row.minimum_charge))
        exp = exp_base * (1 + float(rc_row.fuel_percentage))
        return abs((r["base_charge"] + r["fuel_surcharge"]) - exp) <= max(abs_t, pct_t * exp)
    rep.check("invoice_within_rate_tolerance", len(inv_w), int((~inv_w.apply(tol_fast, axis=1)).sum()), "HIGH")

    # 15. POD exists for completed deliveries
    pod_ids = set(d["fact_proof_of_delivery"]["shipment_id"])
    rep.check("pod_for_delivered", len(delivered_ids), len(delivered_ids - pod_ids), "HIGH")

    # 16. POD received >= delivery
    pod = d["fact_proof_of_delivery"].copy()
    pod["delivery_timestamp"] = pd.to_datetime(pod["delivery_timestamp"])
    pod["received_timestamp"] = pd.to_datetime(pod["received_timestamp"])
    rep.check("pod_after_delivery", len(pod),
              (pod["received_timestamp"] < pod["delivery_timestamp"]).sum(), "MEDIUM")

    # 17. Paid invoices are approved
    paid = inv[inv["payment_status"] == "PAID"]
    rep.check("paid_invoice_is_approved", len(paid),
              (paid["approval_status"] != "APPROVED").sum(), "CRITICAL")

    # 18. Capacity utilization <= 100%
    cap = d["fact_carrier_capacity"]
    rep.check("capacity_utilization_le_100", len(cap),
              (cap["capacity_utilization_pct"] > 100.0001).sum(), "HIGH")

    # 19. Accrual accounting logic: RELEASED => invoice received & approved
    acc = d["fact_accrual"]
    released = acc[acc["accrual_status"] == "RELEASED"]
    rep.check("accrual_released_has_invoice", len(released),
              (released["invoice_received_flag"] != 1).sum(), "HIGH")
    rep.check("accrual_variance_when_received", len(acc[acc["invoice_received_flag"] == 1]),
              (acc[acc["invoice_received_flag"] == 1]["actual_invoice_cost"].isna()).sum(), "MEDIUM")

    # 20. Lineage: every enterprise shipment maps to a unique staged source record
    stg_ids = set(d["stg_shipment"]["source_record_id"])
    rep.check("shipment_lineage_to_source", len(ship),
              int((~ship["source_record_id"].isin(stg_ids)).sum()), "CRITICAL")
    rep.check("shipment_count_matches_source", 1, int(len(ship) != len(stg_ids)), "CRITICAL")

    return rep


def main() -> int:
    cfg = load_config()
    d = _load()
    rep = run_checks(d, cfg)
    frame = rep.frame()
    frame.to_csv(CLEAN / "rpt_phase2_baseline_validation.csv", index=False)

    critical_fail = frame[(frame["severity"] == "CRITICAL") & (frame["status"] == "FAIL")]
    any_fail = frame[frame["status"] == "FAIL"]
    log.info("Baseline validation: %d checks, %d failed (%d critical)",
             len(frame), len(any_fail), len(critical_fail))
    if len(any_fail):
        for r in any_fail.itertuples(index=False):
            log.warning("  FAIL[%s] %s: %d/%d", r.severity, r.validation_name, r.failures, r.records_tested)
    else:
        log.info("  ✓ all checks passed")
    return 1 if len(critical_fail) else 0


if __name__ == "__main__":
    sys.exit(main())
