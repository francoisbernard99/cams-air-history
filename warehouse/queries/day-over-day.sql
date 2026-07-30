-- How much did each site move from one day to the next?
--
-- LAG() reaches back to the previous row inside a partition. Partitioning by
-- (site, species) is what keeps Paris from reading Bordeaux's value as its own
-- previous day.
--
-- The first day of each series has no predecessor, so its change is NULL --
-- not zero. A missing comparison is not an absence of change.
SELECT
    day,
    site,
    species,
    mean_value,
    LAG(mean_value) OVER w                          AS previous_day,
    round(mean_value - LAG(mean_value) OVER w, 2)   AS change,
    round(
        100 * (mean_value - LAG(mean_value) OVER w)
        / nullif(LAG(mean_value) OVER w, 0), 1
    )                                               AS change_percent,
    unit
FROM daily
WHERE species = 'pm2_5'
WINDOW w AS (PARTITION BY site, species ORDER BY day)
ORDER BY abs(coalesce(mean_value - LAG(mean_value) OVER w, 0)) DESC, day;
