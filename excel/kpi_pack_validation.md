# Excel KPI Pack Validation

Validated workbook: `excel/logistics_kpi_pack.xlsx`

**Result:** 44/44 checks passed. The workbook was reviewed without changing analytical values.

## Workbook sheets and sources

| Worksheet | Rows | Columns | Source | Filter / freeze panes |
|---|---:|---:|---|---|
| Executive Summary | 28 | 5 | Live Phase 3 KPI and control views | `A6:E28` / `A7` |
| Shipment Exceptions | 1,684 | 38 | rpt_fact_shipment exception filter | `A6:AL1684` / `A7` |
| Carrier Scorecard | 16 | 27 | rpt_carrier_scorecard | `A6:AA16` / `A7` |
| Lane Scorecard | 784 | 34 | rpt_lane_scorecard | `A6:AH784` / `A7` |
| Freight Audit | 2,452 | 31 | rpt_fact_freight_audit exception filter | `A6:AE2452` / `A7` |
| Three-Way Match | 9,948 | 18 | v_three_way_match | `A6:R9948` / `A7` |
| Accrual Report | 10,330 | 14 | rpt_fact_accrual | `A6:N10330` / `A7` |
| Open Claims | 184 | 12 | rpt_fact_claim open filter | `A6:L184` / `A7` |
| Data Quality | 4,021 | 15 | rpt_fact_data_quality | `A6:O4021` / `A7` |
| Metric Definitions | 21 | 4 | Documented metric-definition registry | `A6:D21` / `A7` |

## Key reconciliation checks

| Check | Status | Detail |
|---|---|---|
| Expected worksheets | PASS | Executive Summary, Shipment Exceptions, Carrier Scorecard, Lane Scorecard, Freight Audit, Three-Way Match, Accrual Report, Open Claims, Data Quality, Metric Definitions |
| Executive Summary: filter | PASS | A6:E28 |
| Executive Summary: freeze panes | PASS | A7 |
| Executive Summary: populated | PASS | 28 rows x 5 columns |
| Shipment Exceptions: filter | PASS | A6:AL1684 |
| Shipment Exceptions: freeze panes | PASS | A7 |
| Shipment Exceptions: populated | PASS | 1684 rows x 38 columns |
| Carrier Scorecard: filter | PASS | A6:AA16 |
| Carrier Scorecard: freeze panes | PASS | A7 |
| Carrier Scorecard: populated | PASS | 16 rows x 27 columns |
| Lane Scorecard: filter | PASS | A6:AH784 |
| Lane Scorecard: freeze panes | PASS | A7 |
| Lane Scorecard: populated | PASS | 784 rows x 34 columns |
| Freight Audit: filter | PASS | A6:AE2452 |
| Freight Audit: freeze panes | PASS | A7 |
| Freight Audit: populated | PASS | 2452 rows x 31 columns |
| Three-Way Match: filter | PASS | A6:R9948 |
| Three-Way Match: freeze panes | PASS | A7 |
| Three-Way Match: populated | PASS | 9948 rows x 18 columns |
| Accrual Report: filter | PASS | A6:N10330 |
| Accrual Report: freeze panes | PASS | A7 |
| Accrual Report: populated | PASS | 10330 rows x 14 columns |
| Open Claims: filter | PASS | A6:L184 |
| Open Claims: freeze panes | PASS | A7 |
| Open Claims: populated | PASS | 184 rows x 12 columns |
| Data Quality: filter | PASS | A6:O4021 |
| Data Quality: freeze panes | PASS | A7 |
| Data Quality: populated | PASS | 4021 rows x 15 columns |
| Metric Definitions: filter | PASS | A6:D21 |
| Metric Definitions: freeze panes | PASS | A7 |
| Metric Definitions: populated | PASS | 21 rows x 4 columns |
| No formula-error tokens | PASS | [] |
| No placeholder rows | PASS | [] |
| Workbook intentionally contains no cell formulas | PASS | [] |
| Executive disclosure visible | PASS |  |
| Executive Summary is recruiter-readable | PASS |  |
| Shipment count reconciles | PASS | 10324 |
| Freight spend reconciles | PASS | 229333236.9 |
| Recoverable overcharge reconciles | PASS | 428053.23 |
| Currency formatting | PASS | "$"#,##0.00 |
| Percentage formatting | PASS | 0.00"%" |
| Carrier detail row count | PASS | 10 |
| Lane detail row count | PASS | 778 |
| Data-quality detail row count | PASS | 4015 |

## Refresh procedure

1. Run `python3 src/run_phase3.py` to refresh the database, reporting CSVs, and workbook.
2. Run `python3 src/run_phase4.py` to regenerate presentation assets and repeat workbook reconciliation.
3. Confirm the Phase 3 and Phase 4 validation reports contain no failed critical checks.

## Known limitations

- Shipment patterns are public-source derived; enterprise and finance records are deterministic simulations.
- Expected freight and accrual values are simulated planning/control baselines, not approved company budgets.
- The workbook contains values and conditional formatting rather than cell formulas; refresh is performed by the Python/SQL pipeline.
- The workbook is an Excel management pack, not a substitute for the manually built Power BI report described under `dashboard/`.
