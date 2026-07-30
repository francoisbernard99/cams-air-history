"""Tests for the storage module."""

import csv
import os

import pytest

from collector import storage


def row(timestamp: str, site: str = "Paris", value: float = 6.5) -> dict:
    return {
        "timestamp": timestamp,
        "site": site,
        "latitude": 48.85,
        "longitude": 2.35,
        "species": "pm2_5",
        "value": value,
        "unit": "μg/m³",
    }


ROWS = [row("2026-07-29T00:00")]


def test_write_rows_produces_a_readable_csv(tmp_path):
    path = str(tmp_path / "out.csv")
    written = storage.write_rows(ROWS, path)

    assert written == 1
    with open(path, encoding="utf-8", newline="") as handle:
        reread = list(csv.DictReader(handle))
    assert reread[0]["site"] == "Paris"
    assert reread[0]["value"] == "6.5"


def test_write_rows_creates_missing_directory(tmp_path):
    path = str(tmp_path / "some" / "nested" / "out.csv")
    storage.write_rows(ROWS, path)
    assert os.path.exists(path)


def test_interrupted_write_leaves_no_partial_file(tmp_path):
    """Writing is all or nothing. A half-written file would later be read as if
    it were complete."""

    def failing_rows():
        yield ROWS[0]
        raise RuntimeError("failure midway through writing")

    path = str(tmp_path / "out.csv")
    with pytest.raises(RuntimeError):
        storage.write_rows(failing_rows(), path)

    assert not os.path.exists(path)
    assert list(tmp_path.iterdir()) == []


def test_group_by_date_splits_on_the_calendar_day():
    rows = [row("2026-07-29T23:00"), row("2026-07-30T00:00"), row("2026-07-30T01:00")]
    grouped = storage.group_by_date(rows)

    assert sorted(grouped) == ["2026-07-29", "2026-07-30"]
    assert len(grouped["2026-07-30"]) == 2


def test_write_daily_produces_one_file_per_day(tmp_path):
    """One file per calendar day whatever range was requested. This invariant
    is what lets a refetch close a gap instead of duplicating rows."""
    rows = [row("2026-07-29T23:00"), row("2026-07-30T00:00")]
    written = storage.write_daily(rows, str(tmp_path))

    assert written == {"2026-07-29": 1, "2026-07-30": 1}
    assert os.path.exists(tmp_path / "air-quality-2026-07-29.csv")
    assert os.path.exists(tmp_path / "air-quality-2026-07-30.csv")


def test_refetching_a_day_replaces_it_instead_of_appending(tmp_path):
    """CAMS revises its analyses, so a later fetch of the same day must win --
    without ever doubling the rows."""
    storage.write_daily([row("2026-07-29T00:00", value=6.5)], str(tmp_path))
    storage.write_daily(
        [row("2026-07-29T00:00", value=9.9), row("2026-07-29T01:00", value=8.1)],
        str(tmp_path),
    )

    with open(tmp_path / "air-quality-2026-07-29.csv", encoding="utf-8") as handle:
        reread = list(csv.DictReader(handle))

    assert len(reread) == 2
    assert reread[0]["value"] == "9.9"
