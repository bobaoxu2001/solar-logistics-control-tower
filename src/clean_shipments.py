"""Transform the raw SCMS file into the stg_shipment staging table.

Every transformation is specified in src/mappings.py and documented in
documentation/source_to_target_mapping.xlsx. Nothing is silently dropped:
rows that fail hard validation go to data/processed/rejected_records.csv
with a rejection reason.

Outputs:
  data/processed/stg_shipment.csv
  data/processed/rejected_records.csv
  data/samples/stg_shipment_sample_100.csv

Usage:
    python src/clean_shipments.py
"""

from __future__ import annotations

import re
import sys

import numpy as np
import pandas as pd

from common import DATA_PROCESSED, DATA_SAMPLES, PROJECT_ROOT, ensure_dirs, get_logger, load_config

log = get_logger("clean_shipments")


def parse_date(series: pd.Series, sentinels: list[str], fmt: str) -> pd.Series:
    s = series.where(~series.isin(sentinels))
    return pd.to_datetime(s, format=fmt, errors="coerce")


def resolve_references(
    df: pd.DataFrame, col: str, sentinel_labels: dict[str, str], ref_pattern: str
) -> tuple[pd.Series, pd.Series]:
    """Resolve 'See DN/ASN (ID#:n)' cross-references in a numeric column.

    Returns (numeric_value, provenance) where provenance is one of:
      direct | resolved_reference | missing_unresolved_reference | <sentinel label>
    """
    raw = df[col]
    value = pd.to_numeric(raw, errors="coerce")
    source = pd.Series(np.where(value.notna(), "direct", ""), index=df.index, dtype="object")

    # Named sentinels ("Weight Captured Separately", ...) → NULL + label
    for sentinel, label in sentinel_labels.items():
        mask = raw.eq(sentinel)
        source[mask] = label

    # Cross-references: look up the referenced row's own numeric value (one hop;
    # in this dataset referenced rows always carry a direct numeric value).
    ref_id = raw.str.extract(ref_pattern, expand=False).astype("Int64")
    direct_by_id = pd.Series(value.values, index=df["ID"].astype("int64").values)
    resolvable = ref_id.notna()
    resolved = pd.Series(
        direct_by_id.reindex(ref_id[resolvable].astype("int64")).values,
        index=df.index[resolvable],
    )
    ok = resolved.notna()
    value.loc[resolved.index[ok]] = resolved[ok]
    source.loc[resolved.index[ok]] = "resolved_reference"
    source.loc[resolved.index[~ok]] = "missing_unresolved_reference"
    return value, source


def map_product_category(df: pd.DataFrame, category_map: dict[str, str]) -> pd.Series:
    def lookup(group: str, sub: str) -> str | None:
        return category_map.get(f"{group}|{sub}") or category_map.get(f"{group}|*")

    return pd.Series(
        [lookup(g, s) for g, s in zip(df["Product Group"], df["Sub Classification"])],
        index=df.index,
    )


