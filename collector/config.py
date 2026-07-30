"""Collector settings.

Everything that can be changed without touching the code lives here.
"""

# Open-Meteo air quality endpoint.
# No API key is required: free access is open for non-commercial use under the
# CC-BY 4.0 licence. See ATTRIBUTION in the README.
API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# Species requested on every call.
#
# The API exposes 18 variables. Asking for one more costs neither an extra call
# nor an extra second: it is the same `hourly` parameter. The list below is a
# starting point. Atmospheric chemistry species available but not enabled:
#   ammonia, methane, formaldehyde, glyoxal, peroxyacyl_nitrates,
#   non_methane_volatile_organic_compounds, aerosol_optical_depth, dust,
#   uv_index, european_aqi, us_aqi
SPECIES = [
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "carbon_monoxide",
]

# Locations queried.
#
# Week 1: a handful of cities, enough to run the whole chain end to end. The
# national grid comes in week 2 -- see ROADMAP.md, because it raises a real
# volume problem: roughly 15,000 grid points at 0.1 deg against a quota of
# 10,000 calls per day.
SITES = [
    {"name": "Paris", "latitude": 48.85, "longitude": 2.35},
    {"name": "Lyon", "latitude": 45.76, "longitude": 4.84},
    {"name": "Marseille", "latitude": 43.30, "longitude": 5.37},
    {"name": "Lille", "latitude": 50.63, "longitude": 3.06},
    {"name": "Bordeaux", "latitude": 44.84, "longitude": -0.58},
]

# Retries on network failure or server-side error.
# The wait doubles on each attempt: 2s, 4s, 8s.
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0

# HTTP response timeout, in seconds.
TIMEOUT_SECONDS = 60

# Run log, written next to the data. One JSON object per line.
RUN_LOG_NAME = "runs.jsonl"

# Output columns, in order.
# Long format: one row per (hour, site, species). This is the shape SQL and
# DuckDB handle most naturally.
COLUMNS = ["timestamp", "site", "latitude", "longitude", "species", "value", "unit"]
