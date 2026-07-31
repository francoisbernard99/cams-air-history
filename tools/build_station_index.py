"""Build the vendored index of French air quality monitoring stations.

Source: European Environment Agency, station metadata for the whole of Europe.
Kept: French stations measuring at least one of the species this project
collects, with their official classification.

Run from the repository root:

    .venv/bin/python tools/build_station_index.py

The output is committed. Regenerate it when the EEA republishes its metadata --
stations open and close a few times a year, not daily.

Why the classification matters more than the coordinates: a traffic station
measures a microenvironment a few metres wide that an 11 km model cell does not
claim to describe. Comparing the two and calling the gap a model error would be
a mistake. The type and area fields are what make an honest comparison possible,
so they are the reason this index exists.

Why activity is read from the download service and not from the metadata: the
metadata's ObservationDateEnd is *declared*, one row per sampling point, and a
station appears in several rows at once. Trusting it means trusting a statement.
Asking the download service which files it currently publishes means observing a
fact. The two disagree by about a third of the network.
"""

import json
import math
import pathlib
import re
import sys
import urllib.request

METADATA_URL = "https://discomap.eea.europa.eu/map/fme/metadata/PanEuropean_metadata.csv"
DOWNLOADS_API = "https://eeadmz1-downloads-api-appservice.azurewebsites.net"
VOCABULARY = "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/"

# dataset 1 is the near-real-time stream: what is being published right now.
NEAR_REAL_TIME = 1

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "tools" / ".eea_metadata.csv"
COMMUNES = ROOT / "web" / "assets" / "communes.json"
OUTPUT = ROOT / "web" / "assets" / "stations.json"

# EEA pollutant vocabulary codes, matching collector/config.py.
SPECIES = {
    "6001": "pm2_5",
    "5": "pm10",
    "8": "nitrogen_dioxide",
    "7": "ozone",
    "1": "sulphur_dioxide",
    "10": "carbon_monoxide",
}

# Kept short: this index is embedded in the page.
TYPES = {"background": 0, "traffic": 1, "industrial": 2}
AREAS = {"urban": 0, "suburban": 1}          # everything rural collapses to 2


def download() -> pathlib.Path:
    if CACHE.is_file():
        print(f"métadonnées en cache : {CACHE.stat().st_size // 1024 // 1024} Mo")
        return CACHE
    print("téléchargement des métadonnées AEE (26 Mo)…")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(METADATA_URL, CACHE)
    return CACHE


def published_now() -> dict[str, set[str]]:
    """Which stations the EEA is currently publishing, and for which species.

    One request per species. The answer is the list of files that exist, so a
    station missing here is not producing data whatever its metadata claims.
    """
    published: dict[str, set[str]] = {}

    for code, name in SPECIES.items():
        body = json.dumps({
            "countries": ["FR"], "cities": [],
            "pollutants": [VOCABULARY + code],
            "dataset": NEAR_REAL_TIME, "source": "Api",
        }).encode()
        request = urllib.request.Request(
            DOWNLOADS_API + "/ParquetFile/urls", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            listing = response.read().decode("utf-8", "replace")

        codes = set(re.findall(r"SPO-(FR[A-Z0-9]+)_", listing))
        for eoi in codes:
            published.setdefault(eoi, set()).add(name)
        print(f"  {name:22} {len(codes):4} stations publient")

    return published


def read_stations(path: pathlib.Path) -> dict:
    """One entry per station, with the set of species it measures."""
    stations: dict[str, dict] = {}

    with open(path, encoding="utf-8", errors="replace") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        column = {name: i for i, name in enumerate(header)}

        for line in handle:
            row = line.rstrip("\n").split("\t")
            if len(row) < len(header) or row[column["Countrycode"]] != "FR":
                continue

            code = row[column["AirPollutantCode"]].rsplit("/", 1)[-1]
            if code not in SPECIES:
                continue

            eoi = row[column["AirQualityStationEoICode"]].strip()
            kind = row[column["AirQualityStationType"]].rsplit("/", 1)[-1]
            area = row[column["AirQualityStationArea"]].rsplit("/", 1)[-1]
            if not eoi or not kind:
                continue

            try:
                lat = float(row[column["Latitude"]])
                lon = float(row[column["Longitude"]])
            except ValueError:
                continue
            # Metropolitan France only: the model grid this project collects
            # stops there, so an overseas station would have nothing to compare.
            if not (41.0 <= lat <= 51.5 and -5.5 <= lon <= 10.0):
                continue

            entry = stations.setdefault(eoi, {
                "code": eoi, "lat": lat, "lon": lon,
                "type": TYPES.get(kind, 0), "area": AREAS.get(area, 2),
                "species": set(),
            })
            entry["species"].add(SPECIES[code])

    return stations


def nearest_commune(stations: dict) -> None:
    """Label each station by the commune whose centre is closest.

    The EEA publishes no human-readable station name, only codes like FR31002.
    A code tells a reader nothing; the nearest town tells them where they are.
    """
    index = json.loads(COMMUNES.read_text(encoding="utf-8"))
    noms = index["noms"].split("\n")
    lons, lats = index["lon"], index["lat"]

    for station in stations.values():
        best, best_d2 = 0, float("inf")
        # Longitude degrees shrink with latitude; without this the labels drift
        # east-west, which is exactly where France is widest.
        cos_lat = math.cos(math.radians(station["lat"]))
        for i in range(len(noms)):
            dx = (lons[i] - station["lon"]) * cos_lat
            dy = lats[i] - station["lat"]
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best, best_d2 = i, d2
        station["commune"] = noms[best]


def main() -> int:
    if not COMMUNES.is_file():
        print(f"manquant : {COMMUNES}", file=sys.stderr)
        return 1

    stations = read_stations(download())
    print(f"{len(stations)} stations dans les métadonnées")

    print("ce que l'AEE publie réellement aujourd'hui :")
    live = published_now()

    # A station's species list becomes what it publishes, not what it declares.
    # Anything still in the metadata but absent from the download service is
    # kept and flagged: the network's history is informative, but it must never
    # be mistaken for something usable.
    for eoi, station in stations.items():
        station["species"] = sorted(live.get(eoi, set()))
        station["active"] = bool(station["species"])

    actives = sum(1 for s in stations.values() if s["active"])
    print(f"{actives} actives, {len(stations) - actives} sans publication courante")

    nearest_commune(stations)

    ordered = sorted(stations.values(), key=lambda s: s["code"])
    payload = {
        "source": "Agence européenne pour l'environnement — métadonnées des "
                  "stations et service de téléchargement (flux temps quasi réel)",
        "types": ["fond", "trafic", "industriel"],
        "areas": ["urbain", "périurbain", "rural"],
        "actives": actives,
        "stations": [
            [s["code"], s["commune"], round(s["lon"], 3), round(s["lat"], 3),
             s["type"], s["area"], s["species"], 1 if s["active"] else 0]
            for s in ordered
        ],
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    counts: dict[tuple, int] = {}
    for s in ordered:
        key = (payload["types"][s["type"]], payload["areas"][s["area"]])
        counts[key] = counts.get(key, 0) + 1
    for (kind, area), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:11} {area:11} {n:4}")

    print(f"écrit : {OUTPUT} ({OUTPUT.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
