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
python -m collector                                       # current day
python -m collector --past-days 7                         # the last 7 days
python -m collector --start 2013-01-01 --end 2013-12-31   # replay the archive
python -m collector --dry-run                             # print the URL only
```

The archive goes back to **2013**. The historical database does not have to
fill up slowly over time: it can be loaded from day one.

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
  storage.py    atomic CSV writing
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
