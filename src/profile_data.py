"""Profile the raw SCMS file and generate documentation artifacts.

Outputs:
  data/interim/raw_profile.csv                    — per-column profile
  data/samples/raw_sample_100.csv                 — first 100 raw rows (for reviewers)
  documentation/data_dictionary.xlsx              — raw data dictionary (+ excluded columns)
  documentation/source_to_target_mapping.xlsx     — STM from src/mappings.py

Usage:
    python src/profile_data.py
"""

from __future__ import annotations

import sys

import pandas as pd

from common import DATA_INTERIM, DATA_SAMPLES, DOCS_DIR, PROJECT_ROOT, ensure_dirs, get_logger, load_config
from mappings import EXCLUDED_RAW_COLUMNS, STG_SHIPMENT_MAPPING

log = get_logger("profile_data")

# Paraphrased from the original USAID SCMS data dictionary.
RAW_DEFINITIONS = {
    "ID": "Unique row identifier for the shipment line item.",
    "Project Code": "SCMS project the line item was procured under.",
    "PQ #": "Price-quote reference number.",
    "PO / SO #": "Purchase order / sales order reference.",
    "ASN/DN #": "Advanced shipment notice / delivery note reference.",
    "Country": "Destination country of the delivery.",
    "Managed By": "SCMS office managing the delivery.",
    "Fulfill Via": "Fulfillment channel: Direct Drop (vendor→client) or From RDC (regional distribution center).",
    "Vendor INCO Term": "Incoterm agreed with the vendor ('N/A - From RDC' when shipped from an RDC).",
    "Shipment Mode": "Transport mode (Air, Truck, Ocean, Air Charter).",
    "PQ First Sent to Client Date": "Date the price quote was first sent to the client.",
    "PO Sent to Vendor Date": "Date the purchase order was sent to the vendor.",
    "Scheduled Delivery Date": "Contractually scheduled delivery date.",
    "Delivered to Client Date": "Actual delivery date to the client.",
    "Delivery Recorded Date": "Date the delivery was recorded in the system.",
    "Product Group": "Product family (ARV, HRDT, ANTM, ACT, MRDT).",
    "Sub Classification": "Product sub-family (Adult, Pediatric, HIV test, ...).",
    "Vendor": "Vendor / supplier name.",
    "Item Description": "Free-text product description.",
    "Molecule/Test Type": "Active molecule or test type.",
    "Brand": "Brand name (or Generic).",
    "Dosage": "Dosage strength.",
    "Dosage Form": "Dosage form (tablet, capsule, test kit, ...).",
    "Unit of Measure (Per Pack)": "Units contained in one pack.",
    "Line Item Quantity": "Number of packs shipped on the line item.",
    "Line Item Value": "Extended value of the line item (USD).",
    "Pack Price": "Price per pack (USD).",
    "Unit Price": "Price per unit (USD).",
    "Manufacturing Site": "Manufacturing site the product shipped from (origin).",
    "First Line Designation": "Whether the product is a first-line treatment (Yes/No).",
    "Weight (Kilograms)": "Shipment line weight in kg; may reference another row ('See DN/ASN (ID#:n)') or read 'Weight Captured Separately'.",
    "Freight Cost (USD)": "Freight cost in USD; may reference another row, or read 'Freight Included in Commodity Cost' / 'Invoiced Separately'.",
    "Line Item Insurance (USD)": "Insurance cost allocated to the line item (USD).",
}


def infer_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "unknown"
    numeric = pd.to_numeric(non_null, errors="coerce")
    if numeric.notna().all():
        return "integer" if (numeric % 1 == 0).all() else "numeric"
    if numeric.notna().any():
        return "mixed (numeric + text sentinels)"
    parsed = pd.to_datetime(non_null, format="%d-%b-%y", errors="coerce")
    if parsed.notna().all():
        return "date (%d-%b-%y)"
    if parsed.notna().any():
        return "mixed (date + text sentinels)"
    return "text"


def build_profile(df: pd.DataFrame) -> pd.DataFrame:
    target_by_source: dict[str, list[str]] = {}
    rule_by_source: dict[str, list[str]] = {}
    for tgt, src, _cls, _typ, rule in STG_SHIPMENT_MAPPING:
        for s in [c.strip() for c in src.split("+")]:
            target_by_source.setdefault(s, []).append(tgt)
            rule_by_source.setdefault(s, []).append(rule)

    rows = []
    for col in df.columns:
        s = df[col]
        if col in EXCLUDED_RAW_COLUMNS:
            target, rule = "(not modeled)", EXCLUDED_RAW_COLUMNS[col]
        else:
            target = ", ".join(dict.fromkeys(target_by_source.get(col, ["(not modeled)"])))
            rule = " | ".join(dict.fromkeys(rule_by_source.get(col, [""])))
        rows.append({
            "original_column": col,
            "original_definition": RAW_DEFINITIONS.get(col, ""),
            "inferred_type": infer_type(s),
            "missing_pct": round(s.isna().mean() * 100, 2),
            "distinct_values": s.nunique(),
            "top_values": "; ".join(f"{v} ({c})" for v, c in s.value_counts().head(3).items()),
            "target_model_column": target,
            "transformation_rule": rule,
        })
    return pd.DataFrame(rows)


def main() -> int:
    cfg = load_config()
    ensure_dirs()
    raw_path = PROJECT_ROOT / cfg["source_dataset"]["local_path"]
    if not raw_path.exists():
        log.error("Raw file missing — run src/download_data.py first.")
        return 1

    df = pd.read_csv(raw_path, encoding="utf-8-sig", dtype=str)
    log.info("Loaded raw file: %d rows x %d columns", *df.shape)

    profile = build_profile(df)
    profile.to_csv(DATA_INTERIM / "raw_profile.csv", index=False)
    df.head(100).to_csv(DATA_SAMPLES / "raw_sample_100.csv", index=False)

    # documentation/data_dictionary.xlsx
    DOCS_DIR.mkdir(exist_ok=True)
    excluded = pd.DataFrame(
        [{"original_column": k, "exclusion_reason": v} for k, v in EXCLUDED_RAW_COLUMNS.items()]
    )
    with pd.ExcelWriter(DOCS_DIR / "data_dictionary.xlsx", engine="openpyxl") as xw:
        profile.to_excel(xw, sheet_name="raw_data_dictionary", index=False)
        excluded.to_excel(xw, sheet_name="excluded_columns", index=False)

    # documentation/source_to_target_mapping.xlsx
    stm = pd.DataFrame(
        STG_SHIPMENT_MAPPING,
        columns=["target_column", "source_column", "classification", "target_type", "transformation_rule"],
    )
    stm.insert(0, "target_table", "stg_shipment")
    with pd.ExcelWriter(DOCS_DIR / "source_to_target_mapping.xlsx", engine="openpyxl") as xw:
        stm.to_excel(xw, sheet_name="stg_shipment", index=False)

    log.info("Wrote raw_profile.csv, raw_sample_100.csv, data_dictionary.xlsx, source_to_target_mapping.xlsx")

    # Console summary for the analyst
    key_cols = ["Shipment Mode", "Weight (Kilograms)", "Freight Cost (USD)"]
    for c in key_cols:
        nn = pd.to_numeric(df[c], errors="coerce").notna().sum() if "(" in c else df[c].notna().sum()
        log.info("%-22s non-missing/numeric: %d / %d", c, nn, len(df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
