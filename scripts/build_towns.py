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
import math
import sys
from pathlib import Path

import shapefile
from shapely.geometry import Point, box as make_box, shape
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
# Natural Earth versions each layer's own VERSION.txt, and they differ.
ADMIN1_VERSION = "5.1.1"

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
# unit's polygon, unless the largest town inside it is more than three times
# the size, and otherwise the largest town inside it by `POP_MAX`. Five of
# the 36 are not their unit's capital. Two have no capital of their own
# inside them, because Chandigarh is the capital of both Punjab and Haryana
# and is a union territory in its own right, so those two get Ludhiana and
# Faridabad; and three are outgrown by a neighbour under the three times
# rule: Gujarat gets Ahmedabad, Assam gets Guwahati, Delhi gets Delhi.
UNITS_EXPECT = 36
UNITS_EXPECT_CAPITALS = 31
UNITS_EXPECT_REP_POINT = {"Andhra Pradesh", "Jammu and Kashmir"}
UNITS_GZIP_BUDGET = 4_000

# How much room there is to write a unit's name inside the unit. SPEC 11.31.
#
# A full name is written at the unit's own label point and nowhere else, and
# only when the whole word fits inside the unit's own polygon. Deciding that
# on the page needs the polygon, and the polygons are 3 MB of shapefile that
# the page has no other use for -- so the question is answered here instead,
# where the polygons are, and what the page carries is the answer.
#
# A label box is centred on the label point, so one number settles each shape
# of box: the tallest box of that shape which is still inside the unit. These
# are the shapes, as width over height in degrees, and `fit` in units.json is
# half the height in degrees for each of them in turn. A box is drawn only if
# it is no taller than the entry for the first shape at least as wide as it
# is, which is the conservative side of the table: the box tested is wider
# than the box drawn, so a box that passes is inside with room to spare.
#
# Up to 25: a name 25 times wider than it is tall is about 350 pixels of
# capitals, which no unit on this map has room for at any zoom a reader
# starts at. Anything wider than the last shape is refused outright.
FIT_ASPECTS = (2.0, 4.0, 6.0, 9.0, 13.0, 18.0, 25.0)

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


def assign_units(found: list[dict]) -> dict[str, int]:
    """Put every town in its state or union territory. SPEC 11.38.

    Natural Earth's own `ADM1NAME` on the populated-places layer is not
    reliable -- it calls Bhavnagar "Dadra and Nagar Haveli" -- so the unit
    is decided the way the map decides it: the town's own point against the
    unit's own polygon, from the admin-1 layer. A town on a boundary that
    no polygon contains is left without one and reported, rather than
    guessed at.

    This is what lets a reader type "Kerala" and be given the cities inside
    Kerala, and it is why the search can refuse to put one count on a whole
    state: the state is a list of cities and never a square.
    """
    points = [(town, Point(town["lon"], town["lat"])) for town in found]
    tally: dict[str, int] = {}
    for record, poly in admin1():
        name = str(record["name"]).strip()
        ready = prep(poly)
        for town, point in points:
            if "unit" in town:
                continue
            if ready.contains(point):
                town["unit"] = name
                tally[name] = tally.get(name, 0) + 1
    return tally


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
        # SPEC 11.38: the unit the point is actually in, from the admin-1
        # polygons, which is what the search groups cities by.
        if town.get("unit"):
            entry["unit"] = town["unit"]
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


def room_for(poly, lon: float, lat: float, aspect: float) -> float:
    """The tallest box of this shape that fits inside the unit, centred.

    SPEC 11.31. The unit's name is written at one place and one place only --
    the middle of the box is the label point -- so the question "does this
    name fit inside this unit" is the question "is this box inside this
    polygon", and the answer is a single number per shape of box: boxes of
    one shape nest, so if a box of a given height fits, every shorter one of
    the same shape fits too, and there is a tallest one that does.

    `aspect` is the box's width divided by its height **in degrees**, and
    what comes back is half its height in degrees of latitude. Binary search
    to a tenth of a second of arc, over `within`, which is the real
    containment test and not an approximation of one.

    Measured at the rounded label point that reaches the page, not at the
    full-precision one, so the number the page checks against is the number
    that was measured.
    """
    low, high = 0.0, (poly.bounds[3] - poly.bounds[1]) / 2 + 1e-6
    if not poly.contains(Point(lon, lat)):
        return 0.0
    for _ in range(40):
        middle = (low + high) / 2
        trial = make_box(lon - middle * aspect, lat - middle,
                         lon + middle * aspect, lat + middle)
        if trial.within(poly):
            low = middle
        else:
            high = middle
        if high - low < 3e-5:
            break
    return low


def fit_table(poly, lon: float, lat: float) -> list[float]:
    """Half the height that fits, for each shape of box in FIT_ASPECTS.

    Clamped so the list never rises as the boxes get wider, which it cannot
    do in truth -- a wider box of the same height is a superset of a
    narrower one -- but which rounding to four places could otherwise show.
    """
    room = []
    for aspect in FIT_ASPECTS:
        # Down to four places, never up: a number rounded up is a box the
        # polygon does not actually contain, which is the one mistake this
        # whole table exists to stop. Four places is 0.36 seconds of arc,
        # about 11 metres.
        here = math.floor(room_for(poly, lon, lat, aspect) * 1e4) / 1e4
        room.append(min(here, room[-1]) if room else here)
    return room


