"""Shared fixtures/loaders for Phase 2 tests.

Tests read the artifacts produced by `python src/run_phase2.py`. If they are
missing, the tests skip with a clear instruction rather than failing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
CLEAN = PROJECT_ROOT / "data" / "processed" / "clean"
OPER = PROJECT_ROOT / "data" / "processed" / "operational"
PROCESSED = PROJECT_ROOT / "data" / "processed"

_SKIP = "Phase 2 artifacts missing — run `python src/run_phase2.py` first"


def clean(name: str) -> pd.DataFrame:
    p = CLEAN / f"{name}.csv"
    if not p.exists():
        pytest.skip(_SKIP)
    return pd.read_csv(p)


def oper(name: str) -> pd.DataFrame:
    p = OPER / f"{name}.csv"
    if not p.exists():
        pytest.skip(_SKIP)
    return pd.read_csv(p)


def processed(name: str) -> pd.DataFrame:
    p = PROCESSED / f"{name}.csv"
    if not p.exists():
        pytest.skip(_SKIP)
    return pd.read_csv(p)
