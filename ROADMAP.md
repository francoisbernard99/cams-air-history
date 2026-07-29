# Roadmap

Four weeks, hard stop at the end of week 4 whatever the state. Whatever is not
done becomes a version 2, on a repository that already runs.

## Week 1 — the collector

- [x] Repository skeleton, licence, `.gitignore`
- [x] API call, retries, reshaping into flat rows
- [x] Atomic CSV writing (all or nothing)
- [x] Network-free tests
- [x] Tests running on every push
- [ ] First real collection checked by hand
- [ ] Replay a slice of the archive (`--start` / `--end`)

## Week 2 — automation

This is where most of the technical credibility is won.

- [ ] Enable the `schedule` block in `.github/workflows/collect.yml`
- [ ] **Graceful degradation**: if the source does not answer, keep the last
      valid collection, report the outage, break nothing
- [ ] Decide where produced data lands (dedicated branch, artifact, or
      published output) — settle it in `docs/DECISIONS.md`
- [ ] Collection log: date, duration, volume received, incidents
- [ ] Extend coverage beyond the five cities

  The real engineering problem of this project: covering France at 0.1 deg
  means roughly 15,000 grid points against 10,000 calls allowed per day. The
  API accepts several coordinates per call — that is the lead. What remains is
  splitting the territory and choosing a useful resolution. Describe the
  solution in the README: it is worth more than the code implementing it.

## Week 3 — memory

- [ ] DuckDB database fed by the CSV files
- [ ] **Backfill the archive**: it goes back to 2013, the database does not
      have to wait to fill itself
- [ ] Queries answering real questions: worst day of the month, how long an
      episode lasted, comparison between two periods
- [ ] Idempotent collection: replaying the same day twice must not duplicate
      rows

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
