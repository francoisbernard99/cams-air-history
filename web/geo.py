"""Turn the vendored GeoJSON outline into SVG paths, at build time.

The basemap is computed once by Python and embedded in the page, so the map
needs no tile server and no map library. That keeps the promise the rest of the
project makes: nothing is fetched from a third party to render the page.

The projection is Web Mercator, chosen because its inverse is three lines of
arithmetic -- the browser has to turn a click position back into a longitude
and latitude, and that has to be exact.
"""

import json
import math
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
REGIONS_PATH = ASSETS / "regions.geojson"

# Metropolitan France, with a little air around it.
LON_MIN, LON_MAX = -5.4, 9.8
LAT_MIN, LAT_MAX = 41.2, 51.3

# Simplification tolerance, in SVG units. Roughly "drop any vertex that sits
# less than a third of a pixel off the line it would replace".
TOLERANCE = 0.35


def mercator(lon: float, lat: float) -> tuple[float, float]:
    """Longitude/latitude in degrees to Web Mercator, in radians."""
    lat = max(min(lat, 85.0), -85.0)
    return (
        math.radians(lon),
        math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)),
    )


def projection(width: float) -> dict:
    """Everything needed to project, and to invert the projection in JS."""
    x_min, y_min = mercator(LON_MIN, LAT_MIN)
    x_max, y_max = mercator(LON_MAX, LAT_MAX)
    scale = width / (x_max - x_min)
    return {
        "width": round(width, 2),
        "height": round((y_max - y_min) * scale, 2),
        "xMin": x_min,
        "yMax": y_max,
        "scale": scale,
        "lonMin": LON_MIN,
        "lonMax": LON_MAX,
        "latMin": LAT_MIN,
        "latMax": LAT_MAX,
    }


def to_svg(lon: float, lat: float, proj: dict) -> tuple[float, float]:
    x, y = mercator(lon, lat)
    return ((x - proj["xMin"]) * proj["scale"],
            (proj["yMax"] - y) * proj["scale"])


def _simplify(points: list[tuple[float, float]], tolerance: float) -> list:
    """Douglas-Peucker, written as a loop rather than recursion.

    A coastline can carry thousands of vertices, and Python's recursion limit is
    a poor reason for a build to fail.
    """
    if len(points) < 3:
        return points

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]

    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue

        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)

        furthest, worst = first, -1.0
        for index in range(first + 1, last):
            px, py = points[index]
            if length == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                distance = abs(dy * px - dx * py + bx * ay - by * ax) / length
            if distance > worst:
                furthest, worst = index, distance

        if worst > tolerance:
            keep[furthest] = True
            stack.append((first, furthest))
            stack.append((furthest, last))

    return [point for point, kept in zip(points, keep) if kept]


def _rings(geometry: dict) -> list:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def _path(ring: list, proj: dict) -> str:
    points = _simplify([to_svg(lon, lat, proj) for lon, lat, *_ in ring], TOLERANCE)
    if len(points) < 3:
        return ""
    # One decimal is about 20 metres at this scale -- far finer than a
    # coastline drawn 700 pixels wide can show, and it halves the page weight.
    body = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}"
                    for i, (x, y) in enumerate(points))
    return body + "Z"


def regions(width: float = 760) -> tuple[list[dict], dict]:
    """The region outlines as SVG paths, plus the projection they used."""
    proj = projection(width)
    data = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))

    shapes = []
    for feature in data["features"]:
        paths = [_path(ring, proj) for ring in _rings(feature["geometry"])]
        paths = [path for path in paths if path]
        if paths:
            shapes.append({
                "code": feature["properties"]["code"],
                "name": feature["properties"]["nom"],
                "d": " ".join(paths),
            })
    return shapes, proj
