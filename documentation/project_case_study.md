# Project Case Study — Solar Logistics Control Tower & Freight Audit System

## Context

Renewable-energy supply chains move high-value modules, inverters, batteries, and electrical components across long international lanes. A logistics analyst must connect service performance to freight cost, documentation, carrier accountability, and month-end finance controls. Real enterprise records are rarely public, so this portfolio project starts with 10,324 public shipment-history records and builds a transparent deterministic solar-logistics scenario around them.

## Challenge

Shipment status alone does not answer the questions a logistics leader or Accounts Payable team needs. Planned and actual milestones may sit in a TMS, orders and quantities in ERP, receipt evidence in WMS or POD systems, rates in carrier contracts, invoice components in freight settlement, and accruals in finance. Fragmentation makes it difficult to:

- measure OTIF and Goods in Transit consistently;
- identify overdue or high-value shipment risk;
- compare invoiced freight with an effective contractual expectation;
- decide whether an invoice should be approved, reviewed, or blocked;
- evaluate carrier and lane performance with enough volume context; and
- prove that data-quality controls detect known defects.

## Approach

The project uses a layered, reproducible design:

1. **Real shipment foundation.** Public shipment patterns retain dates, modes, weights, values, costs, origins, destinations, and record-level lineage. Product identity is deterministically remapped to a disclosed renewable-energy catalog.
2. **Simulated enterprise systems.** Seeded generation creates the carrier, lane, rate-card, PO, milestone, invoice, accessorial, POD, claim, approval, capacity, and accrual records that are normally confidential.
3. **Relational model.** The clean baseline separates master data from operational facts and passes 60 validation checks before any exception is introduced.
4. **Controlled exception injection.** A separate operational layer contains 2,220 documented exceptions across 19 types, with clean and injected values captured in a manifest.
5. **SQL analytics and controls.** Views calculate OTIF, GIT, transit, freight rating, invoice audit, three-way match, accruals, scorecards, data-quality detection, and root-cause evidence.
6. **Management reporting.** Fourteen Power BI-ready exports, safe-division DAX, six dashboard specifications, a ten-sheet Excel pack, and source-backed static mockups make the results reviewable.

## Solution

### Shipment control tower

The shipment layer defines delivered, on-time, in-full, OTIF, late, partial, GIT, overdue-GIT, transit variance, POD, and invoice flags at shipment grain. At the 2025-07-01 snapshot, 10,012 of 10,324 shipments are delivered and 312 remain in transit with $32,491,473.31 of shipment value.

### Freight audit and payment controls

For each shipment, the audit selects a carrier-lane rate valid on the ship date. Expected freight uses the greater of weight-based cost or minimum charge, then adds contractual fuel, supported accessorials, and tax. Missing or expired rates remain unknown. The invoice comparison identifies duplicates, carrier/shipment mismatches, currency issues, fuel issues, and material overcharges. Three-way matching converts those checks into approve, warning, review, block, or missing-record decisions.

### Finance and accrual reporting

One expected-freight accrual is maintained per shipment. Reports separate released and open accruals, invoice receipt, actual cost, uninvoiced shipments, and variance. Expected values are labeled as simulated planning baselines rather than corporate budgets.

### Carrier, lane, and root-cause analysis

Carrier scores balance OTIF, transit reliability, cost/kg, invoice accuracy, POD compliance, and claims. Volume gates prevent low-observation carriers and lanes from being treated as reliable ranks. Root-cause outputs separate observation, drill-down evidence, possible cause, business impact, owner, corrective action, and follow-up KPI.

### Manifest-backed data-quality framework

Twenty-five SQL rules generate record-level detections with severity, owner, SLA, and source layer. Matching those IDs to the injected manifest produces true positives, false positives, and false negatives by exception type. This makes detection quality testable and exposes overlaps rather than suppressing them.

## Results

- **Service:** 86.88% OTIF, 88.56% on-time, 98.00% in-full, and 5.56 average transit days.
- **Control validation:** 4,015 detections against 2,220 manifested records; 99.37% recall and 100% critical recall.
- **Modeled exposure:** $428,053.23 overcharge, $1,999,642.11 duplicate-payment, and $50,145.64 accessorial exposure—$2,477,840.98 total.
- **Three-way match:** 7,275 matched, 155 matched with warning, 2,233 review required, 219 block payment, and 60 missing records.
- **Accruals:** $5,101,238.49 open accrual, 316 uninvoiced shipments, and $750,473.42 total variance.
- **Performance:** Meridian Freight Forwarders ranks first at 68.99/100 (Acceptable). LANE00575 has 64 shipments and 64.06% OTIF and is classified Low service, High variance, High accessorial.

## Business recommendations

1. **Tighten shared rate-card maintenance.** Procurement should version non-overlapping carrier-lane effective windows and monitor renewal lead time. This targets the 1,839 high-severity expired-rate detections and prevents unreliable expected-freight calculations.
2. **Prioritize payment blocks.** Accounts Payable should validate and hold duplicate, orphan, and carrier-mismatch invoices before release. Duplicate-payment exposure is the largest component at $1,999,642.11.
3. **Create a LANE00575 recovery plan.** Transportation Operations should review milestone delays, accessorial documentation, and carrier capacity on this sufficient-volume lane, then track OTIF and transit variability weekly.
4. **Move fuel validation before payment.** The 138 incorrect-fuel cases justify a pre-payment comparison of invoiced fuel to the applicable contractual percentage.
5. **Strengthen POD and customs-document ownership.** Warehouse Operations and Trade Compliance should use SLA queues and recurring scorecards for missing POD and documentation exceptions instead of resolving them only at settlement.

## Limitations

This is a deterministic portfolio simulation. Shipment patterns are public-source derived, while solar product mapping and enterprise/finance records are derived or simulated. The financial findings are modeled exposures, not real-company errors or realized savings. SQLite was live-tested; PostgreSQL compatibility was hardened but not executed against a live PostgreSQL server. Static dashboards are design mockups from reporting outputs, not Power BI screenshots.

## What I would do next in production

I would replace CSV and generated records with governed TMS, ERP, WMS, carrier-contract, and finance integrations; validate actual contract versions and currencies; run live PostgreSQL performance and permission tests; orchestrate daily incremental refresh; add exception-resolution timestamps, evidence attachments, and accountable owners; deploy the semantic model to a controlled Power BI workspace; and monitor refresh, rule drift, false positives, dispute outcomes, and realized recovery separately from modeled exposure.
