"""Phase 2 — extend the Excel documentation with the enterprise model.

Appends/refreshes sheets on:
  documentation/data_dictionary.xlsx        (phase2_tables, phase2_columns)
  documentation/source_to_target_mapping.xlsx (phase2_derivation)

Reads the generated clean CSVs so column lists and row counts are always in sync
with the pipeline. Idempotent (sheets are replaced).

Usage:
    python src/build_phase2_docs.py
"""

from __future__ import annotations

import sys

import pandas as pd

from common import DATA_PROCESSED, DOCS_DIR, get_logger

log = get_logger("build_phase2_docs")
CLEAN = DATA_PROCESSED / "clean"

# table -> (layer, provenance_basis, derivation_rule)
TABLE_DOC = {
    "dim_location": ("dimension", "PUBLIC/DERIVED",
                     "Origins from manufacturing_site; destinations one DC per destination_country; "
                     "warehouse locations simulated. Coordinates left NULL (never fabricated)."),
    "dim_location_xref": ("mapping", "DERIVED",
                          "Preserves each raw location string and how it mapped to a location_id (match_method)."),
    "dim_hts_code": ("dimension", "SIMULATED",
                     "One illustrative HS-prefixed code per product category. NOT official US HTS (code_type)."),
    "dim_product": ("dimension", "SIMULATED",
                    "5 SKUs per renewable-energy category; unit_weight/value seeded from the observed "
                    "per-unit source distribution (median of weight/qty, value/qty)."),
    "dim_business_partner": ("dimension", "DERIVED/SIMULATED",
                             "Unified registry: suppliers (real vendors), carriers, brokers, customers."),
    "dim_supplier": ("dimension", "DERIVED",
                     "One per real source vendor; location = most-used manufacturing site."),
    "dim_warehouse": ("dimension", "SIMULATED", "5 regional DCs (config); location FK to dim_location."),
    "dim_carrier": ("dimension", "SIMULATED", "12 fictional carriers across all modes (config)."),
    "dim_lane": ("dimension", "DERIVED",
                 "Distinct (origin, destination, mode) combinations; standard_transit_days = mode/region "
                 "standard (source has no departure timestamp). estimated_distance NULL (not measurable)."),
    "dim_rate_card": ("dimension", "SIMULATED",
                      "One rate per (pool carrier, lane); rate_per_kg ~ observed mode freight/kg with "
                      "deterministic carrier spread; single wide effective window (no overlap)."),
    "fact_purchase_order": ("fact", "DERIVED",
                            "Groups shipment lines sharing a source PO reference; else one derived PO per line."),
    "fact_shipment": ("fact", "DERIVED",
                      "One per staged shipment (source_record_id lineage). Real value/qty/delivery preserved; "
                      "ship dates derived from mode/lane transit (ship_date_derived_flag=1)."),
    "fact_shipment_milestone": ("fact", "SIMULATED",
                                "Mode-aware milestone templates; timestamps reconcile to shipment dates."),
    "fact_freight_invoice": ("fact", "SIMULATED",
                             "One per delivered shipment; charges from the applicable rate card (+small "
                             "rating noise within audit tolerance)."),
    "fact_invoice_line": ("fact", "SIMULATED", "BASE_FREIGHT / FUEL_SURCHARGE / ACCESSORIAL / TAX lines; sum to total."),
    "fact_accessorial_charge": ("fact", "SIMULATED",
                                "Low-frequency, mode-plausible charges; clean baseline all contractually allowed."),
    "fact_proof_of_delivery": ("fact", "SIMULATED", "One per delivered shipment; generic role-based recipient (no PII)."),
    "fact_claim": ("fact", "SIMULATED",
                   "Risk-weighted legitimate claims (late/high-value/ocean more likely)."),
    "fact_carrier_capacity": ("fact", "SIMULATED",
                              "Monthly per carrier x lane; utilization <=100% with seasonal variation."),
    "fact_invoice_approval": ("fact", "SIMULATED",
                              "4-stage workflow; chronological; paid => approved."),
    "fact_accrual": ("fact", "DERIVED",
                     "Per shipment by accounting period; expected freight vs received invoice; "
                     "RELEASED only when invoice received & approved."),
}


def main() -> int:
    if not (CLEAN / "fact_shipment.csv").exists():
        log.error("Run src/run_phase2.py first."); return 1

    table_rows, column_rows, deriv_rows = [], [], []
    for tbl, (layer, prov, rule) in TABLE_DOC.items():
        df = pd.read_csv(CLEAN / f"{tbl}.csv")
        classes = df["data_class"].value_counts().to_dict() if "data_class" in df else {}
        table_rows.append({"table": tbl, "layer": layer, "provenance": prov,
                           "row_count": len(df), "data_class_breakdown": str(classes),
                           "description": rule})
        for col in df.columns:
            column_rows.append({"table": tbl, "column": col, "dtype": str(df[col].dtype),
                                "null_pct": round(df[col].isna().mean() * 100, 2)})
        deriv_rows.append({"target_table": tbl, "layer": layer, "classification": prov,
                           "derivation_rule": rule})

    dd_path = DOCS_DIR / "data_dictionary.xlsx"
    with pd.ExcelWriter(dd_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as xw:
        pd.DataFrame(table_rows).to_excel(xw, sheet_name="phase2_tables", index=False)
        pd.DataFrame(column_rows).to_excel(xw, sheet_name="phase2_columns", index=False)

    stm_path = DOCS_DIR / "source_to_target_mapping.xlsx"
    with pd.ExcelWriter(stm_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as xw:
        pd.DataFrame(deriv_rows).to_excel(xw, sheet_name="phase2_derivation", index=False)

    log.info("Updated data_dictionary.xlsx (phase2_tables, phase2_columns) and "
             "source_to_target_mapping.xlsx (phase2_derivation): %d tables, %d columns",
             len(table_rows), len(column_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
