# Interview Materials — Solar Logistics Control Tower

## 30-second answer

I built a reproducible logistics control tower using 10,324 public shipment patterns plus transparently simulated ERP, TMS, WMS, carrier-contract, and finance data. It measures OTIF and GIT, audits freight invoices, performs three-way matching and accrual reporting, ranks carriers and lanes, and validates 25 data-quality rules against a controlled manifest. The project achieved 99.37% detection recall and 100% critical recall and surfaced $2.48M of modeled financial-control exposure.

## 90-second answer

The project starts with checksum-verified public shipment history and preserves record-level lineage. Because real rates, invoices, PODs, approvals, and accruals are confidential, I generate those enterprise records deterministically and label them simulated. I keep a clean baseline separate from an exception-injected operational layer. Then SQL views calculate 86.88% OTIF, $32.49M in Goods in Transit, freight expected-versus-invoiced variance, three-way-match decisions, open accrual, and carrier/lane scorecards. I inject 2,220 documented exceptions and reconcile the rule detections to that manifest, producing 99.37% recall and 100% critical recall. Finally, I publish 14 Power BI-ready exports, DAX, six source-backed dashboard mockups, a ten-sheet Excel pack, root-cause evidence, and operating documentation. The important design choice is that public, derived, simulated, clean, and operational data always remain distinguishable.

## Two-minute answer

I wanted to demonstrate the full work of a Logistics Data Specialist, not only a chart. I began with 10,324 public shipment-history records and retained dates, modes, weights, values, freight, origins, destinations, and record-level lineage. Product identity is deterministically adapted to a solar scenario. I then generated the enterprise data that are normally confidential—carriers, lanes, rate cards, milestones, purchase orders, invoices, accessorials, PODs, claims, approvals, capacity, and accruals—with a fixed seed.

The clean relational baseline passes 60 checks before I inject 2,220 controlled exceptions. Phase 3 computes OTIF, GIT, transit, freight audit, three-way matching, accruals, carrier and lane scores, and root-cause evidence. The expected-freight engine respects effective dates, minimum charges, contractual fuel, and supported accessorials; missing rates stay unknown. It identifies $428,053.23 of modeled overcharge, $1,999,642.11 of duplicate-payment exposure, and $50,145.64 of accessorial exposure. The data-quality rules achieve 99.37% recall and 100% critical recall. I finish with reconciled Power BI views and DAX, six dashboard pages, a ten-sheet Excel pack, and an SOP. The financial records and findings are simulations, so I describe them as control exposures rather than realized savings.

## Four resume bullets

- Built a reproducible SQL/Python logistics control tower for **10,324** source-derived shipments, delivering OTIF, GIT, transit, freight, POD, claims, accrual, and exception analytics with record-level lineage.
- Implemented a config-driven **25-rule** data-quality framework and manifest reconciliation, achieving **99.37% recall** and **100% critical recall** across **2,220** controlled exceptions.
- Developed effective-date freight rating, invoice audit, and three-way matching that surfaced **$428K modeled overcharge**, **$2.00M duplicate-payment exposure**, and explicit approve/review/block decisions.
- Produced **14 Power BI-ready exports**, safe-division DAX, **six source-backed dashboard mockups**, and a reconciled **10-sheet Excel KPI pack** with carrier/lane and finance controls.

## Five technical interview questions

### 1. How did you validate exception detection?

I matched detected record IDs to the injected manifest by exception type and calculated TP, FP, FN, precision, recall, and F1. The pipeline gates at 95% overall recall and 100% critical recall and retains legitimate overlaps.

### 2. How does the freight calculation work?

It selects the carrier-lane rate effective on ship date, uses `max(rate/kg × weight, minimum charge)`, adds contractual fuel, includes only supported and allowed accessorials, and adds tax. Missing or expired rates return an unknown expectation.

### 3. How did you make the pipeline reproducible?

Generation uses fixed seeds and stable sorting. Clean and operational outputs are replaced deterministically, tests cover key calculations, and Phase 3 and Phase 4 artifacts are hash-compared across repeated runs.

### 4. How is the carrier score calculated?

Six metrics are min-max normalized with explicit directionality. OTIF, reliability, invoice accuracy, and POD are higher-is-better; cost/kg and claims are lower-is-better. Configured weights sum to 100%, and low-volume entities are not ranked.

### 5. What was the hardest technical issue?

The hardest issue was preserving honest exception semantics when one altered shared rate card affected many later invoices. I separated card-level detection from invoice-manifest recall, documented the 12 invoices that shipped before the altered expiry, and did not force a misleading 100% invoice-level match.

## Five logistics-business questions

