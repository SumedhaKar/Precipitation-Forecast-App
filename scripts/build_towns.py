"""Build the town list the search reads and the names the map draws.

SPEC 11.28 and 11.29. Two files, from Natural Earth 1:10m, which is public
domain and the same source family as the two outlines the map draws
(SPEC 11.14):

  web/src/towns.json   every populated place inside the India outline, for
                       the search box. 215 towns.
  web/src/units.json   the 36 states and union territories of admin-1, each
                       with a point to write its name at and the one city the
                       map labels inside it.

The second file is built here rather than in scripts/build_outline.py because
choosing a unit's city is a question about populated places -- which of them
is a capital, and which is the largest -- and this is the script that already
reads them.

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
from shapely.geometry import LineString, Point, shape
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg  # noqa: E402

NE = cfg.RAW / "ne"
PLACES = NE / "ne_10m_populated_places"
ADMIN0 = NE / "ne_10m_admin_0_countries_ind"
ADMIN1 = NE / "ne_10m_admin_1_states_provinces"

PLACES_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/"
    "ne_10m_populated_places.zip"
)
PLACES_SHA256 = "cd149186f03d2603e0410da399b980a4357d0ac32d3a2305a49ed3dffcc41d7b"
PLACES_VERSION = "5.1.2"

MASK_FILE = cfg.ROOT / "config" / "india_mask.json"
OUT = cfg.ROOT / "web" / "src" / "towns.json"
OUT_UNITS = cfg.ROOT / "web" / "src" / "units.json"

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

# SPEC 11.29, the second file this script writes: the names the map draws.
#
# One entry per India admin-1 unit -- 28 states and 8 union territories, which
# is what `admin == "India"` gives in ne_10m_admin_1_states_provinces -- with
# a point to write the unit's name at and the one city the map labels inside
# it. Union territories are in the same list as states because the map draws
# them the same way; `code` is Natural Earth's own `postal` field, which the
# page falls back to when a long name will not fit inside a small unit.
#
# The city is the unit's capital where Natural Earth marks one inside the
# unit's polygon, and otherwise the largest town inside it by `POP_MAX`. Two
# units have no capital of their own inside them, because Chandigarh is the
# capital of both Punjab and Haryana and is a union territory in its own
# right, so those two get their largest town instead: Ludhiana and Faridabad.
UNITS_EXPECT = 36
UNITS_EXPECT_CAPITALS = 34
UNITS_EXPECT_REP_POINT = {"Andhra Pradesh", "Jammu and Kashmir"}
UNITS_GZIP_BUDGET = 2_500

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


def inside(ready) -> list[dict]:
    """Every populated place whose point falls inside the India outline.

    The one pass both files are built from. `kind` is Natural Earth's own
    `FEATURECLA`, which is how a capital is recognised, and `pop` its
    `POP_MAX`, which is how the largest town is; neither reaches the browser
    except as the order the units are listed in.
    """
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
            "kind": str(record["FEATURECLA"]).strip(),
            "pop": int(record["POP_MAX"] or 0),
            "lat": float(lat),
            "lon": float(lon),
        })
    return found


def build(found: list[dict]) -> tuple[dict, list[str]]:
    """The towns.json body, and the by-country tally for the checks."""
    rows = mask_rows()

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


def admin1() -> list[tuple[dict, object]]:
    """The India units of admin-1, largest polygon first.

    Largest first is the order the map tries to place the names in, so the
    name a small union territory has no room for is the one that gives way,
    not Rajasthan's. The area is in square degrees, which is only ever
    compared with another area here, so no projection is needed.
    """
    reader = shapefile.Reader(str(ADMIN1))
    fields = [f[0] for f in reader.fields[1:]]
    found = []
    for item in reader.iterShapeRecords():
        record = dict(zip(fields, item.record))
        if str(record.get("admin")) != "India":
            continue
        found.append((record, shape(item.shape.__geo_interface__)))
    found.sort(key=lambda unit: -unit[1].area)
    return found


def label_point(record: dict, poly) -> tuple[object, str]:
    """Where to write a unit's name, which must be inside the unit.

    Natural Earth publishes a label point per unit in its `latitude` and
    `longitude` fields and it is usually the better one, because it is placed
    by eye. It is used only when it is actually inside the polygon: for Andhra
    Pradesh and for Jammu and Kashmir it is not, and those two fall back to
    shapely's representative point of the largest part, which is inside by
    construction. A name written outside its own unit would be worse than an
    awkwardly placed one.
    """
    own = Point(float(record["longitude"]), float(record["latitude"]))
    if poly.contains(own):
        return own, "natural earth label point"
    biggest = (max(poly.geoms, key=lambda part: part.area)
               if poly.geom_type == "MultiPolygon" else poly)
    return biggest.representative_point(), "representative point"


def room_at(poly, at) -> float:
    """How wide the unit is, in degrees of longitude, at the label point.

    SPEC 11.29. A name is written across the unit, so what decides whether it
    can be written at all is how much unit there is to write it on. This cuts
    the unit with a horizontal line through the label point and measures the
    piece of that line the label point is on: 11.5 degrees for Madhya
    Pradesh, 0.42 for Dadra and Nagar Haveli and Daman and Diu.

    Without it the map wrote DADRA AND NAGAR HAVELI AND DAMAN AND DIU across
    230 pixels of the Arabian Sea for a union territory 7 pixels wide, which
    reads as a name for the sea. A unit with no room for its name is marked
    with its two letter code until the reader zooms in far enough for the
    name to fit inside it.
    """
    west, _, east, _ = poly.bounds
    cut = LineString([(west - 1, at.y), (east + 1, at.y)]).intersection(poly)
    if cut.is_empty:
        return 0.0
    pieces = list(getattr(cut, "geoms", [cut]))
    here = [piece for piece in pieces
            if piece.bounds[0] - 1e-9 <= at.x <= piece.bounds[2] + 1e-9]
    chosen = here or pieces
    return max(piece.bounds[2] - piece.bounds[0] for piece in chosen)


def main_city(mine: list[dict]) -> dict | None:
    """The one city the map labels in a unit, or None if it has no town.

    The capital if Natural Earth marks one inside the unit -- the national
    capital first, so Delhi gets New Delhi -- and otherwise the largest town
    by population. Every town considered here is already in towns.json, so
    "the capital is not in the town list" and "the unit has no capital inside
    it" are the same case and both land on the largest town.
    """
    caps = [town for town in mine if "capital" in town["kind"].lower()]
    if caps:
        caps.sort(key=lambda town: (0 if "admin-0" in town["kind"].lower()
                                    else 1, -town["pop"], town["name"]))
        return caps[0]
    if not mine:
        return None
    return sorted(mine, key=lambda town: (-town["pop"], town["name"]))[0]


def build_units(found: list[dict]) -> tuple[dict, dict]:
    """The units.json body, and the tally the checks are made against."""
    rows = mask_rows()
    points = [(town, Point(town["lon"], town["lat"])) for town in found]

    units = []
    tally = {"capitals": 0, "rep_point": set(), "not_forecast": {},
             "no_city": []}
    for record, poly in admin1():
        name = str(record["name"]).strip()
        code = str(record["postal"]).strip() \
            or str(record["iso_3166_2"]).strip().split("-")[-1]
        at, how = label_point(record, poly)
        if how == "representative point":
            tally["rep_point"].add(name)
        mine = [town for town, point in points if poly.contains(point)]
        city = main_city(mine)
        entry = {
            "name": name,
            "code": code,
            "lat": round(at.y, 3),
            "lon": round(at.x, 3),
            "span": round(room_at(poly, at), 2),
        }
        if city is None:
            tally["no_city"].append(name)
        else:
            if "capital" in city["kind"].lower():
                tally["capitals"] += 1
            square = resolve(rows, city["lat"], city["lon"])
            entry["city"] = {"name": city["name"], "pop": city["pop"],
                             **square}
            if square.get("not_forecast"):
                tally["not_forecast"][city["name"]] = square["not_forecast"]
        units.append(entry)

    body = {
        "note": (
            "SPEC 11.29. The 28 states and 8 union territories of Natural "
            "Earth 1:10m admin-1, `admin = India`, listed largest polygon "
            "first, which is the order the map tries to place their names in. "
            "`lat` and `lon` are where the unit's name is written and are "
            "inside the unit. `code` is Natural Earth's own `postal` field, "
            "shown instead of the name where the name does not fit. `city` is "
            "the one town the map labels in that unit -- its capital where "
            "Natural Earth marks one inside the unit, otherwise the largest "
            "town inside it by population -- and its `lat` and `lon` are the "
            "0.25 degree square the page shows, never the town's own "
            "position. Built by scripts/build_towns.py."
        ),
        "source": {
            "units": "ne_10m_admin_1_states_provinces",
            "cities": "ne_10m_populated_places",
            "version": PLACES_VERSION,
            "licence": "public domain",
            "rule": "admin = India, and the town's point inside the unit's "
                    "own polygon",
        },
        "units": units,
    }
    return body, tally


def written(body: dict) -> bytes:
    return (json.dumps(body, indent=1, ensure_ascii=False) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed file, write nothing")
    args = parser.parse_args()

    download()
    found = inside(prep(outline()))
    body, countries = build(found)
    raw = written(body)
    towns = body["towns"]
    units_body, units_tally = build_units(found)
    units_raw = written(units_body)
    units = units_body["units"]

    countries_tally: dict[str, int] = {}
    for country in countries:
        countries_tally[country] = countries_tally.get(country, 0) + 1
    moved = [t for t in towns if "moved_from" in t]
    missing = {t["name"]: t["not_forecast"] for t in towns
               if "not_forecast" in t}
    gz = len(gzip.compress(raw, 9))
    units_gz = len(gzip.compress(units_raw, 9))

    print(f"towns:   {len(towns)}, {len(raw)} bytes, {gz} gzipped, "
          f"budget {GZIP_BUDGET}")
    print(f"units:   {len(units)}, {len(units_raw)} bytes, {units_gz} "
          f"gzipped, budget {UNITS_GZIP_BUDGET}")
    print(f"  cities that are the unit's own capital: "
          f"{units_tally['capitals']} of {len(units)}")
    print(f"  name placed at shapely's representative point: "
          f"{sorted(units_tally['rep_point'])}")
    print(f"  main city with no square: {units_tally['not_forecast']}")
    print(f"  units with no town inside them: {units_tally['no_city']}")
    print(f"by country inside the outline: {countries_tally}")
    print(f"own square in the mask: {len(towns) - len(moved) - len(missing)}, "
          f"nearest land square one step out: {len(moved)}, "
          f"no square within one: {len(missing)}")
    print(f"not forecast: {missing}")

    if len(towns) != EXPECT_TOWNS:
        raise SystemExit(f"{len(towns)} towns, not the {EXPECT_TOWNS} "
                         "measured for SPEC 11.28")
    if countries_tally != EXPECT_BY_COUNTRY:
        raise SystemExit(f"inside the outline by country is "
                         f"{countries_tally}, not {EXPECT_BY_COUNTRY}")
    if missing != EXPECT_NOT_FORECAST:
        raise SystemExit(f"the towns with no square are {missing}, not "
                         f"{EXPECT_NOT_FORECAST}")
    if gz > GZIP_BUDGET:
        raise SystemExit(f"{gz} gzipped bytes is over the budget")
    for town in towns:
        if not (LAT_MIN <= town["lat"] <= LAT_MAX
                and LON_MIN <= town["lon"] <= LON_MAX):
            raise SystemExit(f"{town['name']} is outside the India box")

    if len(units) != UNITS_EXPECT:
        raise SystemExit(f"{len(units)} admin-1 units, not the {UNITS_EXPECT} "
                         "measured for SPEC 11.29")
    if units_tally["capitals"] != UNITS_EXPECT_CAPITALS:
        raise SystemExit(f"{units_tally['capitals']} of the main cities are "
                         f"their unit's capital, not {UNITS_EXPECT_CAPITALS}")
    if units_tally["rep_point"] != UNITS_EXPECT_REP_POINT:
        raise SystemExit("the units whose name is placed at a representative "
                         f"point are {sorted(units_tally['rep_point'])}, not "
                         f"{sorted(UNITS_EXPECT_REP_POINT)}")
    if units_tally["no_city"]:
        raise SystemExit("no town inside "
                         f"{units_tally['no_city']}, so it has no main city")
    if units_gz > UNITS_GZIP_BUDGET:
        raise SystemExit(f"{units_gz} gzipped bytes is over the units budget")
    for unit in units:
        if not unit["code"]:
            raise SystemExit(f"{unit['name']} has no postal code")
        if not (LAT_MIN <= unit["lat"] <= LAT_MAX
                and LON_MIN <= unit["lon"] <= LON_MAX):
            raise SystemExit(f"{unit['name']}'s name is outside the India box")

    if args.check:
        for path, wanted in ((OUT, raw), (OUT_UNITS, units_raw)):
            if not path.exists():
                raise SystemExit(f"{path} does not exist")
            # Compared with the line endings normalised, because git is
            # allowed to change them: this repository stores LF and
            # `core.autocrlf` is on, so a fresh clone on Windows has the same
            # file with CRLF in it. Every byte that says anything is still
            # compared.
            if path.read_bytes().replace(b"\r\n", b"\n") != wanted:
                raise SystemExit(f"{path} is not what this script would write")
        print("checked: both committed files are byte for byte what this "
              "writes, line endings aside")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(raw)
    print(f"wrote {OUT}")
    OUT_UNITS.write_bytes(units_raw)
    print(f"wrote {OUT_UNITS}")


if __name__ == "__main__":
    main()
