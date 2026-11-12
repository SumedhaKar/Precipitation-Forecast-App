"""Build the town list the website's search box reads. SPEC 11.28.

Writes `web/src/towns.json` from Natural Earth 1:10m populated places, which
is public domain and the same source family as the two outlines the map draws
(SPEC 11.14).

Which towns
-----------
A town is in the list when its point falls **inside the drawn India
outline** -- `ne_10m_admin_0_countries_ind`, the India point-of-view edition,
the same geometry the forecast mask was cut with (SPEC 3.5).

That is a geometric rule, not a judgement of mine, and it is the rule the
rest of this project already runs on: the outline decides what is India, so
it decides which towns are in India too. It gives 215 towns. 214 of them are
the ones Natural Earth's own `ADM0NAME` field calls India, and the 215th is
Gilgit, which Natural Earth's `FCLASS_IN` field -- its India point-of-view
column -- also marks. Nothing from Nepal, Bangladesh, Bhutan or Myanmar
creeps in: the count by `ADM0NAME` of the towns inside the outline is exactly
`{India: 214, Pakistan: 1}`.

Which square
------------
Each town is resolved by the rule of SPEC 11.7, the same one `api/place` uses
for any point: its own 0.25 degree square if that square is in the India
mask, otherwise the nearest of the eight squares one step out, nearest first
and ties broken north then west. The list stores the square the page will
show, never the town's own position, so a coordinate finer than 28 km never
reaches the bundle.

A town with no India square within one step is written with `not_forecast`
and the island group it is in, and the page says so in words rather than
sending a request that can only fail (SPEC 11.28). Two towns are like this,
and both are islands:

    Kavaratti     Lakshadweep, 10.50 N 72.75 E, land fraction 0.0000,
                  square centre 13.4 km from the nearest land in the outline
    Port Blair    Andaman & Nicobar, 11.75 N 92.75 E, centre inside the
                  outline but land fraction 0.0469, under the 0.5 of SPEC 3.5

The script checks all of that rather than assuming it, and fails instead of
writing if any of it stops being true.

    python scripts/build_towns.py
    python scripts/build_towns.py --check    # verify, write nothing
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import shapefile
from shapely.geometry import Point, shape
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg  # noqa: E402

NE = cfg.RAW / "ne"
PLACES = NE / "ne_10m_populated_places"
ADMIN0 = NE / "ne_10m_admin_0_countries_ind"

PLACES_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/"
    "ne_10m_populated_places.zip"
)
PLACES_SHA256 = "cd149186f03d2603e0410da399b980a4357d0ac32d3a2305a49ed3dffcc41d7b"
PLACES_VERSION = "5.1.2"

MASK_FILE = cfg.ROOT / "config" / "india_mask.json"
OUT = cfg.ROOT / "web" / "src" / "towns.json"

# SPEC 1.4, the India box, and SPEC 8.4's grid.
LAT_MAX, LAT_MIN = 38.0, 6.0
LON_MIN, LON_MAX = 68.0, 98.0
STEP = 0.25

# Bytes. The list goes into the page's first chunk, because the search box is
# there from the first paint, so it is kept small enough not to matter next to
# the 78 KB that chunk already is (SPEC 11.16).
GZIP_BUDGET = 12_000

# What the script refuses to write without. Measured, and recorded in
# SPEC 11.28; if Natural Earth changes, these numbers change with a note
# rather than quietly.
EXPECT_TOWNS = 215
EXPECT_BY_COUNTRY = {"India": 214, "Pakistan": 1}
EXPECT_NOT_FORECAST = {"Kavaratti": "Lakshadweep",
                       "Port Blair": "Andaman & Nicobar"}

# The groups of SPEC 11.28 and config/india_mask.json, inclusive bounds.
ISLAND_GROUPS = {
    "Lakshadweep": {"lat": (8.0, 12.5), "lon": (71.5, 74.0)},
    "Andaman & Nicobar": {"lat": (6.0, 14.0), "lon": (92.0, 94.5)},
}


def download() -> None:
    """Fetch the populated places shapefile if it is not already here."""
    import zipfile

    import requests

    if PLACES.with_suffix(".shp").exists():
        return
    NE.mkdir(parents=True, exist_ok=True)
    target = PLACES.with_suffix(".zip")
    print(f"fetching {PLACES_URL}")
    answer = requests.get(PLACES_URL, timeout=180)
    answer.raise_for_status()
    got = hashlib.sha256(answer.content).hexdigest()
    if got != PLACES_SHA256:
        raise SystemExit(
            f"ne_10m_populated_places.zip is sha256 {got}, not {PLACES_SHA256}")
    target.write_bytes(answer.content)
    with zipfile.ZipFile(target) as archive:
        archive.extractall(NE)
    print(f"  {len(answer.content)} bytes, sha256 {got}")


def outline():
    """The India point-of-view polygon the mask was cut with."""
    reader = shapefile.Reader(str(ADMIN0))
    fields = [f[0] for f in reader.fields[1:]]
    for item in reader.iterShapeRecords():
        record = dict(zip(fields, item.record))
        if record.get("ADMIN") == "India":
            return shape(item.shape.__geo_interface__)
    raise SystemExit(f"no India feature in {ADMIN0.name}")


def mask_rows() -> list[str]:
    mask = json.loads(MASK_FILE.read_text("utf8"))
    grid = mask["grid"]
    if (grid["lat_first"], grid["lon_first"], grid["step"]) != (
            LAT_MAX, LON_MIN, STEP):
        raise SystemExit(f"{MASK_FILE.name} is on a different grid")
    return mask["india_rows"]


def snap(lat: float, lon: float) -> tuple[int, int, float, float]:
    i = round((LAT_MAX - lat) / STEP)
    j = round((lon - LON_MIN) / STEP)
    return i, j, round(LAT_MAX - STEP * i, 2), round(LON_MIN + STEP * j, 2)


def square_of(i: int, j: int) -> tuple[float, float]:
    return round(LAT_MAX - STEP * i, 2), round(LON_MIN + STEP * j, 2)


def resolve(rows: list[str], lat: float, lon: float) -> dict:
    """SPEC 11.7: the town's own square, or the nearest one step out."""

    def is_india(i: int, j: int) -> bool:
        return (0 <= i < len(rows) and 0 <= j < len(rows[i])
                and rows[i][j] == "1")

    i, j, s_lat, s_lon = snap(lat, lon)
    if is_india(i, j):
        return {"lat": s_lat, "lon": s_lon}

    ring = [(i + di, j + dj)
            for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di, dj) != (0, 0)]
    ring.sort(key=lambda t: ((t[0] - i) ** 2 + (t[1] - j) ** 2, t[0], t[1]))
    for ni, nj in ring:
        if is_india(ni, nj):
            n_lat, n_lon = square_of(ni, nj)
            return {"lat": n_lat, "lon": n_lon,
                    "moved_from": {"lat": s_lat, "lon": s_lon}}

    group = None
    for name, box in ISLAND_GROUPS.items():
        if (box["lat"][0] <= lat <= box["lat"][1]
                and box["lon"][0] <= lon <= box["lon"][1]):
            group = name
    return {"lat": s_lat, "lon": s_lon, "not_forecast": group}


