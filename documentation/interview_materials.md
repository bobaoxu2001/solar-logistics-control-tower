# Interview Materials — Solar Logistics Control Tower

## 30-second introduction

I built an end-to-end logistics control tower on 10,324 public-source shipment patterns, then added deterministic simulated ERP, TMS, carrier, and finance data. The Phase 3 layer measures OTIF and GIT, audits freight invoices, performs three-way matching and accrual reporting, validates injected exceptions at 99.37% recall with 100% critical recall, and publishes reconciled Power BI views plus a working Excel KPI pack.

## Two-minute walkthrough

The project begins with a checksum-verified USAID shipment dataset and preserves record-level lineage. I remapped product identity to a clearly disclosed solar portfolio while keeping the real shipment patterns. Phase 2 generates clean and exception-injected enterprise layers with carriers, rate cards, milestones, invoices, PODs, claims, capacity, approvals, and accruals. Phase 3 computes 86.88% OTIF and 312 GIT shipments, applies 25 data-quality rules, and reconciles every detection to a 2,220-record manifest. The freight engine selects effective rates, enforces minimum charges and fuel percentages, leaves missing rates unknown, and identifies $428,053.23 of modeled overcharge exposure plus duplicate and accessorial risk. Carrier and lane scorecards use transparent configurable weights and volume gates. Finally, I export a star-schema reporting layer, DAX specifications, a 10-sheet Excel pack, three evidence-led case studies, and an operating SOP. The key design choice was to preserve honest boundaries: public, derived, simulated, clean, and operational data are always separated.

## Resume bullets

- Built a reproducible SQL/Python logistics control tower for **10,324** source-derived shipments, delivering OTIF, GIT, transit, freight, POD, claims, capacity, accrual, and exception analytics with record-level lineage.
- Implemented a config-driven **25-rule** data-quality framework and manifest reconciliation, achieving **99.37% overall recall** and **100% critical recall** across **2,220** controlled exceptions.
- Developed effective-date freight rating, invoice audit, and three-way matching that surfaced **$428,053 modeled overcharge exposure**, **$1,999,642 duplicate exposure**, and explicit payment-block/review decisions.
- Produced **14 reporting exports**, Power BI star-schema/DAX specifications, and a reconciled **10-sheet Excel KPI pack** with carrier/lane scorecards, root-cause evidence, and finance controls.

## Interview questions and answers

### 1. How did you validate exception detection?

I used the injected manifest as ground truth, compared record IDs by exception type, and calculated TP, FP, FN, precision, recall, and F1. I gated the pipeline at 95% overall recall and 100% critical recall and documented cross-exception overlaps instead of hiding them.

### 2. How did you avoid overstating freight recovery?

Missing or expired rates produce a null expected total, not zero. Material disputes require both absolute and percentage thresholds. Every dollar is labeled modeled exposure on simulated invoices, pending real-world dispute validation.

### 3. How does the carrier score work?

It min-max normalizes six peer metrics with explicit directionality: higher is better for OTIF, reliability, invoice accuracy, and POD; lower is better for cost/kg and claims. Configured weights sum to 100%, and low-volume carriers are excluded from ranking.

### 4. What bug did you catch during Phase 3?

I found negative GIT ages because the snapshot population included future modeled departures. I preserved the agreed snapshot count but clipped age at zero and added regression coverage. I also retained earlier fixes for null carrier mismatches, unrated expected totals, invoice materiality, and shipment-level quantity matching.

### 5. What would change in production?

I would connect governed ERP/TMS/WMS sources, add currency conversion and slowly changing dimensions, manage identities and SLAs in an orchestration platform, validate rate-card approvals, and publish monitored Power BI datasets. This repository proves the transparent analytical logic, not production deployment.

## LinkedIn project description

Built a portfolio solar-logistics control tower using 10,324 public-source shipment patterns plus transparently simulated enterprise data. The project covers OTIF/GIT analytics, freight rating and audit, three-way match, accruals, carrier/lane scorecards, 25 data-quality controls, evidence-led root-cause analysis, Power BI semantic views/DAX, and a reconciled 10-sheet Excel KPI pack. Manifest testing achieved 99.37% overall detection recall and 100% critical recall. All public, derived, simulated, clean-baseline, and operational-exception layers remain explicitly separated.
