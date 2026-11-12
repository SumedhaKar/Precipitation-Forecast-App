"""HC8: for one square, five independent things must give the same answer.

SPEC 11.25. HC7 compared two copies of the same run. This compares what the
store serves, what the API says, what the page prints and what the map
actually painted -- the last of those read back as a pixel out of the WebGL
canvas, which is the only check in this project that looks at the thing a
reader looks at.

Five things per square:

  1. the store byte   i = (38.0 - lat) / 0.25, j = (lon - 68.0) / 0.25,
                      byte = i * 121 + j, out of
                      runs/<run>/counts/ge<T>mm_day<d>.u8
  2. the tile         c[day - 1][k] out of runs/<run>/tiles/<tile>.json,
                      tile = floor(lat / 4) * 4, floor(lon / 4) * 4
  3. /api/place       counts for that day and threshold, from the live site
  4. the panel        the number the page printed for that square
  5. the pixel        the colour the map painted at that square's centre,
                      and the class the panel named

It passes when 1, 2, 3 and 4 are the same integer, the pixel is exactly the
palette hex of SPEC 11.17 for the class that contains that integer, and the
class the panel named is that class.

No project imports. Every read is an anonymous HTTPS GET of a public URL:
no Authorization header, no credential, and BLOB_READ_WRITE_TOKEN is never
read. The index arithmetic and the palette table are written out here
longhand so they can be followed with a pencil, exactly as HC7 does it.

4 and 5 cannot be fetched: they have to be taken out of a browser looking at
the live site. The browser step writes them to a JSON file and this script
is given it with --page. The file also carries what the page says about
itself, and this script refuses to believe a single sampled colour unless
all of it holds:

  * preserveDrawingBuffer is on, or the pixel read back is not the pixel
    drawn. The page turns it on only for ?handcheck=1 (SPEC 11.25), and the
    first version of this check read back nothing but transparent black
    because MapLibre 6 takes that flag inside `canvasContextAttributes` and
    ignores a top level one in silence;
  * the basemap slot of SPEC 11.14 is empty and the slot paints at zero, so
    nothing is drawn under the squares;
  * the squares are drawn at fill-opacity 1, so the pixel is the palette
    colour and not a blend of it;
  * nothing was chosen when the pixel was sampled, and the zoom was below
    the zoom the grid appears at, so no layer of NOT_DATA_LAYERS -- the
    grid, the chosen square's outline, its ring -- could put a pixel on the
    square being sampled.

Usage:

    python handchecks/hc8_map_square.py --squares
    python handchecks/hc8_map_square.py --page <page.json>

The first prints the five squares and what the store, the tiles and the API
say about them, which is what the browser step is then asked to look at. The
second does the whole check and writes handchecks/results/hc8_map.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "results" / "hc8_map.csv"
SITE = "https://precipitation-forecast-app.vercel.app"
STORE = "https://zshhfucqsimhyy61.public.blob.vercel-storage.com"
TOKEN_NAME = "BLOB_READ_WRITE_TOKEN"

# The grid, written out rather than imported.
LAT_MAX = 38.0
LON_MIN = 68.0
STEP = 0.25
N_LON = 121
TILE_DEGREES = 4.0
NOT_INDIA = 255
THRESHOLDS = (1, 10, 50)

# SPEC 11.17, copied out by hand. If this ever disagrees with
# web/src/palette.js, one of the two is wrong and HC8 is the one that says
# so: it is a second opinion, not a second import.
CLASSES = [
    (0, 0, "0", "#eceff1"),
    (1, 10, "1-10", "#c7e9b4"),
    (11, 20, "11-20", "#7fcdbb"),
    (21, 30, "21-30", "#41b6c4"),
    (31, 40, "31-40", "#1d91c0"),
    (41, 50, "41-50", "#225ea8"),
    (51, 51, "51", "#0c2c84"),
]

# The five squares. One is the requirement of SPEC 11.25 -- the square HC6
# and HC7 used -- and the other four were chosen from this run's own counts
# so that the ends of the palette table and three of its middle classes are
# all exercised. They were also chosen to be squares whose centre is well
# clear of a drawn line: the state lines and the coast are painted over the
# squares, so a square centre that sits on one has a boundary's colour on it
# and not its own. `clear_degrees` is how far the centre is from the nearest
# line the map draws, measured against the very files the map draws them
# from. That is a fact about where the lines are, not about what the counts
# say, so choosing on it cannot flatter the answer.
SQUARES = [
    {"lat": 34.25, "lon": 73.5, "threshold": 1, "day": 1,
     "why": "the HC6 and HC7 square, required by SPEC 11.25",
     "clear_degrees": 0.022},
    {"lat": 27.0, "lon": 74.0, "threshold": 1, "day": 1,
     "why": "a square no model run reaches 1 mm in, deep inside Rajasthan",
     "clear_degrees": 2.142},
    {"lat": 20.5, "lon": 84.25, "threshold": 1, "day": 1,
     "why": "a middle class, 1-10, inland in Odisha",
     "clear_degrees": 1.209},
    {"lat": 35.0, "lon": 79.0, "threshold": 1, "day": 1,
     "why": "a middle class, 11-20, inland in Ladakh",
     "clear_degrees": 0.778},
    {"lat": 34.0, "lon": 77.25, "threshold": 1, "day": 1,
     "why": "a middle class, 31-40, inland in Ladakh",
     "clear_degrees": 0.885},
]


def get(url: str) -> bytes:
    """A plain public GET. No headers, no credential, nothing cached."""
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise SystemExit(f"{url} answered {response.status}")
        return response.read()


def row_of(lat: float) -> int:
    return int(round((LAT_MAX - lat) / STEP))


def col_of(lon: float) -> int:
    return int(round((lon - LON_MIN) / STEP))


def tile_name(lat: float, lon: float) -> str:
    lat_s = math.floor(lat / TILE_DEGREES) * TILE_DEGREES
    lon_w = math.floor(lon / TILE_DEGREES) * TILE_DEGREES
    ns = "N" if lat_s >= 0 else "S"
    ew = "E" if lon_w >= 0 else "W"
    return f"{abs(int(lat_s))}{ns}_{abs(int(lon_w))}{ew}"


def class_of(count: int) -> tuple[str, str]:
    """The class name and hex for a count, out of the table above."""
    for low, high, label, colour in CLASSES:
        if low <= count <= high:
            return label, colour
    raise SystemExit(f"{count} is not a count out of 51")


def store_byte(run: str, square: dict) -> int:
    i = row_of(square["lat"])
    j = col_of(square["lon"])
    byte = i * N_LON + j
    name = f"ge{square['threshold']}mm_day{square['day']}.u8"
    raw = get(f"{STORE}/runs/{run}/counts/{name}")
    if len(raw) != 129 * N_LON:
        raise SystemExit(f"{name} is {len(raw)} bytes, not {129 * N_LON}")
    return raw[byte]


def tile_count(run: str, square: dict) -> int:
    name = tile_name(square["lat"], square["lon"])
    body = json.loads(get(f"{STORE}/runs/{run}/tiles/{name}.json"))
    k = THRESHOLDS.index(square["threshold"])
    for one in body["squares"]:
        if (abs(one["lat"] - square["lat"]) < 1e-9
                and abs(one["lon"] - square["lon"]) < 1e-9):
            return one["c"][square["day"] - 1][k]
    raise SystemExit(f"{square['lat']} {square['lon']} is not in tile {name}")


def api_count(site: str, square: dict) -> int:
    url = f"{site}/api/place?lat={square['lat']}&lon={square['lon']}"
    body = json.loads(get(url))
    asked = body["square"]
    if (abs(asked["lat"] - square["lat"]) > 1e-9
            or abs(asked["lon"] - square["lon"]) > 1e-9):
        raise SystemExit(f"api/place answered for {asked}, not {square}")
    day = body["days"][square["day"] - 1]
    return day["counts"][f"ge{square['threshold']}"]


def check_facts(facts: dict) -> list[str]:
    """What has to hold before a sampled pixel means anything."""
    wrong = []
    if not facts.get("preserveDrawingBuffer"):
        wrong.append("preserveDrawingBuffer was off, so the pixel read back "
                     "is not the pixel drawn")
    if facts.get("basemapSlot"):
        wrong.append(f"the basemap slot holds {facts['basemapSlot']}")
    if facts.get("slotOpacity") != 0:
        wrong.append(f"the basemap slot paints at {facts.get('slotOpacity')}")
    if facts.get("squareOpacity") != 1:
        wrong.append(f"the squares are drawn at {facts.get('squareOpacity')}, "
                     "so a pixel is a blend and not a palette colour")
    if facts.get("picked"):
        wrong.append(f"{facts['picked']} chosen-square features were in view "
                     "when the pixel was sampled")
    if not facts.get("zoom", 99) < facts.get("gridFromZoom", 0):
        wrong.append(f"sampled at zoom {facts.get('zoom')}, which is not "
                     f"below the {facts.get('gridFromZoom')} the grid "
                     "appears at")
    return wrong


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", help="what the browser read, as JSON")
    parser.add_argument("--squares", action="store_true",
                        help="print the five squares and the three numbers "
                             "that can be fetched, and write nothing")
    parser.add_argument("--site", default=SITE)
    args = parser.parse_args()

    if os.environ.get(TOKEN_NAME):
        print(f"note: {TOKEN_NAME} is set in this shell. It is not read "
              "here, and nothing below uses it.")

    manifest = json.loads(get(f"{STORE}/manifest.json?cb=hc8"))
    run = manifest["run_id"]
    print(f"run {run}, published {manifest['publish_time_ist']} IST")
    print(f"site {args.site}")
    print()

    fetched = []
    for square in SQUARES:
        i, j = row_of(square["lat"]), col_of(square["lon"])
        one = dict(square)
        one.update({
            "run": run, "i": i, "j": j, "byte": i * N_LON + j,
            "tile": tile_name(square["lat"], square["lon"]),
            "store": store_byte(run, square),
            "tile_count": tile_count(run, square),
            "api": api_count(args.site, square),
        })
        one["class"], one["hex"] = class_of(one["store"])
        fetched.append(one)
        print(f"{one['lat']:>6} N {one['lon']:>6} E  "
              f"{one['threshold']:>2} mm day {one['day']}  "
              f"i {i:>3} j {j:>3} byte {one['byte']:>5} tile {one['tile']:<8} "
              f"store {one['store']:>3} tile {one['tile_count']:>3} "
              f"api {one['api']:>3}  {one['class']:>5} {one['hex']}")

    if args.squares:
        print("\nAsk the page, at ?handcheck=1, for each square: the panel's "
              "count, the class the panel names, and the pixel at the "
              "square's centre.")
        return

    if not args.page:
        raise SystemExit("--page is needed: 4 and 5 come out of a browser")

    page = json.loads(Path(args.page).read_text("utf-8"))
    facts = page["facts"]
    broken = check_facts(facts)
    for line in broken:
        print(f"REFUSED: {line}")
    seen = {(round(one["lat"], 4), round(one["lon"], 4),
             one["threshold"], one["day"]): one for one in page["squares"]}

    rows = []
    bad = 0
    print()
    for one in fetched:
        key = (round(one["lat"], 4), round(one["lon"], 4),
               one["threshold"], one["day"])
        drawn = seen.get(key)
        if drawn is None:
            raise SystemExit(f"the page was not asked about {key}")
        same = (one["store"] == one["tile_count"] == one["api"]
                == drawn["panel"])
        right_colour = drawn["pixel"].lower() == one["hex"]
        right_class = drawn["class"].strip() == one["class"]
        verdict = ("pass" if same and right_colour and right_class
                   and not broken else "FAIL")
        if verdict == "FAIL":
            bad += 1
        rows.append({
            "run": one["run"], "lat": one["lat"], "lon": one["lon"],
            "threshold_mm": one["threshold"], "lead_day": one["day"],
            "i": one["i"], "j": one["j"], "byte": one["byte"],
            "tile": one["tile"],
            "store_byte": one["store"], "tile_count": one["tile_count"],
            "api_place": one["api"], "panel": drawn["panel"],
            "pixel": drawn["pixel"], "palette_hex": one["hex"],
            "panel_class": drawn["class"], "class": one["class"],
            "sampled_at_x": drawn["x"], "sampled_at_y": drawn["y"],
            "sample_zoom": round(facts["zoom"], 4),
            "grid_from_zoom": round(facts["gridFromZoom"], 4),
            "basemap_slot": "empty" if not facts["basemapSlot"]
                            else ",".join(facts["basemapSlot"]),
            "square_opacity": facts["squareOpacity"],
            "chosen_features_in_view": facts["picked"],
            "preserve_drawing_buffer": facts["preserveDrawingBuffer"],
            "clear_of_lines_degrees": one["clear_degrees"],
            "why_this_square": one["why"],
            "site": args.site,
            "checked_at_ist": page["checked_at_ist"],
            "verdict": verdict,
        })
        print(f"{verdict:>4}  {one['lat']} N {one['lon']} E  "
              f"store {one['store']} tile {one['tile_count']} "
              f"api {one['api']} panel {drawn['panel']}  "
              f"pixel {drawn['pixel']} palette {one['hex']}  "
              f"panel class {drawn['class']!r} table {one['class']!r}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {OUT}")

    if broken or bad:
        raise SystemExit(f"HC8 failed: {bad} of {len(rows)} squares, "
                         f"{len(broken)} conditions refused")
    print("HC8: five squares, five things each, all agreeing.")


if __name__ == "__main__":
    main()
