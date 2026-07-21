# Solar Logistics Control Tower & Freight Audit System

A portfolio logistics-control system that combines public shipment history with simulated ERP, TMS, WMS, carrier-contract, freight-settlement, and finance data to demonstrate operational reporting, freight controls, and management decision support.

> **Data disclosure.** This project combines real public shipment history with deterministically simulated ERP, TMS, WMS, freight-settlement, and finance records. The simulated records represent information that would ordinarily be confidential.

## Key outcomes

| Shipments analyzed | OTIF | Goods in Transit | Control recall | Critical recall | Modeled financial exposure |
|---:|---:|---:|---:|---:|---:|
| **10,324** | **86.88%** | **$32.49M** | **99.37%** | **100%** | **$2.48M** |

The $2.48M financial-control exposure is modeled within simulated enterprise records. It is not a claim of realized savings or a real-company recovery.

**Business capabilities demonstrated:** shipment control tower · OTIF and transit performance · freight invoice audit · three-way matching · accrual reporting · carrier scorecard · data-quality controls · management reporting

**Technology:** Python · SQL · PostgreSQL-compatible analytics · SQLite · Power BI · DAX · Excel · openpyxl · pytest

**Start here:** choose a [2-minute, 5-minute, or 10-minute portfolio viewing path](PORTFOLIO_GUIDE.md).

## Executive dashboard preview

![Power BI dashboard design mockup generated from project reporting outputs](dashboard/screenshots/01_executive_overview.png)

The static preview is generated from the same reconciled reporting outputs used by the Excel pack. It is a design mockup—not a fabricated Power BI screenshot or `.pbix` file.

## Business problem

Renewable-energy logistics teams need a unified view of shipment execution, proof of delivery, carrier performance, contractual freight, invoice exceptions, and month-end accruals. In practice, those signals are split across operational and finance systems. This project demonstrates how a Logistics Data Specialist can turn fragmented records into traceable controls and concise management reporting.

The workflow supports three decisions:

1. Which shipments, carriers, and lanes need operational attention?
2. Which freight invoices can be approved, reviewed, or blocked?
3. Which data-quality and master-data controls should be corrected first?

## Architecture

![Project architecture from public shipment source to reporting](documentation/diagrams/project_architecture.png)

The pipeline preserves a clean baseline separately from an operational exception layer. Controlled exceptions are injected only after the baseline passes 60 validation checks, then reconciled to a manifest so the detection framework can be measured rather than assumed.

See [the detailed architecture and assumption log](documentation/project_architecture.md) and [the Power BI data model](dashboard/data_model.md).

## Data source and disclosure

| Layer | Source | Classification |
|---|---|---|
| Shipment lines (10,324) | USAID *Supply Chain Shipment Pricing Data* public history, acquired from a mirror and checked against pinned SHA-256 `918b992d…` | PUBLIC |
| Solar catalog remap, lanes, reporting dates | Deterministic mappings with record-level lineage | DERIVED |
| Carriers, rates, invoices, milestones, PODs, claims, approvals, accruals | Seeded Python generation derived from shipment patterns | SIMULATED |

The public source originally records pharmaceutical shipments. Dates, modes, weights, values, freight costs, origins, and destinations are retained as shipment patterns; product identity is deterministically remapped to a renewable-energy catalog. Original product fields and `source_record_id` remain available for lineage. No data is presented as coming from a real solar company.

The repository preserves the publisher attribution, original portal identifier, mirror disclosure, and pinned checksum. The exact reuse terms were not independently verified from the current repository evidence; users should review the original source terms before redistributing the dataset. This portfolio is not affiliated with USAID, the mirror maintainers, any target employer, or any real solar company.

## Analytical modules

| Module | What it answers | Verified output |
|---|---|---:|
| Shipment control tower | What is delivered, late, partial, overdue, or still in transit? | 10,012 delivered; 312 GIT |
| OTIF and transit | Are shipments arriving by plan and in full? | 86.88% OTIF; 5.56 average transit days |
| Freight audit | Does each invoice reconcile to shipment, rate, fuel, currency, and accessorial evidence? | $428,053.23 modeled overcharge |
| Three-way match | Can PO, shipment, and invoice proceed to payment? | 219 block-payment decisions |
| Accrual reporting | What expected freight remains open or uninvoiced? | $5,101,238.49 open accrual |
| Carrier and lane scorecards | Which partners and lanes need action? | Meridian 68.99/100; LANE00575 highlighted |
| Data-quality controls | Do the rules detect the controlled truth set? | 99.37% recall; 100% critical recall |
| Root-cause evidence | Where is deterioration or exposure concentrated? | Three evidence-led cases |

## Freight-audit workflow

![Freight audit workflow from shipment and rate inputs to payment decision](documentation/diagrams/freight_audit_workflow.png)

The expected-charge engine selects an effective carrier-lane rate, enforces the minimum charge, computes fuel, includes only permitted and supported accessorials, and adds tax. Missing or expired rates remain unknown instead of becoming false zero-dollar expectations. Invoice comparison then classifies variance and feeds approve, review, or block decisions.

## Data-quality validation

![Data-quality manifest validation workflow](documentation/diagrams/data_quality_validation.png)

The framework reconciles detected record IDs to 2,220 manifested exceptions by type. It achieved 99.37% overall recall and 100% critical recall. Precision is 54.94% because shared rate-card spillover and overlapping control rules expose additional legitimate issues beyond the injected manifest; those detections are not hidden or forced into the truth set.

