"""Build the DuckDB warehouse from the collected CSV files.

The database is derived, not precious: it is rebuilt from scratch in seconds
and never committed. The CSV files on the `data` branch remain the source of
truth, so a corrupted or outdated database is fixed by rebuilding, never by
repairing.
"""

import os
from pathlib import Path

import duckdb

from collector import config

HERE = Path(__file__).parent
SCHEMA_PATH = HERE / "schema.sql"
QUERIES_DIR = HERE / "queries"

DEFAULT_DATA_DIR = "archive/data"
DEFAULT_DATABASE = "air.duckdb"


def available_queries() -> list[str]:
    """Names of the questions that can be asked, taken from the .sql files."""
    return sorted(path.stem for path in QUERIES_DIR.glob("*.sql"))


def query_text(name: str) -> str:
    path = QUERIES_DIR / f"{name}.sql"
    if not path.is_file():
        known = ", ".join(available_queries())
        raise FileNotFoundError(f"unknown query '{name}'. Available: {known}")
    return path.read_text(encoding="utf-8")


def build(data_dir: str = DEFAULT_DATA_DIR, database: str = DEFAULT_DATABASE) -> dict:
    """(Re)build the whole database and return a short summary."""
    csv_glob = os.path.join(data_dir, "air-quality-*.csv")
    runs_path = os.path.join(data_dir, config.RUN_LOG_NAME)

    connection = duckdb.connect(database)
    connection.execute("SET VARIABLE csv_glob = ?", [csv_glob])
    connection.execute("SET VARIABLE runs_path = ?", [runs_path])
    connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    # The run log may not exist yet on a fresh checkout. Its absence is not an
    # error -- the table simply stays empty, and every query keeps working.
    if os.path.exists(runs_path):
        # BY NAME tolerates a log written before a column existed: an archive
        # that has never seen an outage carries no `error` key at all.
        connection.execute("""
            INSERT INTO runs BY NAME
            SELECT * FROM read_json_auto(
                getvariable('runs_path'), format = 'newline_delimited'
            )
        """)

    summary = connection.execute("""
        SELECT count(*)                       AS rows,
               count(DISTINCT site)           AS sites,
               count(DISTINCT species)        AS species,
               count(DISTINCT CAST(measured_at AS DATE)) AS days,
               min(measured_at)               AS first_hour,
               max(measured_at)               AS last_hour
        FROM readings
    """).fetchone()
    gaps = connection.execute("SELECT count(*) FROM gaps").fetchone()[0]
    outages = connection.execute(
        "SELECT count(*) FROM runs WHERE outcome <> 'ok'"
    ).fetchone()[0]
    connection.close()

    keys = ["rows", "sites", "species", "days", "first_hour", "last_hour"]
    return dict(zip(keys, summary)) | {"gaps": gaps, "outages": outages}
