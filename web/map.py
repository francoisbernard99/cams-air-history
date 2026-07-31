"""Render the interactive map, basemap included, at build time.

The outline, the archived points and the projection parameters are all written
into the page by Python. The script that ships with it only handles clicks and
the live request -- it never has to fetch a basemap.
"""

import json
from html import escape
from pathlib import Path

from web import geo

STATIONS_PATH = Path(__file__).parent / "assets" / "stations.json"


def _stations(proj: dict, labels: dict[str, str]) -> tuple[str, int]:
    """Measurement stations, drawn into the SVG rather than added by script.

    They are the counterpoint to the whole page: the model says what it
    computes, these say what was actually measured. Rendering them server-side
    means they exist even with scripting off, and their tooltips are the
    browser's own.
    """
    if not STATIONS_PATH.is_file():
        return "", 0

    data = json.loads(STATIONS_PATH.read_text(encoding="utf-8"))
    marks = []
    for code, commune, lon, lat, kind, area, species, active in data["stations"]:
        x, y = geo.to_svg(lon, lat, proj)
        mesure = (", ".join(labels.get(s, s) for s in species) if species
                  else "ne publie plus")
        titre = (f"{commune} — {code}\n"
                 f"{data['types'][kind]}, {data['areas'][area]}\n"
                 f"{'mesure : ' + mesure if active else mesure}")
        marks.append(
            f'<circle class="station" data-type="{data["types"][kind]}" '
            f'data-active="{active}" cx="{x:.1f}" cy="{y:.1f}" r="2.6">'
            f"<title>{escape(titre)}</title></circle>"
        )
    return "".join(marks), data


def figure(sites: list[dict], species: list[str], labels: dict[str, str]) -> str:
    """The whole map block: SVG, controls, and the config the script reads."""
    shapes, proj = geo.regions()

    paths = "".join(
        f'<path class="region" d="{shape["d"]}"><title>{escape(shape["name"])}'
        f"</title></path>"
        for shape in shapes
    )

    stations, station_data = _stations(proj, labels)
    total = len(station_data.get("stations", [])) if station_data else 0
    actives = station_data.get("actives", 0) if station_data else 0

    # The archived points, focusable so the map can be driven from a keyboard.
    markers = ""
    for site in sites:
        x, y = geo.to_svg(site["longitude"], site["latitude"], proj)
        markers += (
            f'<circle class="site" cx="{x:.1f}" cy="{y:.1f}" r="5" tabindex="0" '
            f'role="button" aria-label="{escape(site["name"])}">'
            f'<title>{escape(site["name"])}</title></circle>'
        )

    config = json.dumps({
        "scale": proj["scale"],
        "xMin": proj["xMin"],
        "yMax": proj["yMax"],
        "species": species,
        "labels": {key: labels.get(key, key) for key in species},
        # Served from this same site, not a third party, and only fetched if the
        # visitor actually searches. 35 000 communes weigh too much to inline.
        "communes": "communes.json",
    }, ensure_ascii=False)

    return f"""
  <figure id="map-figure" class="map-figure" hidden>
    <figcaption class="map-controls">
      <span class="map-search">
        <label class="sr-only" for="commune">Rechercher une commune</label>
        <input id="commune" type="search" autocomplete="off" role="combobox"
               aria-expanded="false" aria-controls="commune-results"
               placeholder="Commune ou code postal">
        <ul id="commune-results" role="listbox" hidden></ul>
      </span>
      <span class="map-modes" role="group" aria-label="Mode de sélection">
        <button type="button" data-mode="point" aria-pressed="true">Pointer</button>
        <button type="button" data-mode="zone" aria-pressed="false">Zone</button>
      </span>
      <span class="map-layer">
        <label for="stations-filter">Stations</label>
        <select id="stations-filter">
          <option value="none" selected>masquées</option>
          <option value="fond">de fond</option>
          <option value="trafic">de trafic</option>
          <option value="industriel">industrielles</option>
          <option value="all">toutes les actives</option>
          <option value="inactive">celles qui ne publient plus</option>
        </select>
      </span>
      <span id="map-status" class="note">Chargement…</span>
    </figcaption>

    <svg id="map" viewBox="0 0 {proj['width']} {proj['height']}"
         role="application"
         aria-label="Carte de France : cliquez un point pour obtenir ses concentrations">
      {paths}
      <g id="stations" data-showing="none">{stations}</g>
      {markers}
      <rect class="zone-box" x="0" y="0" width="0" height="0" style="display:none"/>
    </svg>

    <p id="stations-note" class="note" hidden>
      Réseau français de mesure, d'après l'Agence européenne pour
      l'environnement&nbsp;: <strong>{actives} stations publient actuellement</strong>,
      sur {total} présentes dans les métadonnées. Les {total - actives} autres
      figurent au registre mais n'envoient plus rien&nbsp;; les afficher comme
      utilisables serait trompeur.
      <br>
      Elles mesurent&nbsp;; la carte, elle, affiche un modèle calculé sur une
      maille d'environ 11&nbsp;km de côté. Une station de trafic décrit quelques
      mètres de rue, que cette maille ne prétend pas représenter&nbsp;: l'écart y
      est attendu, et le lire comme une erreur du modèle serait une faute.
    </p>

    <div id="map-panel" class="map-panel"></div>
  </figure>

  <script type="application/json" id="map-config">{config}</script>
"""
