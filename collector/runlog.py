"""Append-only log of collection runs.

Every run leaves a trace, successful or not. Without this, an outage is
invisible: the job goes green because it handled the failure gracefully, and
nobody ever learns the data has a hole.

One JSON object per line (JSON Lines). Append-only means concurrent readers
never see a half-written file, and DuckDB reads the format directly.
"""

import json
import os
from typing import Any


def append(path: str, entry: dict[str, Any]) -> None:
    """Add one entry at the end of the log."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def tail(path: str, count: int) -> list[dict[str, Any]]:
    """Return the last `count` entries, oldest first.

    Malformed lines are skipped rather than raising: a corrupted log line must
    never take down the collector that writes to it.
    """
    if not os.path.exists(path):
        return []

    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return entries[-count:]
