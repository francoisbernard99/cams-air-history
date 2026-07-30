# cams-air-history

[![tests](https://github.com/francoisbernard99/cams-air-history/actions/workflows/tests.yml/badge.svg)](https://github.com/francoisbernard99/cams-air-history/actions/workflows/tests.yml)

Hourly air quality history over France, collected automatically from an open
public source, archived, and queryable.

**No API key. No dependency. No server.**

```bash
git clone <repository-url>
cd cams-air-history
python -m collector
```

That is all. No configuration file to fill in, no account to create, no secret
to declare. If those three lines are not enough to produce data, that is a bug
in this repository.

---

## What it does

1. **Collect** — query the Open-Meteo air quality API, which exposes fields
   from the European CAMS service.
2. **Archive** — write one dated CSV file per run, in long format (one row per
   hour, site and species).
3. **Accumulate** — feed a DuckDB database queryable in SQL *(week 3)*.
4. **Serve** — map or dashboard *(week 4)*.

See [ROADMAP.md](ROADMAP.md) for progress, and
[docs/DECISIONS.md](docs/DECISIONS.md) for the technical choices and what each
one costs.

## What this data is — and is not

**These are not measurements.**

CAMS is a model. It assimilates satellite observations and ground stations, but
what it returns is a **computed** field, not a measured value. A PM2.5 figure
for Paris at 14:00 was not measured in Paris at 14:00: it was simulated, on a
grid cell roughly 11 km across.

Three practical consequences:

- An 11 km cell averages a whole city. It does not separate a boulevard from a
  park, even though the gap between those two can exceed the gap between two
  cities.
- A modelled field is smooth by construction. Short, localised peaks are
  damped, sometimes absent.
- Comparing these values against a regulatory threshold is meaningless: those
  thresholds apply to standardised station measurements, not to model output.

This project therefore shows **a regional estimate** — useful to observe trends
and episodes, useless to say what a person breathes at a given address.

This distinction is not a footnote. It is the subject of the project.

## Available species

The API exposes 18 variables. Requesting one more costs neither an extra call
nor an extra second.

| Collected by default | Available, not enabled |
|---|---|
| `pm2_5`, `pm10` | `aerosol_optical_depth`, `dust` |
| `nitrogen_dioxide`, `sulphur_dioxide` | `ammonia`, `methane` |
| `ozone`, `carbon_monoxide` | `formaldehyde`, `glyoxal` |
| | `peroxyacyl_nitrates` |
| | `non_methane_volatile_organic_compounds` |
| | `uv_index`, `european_aqi`, `us_aqi` |

The right-hand column belongs to atmospheric chemistry rather than to air
quality indices. Enable them in `collector/config.py`.

## Usage

```bash
python -m collector                                       # today
python -m collector --catch-up 7                          # today plus the last 7 days
python -m collector --start 2013-01-01 --end 2013-12-31   # backfill a year
python -m collector --dry-run                             # print the URL only
```

Every request is a date range, and the result is always written as **one CSV
file per calendar day**. Refetching a window therefore rewrites those days
rather than appending to them — running the same command twice changes nothing.

The archive goes back to **2013**. The historical database does not have to
fill up slowly over time: it can be loaded from day one, one year per call
(a year for one point and six species is about 400 KB, in under a second).

## When the source goes down

An unattended collector is judged on what it does on a bad day, not a good one.

- The run **keeps the last valid data**. Nothing is deleted, truncated or
  blanked. A day that could not be fetched simply stays missing.
- The run **records the outage** in `data/runs.jsonl`, one JSON object per
  line. A job that goes green because it handled a failure gracefully would
  otherwise hide the hole it just left.
- The next run **repairs the gap on its own**. The scheduled job asks for a
  seven-day window, so yesterday's outage is refilled this morning with nobody
  intervening.
- Exit codes separate the two kinds of failure, because automation reads them:

  | Code | Meaning | The run |
  |---|---|---|
  | `0` | collection succeeded | green |
  | `1` | unexpected failure, a bug | red — it needs a human |
  | `2` | source unavailable | green with a warning — it repairs itself |

An outage is not a bug. Turning it red would train you to ignore red.

## Where the data lives

The collected files are published on a dedicated **`data` branch**, not on
`main`. The history of `main` stays readable — one commit per code change,
rather than one per day of data.

```bash
git worktree add archive data   # both branches checked out at once
```

That puts the archive in `archive/data/`, the same layout the workflow uses.

## Asking the archive questions

```bash
pip install -r requirements.txt

python -m warehouse build            # (re)build the database from the CSV files
python -m warehouse list             # the questions available
python -m warehouse ask worst-days   # answer one
```

The database is a **derived artifact**: rebuilt from the CSV files in seconds,
never committed. The files on the `data` branch stay the source of truth, so a
corrupted or outdated database is fixed by rebuilding, never by repairing.

Each question is one reviewable `.sql` file in `warehouse/queries/`:

| Question | What it uses |
|---|---|
| `overview` | what the archive holds, per species — read this first |
| `worst-days` | `RANK()` within each species, complete days only |
| `day-over-day` | `LAG()` partitioned by site, so no site reads another's value |
| `episodes` | gaps and islands: how long a run of hours above a level lasted |
| `archive-health` | incomplete days and recorded outages — **meant to return nothing** |

Two properties the tests pin down, because SQL fails silently:

- an **incomplete day is excluded** from rankings. Six hours averaged against
  twenty-four is an artefact, not a record.
- a **missing hour splits an episode in two**. An archive with a hole must not
  claim a continuity it cannot prove.

Thresholds used in the queries are reading aids, **not regulatory limits** —
see the section above on what this data is.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

No test touches the network. A test that depends on the internet fails the day
the source goes down, and you end up not trusting your own test suite.

## Layout

```
collector/
  config.py     settings: species, sites, retries
  api.py        HTTP call, retries, reshaping
  storage.py    atomic CSV writing, one file per day
  runlog.py     append-only log of runs and outages
  __main__.py   entry point, exit codes
warehouse/
  schema.sql    tables and views
  build.py      rebuild the database from the CSV files
  queries/      one .sql file per question
  __main__.py   entry point
tests/          network-free tests
docs/
  DECISIONS.md  log of technical decisions
.github/workflows/
  tests.yml     tests on every push
  collect.yml   scheduled collection
data/           output (not tracked)
```

## Attribution

The source's CC-BY 4.0 licence requires crediting both parties below. This
notice must stay visible on any page publishing this data:

> Data from the European **CAMS** service (Copernicus Atmosphere Monitoring
> Service), distributed by **[Open-Meteo](https://open-meteo.com)** under the
> CC-BY 4.0 licence.

The code in this repository is MIT licensed — see [LICENSE](LICENSE).
