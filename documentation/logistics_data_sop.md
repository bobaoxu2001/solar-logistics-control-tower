# Logistics Data and Freight Control SOP

## Purpose and scope

This SOP governs the portfolio control-tower pipeline from shipment master data through freight settlement, accrual, data-quality management, and reporting. Shipment patterns are public-source derived; enterprise records and financial controls are simulated. Owners below are functional roles, not real-company assignments.

## 1. Master-data maintenance

- Transportation Operations owns carrier and lane assignments; Procurement owns rate cards; Trade Compliance owns HTS and customs requirements.
- New or changed carrier, lane, location, product, and rate rows require a unique key, effective date, active flag, provenance class, and peer review.
- Rate windows for the same carrier-lane must not overlap. Procurement reviews upcoming expirations weekly and loads renewals before the current end date.
- Corrections are additive/versioned. Do not overwrite historical effective dates without an audit note.

## 2. Shipment validation

- Validate shipment, PO, carrier, lane, product, origin, destination, planned dates, quantity, weight, and value before release.
- Reject impossible date sequences, unresolved foreign keys, nonpositive quantity/weight, and missing mandatory identifiers.
- Preserve `source_record_id` through every layer. Record operational corrections in the exception/audit trail rather than altering public-source history.

## 3. Milestone standards

- Milestones must follow the configured sequence and use planned and actual timestamps in a consistent timezone.
- A completed milestone cannot precede an earlier completed sequence. Delivered shipments require a completed customer-delivery milestone.
- Transportation Operations reviews missed, stale, or out-of-sequence milestones daily; high-severity issues are assigned within one business day.

## 4. POD controls

- Warehouse Operations obtains POD for every delivered shipment and validates delivery timestamp, received timestamp, shipment ID, and non-PII recipient role.
- Missing POD is medium severity with a 168-hour resolution SLA. Repeated carrier/lane gaps are reviewed in the weekly scorecard.

## 5. Rate-card maintenance

- Procurement loads carrier, lane, mode, effective window, basis, rate, minimum charge, fuel percentage, currency, and accessorial permissions.
- Validate a single applicable rate per carrier-lane-ship-date. Missing or expired rates make expected freight unknown; they must never be treated as a zero-dollar expectation.
- Review the rate-expiry report weekly and the full active-rate inventory before month end.

## 6. Freight-invoice validation

- Accounts Payable validates shipment existence, carrier, currency, invoice number uniqueness, charge components, applicable rate, fuel calculation, supported accessorials, and invoice total.
- Material invoice disputes require both the configured absolute and percentage thresholds; DQ detection uses the broader either-threshold rule to surface injected errors.
- Duplicate, orphan, carrier-mismatch, and paid-without-approval invoices are blocked. Unrated invoices route to Procurement and are not classified as full-value overcharges.

## 7. Three-way matching

- Match PO to shipment to invoice before payment release.
- Compare delivered quantity with the shipment's own planned quantity, not a grouped PO total.
- `BLOCK_PAYMENT` and `MISSING_RECORD` stop payment. `REVIEW_REQUIRED` routes to the named owner. `MATCHED_WITH_WARNING` requires documented review; `MATCHED` may proceed.

## 8. Accessorial approval

- The invoice must contain a supported accessorial record with charge type, amount, contractual permission, document flag, approval status, and reason.
- Unauthorized charges are fully recoverable; excessive charges are recoverable above the configured band. Unsupported charges remain on hold until documentation is received.

## 9. Accrual handling

- Create one expected-freight accrual per shipment/accounting period. The expected amount is a simulated planning baseline, not a corporate budget.
- Release only after invoice receipt and approval. Reconcile expected versus actual invoice cost and investigate material variance.
- Finance reviews uninvoiced shipments, open accruals, release dates, and period totals at month end.

## 10. Severity, SLA, assignment, and escalation

| Severity | SLA | Typical response |
|---|---:|---|
| Critical | 24 hours | Block payment/process, notify owner and Finance/Operations lead |
| High | 72 hours | Assign named owner, contain exposure, correct master/process data |
| Medium | 168 hours | Resolve in weekly control cycle and monitor recurrence |
| Low | 336 hours | Add to control backlog and close with evidence |

Exceptions are assigned using `phase3.exception_owners`. Breached critical/high SLAs escalate to the functional lead; unresolved financial-control items remain blocked.

## 11. Audit trail

- Retain source layer, rule, record ID/type, detected timestamp, severity, owner, status, age, clean value, injected/operational value, and resolution evidence.
- Pipeline reruns replace derived report tables deterministically and never delete source or manifest evidence.
- Changes to thresholds, weights, mappings, and effective dates require a repository commit and updated definition note.

## 12. Weekly controls

1. Run `python src/run_phase3.py` and confirm the validation gate passes.
2. Review critical/high open exceptions and SLA breaches.
3. Review overdue GIT, missing POD, milestone gaps, carrier/lane scorecards, rate expirations, invoice audit, and open claims.
4. Assign corrective actions and record owners/dates.
5. Reconcile SQL reporting views to the Excel KPI pack.

## 13. Month-end controls

1. Freeze the reporting snapshot and confirm all required source tables are present.
2. Reconcile shipment, invoice, accrual, claim, and exception counts.
3. Validate open accruals, uninvoiced shipments, released accruals, and expected-versus-actual variance.
4. Review all blocked/review-required three-way matches and recoverable freight exposure.
5. Confirm Power BI exports and Excel totals match SQL; archive the validation report and management commentary.
