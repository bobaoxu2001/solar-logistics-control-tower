"""Public-portfolio portability, links, disclosure, and health tests."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import check_repository_health as health  # noqa: E402


def test_repository_health_checks_all_pass():
    checks = health.run_health_checks()
    assert checks
    assert all(check["status"] == "PASS" for check in checks), checks


def test_tracked_text_has_no_machine_specific_absolute_paths():
    assert health.scan_local_paths() == []


def test_repository_markdown_links_are_relative_and_resolve():
    assert health.scan_markdown_links() == []


def test_tracked_text_has_no_high_confidence_secret_patterns():
    assert health.scan_secrets() == []


def test_publication_content_has_no_personal_contact_patterns():
    assert health.scan_personal_info() == []


def test_no_real_environment_file_is_tracked():
    assert health.tracked_env_issues() == []


def test_required_publication_assets_exist():
    assert health.required_asset_issues() == []


def test_ci_workflow_has_required_triggers_and_least_privilege():
    path = PROJECT_ROOT / ".github" / "workflows" / "tests.yml"
    assert path.exists()
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = workflow["on"]
    assert {"push", "pull_request", "workflow_dispatch"} <= set(triggers)
    assert triggers["push"]["branches"] == ["master"]
    assert triggers["pull_request"]["branches"] == ["master"]
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "true"


def test_ci_workflow_uses_python_311_and_dependency_cache():
    workflow = yaml.load(
        (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    steps = workflow["jobs"]["validate"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    setup = next(step for step in steps if step.get("uses", "").startswith("actions/setup-python@"))
    assert checkout["with"]["fetch-depth"] == "0"
    assert setup["with"]["python-version"] == "3.11"
    assert setup["with"]["cache"] == "pip"


def test_ci_workflow_runs_full_validation_commands():
    text = (PROJECT_ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    for command in [
        "python -m pytest tests/ -q",
        "python src/check_repository_health.py",
        "python src/run_publication_audit.py",
        "git diff --check",
    ]:
        assert command in text


def test_mit_license_is_standard_and_names_copyright_holder():
    text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License\n")
    assert "Copyright (c) 2026 Ao Xu" in text
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


def test_data_notice_preserves_external_dataset_license_boundary():
    text = (PROJECT_ROOT / "DATA_NOTICE.md").read_text(encoding="utf-8")
    assert "Supply Chain Shipment Pricing Data" in text
    assert "original portal is offline" in text
    assert "exact redistribution or reuse terms were not independently verified" in text
    assert "external dataset is not relicensed under this repository's MIT License" in text
    assert "deterministic simulated portfolio records" in text


def test_readme_has_ci_python_and_mit_badges():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "actions/workflows/tests.yml/badge.svg" in readme
    assert "python-3.11%2B" in readme
    assert "license-MIT" in readme


def test_readme_links_license_and_data_notice():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "[MIT License](LICENSE)" in readme
    assert "[Data and third-party content notice](DATA_NOTICE.md)" in readme
    assert "External public-source data is not covered by the MIT License" in readme


def test_precision_explanation_is_consistent_in_reviewer_documents():
    paths = [
        "README.md",
        "documentation/interview_materials.md",
        "documentation/interview_demo_script.md",
        "documentation/project_case_study.md",
        "documentation/recruiter_walkthrough.md",
    ]
    for relative in paths:
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8").lower()
        assert "54.94%" in text, relative
        assert "rule-based" in text, relative
        assert "business review" in text, relative


def test_control_system_is_not_described_as_a_machine_learning_model():
    documentation = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [PROJECT_ROOT / "README.md", *(PROJECT_ROOT / "documentation").glob("*.md")]
    )
    assert not re.search(r"(?i)\b(?:machine[- ]learning|ml)\s+model\b", documentation)
    assert "not a machine-learning classifier" in documentation.lower()


def test_portfolio_guide_has_three_viewing_paths():
    guide = (PROJECT_ROOT / "PORTFOLIO_GUIDE.md").read_text(encoding="utf-8")
    assert "## Recruiter: 2 minutes" in guide
    assert "## Hiring manager: 5 minutes" in guide
    assert "## Interviewer: 10 minutes" in guide


def test_readme_has_public_simulated_affiliation_and_source_terms_disclosures():
    assert health.disclosure_issues() == []


def test_financial_exposure_is_always_identified_as_modeled_in_readme_opening():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    opening = readme.split("## Executive dashboard preview", 1)[0].lower()
    assert "$2.48m" in opening
    assert "modeled financial exposure" in opening
    assert "modeled within simulated enterprise records" in opening


def test_publication_audit_summary_exists_and_records_pass():
    summary = PROJECT_ROOT / "documentation" / "publication_audit_summary.md"
    assert summary.exists()
    text = summary.read_text(encoding="utf-8")
    assert "**Final result: PASS.**" in text
    assert "Local absolute paths found:** 0" in text
    assert "Broken local Markdown links found:** 0" in text
    assert "High-confidence secret issues found:** 0" in text
