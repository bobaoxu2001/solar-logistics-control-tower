# 8–10 Minute Interview Demo Script

Use the repository in this order: README → architecture diagram → Executive Overview → Freight Audit → Data Quality → Carrier/Lane → case study. Keep the data disclosure visible when introducing any modeled financial result.

## Minute 0–1 — Business problem

- **What to show:** The README title, six headline metrics, and Executive Overview preview.
- **What to say:** “I built a solar-logistics control tower that connects shipment service, freight settlement, data quality, and finance controls. The business problem is fragmentation: planned dates and status live in transport systems, quantities in ERP, POD in warehouse processes, contractual rates in procurement, and invoices and accruals in finance. I designed one traceable model that answers where service is failing, which invoices need action, and whether the controls are detecting known defects.”
- **Likely question:** “Is this a real company deployment?”
- **Strong answer:** “No. The shipment patterns are public-source derived; the enterprise and finance records are deterministic simulations because those records are normally confidential. The project demonstrates the analytical and control design, not production deployment.”

## Minute 1–2 — Data strategy

- **What to show:** README data-source table and the disclosure.
- **What to say:** “I preserved 10,324 real public shipment-history patterns—dates, modes, weights, values, freight, origins, and destinations—and retained record-level lineage. I remapped product identity to a disclosed solar catalog. Then I generated carriers, lanes, rates, milestones, invoices, PODs, claims, approvals, capacity, and accruals with a fixed seed. That gave me enterprise-like relationships without pretending to possess confidential company data.”
- **Likely question:** “Why simulate some of the data?”
- **Strong answer:** “Rates, invoices, approvals, and accruals are rarely public. Simulation let me demonstrate those controls while keeping provenance explicit and the output reproducible.”

## Minute 2–3 — Architecture

- **What to show:** `documentation/diagrams/project_architecture.png`.
- **What to say:** “Phase 1 acquires, profiles, cleans, and maps the public source. Phase 2 creates a relational enterprise layer. The clean baseline must pass 60 checks before I inject any controlled defects. The exception-injected operational layer stays separate, and a 2,220-record manifest captures the truth set. Phase 3 applies SQL controls, builds scorecards and root-cause evidence, and exports Power BI and Excel reporting. Phase 4 turns those verified outputs into portfolio visuals and interview artifacts.”
- **Likely question:** “Why keep clean and operational layers?”
- **Strong answer:** “It prevents test defects from contaminating the source of truth and lets me prove that the same controls pass a clean baseline and detect controlled exceptions.”

## Minute 3–4 — Executive dashboard

- **What to show:** `dashboard/screenshots/01_executive_overview.png`.
- **What to say:** “The reporting snapshot has 10,012 delivered shipments and 312 in transit. OTIF is 86.88%, split into 88.56% on-time and 98.00% in-full. GIT value is $32.49M. The modeled financial-control exposure is $2.48M, and open accrual is $5.10M. Critical-exception recall is 100%. I show service, operational risk, finance exposure, and control quality together so management can prioritize.”
- **Likely question:** “What would you look at first?”
- **Strong answer:** “I would protect payment first because duplicate exposure dominates, then review rate-card governance and the sufficient-volume lane with 64.06% OTIF.”

## Minute 4–5 — Freight audit

- **What to show:** `documentation/diagrams/freight_audit_workflow.png` and `dashboard/screenshots/04_freight_audit.png`.
- **What to say:** “The expected-charge calculation selects a rate effective on the shipment date, applies the maximum of weight-based charge or minimum charge, then adds contractual fuel, supported accessorials, and tax. I compare that expectation to the invoice and separately test duplicates, carrier, shipment, and currency. Missing or expired rates remain unknown rather than becoming fake zero-dollar expectations. The output identifies $428,053.23 of modeled overcharge, $1,999,642.11 of duplicate exposure, and $50,145.64 of accessorial exposure.”
- **Likely question:** “How do you know the audit findings are correct?”
- **Strong answer:** “The component logic has SQL and unit reconciliation tests, effective-date and minimum-charge tests, one-row-per-invoice checks, and exact expected-versus-invoiced validation. The exception manifest tests detection; the dollar values remain modeled pending real contract and dispute evidence.”

