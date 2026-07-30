-- Can the archive be trusted?
--
-- Two ways it can be wrong, brought together in one answer: days that are
-- incomplete, and runs where the source was unavailable.
--
-- This query is meant to return nothing. An empty result is the good news --
-- and knowing that an empty result IS the good news is the whole point of
-- keeping a run log.
SELECT
    'incomplete day'                    AS issue,
    CAST(day AS VARCHAR)                AS moment,
    site || ' / ' || species            AS detail,
    missing_hours || ' hour(s) missing' AS extent
FROM gaps

UNION ALL

SELECT
    'source outage',
    CAST(run_at AS VARCHAR),
    "range",
    coalesce(error, 'no reason recorded')
FROM runs
WHERE outcome <> 'ok'

ORDER BY moment DESC, issue;
