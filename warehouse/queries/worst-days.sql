-- Which days stand out, for each species?
--
-- RANK() ranks days inside each species independently, so an ozone day is
-- never compared against a PM2.5 day -- they do not share a scale. Ties keep
-- the same rank, which matters here: two sites can genuinely share a peak.
--
-- Incomplete days are excluded. A day holding six hours would otherwise
-- average six hours against another day's twenty-four.
WITH ranked AS (
    SELECT
        species,
        day,
        site,
        mean_value,
        max_value,
        unit,
        RANK() OVER (PARTITION BY species ORDER BY mean_value DESC) AS rank_in_species
    FROM daily
    WHERE hours = 24
)
SELECT
    species,
    rank_in_species AS rank,
    day,
    site,
    mean_value,
    max_value AS peak_hour,
    unit
FROM ranked
WHERE rank_in_species <= 3
ORDER BY species, rank_in_species, site;
