"""Put every India square in one of IMD's four rainfall regions.

SPEC 5.4. Writes `config/regions.json`, which says, for each of the 4,613
India squares of SPEC 3.5, which of the four homogeneous rainfall regions the
India Meteorological Department would report it under.

The regions are IMD's, not ours: its 36 meteorological subdivisions grouped
under four headings in the subdivision-wise rainfall table of its Annual
Report 2025. Subdivisions are not polygons we have, so each one is translated
to the states and union territories it covers, and a square takes the region
of the state its centre falls in.

Three things this script checks rather than assumes, failing instead of
writing if any stops being true:

  * all 36 Natural Earth admin-1 units with `admin = India` appear exactly
    once across the four regions, and every name in our table is one of them;
  * the square counts match SPEC 5.4 -- 1,501, 1,510, 857 and 745 -- and so
    does the India total of 4,613;
  * the 183 squares that reach a region by rule 3, having no Indian state
    polygon over them at all, are all in the far northwest and none of them
    is a coastal square. Rule 3 is only safe while that holds, so the build
    prints their latitude and longitude range every time.

Natural Earth publishes no point-of-view edition of admin-1, which is why
rule 3 is needed: Gilgit-Baltistan, Pakistan-administered Kashmir and Aksai
Chin are inside the India outline the mask was cut with and have no Indian
state polygon over them.

The output is committed, as `config/india_mask.json` is. The shapefiles are
not -- `data/` is never committed -- so nothing downstream may rebuild this
from them.

    python scripts/build_regions.py
    python scripts/build_regions.py --check    # verify, write nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import shapefile
from shapely.geometry import Point, shape
from shapely.prepared import prep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg  # noqa: E402

NE = cfg.RAW / "ne"
ADMIN1 = NE / "ne_10m_admin_1_states_provinces"
ADMIN1_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/"
    "ne_10m_admin_1_states_provinces.zip"
)
ADMIN1_SHA256 = (
    "efc59726337323058f9446210adc96673179cd344e053666ee3d28cb58ba2b05")
ADMIN1_VERSION = "5.1.1"

MASK_FILE = cfg.ROOT / "config" / "india_mask.json"
OUT = cfg.ROOT / "config" / "regions.json"

# The order is fixed here and never sorted anywhere else: the region code
# stored in the rows below is the position in this tuple, counting from 1.
REGIONS = (
    "Northwest India",
    "Central India",
    "South Peninsula",
    "East & Northeast India",
)

SOURCE = (
    "India Meteorological Department, Annual Report 2025, Table 1, "
    "'Subdivision-wise rainfall (mm) distribution', page 96. "
    "https://metnet.imd.gov.in/docs/imdnews/ANNUAL_REPORT2025English.pdf"
)

# IMD's own groupings, spelled as that table prints them. Kept here because
# they are the provenance of the state lists below and of nothing else: no
# code reads them, and a reader checking our regions against IMD's needs the
# subdivision names, not ours.
SUBDIVISIONS = {
    "Northwest India": (
        "East U.P.", "West U.P.", "Uttarakhand", "Har., Chd & Delhi",
        "Punjab", "Himachal Pradesh", "J&K and Ladakh", "West Rajasthan",
        "East Rajasthan",
    ),
    "Central India": (
        "Odisha", "West Madhya Pradesh", "East Madhya Pradesh",
        "Gujarat region", "Saurashtra & Kutch", "Konkan & Goa",
        "Madhya Maharashtra", "Marathwada", "Vidarbha", "Chhattisgarh",
    ),
    "South Peninsula": (
        "A & N Island", "Coastal A.P. & Yanam", "Telangana", "Rayalaseema",
        "Tamil., Pudu. & Karaikal", "Coastal Karnataka", "N.I. Karnataka",
        "S.I. Karnataka", "Kerala & Mahe", "Lakshadweep",
    ),
    "East & Northeast India": (
        "Arunachal Pradesh", "Assam & Meghalaya", "NMMT", "SHWB & Sikkim",
        "Gangetic West Bengal", "Jharkhand", "Bihar",
    ),
}

# The states and union territories each region's subdivisions cover, named as
# Natural Earth names them. No subdivision boundary cuts a state between two
# regions, so no choice had to be made here (SPEC 5.4).
STATES = {
    "Northwest India": (
        "Uttar Pradesh", "Uttarakhand", "Haryana", "Chandigarh", "Delhi",
        "Punjab", "Himachal Pradesh", "Jammu and Kashmir", "Ladakh",
        "Rajasthan",
    ),
    "Central India": (
        "Odisha", "Madhya Pradesh", "Gujarat",
        "Dadra and Nagar Haveli and Daman and Diu", "Goa", "Maharashtra",
        "Chhattisgarh",
    ),
    "South Peninsula": (
        "Andaman and Nicobar", "Andhra Pradesh", "Telangana", "Tamil Nadu",
        "Puducherry", "Karnataka", "Kerala", "Lakshadweep",
    ),
    "East & Northeast India": (
        "Arunachal Pradesh", "Assam", "Meghalaya", "Nagaland", "Manipur",
        "Mizoram", "Tripura", "Sikkim", "West Bengal", "Jharkhand", "Bihar",
    ),
}

# Where rule 3 sends a square with no Indian state polygon over it.
FALLBACK = "Northwest India"

# SPEC 5.4, measured 12 November 2026. A change in any of these is a change
# in the product and has to be read, not absorbed.
EXPECT_COUNTS = {
    "Northwest India": 1501,
    "Central India": 1510,
    "South Peninsula": 857,
    "East & Northeast India": 745,
}
EXPECT_TOTAL = 4613
EXPECT_FALLBACK = 183
FALLBACK_BOX = (33.0, 37.0, 72.75, 80.25)      # lat min, lat max, lon min, max

# SPEC 5.4's region tests, on the nearest India square to each place.
PLACE_TESTS = {
    "Delhi": (28.6139, 77.2090, "Northwest India"),
    "Jaipur": (26.9124, 75.7873, "Northwest India"),
    "Srinagar": (34.0837, 74.7973, "Northwest India"),
    "Mumbai": (19.0760, 72.8777, "Central India"),
    "Bhopal": (23.2599, 77.4126, "Central India"),
    "Ahmedabad": (23.0225, 72.5714, "Central India"),
    "Chennai": (13.0827, 80.2707, "South Peninsula"),
    "Bengaluru": (12.9716, 77.5946, "South Peninsula"),
    "Thiruvananthapuram": (8.5241, 76.9366, "South Peninsula"),
    "Kolkata": (22.5726, 88.3639, "East & Northeast India"),
    "Patna": (25.5941, 85.1376, "East & Northeast India"),
    "Guwahati": (26.1445, 91.7362, "East & Northeast India"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_mask() -> dict:
    """The India mask of SPEC 3.5, as arrays."""
    record = json.loads(MASK_FILE.read_text(encoding="utf-8"))
    india = np.array([[c == "1" for c in row] for row in record["india_rows"]],
                     dtype=bool)
    coastal = np.array(
        [[c == "1" for c in row] for row in record["coastal_rows"]],
        dtype=bool)
    return {
        "india": india,
        "coastal": coastal,
        "lat": np.array(record["lat"], dtype=float),
        "lon": np.array(record["lon"], dtype=float),
        "grid": record["grid"],
        "counts": record["counts"],
    }


def load_states() -> dict:
    """Every `admin = India` polygon in admin-1, by Natural Earth's name."""
    if not ADMIN1.with_suffix(".shp").exists():
        raise SystemExit(f"missing shapefile: {ADMIN1}.shp")
    zip_path = ADMIN1.with_suffix(".zip")
    if zip_path.exists():
        got = sha256(zip_path)
        if got != ADMIN1_SHA256:
            raise SystemExit(
                f"{zip_path.name} is sha256 {got}, not {ADMIN1_SHA256}")
    reader = shapefile.Reader(str(ADMIN1))
    fields = [f[0] for f in reader.fields[1:]]
    for needed in ("admin", "name"):
        if needed not in fields:
            raise SystemExit(f"admin-1 has no {needed} field")
    a, n = fields.index("admin"), fields.index("name")
    out = {}
    for record in reader.iterShapeRecords():
        if record.record[a] != "India":
            continue
        name = record.record[n]
        if name in out:
            raise SystemExit(f"admin-1 lists {name} twice")
        out[name] = shape(record.shape.__geo_interface__)
    return out


