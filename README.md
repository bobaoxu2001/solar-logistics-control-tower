# Solar Logistics Control Tower & Freight Audit System

End-to-end logistics analytics for **SunGrid Energy Solutions**, a fictional
global manufacturer of solar modules, inverters, battery energy-storage
systems, and electrical balance-of-system components.

**Workflow demonstrated:** raw logistics data → validation → relational data
model → KPI calculations → exception detection → freight audit → management
reporting → business recommendations.

**Skills demonstrated:** SQL, Python, Excel/Power Query, Power BI, logistics
KPI reporting (OTIF, goods-in-transit, transit time, freight spend), shipment
milestone tracking, master-data validation, freight invoice auditing,
three-way matching, accrual and variance reporting, root-cause analysis, and
SOP development.

> **Data disclosure.** This portfolio project uses public shipment data
> supplemented with simulated enterprise records. The simulated records
> represent data that would ordinarily be stored in confidential ERP, TMS,
> WMS, carrier-contract, and financial systems. The architecture is a
> relational analytics environment simulating data flows across ERP, TMS,
> WMS, carrier, customs, and freight-settlement systems — it does not claim
> professional SAP experience, and none of the data comes from any real
> company.

## Data sources

| Layer | Source | Class |
|---|---|---|
| Shipment lines (10,324) | USAID *Supply Chain Shipment Pricing Data* (SCMS Delivery History Dataset), public domain. The official portal went offline in 2025; the file is downloaded from public mirrors and **verified against a pinned SHA-256** (`918b992d…`). | PUBLIC |
| Solar catalog remap, lanes, reporting dates | Deterministic rules documented in `documentation/source_to_target_mapping.xlsx` | DERIVED |
| Carriers, rate cards, invoices, milestones, PODs, claims, accruals | Seeded Python generation (Phase 2), always derived from the real shipment patterns | SIMULATED |

The source data records pharmaceutical shipments. Real shipment **patterns**
(dates, modes, weights, values, freight costs, origins, destinations) are
preserved; the **product identity** is remapped to a renewable-energy catalog
(e.g. `ARV|Adult → SOLAR_MODULE`). Every staged row keeps lineage to its
original record via `source_record_id`, and original product fields are
retained in `*_raw` columns.

## Architecture

See [documentation/project_architecture.md](documentation/project_architecture.md)
for the full diagram, ERD (Mermaid), and the Phase 1 assumption log.

- **Database:** PostgreSQL 16 (`docker compose up -d`) or SQLite fallback —
  selected via `DATABASE_URL` (see `.env.example`)
- **Pipeline:** Python 3.11, pandas, SQLAlchemy; config-driven
  (`config/project_config.yaml`), fixed random seed, reproducible end-to-end
- **Analytics:** SQL views (`sql/`), Power BI specification + DAX, Excel KPI pack

## How to run (Phase 1)

```bash
python -m pip install -r requirements.txt
cp .env.example .env                # optional; defaults to SQLite

python src/download_data.py         # acquire + checksum-verify source data
python src/profile_data.py          # raw profile, data dictionary, STM workbook
python src/clean_shipments.py       # staging transform + reject ledger
python src/load_database.py         # DDL + load stg_shipment
python -m pytest tests/ -q          # 11 tests
```

## How to run (Phase 2 — enterprise simulation)

```bash
python src/run_phase2.py          # full Phase 2, end to end (~8s)
python -m pytest tests/ -q        # 52 tests (11 Phase 1 + 41 Phase 2)
```

`run_phase2.py` generates the clean master + fact data, validates the clean
baseline (aborts on any critical failure), injects controlled exceptions into a
separate operational layer, loads that layer into the database, refreshes the
Excel docs, and writes [documentation/phase2_summary.md](documentation/phase2_summary.md).
It is deterministic and idempotent — re-running produces byte-identical data.

With PostgreSQL instead of SQLite:

```bash
docker compose up -d
export DATABASE_URL=postgresql+psycopg2://sunlog:sunlog_dev_password@localhost:5432/sunlog
python src/load_database.py && python src/run_phase2.py
```

## What Phase 2 builds

