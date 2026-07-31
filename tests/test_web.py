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


def test_the_page_loads_no_third_party_code_or_asset(page):
    """The contract changed when the map arrived, and it is worth stating
    exactly: the page may now carry a script, but that script is written here
    and inlined. Nothing is *fetched* from a third party to render the page --
    no CDN, no stylesheet, no tile server, no font. That is what keeps the page
    working in five years without depending on anyone."""
    assert "<script src" not in page
    assert "@import" not in page
    assert "<link" not in page

    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
    allowed = ("open-meteo.com", "github.com")
    assert all(any(host in url for host in allowed) for url in external), external


def test_the_only_live_call_goes_to_the_documented_api(page):
    """A click asks Open-Meteo directly from the visitor's browser. Any other
    host appearing here would mean data is being routed somewhere undisclosed."""
    hosts = set(re.findall(r'https?://([a-z0-9.-]+)', page))
    assert hosts <= {
        "air-quality-api.open-meteo.com",  # the live request
        "open-meteo.com",                  # attribution
        "github.com",                      # source
        "www.w3.org",                      # SVG namespace, not a request
    }, hosts


def test_light_is_the_default_theme(page):
    """The page must open the same way for everyone, whatever their system is
    set to. A `prefers-color-scheme` rule would quietly override that."""
    assert "prefers-color-scheme" not in page

    # The served <html> tag must carry no theme: dark is only ever stamped on it
    # later, by the reader's own stored choice.
    html_tag = re.search(r"<html[^>]*>", page).group(0)
    assert "data-theme" not in html_tag, html_tag


def test_a_theme_switch_is_offered(page):
    """Light by default is a choice made for the reader; the button is what
    hands the choice back."""
    assert 'id="theme-toggle"' in page
    assert ':root[data-theme="dark"]' in page
    assert "localStorage" in page


def test_the_caveat_is_present(page):
    """If this drops out, the page starts passing modelled values off as
    measurements. Asserted on the claims rather than on one exact sentence, so
    rewording the page does not silently disarm the check."""
    assert "ne sont pas des mesures" in page
    assert "11 km" in page
    assert "seuil réglementaire" in page
    assert "moyenne une agglomération" in page


def test_the_caveat_also_travels_with_the_live_values(page):
    """The map panel is built by the script, far from the page's own prose. A
    reader who only ever clicks the map must still be told what they are seeing."""
    panel_note = "pas des mesures"
    assert page.count(panel_note) >= 2


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
