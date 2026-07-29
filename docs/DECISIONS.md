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