def main() -> int:
    cfg = load_config()
    clean_cfg = cfg["cleaning"]
    fmt = clean_cfg["date_format"]
    sentinels = clean_cfg["date_sentinels"]
    ensure_dirs()

    raw_path = PROJECT_ROOT / cfg["source_dataset"]["local_path"]
    df = pd.read_csv(raw_path, encoding="utf-8-sig", dtype=str)
    log.info("Loaded raw file: %d rows", len(df))

    # --- Hard validation (rejects, never silent drops) ---------------------
    rejects = []
    dup_mask = df["ID"].duplicated(keep=False)
    if dup_mask.any():
        rejects.append((df[dup_mask], "duplicate ID"))
        df = df[~dup_mask]
    for col, reason in [
        ("Scheduled Delivery Date", "unparseable scheduled delivery date"),
        ("Delivered to Client Date", "unparseable actual delivery date"),
    ]:
        bad = pd.to_datetime(df[col], format=fmt, errors="coerce").isna()
        if bad.any():
            rejects.append((df[bad], reason))
            df = df[~bad]
    qty = pd.to_numeric(df["Line Item Quantity"], errors="coerce")
    bad = qty.isna() | (qty <= 0)
    if bad.any():
        rejects.append((df[bad], "non-positive or non-numeric quantity"))
        df = df[~bad]

    # --- Transformations ---------------------------------------------------
    out = pd.DataFrame(index=df.index)
    out["source_record_id"] = df["ID"].astype("int64")
    out["po_so_number"] = df["PO / SO #"]
    out["asn_dn_number"] = df["ASN/DN #"]
    out["project_code"] = df["Project Code"]
    out["destination_country"] = df["Country"]
    out["managed_by"] = df["Managed By"]
    out["fulfill_via"] = df["Fulfill Via"]
    out["incoterm"] = df["Vendor INCO Term"].where(df["Vendor INCO Term"] != "N/A - From RDC")
    out["shipment_mode_raw"] = df["Shipment Mode"]
    out["shipment_mode"] = df["Shipment Mode"].map(clean_cfg["shipment_mode_map"])
    out["missing_mode_flag"] = df["Shipment Mode"].isna().astype(int)

    out["pq_first_sent_date"] = parse_date(df["PQ First Sent to Client Date"], sentinels, fmt)
    out["po_sent_date"] = parse_date(df["PO Sent to Vendor Date"], sentinels, fmt)
    out["scheduled_delivery_date"] = pd.to_datetime(df["Scheduled Delivery Date"], format=fmt)
    out["actual_delivery_date"] = pd.to_datetime(df["Delivered to Client Date"], format=fmt)
    out["delivery_recorded_date"] = pd.to_datetime(df["Delivery Recorded Date"], format=fmt)

    out["product_group_raw"] = df["Product Group"]
    out["sub_classification_raw"] = df["Sub Classification"]
    out["product_category"] = map_product_category(df, cfg["adaptation"]["product_category_map"])
    unmapped = out["product_category"].isna()
    if unmapped.any():
        log.warning("%d rows have no product-category mapping — check config", unmapped.sum())

    out["vendor_name"] = df["Vendor"]
    out["item_description_raw"] = df["Item Description"]
    out["manufacturing_site"] = df["Manufacturing Site"]
    out["first_line_designation"] = df["First Line Designation"].eq("Yes").astype(int)
    out["unit_of_measure_per_pack"] = pd.to_numeric(df["Unit of Measure (Per Pack)"]).astype("int64")
    out["line_item_quantity"] = pd.to_numeric(df["Line Item Quantity"]).astype("int64")
    out["line_item_value_usd"] = pd.to_numeric(df["Line Item Value"])
    out["pack_price_usd"] = pd.to_numeric(df["Pack Price"])
    out["unit_price_usd"] = pd.to_numeric(df["Unit Price"])

    ref_pattern = clean_cfg["reference_pattern"]
    out["weight_kg"], out["weight_source"] = resolve_references(
        df, "Weight (Kilograms)",
        {s: "missing_captured_separately" for s in clean_cfg["weight_sentinels"]},
        ref_pattern,
    )
    out["freight_cost_usd"], out["freight_cost_source"] = resolve_references(
        df, "Freight Cost (USD)",
        {
            "Freight Included in Commodity Cost": "missing_included_in_commodity",
            "Invoiced Separately": "missing_invoiced_separately",
        },
        ref_pattern,
    )
    out["line_item_insurance_usd"] = pd.to_numeric(df["Line Item Insurance (USD)"], errors="coerce")

    shift = pd.DateOffset(years=cfg["adaptation"]["date_shift_years"])
    out["reporting_scheduled_delivery_date"] = out["scheduled_delivery_date"] + shift
    out["reporting_actual_delivery_date"] = out["actual_delivery_date"] + shift

    # --- Write outputs ------------------------------------------------------
    out.to_csv(DATA_PROCESSED / "stg_shipment.csv", index=False)
    out.head(100).to_csv(DATA_SAMPLES / "stg_shipment_sample_100.csv", index=False)

    if rejects:
        rej = pd.concat(
            [chunk.assign(rejection_reason=reason) for chunk, reason in rejects]
        )
    else:
        rej = pd.DataFrame(columns=list(df.columns) + ["rejection_reason"])
    rej.to_csv(DATA_PROCESSED / "rejected_records.csv", index=False)

    log.info("stg_shipment: %d rows | rejected: %d rows", len(out), len(rej))
    log.info("weight_source:\n%s", out["weight_source"].value_counts().to_string())
    log.info("freight_cost_source:\n%s", out["freight_cost_source"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
