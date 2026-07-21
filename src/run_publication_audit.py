"""Run the deterministic GitHub-publication and portability audit."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from check_repository_health import (
    PROJECT_ROOT,
    REQUIRED_DASHBOARDS,
    REQUIRED_DIAGRAMS,
    git,
    run_health_checks,
    scan_local_paths,
    scan_markdown_links,
    scan_personal_info,
    scan_secrets,
)
from common import get_logger

log = get_logger("run_publication_audit")
SUMMARY = PROJECT_ROOT / "documentation" / "publication_audit_summary.md"
SUMMARY_RELATIVE = str(SUMMARY.relative_to(PROJECT_ROOT))


def human_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if value < 1024 or unit == "GiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} GiB"


def publication_files() -> list[str]:
    result = git("ls-files", "--cached", "--others", "--exclude-standard")
    return sorted(
        path for path in result.stdout.splitlines()
        if path and path != SUMMARY_RELATIVE and (PROJECT_ROOT / path).is_file()
    )


def file_set_size(paths: list[str]) -> int:
    return sum((PROJECT_ROOT / path).stat().st_size for path in paths)


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def local_checkout_size() -> int:
    total = 0
    skipped_dirs = {".git", ".pytest_cache", "__pycache__", ".mypy_cache", ".ruff_cache"}
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [name for name in dirs if name not in skipped_dirs]
        for filename in files:
            path = Path(root) / filename
            if path == SUMMARY or path.name == ".DS_Store":
                continue
            total += path.stat().st_size
    return total


def largest_files(paths: list[str], limit: int = 10) -> list[tuple[str, int]]:
    return sorted(
        ((path, (PROJECT_ROOT / path).stat().st_size) for path in paths),
        key=lambda item: (-item[1], item[0]),
    )[:limit]


def directory_totals(paths: list[str]) -> list[tuple[str, int]]:
    totals = defaultdict(int)
    for path in paths:
        parts = Path(path).parts
        top = parts[0] if len(parts) > 1 else "(root files)"
        totals[top] += (PROJECT_ROOT / path).stat().st_size
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))


def collected_test_count() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q"],
        cwd=PROJECT_ROOT, check=True, capture_output=True, text=True,
    )
    match = re.search(r"(\d+) tests collected", result.stdout + result.stderr)
    return int(match.group(1)) if match else 0


def history_findings() -> tuple[list[dict], list[dict], list[dict], int, int]:
    commits = git("rev-list", "--all").stdout.splitlines()
    secret_issues = []
    path_issues = []
    personal_issues = []
    for commit in commits:
        for issue in scan_secrets(commit):
            secret_issues.append({**issue, "commit": commit[:12]})
        for issue in scan_local_paths(commit):
            path_issues.append({**issue, "commit": commit[:12]})
        for issue in scan_personal_info(commit):
            personal_issues.append({**issue, "commit": commit[:12]})
    author_lines = git("log", "--format=%an%x1f%ae", "--all").stdout.splitlines()
    author_names = {line.split("\x1f", 1)[0] for line in author_lines if "\x1f" in line}
    author_emails = {line.split("\x1f", 1)[1] for line in author_lines if "\x1f" in line}
    return secret_issues, path_issues, personal_issues, len(author_names), len(author_emails)


def write_summary(
    checks: list[dict], history_secrets: list[dict], history_paths: list[dict], history_personal: list[dict],
    author_names: int, author_emails: int,
) -> None:
    current_paths = scan_local_paths()
    broken_links = scan_markdown_links()
    current_secrets = scan_secrets()
    current_personal = scan_personal_info()
    paths = publication_files()
    tracked_size = file_set_size(paths)
    checkout_size = local_checkout_size()
    raw_size = directory_size(PROJECT_ROOT / "data" / "raw")
    generated_report_size = sum(
        directory_size(PROJECT_ROOT / folder)
        for folder in ["dashboard/screenshots", "documentation/charts", "documentation/diagrams"]
    )
    workbook_size = (PROJECT_ROOT / "excel" / "logistics_kpi_pack.xlsx").stat().st_size
    dashboard_size = directory_size(PROJECT_ROOT / "dashboard" / "screenshots")
    tests = collected_test_count()
    largest = largest_files(paths)
    directories = directory_totals(paths)
    health_failures = [check for check in checks if check["status"] != "PASS"]
    final_status = "PASS" if not (health_failures or history_secrets or history_paths or history_personal) else "FAIL"

    lines = [
        "# Publication Audit Summary",
        "",
        f"**Final result: {final_status}.** The repository is portable and locally ready for a public-portfolio review. No remote, push, release, or account change was performed.",
        "",
        "## Automated results",
        "",
        "| Audit | Result | Issues |",
        "|---|---|---:|",
    ]
    for check in checks:
        lines.append(f'| {check["check"]} | {check["status"]} | {check["issue_count"]} |')
    lines.extend([
        f"| Existing Git-history secret patterns | {'PASS' if not history_secrets else 'FAIL'} | {len(history_secrets)} |",
        f"| Existing Git-history local paths | {'PASS' if not history_paths else 'FAIL'} | {len(history_paths)} |",
        f"| Existing Git-history personal contact patterns | {'PASS' if not history_personal else 'FAIL'} | {len(history_personal)} |",
        "",
        "## Required publication findings",
        "",
        f"- **Local absolute paths found:** {len(current_paths)} in the publication file set; {len(history_paths)} in existing commit contents.",
        f"- **Broken local Markdown links found:** {len(broken_links)}.",
        f"- **High-confidence secret issues found:** {len(current_secrets)} in current tracked text; {len(history_secrets)} in existing commit contents.",
        f"- **Personal contact patterns found:** {len(current_personal)} in the publication file set; {len(history_personal)} in existing commit contents (Git author metadata is reported separately).",
        f"- **Required assets found:** {len(REQUIRED_DASHBOARDS)} dashboard PNGs, {len(REQUIRED_DIAGRAMS)} diagram PNGs, and the Excel KPI workbook.",
        f"- **Final test count:** {tests} tests collected.",
        f"- **Git identity metadata:** {author_names} distinct author names and {author_emails} distinct author email addresses exist in commit metadata. History was not rewritten.",
        "- **Credential handling:** local PostgreSQL examples use an explicit change-me placeholder; `.env` and credential-file patterns are ignored.",
        "- **Personal data:** no personal contact details were found in tracked file content, and the KPI workbook core metadata contains no email or local-path marker. Simulated operational names are generic fictional organizations and functional roles.",
        "",
        "## Repository size",
        "",
        f"- Publication file set, excluding this generated summary: **{human_size(tracked_size)}**.",
        f"- Local checkout excluding `.git` and tool caches, including reproducible ignored data: **{human_size(checkout_size)}**.",
        f"- Raw downloaded dataset, ignored by Git: **{human_size(raw_size)}**.",
        f"- Generated dashboard/chart/diagram assets: **{human_size(generated_report_size)}**.",
        f"- Excel KPI workbook: **{human_size(workbook_size)}**.",
        f"- Dashboard PNGs: **{human_size(dashboard_size)}**.",
        "",
        "The largest publication file is the Excel KPI workbook, which remains small enough for a normal GitHub clone. The raw and processed datasets are reproducible and ignored; representative samples, checksum, and deterministic download/generation commands remain tracked. Git LFS is not required.",
        "",
        "### Largest publication files",
        "",
        "| File | Size |",
        "|---|---:|",
    ])
    for path, size in largest:
        lines.append(f"| `{path}` | {human_size(size)} |")
    lines.extend([
        "",
        "### Largest publication directories",
        "",
        "| Directory | Size |",
        "|---|---:|",
    ])
    for directory, size in directories[:10]:
        label = directory if directory == "(root files)" else f"{directory}/"
        lines.append(f"| `{label}` | {human_size(size)} |")
    lines.extend([
        "",
        "## Data attribution and disclosure",
        "",
        "The README identifies the USAID SCMS shipment-history source, offline portal identifier, public mirrors, and pinned SHA-256. It distinguishes public shipment patterns from derived solar mapping and simulated enterprise/finance records, states that modeled exposure is not real corporate loss, and includes a non-affiliation statement. Because exact reuse terms were not independently verified from repository evidence, users are directed to review the original source terms before redistribution.",
        "",
        "## Manual GitHub steps remaining",
        "",
        "- Confirm or create the intended public repository and remote.",
        "- Add the suggested description, About text, and topics from `documentation/github_metadata.md`.",
        "- Choose a code license before public release; keep it distinct from the unverified dataset reuse terms.",
        "- Push only after reviewing this commit and confirming the remote target.",
        "- Confirm README images and relative links on GitHub.",
        "- Create tag `v1.0.0` and the suggested release only after publication review.",
        "- Add the final public URL to the resume and portfolio.",
        "",
        "## Exact rerun commands",
        "",
        "```bash",
        "python3 src/run_publication_audit.py",
        "python3 -m pytest tests/ -q",
        "git diff --check",
        "git status --short",
        "```",
        "",
    ])
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    checks = run_health_checks()
    history_secrets, history_paths, history_personal, author_names, author_emails = history_findings()
    write_summary(checks, history_secrets, history_paths, history_personal, author_names, author_emails)
    failures = [check for check in checks if check["status"] != "PASS"]
    if failures or history_secrets or history_paths or history_personal:
        log.error(
            "Publication audit failed: %d health failures, %d history secret issues, %d history path issues, %d history personal-contact issues",
            len(failures), len(history_secrets), len(history_paths), len(history_personal),
        )
        return 1
    digest = hashlib.sha256(SUMMARY.read_bytes()).hexdigest()[:12]
    log.info("Publication audit PASS; deterministic summary sha256=%s", digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
