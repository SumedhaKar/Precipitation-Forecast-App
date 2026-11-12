"""Build the two map outlines the website draws, from Natural Earth.

SPEC 11.14. Writes `web/src/geo/india.geo.json`, the national outline, and
`web/src/geo/states.geo.json`, the **internal** state boundaries only.

Both come from the files already in `data/raw/ne/`, the same ones the India
mask (SPEC 3.5) and the IMD regions (SPEC 5.4) are built from, so the drawn
map and the forecast squares cannot disagree about where India is:

  india.geo.json    ne_10m_admin_0_countries_ind, the India point-of-view
                    edition, the `India` feature. The same source as the mask.
  states.geo.json   ne_10m_admin_1_states_provinces, `admin == "India"`, and
                    **only the boundaries shared by two Indian states or
                    union territories**, clipped to the outline above.

Natural Earth publishes no point-of-view edition of admin-1 (SPEC 5.4): its
Jammu and Kashmir polygon stops at 34.77 N and Ladakh at 35.50 N, while the
point-of-view outline reaches 37.05 N. So an outer edge taken from admin-1
would be a different boundary from the one the mask was cut with.

Keeping only **shared** boundaries removes that risk by construction. A line
is written only where two Indian units meet, which no outer edge ever is, so
nothing in this file can contradict the national outline. The Jammu and
Kashmir to Ladakh boundary is a boundary between two Indian units and is
drawn; the northern edges of both are not shared with anything and are not.
Where admin-1 has no polygon at all the map shows no state line, which is the
honest result rather than a line invented to fill the space.

The script checks all of that rather than assuming it, and fails instead of
writing if any of it stops being true.

Run it when the Natural Earth files change. The output is committed; the
shapefiles are not (`data/` is never committed).

    python scripts/build_outline.py
    python scripts/build_outline.py --check    # verify, write nothing
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

import shapefile
from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import linemerge, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg  # noqa: E402

NE = cfg.RAW / "ne"
ADMIN0 = NE / "ne_10m_admin_0_countries_ind"
ADMIN1 = NE / "ne_10m_admin_1_states_provinces"
LAND = NE / "ne_10m_land"

OUT_DIR = cfg.ROOT / "web" / "src" / "geo"
OUTLINE = OUT_DIR / "india.geo.json"
STATES = OUT_DIR / "states.geo.json"
LAND_FILE = OUT_DIR / "land.geo.json"

# SPEC 11.30. The land around India, so that Nepal and Bangladesh do not read
# as ocean. Coastlines only: ne_10m_land has no borders in it at all, which
# is the point of using it. The only line between India and its neighbours
# stays the India point-of-view outline above.
LAND_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip"
LAND_SHA256 = "e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc"
LAND_VERSION = "5.1.1"

# The box the map can ever show: the India box of SPEC 1.4 grown by the same
# amounts as `LIMITS` in web/src/Map.jsx, which is what maxBounds allows
# anyone to pan to. A test keeps the two the same.
LAND_BOX = (cfg.LON_MIN - 40, cfg.LAT_MIN - 24, cfg.LON_MAX + 40,
            cfg.LAT_MAX + 14)

# Degrees. 0.05 is about 5.5 km. This is background, not data: no number on
# the page is read off it, nothing is clicked on it, and India's own coast is
# drawn from india.geo.json at five times this detail.
LAND_SIMPLIFY = 0.05

# Square degrees. About 120 km2 near this latitude. Below it an island is
# smaller than two of our forecast squares and is a speck at every zoom the
# whole country fits in; keeping all 2,328 of them would cost three times the
# file for coastline nobody can see. India's own islands are not affected:
# they are drawn from the outline, which is not filtered at all.
LAND_MIN_AREA = 0.01

# Decimal places in the written coordinates. 2 is about 1.1 km, a fifth of
# the simplification above, so it cannot move a coast anywhere the
# simplification has not already moved it.
LAND_PLACES = 2

LAND_GZIP_BUDGET = 40_000

# Degrees. 0.01 is about 1.1 km, which is finer than the 0.25 degree squares
# the map is actually about by a factor of 25, so simplifying this far cannot
# move a drawn line into a square it does not belong to.
SIMPLIFY = 0.01

# Decimal places kept in the written coordinates. 3 is about 110 m.
PLACES = 3

# The same number as a grid size, which is what the geometry is snapped to
# before anything is filtered or written.
GRID = 10 ** -PLACES

# Degrees. Two polygons that share a border do not always share it to the
# last bit: the admin-1 edges are drawn separately and can miss each other by
# a sliver. Each boundary is thickened by this much before being intersected
# with its neighbour, so a shared border is found rather than lost.
# 0.001 is about 110 m, which is the precision these files are written to.
SHARED_TOLERANCE = 0.001

# Degrees of slack allowed when checking a kept line against the outline.
INSIDE_TOLERANCE = 0.01

# The two units to check by name, because they are the reason this file only
# ever draws shared boundaries (SPEC 11.14).
MUST_SHARE = ("Jammu and Kashmir", "Ladakh")

# A size the map can afford. SPEC 11.14 holds the measured values.
GZIP_BUDGET = 60_000


def load(path: Path, field: str, want: str, name_field: str | None = None):
    """Every shape in `path` whose `field` equals `want`.

    With `name_field`, returns (name, geometry) pairs instead of geometries.
    """
    if not path.with_suffix(".shp").exists():
        raise SystemExit(f"missing shapefile: {path}.shp")
    reader = shapefile.Reader(str(path))
    fields = [f[0] for f in reader.fields[1:]]
    for needed in (field, name_field):
        if needed and needed not in fields:
            raise SystemExit(f"{path.name} has no {needed} field")
    k = fields.index(field)
    n = fields.index(name_field) if name_field else None
    out = []
    for record in reader.iterShapeRecords():
        if record.record[k] != want:
            continue
        geometry = shape(record.shape.__geo_interface__)
        out.append((record.record[n], geometry) if n is not None else geometry)
    return out


def lines_only(geometry):
    """The line parts of a geometry, dropping points where two units touch."""
    if geometry.is_empty:
        return []
    kinds = ("LineString", "MultiLineString", "LinearRing")
    if geometry.geom_type in kinds:
        return [geometry]
    if hasattr(geometry, "geoms"):
        out = []
        for part in geometry.geoms:
            out.extend(lines_only(part))
        return out
    return []


def line_parts(geometry) -> list:
    """Every individual LineString in a geometry.

    Unlike `lines_only`, this descends into a MultiLineString instead of
    returning it whole, which is what filtering one part at a time needs.
    """
    out = []
    for piece in lines_only(geometry):
        if piece.geom_type == "MultiLineString":
            out.extend(piece.geoms)
        else:
            out.append(piece)
    return out


def shared_boundaries(units: list[tuple[str, object]]) -> dict:
    """Every boundary shared by two of `units`, keyed by the pair of names.

    A pair is looked at only when their bounding boxes overlap, so this is
    36 units and a few dozen real comparisons rather than 630.
    """
    out = {}
    for a in range(len(units)):
        name_a, geom_a = units[a]
        edge_a = geom_a.boundary.buffer(SHARED_TOLERANCE)
        for b in range(a + 1, len(units)):
            name_b, geom_b = units[b]
            box_a, box_b = geom_a.bounds, geom_b.bounds
            if (box_a[0] > box_b[2] or box_b[0] > box_a[2]
                    or box_a[1] > box_b[3] or box_b[1] > box_a[3]):
                continue
            parts = lines_only(geom_b.boundary.intersection(edge_a))
            if not parts:
                continue
            shared = unary_union(parts)
            if shared.length <= 0:
                continue
            out[(name_a, name_b)] = shared
    return out


def round_coords(text: str, places: int = PLACES) -> str:
    """Shorten coordinates in a JSON string, which halves the file."""
    return re.sub(
        r"-?\d+\.\d{%d,}" % (places + 1),
        lambda m: f"{float(m.group(0)):.{places}f}",
        text,
    )


def feature(geometry, properties: dict) -> str:
    body = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": properties,
             "geometry": mapping(geometry)},
        ],
    }
    return round_coords(json.dumps(body, separators=(",", ":")))


def sizes(text: str) -> tuple[int, int]:
    raw = text.encode()
    return len(raw), len(gzip.compress(raw, 9))


def fetch_land() -> None:
    """Download ne_10m_land if it is not already here, by its hash."""
    import hashlib
    import zipfile

    import requests

    if LAND.with_suffix(".shp").exists():
        return
    NE.mkdir(parents=True, exist_ok=True)
    target = LAND.with_suffix(".zip")
    print(f"fetching {LAND_URL}")
    answer = requests.get(LAND_URL, timeout=180)
    answer.raise_for_status()
    got = hashlib.sha256(answer.content).hexdigest()
    if got != LAND_SHA256:
        raise SystemExit(
            f"ne_10m_land.zip is sha256 {got}, not {LAND_SHA256}")
    target.write_bytes(answer.content)
    with zipfile.ZipFile(target) as archive:
        archive.extractall(NE)
    print(f"  {len(answer.content)} bytes, sha256 {got}")


def land_background() -> tuple[str, dict]:
    """The land around India, clipped to the box the map can show.

    SPEC 11.30. Nothing here is a border and nothing here is data: it is one
    fill, in one colour, drawn under India's own white fill so that the
    country still ends exactly where the point-of-view outline says it does.
    What it fixes is that Nepal, Bangladesh, Myanmar and Pakistan were
    painted the same colour as the Arabian Sea, because the page drew no
    land it does not forecast.
    """
    if not LAND.with_suffix(".shp").exists():
        raise SystemExit(f"missing shapefile: {LAND}.shp")
    west, south, east, north = LAND_BOX
    window = shape({
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north],
                         [west, north], [west, south]]],
    })

    reader = shapefile.Reader(str(LAND))
    kept = []
    seen = 0
    dropped = 0
    dropped_area = 0.0
    for item in reader.iterShapes():
        geometry = shape(item.__geo_interface__)
        if not geometry.intersects(window):
            continue
        clipped = geometry.intersection(window)
        for piece in getattr(clipped, "geoms", [clipped]):
            if piece.geom_type != "Polygon" or piece.is_empty:
                continue
            seen += 1
            if piece.area < LAND_MIN_AREA:
                dropped += 1
                dropped_area += piece.area
                continue
            simple = piece.simplify(LAND_SIMPLIFY, preserve_topology=True)
            if not simple.is_empty:
                kept.append(simple)

    body = {
        "type": "FeatureCollection",
        # The box is written down so a test can hold it against the map's own
        # maxBounds: land that stops inside the area a reader can pan to
        # would be a coastline that is not there.
        "properties": {
            "note": "SPEC 11.30. Natural Earth 1:10m land, public domain, "
                    "coastlines only and no boundary of any kind, clipped to "
                    "the box the map can show, simplified to "
                    f"{LAND_SIMPLIFY} degrees. Background: nothing is read "
                    "off it. Built by scripts/build_outline.py.",
            "source": "ne_10m_land",
            "version": LAND_VERSION,
            "box": list(LAND_BOX),
            "simplify_degrees": LAND_SIMPLIFY,
            "min_area_square_degrees": LAND_MIN_AREA,
        },
        "features": [
            {"type": "Feature", "properties": {}, "geometry": mapping(part)}
            for part in kept
        ],
    }
    text = round_coords(json.dumps(body, separators=(",", ":")),
                        places=LAND_PLACES)
    raw, gz = sizes(text)
    facts = {
        "land_parts": len(kept),
        "land_seen": seen,
        "land_dropped": dropped,
        "land_dropped_area": dropped_area,
        "land_points": sum(len(part.exterior.coords) for part in kept),
        "land_bytes": (raw, gz),
    }
    return text, facts


def build() -> tuple[str, str, dict]:
    """Return the two files' contents and everything worth printing."""
    india = unary_union(load(ADMIN0, "NAME", "India"))
    units = load(ADMIN1, "admin", "India", name_field="name")

    outline = india.simplify(SIMPLIFY, preserve_topology=True)

    # Only boundaries shared by two Indian units, so no outer edge from
    # admin-1 can disagree with the point-of-view outline (SPEC 11.14).
    pairs = shared_boundaries(units)
    every_line = unary_union([geometry.boundary for _, geometry in units])
    shared = unary_union(list(pairs.values()))

    # Clip to the outline. A shared border is interior by definition, so this
    # only trims slivers where the two editions draw a coast differently.
    inside = linemerge(shared.intersection(india))
    state_lines = inside.simplify(SIMPLIFY, preserve_topology=False)

    # Snap both to the grid the file is written on, and drop whatever does
    # not survive it.
    #
    # Noding two boundaries against each other leaves places where the shared
    # line is a few centimetres long: real, where two units very nearly touch
    # at a point, but nothing to draw. Written at three decimal places both
    # of its ends round to the same coordinate, and the file ends up with a
    # zero-length closed ring in it, which is nonsense for a reader and was
    # found on 12 November 2026 at 93.018 E 24.399 N.
    #
    # Rounding in the text and filtering in the geometry cannot agree about
    # cases like that, so the geometry is snapped to the grid first and the
    # filtering happens after: what is written is exactly what was checked.
    outline = set_precision(outline, GRID)
    was = line_parts(state_lines)
    kept = [part for part in (set_precision(p, GRID) for p in was)
            if not part.is_empty and part.length > 0]
    dropped = len(was) - len(kept)
    state_lines = unary_union(kept)

    note = ("Natural Earth 1:10m, version 5.1.1, public domain. "
            "Built by scripts/build_outline.py, SPEC 11.14.")
    outline_json = feature(outline, {
        "name": "India",
        "source": "ne_10m_admin_0_countries_ind, India point-of-view edition",
        "note": note,
    })
    states_json = feature(state_lines, {
        "name": "boundaries between Indian states and union territories",
        "source": "ne_10m_admin_1_states_provinces, admin = India",
        "note": note + " Only boundaries shared by two Indian units, clipped "
                       "to the national outline: no outer edge, and no "
                       "boundary claim of any kind.",
    })

    def parts(geometry) -> int:
        return len(geometry.geoms) if hasattr(geometry, "geoms") else 1

    def points(geometry) -> int:
        return sum(len(ring) for ring in _rings(geometry))

    # The checks that make "no claim" more than a sentence in a docstring.
    names = [name for name, _ in units]
    checks = {
        "units": len(units),
        "sharing_pairs": len(pairs),
        "must_share_present": [n for n in MUST_SHARE if n in names],
        "must_share_length": pairs.get(MUST_SHARE, pairs.get(
            tuple(reversed(MUST_SHARE)))),
        "admin1_north": max(geometry.bounds[3] for _, geometry in units),
        "outline_north": india.bounds[3],
        "state_north": state_lines.bounds[3],
        "outside_outline": state_lines.difference(
            india.buffer(INSIDE_TOLERANCE)).length,
    }
    checks["must_share_length"] = (
        checks["must_share_length"].length
        if checks["must_share_length"] is not None else 0.0)

    facts = {
        "outline_parts": parts(outline),
        "outline_points": points(outline),
        "outline_bytes": sizes(outline_json),
        "outline_bbox": [round(v, 4) for v in outline.bounds],
        "source_bbox": [round(v, 4) for v in india.bounds],
        "outline_area_kept": 100.0 * outline.area / india.area,
        "state_parts": parts(state_lines),
        "state_points": points(state_lines),
        "state_bytes": sizes(states_json),
        "state_degrees": state_lines.length,
        "every_line_degrees": every_line.length,
        "shared_degrees": shared.length,
        "dropped_points": dropped,
        **checks,
    }
    return outline_json, states_json, facts


