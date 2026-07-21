# Seven-Slide Interview Presentation Outline

## Slide 1 — Business problem and project objective

- **Objective:** Establish why fragmented logistics and finance records need one control framework.
- **Headline:** From shipment visibility to payment control.
- **Visual:** Executive dashboard preview with the data disclosure visible.
- **Main messages:** 10,324 source-derived shipments; operational and financial controls in one model; portfolio simulation, not a production-company claim.
- **Speaker notes:** Open with the three decisions: where service is failing, which invoices require action, and whether the controls detect known defects.
- **Transition:** “To make those decisions credible, I first had to design an honest data strategy.”

## Slide 2 — Data and architecture

- **Objective:** Explain the public foundation, simulated enterprise systems, and clean/operational separation.
- **Headline:** Real patterns, transparent simulation, preserved lineage.
- **Visual:** `documentation/diagrams/project_architecture.png`.
- **Main messages:** public shipment history; deterministic ERP/TMS/WMS/rate/invoice/finance generation; clean baseline before exception injection.
- **Speaker notes:** Emphasize the 60 clean-baseline checks and 2,220-record exception manifest.
- **Transition:** “With that governed foundation, the first business layer is the shipment control tower.”

## Slide 3 — Logistics control tower

- **Objective:** Show how service and GIT are monitored.
- **Headline:** 86.88% OTIF with $32.49M in Goods in Transit.
- **Visual:** `dashboard/screenshots/02_shipment_control_tower.png` plus `documentation/charts/monthly_otif_trend.png`.
- **Main messages:** 10,012 delivered and 312 GIT; on-time and in-full separated; 45.70-point monthly deterioration provides a drill-down case.
- **Speaker notes:** Define OTIF at delivered-shipment grain and explain the zero-age treatment for modeled future departures.
- **Transition:** “Shipment performance then feeds the financial question: was the carrier invoice correct?”

## Slide 4 — Freight audit and financial controls

- **Objective:** Explain expected charge, invoice comparison, and payment decisions.
- **Headline:** $2.48M of modeled control exposure identified.
- **Visual:** `documentation/diagrams/freight_audit_workflow.png` and `documentation/charts/freight_audit_exposure_waterfall.png`.
- **Main messages:** missing rates remain unknown; duplicate exposure is the largest component; 219 rows block payment.
- **Speaker notes:** Distinguish overcharge, duplicate, and accessorial components and avoid calling them realized savings.
- **Transition:** “Because I injected known defects, I could also test whether these controls actually work.”

## Slide 5 — Data quality and manifest validation

- **Objective:** Demonstrate measurable rule performance and honest interpretation.
- **Headline:** 99.37% recall and 100% critical recall.
- **Visual:** `dashboard/screenshots/06_data_quality_controls.png`.
- **Main messages:** 25 rules and 4,015 detections; 2,220-record truth set; 54.94% precision reflects additional legitimate detections and overlaps.
- **Speaker notes:** Explain TP/FP/FN by exception type and the shared-rate-card spillover caveat.
- **Transition:** “Once the controls were validated, I used them to compare carriers, lanes, and concentrations.”

## Slide 6 — Carrier, lane, and root-cause findings

- **Objective:** Connect scorecards to concrete operating actions.
- **Headline:** Service, cost, and control risk concentrate in specific lanes and invoice populations.
- **Visual:** `dashboard/screenshots/03_carrier_lane_performance.png`.
- **Main messages:** Meridian leads at 68.99/100 but is only Acceptable; LANE00575 has 64.06% OTIF; 32 invoice rows carry $739,720.91 of modeled exposure.
- **Speaker notes:** Explain volume gates and why the evidence supports concentration, not a definitive causal claim.
- **Transition:** “Those concentrations lead directly to a short operational roadmap.”

## Slide 7 — Recommendations and production roadmap

- **Objective:** Close with prioritized actions and an honest next step.
- **Headline:** Fix master-data and payment controls first, then operationalize the workflow.
- **Visual:** Five-action list paired with the architecture’s production endpoints.
- **Main messages:** rate-card governance; pre-payment block/fuel validation; LANE00575 recovery plan; live integrations and managed Power BI refresh.
- **Speaker notes:** Separate immediate process actions from production engineering. Reiterate simulated-data and live-PostgreSQL limitations.
- **Transition:** “The repository proves the transparent logic and reporting package; production would replace simulated sources with governed system integrations.”
