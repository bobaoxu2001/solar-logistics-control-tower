"""Phase 2 — generate the clean-baseline operational fact tables.

Reads the staged shipments, the master data, and the shared per-shipment
resolution from generate_master_data.py, then builds POs, shipments (with
documented date derivation), milestones, freight invoices + lines, accessorials,
PODs, claims, capacity, invoice approvals, and accruals — all deterministic.

The output is the CLEAN baseline (data/processed/clean/*.csv): internally
consistent, zero intended exceptions. Exceptions are injected separately by
src/inject_exceptions.py. Also writes rpt_lane_derivation.csv and
rpt_rate_reconciliation.csv.
"""

from __future__ import annotations

import sys
from datetime import timedelta

import numpy as np
import pandas as pd

from common import DATA_INTERIM, DATA_PROCESSED, get_logger, load_config
from gen_common import DERIVED, SIMULATED, record_rng, region_of

log = get_logger("generate_enterprise_data")
CLEAN = DATA_PROCESSED / "clean"


def _read(name, **kw):
    return pd.read_csv(CLEAN / f"{name}.csv", **kw)


def _uni(salt, key, lo=0.0, hi=1.0):
    return float(record_rng(salt, key).uniform(lo, hi))


# ---------------------------------------------------------------------------
# Shipment fact (with date derivation)
# ---------------------------------------------------------------------------
def build_shipments(stg, res, lanes, products, cfg):
    p2 = cfg["phase2"]
    pool = p2["carrier_mode_pool"]
    std_by_lane = dict(zip(lanes["lane_id"], lanes["standard_transit_days"]))
    as_of = pd.Timestamp(p2["data_as_of_date"])
    booking_lead = int(p2["booking_lead_days"])
    noise = int(p2["transit_noise_days"])

    # product SKUs & category unit weights
    prod_by_cat = {c: g["product_id"].tolist() for c, g in products.groupby("product_category")}
    unitwt_by_prod = dict(zip(products["product_id"], products["unit_weight_kg"]))

    site_country = dict(zip(
        _read("dim_location")["location_id"], _read("dim_location")["country"]))

    m = stg.merge(res, on="source_record_id", how="left")
    rows = []
    for r in m.itertuples(index=False):
        srid = r.source_record_id
        mode = r.resolved_mode
        lane_id = r.lane_id
        # carrier: deterministic pick from the lane-mode pool
        cands = pool.get(mode, ["CAR09"])
        carrier_id = str(record_rng("carrier", srid).choice(cands))
        # product: deterministic pick within category
        cat = r.product_category
        pcands = prod_by_cat.get(cat, [])
        product_id = str(record_rng("product", srid).choice(pcands)) if pcands else None

        qty = int(r.line_item_quantity)
        # weight: real where available, else imputed from product unit weight
        if pd.notna(r.weight_kg):
            weight = float(r.weight_kg); weight_imp = 0
        else:
            uw = unitwt_by_prod.get(product_id, 0.3)
            weight = round(uw * qty, 2); weight_imp = 1

        planned_delivery = pd.Timestamp(r.reporting_scheduled_delivery_date)
        actual_delivery = pd.Timestamp(r.reporting_actual_delivery_date)
        std = int(std_by_lane.get(lane_id, 10))
        # actual transit: standard +/- seeded jitter, clamped >= 1
        jitter = int(round(record_rng("transit", srid).uniform(-noise, noise)))
        actual_transit = max(1, std + jitter)
        actual_ship = actual_delivery - timedelta(days=actual_transit)
        planned_ship = planned_delivery - timedelta(days=std)
        booking = min(actual_ship, planned_ship) - timedelta(days=booking_lead)

        delivered = actual_delivery <= as_of
        status = "DELIVERED" if delivered else "IN_TRANSIT"

        # customs required if cross-border (origin country != dest country)
        oc = site_country.get(r.origin_location_id)
        dc = r.destination_country
        customs = 0 if (oc is not None and oc == dc) else 1
        hazmat = 1 if cat == "BATTERY_ESS" else 0

        rows.append({
            "shipment_id": f"SHP{srid:07d}", "source_record_id": srid,
            "po_id": None,  # filled after PO build
            "carrier_id": carrier_id, "lane_id": lane_id, "product_id": product_id,
            "origin_location_id": r.origin_location_id,
            "destination_location_id": r.destination_location_id,
            "warehouse_id": r.warehouse_id, "shipment_mode": mode,
            "incoterm": (r.incoterm if pd.notna(r.incoterm) else None),
            "booking_date": booking.date(), "planned_ship_date": planned_ship.date(),
            "actual_ship_date": actual_ship.date(),
            "planned_delivery_date": planned_delivery.date(),
            "actual_delivery_date": (actual_delivery.date() if delivered else None),
            "planned_quantity": qty, "shipped_quantity": (qty if status != "IN_TRANSIT" else qty),
            "delivered_quantity": (qty if delivered else None),
            "shipment_weight_kg": weight, "shipment_value_usd": float(r.line_item_value_usd),
            "shipment_status": status, "customs_required_flag": customs, "hazmat_flag": hazmat,
            "is_delivered_flag": int(delivered), "ship_date_derived_flag": 1,
            "weight_imputed_flag": weight_imp, "mode_imputed_flag": int(r.mode_imputed_flag),
            "data_class": DERIVED,
            # transient helpers (dropped before persist)
            "helper_transit": actual_transit, "helper_std": std,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Purchase orders — group shipment lines sharing a source PO reference
# ---------------------------------------------------------------------------
def build_purchase_orders(stg, ships, suppliers, products, cfg):
    p2 = cfg["phase2"]
    prefix = p2["po_number_prefix"]
    lead = int(p2["po_lead_days_before_ship"])
    sup_by_vendor = dict(zip(suppliers["supplier_name"], suppliers["supplier_id"]))

    s = ships.merge(
        stg[["source_record_id", "po_so_number", "vendor_name", "product_category",
             "unit_price_usd"]],
        on="source_record_id", how="left")
    # group key: real PO reference when present, else per-source-line derived key
    s["po_group"] = s.apply(
        lambda r: f"SRC:{r['po_so_number']}" if isinstance(r["po_so_number"], str)
        and r["po_so_number"] not in ("", "nan") else f"LINE:{r['source_record_id']}", axis=1)

    po_rows, po_map = [], {}
    for i, (gkey, g) in enumerate(sorted(s.groupby("po_group"), key=lambda x: x[0]), 1):
        po_id = f"PO{i:06d}"
        po_number = f"{prefix}-{i:06d}"
        vendor = g["vendor_name"].dropna().mode()
        supplier_id = sup_by_vendor.get(vendor.iloc[0]) if len(vendor) else None
        product_id = g["product_id"].dropna().mode()
        product_id = product_id.iloc[0] if len(product_id) else None
        ordered_qty = int(g["planned_quantity"].sum())
        value = float(g["shipment_value_usd"].sum())
        unit_price = round(value / ordered_qty, 4) if ordered_qty else None
        earliest_ship = pd.to_datetime(g["planned_ship_date"]).min()
        po_created = (earliest_ship - timedelta(days=lead)).date()
        exp_delivery = pd.to_datetime(g["planned_delivery_date"]).min().date()
        all_delivered = (g["shipment_status"] == "DELIVERED").all()
        po_rows.append({
            "po_id": po_id, "po_number": po_number, "supplier_id": supplier_id,
            "product_id": product_id, "ordered_quantity": ordered_qty,
            "unit_price": unit_price, "purchase_value": round(value, 2), "currency": "USD",
            "po_created_date": po_created, "expected_ship_date": earliest_ship.date(),
            "expected_delivery_date": exp_delivery,
            "po_status": "CLOSED" if all_delivered else "SHIPPED", "data_class": DERIVED,
        })
        for srid in g["source_record_id"]:
            po_map[srid] = po_id
    return pd.DataFrame(po_rows), po_map


# ---------------------------------------------------------------------------
# Milestones — mode-aware ordered templates
# ---------------------------------------------------------------------------
_SEQ_ORDER = ["BOOKING_CONFIRMED", "PICKUP_COMPLETED", "ORIGIN_DEPARTURE", "EXPORT_CUSTOMS",
              "PORT_ARRIVAL", "IMPORT_CUSTOMS", "WAREHOUSE_ARRIVAL", "OUT_FOR_DELIVERY",
              "CUSTOMER_DELIVERY", "POD_RECEIVED"]


def build_milestones(ships, cfg):
    tmpl = cfg["phase2"]["milestone_offsets_frac"]
    as_of = pd.Timestamp(cfg["phase2"]["data_as_of_date"])
    rows = []
    for r in ships.itertuples(index=False):
        mode = r.shipment_mode
        offsets = tmpl.get(mode, tmpl["AIR"])
        ship_ts = pd.Timestamp(r.actual_ship_date)
        transit = r.helper_transit
        # order milestones by canonical sequence then by fractional offset
        items = sorted(offsets.items(), key=lambda kv: (_SEQ_ORDER.index(kv[0]), kv[1]))
        seq = 0
        for mtype, frac in items:
            seq += 1
            planned_ts = ship_ts + timedelta(days=frac * r.helper_std)
            actual_ts = ship_ts + timedelta(days=frac * transit)
            completed = r.is_delivered_flag == 1 or actual_ts <= as_of
            rows.append({
                "milestone_id": f"MS{r.source_record_id:07d}-{seq:02d}",
                "shipment_id": r.shipment_id, "milestone_type": mtype,
                "milestone_sequence": seq,
                "planned_timestamp": planned_ts, "actual_timestamp": (actual_ts if completed else None),
                "milestone_status": "COMPLETED" if completed else "PLANNED",
                "exception_reason": None, "data_class": SIMULATED,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Rate lookup helper
# ---------------------------------------------------------------------------
def rate_lookup(rate_cards):
    idx = {}
    for r in rate_cards.itertuples(index=False):
        idx[(r.carrier_id, r.lane_id)] = r
    return idx


def expected_freight(ship, rate):
    """Return (base, fuel) expected from the rate card (before rating noise)."""
    base = max(float(rate.rate_per_kg) * float(ship.shipment_weight_kg),
               float(rate.minimum_charge))
    fuel = base * float(rate.fuel_percentage)
    return round(base, 2), round(fuel, 2)


# ---------------------------------------------------------------------------
# Accessorials (built before invoices so invoice totals include them)
# ---------------------------------------------------------------------------
def build_accessorials(ships, cfg):
    rules = cfg["phase2"]["accessorial_base_rates"]
    rows = []
    for r in ships.itertuples(index=False):
        if r.shipment_status != "DELIVERED":
            continue
        for ctype, spec in rules.items():
            if r.shipment_mode not in spec["modes"]:
                continue
            if _uni(f"acc_{ctype}", r.source_record_id) < spec["rate"]:
                lo, hi = spec["amount_range"]
                amt = round(_uni(f"acc_amt_{ctype}", r.source_record_id, lo, hi), 2)
                rows.append({
                    "accessorial_id": f"ACC-{r.source_record_id:07d}-{ctype[:3]}",
                    "invoice_id": f"INV{r.source_record_id:07d}",  # 1:1 invoice per shipment
                    "shipment_id": r.shipment_id, "charge_type": ctype, "charge_amount": amt,
                    "supporting_document_flag": 1, "contractually_allowed_flag": 1,
                    "approval_status": "APPROVED",
                    "reason": f"{ctype.title()} incurred at destination", "data_class": SIMULATED,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Freight invoices + invoice lines
# ---------------------------------------------------------------------------
def build_invoices(ships, rate_idx, accessorials, cfg):
    p2 = cfg["phase2"]
    noise_pct = float(p2["invoice_rating_noise_pct"])
    lag_lo, lag_hi = p2["invoice_lag_days_range"]
    acc_by_ship = accessorials.groupby("shipment_id")["charge_amount"].sum().to_dict() if len(accessorials) else {}

    inv_rows, line_rows, recon = [], [], []
    for r in ships.itertuples(index=False):
        if r.shipment_status != "DELIVERED":
            continue  # invoice only after service completion
        rate = rate_idx.get((r.carrier_id, r.lane_id))
        if rate is None:
            continue  # should not happen in clean baseline (asserted in validation)
        base, fuel = expected_freight(r, rate)
        # small deterministic rating noise, kept well within audit tolerance
        nf = 1 + record_rng("inv_noise", r.source_record_id).uniform(-noise_pct, noise_pct)
        base_inv = round(base * nf, 2)
        fuel_inv = round(base_inv * float(rate.fuel_percentage), 2)
        acc = round(float(acc_by_ship.get(r.shipment_id, 0.0)), 2)
        tax = round(base_inv * float(p2["rate_card"]["tax_pct"]), 2)
        total = round(base_inv + fuel_inv + acc + tax, 2)

        delivery = pd.Timestamp(r.actual_delivery_date)
        inv_date = (delivery + timedelta(days=int(_uni("inv_lag", r.source_record_id, lag_lo, lag_hi)))).date()
        invoice_id = f"INV{r.source_record_id:07d}"
        inv_rows.append({
            "invoice_id": invoice_id, "invoice_number": f"FIN-{r.source_record_id:07d}",
            "shipment_id": r.shipment_id, "carrier_id": r.carrier_id, "invoice_date": inv_date,
            "service_period_start": r.actual_ship_date, "service_period_end": r.actual_delivery_date,
            "base_charge": base_inv, "fuel_surcharge": fuel_inv, "accessorial_charge": acc,
            "tax_amount": tax, "invoice_total": total, "currency": str(rate.currency),
            "approval_status": None, "payment_status": None,  # filled by approvals
            "data_class": SIMULATED,
        })
        line_rows.append({"invoice_line_id": f"IL-{r.source_record_id:07d}-1", "invoice_id": invoice_id,
                          "line_type": "BASE_FREIGHT", "description": "Base freight per rate card",
                          "amount": base_inv, "currency": str(rate.currency), "data_class": SIMULATED})
        line_rows.append({"invoice_line_id": f"IL-{r.source_record_id:07d}-2", "invoice_id": invoice_id,
                          "line_type": "FUEL_SURCHARGE", "description": "Fuel surcharge",
                          "amount": fuel_inv, "currency": str(rate.currency), "data_class": SIMULATED})
        if acc > 0:
            line_rows.append({"invoice_line_id": f"IL-{r.source_record_id:07d}-3", "invoice_id": invoice_id,
                              "line_type": "ACCESSORIAL", "description": "Accessorial charges",
                              "amount": acc, "currency": str(rate.currency), "data_class": SIMULATED})
        if tax > 0:
            line_rows.append({"invoice_line_id": f"IL-{r.source_record_id:07d}-4", "invoice_id": invoice_id,
                              "line_type": "TAX", "description": "Tax", "amount": tax,
                              "currency": str(rate.currency), "data_class": SIMULATED})
        recon.append({"mode": r.shipment_mode, "expected": base + fuel, "invoiced": base_inv + fuel_inv})
    return pd.DataFrame(inv_rows), pd.DataFrame(line_rows), pd.DataFrame(recon)


# ---------------------------------------------------------------------------
# Invoice approvals (sets approval_status / payment_status on invoices)
# ---------------------------------------------------------------------------
def build_approvals(invoices, ships, cfg):
    ap = cfg["phase2"]["approval"]
    stages = ap["stages"]
    lo, hi = ap["review_days_range"]
    as_of = pd.Timestamp(cfg["phase2"]["data_as_of_date"])
    pending_cut = as_of - timedelta(days=int(ap["pending_recent_days"]))
    paid_frac = float(ap["paid_fraction_of_approved"])
    role_by_stage = {"LOGISTICS_REVIEW": "Logistics Analyst", "RATE_VALIDATION": "Freight Auditor",
                     "FINANCE_APPROVAL": "AP Finance Approver", "PAYMENT_RELEASE": "Treasury"}

    rows, inv_status = [], {}
    for r in invoices.itertuples(index=False):
        srid = int(r.shipment_id.replace("SHP", ""))
        inv_date = pd.Timestamp(r.invoice_date)
        # recent invoices may legitimately still be pending
        stays_pending = inv_date > pending_cut and _uni("pending", srid) < 0.5
        ts = inv_date
        approved_all = True
        for stg_i, stage in enumerate(stages, 1):
            submitted = ts
            if stays_pending and stg_i >= 3:
                rows.append({"approval_id": f"AP-{srid:07d}-{stg_i}", "invoice_id": r.invoice_id,
                             "approval_stage": stage, "assigned_role": role_by_stage[stage],
                             "submitted_timestamp": submitted, "approved_timestamp": None,
                             "approval_status": "PENDING", "rejection_reason": None,
                             "data_class": SIMULATED})
                approved_all = False
                break
            dd = int(_uni(f"appr_{stg_i}", srid, lo, hi))
            approved = submitted + timedelta(days=dd)
            ts = approved
            rows.append({"approval_id": f"AP-{srid:07d}-{stg_i}", "invoice_id": r.invoice_id,
                         "approval_stage": stage, "assigned_role": role_by_stage[stage],
                         "submitted_timestamp": submitted, "approved_timestamp": approved,
                         "approval_status": "APPROVED", "rejection_reason": None,
                         "data_class": SIMULATED})
        if approved_all:
            paid = _uni("paid", srid) < paid_frac
            inv_status[r.invoice_id] = ("APPROVED", "PAID" if paid else "UNPAID", ts)
        else:
            inv_status[r.invoice_id] = ("PENDING", "UNPAID", None)
    return pd.DataFrame(rows), inv_status


# ---------------------------------------------------------------------------
# Proof of delivery
# ---------------------------------------------------------------------------
def build_pod(ships, cfg):
    roles = ["Warehouse Receiving Clerk", "Site Project Foreman", "DC Dock Supervisor",
             "Customer Logistics Coordinator"]
    rows = []
    for r in ships.itertuples(index=False):
        if r.shipment_status != "DELIVERED":
            continue
        delivery = pd.Timestamp(r.actual_delivery_date)
        received = delivery + timedelta(hours=int(_uni("pod", r.source_record_id, 1, 48)))
        recipient = roles[int(_uni("pod_role", r.source_record_id, 0, len(roles))) % len(roles)]
        rows.append({
            "pod_id": f"POD{r.source_record_id:07d}", "shipment_id": r.shipment_id,
            "delivery_timestamp": delivery, "received_timestamp": received,
            "recipient_name": recipient, "document_reference": f"POD-{r.source_record_id:07d}",
            "pod_status": "RECEIVED", "data_class": SIMULATED,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Claims (legitimate business records, risk-weighted)
# ---------------------------------------------------------------------------
def build_claims(ships, cfg):
    c = cfg["phase2"]["claims"]
    vhi = ships["shipment_value_usd"].quantile(0.90)
    rows = []
    for r in ships.itertuples(index=False):
        if r.shipment_status != "DELIVERED":
            continue
        p = c["base_rate"]
        late = pd.Timestamp(r.actual_delivery_date) > pd.Timestamp(r.planned_delivery_date)
        if late:
            p *= c["late_multiplier"]
        if r.shipment_value_usd >= vhi:
            p *= c["high_value_multiplier"]
        if r.shipment_mode in ("OCEAN", "MULTIMODAL"):
            p *= c["ocean_multiplier"]
        if _uni("claim", r.source_record_id) >= min(p, 0.5):
            continue
        rng = record_rng("claim_attr", r.source_record_id)
        ctype = str(rng.choice(c["types"]))
        cause = str(rng.choice(c["root_causes"]))
        amt = round(float(r.shipment_value_usd) * rng.uniform(0.02, 0.15), 2)
        created = (pd.Timestamp(r.actual_delivery_date) + timedelta(days=int(rng.uniform(2, 20)))).date()
        is_open = rng.uniform() < c["open_fraction"]
        closed = None if is_open else (pd.Timestamp(created) + timedelta(days=int(rng.uniform(10, 60)))).date()
        rows.append({
            "claim_id": f"CLM{r.source_record_id:07d}", "shipment_id": r.shipment_id,
            "claim_type": ctype, "claim_amount": amt,
            "claim_status": "OPEN" if is_open else str(rng.choice(["APPROVED", "DENIED", "CLOSED"])),
            "root_cause": cause, "created_date": created, "closed_date": closed,
            "data_class": SIMULATED,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Carrier capacity (monthly, per carrier x lane)
# ---------------------------------------------------------------------------
def build_capacity(ships, cfg):
    headroom = float(cfg["phase2"]["capacity_headroom_pct"])
    df = ships.copy()
    df["period_month"] = pd.to_datetime(df["actual_ship_date"]).dt.to_period("M").astype(str)
    grp = df.groupby(["carrier_id", "lane_id", "period_month"]).agg(
        utilized=("shipment_weight_kg", "sum")).reset_index()
    rows = []
    for i, r in enumerate(grp.itertuples(index=False), 1):
        month = int(r.period_month.split("-")[1])
        seasonal = 1 + 0.15 * np.sin((month / 12) * 2 * np.pi)  # deterministic seasonal swing
        booked = r.utilized * (1 + 0.05 * _uni("cap_book", f"{r.carrier_id}:{r.lane_id}:{r.period_month}"))
        available = booked / max(0.55, (1 - headroom * seasonal))
        util_pct = round(min(100.0, r.utilized / available * 100), 2) if available else 0.0
        rows.append({
            "capacity_id": f"CAP{i:06d}", "carrier_id": r.carrier_id, "lane_id": r.lane_id,
            "period_start": f"{r.period_month}-01", "period_month": r.period_month,
            "available_capacity_kg": round(available, 2), "booked_capacity_kg": round(booked, 2),
            "utilized_capacity_kg": round(float(r.utilized), 2), "capacity_utilization_pct": util_pct,
            "data_class": SIMULATED,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Accruals
# ---------------------------------------------------------------------------
def build_accruals(ships, invoices, inv_status, rate_idx, cfg):
    lag = int(cfg["phase2"]["accrual"]["month_end_cutoff_lag_days"])
    inv_by_ship = {r.shipment_id: r for r in invoices.itertuples(index=False)}
    rows = []
    for r in ships.itertuples(index=False):
        rate = rate_idx.get((r.carrier_id, r.lane_id))
        if rate is None:
            continue
        base, fuel = expected_freight(r, rate)
        expected = round(base + fuel, 2)
        # service completion period: delivery for delivered, planned for in-transit
        svc_date = pd.Timestamp(r.actual_delivery_date) if r.shipment_status == "DELIVERED" \
            else pd.Timestamp(r.planned_delivery_date)
        period = svc_date.to_period("M")
        period_end = (period.to_timestamp("M"))
        created = period_end.date()
        inv = inv_by_ship.get(r.shipment_id)
        received = False
        actual_cost = None
        release_date = None
        status = "ACCRUED"
        if inv is not None:
            inv_date = pd.Timestamp(inv.invoice_date)
            received = inv_date <= period_end + timedelta(days=lag) or inv_date <= pd.Timestamp(cfg["phase2"]["data_as_of_date"])
            appr_status, _pay, appr_ts = inv_status.get(inv.invoice_id, ("PENDING", "UNPAID", None))
            if received:
                actual_cost = float(inv.invoice_total)
                if appr_status == "APPROVED":
                    status = "RELEASED"
                    release_date = (appr_ts.date() if appr_ts is not None else None)
                else:
                    status = "ACCRUED"  # invoice received but not approved
        variance = round((actual_cost - expected), 2) if actual_cost is not None else None
        rows.append({
            "accrual_id": f"ACR{r.source_record_id:07d}", "shipment_id": r.shipment_id,
            "accounting_period": str(period), "expected_freight_cost": expected,
            "invoice_received_flag": int(received), "actual_invoice_cost": actual_cost,
            "accrual_status": status, "accrual_created_date": created,
            "accrual_release_date": release_date, "accrual_variance": variance,
            "data_class": DERIVED,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def build_lane_report(ships, stg, lanes, cfg):
    th = cfg["phase2"]["data_sufficiency_thresholds"]
    m = ships.merge(stg[["source_record_id", "po_sent_date"]], on="source_record_id", how="left")
    m["order_lead"] = (pd.to_datetime(m["actual_delivery_date"]) - pd.to_datetime(m["po_sent_date"])).dt.days
    rows = []
    for lane in lanes.itertuples(index=False):
        g = m[m["lane_id"] == lane.lane_id]
        n = len(g)
        suff = "HIGH" if n >= th["high"] else ("MEDIUM" if n >= th["medium"] else "LOW")
        rows.append({
            "lane_id": lane.lane_id, "origin_name": lane.origin_name,
            "destination_name": lane.destination_name, "transport_mode": lane.transport_mode,
            "n_shipments": n,
            "median_order_lead_days": round(float(g["order_lead"].median()), 2) if g["order_lead"].notna().any() else None,
            "median_derived_transit_days": round(float(g["helper_transit"].median()), 2) if n else None,
            "standard_transit_days": lane.standard_transit_days,
            "derivation_method": "MODE_REGION_STANDARD", "data_sufficiency": suff,
        })
    return pd.DataFrame(rows)


def build_rate_recon(recon_df, stg):
    obs = stg[stg["freight_cost_usd"].notna()].groupby("shipment_mode")["freight_cost_usd"].median()
    rows = []
    for mode, g in recon_df.groupby("mode"):
        observed = float(obs.get(mode, np.nan))
        exp_med = float(g["expected"].median())
        rows.append({
            "reconciliation_scope": mode, "n_shipments_with_freight": int(g.shape[0]),
            "median_observed_freight": round(observed, 2) if not np.isnan(observed) else None,
            "median_expected_freight": round(exp_med, 2),
            "expected_to_observed_ratio": round(exp_med / observed, 4) if observed and not np.isnan(observed) else None,
            "notes": "Expected = rate_per_kg*weight (>=min) + fuel; observed = source freight median",
        })
    all_obs = float(stg["freight_cost_usd"].median())
    rows.append({"reconciliation_scope": "ALL", "n_shipments_with_freight": int(recon_df.shape[0]),
                 "median_observed_freight": round(all_obs, 2),
                 "median_expected_freight": round(float(recon_df["expected"].median()), 2),
                 "expected_to_observed_ratio": round(float(recon_df["expected"].median()) / all_obs, 4),
                 "notes": "All-mode roll-up"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def main() -> int:
    cfg = load_config()
    stg = pd.read_csv(DATA_PROCESSED / "stg_shipment.csv", parse_dates=[
        "po_sent_date", "reporting_scheduled_delivery_date", "reporting_actual_delivery_date"])
    res = pd.read_csv(DATA_INTERIM / "shipment_resolved.csv")
    lanes = _read("dim_lane")
    products = _read("dim_product")
    suppliers = _read("dim_supplier")
    rate_cards = _read("dim_rate_card")
    rate_idx = rate_lookup(rate_cards)

    log.info("Building shipments…")
    ships = build_shipments(stg, res, lanes, products, cfg)

    log.info("Building purchase orders…")
    pos, po_map = build_purchase_orders(stg, ships, suppliers, products, cfg)
    ships["po_id"] = ships["source_record_id"].map(po_map)

    log.info("Building milestones…")
    milestones = build_milestones(ships, cfg)

    log.info("Building accessorials & invoices…")
    accessorials = build_accessorials(ships, cfg)
    invoices, inv_lines, recon = build_invoices(ships, rate_idx, accessorials, cfg)

    log.info("Building approvals…")
    approvals, inv_status = build_approvals(invoices, ships, cfg)
    invoices["approval_status"] = invoices["invoice_id"].map(lambda i: inv_status[i][0])
    invoices["payment_status"] = invoices["invoice_id"].map(lambda i: inv_status[i][1])

    log.info("Building POD, claims, capacity, accruals…")
    pod = build_pod(ships, cfg)
    claims = build_claims(ships, cfg)
    capacity = build_capacity(ships, cfg)
    accruals = build_accruals(ships, invoices, inv_status, rate_idx, cfg)

    lane_report = build_lane_report(ships, stg, lanes, cfg)
    rate_recon = build_rate_recon(recon, stg)

    # drop transient helpers before persisting the shipment fact
    ships_out = ships.drop(columns=["helper_transit", "helper_std"])

    outputs = {
        "fact_purchase_order": pos, "fact_shipment": ships_out,
        "fact_shipment_milestone": milestones, "fact_freight_invoice": invoices,
        "fact_invoice_line": inv_lines, "fact_accessorial_charge": accessorials,
        "fact_proof_of_delivery": pod, "fact_claim": claims,
        "fact_carrier_capacity": capacity, "fact_invoice_approval": approvals,
        "fact_accrual": accruals, "rpt_lane_derivation": lane_report,
        "rpt_rate_reconciliation": rate_recon,
    }
    for name, df in outputs.items():
        df.to_csv(CLEAN / f"{name}.csv", index=False)
        log.info("  %-28s %6d rows", name, len(df))

    delivered = int((ships_out["shipment_status"] == "DELIVERED").sum())
    log.info("shipments=%d (delivered=%d, in_transit=%d) | POs=%d | invoices=%d | claims=%d",
             len(ships_out), delivered, len(ships_out) - delivered, len(pos), len(invoices), len(claims))
    log.info("rate reconciliation (expected/observed ratio ALL): %s",
             rate_recon.loc[rate_recon["reconciliation_scope"] == "ALL", "expected_to_observed_ratio"].iloc[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
