"""Phase 2 — controlled exception injection (separate from the clean baseline).

Reads the validated clean baseline (data/processed/clean/*.csv) and the rates in
config/exception_config.yaml, then writes an OPERATIONAL copy
(data/processed/operational/*.csv) with deterministically injected data-quality
and billing exceptions. The clean baseline is never modified. Every change is
recorded in the exception manifest (clean_value + injected_value preserved), so
Phase 3 can measure whether SQL validation rules detect each injected defect.

Design guarantees:
  * Deterministic & reproducible (seeded); re-running yields identical output.
  * Disjoint selection — a given record/column is touched by at most one
    exception type (per-pool `used` sets), so exceptions never silently overlap.
  * Config-driven — rates live in exception_config.yaml; any type can be
    disabled by removing it or setting rate 0.
  * Idempotent — operational files are fully rewritten each run.

Usage:
    python src/inject_exceptions.py
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from common import DATA_PROCESSED, get_logger, load_config
from gen_common import SIMULATED, det_hash

log = get_logger("inject_exceptions")
CLEAN = DATA_PROCESSED / "clean"
OPER = DATA_PROCESSED / "operational"

# Detection-rule hints consumed by Phase 3 (documented expectation per type).
DETECTION_RULES = {
    "missing_carrier_id": "fact_shipment.carrier_id IS NULL",
    "invalid_lane": "fact_shipment.lane_id NOT IN (SELECT lane_id FROM dim_lane)",
    "duplicate_invoice": "invoice_number appears on >1 invoice row",
    "missing_pod": "delivered shipment with no fact_proof_of_delivery row",
    "expired_rate_card": "shipment actual_ship_date > applicable rate effective_end_date",
    "invoice_carrier_mismatch": "invoice.carrier_id <> shipment.carrier_id",
    "delivery_before_ship": "actual_delivery_date < actual_ship_date",
    "over_delivery": "delivered_quantity > planned_quantity",
    "unauthorized_detention": "accessorial contractually_allowed_flag = 0",
    "excessive_demurrage": "demurrage charge_amount above contractual band",
    "incorrect_fuel_surcharge": "abs(fuel_surcharge - base_charge*contractual_pct) beyond tolerance",
    "shipment_without_invoice": "delivered shipment with no fact_freight_invoice row",
    "invoice_without_shipment": "invoice.shipment_id NOT IN (SELECT shipment_id FROM fact_shipment)",
    "duplicate_payment_risk": ">1 PAID invoice for the same shipment_id",
    "incorrect_currency": "invoice.currency <> applicable rate_card.currency",
    "missing_hts_code": "dim_product.hts_code IS NULL",
    "missing_customs_doc": "customs milestone status MISSED / missing for customs-required shipment",
    "partial_delivery": "delivered_quantity < planned_quantity",
    "damaged_shipment_claim": "injected DAMAGE claim linked to shipment",
}


class Injector:
    def __init__(self, tables: dict, cfg: dict, exc_cfg: dict):
        self.t = tables
        self.cfg = cfg
        self.seed = int(cfg["random_seed"])
        self.exc = exc_cfg["exceptions"]
        self.manifest = []
        self.summary = []
        self._used = {}  # pool_name -> set(record_id)
        self.now = datetime.now(timezone.utc)

    # -- selection ---------------------------------------------------------
    def target_count(self, etype: str, n_eligible: int) -> int:
        rate = float(self.exc[etype]["rate"])
        n = int(round(rate * n_eligible))
        if n == 0 and rate > 0 and n_eligible > 0:
            n = 1
        return min(n, n_eligible)

    def select(self, etype: str, pool_name: str, ids: list, n: int) -> list:
        used = self._used.setdefault(pool_name, set())
        ranked = sorted((i for i in ids if i not in used), key=lambda x: det_hash(etype, x))
        chosen = ranked[:n]
        used.update(chosen)
        return chosen

    def record(self, etype: str, table: str, record_id, column, clean, injected):
        self.manifest.append({
            "exception_manifest_id": f"XM-{len(self.manifest)+1:06d}",
            "exception_type": etype, "target_table": table, "record_id": str(record_id),
            "column_name": column,
            "clean_value": (None if clean is None else str(clean)),
            "injected_value": (None if injected is None else str(injected)),
            "injection_timestamp": self.now, "random_seed": self.seed,
            "configured_rate": float(self.exc[etype]["rate"]),
            "severity": self.exc[etype]["severity"].upper(),
            "expected_detection_rule": DETECTION_RULES[etype], "data_class": SIMULATED,
        })

    # -- helpers -----------------------------------------------------------
    def _rate_currency_by_ship(self):
        ship = self.t["fact_shipment"]
        rc = self.t["dim_rate_card"]
        cur = {(r.carrier_id, r.lane_id): r.currency for r in rc.itertuples(index=False)}
        return {r.shipment_id: cur.get((r.carrier_id, r.lane_id)) for r in ship.itertuples(index=False)}

    # -- exception implementations ----------------------------------------
    def run(self):
        # exception_reason is all-null (float) in the clean baseline; make it
        # object so string reasons can be written (pandas 3.0 is strict).
        ms = self.t["fact_shipment_milestone"]
        ms["exception_reason"] = ms["exception_reason"].astype(object)
        ms["actual_timestamp"] = ms["actual_timestamp"].astype(object)

        ship = self.t["fact_shipment"]
        delivered = ship[ship["shipment_status"] == "DELIVERED"]["shipment_id"].tolist()
        ship_ix = {sid: i for i, sid in zip(ship.index, ship["shipment_id"])}
        # invoice-exception rate denominator = clean invoice count (before any
        # deletions/inserts), so expected counts stay stable and predictable.
        self.base_invoice_count = len(self.t["fact_freight_invoice"])

        # ---- shipment-level (disjoint over delivered shipments) ----------
        # Deletions (missing_pod, shipment_without_invoice) run here so that
        # invoice-level exceptions below never select an already-deleted invoice.
        self._missing_carrier_id(ship, ship_ix, delivered)
        self._invalid_lane(ship, ship_ix, delivered)
        self._delivery_before_ship(ship, ship_ix, delivered)
        self._over_delivery(ship, ship_ix, delivered)
        self._partial_delivery(ship, ship_ix, delivered)
        self._missing_pod(delivered)
        self._shipment_without_invoice(delivered)
        self._missing_customs_doc(ship, delivered)
        self._damaged_shipment_claim(ship, ship_ix, delivered)

        # ---- invoice-level (disjoint over invoices; each reads current self.t)
        self._invoice_carrier_mismatch()
        self._incorrect_fuel_surcharge()
        self._incorrect_currency()
        self._expired_rate_card()
        self._duplicate_invoice()
        self._duplicate_payment_risk()
        self._invoice_without_shipment()

        # ---- accessorial-level (inserts) ---------------------------------
        self._unauthorized_detention(ship, delivered)
        self._excessive_demurrage(ship, delivered)

        # ---- product-level ----------------------------------------------
        self._missing_hts_code()

    def _log_summary(self, etype, eligible, chosen, table, overlap=False):
        self.summary.append({
            "exception_type": etype, "eligible_records": eligible,
            "configured_rate": float(self.exc[etype]["rate"]),
            "expected_count": self.target_count(etype, eligible),
            "actual_count": chosen, "affected_table": table,
            "severity": self.exc[etype]["severity"].upper(), "overlap_occurred": overlap,
        })

    # shipment-level
    def _missing_carrier_id(self, ship, ix, pool):
        e = "missing_carrier_id"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        for sid in ids:
            i = ix[sid]; clean = ship.at[i, "carrier_id"]
            ship.at[i, "carrier_id"] = None
            self.record(e, "fact_shipment", sid, "carrier_id", clean, None)
        self._log_summary(e, len(pool), len(ids), "fact_shipment")

    def _invalid_lane(self, ship, ix, pool):
        e = "invalid_lane"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        for sid in ids:
            i = ix[sid]; clean = ship.at[i, "lane_id"]
            ship.at[i, "lane_id"] = "LANE_INVALID"
            self.record(e, "fact_shipment", sid, "lane_id", clean, "LANE_INVALID")
        self._log_summary(e, len(pool), len(ids), "fact_shipment")

    def _delivery_before_ship(self, ship, ix, pool):
        e = "delivery_before_ship"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        for sid in ids:
            i = ix[sid]; clean = ship.at[i, "actual_delivery_date"]
            newv = str((pd.Timestamp(ship.at[i, "actual_ship_date"]) - timedelta(days=2)).date())
            ship.at[i, "actual_delivery_date"] = newv
            self.record(e, "fact_shipment", sid, "actual_delivery_date", clean, newv)
        self._log_summary(e, len(pool), len(ids), "fact_shipment")

    def _over_delivery(self, ship, ix, pool):
        e = "over_delivery"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        for sid in ids:
            i = ix[sid]; clean = ship.at[i, "delivered_quantity"]
            newv = int(round(float(ship.at[i, "planned_quantity"]) * 1.2))
            ship.at[i, "delivered_quantity"] = newv
            self.record(e, "fact_shipment", sid, "delivered_quantity", clean, newv)
        self._log_summary(e, len(pool), len(ids), "fact_shipment")

    def _partial_delivery(self, ship, ix, pool):
        e = "partial_delivery"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        for sid in ids:
            i = ix[sid]; clean = ship.at[i, "delivered_quantity"]
            newv = int(round(float(ship.at[i, "planned_quantity"]) * 0.7))
            ship.at[i, "delivered_quantity"] = newv
            self.record(e, "fact_shipment", sid, "delivered_quantity", clean, newv)
        self._log_summary(e, len(pool), len(ids), "fact_shipment")

    def _missing_pod(self, pool):
        e = "missing_pod"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        pod = self.t["fact_proof_of_delivery"]
        drop = pod["shipment_id"].isin(ids)
        for sid in ids:
            self.record(e, "fact_proof_of_delivery", sid, "pod_id", f"POD_for_{sid}", "DELETED")
        self.t["fact_proof_of_delivery"] = pod[~drop].reset_index(drop=True)
        self._log_summary(e, len(pool), len(ids), "fact_proof_of_delivery")

    def _shipment_without_invoice(self, pool):
        e = "shipment_without_invoice"
        ids = self.select(e, "shipment", pool, self.target_count(e, len(pool)))
        inv = self.t["fact_freight_invoice"]
        drop = inv["shipment_id"].isin(ids)
        dropped_inv = inv[drop]
        # cascade: also drop their invoice lines / approvals / accessorials
        for tbl, col in [("fact_invoice_line", "invoice_id"), ("fact_invoice_approval", "invoice_id"),
                         ("fact_accessorial_charge", "invoice_id")]:
            di = self.t[tbl]
            self.t[tbl] = di[~di[col].isin(dropped_inv["invoice_id"])].reset_index(drop=True)
        for sid in ids:
            self.record(e, "fact_freight_invoice", sid, "invoice_id",
                        dropped_inv.loc[dropped_inv["shipment_id"] == sid, "invoice_id"].iloc[0], "DELETED")
        self.t["fact_freight_invoice"] = inv[~drop].reset_index(drop=True)
        self._log_summary(e, len(pool), len(ids), "fact_freight_invoice")

    def _missing_customs_doc(self, ship, pool):
        e = "missing_customs_doc"
        # only modes whose milestone template actually contains customs milestones
        customs_modes = ["AIR", "AIR_CHARTER", "OCEAN", "MULTIMODAL"]
        customs_ids = ship[(ship["shipment_id"].isin(pool)) & (ship["customs_required_flag"] == 1)
                           & (ship["shipment_mode"].isin(customs_modes))]["shipment_id"].tolist()
        ids = self.select(e, "shipment", customs_ids, self.target_count(e, len(customs_ids)))
        ms = self.t["fact_shipment_milestone"]
        mask = ms["shipment_id"].isin(ids) & ms["milestone_type"].isin(["IMPORT_CUSTOMS", "EXPORT_CUSTOMS"])
        # pick the highest-sequence customs milestone per shipment to flag
        targets = ms[mask].sort_values("milestone_sequence").groupby("shipment_id").tail(1)
        for r in targets.itertuples():
            self.t["fact_shipment_milestone"].at[r.Index, "milestone_status"] = "MISSED"
            self.t["fact_shipment_milestone"].at[r.Index, "actual_timestamp"] = None
            self.t["fact_shipment_milestone"].at[r.Index, "exception_reason"] = "MISSING_CUSTOMS_DOCUMENTATION"
            self.record(e, "fact_shipment_milestone", r.milestone_id, "milestone_status", "COMPLETED", "MISSED")
        self._log_summary(e, len(customs_ids), len(targets), "fact_shipment_milestone")

    def _damaged_shipment_claim(self, ship, ix, pool):
        e = "damaged_shipment_claim"
        existing = set(self.t["fact_claim"]["shipment_id"])
        eligible = [s for s in pool if s not in existing]
        ids = self.select(e, "shipment", eligible, self.target_count(e, len(pool)))
        rows = []
        for sid in ids:
            i = ix[sid]
            amt = round(float(ship.at[i, "shipment_value_usd"]) * 0.08, 2)
            created = (pd.Timestamp(ship.at[i, "actual_delivery_date"]) + timedelta(days=5)).date()
            rows.append({"claim_id": f"CLM-INJ-{sid}", "shipment_id": sid, "claim_type": "DAMAGE",
                         "claim_amount": amt, "claim_status": "OPEN", "root_cause": "ROUGH_HANDLING",
                         "created_date": created, "closed_date": None, "data_class": SIMULATED})
            self.record(e, "fact_claim", f"CLM-INJ-{sid}", "claim_id", None, "INSERTED")
        if rows:
            self.t["fact_claim"] = pd.concat([self.t["fact_claim"], pd.DataFrame(rows)], ignore_index=True)
        self._log_summary(e, len(pool), len(ids), "fact_claim")

    # invoice-level (each reads/writes the CURRENT self.t frame; rate
    # denominator is the pre-injection clean invoice count)
    def _invoice_carrier_mismatch(self):
        e = "invoice_carrier_mismatch"
        inv = self.t["fact_freight_invoice"]
        ix = {iid: i for i, iid in zip(inv.index, inv["invoice_id"])}
        ids = self.select(e, "invoice", inv["invoice_id"].tolist(), self.target_count(e, self.base_invoice_count))
        carriers = ["CAR01", "CAR03", "CAR06", "CAR09"]
        for iid in ids:
            i = ix[iid]; clean = inv.at[i, "carrier_id"]
            newc = next(c for c in carriers if c != clean)
            inv.at[i, "carrier_id"] = newc
            self.record(e, "fact_freight_invoice", iid, "carrier_id", clean, newc)
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _incorrect_fuel_surcharge(self):
        e = "incorrect_fuel_surcharge"
        inv = self.t["fact_freight_invoice"]
        ix = {iid: i for i, iid in zip(inv.index, inv["invoice_id"])}
        ids = self.select(e, "invoice", inv["invoice_id"].tolist(), self.target_count(e, self.base_invoice_count))
        for iid in ids:
            i = ix[iid]; clean = float(inv.at[i, "fuel_surcharge"])
            newv = round(clean * 1.6, 2)
            delta = newv - clean
            inv.at[i, "fuel_surcharge"] = newv
            inv.at[i, "invoice_total"] = round(float(inv.at[i, "invoice_total"]) + delta, 2)
            self.record(e, "fact_freight_invoice", iid, "fuel_surcharge", clean, newv)
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _incorrect_currency(self):
        e = "incorrect_currency"
        inv = self.t["fact_freight_invoice"]
        ix = {iid: i for i, iid in zip(inv.index, inv["invoice_id"])}
        ids = self.select(e, "invoice", inv["invoice_id"].tolist(), self.target_count(e, self.base_invoice_count))
        for iid in ids:
            i = ix[iid]; clean = inv.at[i, "currency"]
            inv.at[i, "currency"] = "EUR"
            self.record(e, "fact_freight_invoice", iid, "currency", clean, "EUR")
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _expired_rate_card(self):
        # Selected invoices' applicable rate card is expired to just before the
        # shipment ship date. Several invoices may share a rate card (same
        # carrier+lane); the DDL mutation is de-duplicated (idempotent) but each
        # selected invoice is recorded, so every one becomes a detectable
        # "shipped after rate expiry" exception. Counted at the invoice level to
        # match the configured target table.
        e = "expired_rate_card"
        inv = self.t["fact_freight_invoice"]
        ids = self.select(e, "invoice", inv["invoice_id"].tolist(), self.target_count(e, self.base_invoice_count))
        ship = self.t["fact_shipment"].set_index("shipment_id")
        rc = self.t["dim_rate_card"]
        rc_ix = {(r.carrier_id, r.lane_id): idx for idx, r in zip(rc.index, rc.itertuples(index=False))}
        expired_rate_ids = set()
        for iid in ids:
            row = inv[inv["invoice_id"] == iid].iloc[0]
            sid = row["shipment_id"]
            if sid not in ship.index:
                continue
            carrier, lane = ship.at[sid, "carrier_id"], ship.at[sid, "lane_id"]
            j = rc_ix.get((carrier, lane))
            newv = str((pd.Timestamp(ship.at[sid, "actual_ship_date"]) - timedelta(days=1)).date())
            if j is not None and rc.at[j, "rate_id"] not in expired_rate_ids:
                rc.at[j, "effective_end_date"] = newv
                expired_rate_ids.add(rc.at[j, "rate_id"])
            self.record(e, "fact_freight_invoice", iid, "applicable_rate_effective_end",
                        "active", newv)
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _duplicate_invoice(self):
        e = "duplicate_invoice"
        inv = self.t["fact_freight_invoice"]
        ids = self.select(e, "invoice", inv["invoice_id"].tolist(), self.target_count(e, self.base_invoice_count))
        dups = []
        for k, iid in enumerate(ids, 1):
            orig = inv[inv["invoice_id"] == iid].iloc[0].to_dict()
            orig["invoice_id"] = f"{iid}-DUP"          # new PK, SAME invoice_number
            dups.append(orig)
            self.record(e, "fact_freight_invoice", orig["invoice_id"], "invoice_number",
                        None, orig["invoice_number"])
        if dups:
            self.t["fact_freight_invoice"] = pd.concat([inv, pd.DataFrame(dups)], ignore_index=True)
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _duplicate_payment_risk(self):
        e = "duplicate_payment_risk"
        inv = self.t["fact_freight_invoice"]
        paid = inv[inv["payment_status"] == "PAID"]["invoice_id"].tolist()
        ids = self.select(e, "invoice", paid, self.target_count(e, self.base_invoice_count))
        dups = []
        for iid in ids:
            orig = inv[inv["invoice_id"] == iid].iloc[0].to_dict()
            orig["invoice_id"] = f"{iid}-PAY2"
            orig["invoice_number"] = f"{orig['invoice_number']}-R"
            orig["payment_status"] = "PAID"
            dups.append(orig)
            self.record(e, "fact_freight_invoice", orig["invoice_id"], "payment_status",
                        None, "PAID (second payment for same shipment)")
        if dups:
            self.t["fact_freight_invoice"] = pd.concat([self.t["fact_freight_invoice"], pd.DataFrame(dups)],
                                                       ignore_index=True)
        self._log_summary(e, self.base_invoice_count, len(ids), "fact_freight_invoice")

    def _invoice_without_shipment(self):
        e = "invoice_without_shipment"
        n = self.target_count(e, self.base_invoice_count)
        rows = []
        for k in range(1, n + 1):
            iid = f"INV-ORPHAN-{k:04d}"
            rows.append({"invoice_id": iid, "invoice_number": f"FIN-ORPHAN-{k:04d}",
                         "shipment_id": f"SHP-ORPHAN-{k:04d}", "carrier_id": "CAR09",
                         "invoice_date": self.now.date(), "service_period_start": None,
                         "service_period_end": None, "base_charge": 1000.0, "fuel_surcharge": 180.0,
                         "accessorial_charge": 0.0, "tax_amount": 0.0, "invoice_total": 1180.0,
                         "currency": "USD", "approval_status": "PENDING", "payment_status": "UNPAID",
                         "data_class": SIMULATED})
            self.record(e, "fact_freight_invoice", iid, "shipment_id", None, f"SHP-ORPHAN-{k:04d}")
        if rows:
            self.t["fact_freight_invoice"] = pd.concat([self.t["fact_freight_invoice"], pd.DataFrame(rows)],
                                                       ignore_index=True)
        self._log_summary(e, self.base_invoice_count, n, "fact_freight_invoice")

    # accessorial-level (inserts)
    def _add_accessorial(self, etype, ship, pool, ctype, amount_fn, allowed, doc, reason):
        modes = {"unauthorized_detention": ["TRUCK", "OCEAN", "MULTIMODAL"],
                 "excessive_demurrage": ["OCEAN", "MULTIMODAL"]}[etype]
        eligible = ship[(ship["shipment_id"].isin(pool)) & (ship["shipment_mode"].isin(modes))]["shipment_id"].tolist()
        ids = self.select(etype, "accessorial_ship", eligible, self.target_count(etype, len(eligible)))
        inv = self.t["fact_freight_invoice"]
        inv_by_ship = {r.shipment_id: r.invoice_id for r in inv.itertuples(index=False)}
        rows = []
        for sid in ids:
            iid = inv_by_ship.get(sid)
            if iid is None:
                continue
            amt = amount_fn(sid)
            rows.append({"accessorial_id": f"ACC-INJ-{etype[:3]}-{sid}", "invoice_id": iid,
                         "shipment_id": sid, "charge_type": ctype, "charge_amount": amt,
                         "supporting_document_flag": doc, "contractually_allowed_flag": allowed,
                         "approval_status": "PENDING", "reason": reason, "data_class": SIMULATED})
            self.record(etype, "fact_accessorial_charge", f"ACC-INJ-{etype[:3]}-{sid}",
                        "charge_type", None, f"{ctype} amt={amt} allowed={allowed}")
        if rows:
            self.t["fact_accessorial_charge"] = pd.concat([self.t["fact_accessorial_charge"], pd.DataFrame(rows)],
                                                          ignore_index=True)
        self._log_summary(etype, len(eligible), len(rows), "fact_accessorial_charge")

    def _unauthorized_detention(self, ship, pool):
        s = ship.set_index("shipment_id")
        self._add_accessorial("unauthorized_detention", ship, pool, "DETENTION",
                              lambda sid: round(float(s.at[sid, "shipment_weight_kg"]) * 0.02 + 300, 2),
                              allowed=0, doc=0, reason="Detention billed without contractual basis")

    def _excessive_demurrage(self, ship, pool):
        self._add_accessorial("excessive_demurrage", ship, pool, "DEMURRAGE",
                              lambda sid: 9500.0, allowed=1, doc=1,
                              reason="Demurrage far above contractual band")

    # product-level
    def _missing_hts_code(self):
        e = "missing_hts_code"
        prod = self.t["dim_product"]
        ids = self.select(e, "product", prod["product_id"].tolist(), self.target_count(e, len(prod)))
        for pid in ids:
            i = prod.index[prod["product_id"] == pid][0]
            clean = prod.at[i, "hts_code"]
            prod.at[i, "hts_code"] = None
            self.record(e, "dim_product", pid, "hts_code", clean, None)
        self._log_summary(e, len(prod), len(ids), "dim_product")


def main() -> int:
    cfg = load_config()
    exc_cfg = load_config("exception_config.yaml")
    OPER.mkdir(parents=True, exist_ok=True)

    # Load a mutable copy of every clean table.
    clean_files = sorted(CLEAN.glob("*.csv"))
    tables = {f.stem: pd.read_csv(f) for f in clean_files}

    inj = Injector(tables, cfg, exc_cfg)
    inj.run()

    # Persist operational copy (all tables, mutated or not) + manifest + summary.
    if OPER.exists():
        shutil.rmtree(OPER)
    OPER.mkdir(parents=True)
    for name, df in inj.t.items():
        df.to_csv(OPER / f"{name}.csv", index=False)

    manifest = pd.DataFrame(inj.manifest)
    manifest.to_csv(OPER / "meta_exception_manifest.csv", index=False)
    manifest.to_csv(DATA_PROCESSED / "exception_manifest.csv", index=False)
    summary = pd.DataFrame(inj.summary)
    summary.to_csv(DATA_PROCESSED / "exception_summary.csv", index=False)

    log.info("Injected %d exception records across %d types", len(manifest), summary["exception_type"].nunique())
    for r in summary.itertuples(index=False):
        log.info("  %-26s eligible=%6d expected=%4d actual=%4d -> %s",
                 r.exception_type, r.eligible_records, r.expected_count, r.actual_count, r.affected_table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
