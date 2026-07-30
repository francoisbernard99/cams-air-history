-- What is in the archive?
--
-- One line per species: how much of it there is, and the range it covers.
-- Read this first, before trusting any of the other answers.
SELECT
    species,
    any_value(unit)                  AS unit,
    count(DISTINCT day)              AS days,
    count(DISTINCT site)             AS sites,
    min(day)                         AS first_day,
    max(day)                         AS last_day,
    round(avg(mean_value), 2)        AS mean_value,
    max(max_value)                   AS highest_hour
FROM daily
GROUP BY species
ORDER BY species;
