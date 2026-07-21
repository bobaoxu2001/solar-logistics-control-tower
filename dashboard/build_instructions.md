# Power BI Build Instructions

1. Run `python src/run_phase3.py` to refresh the database and `data/processed/reporting/` exports.
2. Connect Power BI Desktop to PostgreSQL and select the `sunlog.rpt_*` views, or import the matching CSV exports for the SQLite demo.
3. Create relationships exactly as documented in `dashboard/data_model.md`; use single-direction filtering.
4. Mark `rpt_dim_date[date]` as the date table and sort month name by month number.
5. Copy measures from `dashboard/measures.dax` into a dedicated Measures table and apply percentage/currency formats.
6. Build the six pages in `dashboard/dashboard_specification.md`, preserving the operational versus simulated-data disclosure.
7. Reconcile shipment count, freight spend, exception count, carrier rows, and lane rows to the Excel KPI pack before publishing.
8. Configure refresh credentials for the selected database or file location. Do not claim live ERP/TMS connectivity; this portfolio project refreshes from its reproducible local pipeline.
