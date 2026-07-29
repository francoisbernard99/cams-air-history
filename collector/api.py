"""Open-Meteo API calls and response reshaping.

No third-party dependency: `urllib` ships with Python. The collector therefore
runs on any machine and in any CI environment without an install step.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

from collector import config


class SourceUnavailable(Exception):
    """The source did not answer correctly after every retry."""


def build_url(
    sites: list[dict],
    species: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
    past_days: int | None = None,
    forecast_days: int = 1,
) -> str:
    """Build the request URL.

    The API accepts several coordinates in a single call, comma separated.
    That is what will later allow covering France without exceeding the quota
    of 10,000 calls per day.
    """
    params: dict[str, Any] = {
        "latitude": ",".join(str(s["latitude"]) for s in sites),
        "longitude": ",".join(str(s["longitude"]) for s in sites),
        "hourly": ",".join(species),
    }

    # `start_date`/`end_date` replay the archive (it goes back to 2013).
    # `past_days` catches up on the days that just went by.
    # The two do not combine: an explicit date range wins.
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
    else:
        params["forecast_days"] = forecast_days
        if past_days is not None:
            params["past_days"] = past_days

    return f"{config.API_URL}?{urllib.parse.urlencode(params)}"


def fetch(url: str, max_attempts: int = config.MAX_ATTEMPTS) -> list[dict]:
    """Call the URL and always return a list of responses.

    The API returns a bare object for a single point and an array for several.
    Normalising here means the rest of the code only ever handles one case.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=config.TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, list) else [payload]

        except urllib.error.HTTPError as error:
            # 4xx other than 429: the request itself is wrong, retrying it
            # unchanged will not help.
            if error.code != 429 and 400 <= error.code < 500:
                raise SourceUnavailable(f"request rejected (HTTP {error.code})") from error
            last_error = error

        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error

        if attempt < max_attempts:
            time.sleep(config.BACKOFF_SECONDS * 2 ** (attempt - 1))

    raise SourceUnavailable(
        f"no valid response after {max_attempts} attempts: {last_error}"
    )


def to_rows(payloads: list[dict], sites: list[dict]) -> Iterator[dict]:
    """Turn responses into flat rows, ready for a CSV file.

    A response groups values by species; we unfold them into one row per
    (hour, site, species).
    """
    if len(payloads) != len(sites):
        raise ValueError(
            f"got {len(payloads)} responses for {len(sites)} requested sites"
        )

    for payload, site in zip(payloads, sites):
        hourly = payload["hourly"]
        units = payload.get("hourly_units", {})
        timestamps = hourly["time"]

        for species, values in hourly.items():
            if species == "time":
                continue
            for timestamp, value in zip(timestamps, values):
                # The API returns None for a missing value. We do not invent a
                # zero -- we simply skip the row.
                if value is None:
                    continue
                yield {
                    "timestamp": timestamp,
                    "site": site["name"],
                    "latitude": site["latitude"],
                    "longitude": site["longitude"],
                    "species": species,
                    "value": value,
                    "unit": units.get(species, ""),
                }
