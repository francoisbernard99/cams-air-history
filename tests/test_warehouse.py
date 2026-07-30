"""Tests for the warehouse.

These build a real DuckDB database from small CSV fixtures. Testing SQL by
reading it does not work: a window function either partitions the way you think
or it silently does not.
"""

import csv

import duckdb
import pytest

from collector import config
from warehouse import build as warehouse

QUERY_NAMES = warehouse.available_queries()


def write_day(directory, day: str, hours: range, site="Paris", species="pm2_5",
              value=6.5) -> None:
    """Write one daily CSV file, the way the collector does."""
    path = directory / f"air-quality-{day}.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=config.COLUMNS)
        writer.writeheader()
        for hour in hours:
            writer.writerow({
                "timestamp": f"{day}T{hour:02d}:00",
                "site": site,
                "latitude": 48.85,
                "longitude": 2.35,
                "species": species,
                "value": value(hour) if callable(value) else value,
                "unit": "μg/m³",
            })


@pytest.fixture
def archive(tmp_path):
    """A data directory and the database built from it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir, str(tmp_path / "test.duckdb")


def ask(database: str, name: str) -> list[tuple]:
    connection = duckdb.connect(database, read_only=True)
    try:
        return connection.sql(warehouse.query_text(name)).fetchall()
    finally:
        connection.close()


def test_build_counts_what_it_loaded(archive):
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    write_day(data_dir, "2026-07-30", range(24))

    summary = warehouse.build(str(data_dir), database)

    assert summary["rows"] == 48
    assert summary["days"] == 2
    assert summary["sites"] == 1
    assert summary["gaps"] == 0


def test_a_missing_run_log_is_not_an_error(archive):
    """A fresh checkout has no run log yet. Every query must still work."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))

    summary = warehouse.build(str(data_dir), database)

    assert summary["outages"] == 0
    assert ask(database, "archive-health") == []


def test_an_incomplete_day_is_reported_not_hidden(archive):
    """A day holding six hours must not quietly average against a full one."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    write_day(data_dir, "2026-07-30", range(6))

    summary = warehouse.build(str(data_dir), database)
    assert summary["gaps"] == 1

    issues = ask(database, "archive-health")
    assert len(issues) == 1
    assert issues[0][0] == "incomplete day"
    assert "18 hour(s) missing" in issues[0][3]


def test_worst_days_ignores_incomplete_days(archive):
    """An incomplete day showing a high average is an artefact, not a record."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24), value=10.0)
    write_day(data_dir, "2026-07-30", range(2), value=999.0)

    warehouse.build(str(data_dir), database)
    days = [row[2].isoformat() for row in ask(database, "worst-days")]

    assert days == ["2026-07-29"]


def test_an_outage_in_the_log_surfaces_in_archive_health(archive):
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    (data_dir / config.RUN_LOG_NAME).write_text(
        '{"run_at": "2026-07-30T05:17:00+00:00", "range": "2026-07-23..2026-07-30",'
        ' "outcome": "outage", "days": 0, "rows": 0, "sites": 5, "species": 6,'
        ' "duration_s": 8.1, "error": "connection refused"}\n'
    )

    summary = warehouse.build(str(data_dir), database)
    assert summary["outages"] == 1

    issues = ask(database, "archive-health")
    assert issues[0][0] == "source outage"
    assert issues[0][3] == "connection refused"


def test_a_log_without_any_outage_still_has_an_error_column(archive):
    """The first ever outage must not be the moment the schema changes."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    (data_dir / config.RUN_LOG_NAME).write_text(
        '{"run_at": "2026-07-30T05:17:00+00:00", "range": "2026-07-30..2026-07-30",'
        ' "outcome": "ok", "days": 1, "rows": 24, "sites": 1, "species": 1,'
        ' "duration_s": 0.4}\n'
    )

    warehouse.build(str(data_dir), database)

    connection = duckdb.connect(database, read_only=True)
    columns = [d[0] for d in connection.sql("SELECT * FROM runs").description]
    connection.close()
    assert "error" in columns


def test_episodes_group_consecutive_hours(archive):
    data_dir, database = archive
    # Six hours above the threshold, then back down.
    write_day(data_dir, "2026-07-29", range(24),
              value=lambda hour: 40.0 if 6 <= hour < 12 else 2.0)

    warehouse.build(str(data_dir), database)
    episodes = ask(database, "episodes")

    assert len(episodes) == 1
    assert episodes[0][4] == 6  # hours


def test_a_missing_hour_splits_an_episode_in_two(archive):
    """The heart of the gaps-and-islands query. An archive with a hole must not
    claim a continuity it cannot prove."""
    data_dir, database = archive
    hours = [h for h in range(24) if h != 9]  # hour 9 never collected
    write_day(data_dir, "2026-07-29", hours,
              value=lambda hour: 40.0 if 6 <= hour < 14 else 2.0)

    warehouse.build(str(data_dir), database)
    episodes = ask(database, "episodes")

    assert len(episodes) == 2
    assert sorted(row[4] for row in episodes) == [3, 4]


@pytest.mark.parametrize("name", QUERY_NAMES)
def test_every_query_runs_on_an_empty_archive(archive, name):
    """A query that only works once data looks interesting is a query that will
    break on the day it is needed."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    warehouse.build(str(data_dir), database)

    ask(database, name)


def test_asking_an_unknown_query_names_the_ones_that_exist():
    with pytest.raises(FileNotFoundError, match="worst-days"):
        warehouse.query_text("no-such-question")
