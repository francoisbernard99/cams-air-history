"""Tests for the page renderer.

The page is the part a stranger sees, so the checks here are about what must
never silently disappear from it: the caveat, the attribution, and the promise
that nothing is loaded from a third party.
"""

import re

import pytest

from tests.test_warehouse import archive, write_day  # noqa: F401  (pytest fixture)
from warehouse import build as warehouse
from web import build as web


@pytest.fixture
def page(archive):  # noqa: F811
    """A short archive whose values actually move.

    Flat values would leave the anomaly section empty, and the page would be
    tested in a state no real archive is ever in.
    """
    data_dir, database = archive
    for offset, day in enumerate(("2026-07-28", "2026-07-29", "2026-07-30")):
        write_day(data_dir, day, range(24),
                  value=lambda hour, offset=offset: 5.0 + offset * 4 + hour % 5)
    warehouse.build(str(data_dir), database)
    return web.render(database)


def test_the_page_loads_nothing_from_a_third_party(page):
    """The whole point of a static page is that it still works in five years.
    A CDN reference would hand that guarantee to someone else."""
    assert "<script" not in page
    assert "@import" not in page
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    assert all("open-meteo.com" in url or "github.com" in url for url in external)


def test_the_caveat_is_present(page):
    """If this ever drops out of the template, the page starts passing modelled
    values off as measurements. It is the one section that cannot go missing."""
    assert "ne sont pas des mesures" in page
    assert "11 kilomètres" in page
    assert "seuil réglementaire" in page


def test_the_attribution_is_present(page):
    """Required by the CC-BY 4.0 licence of the source."""
    assert "CAMS" in page
    assert "Open-Meteo" in page
    assert "CC-BY 4.0" in page


def test_no_placeholder_survives_rendering(page):
    assert not re.search(r"\$[a-z_]{3,}", page)


def test_every_chart_ships_a_table_view(page):
    """A value must never be reachable only by hovering."""
    assert page.count("<table") >= page.count('class="chart"')


def test_the_page_states_how_fresh_it_is(page):
    assert "archive à jour" in page or "archive en retard" in page


def test_a_flat_archive_has_no_anomaly_and_still_renders(archive):  # noqa: F811
    """A species whose values never move has no spread to standardise against.

    Regression: the anomaly score divides by (p90 - median), which is zero here.
    That returned NULL and crashed the render rather than saying "not enough
    data yet" -- the failure mode of a brand-new archive.
    """
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24), value=6.5)
    warehouse.build(str(data_dir), database)

    rendered = web.render(database)
    assert "Pas encore assez de journées complètes" in rendered


def test_an_unlabelled_species_falls_back_to_its_key(archive):  # noqa: F811
    """Enabling a new species in config.py must never break the build."""
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24), species="glyoxal")
    warehouse.build(str(data_dir), database)

    assert "Glyoxal" in web.render(database)


def test_species_order_follows_the_collection_config(archive):  # noqa: F811
    """The page must not invent a hierarchy between species. Order comes from
    config.SPECIES, not from a judgement made here."""
    data_dir, database = archive
    # One species per file, since a day maps to a single file. Ozone is written
    # first so a wrong order would show up as ozone appearing before PM2.5.
    write_day(data_dir, "2026-07-29", range(24), species="ozone")
    write_day(data_dir, "2026-07-30", range(24), species="pm2_5")
    warehouse.build(str(data_dir), database)

    rendered = web.render(database)
    assert rendered.index("Particules PM2,5") < rendered.index("Ozone (O")


def test_build_writes_a_self_contained_file(archive, tmp_path):  # noqa: F811
    data_dir, database = archive
    write_day(data_dir, "2026-07-29", range(24))
    warehouse.build(str(data_dir), database)

    path = web.build(database, str(tmp_path / "out"))

    with open(path, encoding="utf-8") as handle:
        assert handle.read().startswith("<!doctype html>")
