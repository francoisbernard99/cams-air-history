"""Tests for the storage module."""

import csv
import os

import pytest

from collector import storage

ROWS = [
    {
        "timestamp": "2026-07-29T00:00",
        "site": "Paris",
        "latitude": 48.85,
        "longitude": 2.35,
        "species": "pm2_5",
        "value": 6.5,
        "unit": "μg/m³",
    }
]


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
