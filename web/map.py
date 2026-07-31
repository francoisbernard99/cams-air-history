"""Render the interactive map, basemap included, at build time.

The outline, the archived points and the projection parameters are all written
into the page by Python. The script that ships with it only handles clicks and
the live request -- it never has to fetch a basemap.
"""

import json
from html import escape

from web import geo


def figure(sites: list[dict], species: list[str], labels: dict[str, str]) -> str:
    """The whole map block: SVG, controls, and the config the script reads."""
    shapes, proj = geo.regions()

    paths = "".join(
        f'<path class="region" d="{shape["d"]}"><title>{escape(shape["name"])}'
        f"</title></path>"
        for shape in shapes
    )

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
      <span id="map-status" class="note">Chargement…</span>
    </figcaption>

    <svg id="map" viewBox="0 0 {proj['width']} {proj['height']}"
         role="application"
         aria-label="Carte de France : cliquez un point pour obtenir ses concentrations">
      {paths}
      {markers}
      <rect class="zone-box" x="0" y="0" width="0" height="0" style="display:none"/>
    </svg>

    <div id="map-panel" class="map-panel"></div>
  </figure>

  <script type="application/json" id="map-config">{config}</script>
"""
