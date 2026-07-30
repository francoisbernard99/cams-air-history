"""Writing collected data to disk.

One CSV file per calendar day, whatever range was requested. That invariant is
what makes the collector self-healing: refetching a window simply rewrites the
days it covers, so a gap left by an outage closes on its own at the next run.

Week 3: these files will feed a DuckDB database -- see ROADMAP.md.
"""

import csv
import os
import tempfile
from typing import Iterable

from collector import config


def output_path(directory: str, stamp: str) -> str:
    """Path of the file holding one calendar day."""
    return os.path.join(directory, f"air-quality-{stamp}.csv")


def group_by_date(rows: Iterable[dict]) -> dict[str, list[dict]]:
    """Split rows by calendar day, taken from the timestamp.

    Rows are held in memory, so a single call should stay within about a year
    of data. Backfilling further is done one year at a time -- see the README.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["timestamp"][:10], []).append(row)
    return grouped


def write_daily(rows: Iterable[dict], directory: str) -> dict[str, int]:
    """Write one file per day and return {date: rows written}."""
    return {
        date: write_rows(day_rows, output_path(directory, date))
        for date, day_rows in sorted(group_by_date(rows).items())
    }


def write_rows(rows: Iterable[dict], path: str) -> int:
    """Write rows as CSV and return how many were written.

    Writing goes through a temporary file that is renamed at the end. If the
    program is interrupted midway, it leaves behind no half-written file that a
    later read would mistake for a complete one.

    Rewriting an existing day is deliberate: CAMS revises its analyses, and the
    rename is atomic, so a reader either sees the old file or the new one --
    never a mixture.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    written = 0
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=directory, delete=False, suffix=".tmp"
    )
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=config.COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
                written += 1
        os.replace(handle.name, path)
    except BaseException:
        # The temporary file must never outlive a failure.
        if os.path.exists(handle.name):
            os.unlink(handle.name)
        raise

    return written