def main_city(mine: list[dict]) -> dict | None:
    """The one city the map labels in a unit, or None if it has no town.

    The capital if Natural Earth marks one inside the unit -- the national
    capital first -- **unless** the largest town inside the unit has more
    than three times the capital's population, when it is that town instead.
    A unit with no capital inside it gets its largest town, which is the same
    rule with nothing to compare against.

    The three in the middle are what the rule is for: a capital nobody would
    look for on a map of rain. Gandhinagar is 195,891 beside Ahmedabad's
    5,375,000, Dispur is 16,140 beside Guwahati's 983,000, and New Delhi is
    317,797 beside Delhi's 15,926,000. Three times is wide enough that a
    capital which is merely smaller than a neighbour keeps the label -- Bhopal
    over Indore, Lucknow over Kanpur, Thiruvananthapuram over Kochi.

    The population is Natural Earth's own `POP_MAX`, and it is the figure for
    the built-up area rather than the town, which is why Andhra Pradesh keeps
    Amaravati: `POP_MAX` calls it 5,800,000, the capital region around
    Vijayawada and Guntur, against Vishakhapatnam's 1,529,000. The field this
    project trusts for size is the one it uses everywhere else; swapping to
    `POP_MIN` to move that one label would put Assam's largest town at
    Guwahati's `POP_MIN` of 17,516, which is worse.
    """
    caps = [town for town in mine if "capital" in town["kind"].lower()]
    if not mine:
        return None
    biggest = sorted(mine, key=lambda town: (-town["pop"], town["name"]))[0]
    if not caps:
        return biggest
    caps.sort(key=lambda town: (0 if "admin-0" in town["kind"].lower()
                                else 1, -town["pop"], town["name"]))
    capital = caps[0]
    return biggest if biggest["pop"] > 3 * capital["pop"] else capital


def build_units(found: list[dict]) -> tuple[dict, dict]:
    """The units.json body, and the tally the checks are made against."""
    rows = mask_rows()
    points = [(town, Point(town["lon"], town["lat"])) for town in found]

    units = []
    tally = {"capitals": 0, "rep_point": set(), "not_forecast": {},
             "no_city": [], "no_room": []}
    for record, poly in admin1():
        name = str(record["name"]).strip()
        code = str(record["postal"]).strip() \
            or str(record["iso_3166_2"]).strip().split("-")[-1]
        at, how = label_point(record, poly)
        if how == "representative point":
            tally["rep_point"].add(name)
        mine = [town for town, point in points if poly.contains(point)]
        city = main_city(mine)
        lat, lon = round(at.y, 3), round(at.x, 3)
        west, south, east, north = poly.bounds
        entry = {
            "name": name,
            "code": code,
            "lat": lat,
            "lon": lon,
            # SPEC 11.38. The unit's own bounding box, west, south, east,
            # north, which is what the map is fitted to when a reader
            # searches for a state. Rounded **outwards** to a hundredth of
            # a degree -- about a kilometre -- so the box always holds the
            # whole unit: rounded to nearest it could cut a district off
            # the map of the state it belongs to, and a kilometre of extra
            # sea costs nothing.
            "box": [math.floor(west * 100) / 100,
                    math.floor(south * 100) / 100,
                    math.ceil(east * 100) / 100,
                    math.ceil(north * 100) / 100],
            "fit": fit_table(poly, lon, lat),
        }
        if entry["fit"][0] <= 0:
            tally["no_room"].append(name)
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
            "inside the unit, and `fit` is how much room there is to write "
            "it there (SPEC 11.31). `code` is Natural Earth's own `postal` "
            "field, shown instead of the name wherever the name does not fit "
            "inside the unit itself. `city` is "
            "the one town the map labels in that unit -- its capital where "
            "Natural Earth marks one inside the unit, otherwise the largest "
            "town inside it by population -- and its `lat` and `lon` are the "
            "0.25 degree square the page shows, never the town's own "
            "position. `box` is the unit's own bounding box as west, south, "
            "east, north, which the search fits the map to (SPEC 11.38). "
            "Built by scripts/build_towns.py."
        ),
        "fit": {
            "aspects": list(FIT_ASPECTS),
            "note": (
                "SPEC 11.31. Each unit's `fit` is half the height, in "
                "degrees of latitude, of the tallest box centred on its "
                "label point that is still inside the unit's own polygon, "
                "for a box of each of these shapes in turn -- the shape "
                "being its width over its height in degrees. The page draws "
                "a unit's full name only where the name's own box passes "
                "this test, and its two letter code everywhere else, so a "
                "name is never written across a neighbour. Measured by "
                "binary search over shapely's `within`, to a tenth of a "
                "second of arc, at the rounded label point above."
            ),
        },
        "source": {
            "units": "ne_10m_admin_1_states_provinces",
            "units_version": ADMIN1_VERSION,
            "cities": "ne_10m_populated_places",
            "cities_version": PLACES_VERSION,
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
    units_tally_by_name = assign_units(found)
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
    print(f"  no room for a name of any shape: {units_tally['no_room']}")
    print("  room for a 6-to-1 name, degrees of latitude: "
          + ", ".join(f"{u['name']} {u['fit'][2]}" for u in units[:3]))
    without = sorted(t["name"] for t in found if not t.get("unit"))
    print(f"cities placed in a state or union territory: "
          f"{sum(units_tally_by_name.values())} of {len(found)}")
    if without:
        print(f"  no unit contains: {without}")
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
    for unit in units:
        if len(unit["fit"]) != len(FIT_ASPECTS):
            raise SystemExit(f"{unit['name']} has {len(unit['fit'])} fit "
                             f"numbers, not {len(FIT_ASPECTS)}")
        if any(b > a for a, b in zip(unit["fit"], unit["fit"][1:])):
            raise SystemExit(f"{unit['name']}'s fit table rises as the box "
                             f"widens, which cannot be: {unit['fit']}")
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
