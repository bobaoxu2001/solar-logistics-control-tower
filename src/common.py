"""Shared helpers: project paths, configuration loading, logging."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_INTERIM = PROJECT_ROOT / "data" / "interim"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_SAMPLES = PROJECT_ROOT / "data" / "samples"
DOCS_DIR = PROJECT_ROOT / "documentation"
SQL_DIR = PROJECT_ROOT / "sql"


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)


def load_config(name: str = "project_config.yaml") -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def database_url(cfg: dict | None = None) -> str:
    """DATABASE_URL env var wins; fall back to the configured SQLite path."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    cfg = cfg or load_config()
    default = cfg["database"]["default_url"]
    if default.startswith("sqlite:///") and not default.startswith("sqlite:////"):
        # anchor the relative SQLite path to the project root
        rel = default.removeprefix("sqlite:///")
        return f"sqlite:///{PROJECT_ROOT / rel}"
    return default


def ensure_dirs() -> None:
    for d in (DATA_RAW, DATA_INTERIM, DATA_PROCESSED, DATA_SAMPLES):
        d.mkdir(parents=True, exist_ok=True)
