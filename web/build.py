"""Render the static page from the DuckDB warehouse.

Python reads the archive and writes one self-contained HTML file. No server, no
build toolchain, no runtime fetch: whatever the page shows was true at the
moment it was generated, and it will still render years from now.

The page is in French because that is who reads it; the repository is in
English. See docs/DECISIONS.md.
"""

import os
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from string import Template

import duckdb

from collector import config
from web import charts, map as mapview

HERE = Path(__file__).parent
TEMPLATE_PATH = HERE / "template.html"
STYLE_PATH = HERE / "style.css"
SCRIPT_PATH = HERE / "app.js"

DEFAULT_DATABASE = "air.duckdb"
DEFAULT_OUTPUT = "public"

WINDOW_DAYS = 90

# French labels for the page. Anything not listed falls back to its raw key, so
# enabling a new species in config.py never breaks the build.
SPECIES_LABELS = {
    "pm2_5": "Particules PM2,5",
    "pm10": "Particules PM10",
    "nitrogen_dioxide": "Dioxyde d'azote (NO₂)",
    "ozone": "Ozone (O₃)",
    "sulphur_dioxide": "Dioxyde de soufre (SO₂)",
    "carbon_monoxide": "Monoxyde de carbone (CO)",
    "ammonia": "Ammoniac (NH₃)",
    "methane": "Méthane (CH₄)",
    "formaldehyde": "Formaldéhyde (HCHO)",
    "glyoxal": "Glyoxal (CHOCHO)",
    "peroxyacyl_nitrates": "Nitrates de peroxyacyle (PAN)",
    "non_methane_volatile_organic_compounds": "COV non méthaniques",
    "aerosol_optical_depth": "Épaisseur optique des aérosols",
    "dust": "Poussières désertiques",
}


def label_for(species: str) -> str:
    return SPECIES_LABELS.get(species, species)


def short_date(day) -> str:
    return f"{day.day:02d}/{day.month:02d}"


def french_datetime(moment) -> str:
    return moment.strftime("%d/%m/%Y à %H:%M UTC")


def _summary(connection) -> dict:
    row = connection.execute("""
        SELECT count(*)                                  AS rows,
               count(DISTINCT CAST(measured_at AS DATE))  AS days,
               count(DISTINCT site)                       AS sites,
               count(DISTINCT species)                    AS species,
               min(CAST(measured_at AS DATE))             AS first_day,
               max(CAST(measured_at AS DATE))             AS last_day,
               max(measured_at)                           AS last_hour
        FROM readings
    """).fetchone()
    keys = ["rows", "days", "sites", "species", "first_day", "last_day", "last_hour"]
    return dict(zip(keys, row))


def _series_by_species(connection) -> dict[str, dict]:
    """Daily mean across sites for the recent window, plus the site spread.

    Incomplete days are excluded: a day holding six hours would average against
    another day's twenty-four.
    """
    rows = connection.execute(f"""
        SELECT species,
               day,
               round(avg(mean_value), 2) AS mean_value,
               min(mean_value)           AS low,
               max(mean_value)           AS high,
               any_value(unit)           AS unit
        FROM daily
        WHERE hours = 24
          AND day > (SELECT max(day) FROM daily) - INTERVAL {WINDOW_DAYS} DAY
        GROUP BY species, day
        ORDER BY species, day
    """).fetchall()

    series: dict[str, dict] = {}
    for species, day, mean_value, low, high, unit in rows:
        entry = series.setdefault(
            species, {"points": [], "band": [], "rows": [], "unit": unit}
        )
        entry["points"].append((short_date(day), mean_value))
        entry["band"].append((short_date(day), low, high))
        entry["rows"].append((day.isoformat(), mean_value, low, high))
    return series


def _coverage(connection) -> list[tuple[str, int]]:
    rows = connection.execute("""
        SELECT CAST(measured_at AS DATE)  AS day,
               count(DISTINCT measured_at) AS hours
        FROM readings
        GROUP BY 1
        ORDER BY 1
    """).fetchall()
    return [(day.isoformat(), hours) for day, hours in rows]


