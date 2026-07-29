"""Tests for the api module.

No test touches the network. A test that depends on the internet fails the day
the source goes down, and you end up not trusting your own test suite.
"""

import pytest

from collector import api

SITES = [
    {"name": "Paris", "latitude": 48.85, "longitude": 2.35},
    {"name": "Lyon", "latitude": 45.76, "longitude": 4.84},
]

# A real API response, cut down to two hours and two species.
PAYLOADS = [
    {
        "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³", "ozone": "μg/m³"},
        "hourly": {
            "time": ["2026-07-29T00:00", "2026-07-29T01:00"],
            "pm2_5": [6.5, 6.5],
            "ozone": [58.0, 55.0],
        },
    },
    {
        "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³", "ozone": "μg/m³"},
        "hourly": {
            "time": ["2026-07-29T00:00", "2026-07-29T01:00"],
            "pm2_5": [9.1, None],
            "ozone": [61.0, 60.0],
        },
    },
]


def test_build_url_batches_coordinates():
    """Several sites fit in a single call: this is what will allow covering
    France without blowing the daily quota."""
    url = api.build_url(SITES, ["pm2_5"])
    assert "latitude=48.85%2C45.76" in url
    assert "longitude=2.35%2C4.84" in url


def test_build_url_date_range_wins_over_forecast():
    url = api.build_url(SITES, ["pm2_5"], start_date="2013-01-01", end_date="2013-01-02")
    assert "start_date=2013-01-01" in url
    assert "forecast_days" not in url


def test_to_rows_unfolds_every_hour_and_species():
    rows = list(api.to_rows(PAYLOADS, SITES))
    # 2 sites x 2 hours x 2 species = 8, minus the one missing value = 7.
    assert len(rows) == 7
    assert rows[0]["site"] == "Paris"
    assert rows[0]["species"] == "pm2_5"
    assert rows[0]["value"] == 6.5


def test_to_rows_skips_missing_values():
    """A missing value must never become a zero: a zero is a reading, an
    absence is not."""
    rows = list(api.to_rows(PAYLOADS, SITES))
    lyon_pm25 = [r for r in rows if r["site"] == "Lyon" and r["species"] == "pm2_5"]
    assert len(lyon_pm25) == 1
    assert all(r["value"] is not None for r in rows)


def test_to_rows_rejects_mismatch_between_responses_and_sites():
    """If the API returns fewer responses than sites requested, pairing them in
    order would attach values to the wrong city."""
    with pytest.raises(ValueError):
        list(api.to_rows(PAYLOADS[:1], SITES))
