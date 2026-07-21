# Logistics Control Tower Dashboard Specification

## 1. Executive Logistics Overview

Cards: shipment count, OTIF, on-time, GIT count/value, freight spend, recoverable overcharge, open accrual, and data-quality score. Add monthly OTIF and freight trends, plus top exception and carrier callouts. Global slicers: date, carrier, mode, lane region, and product category.

## 2. Shipment Control Tower

Display GIT and overdue-GIT cards, an aging distribution, lane/carrier breakdowns, and a shipment detail table with planned/actual dates, delay, value, POD, and exception flags. Drill through to milestone history using `shipment_id`.

## 3. Carrier and Lane Performance

Use ranked carrier scorecards with all six component scores, total score, classification, and action. Show lane volume, spend, cost/kg, OTIF, delay, variability, claims, accessorial, invoice-exception, capacity, DQ rate, service classification, and recommendation. Visually separate insufficient-volume entities from ranked peers.

## 4. Freight Audit

Cards: invoiced freight, expected freight, variance, potential overcharge, accessorial spend, and invoice accuracy. Break down audit status by carrier and lane; provide invoice-level drill-through with component charges, rate status, materiality, and dispute action.

## 5. Finance and Accrual

Cards: open accrual, accrual variance, uninvoiced shipments, and released accruals. Show accounting-period expected freight versus actual invoiced freight. Label expected freight as a simulated planning baseline, not an approved corporate budget.

## 6. Data Quality and Controls

Cards: open exceptions, data-quality score, detection precision, detection recall, and critical recall. Show severity/owner/SLA aging, manifest reconciliation, and the three root-cause case studies. Distinguish observed detections, injected-manifest truth, possible causes, and recommended actions.

## Interaction and display rules

- Rates use percentage formats and zero-safe DAX division.
- Currency is USD because the analytical control layer converts no currencies; mismatched currency remains an exception.
- Tooltips state metric grain and whether the underlying field is public, derived, or simulated.
- Red/amber/green thresholds mirror the configuration and scorecard classifications.
- No `.pbix` is included; this specification and `measures.dax` are the reproducible build contract.
