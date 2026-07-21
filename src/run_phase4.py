"""Run deterministic Phase 4 visual, portfolio, and validation generation."""

from __future__ import annotations

import csv
import hashlib
import subprocess
import sys
from pathlib import Path

import build_phase4_docs
import phase4_visuals
import run_phase3
import validate_dashboard_outputs
import validate_excel_kpi_pack
import validate_phase4
from common import DATA_PROCESSED, PROJECT_ROOT, get_logger

log = get_logger("run_phase4")
BASELINE_COMMIT = "eb67a80"
HASH_MANIFEST = PROJECT_ROOT / "documentation" / "phase4_artifact_hashes.csv"


def step(name, function) -> None:
    log.info("=" * 72)
    log.info("STEP: %s", name)
    log.info("=" * 72)
    result = function()
    if result not in (None, 0):
        raise RuntimeError(f"Phase 4 step failed: {name} (rc={result})")


def verify_repository() -> int:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        log.error("Repository HEAD is not at or after required commit %s", BASELINE_COMMIT)
        return 1
    log.info("Confirmed repository is at or after %s", BASELINE_COMMIT)
    return 0


def ensure_phase3() -> int:
    required = [
        DATA_PROCESSED / "sunlog.db",
        DATA_PROCESSED / "reporting" / "rpt_fact_shipment.csv",
        DATA_PROCESSED / "reporting" / "rpt_fact_freight_audit.csv",
        DATA_PROCESSED / "reporting" / "rpt_fact_accrual.csv",
        DATA_PROCESSED / "reporting" / "rpt_fact_data_quality.csv",
        PROJECT_ROOT / "excel" / "logistics_kpi_pack.xlsx",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        log.warning("Missing Phase 3 outputs; running Phase 3: %s", missing)
        return run_phase3.main()
    log.info("Confirmed %d required Phase 3 outputs", len(required))
    return 0


def artifact_paths() -> list[Path]:
    paths = sorted((PROJECT_ROOT / "dashboard" / "screenshots").glob("*.png"))
    paths += sorted((PROJECT_ROOT / "documentation" / "charts").glob("*.png"))
    paths += sorted((PROJECT_ROOT / "documentation" / "diagrams").glob("*.png"))
    paths += sorted((PROJECT_ROOT / "documentation" / "diagrams").glob("*.mmd"))
    paths += [
        PROJECT_ROOT / "dashboard" / "dashboard_metric_reconciliation.csv",
        PROJECT_ROOT / "documentation" / "charts" / "chart_source_reconciliation.csv",
        PROJECT_ROOT / "excel" / "kpi_pack_validation.md",
    ]
    return paths


def hashes() -> dict[str, str]:
    return {
        str(path.relative_to(PROJECT_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in artifact_paths()
    }


def generation_pass() -> int:
    phase4_visuals.generate_all()
    if validate_dashboard_outputs.main():
        return 1
    if validate_excel_kpi_pack.main():
        return 1
    return 0


def idempotency_gate() -> int:
    first = hashes()
    if generation_pass():
        return 1
    second = hashes()
    names = sorted(set(first) | set(second))
    rows = [
        {"artifact": name, "first_sha256": first.get(name, ""), "second_sha256": second.get(name, ""), "match": "PASS" if first.get(name) == second.get(name) else "FAIL"}
        for name in names
    ]
    HASH_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with HASH_MANIFEST.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["artifact", "first_sha256", "second_sha256", "match"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    failures = [row for row in rows if row["match"] == "FAIL"]
    if failures:
        for row in failures:
            log.error("Non-idempotent artifact: %s", row["artifact"])
        return 1
    log.info("Idempotency: %d/%d artifact hashes match", len(rows), len(rows))
    return 0


def main() -> int:
    try:
        step("Verify repository baseline", verify_repository)
        step("Confirm or rebuild Phase 3 outputs", ensure_phase3)
        step("Generate dashboard, chart, and diagram artifacts", generation_pass)
        step("Repeat generation and compare artifact hashes", idempotency_gate)
        step("Update Phase 4 summary", build_phase4_docs.main)
        step("Run Phase 4 validation gate", validate_phase4.main)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1
    log.info("=" * 72)
    log.info("PHASE 4 COMPLETE")
    log.info("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
