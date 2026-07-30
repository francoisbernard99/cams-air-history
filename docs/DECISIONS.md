# Decision log

One entry per structural choice: the context, the decision, what it costs. A
technical reviewer reads this file before the code — it shows the reasoning,
not just the result.

---

## 2026-07-29 — Open-Meteo as the source, and no API key

**Context.** The source had to be able to run free and indefinitely. Any keyed
or quota-bound source kills the project the day the quota lapses.

**Verified live**, not just read in the documentation:

| Check | Result |
|---|---|
| API key | none, HTTP 200 in 0.13 s |
| Free quotas | 600/min, 5,000/h, 10,000/day, 300,000/month |
| 30 consecutive calls | 30 valid responses |
| Archive | reaches back to 2013-01-01, confirmed by direct call |
| One year, one point, six species | 418 KB in 0.87 s |
| Several sites per call | yes, the response becomes an array |
| Licence | CC-BY 4.0, non-commercial use |

**Decision.** Open-Meteo `air-quality`, without a key.

**Consequence.** No `.env` file, no GitHub secret, nothing to configure. The
repository clones and runs. That is a quality, not a shortcut: reproducibility
is the first thing a reviewer checks.

---

## 2026-07-29 — Standard library only for collection

**Context.** `requests` would have made the code slightly shorter.

**Decision.** `urllib`, `csv`, `json` — nothing else. No dependency to install
in order to collect.

**Cost.** A few more lines, and HTTP error handling written by hand.

**Benefit.** CI has no install step, so nothing breaks when a version changes.
The collector runs on any machine with Python. `pytest` stays the only
dependency, and only for development.

---

## 2026-07-29 — Long format rather than wide

**Decision.** One row per (hour, site, species), rather than one column per
species.

**Why.** Adding a species no longer forces a schema change. It is also the
shape SQL and DuckDB handle most naturally for aggregations and window
functions.

**Cost.** Larger files, and a pivot step needed to display a table on screen.

---

## 2026-07-29 — Atomic writes

**Context.** Collection runs unattended. An interruption partway through a
write would leave a truncated file that the next read would take for a complete
one.

**Decision.** Write to a temporary file, then rename. Rename is atomic within a
filesystem: the final file only ever exists complete.

---

## 2026-07-29 — English in the repository, French on the site

**Decision.** Identifiers, comments, docstrings, commit messages and
documentation in English. The published site and its text in French.

**Why.** A repository half in French and half in English reads as unfinished.
English is the default for code and makes the work legible to any reviewer. The
site, on the other hand, addresses a French audience — and that is where the
scientific commentary belongs.

---

## 2026-07-29 — Data on a dedicated `data` branch

**Context.** The scheduled job runs on a machine that is destroyed straight
afterwards. Without a publishing step, collection produces nothing that
survives.

**Options considered.**

| Option | Why not |
|---|---|
| Run artifacts | expire after 90 days — fatal for an archive |
| Commits on `main` | one commit per day drowns the code history |
| GitHub Pages | that is for serving the site in week 4, not for storage |

**Decision.** An orphan `data` branch, written by the workflow. The history of
`main` stays readable, the data genuinely accumulates, and it costs nothing.

**What will invalidate this.** About 720 rows a day is roughly 18 MB a year,
which is comfortable. Moving to a national grid multiplies that by a factor
that this choice will not absorb. **Revisit this decision before increasing
spatial coverage** — see the open question below.

---

## 2026-07-29 — An outage is not a bug

**Context.** Until now any failure exited with code 1. On a scheduled run that
means a red cross nobody looks at, and a permanent hole in the archive.

**Decision.** Three exit codes:

| Code | Meaning | Run status |
|---|---|---|
| 0 | success | green |
| 1 | unexpected failure, a bug | red, needs a human |
| 2 | source unavailable | green with a warning, self-healing |

**Why.** Turning a third-party outage red trains you to ignore red. Red must
keep meaning "something is broken that I can fix".

**Consequence.** The daily run asks for a seven-day window rather than just
today, so a day missed during an outage is refetched the next morning without
anyone intervening. Self-repair costs one API call, not a piece of machinery.

---

## 2026-07-29 — One file per calendar day, whatever range is requested

**Context.** A range request returns several days in a single response. Writing
one file per request would have made a backfill and a daily run produce files
with different meanings.

**Decision.** Rows are split by calendar day; each day is written atomically to
its own file. Requesting a range overwrites exactly the days it covers.

**Why it matters.** Idempotence for free: running the same command twice
changes nothing, and a refetch closes a gap instead of duplicating rows. This
is also what makes the self-repair above possible. And since CAMS revises its
analyses, a later fetch of the same day legitimately wins.

**Cost.** Rows for a whole range are held in memory before being split, so a
single call should stay within about a year. Backfilling 2013 onwards is done
one year at a time.

---

## 2026-07-30 — The database is derived, the CSV files are the truth

**Context.** A DuckDB file could have been committed to the `data` branch,
saving a rebuild step.

**Decision.** It is never committed. `python -m warehouse build` rebuilds it
from the CSV files in about a second, and `.gitignore` excludes `*.duckdb`.

**Why.** A binary blob in git history is a blob you can never remove. And a
database that is rebuilt on every run cannot silently drift away from its
source: a corrupted or outdated warehouse is fixed by rebuilding, never by
repairing.

**Cost.** One command to run before querying, and DuckDB becomes a dependency
of the analysis side. The collector keeps its own dependency count at zero --
the job that must run unattended every morning cannot break because of a
library upgrade, while the analysis side can afford richer tools.

---

## 2026-07-30 — The `runs` table is declared, not inferred

**Context.** `read_json_auto` infers columns from the file. A run log that has
never recorded an outage contains no `error` key at all.

**Decision.** The table is declared explicitly in `schema.sql`, and the log is
loaded with `INSERT INTO runs BY NAME`.

**Why.** Otherwise the schema would change shape on the day of the first
outage — exactly when a query against it is most needed. A test pins this down:
loading a log with no outage must still produce an `error` column.

---

## 2026-07-30 — Data quality enforced in SQL, not in commentary

**Context.** Incomplete days and missing hours are real: an outage leaves them
behind by design.

**Decisions, each with a test:**

- `worst-days` filters on `hours = 24`. Six hours averaged against twenty-four
  produces an artefact that would rank as a record.
- `episodes` builds its island key from real timestamps, so a missing hour
  splits an episode in two rather than bridging it.
- `archive-health` exists to return nothing. Knowing that an empty result *is*
  the good news is the whole reason for keeping a run log.

**Why in SQL rather than in the README.** A warning in prose is read once. A
`WHERE` clause holds every time, including by whoever copies the query.

---

## 2026-07-30 — One .sql file per question

**Decision.** `warehouse/queries/<name>.sql`, discovered by filename. The CLI
lists what exists rather than hard-coding a menu.

**Why.** Each question is reviewable on its own, diffs cleanly, and can be
copied straight into a SQL client. Adding a question means adding a file, with
no Python to touch.

**Cost.** No parameters yet — thresholds are written into the query. Fine while
the questions are few; revisit when they need arguments.

---

## Still to decide

- **Week 2** — where produced data lands: dedicated branch, run artifact, or
  published output? Each carries a different cost in volume and git history.
- **Week 2** — which spatial resolution, given that France at 0.1 deg exceeds
  the daily call quota.
- **Week 3** — which uniqueness key makes collection replayable without
  duplicates.
- **Week 4** — which species the site highlights, and what is written beside
  it. An editorial choice, not a technical one: it blocks nothing before
  week 4.
