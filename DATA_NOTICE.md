# Data and Third-Party Content Notice

This notice separates the repository's original portfolio materials from external source data and simulated enterprise records. It does not replace the terms of any external data provider.

## Original project materials

The original Python and SQL code, tests, documentation, dashboard specifications, generated visual layouts, and deterministic simulation logic authored for this portfolio project are covered by the repository's [MIT License](LICENSE).

## Public-source shipment data

The shipment-history foundation is derived from the USAID **Supply Chain Shipment Pricing Data** (also identified in the repository as the SCMS Delivery History Dataset), originally published by USAID under portal identifier `a3rc-nmf6` at `data.usaid.gov`. The original portal is offline. The pipeline therefore acquires the source from disclosed public mirrors and accepts it only when its SHA-256 matches the pinned value in `config/project_config.yaml`.

The exact redistribution or reuse terms were not independently verified from the current repository evidence. The external dataset is not relicensed under this repository's MIT License. Users must review the original source terms before downloading, redistributing, or reusing the source data.

Raw and processed datasets are excluded from Git where applicable. They can be regenerated through the documented, checksum-verified pipeline; only representative samples and final recruiter-facing assets are tracked.

## Simulated enterprise data

Carriers, rate cards, invoices, shipment milestones, proofs of delivery (PODs), claims, approvals, accruals, and financial exposures are deterministic simulated portfolio records. They do not represent a real company's data, losses, savings, invoices, contracts, or operational results. Detected financial amounts are modeled control exposures that require business review, not confirmed billing errors or realized recoveries.

## Non-affiliation

This independent portfolio project is not affiliated with USAID, any mirror maintainer, any target employer, any real renewable-energy company, or any fictional carrier represented in the simulation.
