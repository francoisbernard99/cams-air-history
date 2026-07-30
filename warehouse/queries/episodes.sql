-- How long did each episode last?
--
-- The classic "gaps and islands" problem. Consecutive hours above a threshold
-- form an island; the trick is that for a run of consecutive hours, the
-- quantity (hour - row_number) stays constant, and changes as soon as the run
-- breaks. Grouping on it recovers each episode.
--
-- Because the key is built from real timestamps, a missing hour genuinely
-- splits an episode in two. That is the correct behaviour: an archive with a
-- hole must not claim continuity it cannot prove.
--
-- The threshold below is a reading aid, NOT a regulatory limit. These are
-- modelled values on an 11 km grid, and regulatory thresholds apply to
-- standardised station measurements. See the README.
WITH above_threshold AS (
    SELECT
        site,
        species,
        measured_at,
        value,
        unit,
        row_number() OVER (
            PARTITION BY site, species ORDER BY measured_at
        ) AS seq
    FROM readings
    WHERE species = 'pm2_5'
      AND value >= 15
),
islands AS (
    SELECT *, measured_at - to_hours(seq) AS island_key
    FROM above_threshold
)
SELECT
    site,
    species,
    min(measured_at)          AS started_at,
    max(measured_at)          AS ended_at,
    count(*)                  AS hours,
    round(avg(value), 1)      AS mean_value,
    max(value)                AS peak,
    any_value(unit)           AS unit
FROM islands
GROUP BY site, species, island_key
HAVING count(*) >= 3
ORDER BY hours DESC, started_at;
