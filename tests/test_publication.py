"""Public-portfolio portability, links, disclosure, and health tests."""

from __future__ import annotations

import sys
from pathlib import Path

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
