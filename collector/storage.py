"""Writing collected data to disk.

Week 1: one dated CSV file per run. It is readable by eye, versioned by its
filename, and DuckDB reads it directly with no conversion step.
Week 3: these files will feed a DuckDB database -- see ROADMAP.md.
"""

import csv
import os
import tempfile
from typing import Iterable

from collector import config


def output_path(directory: str, stamp: str) -> str:
    """Path of the file produced for a given stamp."""
    return os.path.join(directory, f"air-quality-{stamp}.csv")


def write_rows(rows: Iterable[dict], path: str) -> int:
    """Write rows as CSV and return how many were written.

    Writing goes through a temporary file that is renamed at the end. If the
    program is interrupted midway, it leaves behind no half-written file that a
    later read would mistake for a complete one.
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
