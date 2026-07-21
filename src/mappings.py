"""Source-to-target mapping for the SCMS raw file → stg_shipment staging table.

This module is the single source of truth for the mapping. It is consumed by:
  * clean_shipments.py  — to drive the actual transformation
  * profile_data.py     — to export documentation/source_to_target_mapping.xlsx

classification values:
  PUBLIC   — value comes straight from the public source file (possibly parsed)
  DERIVED  — computed from public values by a documented, deterministic rule
  SIMULATED— will be generated in Phase 2 (listed here only when the staging
             table carries a placeholder for it)
"""

# One row per TARGET column in stg_shipment.
# original definitions paraphrased from the USAID SCMS data dictionary.
STG_SHIPMENT_MAPPING = [
    # target_column, source_column, classification, target_type, rule
    ("source_record_id", "ID", "PUBLIC", "INTEGER",
     "Copied unchanged. Primary lineage key back to the raw file."),
    ("po_so_number", "PO / SO #", "PUBLIC", "TEXT",
     "Copied unchanged (purchase order / sales order reference)."),
    ("asn_dn_number", "ASN/DN #", "PUBLIC", "TEXT",
     "Copied unchanged (advanced shipment notice / delivery note)."),
    ("project_code", "Project Code", "PUBLIC", "TEXT", "Copied unchanged."),
    ("destination_country", "Country", "PUBLIC", "TEXT",
     "Copied unchanged; becomes destination location in dim_location."),
    ("managed_by", "Managed By", "PUBLIC", "TEXT", "Copied unchanged."),
    ("fulfill_via", "Fulfill Via", "PUBLIC", "TEXT",
     "Copied unchanged. 'From RDC' rows have no vendor PO date by design."),
    ("incoterm", "Vendor INCO Term", "PUBLIC", "TEXT",
     "'N/A - From RDC' → NULL (not an Incoterm); otherwise copied."),
    ("shipment_mode_raw", "Shipment Mode", "PUBLIC", "TEXT", "Copied unchanged."),
    ("shipment_mode", "Shipment Mode", "DERIVED", "TEXT",
     "Normalized via cleaning.shipment_mode_map (AIR/AIR_CHARTER/TRUCK/OCEAN); "
     "NULL kept as NULL and flagged missing_mode_flag=1."),
    ("pq_first_sent_date", "PQ First Sent to Client Date", "PUBLIC", "DATE",
     "Parsed %d-%b-%y; sentinels ('Pre-PQ Process','Date Not Captured') → NULL."),
    ("po_sent_date", "PO Sent to Vendor Date", "PUBLIC", "DATE",
     "Parsed %d-%b-%y; sentinels ('N/A - From RDC','Date Not Captured') → NULL."),
    ("scheduled_delivery_date", "Scheduled Delivery Date", "PUBLIC", "DATE",
     "Parsed %d-%b-%y (100% parseable in source)."),
    ("actual_delivery_date", "Delivered to Client Date", "PUBLIC", "DATE",
     "Parsed %d-%b-%y (100% parseable in source)."),
    ("delivery_recorded_date", "Delivery Recorded Date", "PUBLIC", "DATE",
     "Parsed %d-%b-%y (100% parseable in source)."),
    ("product_group_raw", "Product Group", "PUBLIC", "TEXT", "Copied unchanged."),
    ("sub_classification_raw", "Sub Classification", "PUBLIC", "TEXT", "Copied unchanged."),
    ("product_category", "Product Group + Sub Classification", "DERIVED", "TEXT",
     "Deterministic remap to the SunGrid solar catalog via "
     "adaptation.product_category_map (e.g. 'ARV|Adult' → SOLAR_MODULE). "
     "Real shipment patterns preserved; product identity adapted."),
    ("vendor_name", "Vendor", "PUBLIC", "TEXT", "Copied unchanged."),
    ("item_description_raw", "Item Description", "PUBLIC", "TEXT",
     "Copied unchanged; retained for lineage only."),
    ("manufacturing_site", "Manufacturing Site", "PUBLIC", "TEXT",
     "Copied unchanged; becomes origin location in dim_location."),
    ("first_line_designation", "First Line Designation", "PUBLIC", "BOOLEAN",
     "'Yes'/'No' → 1/0."),
    ("unit_of_measure_per_pack", "Unit of Measure (Per Pack)", "PUBLIC", "INTEGER",
     "Cast to integer."),
    ("line_item_quantity", "Line Item Quantity", "PUBLIC", "INTEGER",
     "Cast to integer. Serves as planned quantity baseline; delivered-quantity "
     "deviations are injected only in Phase 2 exception simulation."),
    ("line_item_value_usd", "Line Item Value", "PUBLIC", "NUMERIC(14,2)",
     "Cast to numeric USD."),
    ("pack_price_usd", "Pack Price", "PUBLIC", "NUMERIC(12,2)", "Cast to numeric USD."),
    ("unit_price_usd", "Unit Price", "PUBLIC", "NUMERIC(12,4)", "Cast to numeric USD."),
    ("weight_kg", "Weight (Kilograms)", "PUBLIC", "NUMERIC(12,2)",
     "Numeric values cast directly. 'See DN/ASN (ID#:n)' cross-references "
     "resolved by looking up row n's weight. Remaining sentinels → NULL."),
    ("weight_source", "Weight (Kilograms)", "DERIVED", "TEXT",
     "Provenance flag: direct | resolved_reference | missing_captured_separately | "
     "missing_unresolved_reference."),
    ("freight_cost_usd", "Freight Cost (USD)", "PUBLIC", "NUMERIC(12,2)",
     "Numeric values cast directly. 'See DN/ASN (ID#:n)' cross-references "
     "resolved by lookup. Remaining sentinels → NULL."),
    ("freight_cost_source", "Freight Cost (USD)", "DERIVED", "TEXT",
     "Provenance flag: direct | resolved_reference | missing_included_in_commodity | "
     "missing_invoiced_separately | missing_unresolved_reference."),
    ("line_item_insurance_usd", "Line Item Insurance (USD)", "PUBLIC", "NUMERIC(12,2)",
     "Cast to numeric; blank → NULL."),
    ("reporting_scheduled_delivery_date", "Scheduled Delivery Date", "DERIVED", "DATE",
     "scheduled_delivery_date + adaptation.date_shift_years (constant shift so "
     "dashboards show a recent window; intervals preserved)."),
    ("reporting_actual_delivery_date", "Delivered to Client Date", "DERIVED", "DATE",
     "actual_delivery_date + adaptation.date_shift_years."),
]

# Raw columns intentionally NOT carried into stg_shipment (kept in the raw file
# and the data dictionary; excluded from the model with the reason recorded).
EXCLUDED_RAW_COLUMNS = {
    "PQ #": "Internal price-quote id; superseded by PO / SO # for matching.",
    "Molecule/Test Type": "Pharma-specific; not meaningful after solar adaptation. Retained in raw only.",
    "Brand": "Pharma-specific; retained in raw only.",
    "Dosage": "Pharma-specific (16.8% missing); retained in raw only.",
    "Dosage Form": "Pharma-specific; retained in raw only.",
}