def _worst_per_species(connection) -> list[tuple]:
    return connection.execute("""
        WITH ranked AS (
            SELECT species, day, site, mean_value, max_value, unit,
                   row_number() OVER (
                       PARTITION BY species ORDER BY mean_value DESC
                   ) AS position
            FROM daily
            WHERE hours = 24
        )
        SELECT species, day, site, mean_value, max_value, unit
        FROM ranked
        WHERE position = 1
        ORDER BY species
    """).fetchall()


def _anomalies(connection, limit: int = 4) -> list[tuple]:
    """The days that depart most from what is normal *for their own species*.

    Species share no scale -- 80 ug/m3 of ozone is an ordinary afternoon, the
    same figure in PM2.5 is not -- so each day is standardised against its own
    species before they are compared.

    The measure is (day - median) / (p90 - median): how many times over the
    normal gap between a median day and an already-loaded one. A plain ratio to
    the median was tried first and rejected: it rewards species with a very low
    background, so sulphur dioxide at 17 ug/m3 outranked PM2.5 at 83, which is
    the wrong answer to the question the page is asking.
    """
    return connection.execute(f"""
        WITH spread AS (
            SELECT species,
                   median(mean_value)                   AS typical,
                   quantile_cont(mean_value, 0.90)      AS loaded
            FROM daily
            WHERE hours = 24
            GROUP BY species
        ),
        scored AS (
            SELECT d.species, d.day, d.site, d.mean_value, d.max_value, d.unit,
                   s.typical,
                   (d.mean_value - s.typical)
                       / nullif(s.loaded - s.typical, 0) AS score
            FROM daily d
            JOIN spread s USING (species)
            WHERE d.hours = 24
        )
        SELECT species, day, site, mean_value, max_value, unit,
               round(typical, 2) AS typical,
               round(score, 1)   AS score
        FROM scored
        -- A species whose values never move has no spread to standardise
        -- against, so it has no anomaly either. Dropping it here is what keeps
        -- a short or flat archive from producing a score of NULL downstream.
        WHERE score IS NOT NULL
        ORDER BY score DESC
        LIMIT {limit}
    """).fetchall()


def _episode_hours(connection, site: str, species: str, day) -> list[tuple]:
    return connection.execute("""
        SELECT measured_at, value, unit
        FROM readings
        WHERE site = ? AND species = ?
          AND CAST(measured_at AS DATE)
              BETWEEN CAST(? AS DATE) - INTERVAL 1 DAY
                  AND CAST(? AS DATE) + INTERVAL 1 DAY
        ORDER BY measured_at
    """, [site, species, day, day]).fetchall()


def _health_rows(connection) -> list[tuple]:
    """Incomplete days and recorded outages, newest first."""
    return connection.execute("""
        SELECT 'Journée incomplète'               AS issue,
               CAST(day AS VARCHAR)                AS moment,
               site || ' / ' || species            AS detail,
               missing_hours || ' h manquantes'    AS extent
        FROM gaps
        UNION ALL
        SELECT 'Panne de la source', CAST(run_at AS VARCHAR), "range",
               coalesce(error, 'motif non enregistré')
        FROM runs
        WHERE outcome <> 'ok'
        ORDER BY moment DESC
        LIMIT 40
    """).fetchall()


def _tile(label: str, value: str) -> str:
    return (
        f'<div class="tile"><div class="tile-label">{escape(label)}</div>'
        f'<div class="tile-value">{escape(value)}</div></div>'
    )