### 1. What does 86.88% OTIF mean?

Among delivered shipments, 86.88% arrived on or before the planned delivery date and with delivered quantity at least equal to planned quantity.

### 2. What business action would you take first?

Hold and validate the payment-block population because duplicate-payment exposure is the largest immediate modeled risk, then correct rate-card effective-date governance.

### 3. Why highlight LANE00575?

It has sufficient volume—64 shipments—yet only 64.06% OTIF and simultaneous high-variance and high-accessorial flags, so it is a defensible service-recovery candidate.

### 4. Why can the top carrier still be only Acceptable?

Ranking is relative to peers; classification uses absolute thresholds. Meridian leads the peer set at 68.99/100 but does not meet the Preferred threshold.

### 5. How would you reduce missing POD problems?

Assign Warehouse Operations ownership, trigger a 168-hour SLA queue, monitor recurrence by carrier/lane, and require resolution evidence before closing the exception.

## Five behavioral questions with concise STAR answers

### 1. Tell me about a time you found a data problem.

- **Situation:** GIT records included modeled future departures.
- **Task:** Keep the agreed snapshot population without reporting impossible negative age.
- **Action:** I traced date logic, clipped age at zero, retained the 312 records, and added regression tests and disclosure.
- **Result:** The snapshot remained consistent and all Phase 3 validation checks passed.

### 2. Tell me about a time requirements conflicted.

- **Situation:** The manifest expected expired-rate defects, but shared cards affected additional invoices.
- **Task:** Preserve both logical detection and honest validation.
- **Action:** I separated card-level from invoice-level evidence and documented the shared-card artifact.
- **Result:** Critical recall remained 100%, expired-rate invoice recall was honestly reported at 92%, and legitimate spillover stayed visible.

### 3. Tell me about a time you prioritized business impact.

- **Situation:** The audit generated several exception categories.
- **Task:** Translate technical flags into an action order.
- **Action:** I decomposed exposure into overcharge, duplicate, and accessorial components and connected them to three-way-match decisions.
- **Result:** Duplicate-payment controls and 219 payment blocks emerged as the first operational priority.

### 4. Tell me about a time you made complex work understandable.

- **Situation:** The repository contained SQL, Python, DAX, Excel, and detailed controls.
- **Task:** Support recruiter, manager, and interview audiences.
- **Action:** I created a recruiter-first README, six dashboard mockups, a two-minute walkthrough, a case study, and a timed demo script, all sourced from the same outputs.
- **Result:** The project now supports 30-second, three-minute, and ten-minute viewing depths without changing the analytics.

### 5. Tell me about a time you protected quality under time pressure.

- **Situation:** Presentation work could have encouraged manual headline numbers.
- **Task:** Add visuals without weakening reproducibility.
- **Action:** I generated every page from Phase 3 views, created a metric reconciliation ledger, added existence/link/disclosure tests, and hash-compared repeated Phase 4 runs.
- **Result:** The presentation layer remained deterministic and traceable to the analytical source.

## Direct challenge questions

### Why did you simulate some of the data?

Carrier contracts, invoices, approvals, and accruals are ordinarily confidential. Deterministic simulation lets me demonstrate the relationships and controls while preserving a truthful data boundary and reproducibility.

### Why is precision only 54.94%?

The manifest measures injected records, but the rules also detect additional legitimate issues. Shared rate-card changes affect later invoices, and one record can trigger overlapping controls. I disclose that spillover and would use production resolution outcomes to tune rule specificity.

### What does 99.37% recall mean here?

Across exception types represented in the manifest, 99.37% of manifested record/type combinations were detected. It does not mean 99.37% accuracy on unknown production defects.

### How do you know the freight-audit findings are correct?

Effective-date selection, minimum charge, fuel, accessorial, component totals, one-row-per-invoice, and reconciliation values are tested. The exception manifest validates control detection. Real-world recovery would still require actual contracts, documents, and dispute confirmation.

### What would change with real SAP or TMS data?

I would add governed connectors, identities, currencies, slowly changing dimensions, late-arriving events, contract approvals, role-based access, orchestration, audit evidence, and dispute-resolution workflow. The KPI definitions could remain, but data operations become production-grade.

### What was the hardest technical issue?

Shared effective-dated rate cards created legitimate spillover beyond the injected rows. The solution was not to suppress the detections; it was to reconcile at the correct grain and explain card-level versus invoice-level results.

### What business action would you take first?

Block and validate duplicate, orphan, and carrier-mismatch invoice populations before payment, because the duplicate component dominates modeled exposure. Then fix rate-card governance so future expected-charge calculations remain reliable.
