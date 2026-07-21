# Interview Chart Source Map

All charts are standalone, high-resolution PNG files generated from the verified Phase 3 SQLite views. Titles state the business question; footers state the source and public-versus-simulated disclosure.

| Chart | Analytical question | Form | Source | Supported takeaway |
|---|---|---|---|---|
| [`monthly_otif_trend.png`](charts/monthly_otif_trend.png) | When did service deteriorate? | Line, 36 monthly points | `v_kpi_otif_by_month` | Strongest monthly decline was 45.70 pp |
| [`carrier_scorecard.png`](charts/carrier_scorecard.png) | Which eligible carrier ranks highest? | Ranked horizontal bars | `rpt_carrier_scorecard` | Meridian ranks first at 68.99/100 |
| [`lane_risk_matrix.png`](charts/lane_risk_matrix.png) | Which sufficient-volume lanes combine service and cost risk? | Scatter, log cost axis | `rpt_lane_scorecard` | LANE00575 is a sufficient-volume multi-flag lane |
| [`freight_audit_exposure_waterfall.png`](charts/freight_audit_exposure_waterfall.png) | What composes modeled exposure? | Additive waterfall | `v_audit_recoverable_summary` | Duplicate-payment exposure is the largest component |
| [`three_way_match_distribution.png`](charts/three_way_match_distribution.png) | How many invoice decisions can proceed or stop? | Horizontal bars | `v_three_way_match` | 219 block payment; 2,233 review required |
| [`accrual_aging.png`](charts/accrual_aging.png) | How is the open planning balance aged? | Horizontal bars | `rpt_fact_accrual` | $5.10M remains open; future-modeled dates age at zero |
| [`data_quality_detection_performance.png`](charts/data_quality_detection_performance.png) | Which manifested exception types are detected reliably? | Ranked recall bars with precision labels | `rpt_dq_detection_performance` | Overall recall 99.37%; critical recall 100% |
| [`exception_severity_distribution.png`](charts/exception_severity_distribution.png) | Where is the control workload concentrated? | Horizontal bars | `rpt_fact_data_quality` | High severity accounts for 2,279 detections |

The machine-readable reconciliation is in [`documentation/charts/chart_source_reconciliation.csv`](charts/chart_source_reconciliation.csv).
