"""Shared Phase 2 generation utilities: determinism, IDs, geography, DB I/O.

Determinism model
-----------------
Every stochastic choice is drawn from a per-record RNG whose seed is a hash of
(master_seed, salt, natural_key). This makes draws independent of iteration
order and fully reproducible: the same seed always yields identical output, and
re-running never shifts values. IDs are derived from stable natural keys, so
re-running is idempotent (no duplicate rows).
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
import pandas as pd
from sqlalchemy import inspect, text

from common import SQL_DIR, load_config

# --- Provenance constants --------------------------------------------------
PUBLIC = "PUBLIC"
DERIVED = "DERIVED"
SIMULATED = "SIMULATED"


_SEED_CACHE: int | None = None


def master_seed() -> int:
    # Cached: this is called on every per-record draw (~300k times per run);
    # re-reading the YAML each time would dominate runtime.
    global _SEED_CACHE
    if _SEED_CACHE is None:
        _SEED_CACHE = int(load_config()["random_seed"])
    return _SEED_CACHE


def _digest_seed(*parts) -> int:
    raw = ":".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.md5(raw).hexdigest()[:12], 16)


def record_rng(salt: str, key) -> np.random.Generator:
    """Deterministic per-record generator: stable for a given (salt, key)."""
    return np.random.default_rng(_digest_seed(master_seed(), salt, key))


def stream_rng(salt: str) -> np.random.Generator:
    """Deterministic generator for a whole stream (order-sensitive; use only
    when the consuming order is itself deterministic)."""
    return np.random.default_rng(_digest_seed(master_seed(), salt))


def det_hash(salt: str, key) -> int:
    """Stable integer hash for deterministic ordering / selection."""
    return _digest_seed(master_seed(), salt, key)


# --- Geography -------------------------------------------------------------
COUNTRY_REGION = {
    # Africa
    "Angola": "AFRICA", "Benin": "AFRICA", "Botswana": "AFRICA", "Burkina Faso": "AFRICA",
    "Burundi": "AFRICA", "Cameroon": "AFRICA", "Congo, DRC": "AFRICA", "Côte d'Ivoire": "AFRICA",
    "Ethiopia": "AFRICA", "Ghana": "AFRICA", "Guinea": "AFRICA", "Kenya": "AFRICA",
    "Lesotho": "AFRICA", "Liberia": "AFRICA", "Libya": "AFRICA", "Malawi": "AFRICA",
    "Mali": "AFRICA", "Mozambique": "AFRICA", "Namibia": "AFRICA", "Nigeria": "AFRICA",
    "Rwanda": "AFRICA", "Senegal": "AFRICA", "Sierra Leone": "AFRICA", "South Africa": "AFRICA",
    "South Sudan": "AFRICA", "Sudan": "AFRICA", "Swaziland": "AFRICA", "Tanzania": "AFRICA",
    "Togo": "AFRICA", "Uganda": "AFRICA", "Zambia": "AFRICA", "Zimbabwe": "AFRICA",
    # Asia
    "Afghanistan": "ASIA", "Pakistan": "ASIA", "Vietnam": "ASIA", "Thailand": "ASIA",
    "China": "ASIA", "Japan": "ASIA", "Korea": "ASIA", "India": "ASIA",
    # Central Asia / Eurasia
    "Kazakhstan": "EURASIA", "Kyrgyzstan": "EURASIA",
    # Middle East
    "Lebanon": "MIDDLE_EAST",
    # Americas
    "Belize": "AMERICAS", "Dominican Republic": "AMERICAS", "Guatemala": "AMERICAS",
    "Guyana": "AMERICAS", "Haiti": "AMERICAS", "USA": "AMERICAS", "Canada": "AMERICAS",
    "Puerto Rico": "AMERICAS",
    # Europe
    "UK": "EUROPE", "Germany": "EUROPE", "France": "EUROPE", "Switzerland": "EUROPE",
    "Italy": "EUROPE", "Spain": "EUROPE", "Cyprus": "EUROPE", "Greece": "EUROPE",
    "Netherlands": "EUROPE", "Norway": "EUROPE", "Poland": "EUROPE",
    # Oceania
    "Australia": "OCEANIA",
}

# Southern-Africa subset routes to the Southern Africa DC (WH02); rest of
# Africa to the West Africa DC (WH01).
SOUTHERN_AFRICA = {
    "South Africa", "Botswana", "Namibia", "Lesotho", "Swaziland", "Zimbabwe",
    "Zambia", "Malawi", "Mozambique",
}

# Keyword → canonical country for parsing the free-text manufacturing_site.
# Order matters (longer / more specific first). Missing → None (never guessed).
_SITE_COUNTRY_PATTERNS = [
    ("South Africa", "South Africa"), ("Cape Town", "South Africa"), ("Aranda", "South Africa"),
    ("India", "India"), (" IN", "India"), ("INDIA", "India"), ("Nashik", "India"),
    ("Hyderabad", "India"), ("Daman", "India"), ("Goa", "India"), ("Mahar", "India"),
    ("USA", "USA"), (" US", "USA"), ("Chicago", "USA"), ("Elkton", "USA"), ("P'burg USA", "USA"),
    ("Germany", "Germany"), (" DE", "Germany"), ("Wiesbaden", "Germany"),
    ("Ludwigshafen", "Germany"), ("Oranienburg", "Germany"),
    ("UK", "UK"), ("Crawley", "UK"), ("Barnard Castle", "UK"), ("Ware", "UK"),
    ("France", "France"), ("Japan", "Japan"), ("Korea", "Korea"), ("Thailand", "Thailand"),
    ("China", "China"), ("Shanghai", "China"),
    ("Switzerland", "Switzerland"), ("Basel", "Switzerland"),
    ("Canada", "Canada"), ("Mississauga", "Canada"),
    ("Madrid", "Spain"), ("Anagni", "Italy"), (" IT", "Italy"),
    ("Cyprus", "Cyprus"), (" CY", "Cyprus"), (" GR", "Greece"), (" NL", "Netherlands"),
    ("Norway", "Norway"), ("Poland", "Poland"), ("Puerto Rico", "Puerto Rico"),
    ("Australia", "Australia"),
]


def region_of(country: str | None) -> str:
    if country is None or (isinstance(country, float) and pd.isna(country)):
        return "UNKNOWN"
    return COUNTRY_REGION.get(country, "UNKNOWN")


def detect_site_country(site: str | None):
    """Return (country, method). method is COUNTRY_PARSED or UNRESOLVED."""
    if site is None or (isinstance(site, float) and pd.isna(site)):
        return None, "UNRESOLVED"
    padded = f" {site} "
    for kw, country in _SITE_COUNTRY_PATTERNS:
        if kw in padded:
            return country, "COUNTRY_PARSED"
    return None, "UNRESOLVED"


def warehouse_for(country: str | None):
    """Map a destination country to a regional DC (used for From RDC flow)."""
    region = region_of(country)
    if region == "AFRICA":
        return "WH02" if country in SOUTHERN_AFRICA else "WH01"
    return {
        "ASIA": "WH03", "EURASIA": "WH03", "MIDDLE_EAST": "WH03",
        "AMERICAS": "WH04", "EUROPE": "WH05", "OCEANIA": "WH03",
    }.get(region, "WH03")


# --- Database I/O ----------------------------------------------------------
def adapt_sql_for_sqlite(sql: str, schema: str) -> str:
    sql = re.sub(rf"\b{schema}\.", "", sql)
    sql = re.sub(r"CREATE SCHEMA[^;]+;", "", sql, flags=re.IGNORECASE)
    return sql


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL on statement semicolons without corrupting quoted text.

    Handles SQL-standard escaped single quotes (``''``) and ``--`` line
    comments.  This deliberately stays small and portable: the project SQL
    does not use dollar-quoted functions or procedural blocks.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_quote = False
    in_line_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                buf.append(ch)
            i += 1
            continue
        if not in_quote and ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if ch == "'":
            buf.append(ch)
            if in_quote and nxt == "'":
                buf.append(nxt)
                i += 2
                continue
            in_quote = not in_quote
            i += 1
            continue
        if ch == ";" and not in_quote:
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
        else:
            buf.append(ch)
        i += 1
    statement = "".join(buf).strip()
    if statement:
        statements.append(statement)
    if in_quote:
        raise ValueError("Unterminated single-quoted SQL string")
    return statements


def apply_ddl(engine, filename: str, schema: str) -> None:
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    if engine.dialect.name == "sqlite":
        sql = adapt_sql_for_sqlite(sql, schema)
    with engine.begin() as conn:
        for stmt in split_sql_statements(sql):
            conn.execute(text(stmt))


def load_table(engine, df: pd.DataFrame, table: str, schema: str) -> int:
    """Idempotent load into a pre-existing table: DELETE all rows then append."""
    to_schema = None if engine.dialect.name == "sqlite" else schema
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table if to_schema is None else schema + '.' + table}"))
        if len(df):
            df.to_sql(table, conn, schema=to_schema, if_exists="append", index=False)
    return len(df)


def replace_table(engine, df: pd.DataFrame, table: str, schema: str) -> int:
    """Create or refresh a DataFrame-backed table without dropping dependents.

    On rerun, DELETE+append preserves reporting views that depend on the table
    (important on PostgreSQL, where DROP TABLE would otherwise be rejected).
    """
    to_schema = None if engine.dialect.name == "sqlite" else schema
    exists = table in inspect(engine).get_table_names(schema=to_schema)
    if exists:
        qualified = table if to_schema is None else f'{schema}.{table}'
        with engine.begin() as conn:
            conn.execute(text(f"DELETE FROM {qualified}"))
            if len(df):
                df.to_sql(table, conn, schema=to_schema, if_exists="append", index=False)
    else:
        df.to_sql(table, engine, schema=to_schema, if_exists="fail", index=False)
    return len(df)