def _panel(species: str, entry: dict) -> str:
    unit = entry["unit"] or ""
    chart = charts.line_chart(
        entry["points"],
        band=entry["band"],
        unit=unit,
        x_tick_every=max(len(entry["points"]) // 5, 1),
        aria_label=f"Moyenne journalière de {label_for(species)} sur "
                   f"{len(entry['points'])} jours",
    )
    view = charts.table(
        ["Jour", f"Moyenne ({unit})", f"Mini ({unit})", f"Maxi ({unit})"],
        [[day, f"{mean:.2f}", f"{low:.2f}", f"{high:.2f}"]
         for day, mean, low, high in entry["rows"][-14:]],
        caption="Les quatorze derniers jours.",
    )
    return (
        f'<div class="panel"><h3>{escape(label_for(species))}'
        f'<span class="note"> — {escape(unit)}</span></h3>{chart}'
        f'<details><summary>Voir les valeurs</summary>'
        f'<div class="table-wrap">{view}</div></details></div>'
    )


def render(database: str = DEFAULT_DATABASE) -> str:
    connection = duckdb.connect(database, read_only=True)
    try:
        summary = _summary(connection)
        series = _series_by_species(connection)
        coverage = _coverage(connection)
        worst = _worst_per_species(connection)
        anomalies = _anomalies(connection)
        health = _health_rows(connection)
        last_run = connection.execute("SELECT max(run_at) FROM runs").fetchone()[0]
        # Read from the archive rather than from config: the page must name the
        # points it actually plotted, not the ones the collector is set to.
        site_rows = connection.execute("""
            SELECT site, any_value(latitude) AS latitude, any_value(longitude) AS longitude
            FROM readings GROUP BY site ORDER BY site
        """).fetchall()
        sites = [row[0] for row in site_rows]
        episode_hours = (
            _episode_hours(connection, anomalies[0][2], anomalies[0][0], anomalies[0][1])
            if anomalies else []
        )
    finally:
        connection.close()

    now = datetime.now(timezone.utc)

    # Freshness is stated, not implied. A page that silently shows stale data is
    # worse than one that admits it is behind.
    behind_days = (now.date() - summary["last_day"]).days
    freshness = (
        "archive à jour" if behind_days <= 1
        else f"archive en retard de {behind_days} jours"
    )

    incomplete = [day for day in coverage if day[1] < 24]

    # Panels follow the collection order from config, so the page never implies
    # a hierarchy between species that the project does not claim.
    ordered = [s for s in config.SPECIES if s in series]
    ordered += [s for s in sorted(series) if s not in ordered]
    panels = "".join(_panel(species, series[species]) for species in ordered)

    tiles = "".join([
        _tile("Période couverte",
              f"{short_date(summary['first_day'])}/{summary['first_day'].year} → "
              f"{short_date(summary['last_day'])}/{summary['last_day'].year}"),
        _tile("Valeurs horaires", f"{summary['rows']:,}".replace(",", " ")),
        _tile("Villes suivies", str(summary["sites"])),
        _tile("Espèces suivies", str(summary["species"])),
    ])

    worst_table = charts.table(
        ["Espèce", "Journée", "Ville", "Moyenne", "Pointe horaire", "Unité"],
        [[label_for(species), day.isoformat(), site,
          f"{mean:.1f}", f"{peak:.1f}", unit]
         for species, day, site, mean, peak, unit in worst],
    )

    if anomalies:
        species, day, site, mean, peak, unit, typical, score = anomalies[0]

        # When several species peak on the same day at the same place, that is
        # corroboration rather than repetition: one physical event leaves its
        # mark on everything it emits. Worth naming explicitly.
        same_event = [row for row in anomalies[1:]
                      if row[1] == day and row[2] == site]
        corroboration = (
            " Le même jour et au même endroit, "
            + " et ".join(escape(label_for(row[0])) for row in same_event)
            + (" arrive" if len(same_event) == 1 else " arrivent")
            + " aussi en tête du classement : plusieurs espèces indépendantes"
            " désignent un seul événement."
        ) if same_event else ""

        episode_title = f"L'écart le plus fort à la normale : {site}, le {short_date(day)}"
        episode_note = (
            f"{escape(label_for(species))} — moyenne de {mean:.1f} {escape(unit)} "
            f"contre {typical:.1f} en journée médiane, avec une pointe à "
            f"{peak:.1f}. Soit {score:.1f} fois l'écart qui sépare "
            f"habituellement une journée médiane d'une journée déjà chargée."
            f"{corroboration} L'archive désigne elle-même cet épisode : chaque "
            f"journée est ramenée à l'échelle de sa propre espèce, sans quoi "
            f"l'ozone écraserait tout le reste."
        )
        points = [(f"{m.day:02d}/{m.month:02d} {m.hour:02d}h", v)
                  for m, v, _ in episode_hours]
        episode_chart = charts.line_chart(
            points,
            unit=unit,
            width=720,
            height=260,
            x_tick_every=max(len(points) // 6, 1),
            aria_label=f"Valeurs horaires de {label_for(species)} à {site} "
                       f"autour du {day.isoformat()}",
        )
        episode_table = (
            '<details><summary>Voir les valeurs horaires et le classement'
            '</summary><div class="table-wrap">'
            + charts.table(
                ["Espèce", "Journée", "Ville", "Moyenne", "Journée médiane", "Écart"],
                [[label_for(row[0]), row[1].isoformat(), row[2],
                  f"{row[3]:.1f}", f"{row[6]:.1f}", f"×{row[7]:.1f}"]
                 for row in anomalies],
                caption="Les écarts les plus forts de toute l'archive, "
                        "toutes espèces confondues.",
            )
            + '</div><div class="table-wrap">'
            + charts.table(
                ["Heure (UTC)", f"Valeur ({unit})"],
                [[m.strftime("%Y-%m-%d %H:%M"), f"{v:.1f}"] for m, v, _ in episode_hours],
            )
            + "</div></details>"
        )
    else:
        episode_title = "L'écart le plus fort à la normale"
        episode_note = "Pas encore assez de journées complètes pour en désigner un."
        episode_chart = '<p class="empty">Archive trop courte.</p>'
        episode_table = ""

    if health:
        health_table = (
            '<details><summary>Voir le détail des anomalies</summary>'
            '<div class="table-wrap">'
            + charts.table(
                ["Anomalie", "Moment", "Détail", "Ampleur"],
                [list(row) for row in health],
            )
            + "</div></details>"
        )
    else:
        health_table = ('<p class="note">Aucune journée incomplète, aucune panne '
                        'enregistrée. C\'est le résultat attendu.</p>')

    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return template.safe_substitute(
        title="Qualité de l'air en France — historique CAMS",
        style=STYLE_PATH.read_text(encoding="utf-8"),
        updated=french_datetime(last_run) if last_run else french_datetime(now),
        freshness=freshness,
        hero_value=f"{summary['days']:,}".replace(",", " "),
        hero_label="journées archivées, heure par heure",
        script=SCRIPT_PATH.read_text(encoding="utf-8"),
        map=mapview.figure(
            [{"name": name, "latitude": lat, "longitude": lon}
             for name, lat, lon in site_rows],
            ordered,
            SPECIES_LABELS,
        ),
        site_count=str(len(sites)),
        site_list=escape(", ".join(sites[:-1]) + " et " + sites[-1]) if len(sites) > 1
        else escape(sites[0]) if sites else "aucun",
        tiles=tiles,
        panels=panels,
        episode_title=episode_title,
        episode_note=episode_note,
        episode_chart=episode_chart,
        episode_table=episode_table,
        worst_table=worst_table,
        coverage_strip=charts.coverage_strip(coverage),
        complete_days=f"{len(coverage) - len(incomplete)} jours",
        incomplete_days=f"{len(incomplete)} jour(s)",
        health_table=health_table,
        generated_at=french_datetime(now),
    )


def build(database: str = DEFAULT_DATABASE, output_dir: str = DEFAULT_OUTPUT) -> str:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, "index.html")
    Path(path).write_text(render(database), encoding="utf-8")
    return path