def check_table(states: dict) -> None:
    """Our table and Natural Earth's list must be the same 36 names."""
    ours = [name for region in REGIONS for name in STATES[region]]
    if len(ours) != len(set(ours)):
        raise SystemExit("a state appears in two regions")
    missing = sorted(set(states) - set(ours))
    extra = sorted(set(ours) - set(states))
    if missing or extra:
        raise SystemExit(
            f"admin-1 and our table disagree; not in our table: {missing}; "
            f"not in admin-1: {extra}")
    if len(ours) != 36:
        raise SystemExit(f"{len(ours)} units, not 36")
    counted = sum(len(SUBDIVISIONS[region]) for region in REGIONS)
    if counted != 36:
        raise SystemExit(f"{counted} IMD subdivisions listed, not 36")


def assign(mask: dict, states: dict) -> tuple[np.ndarray, list]:
    """A region code for every India square, and the rule 3 squares.

    Code 0 is "not an India square"; 1 to 4 are the regions in the order of
    `REGIONS`. Inside-or-on-boundary counts, by the same `covers` test the
    mask itself used (SPEC 3.5).
    """
    region_of = {name: REGIONS.index(region) + 1
                 for region in REGIONS for name in STATES[region]}
    shapes = [(region_of[name], state.bounds, prep(state))
              for name, state in states.items()]
    out = np.zeros(mask["india"].shape, dtype=np.int8)
    fallback = []
    rows, cols = np.nonzero(mask["india"])
    for i, j in zip(rows.tolist(), cols.tolist()):
        lat = float(mask["lat"][i])
        lon = float(mask["lon"][j])
        point = Point(lon, lat)
        found = 0
        for code, (x0, y0, x1, y1), ready in shapes:
            if not (x0 <= lon <= x1 and y0 <= lat <= y1):
                continue
            if ready.covers(point):
                found = code
                break
        if found == 0:
            found = REGIONS.index(FALLBACK) + 1
            fallback.append({"lat": lat, "lon": lon,
                             "coastal": bool(mask["coastal"][i, j])})
        out[i, j] = found
    return out, fallback