## Minute 5–6 — Data-quality framework

- **What to show:** `dashboard/screenshots/06_data_quality_controls.png`.
- **What to say:** “Twenty-five rules generated 4,015 detections. I join detected record IDs to the 2,220-record manifest by exception type and calculate true positives, false positives, and false negatives. Overall recall is 99.37% and critical recall is 100%. Precision is 54.94% because the rules also detect legitimate shared-card spillover and overlapping operational issues beyond the injected rows.”
- **Likely question:** “Is 54.94% precision poor performance?”
- **Strong answer:** “It would be concerning without diagnosis. Here, the extra detections are traceable: shared rate-card changes affect later invoices and one record can trigger multiple valid controls. I keep those findings visible and would use resolution outcomes to tune rules in production.”

## Minute 6–7 — Carrier and lane analysis

- **What to show:** `dashboard/screenshots/03_carrier_lane_performance.png`.
- **What to say:** “Carrier scores combine OTIF, transit reliability, cost/kg, invoice accuracy, POD compliance, and claims with explicit direction and weights. Meridian Freight Forwarders ranks first at 68.99 out of 100, but only as Acceptable. Volume gates prevent weak samples from being ranked. LANE00575 has 64 shipments and 64.06% OTIF and is flagged for low service, high variance, and high accessorial incidence.”
- **Likely question:** “Why not call the top carrier Preferred?”
- **Strong answer:** “Rank and classification are separate. Meridian is best relative to peers, but its absolute composite does not meet the Preferred threshold.”

## Minute 7–8 — Root-cause findings

- **What to show:** The root-cause panel on the Data Quality dashboard or `documentation/project_case_study.md`.
- **What to say:** “I built three evidence-led cases. The strongest service case is a 45.70-point monthly OTIF decline. The freight case concentrates $739,720.91 across 32 carrier/status invoice rows. The master-data case identifies 1,839 high-severity shared-rate-card detections. Each case separates observation, drill-down, possible cause, impact, owner, action, and follow-up KPI so I do not confuse correlation with proof.”
- **Likely question:** “Can you prove the real operational cause?”
- **Strong answer:** “No. The data supports concentration and a targeted investigation. Production root cause would require carrier communications, capacity evidence, exception-resolution timestamps, and process-owner confirmation.”

## Minute 8–9 — Recommendations

- **What to show:** Recommendation section of the case study.
- **What to say:** “My first five actions are: version and monitor shared rate cards; block duplicate, orphan, and carrier-mismatch invoices before payment; create a LANE00575 service-recovery plan; validate fuel surcharge before payment; and strengthen POD and customs-document SLA queues. Each recommendation maps to a measured concentration and a named functional owner.”
- **Likely question:** “What business action would you take first?”
- **Strong answer:** “I would hold and validate the payment-block population first because it protects the largest immediate modeled exposure. In parallel, Procurement should correct rate-card effective-date governance so the expected-charge control remains reliable.”

## Minute 9–10 — Limitations and production next steps

- **What to show:** README limitations and architecture endpoint.
- **What to say:** “This repository proves transparent logic, reproducibility, and reporting—not a live deployment. SQLite was live-tested; PostgreSQL compatibility was hardened but not live-tested here. I did not fabricate a `.pbix`. In production I would integrate governed TMS, ERP, WMS, contract, and finance sources; test live PostgreSQL security and performance; orchestrate daily incremental refresh; capture ownership and resolution outcomes; and deploy the Power BI semantic model with monitored refresh.”
- **Likely question:** “What changes with real SAP or TMS data?”
- **Strong answer:** “The core definitions stay, but ingestion, identities, currencies, slowly changing dimensions, contract approvals, late-arriving events, access controls, and dispute workflows become production requirements.”