def build() -> tuple[dict, list[str]]:
    """The towns.json body, and the by-country tally for the checks."""
    rows = mask_rows()
    ready = prep(outline())

    reader = shapefile.Reader(str(PLACES))
    fields = [f[0] for f in reader.fields[1:]]
    found = []
    for item in reader.iterShapeRecords():
        lon, lat = item.shape.points[0]
        if not ready.contains(Point(lon, lat)):
            continue
        record = dict(zip(fields, item.record))
        found.append({
            "name": str(record["NAME"]).strip(),
            "state": str(record["ADM1NAME"]).strip(),
            "country": str(record["ADM0NAME"]).strip(),
            "lat": float(lat),
            "lon": float(lon),
        })

    # A duplicated name has to be told apart, or searching it would show one
    # town's numbers under the other's name. Two Aurangabads, in Bihar and in
    # Maharashtra, are the only pair; the state comes from the file's own
    # ADM1NAME and is written only where it is needed, because the field is
    # not always right (it calls Bhavnagar "Dadra and Nagar Haveli") and an
    # unnecessary wrong label is worse than none.
    seen: dict[str, int] = {}
    for town in found:
        seen[town["name"]] = seen.get(town["name"], 0) + 1
    repeated = {name for name, count in seen.items() if count > 1}

    towns = []
    for town in sorted(found, key=lambda t: (t["name"], t["state"])):
        entry = {"name": town["name"]}
        if town["name"] in repeated:
            entry["state"] = town["state"]
        entry.update(resolve(rows, town["lat"], town["lon"]))
        towns.append(entry)

    body = {
        "note": (
            "SPEC 11.28. Towns from Natural Earth 1:10m populated places, "
            f"version {PLACES_VERSION}, public domain, kept where the point "
            "falls inside the drawn India point-of-view outline, which is the "
            "same geometry the forecast mask was cut with. `lat` and `lon` are "
            "the 0.25 degree square the page shows, never the town's own "
            "position. `moved_from` is the town's own square where that square "
            "is sea on this grid and the nearest land square one step away is "
            "shown instead. `not_forecast` names an island group with no "
            "square within one step. Built by scripts/build_towns.py."
        ),
        "source": {
            "layer": "ne_10m_populated_places",
            "version": PLACES_VERSION,
            "url": PLACES_URL,
            "sha256": PLACES_SHA256,
            "licence": "public domain",
            "rule": "point inside ne_10m_admin_0_countries_ind, India "
                    "point-of-view edition, the ADMIN = India feature",
        },
        "towns": towns,
    }
    return body, [t["country"] for t in found]