## Root-cause findings

1. **Monthly OTIF deterioration:** OTIF fell from 90.14% to 44.44%, a 45.70-percentage-point change, with 29 late shipments and $7.28M of late shipment value in the affected month.
2. **Freight invoice concentration:** 32 VoltLine Express Air invoice rows account for $739,720.91 of modeled exposure, primarily duplicate-payment risk.
3. **Shared rate-card control:** 1,839 high-severity detections concentrate in expired shared rate cards; all 124 altered cards are detected, while invoice-level recall is 92% because 12 selected invoices shipped before the shared card expiry.

Recommended actions are documented in the [project case study](documentation/project_case_study.md) and [Logistics Data SOP](documentation/logistics_data_sop.md).

## Dashboard gallery

| Shipment control tower | Carrier and lane performance |
|---|---|
| ![Shipment control tower mockup](dashboard/screenshots/02_shipment_control_tower.png) | ![Carrier and lane performance mockup](dashboard/screenshots/03_carrier_lane_performance.png) |
| Freight audit | Finance and accrual |
| ![Freight audit mockup](dashboard/screenshots/04_freight_audit.png) | ![Finance and accrual mockup](dashboard/screenshots/05_finance_accrual.png) |
| Data quality and controls | Executive overview |
| ![Data quality and controls mockup](dashboard/screenshots/06_data_quality_controls.png) | ![Executive overview mockup](dashboard/screenshots/01_executive_overview.png) |

All six images are labeled **Power BI dashboard design mockup generated from project reporting outputs** and reconcile through [the dashboard metric ledger](dashboard/dashboard_metric_reconciliation.csv). The manually buildable Power BI contract is in [the dashboard specification](dashboard/dashboard_specification.md), [build instructions](dashboard/build_instructions.md), and [DAX measures](dashboard/measures.dax).

## Excel reporting

The [10-sheet Excel KPI pack](excel/logistics_kpi_pack.xlsx) provides an Executive Summary, shipment exceptions, carrier and lane scorecards, freight audit, three-way matching, accruals, open claims, data quality, and metric definitions. Filters, freeze panes, number formats, conditional formatting, and visible disclosure were validated across every sheet.

See [the KPI pack validation report](excel/kpi_pack_validation.md) for worksheet sources, reconciliation checks, refresh steps, and limitations.

## Testing and reproducibility

- Phase 1 clean-source controls, Phase 2 enterprise simulation, and Phase 3 analytics remain covered by the original 100 tests.
- Phase 3 passes 26/26 analytical and reporting validation gates.
- Phase 4 adds checks for local README links, dashboard and chart files, metric reconciliation, workbook structure and values, disclosure coverage, and generation idempotency.
- Two Phase 3 completion runs produced identical hashes across 23 analytical/reporting CSV outputs.
- Phase 4 images, reconciliation ledgers, diagrams, and generated validation documents are deterministic and hash-verifiable.

## How to run

Install the Python dependencies and optionally choose PostgreSQL; SQLite is the default:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env  # optional
```

Run the full data and analytics pipeline:

```bash
python3 src/download_data.py
python3 src/profile_data.py
python3 src/clean_shipments.py
python3 src/load_database.py
python3 src/run_phase2.py
python3 src/run_phase3.py
```

Regenerate and validate the portfolio-presentation layer:

```bash
python3 src/run_phase4.py
python3 -m pytest tests/ -q
```

With PostgreSQL:

```bash
docker compose up -d
export DATABASE_URL=postgresql+psycopg2://sunlog:change-me-local-only@localhost:5432/sunlog
python3 src/load_database.py
python3 src/run_phase2.py
python3 src/run_phase3.py
python3 src/run_phase4.py
```

## Limitations

- Public-source pharmaceutical shipment patterns are adapted to a disclosed solar scenario; product identity is derived rather than observed.
- Carrier, contract, milestone, invoice, POD, claim, approval, and finance records are deterministic simulations.
- Financial findings are modeled control exposures, not real billing errors, realized recovery, approved budget, or production deployment.
- The 312-record GIT snapshot is intentionally retained; modeled future departures receive zero age rather than negative age.
- Expired-rate invoice recall remains about 92% because 12 selected invoices shipped before the single altered expiry of a shared card.
- SQLite is live-tested. PostgreSQL-compatible SQL has been hardened but was not executed against a live PostgreSQL server in this environment.
- Static dashboard images are source-backed design mockups. Power BI Desktop assembly, interactive filtering, accessibility review, refresh credentials, and publication remain manual work. No `.pbix` is fabricated.

## Interview materials

- [Two-minute recruiter walkthrough](documentation/recruiter_walkthrough.md)
- [Five-minute professional case study](documentation/project_case_study.md)
- [8–10 minute interview demo script](documentation/interview_demo_script.md)
- [Seven-slide presentation outline](documentation/presentation_outline.md)
- [Interview answers, resume bullets, and STAR stories](documentation/interview_materials.md)
- [Standalone interview chart gallery and source map](documentation/chart_source_map.md)
- [Phase 4 completion summary](documentation/phase4_summary.md)
- [Publication audit summary](documentation/publication_audit_summary.md)

The recommended ten-minute path is: data disclosure → architecture → Executive Overview → Freight Audit → Data Quality → Carrier/Lane → recommendations → limitations and production roadmap.
