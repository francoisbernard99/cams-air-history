# Roadmap

Four weeks, hard stop at the end of week 4 whatever the state. Whatever is not
done becomes a version 2, on a repository that already runs.

## Week 1 — the collector

- [x] Repository skeleton, licence, `.gitignore`
- [x] API call, retries, reshaping into flat rows
- [x] Atomic CSV writing (all or nothing)
- [x] Network-free tests
- [x] Tests running on every push
- [x] First real collection checked by hand (720 rows, 5 sites, 6 species)
- [x] Replay a slice of the archive (`--start 2013-01-01`, 1440 rows)
- [x] Run `collect` manually from the Actions tab, to prove the API call works
      from a GitHub runner and not only from the laptop

## Week 2 — automation

This is where most of the technical credibility is won.

- [x] Publish to a dedicated `data` branch, keeping `main` history readable
- [x] **Graceful degradation**: an outage keeps the last valid data, is
      reported, and does not break the run
- [x] Exit codes separating an outage (code 2, self-healing) from a bug
      (code 1, needs a human)
- [x] Run log in `data/runs.jsonl`: date, range, duration, rows, incidents
- [x] **Self-repair**: the scheduled run asks for a seven-day window, so a gap
      closes on its own the next morning
- [x] Enable the `schedule` block in `.github/workflows/collect.yml`
- [ ] Watch a first scheduled run land on its own
- [ ] Extend coverage beyond the five cities

  The real engineering problem of this project: covering France at 0.1 deg
  means roughly 15,000 grid points against 10,000 calls allowed per day. The
  API accepts several coordinates per call — that is the lead. What remains is
  splitting the territory and choosing a useful resolution. Describe the
  solution in the README: it is worth more than the code implementing it.

## Week 3 — memory

- [x] DuckDB database fed by the CSV files, rebuilt in seconds, never committed
- [x] Idempotent collection: one file per day means replaying a day replaces it
- [x] Queries answering real questions, one reviewable `.sql` file each:
      `overview`, `worst-days`, `day-over-day`, `episodes`, `archive-health`
- [x] Window functions applied where they earn their keep: `RANK()` per
      species, `LAG()` partitioned by site, gaps-and-islands for episodes
- [x] Data quality guarded in SQL: incomplete days excluded from rankings, a
      missing hour splits an episode rather than papering over it
- [ ] **Backfill the archive**: it goes back to 2013, one year per call

## Week 4 — the front

- [ ] Map or dashboard
- [ ] **The page explaining what the data is and is not** (see the "What this
      data is — and is not" section of the README) — the core of the project,
      not an add-on
- [ ] Complete README: technical choices, limits, how to reproduce
- [ ] CAMS and Open-Meteo attribution clearly visible

## Later (version 2, out of scope)

- Compare the modelled field against real ground measurements
- Cross with wildfire hotspots (public FIRMS data)
- A local Airflow-orchestrated variant, documented, for the CV