def _rings(geometry):
    """Every coordinate ring or line in a geometry, for counting points."""
    kind = geometry.geom_type
    if kind in ("LineString", "LinearRing"):
        yield geometry.coords
    elif kind == "Polygon":
        yield geometry.exterior.coords
        for hole in geometry.interiors:
            yield hole.coords
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from _rings(part)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify and print, write nothing")
    args = ap.parse_args()

    outline_json, states_json, f = build()
    fetch_land()
    land_json, land_facts = land_background()
    f.update(land_facts)
    o_raw, o_gz = f["outline_bytes"]
    s_raw, s_gz = f["state_bytes"]
    l_raw, l_gz = f["land_bytes"]

    print(f"outline: {f['outline_points']} points in {f['outline_parts']} "
          f"parts, {o_raw} bytes, {o_gz} gzipped")
    print(f"         bbox {f['outline_bbox']}, source {f['source_bbox']}, "
          f"{f['outline_area_kept']:.4f}% of the area")
    print(f"states:  {f['state_points']} points in {f['state_parts']} parts, "
          f"{s_raw} bytes, {s_gz} gzipped")
    print(f"         {f['state_degrees']:.1f} degrees kept, "
          f"{f['dropped_points']} parts too short to write dropped, from "
          f"{f['shared_degrees']:.1f} shared between "
          f"{f['sharing_pairs']} pairs of the {f['units']} units, out of "
          f"{f['every_line_degrees']:.1f} degrees of unit outline")
    print(f"total:   {o_gz + s_gz} bytes gzipped, budget {GZIP_BUDGET}")
    print(f"land:    {f['land_parts']} parts of {f['land_seen']} in the box, "
          f"{f['land_points']} points, {l_raw} bytes, {l_gz} gzipped, "
          f"budget {LAND_GZIP_BUDGET}")
    print(f"         {f['land_dropped']} parts under {LAND_MIN_AREA} "
          f"square degrees dropped, {f['land_dropped_area']:.3f} square "
          f"degrees of island in all")
    print(f"north:   outline {f['outline_north']:.4f}, state lines "
          f"{f['state_north']:.4f}, admin-1 coverage ends "
          f"{f['admin1_north']:.4f}")
    print(f"checked: {' and '.join(f['must_share_present'])} share "
          f"{f['must_share_length']:.3f} degrees of boundary; "
          f"{f['outside_outline']:.6f} degrees of state line fall outside "
          f"the outline")

    # The outline is snapped to the GRID the file is written on, so its box
    # cannot equal the source's to the last decimal. It must equal it to
    # within one grid step, which is 110 m: anything more means simplifying
    # has cut a corner off the country rather than smoothed it.
    moved = [abs(a - b) for a, b in zip(f["outline_bbox"], f["source_bbox"])]
    if max(moved) > GRID:
        raise SystemExit(
            f"the outline's bounding box moved by {max(moved):.5f} degrees, "
            f"more than the {GRID} grid it is written on")
    if o_gz + s_gz > GZIP_BUDGET:
        raise SystemExit(f"{o_gz + s_gz} gzipped bytes is over the budget")
    if l_gz > LAND_GZIP_BUDGET:
        raise SystemExit(f"{l_gz} gzipped bytes of land is over the budget")
    if f["land_parts"] < 100:
        raise SystemExit(f"only {f['land_parts']} land parts: the clip box "
                         "or the source has changed")

    # SPEC 11.14: nothing in states.geo.json may contradict the outline.
    if list(f["must_share_present"]) != list(MUST_SHARE):
        raise SystemExit(
            f"admin-1 no longer has {MUST_SHARE}: it has "
            f"{f['must_share_present']}, so the shared-boundary check that "
            "this file depends on cannot be made")
    if f["must_share_length"] <= 0:
        raise SystemExit(
            f"{MUST_SHARE[0]} and {MUST_SHARE[1]} share no boundary, which "
            "means the pairing is not finding real borders")
    if f["outside_outline"] > 0:
        raise SystemExit(
            f"{f['outside_outline']:.6f} degrees of state line lie outside "
            "the national outline, which is exactly what this file must "
            "never do")
    if f["state_north"] > f["admin1_north"] + 1e-9:
        raise SystemExit("a state line runs north of the admin-1 data")

    three = ((OUTLINE, outline_json), (STATES, states_json),
             (LAND_FILE, land_json))
    if args.check:
        for path, text in three:
            if not path.exists():
                raise SystemExit(f"{path} does not exist")
            if path.read_text(encoding="utf-8") != text:
                raise SystemExit(f"{path} is not what this script builds")
        print("check: all three files match what this script builds")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in three:
        # write_bytes, not write_text: on Windows write_text turns every
        # newline into CRLF, and this repository stores LF.
        path.write_bytes(text.encode("utf-8"))
    print("wrote " + ", ".join(str(path.relative_to(cfg.ROOT))
                               for path, _ in three))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
