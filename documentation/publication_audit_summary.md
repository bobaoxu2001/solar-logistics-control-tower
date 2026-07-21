# Publication Audit Summary

**Final result: PASS.** The repository is portable and locally ready for a public-portfolio review. This local audit does not change repository visibility or rewrite Git history.

## Automated results

| Audit | Result | Issues |
|---|---|---:|
| Required files and assets | PASS | 0 |
| Markdown links | PASS | 0 |
| Portable tracked paths | PASS | 0 |
| Credential patterns | PASS | 0 |
| Personal contact patterns | PASS | 0 |
| Tracked environment files | PASS | 0 |
| Workbook integrity | PASS | 0 |
| Data and exposure disclosure | PASS | 0 |
| Existing Git-history secret patterns | PASS | 0 |
| Existing Git-history local paths | PASS | 0 |
| Existing Git-history personal contact patterns | PASS | 0 |

## Required publication findings

- **Local absolute paths found:** 0 in the publication file set; 0 in existing commit contents.
- **Broken local Markdown links found:** 0.
- **High-confidence secret issues found:** 0 in current tracked text; 0 in existing commit contents.
- **Personal contact patterns found:** 0 in the publication file set; 0 in existing commit contents (Git author metadata is reported separately).
- **Required assets found:** 6 dashboard PNGs, 3 diagram PNGs, and the Excel KPI workbook.
- **Final test count:** 139 tests collected.
- **Git identity metadata:** 2 distinct author names and 2 distinct author email addresses exist in commit metadata. History was not rewritten.
- **Credential handling:** local PostgreSQL examples use an explicit change-me placeholder; `.env` and credential-file patterns are ignored.
- **Personal data:** no personal contact details were found in tracked file content, and the KPI workbook core metadata contains no email or local-path marker. Simulated operational names are generic fictional organizations and functional roles.

## Repository size

- Publication file set, excluding this generated summary: **5.38 MiB**.
- Local checkout excluding `.git` and tool caches, including reproducible ignored data: **132.48 MiB**.
- Raw downloaded dataset, ignored by Git: **3.61 MiB**.
- Generated dashboard/chart/diagram assets: **2.14 MiB**.
- Excel KPI workbook: **2.51 MiB**.
- Dashboard PNGs: **1.04 MiB**.

The largest publication file is the Excel KPI workbook, which remains small enough for a normal GitHub clone. The raw and processed datasets are reproducible and ignored; representative samples, checksum, and deterministic download/generation commands remain tracked. Git LFS is not required.

### Largest publication files

| File | Size |
|---|---:|
| `excel/logistics_kpi_pack.xlsx` | 2.51 MiB |
| `dashboard/screenshots/06_data_quality_controls.png` | 194.05 KiB |
| `dashboard/screenshots/04_freight_audit.png` | 179.52 KiB |
| `dashboard/screenshots/02_shipment_control_tower.png` | 176.72 KiB |
| `dashboard/screenshots/01_executive_overview.png` | 176.65 KiB |
| `dashboard/screenshots/03_carrier_lane_performance.png` | 168.73 KiB |
| `dashboard/screenshots/05_finance_accrual.png` | 166.30 KiB |
| `documentation/diagrams/freight_audit_workflow.png` | 150.93 KiB |
| `documentation/charts/monthly_otif_trend.png` | 118.33 KiB |
| `documentation/diagrams/data_quality_validation.png` | 113.30 KiB |

### Largest publication directories

| Directory | Size |
|---|---:|
| `excel/` | 2.51 MiB |
| `documentation/` | 1.21 MiB |
| `dashboard/` | 1.05 MiB |
| `src/` | 324.41 KiB |
| `data/` | 118.19 KiB |
| `sql/` | 91.04 KiB |
| `tests/` | 52.75 KiB |
| `config/` | 20.33 KiB |
| `(root files)` | 19.41 KiB |
| `.github/` | 2.56 KiB |

## Data attribution and disclosure

The README and `DATA_NOTICE.md` identify the USAID SCMS shipment-history source, offline portal identifier, public mirrors, and pinned SHA-256. They distinguish public shipment patterns from derived solar mapping and simulated enterprise/finance records, state that modeled exposure is not real corporate loss, and include a non-affiliation statement. Original project code and documentation use the MIT License; the external dataset is explicitly excluded because its exact reuse terms were not independently verified from repository evidence.

## Manual GitHub steps remaining

- Add the suggested description, About text, and topics from `documentation/github_metadata.md`.
- Confirm README images, relative links, and the CI badge on GitHub.
- Create tag `v1.0.0` and the suggested GitHub release after publication review.
- Add the final public URL to the resume and portfolio.

## Exact rerun commands

```bash
python3 src/run_publication_audit.py
python3 -m pytest tests/ -q
git diff --check
git status --short
```
