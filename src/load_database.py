"""Create the database schema and load Phase 1 staging data.

Target database comes from the DATABASE_URL environment variable
(PostgreSQL primary; SQLite fallback — see .env.example). On SQLite the
PostgreSQL DDL is adapted automatically (schema qualifiers stripped).

Usage:
    python src/load_database.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, text

from common import DATA_PROCESSED, PROJECT_ROOT, SQL_DIR, database_url, get_logger, load_config

log = get_logger("load_database")

DDL_FILES = ["01_create_schema.sql", "02_create_tables.sql", "03_create_indexes.sql"]


def adapt_sql_for_sqlite(sql: str, schema: str) -> str:
    sql = re.sub(rf"\b{schema}\.", "", sql)
    sql = re.sub(r"CREATE SCHEMA[^;]+;", "", sql, flags=re.IGNORECASE)
    return sql


def run_ddl(engine, schema: str) -> None:
    is_sqlite = engine.dialect.name == "sqlite"
    with engine.begin() as conn:
        for fname in DDL_FILES:
            if is_sqlite and fname == "01_create_schema.sql":
                continue
            sql = (SQL_DIR / fname).read_text(encoding="utf-8")
            if is_sqlite:
                sql = adapt_sql_for_sqlite(sql, schema)
            for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                conn.execute(text(stmt))
            log.info("Executed %s", fname)


def qualified(table: str, engine, schema: str) -> str:
    return table if engine.dialect.name == "sqlite" else f"{schema}.{table}"


def main() -> int:
    cfg = load_config()
    schema = cfg["database"]["schema"]
    url = database_url(cfg)
    engine = create_engine(url)
    log.info("Target database: %s (%s)", url.split("@")[-1], engine.dialect.name)

    stg_path = DATA_PROCESSED / "stg_shipment.csv"
    rej_path = DATA_PROCESSED / "rejected_records.csv"
    if not stg_path.exists():
        log.error("stg_shipment.csv missing — run src/clean_shipments.py first.")
        return 1

    run_ddl(engine, schema)

    date_cols = [
        "pq_first_sent_date", "po_sent_date", "scheduled_delivery_date",
        "actual_delivery_date", "delivery_recorded_date",
        "reporting_scheduled_delivery_date", "reporting_actual_delivery_date",
    ]
    stg = pd.read_csv(stg_path, parse_dates=date_cols)
    to_schema = None if engine.dialect.name == "sqlite" else schema

    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {qualified('stg_shipment', engine, schema)}"))
        stg.to_sql("stg_shipment", conn, schema=to_schema, if_exists="append", index=False)

        # Rejected records (kept even when empty — the ledger must exist)
        rej = pd.read_csv(rej_path, dtype=str) if rej_path.exists() else pd.DataFrame()
        conn.execute(text(f"DELETE FROM {qualified('stg_rejected_record', engine, schema)}"))
        if not rej.empty:
            now = datetime.now(timezone.utc)
            ledger = pd.DataFrame({
                "reject_id": [str(uuid.uuid4()) for _ in range(len(rej))],
                "source_record_id": rej.get("ID"),
                "rejection_reason": rej["rejection_reason"],
                "raw_payload": rej.drop(columns=["rejection_reason"]).apply(
                    lambda r: json.dumps(r.dropna().to_dict()), axis=1
                ),
                "rejected_at": now,
            })
            ledger.to_sql("stg_rejected_record", conn, schema=to_schema, if_exists="append", index=False)

        # Provenance
        raw_path = PROJECT_ROOT / cfg["source_dataset"]["local_path"]
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        prov_table = qualified("meta_source_provenance", engine, schema)
        conn.execute(text(f"DELETE FROM {prov_table} WHERE source_name = :n"),
                     {"n": cfg["source_dataset"]["name"]})
        conn.execute(
            text(f"""INSERT INTO {prov_table}
                     (source_name, source_url, sha256, row_count, loaded_at, notes)
                     VALUES (:name, :url, :sha, :rows, :ts, :notes)"""),
            {
                "name": cfg["source_dataset"]["name"],
                "url": cfg["source_dataset"]["original_portal"],
                "sha": digest,
                "rows": len(stg),
                "ts": datetime.now(timezone.utc),
                "notes": "Public USAID dataset; portal offline, acquired from checksum-verified mirror.",
            },
        )

        # Audit thresholds from exception_config.yaml
        exc_cfg = load_config("exception_config.yaml")
        thr_table = qualified("meta_audit_threshold", engine, schema)
        conn.execute(text(f"DELETE FROM {thr_table}"))
        for name, value in exc_cfg["audit_thresholds"].items():
            conn.execute(
                text(f"INSERT INTO {thr_table} (threshold_name, threshold_value, description) "
                     f"VALUES (:n, :v, :d)"),
                {"n": name, "v": value, "d": "Freight-audit tolerance (config-driven)"},
            )

    with engine.connect() as conn:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {qualified('stg_shipment', engine, schema)}")).scalar()
    log.info("Loaded stg_shipment: %d rows | rejected ledger: %d rows", n, len(rej) if rej_path.exists() else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
