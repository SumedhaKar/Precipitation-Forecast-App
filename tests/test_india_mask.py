"""Tests for the India mask (SPEC 3.5).

The point tests are the real check on the outline: Gilgit and Aksai Chin must
be India, which is only true of the India point-of-view edition of Natural
Earth, and Lahore must not be, which is only a quarter of a degree from
Gilgit's longitude.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                       # noqa: E402
from pipeline.india_mask import (                        # noqa: E402
    LSM_THRESHOLD,
    MASK_FILE,
    coastal_from,
    index_of,
    load,
)

MUST_BE_INDIA = [
    ("Delhi", 28.5, 77.25),
    ("Srinagar", 34.0, 74.75),
    ("Gilgit", 36.0, 74.25),
    ("Aksai Chin", 35.0, 79.0),
]

MUST_NOT_BE_INDIA = [
    ("Colombo", 7.0, 80.0),
    ("Kathmandu", 27.75, 85.25),
    ("Dhaka", 23.75, 90.5),
    ("Lahore", 31.5, 74.25),
]


@pytest.fixture(scope="module")
def mask():
    if not MASK_FILE.exists():
        pytest.skip("config/india_mask.json has not been built yet")
    return load()


@pytest.mark.parametrize("name, lat, lon", MUST_BE_INDIA)
def test_these_places_are_india(mask, name, lat, lon):
    i, j = index_of(lat, lon)
    assert mask["india"][i, j], f"{name} at {lat},{lon} should be India"


@pytest.mark.parametrize("name, lat, lon", MUST_NOT_BE_INDIA)
def test_these_places_are_not_india(mask, name, lat, lon):
    i, j = index_of(lat, lon)
    assert not mask["india"][i, j], f"{name} at {lat},{lon} should not be India"


def test_gilgit_and_lahore_are_distinguished(mask):
    """Both near longitude 74.25; only the POV edition separates them."""
    gilgit = index_of(36.0, 74.25)
    lahore = index_of(31.5, 74.25)
    assert mask["india"][gilgit] and not mask["india"][lahore]


def test_index_of_round_trips():
    for i, lat in enumerate(cfg.INDIA_LATS):
        for j, lon in [(0, cfg.INDIA_LONS[0]), (cfg.N_LON - 1, cfg.INDIA_LONS[-1])]:
            assert index_of(lat, lon) == (i, j)


def test_index_of_rejects_points_outside_the_box():
    from pipeline.india_mask import MaskError
    with pytest.raises(MaskError):
        index_of(45.0, 77.0)
    with pytest.raises(MaskError):
        index_of(20.0, 110.0)


# --------------------------------------------------------------- shape

def test_mask_has_the_right_shape(mask):
    assert mask["india"].shape == (cfg.N_LAT, cfg.N_LON)
    assert mask["coastal"].shape == (cfg.N_LAT, cfg.N_LON)


def test_counts_in_the_file_match_the_arrays(mask):
    assert mask["counts"]["india"] == int(mask["india"].sum())
    assert mask["counts"]["coastal"] == int(mask["coastal"].sum())
    assert mask["counts"]["inland"] == int(
        mask["india"].sum() - mask["coastal"].sum())


def test_coastal_is_a_subset_of_india(mask):
    assert not (mask["coastal"] & ~mask["india"]).any()


def test_outline_metadata_is_recorded(mask):
    assert mask["outline"]["version"] == "5.1.1"
    assert mask["outline"]["layer"] == "ne_10m_admin_0_countries_ind"
    assert len(mask["outline"]["sha256"]) == 64
    assert len(mask["land_sea_mask"]["sha256"]) == 64
    assert mask["land_sea_mask"]["threshold"] == LSM_THRESHOLD


# ------------------------------------------------------ coastal rule

def test_coastal_rule_flags_a_square_next_to_sea():
    """One land square with sea to its east is coastal."""
    india = np.zeros((3, 3), dtype=bool)
    india[1, 1] = True

    lsm = np.ones((5, 5), dtype=np.float32)  # padded 3x3 -> 5x5
    lsm[2, 3] = 0.2                          # the neighbour east of centre

    out = _coastal_on_small_grid(india, lsm)
    assert out[1, 1]


def test_coastal_rule_leaves_an_inland_square_alone():
    india = np.zeros((3, 3), dtype=bool)
    india[1, 1] = True
    lsm = np.ones((5, 5), dtype=np.float32)  # every neighbour is land

    out = _coastal_on_small_grid(india, lsm)
    assert not out[1, 1]


def test_coastal_rule_uses_all_eight_neighbours():
    """A diagonal neighbour counts too."""
    india = np.zeros((3, 3), dtype=bool)
    india[1, 1] = True
    lsm = np.ones((5, 5), dtype=np.float32)
    lsm[1, 1] = 0.0  # the diagonal, up and to the left

    out = _coastal_on_small_grid(india, lsm)
    assert out[1, 1]


def test_coastal_rule_ignores_a_non_india_square(mask):
    """Sea next to a square that is not India does not make it coastal."""
    india = np.zeros((3, 3), dtype=bool)   # nothing is India
    lsm = np.zeros((5, 5), dtype=np.float32)

    out = _coastal_on_small_grid(india, lsm)
    assert not out.any()


def _coastal_on_small_grid(india, lsm_padded):
    """Run coastal_from against a small grid by borrowing the real sizes."""
    original = (cfg.N_LAT, cfg.N_LON)
    cfg.N_LAT, cfg.N_LON = india.shape
    try:
        return coastal_from(india, lsm_padded)
    finally:
        cfg.N_LAT, cfg.N_LON = original


# ---------------------------------------------------------------------------
# SPEC 11.14: the two outlines the map draws
#
# The point of this block is that **the country on screen and the squares we
# forecast are the same shape**. The mask above was cut with the Natural Earth
# India point-of-view outline; `web/src/geo/` holds that same outline for
# drawing, plus the boundaries between Indian states. If those ever came from
# different geometry the map would colour squares outside the country it
# draws, and nobody would notice from the code alone.
#
# The committed JSON is always checked. The checks that need the shapefiles
# skip when `data/raw/ne/` is absent, because `data/` is never committed.
# ---------------------------------------------------------------------------

import json          # noqa: E402
import subprocess    # noqa: E402

shapely = pytest.importorskip("shapely", reason="shapely is not installed")
from shapely.geometry import Point, shape   # noqa: E402
from shapely.prepared import prep           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "web" / "src" / "geo"
OUTLINE_FILE = GEO / "india.geo.json"
STATES_FILE = GEO / "states.geo.json"
BUILDER = ROOT / "scripts" / "build_outline.py"

# SPEC 3.5, measured from the shapefile on 12 November 2026.
SOURCE_BBOX = (68.1434, 6.7456, 97.3623, 37.0545)

# The two numbers scripts/build_outline.py writes with: the grid coordinates
# are snapped to, and how far the geometry was simplified. Repeated here so
# the committed-JSON checks do not need the builder or the shapefiles.
GRID = 0.001
SIMPLIFY = 0.01

needs_shapefiles = pytest.mark.skipif(
    not (cfg.RAW / "ne" / "ne_10m_admin_0_countries_ind.shp").exists(),
    reason="data/raw/ne is not committed, so the source cannot be compared")


def line_parts(geometry) -> list:
    """Every individual LineString, the same descent the builder does."""
    return list(getattr(geometry, "geoms", [geometry]))


def geometry_of(path: Path):
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1, "one feature a file, so one geometry"
    return shape(body["features"][0]["geometry"]), body["features"][0]


@pytest.fixture(scope="module")
def outline():
    return geometry_of(OUTLINE_FILE)[0]


@pytest.fixture(scope="module")
def state_lines():
    return geometry_of(STATES_FILE)[0]


# -------------------------------------------------- the committed JSON alone

def test_both_outline_files_hold_one_geometry_each():
    india, feature = geometry_of(OUTLINE_FILE)
    lines, lines_feature = geometry_of(STATES_FILE)
    assert india.geom_type in ("Polygon", "MultiPolygon")
    assert lines.geom_type in ("LineString", "MultiLineString")
    assert india.is_valid
    for properties in (feature["properties"], lines_feature["properties"]):
        assert "Natural Earth" in properties["note"]
        assert "public domain" in properties["note"]
    # The outline must say which edition it is: the whole argument of 11.14
    # rests on it being the point-of-view one the mask was cut with.
    assert "point-of-view" in feature["properties"]["source"]
    assert "admin_0_countries_ind" in feature["properties"]["source"]


def test_the_drawn_outline_keeps_the_shapefiles_bounding_box(outline):
    """To within the 0.001 degree grid the file is written on."""
    for got, expected in zip(outline.bounds, SOURCE_BBOX):
        assert got == pytest.approx(expected, abs=GRID), outline.bounds


def test_every_india_square_centre_is_inside_the_drawn_outline(mask, outline):
    """4,613 squares, every one inside the country the map draws.

    "Inside" here allows the simplification tolerance, and it has to. The
    mask was cut with the full-resolution outline; the drawn one is
    simplified at 0.01 degrees, so a square centre within about a kilometre
    of the coast or the border can land a few metres on the wrong side of the
    drawn line. Measured on 12 November 2026: **two of the 4,613** do, at
    35.25 N 80.25 E and 22.25 N 72.5 E, by 0.12 km and 0.03 km. Both are
    inside the source geometry, which the shapefile test below checks.

    The number that matters is the distance, not the count: a square that
    missed because the outline came from the wrong edition would be tens of
    kilometres out, not tens of metres.
    """
    india = mask["india"]
    assert india.sum() == 4613, "the mask of SPEC 3.5"

    inside = prep(outline)
    worst = 0.0
    strays = []
    for i in range(india.shape[0]):
        for j in range(india.shape[1]):
            if not india[i, j]:
                continue
            point = Point(cfg.INDIA_LONS[j], cfg.INDIA_LATS[i])
            if inside.intersects(point):
                continue
            away = point.distance(outline)
            worst = max(worst, away)
            strays.append((cfg.INDIA_LATS[i], cfg.INDIA_LONS[j], away))

    assert worst <= SIMPLIFY, (
        f"a square centre is {worst:.5f} degrees outside the drawn outline, "
        f"more than the {SIMPLIFY} it was simplified by: {strays[:5]}")
    assert len(strays) < 10, f"{len(strays)} square centres sit outside"


def test_no_state_line_lies_outside_the_outline(outline, state_lines):
    """SPEC 11.14: states.geo.json may not contradict the national outline."""
    stray = state_lines.difference(outline.buffer(SIMPLIFY))
    assert stray.length == pytest.approx(0.0, abs=1e-9), (
        f"{stray.length} degrees of state line fall outside India")


def test_the_state_lines_stop_where_the_admin_one_data_stops(state_lines,
                                                             outline):
    """The northern gap of SPEC 11.14, asserted rather than described.

    Natural Earth's admin-1 Jammu and Kashmir ends at 34.77 N and Ladakh at
    35.50 N, while the point-of-view outline reaches 37.05 N. So the north of
    the country is drawn with no internal subdivision, which is the honest
    result of drawing only boundaries two Indian units share.
    """
    assert state_lines.bounds[3] < 35.5, state_lines.bounds
    assert outline.bounds[3] == pytest.approx(37.0545, abs=GRID)
    assert outline.bounds[3] - state_lines.bounds[3] > 1.0


def test_no_state_line_is_long_enough_to_be_a_national_edge(outline,
                                                            state_lines):
    """The file must not contain an outer edge, closed or otherwise.

    A closed ring is allowed, and there is one: Puducherry's Yanam is an
    enclave inside Andhra Pradesh, so the boundary it shares with Andhra
    Pradesh is its whole perimeter, 0.33 degrees at 82.18 to 82.30 E. That is
    a real boundary between two Indian units and it is drawn.

    What must not appear is anything the size of a coast. The national
    outline's perimeter is about 210 degrees and the longest state line is
    about 16.
    """
    parts = line_parts(state_lines)
    assert len(parts) > 20, "India has many state boundaries"
    perimeter = outline.boundary.length
    longest = max(part.length for part in parts)
    assert longest < 0.1 * perimeter, (
        f"a state line is {longest:.1f} degrees long against a "
        f"{perimeter:.1f} degree national outline")

    closed = [part for part in parts if part.is_closed]
    assert len(closed) <= 3, f"{len(closed)} closed rings is too many"
    for ring in closed:
        assert ring.length > 0, "a zero-length ring is nothing to draw"
        assert ring.length < 2.0, f"a closed ring {ring.length} long"


def test_no_state_line_is_too_short_to_have_been_written(state_lines):
    """SPEC 11.14: parts below the written precision are dropped, not kept.

    Noding two boundaries leaves centimetre-long fragments whose ends round
    to the same coordinate, and one of those became a zero-length ring in the
    first build of this file.
    """
    for part in line_parts(state_lines):
        assert part.length >= GRID * 0.999, part


def test_the_outline_files_are_small_enough_to_ship():
    """SPEC 11.14, the budget: about 60 KB gzipped for both."""
    import gzip
    total = sum(len(gzip.compress(path.read_bytes(), 9))
                for path in (OUTLINE_FILE, STATES_FILE))
    assert total < 60_000, f"{total} gzipped bytes"


# ------------------------------------------ against the shapefiles themselves

@needs_shapefiles
def test_the_committed_outlines_are_what_the_builder_builds():
    """`--check` fails if either file has drifted from its source."""
    done = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        capture_output=True, text=True, check=False, cwd=str(ROOT))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "match what this script builds" in done.stdout


@needs_shapefiles
def test_jammu_and_kashmir_and_ladakh_share_a_drawn_boundary():
    """SPEC 11.14: the one shared boundary that had to be checked by name."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_outline

    units = build_outline.load(build_outline.ADMIN1, "admin", "India",
                               name_field="name")
    names = [name for name, _ in units]
    for wanted in build_outline.MUST_SHARE:
        assert wanted in names, f"admin-1 has no {wanted}"

    pairs = build_outline.shared_boundaries(units)
    key = build_outline.MUST_SHARE
    shared = pairs.get(key) or pairs.get(tuple(reversed(key)))
    assert shared is not None, "Jammu and Kashmir and Ladakh share no border"
    assert shared.length > 1.0, shared.length

    # And it really is drawn: the shared line is inside the committed file.
    drawn = geometry_of(STATES_FILE)[0]
    assert shared.buffer(0.02).intersection(drawn).length > 1.0


@needs_shapefiles
def test_the_drawn_outline_is_the_geometry_the_mask_was_cut_with():
    """SPEC 3.5: one source, so the country and the squares cannot disagree."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_outline

    source = build_outline.unary_union(
        build_outline.load(build_outline.ADMIN0, "NAME", "India"))
    drawn = geometry_of(OUTLINE_FILE)[0]
    assert drawn.area / source.area > 0.9999, "simplifying lost area"
    assert source.difference(drawn.buffer(0.02)).area == pytest.approx(
        0.0, abs=1e-6), "the drawn outline leaves part of the source out"
