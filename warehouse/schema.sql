-- Warehouse schema.
--
-- The database is a derived artifact: it is rebuilt from the CSV files in a
-- few seconds and is never committed. The CSV files on the `data` branch are
-- the source of truth.
--
-- Paths come in as DuckDB variables, set by warehouse/build.py, so this file
-- stays pure SQL with nothing interpolated into it.

-- Every hourly reading, one row per (hour, site, species).
CREATE OR REPLACE TABLE readings AS
SELECT
    CAST(timestamp AS TIMESTAMP) AS measured_at,
    site,
    latitude,
    longitude,
    species,
    CAST(value AS DOUBLE)        AS value,
    unit
FROM read_csv_auto(getvariable('csv_glob'), header = true);

-- Collection history, including outages. Declared explicitly rather than
-- inferred: a log with no outage yet has no `error` key, and a schema that
-- changes the first time something fails is a schema you cannot query.
CREATE OR REPLACE TABLE runs (
    run_at     TIMESTAMP,
    "range"    VARCHAR,
    outcome    VARCHAR,
    days       BIGINT,
    "rows"     BIGINT,
    sites      BIGINT,
    species    BIGINT,
    duration_s DOUBLE,
    error      VARCHAR
);

-- Daily aggregate per site and species. `hours` is deliberately kept: a day
-- with fewer than 24 hours is an incomplete day, and averaging it against a
-- complete one would compare two different things.
CREATE OR REPLACE VIEW daily AS
SELECT
    CAST(measured_at AS DATE)  AS day,
    site,
    species,
    unit,
    count(*)                   AS hours,
    round(avg(value), 2)       AS mean_value,
    max(value)                 AS max_value
FROM readings
GROUP BY ALL;

-- Days that are not complete. Empty is the expected state.
CREATE OR REPLACE VIEW gaps AS
SELECT day, site, species, hours, 24 - hours AS missing_hours
FROM daily
WHERE hours < 24;
