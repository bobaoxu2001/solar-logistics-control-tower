# Two-Minute Recruiter Walkthrough

## What this project is

The **Solar Logistics Control Tower & Freight Audit System** is an end-to-end portfolio project for a Logistics Data Specialist role. It turns 10,324 public shipment-history records into a disclosed renewable-energy logistics scenario, then adds deterministic simulated ERP, TMS, WMS, carrier-contract, freight-settlement, and finance records.

The project shows how I connect operational shipment reporting to financial and data-quality controls—not just how I build a dashboard.

## Why it is relevant

It demonstrates the work logistics teams perform across shipment visibility, OTIF, Goods in Transit, carrier and lane performance, invoice validation, three-way matching, accruals, root-cause analysis, and management reporting. Every record retains lineage, and the clean baseline is kept separate from an exception-injected operational layer.

## Tools

Python, SQL, SQLite, PostgreSQL-compatible analytics, Power BI design and DAX, Excel, openpyxl, pandas, SQLAlchemy, and pytest.

## Six headline metrics

| Metric | Result |
|---|---:|
| Shipments analyzed | 10,324 |
| OTIF | 86.88% |
| Goods in Transit value | $32.49M |
| Detection recall | 99.37% |
| Critical-exception recall | 100% |
| Total modeled financial exposure | $2.48M |

The financial exposure is modeled within simulated enterprise records; it is not a claim of real savings.

The data-quality controls use rule-based deterministic SQL, not a machine-learning classifier. They achieved 99.37% recall, 100% critical-exception recall, and 54.94% precision against the intentionally injected manifest. The precision figure reflects valid downstream rate-card spillover and overlapping control findings outside the narrower truth set; those items remain visible for business review and are not automatically treated as confirmed billing errors.

## Three findings

1. Monthly OTIF fell 45.70 percentage points in the strongest deterioration case.
2. Thirty-two invoice rows for one carrier/status concentration account for $739,720.91 of modeled exposure.
3. Shared rate-card maintenance produced 1,839 high-severity detections and a clear procurement-control recommendation.

## Where to look

- Dashboard images: [`dashboard/screenshots/`](../dashboard/screenshots/)
- Executive preview: [`01_executive_overview.png`](../dashboard/screenshots/01_executive_overview.png)
- Excel reporting: [`excel/logistics_kpi_pack.xlsx`](../excel/logistics_kpi_pack.xlsx)
- Five-minute case study: [`documentation/project_case_study.md`](project_case_study.md)
- Ten-minute walkthrough: [`documentation/interview_demo_script.md`](interview_demo_script.md)

## Data disclosure

This project combines real public shipment history with deterministically simulated ERP, TMS, WMS, freight-settlement, and finance records. The simulated records represent information that would ordinarily be confidential.