def written(body: dict) -> bytes:
    return (json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed file, write nothing")
    args = parser.parse_args()

    download()
    body, countries = build()
    raw = written(body)
    towns = body["towns"]

    tally: dict[str, int] = {}
    for country in countries:
        tally[country] = tally.get(country, 0) + 1
    moved = [t for t in towns if "moved_from" in t]
    missing = {t["name"]: t["not_forecast"] for t in towns
               if "not_forecast" in t}
    gz = len(gzip.compress(raw, 9))

    print(f"towns:   {len(towns)}, {len(raw)} bytes, {gz} gzipped, "
          f"budget {GZIP_BUDGET}")
    print(f"by country inside the outline: {tally}")
    print(f"own square in the mask: {len(towns) - len(moved) - len(missing)}, "
          f"nearest land square one step out: {len(moved)}, "
          f"no square within one: {len(missing)}")
    print(f"not forecast: {missing}")

    if len(towns) != EXPECT_TOWNS:
        raise SystemExit(f"{len(towns)} towns, not the {EXPECT_TOWNS} "
                         "measured for SPEC 11.28")
    if tally != EXPECT_BY_COUNTRY:
        raise SystemExit(f"inside the outline by country is {tally}, not "
                         f"{EXPECT_BY_COUNTRY}")
    if missing != EXPECT_NOT_FORECAST:
        raise SystemExit(f"the towns with no square are {missing}, not "
                         f"{EXPECT_NOT_FORECAST}")
    if gz > GZIP_BUDGET:
        raise SystemExit(f"{gz} gzipped bytes is over the budget")
    for town in towns:
        if not (LAT_MIN <= town["lat"] <= LAT_MAX
                and LON_MIN <= town["lon"] <= LON_MAX):
            raise SystemExit(f"{town['name']} is outside the India box")

    if args.check:
        if not OUT.exists():
            raise SystemExit(f"{OUT} does not exist")
        # Compared with the line endings normalised, because git is allowed
        # to change them: this repository stores LF and `core.autocrlf` is on,
        # so a fresh clone on Windows has the same file with CRLF in it. Every
        # byte that says anything is still compared.
        if OUT.read_bytes().replace(b"\r\n", b"\n") != raw:
            raise SystemExit(f"{OUT} is not what this script would write")
        print("checked: the committed file is byte for byte what this writes,"
              " line endings aside")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(raw)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
