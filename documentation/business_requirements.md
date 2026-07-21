# Business Requirements — Solar Logistics Control Tower & Freight Audit System

## 1. Business context

**SunGrid Energy Solutions** (a fictional case-study company) manufactures and
distributes solar modules, inverters, battery energy-storage systems (BESS), and
electrical balance-of-system (BOS) components. Product moves from manufacturing
sites and suppliers, through ports, distribution centers, and warehouses, to
customer project sites, across ocean, truck, rail, air, and multimodal
transport.

The Logistics Data Specialist owns the data that makes this network
measurable and auditable: shipment milestones, carrier performance, freight
invoices, accruals, and the master data underneath them. This project builds the
analytics environment that role would operate.

> **Data disclosure.** This project combines real public shipment history with
> deterministically simulated ERP, TMS, WMS, carrier-contract, freight-invoice,
> and finance records. Simulated records are used because company rate cards,
> invoices, purchase orders, and settlement data are ordinarily confidential.
> Nothing here is real company data.

## 2. Stakeholders

| Stakeholder | Needs |
|---|---|
| Logistics operations | Shipment status, milestone tracking, exception queues, OTIF |
| Transportation procurement | Carrier scorecards, lane cost, RFP evidence |
| Freight audit / AP | Invoice validation, three-way match, overcharge recovery |
| Finance | Freight accruals, budget vs actual, month-end close |
| Data governance | Master-data quality, referential integrity, HTS/customs completeness |

## 3. Scope by phase

- **Phase 1 (done):** acquire + validate public shipment data; relational
  schema; cleaned staging with lineage.
- **Phase 2 (this phase):** simulate the enterprise environment — master data,
  purchase orders, shipments, milestones, rate cards, freight invoices,
  accessorials, PODs, claims, capacity, accruals — then inject controlled
  exceptions for downstream detection.
- **Phase 3 (next):** data-quality rules, logistics KPIs, freight audit,
  three-way match, accruals, carrier scorecard, root-cause analysis.
- **Phase 4:** Power BI, Excel KPI pack, SOP.

## 4. Phase 2 functional requirements

### 4.1 Determinism & provenance
- All generation is seeded (`random_seed` in `config/project_config.yaml`);
  re-running yields byte-identical data and never duplicates rows.
- Every table carries `data_class` ∈ {PUBLIC, DERIVED, SIMULATED} (this is the
  project's single provenance marker — the prompt's "source_type").
- Every enterprise shipment preserves `source_record_id` lineage to the public
  source row.

### 4.2 Master data (derived from the real shipment foundation)
- **Locations** from real manufacturing sites (origins) and destination
  countries; coordinates left NULL where the source is insufficient (never
  fabricated); raw strings preserved in `dim_location_xref`.
- **Products**: 5 SKUs per renewable-energy category; nominal unit weight/value
  seeded from the observed per-unit source distribution.
- **Carriers**: 12 fictional carriers across all modes; deterministic assignment
  by mode and lane.
- **Lanes** from observed (origin, destination, mode) combinations; standard
  transit derived from mode/region standards because the source has no departure
  timestamp (documented in `rpt_lane_derivation`).
- **Rate cards**: one per (carrier, lane); `rate_per_kg` calibrated to the
  observed mode-level freight/kg so generated freight tracks reality
  (`rpt_rate_reconciliation` — all-mode expected/observed ratio ≈ 1.0).

### 4.3 Operational facts
- Shipments with a documented **date-derivation hierarchy** (real delivery
  dates preserved; ship dates derived and flagged).
- **Mode-aware milestones** (truck shipments have no ocean-port milestones,
  ocean shipments have port + customs milestones, etc.).
- One **freight invoice per delivered shipment** whose charges reconcile to the
  applicable rate card within audit tolerance; invoice total = component lines.
- **Accessorials** only under plausible operational conditions (demurrage on
  ocean, liftgate on truck, …), all contractually allowed in the clean baseline.
- **PODs** for delivered shipments; **claims** risk-weighted to late/high-value/
  ocean shipments; **accruals** driven by accounting period and invoice timing;
  **capacity** with utilization ≤ 100% and seasonal variation.

### 4.4 Clean baseline before exceptions
- The clean baseline must pass every internal-consistency check with **zero
  critical failures** (`rpt_phase2_baseline_validation`) before any exception is
  injected.

### 4.5 Controlled exception injection
- A separate, config-driven layer (`config/exception_config.yaml`) injects 19
  exception types deterministically into an **operational** copy, leaving the
  clean baseline untouched.
- Every change is recorded in the **exception manifest** (clean value + injected
  value), enabling Phase 3 to measure detection.
- Real operational lateness is **not** injected — it is inherited from the source
  data — keeping "real performance" distinct from "injected defect".

## 5. Non-functional requirements
- Runs on PostgreSQL (primary) or SQLite (fallback), selected by `DATABASE_URL`.
- Reproducible end-to-end via one command (`python src/run_phase2.py`).
- No secrets, PII, or large files committed; recipients are generic roles.

## 6. Success criteria (Phase 2)
All Phase 1 tests still pass; master data generated; 10,324 shipments retain
lineage and link to valid products/carriers/lanes/locations/POs; milestones
ordered; every delivered shipment has a valid rate and reconciling invoice;
accessorials/PODs/accruals reconcile; clean baseline has zero critical failures;
exceptions injected separately with an exact manifest; pipeline reproducible and
idempotent; full test suite passes.