def nearest_india(mask: dict, lat: float, lon: float) -> tuple[int, int]:
    """The India square whose centre is nearest a place."""
    rows, cols = np.nonzero(mask["india"])
    dlat = mask["lat"][rows] - lat
    dlon = (mask["lon"][cols] - lon) * np.cos(np.radians(lat))
    best = int(np.argmin(dlat * dlat + dlon * dlon))
    return int(rows[best]), int(cols[best])


def check(codes: np.ndarray, fallback: list, mask: dict) -> dict:
    """Every number SPEC 5.4 states, checked against what was just built."""
    counts = {region: int((codes == i + 1).sum())
              for i, region in enumerate(REGIONS)}
    total = int((codes > 0).sum())
    if counts != EXPECT_COUNTS:
        raise SystemExit(f"region counts are {counts}, not {EXPECT_COUNTS}")
    if total != EXPECT_TOTAL:
        raise SystemExit(f"{total} squares have a region, not {EXPECT_TOTAL}")
    if total != int(mask["india"].sum()):
        raise SystemExit("a square is in the mask with no region")

    if len(fallback) != EXPECT_FALLBACK:
        raise SystemExit(
            f"{len(fallback)} squares reach a region by rule 3, "
            f"not {EXPECT_FALLBACK}")
    lats = [square["lat"] for square in fallback]
    lons = [square["lon"] for square in fallback]
    box = (min(lats), max(lats), min(lons), max(lons))
    if box != FALLBACK_BOX:
        raise SystemExit(
            f"the rule 3 squares span {box}, not {FALLBACK_BOX}. Rule 3 is "
            "only safe while every one of them is in the far northwest")
    coastal = [square for square in fallback if square["coastal"]]
    if coastal:
        raise SystemExit(
            f"{len(coastal)} rule 3 squares are coastal, which rule 3 does "
            f"not allow: {coastal[:5]}")

    places = {}
    for place, (lat, lon, want) in PLACE_TESTS.items():
        i, j = nearest_india(mask, lat, lon)
        got = REGIONS[int(codes[i, j]) - 1]
        if got != want:
            raise SystemExit(
                f"{place}: nearest India square {mask['lat'][i]:.2f} N "
                f"{mask['lon'][j]:.2f} E is {got}, not {want}")
        places[place] = {"lat": float(mask["lat"][i]),
                         "lon": float(mask["lon"][j]), "region": want}
    return {"counts": counts, "total": total, "box": box, "places": places}