This project combines real public shipment history with deterministically
simulated ERP, TMS, WMS, carrier-contract, freight-invoice, and finance records.
Simulated records are used because company rate cards, invoices, purchase
orders, and settlement data are ordinarily confidential — they are clearly
labeled `data_class = 'SIMULATED'` and are **not** real company data.

From the 10,324 cleaned shipment lines, Phase 2 derives a full operational
environment (row counts, clean baseline):

| Layer | Tables (rows) |
|---|---|
| Master data | 12 carriers, 785 lanes, 20 products, 73 suppliers, 5 warehouses, 136 locations, 2,311 rate cards |
| Operational facts | 10,324 shipments · 6,233 purchase orders · 87,046 milestones · 10,012 freight invoices · 22k invoice lines · PODs · claims · 7,200 capacity records · 41k approvals · 10,324 accruals |

Highlights:
- **Freight calibration is grounded in the real data** — generated freight
  tracks the observed source freight distribution (all-mode expected/observed
  ratio ≈ 1.0), so the freight-audit engine in Phase 3 has realistic numbers.
- **Clean baseline is provably consistent** — 60 internal-consistency checks,
  **zero critical failures**, before any exception exists.
- **2,220 controlled exceptions** across 19 types injected into a separate
  operational layer, each recorded in an exception manifest for Phase 3
  detection testing. Real lateness is inherited from the source, never injected.

See [documentation/phase2_summary.md](documentation/phase2_summary.md) and
[documentation/project_architecture.md](documentation/project_architecture.md)
for the full methodology, and
[documentation/business_requirements.md](documentation/business_requirements.md)
for the business framing.

## Phase 1 findings (real data, verified)

- 10,324 shipment lines, 43 destination countries, 88 origin manufacturing
  sites, 73 vendors; modes Air 59%, Truck 27%, Air Charter 6%, Ocean 4%,
  missing 3.5%.
- 2,445 lines record weight/freight as a cross-reference to another line
  (`See DN-xxxx (ID#:yyyy)`); resolving these lifted weight coverage from
  61.7% to 84.2% and freight-cost coverage from 60.0% to 82.7%.
- Remaining gaps are structural, not random: *Weight Captured Separately*
  (1,507), *Freight Included in Commodity Cost* (1,442), *Invoiced
  Separately* (239) — each kept as an explicit provenance flag.
- 0 rows rejected by hard validation; the reject ledger exists and is loaded
  (empty) so the control exists before it is needed.

## Progress

- [x] **Phase 1 — Foundation:** repo, checksum-verified acquisition, raw
  profile, data dictionary, source-to-target mapping, relational DDL
  (23 tables), staging load, 11 passing tests
- [x] **Phase 2 — Enterprise simulation:** master data, POs, rate cards,
  milestones, invoices + lines, accessorials, PODs, claims, capacity,
  approvals, accruals; clean baseline validated (60 checks, 0 critical);
  2,220 controlled exceptions across 19 types with an exact manifest; 52
  passing tests; reproducible via `python src/run_phase2.py`
- [ ] **Phase 3 — Analytics:** DQ rules, KPIs, freight audit, three-way match,
  accruals, carrier scorecard
- [ ] **Phase 4 — Reporting:** Power BI views + DAX, Excel KPI pack, SOP,
  final README
- [ ] **Phase 5 — QA:** reconciliation, exception-detection verification,
  findings

## Repository map

```
config/          project + exception-injection configuration (YAML)
data/            raw / interim / processed / samples (gitignored except samples)
documentation/   architecture, data dictionary, STM mapping, SOP (Phase 4)
sql/             DDL + analytics SQL (01–03 shipped in Phase 1)
src/             pipeline scripts (download → profile → clean → load)
tests/           pytest suite
dashboard/       Power BI specification (Phase 4)
excel/           Excel KPI pack (Phase 4)
```

## Limitations

- Source shipment lines are pharmaceutical-program deliveries adapted into a
  solar case study; absolute weights/values are real, product identity is not.
- Carrier, invoice, and milestone records are simulated (clearly labeled
  `data_class = 'SIMULATED'`); audit findings quantify detection of
  *controlled, documented* exceptions, not real billing errors.
- No ship-date column exists in the source; `ship_date` is derived in
  Phase 2 from mode-standard transit times and labeled as such.
