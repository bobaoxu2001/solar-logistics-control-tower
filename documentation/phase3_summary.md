# Phase 3 Summary — Logistics Analytics, Freight Audit, and Reporting

_Reporting snapshot: 2025-07-01. Generated from the operational exception-injected layer; clean-baseline logic is tested separately._

## Verified headline metrics

| Metric | Result |
|---|---:|
| Shipment count | 10,324 |
| Delivered count | 10,012 |
| Goods in transit | 312 shipments / $32,491,473.31 |
| OTIF | 86.88% |
| On-time rate | 88.56% |
| In-full rate | 98.00% |
| Average transit time | 5.56 days |
| Freight spend | $229,333,236.90 |
| Rated expected freight | $180,056,846.98 |
| Rated invoice variance | $554,819.94 |
| Recoverable overcharge | $428,053.23 |
| Duplicate-invoice exposure | $1,999,642.11 |
| Unauthorized/excessive accessorial recovery | $50,145.64 |
| Invoice accuracy | 75.40% |
| Open accrual | $5,101,238.49 |
| Claims rate / cost | 4.105% / $6,783,260.99 |
| POD compliance | 96.00% |
| Data-quality score | 82.77% |
| Manifest / detected count | 2,220 / 4,015 |
| Detection precision / recall | 54.94% / 99.37% |
| Critical recall | 100.00% |
| Complete test count | 100 tests; 100 passed in the final completion run |

## Freight audit and three-way match

- Unrated invoices remain unknown rather than becoming false full-value overcharges.
- Recoverable modeled exposure totals **$2,477,840.98** across overcharge, duplicate, and accessorial components.
- Three-way match: **7,275 matched**, **155 matched with warning**, **2,233 review required**, **219 block payment**, and **60 missing record**.

## Carrier and lane highlights

- Top ranked carrier: **Meridian Freight Forwarders** at **68.99/100**, rank 1, classified **Acceptable**. Scores are peer-normalized; no carrier is labeled Preferred in this simulated operational population.
- Most multi-flag sufficient-volume lane: **LANE00575**, Mylan (formerly Matrix) Nashik to Mozambique Distribution Center; 64 shipments, OTIF 64.06%, cost/kg $2.1855, classified **Low service; High variance; High accessorial**.
- **648** lanes are below the configurable 20-shipment threshold and are explicitly not treated as reliable ranked comparisons.

## Three evidence-led root-cause findings

### RCA-01: Monthly OTIF deterioration

- Observation: OTIF moved from 90.14% to 44.44% (-45.70 pp).
- Evidence: 29 late shipments; average late delay 15.90 days; late shipment value $7,277,438.14.
- Drill-down: Largest lane/carrier concentration: Meridian Freight Forwarders, Cipla, Goa, India to South Africa Distribution Center, with 3 late shipments and 0 claims.
- Possible cause: Service deterioration is concentrated in the identified carrier-lane-month combination; the available data supports concentration, not a definitive causal mechanism.
- Business impact: Late value on the concentrated segment was $1,411,064.26; associated claim cost was $0.00.
- Corrective action: Transportation Operations should review milestone timestamps and carrier capacity for the concentrated lane, then agree a service-recovery action plan.
- Follow-up KPI: Monthly OTIF, late shipment count, average late days, and claim cost for the identified carrier-lane.

### RCA-02: Freight invoice control exposure

- Observation: 32 invoices for VoltLine Express Air carry $739,720.91 of modeled recoverable exposure.
- Evidence: Affected billed amount $738,455.51 across 32 shipments; shipment value $4,870,812.69.
- Drill-down: Audit status=DUPLICATE_INVOICE; overcharge component=$1,265.40; duplicate component=$738,455.51.
- Possible cause: The pattern is consistent with a billing-control or contractual-rate exception; source records do not prove carrier intent or operational causation.
- Business impact: Potentially recoverable modeled exposure is $739,720.91 before dispute validation.
- Corrective action: Accounts Payable should block or dispute flagged invoices, validate supporting rate evidence, and release only after three-way-match clearance.
- Follow-up KPI: Recoverable exposure, disputed invoice count, resolution cycle time, and invoice accuracy.

### RCA-03: Data-quality and rate-card control concentration

- Observation: 1839 detections (HIGH) produced 9,195 weighted exception points.
- Evidence: Manifest=150, true positives=138, false negatives=12, recall=92.00%.
- Drill-down: Rate-card-level event: all 124 expired cards are detected (card-level recall 100%) and every invoice shipping after its card's expiry is flagged, so detected >> manifest (same-lane spillover = real exposure). Invoice-level recall is 92% because 12 co-selected invoices share a card and ship BEFORE the single dedup expiry date, so at their ship time the card was still valid — a Phase 2 shared-card artifact, not a detection miss.
- Possible cause: The concentration is consistent with shared carrier-lane master-data effective dates; detection results identify exposure but do not establish a real-world process cause.
- Business impact: Stale or ambiguous rate coverage increases manual review volume and can prevent reliable expected-freight calculation.
- Corrective action: Procurement should enforce versioned non-overlapping rate windows and pre-expiry renewal alerts.
- Follow-up KPI: Expired-rate detections, rated-invoice percentage, false-negative count, and rate-card renewal lead time.

## Detection caveats

- Expired-rate-card invoice recall is 92%: 12 manifested invoices shipped before the single deduplicated shared-card expiry and are logically not detectable as expired at shipment time. The shared card creates additional real analytical exposure for later invoices; it is not forced into a false 100% invoice match.
- One invoice-carrier mismatch overlaps a shipment whose carrier was nulled, and one incorrect-fuel record is masked by another operational defect. Both remain visible in reconciliation.
- Low manifest-level precision is driven mainly by shared-rate-card spillover and duplicate-invoice records that also create duplicate-payment risk. These are transparent multi-rule exposures, not hidden failures.

## Data boundary and limitations

Shipment patterns come from the public USAID SCMS dataset. Solar product identity is remapped; carrier, rate, invoice, milestone, POD, claim, capacity, approval, and accrual data are simulated. Findings demonstrate controls on a deterministic portfolio dataset and do not represent a production deployment, real carrier performance, recoveries, or approved budgets. GIT retains the agreed snapshot population; modeled departures after the snapshot are assigned zero age rather than a negative age.