def build() -> tuple[dict, dict]:
    mask = load_mask()
    states = load_states()
    check_table(states)
    codes, fallback = assign(mask, states)
    found = check(codes, fallback, mask)
    lats = [square["lat"] for square in fallback]
    lons = [square["lon"] for square in fallback]
    record = {
        "created_at": dt.datetime.now().replace(microsecond=0).isoformat(),
        "spec_section": "5.4",
        "grid": mask["grid"],
        "source": {
            "regions": SOURCE,
            "boundaries": "Natural Earth admin-1 states and provinces",
            "layer": "ne_10m_admin_1_states_provinces",
            "version": ADMIN1_VERSION,
            "url": ADMIN1_URL,
            "sha256": ADMIN1_SHA256,
            "licence": "public domain",
            "note": ("Natural Earth publishes no point-of-view edition of "
                     "admin-1, which is why rule 3 exists."),
        },
        "rules": {
            "1": "a square takes the region of the state its centre falls in",
            "2": "inside or on the boundary counts, by the same covers test "
                 "as SPEC 3.5",
            "3": f"a square inside the India outline but in no Indian state "
                 f"polygon goes to {FALLBACK}",
        },
        "regions": list(REGIONS),
        "codes": {str(i + 1): region for i, region in enumerate(REGIONS)},
        "subdivisions": {region: list(SUBDIVISIONS[region])
                         for region in REGIONS},
        "states": {region: list(STATES[region]) for region in REGIONS},
        "counts": found["counts"],
        "total": found["total"],
        "fallback": {
            "rule": 3,
            "region": FALLBACK,
            "squares": len(fallback),
            "lat_min": min(lats), "lat_max": max(lats),
            "lon_min": min(lons), "lon_max": max(lons),
            "coastal": 0,
        },
        "place_tests": found["places"],
        "region_rows": ["".join(str(int(v)) for v in row) for row in codes],
    }
    return record, {"codes": codes, "fallback": fallback}


def report(record: dict) -> None:
    print(f"  {record['total']} India squares, all with a region")
    for region in REGIONS:
        print(f"    {region:<24} {record['counts'][region]:>5}")
    back = record["fallback"]
    print(f"  rule 3: {back['squares']} squares, "
          f"{back['lat_min']:.2f} to {back['lat_max']:.2f} N, "
          f"{back['lon_min']:.2f} to {back['lon_max']:.2f} E, "
          f"{back['coastal']} coastal")


def save(record: dict, path: Path = OUT) -> None:
    text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
    path.write_bytes(text.encode())
    back = json.loads(path.read_text(encoding="utf-8"))
    if back != record:
        raise SystemExit("regions.json changed on the way to disk")
    print(f"  wrote {path.relative_to(cfg.ROOT)}, {len(text.encode())} bytes")


def load(path: Path = OUT) -> dict:
    """Read the committed file back as arrays. Used by the pipeline."""
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    record["codes"] = np.array(
        [[int(c) for c in row] for row in record["region_rows"]],
        dtype=np.int8)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="rebuild and compare, write nothing")
    args = parser.parse_args()

    record, _ = build()
    report(record)
    if not args.check:
        save(record)
        return
    if not OUT.exists():
        raise SystemExit(f"{OUT} does not exist yet")
    have = json.loads(OUT.read_text(encoding="utf-8"))
    skip = {"created_at"}
    mine = {k: v for k, v in record.items() if k not in skip}
    theirs = {k: v for k, v in have.items() if k not in skip}
    if mine != theirs:
        changed = sorted(k for k in set(mine) | set(theirs)
                         if mine.get(k) != theirs.get(k))
        raise SystemExit(f"regions.json is out of date: {changed}")
    print("  committed regions.json matches a fresh build")


if __name__ == "__main__":
    main()
