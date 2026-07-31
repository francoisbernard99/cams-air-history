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

## 2026-07-30 — A static page, and no JavaScript at all

**Context.** Streamlit was the obvious candidate: it is quick, and it is on the
author's syllabus.

**Decision.** Python renders one self-contained HTML file, deployed to GitHub
Pages. Charts are inline SVG generated by `web/charts.py`. No charting library,
no CDN, no script tag.

**Why.** A portfolio page is judged by a stranger clicking a link, possibly
months from now. A Streamlit app on a free tier sleeps when idle and takes
seconds to wake; a CDN reference hands the page's lifespan to someone else. A
static file has nothing to go down. A test asserts that the only external URLs
in the page are the two attribution links.

**Cost.** Charts are written by hand rather than configured, and there is no
zoom or client-side filtering. The hover layer is the browser's own: each point
carries an SVG `<title>`, and every chart ships a table view so no value is
hover-only.

---

## 2026-07-30 — The caveat sits before the first chart

**Decision.** "Ce que ces chiffres ne sont pas" is the first section on the
page, above every figure, and a test asserts its presence.

**Why.** It changes how every chart below should be read, so reading it
afterwards is too late. And it is the one section whose silent disappearance
would turn the page into something dishonest — modelled values presented as
measurements. That deserves a test, not trust.

---

## 2026-07-30 — The archive picks its own headline

**Context.** The page needs one episode to lead with. Hard-coding a species
would have been simplest — and would have encoded a judgement about which
pollutant matters that this project does not claim to make.

**Decision.** Each complete day is standardised against its own species, and the
largest departure wins:

```
score = (day mean − species median) / (species p90 − species median)
```

Read as: how many times over the normal gap between a median day and an
already-loaded one.

**A first attempt was wrong and was replaced.** The obvious measure — a plain
ratio to the species median — was tried first. On the real archive it returned
sulphur dioxide at 17 µg/m³ (median 1.2, so a ratio of ×14) ahead of PM2.5 at
83 µg/m³. The measure rewarded species with a very low background rather than
episodes that matter. Comparing the two on real data, not in the abstract, is
what exposed it.

**What the current measure returned.** The top three departures in the archive
are PM10, carbon monoxide and PM2.5 — **all on the same day, at the same
place**. Three species that know nothing about each other converging on one date
is corroboration that a single physical event occurred; the page says so
explicitly when it happens.

**Guard.** A species whose values never move has no spread to standardise
against, so the divisor is zero. Those rows are dropped in SQL; a test covers
the brand-new-archive case, where the page must say "not enough data yet" rather
than crash.

---

## 2026-07-30 — Axis labels anchored inwards at the edges

**Context.** The first and last x-axis labels are centred on points that sit at
the very edge of the viewBox, so half of each label fell outside and was clipped
— `30/0` instead of `30/07`. Visible on every panel.

**Decision.** The first label anchors `start`, the last `end`, the rest stay
centred.

**Why note something this small.** It was invisible to every check that had been
run: the palette validator looks at colour, the tests look at content, and the
HTML parsed clean. Only rendering the page and looking at it found it.

---

## 2026-07-31 — The commune index ships beside the page, not inside it

**Context.** Clicking a map of the whole of France is too coarse to find a
particular town, which is the first thing a visitor tries. Search needs the
34,969 French communes with their coordinates.

**Source.** `geo.api.gouv.fr` (Découpage administratif), Licence Ouverte, fetched
once and vendored into `web/assets/`. Vendoring rather than calling it at build
time keeps the build reproducible offline.

**Decision.** The index is a separate file served from the same origin, fetched
on the first keystroke and never before.

**Why not inline it.** Even compacted it is 1.2 MB, about 420 KB over the wire.
That would quadruple the page weight for a feature many visitors never use.
Same-origin, so the page still depends on no third party — the promise was never
"one file", it was "nothing fetched from anyone else".

**How it was compacted, and what that cost.** 4.6 MB of raw JSON down to 1.2 MB:

| Step | Rationale |
|---|---|
| Columns as parallel arrays, names as one newline-joined string | removes per-row JSON punctuation |
| Coordinates rounded to 3 decimals (~110 m) | the model's own cell is 11 km wide; 110 m was already meaningless here |
| Population dropped | rows are sorted by it, so the array order *is* the ranking |

That last one is the useful trick: search scans in order and stops at eight
matches, so the largest communes surface first with no score stored and no
sorting at query time. A test pins the ordering, because search quality silently
depends on it.

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
