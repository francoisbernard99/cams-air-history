"""Tests for the entry point, and above all for what happens when the source
is down.

Graceful degradation is the part that cannot be checked by looking at the code:
it only shows up when something fails. So we make it fail on purpose.
"""

import argparse
import os

from collector import __main__ as entry
from collector import api, runlog


def args(**overrides) -> argparse.Namespace:
    base = {"start": None, "end": None, "catch_up": 0}
    base.update(overrides)
    return argparse.Namespace(**base)


def test_resolve_range_explicit_range_wins():
    start, end = entry.resolve_range(
        args(start="2013-01-01", end="2013-12-31", catch_up=7), today="2026-07-29"
    )
    assert (start, end) == ("2013-01-01", "2013-12-31")


def test_resolve_range_defaults_to_today_alone():
    assert entry.resolve_range(args(), today="2026-07-29") == (
        "2026-07-29",
        "2026-07-29",
    )


def test_resolve_range_reaches_back_over_the_catch_up_window():
    """A seven day window is what closes a gap left by an outage: the next run
    refetches the days that were missed."""
    assert entry.resolve_range(args(catch_up=7), today="2026-07-29") == (
        "2026-07-22",
        "2026-07-29",
    )


def test_an_outage_keeps_the_previous_data_and_reports_code_2(tmp_path, monkeypatch):
    """The heart of week 2. When the source is down the collector must not
    delete, truncate or blank anything -- and must say so with its exit code."""
    existing = tmp_path / "air-quality-2026-07-28.csv"
    existing.write_text("timestamp,site\n2026-07-28T00:00,Paris\n")
    before = existing.read_text()

    def source_is_down(url, max_attempts=1):
        raise api.SourceUnavailable("no valid response after 4 attempts")

    monkeypatch.setattr(api, "fetch", source_is_down)

    code = entry.main(["--output-dir", str(tmp_path)])

    assert code == entry.EXIT_SOURCE_UNAVAILABLE
    assert existing.read_text() == before


def test_an_outage_is_recorded_in_the_run_log(tmp_path, monkeypatch):
    """A run that goes green because it handled a failure gracefully would
    otherwise hide the hole it just left in the archive."""

    def source_is_down(url, max_attempts=1):
        raise api.SourceUnavailable("connection refused")

    monkeypatch.setattr(api, "fetch", source_is_down)
    entry.main(["--output-dir", str(tmp_path)])

    entries = runlog.tail(str(tmp_path / "runs.jsonl"), 10)
    assert len(entries) == 1
    assert entries[0]["outcome"] == "outage"
    assert "connection refused" in entries[0]["error"]
    assert entries[0]["rows"] == 0


def test_a_successful_run_writes_files_and_logs_the_outcome(tmp_path, monkeypatch):
    payload = {
        "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³"},
        "hourly": {
            "time": ["2026-07-28T00:00", "2026-07-29T00:00"],
            "pm2_5": [6.5, 7.1],
        },
    }
    monkeypatch.setattr(api, "fetch", lambda url, max_attempts=1: [payload])
    monkeypatch.setattr(entry.config, "SITES", [
        {"name": "Paris", "latitude": 48.85, "longitude": 2.35}
    ])

    code = entry.main(["--output-dir", str(tmp_path), "--catch-up", "1"])

    assert code == entry.EXIT_OK
    assert os.path.exists(tmp_path / "air-quality-2026-07-28.csv")
    assert os.path.exists(tmp_path / "air-quality-2026-07-29.csv")

    logged = runlog.tail(str(tmp_path / "runs.jsonl"), 1)[0]
    assert logged["outcome"] == "ok"
    assert logged["days"] == 2
    assert logged["rows"] == 2
