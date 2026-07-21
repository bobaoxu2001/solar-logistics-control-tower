# Phase 2 Summary — Enterprise Logistics Data Simulation

_Generated 2026-07-21 06:23 UTC. Deterministic under `random_seed` in config/project_config.yaml._

## Input

- Cleaned public shipment lines (Phase 1): **10,324**


## Output row counts (clean baseline → operational)

| Table | Clean baseline | Operational (post-injection) |
|---|--:|--:|
| dim_location | 136 | 136 |
| dim_location_xref | 131 | 131 |
| dim_hts_code | 4 | 4 |
| dim_product | 20 | 20 |
| dim_business_partner | 128 | 128 |
| dim_supplier | 73 | 73 |
| dim_warehouse | 5 | 5 |
| dim_carrier | 12 | 12 |
| dim_lane | 785 | 785 |
| dim_rate_card | 2,311 | 2,311 |
| fact_purchase_order | 6,233 | 6,233 |
| fact_shipment | 10,324 | 10,324 |
| fact_shipment_milestone | 87,046 | 87,046 |
| fact_freight_invoice | 10,012 | 9,942 |
| fact_invoice_line | 21,389 | 20,755 |
| fact_accessorial_charge | 1,432 | 1,448 |
| fact_proof_of_delivery | 10,012 | 9,612 |
| fact_claim | 291 | 411 |
| fact_carrier_capacity | 7,200 | 7,200 |
| fact_invoice_approval | 39,989 | 38,789 |
| fact_accrual | 10,324 | 10,324 |

## Clean baseline validation

- Checks run: **60** | Failures: **0** | Critical failures: **0**

- Overall min pass rate: **1.0000**  (✓ clean baseline is consistent)


## Injected exceptions (operational layer)

- Total injected records: **2,220** across **19** types.

| Exception type | Eligible | Configured rate | Expected | Actual | Affected table | Severity |
|---|--:|--:|--:|--:|---|---|
| missing_carrier_id | 10,012 | 0.010 | 100 | 100 | fact_shipment | HIGH |
| invalid_lane | 10,012 | 0.008 | 80 | 80 | fact_shipment | HIGH |
| delivery_before_ship | 10,012 | 0.004 | 40 | 40 | fact_shipment | CRITICAL |
| over_delivery | 10,012 | 0.008 | 80 | 80 | fact_shipment | MEDIUM |
| partial_delivery | 10,012 | 0.020 | 200 | 200 | fact_shipment | MEDIUM |
| missing_pod | 10,012 | 0.040 | 400 | 400 | fact_proof_of_delivery | MEDIUM |
| shipment_without_invoice | 10,012 | 0.030 | 300 | 300 | fact_freight_invoice | MEDIUM |
| missing_customs_doc | 7,194 | 0.015 | 108 | 108 | fact_shipment_milestone | HIGH |
| damaged_shipment_claim | 10,012 | 0.012 | 120 | 120 | fact_claim | MEDIUM |
| invoice_carrier_mismatch | 10,012 | 0.010 | 100 | 100 | fact_freight_invoice | HIGH |
| incorrect_fuel_surcharge | 10,012 | 0.020 | 200 | 200 | fact_freight_invoice | MEDIUM |
| incorrect_currency | 10,012 | 0.006 | 60 | 60 | fact_freight_invoice | MEDIUM |
| expired_rate_card | 10,012 | 0.015 | 150 | 150 | fact_freight_invoice | HIGH |
| duplicate_invoice | 10,012 | 0.012 | 120 | 120 | fact_freight_invoice | CRITICAL |
| duplicate_payment_risk | 10,012 | 0.005 | 50 | 50 | fact_freight_invoice | CRITICAL |
| invoice_without_shipment | 10,012 | 0.006 | 60 | 60 | fact_freight_invoice | CRITICAL |
| unauthorized_detention | 3,183 | 0.015 | 48 | 47 | fact_accessorial_charge | HIGH |
| excessive_demurrage | 377 | 0.010 | 4 | 4 | fact_accessorial_charge | HIGH |
| missing_hts_code | 20 | 0.020 | 1 | 1 | dim_product | MEDIUM |

## Reproducibility

- All IDs are deterministic; all stochastic draws are seeded per-record. Re-running produces byte-identical CSVs and never duplicates rows.

- Clean baseline lives in `data/processed/clean/`; the exception-injected operational layer in `data/processed/operational/`; every change is recorded in `data/processed/exception_manifest.csv`.
