"""Tests for the IMERG remapping (SPEC 3.1 to 3.4 and 3.7).

The remapping is the one step where a silent error would be invisible
downstream: a transpose, a latitude flip or a mean taken the wrong way would
all produce a plausible-looking rainfall field. So the tests here are built
to catch exactly those, and the last one re-implements the whole thing a
second way and compares against real data.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.nasa_process import (                          # noqa: E402
    COMPLETE_CNT,
    MIN_COMPLETE_FRACTION,
    N_LEAD_DAYS,
    PIXEL,
    NasaProcessError,
    build_remap,
    imerg_date_for,
    lead_day_steps,
    nasa_path,
    pixel_edges,
    read_window,
    remap,
    to_lat_lon_descending,
)
from pipeline.nasa_download import existing_file             # noqa: E402

HALF = cfg.GRID_STEP / 2.0


# --------------------------------------------------------------- fixtures

def imerg_centres():
    """The IMERG coordinate vectors, as the real files carry them."""
    lat = -90.0 + PIXEL / 2 + PIXEL * np.arange(1800)
    lon = -180.0 + PIXEL / 2 + PIXEL * np.arange(3600)
    return lat, lon


@pytest.fixture(scope="module")
def remapper():
    lat, lon = imerg_centres()
    lat_edges = pixel_edges(lat, PIXEL, -90.0, 90.0, "lat")
    lon_edges = pixel_edges(lon, PIXEL, -180.0, 180.0, "lon")
    return build_remap(lat_edges, lon_edges)


@pytest.fixture
def window(remapper):
    """Empty rain and count arrays shaped like the India window."""
    shape = (remapper.n_lat_window, remapper.n_lon_window)
    rain = np.zeros(shape, dtype=np.float64)
    cnt = np.full(shape, COMPLETE_CNT, dtype=np.int16)
    return rain, cnt


def window_pixel_edges(remapper):
    """(lat_top, lat_bottom, lon_left, lon_right) per window pixel."""
    lat_desc = remapper.lat_edges_window_desc
    lon = remapper.lon_edges_window
    return lat_desc[:-1], lat_desc[1:], lon[:-1], lon[1:]


def window_pixel_centres(remapper):
    lat_top, lat_bot, lon_left, lon_right = window_pixel_edges(remapper)
    return (lat_top + lat_bot) / 2.0, (lon_left + lon_right) / 2.0


def sind(x):
    return np.sin(np.deg2rad(x))


# -------------------------------------------------------- orientation first

def test_transpose_and_flip_is_what_spec_3_2_says():
    """(lon, lat) ascending becomes (lat, lon) descending."""
    block = np.array([[1.0, 2.0, 3.0],      # lon 0, latitudes ascending
                      [4.0, 5.0, 6.0]])     # lon 1
    out = to_lat_lon_descending(block)
    assert out.shape == (3, 2)
    # Highest latitude first, longitude across the row.
    assert np.array_equal(out, np.array([[3.0, 6.0],
                                         [2.0, 5.0],
                                         [1.0, 4.0]]))


def test_a_transpose_without_the_flip_would_be_caught():
    block = np.arange(6, dtype=np.float64).reshape(2, 3)
    assert not np.array_equal(to_lat_lon_descending(block), block.T)


# --------------------------------------------------------------- the grid

def test_window_covers_the_india_box(remapper):
    lat_top, lat_bot, lon_left, lon_right = window_pixel_edges(remapper)
    assert lat_top[0] >= cfg.LAT_MAX + HALF
    assert lat_bot[-1] <= cfg.LAT_MIN - HALF
    assert lon_left[0] <= cfg.LON_MIN - HALF
    assert lon_right[-1] >= cfg.LON_MAX + HALF


def test_pixel_edges_rejects_a_grid_that_is_not_the_imerg_grid():
    lat, _ = imerg_centres()
    with pytest.raises(NasaProcessError):
        pixel_edges(lat[::-1], PIXEL, -90.0, 90.0, "descending")
    with pytest.raises(NasaProcessError):
        pixel_edges(lat, 0.25, -90.0, 90.0, "wrong spacing")
    with pytest.raises(NasaProcessError):
        pixel_edges(lat + 1.0, PIXEL, -90.0, 90.0, "shifted")
    uneven = lat.copy()
    uneven[500] += 0.05
    with pytest.raises(NasaProcessError):
        pixel_edges(uneven, PIXEL, -90.0, 90.0, "uneven")


def test_weights_sum_to_the_cell_area(remapper):
    """build_remap asserts this; this test pins the identity itself."""
    summed = np.bincount(remapper.rows, weights=remapper.weight,
                         minlength=remapper.n_cells)
    assert np.allclose(summed, remapper.cell_area, rtol=1e-12, atol=0)


# ------------------------------------------------------------ the mean itself

def test_constant_field_comes_back_unchanged(remapper, window):
    rain, cnt = window
    rain[:] = 7.5
    out, fraction = remap(remapper, rain, cnt)
    assert np.allclose(out, 7.5, rtol=0, atol=1e-12)
    assert np.allclose(fraction, 1.0, rtol=0, atol=1e-12)


def test_field_linear_in_longitude_returns_the_cell_centre(remapper, window):
    """Longitude weights are symmetric about every 0.25 cell centre."""
    rain, cnt = window
    _, lon_centres = window_pixel_centres(remapper)
    rain[:] = lon_centres[None, :]

    out, _ = remap(remapper, rain, cnt)
    expected = np.asarray(cfg.INDIA_LONS, dtype=np.float64)[None, :]
    assert np.allclose(out, expected, rtol=0, atol=1e-9)


def test_asymmetric_field_matches_the_exact_cell_means(remapper, window):
    """lon * 1000 + lat. A flip or a transpose cannot survive this."""
    rain, cnt = window
    lat_centres, lon_centres = window_pixel_centres(remapper)
    rain[:] = lon_centres[None, :] * 1000.0 + lat_centres[:, None]

    out, _ = remap(remapper, rain, cnt)

    lat_top, lat_bot, lon_left, lon_right = window_pixel_edges(remapper)
    checked = [(0, 0), (0, cfg.N_LON - 1), (cfg.N_LAT - 1, 0),
               (cfg.N_LAT - 1, cfg.N_LON - 1), (64, 60), (17, 103), (99, 7)]

    for i, j in checked:
        # Written out longhand on purpose: this is the independent side.
        cell_top = cfg.INDIA_LATS[i] + HALF
        cell_bot = cfg.INDIA_LATS[i] - HALF
        cell_left = cfg.INDIA_LONS[j] - HALF
        cell_right = cfg.INDIA_LONS[j] + HALF

        total = 0.0
        weighted = 0.0
        for a in range(remapper.n_lat_window):
            top = min(lat_top[a], cell_top)
            bot = max(lat_bot[a], cell_bot)
            if top <= bot:
                continue
            lat_part = math.sin(math.radians(top)) - math.sin(math.radians(bot))
            for b in range(remapper.n_lon_window):
                right = min(lon_right[b], cell_right)
                left = max(lon_left[b], cell_left)
                if right <= left:
                    continue
                w = lat_part * (right - left)
                total += w
                weighted += w * rain[a, b]
        expected = weighted / total
        assert out[i, j] == pytest.approx(expected, rel=1e-12, abs=1e-9), (
            f"cell {i},{j}")


def test_single_pixel_spike_gets_its_hand_computed_weight(remapper, window):
    """A 100 mm pixel wholly inside one cell, every other pixel dry.

    Cell centre 20.00 N, 70.00 E spans 19.875-20.125 and 69.875-70.125.
    The pixel centred 19.95 N, 69.95 E spans 19.9-20.0 and 69.9-70.0, so it
    lies wholly inside, and its weight is the whole pixel area.
    """
    rain, cnt = window
    lat_centres, lon_centres = window_pixel_centres(remapper)
    a = int(np.argmin(np.abs(lat_centres - 19.95)))
    b = int(np.argmin(np.abs(lon_centres - 69.95)))
    assert lat_centres[a] == pytest.approx(19.95, abs=1e-9)
    assert lon_centres[b] == pytest.approx(69.95, abs=1e-9)
    rain[a, b] = 100.0

    i = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LATS) - 20.0)))
    j = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LONS) - 70.0)))

    pixel_weight = 0.1 * (math.sin(math.radians(20.0))
                          - math.sin(math.radians(19.9)))
    cell_weight = 0.25 * (math.sin(math.radians(20.125))
                          - math.sin(math.radians(19.875)))
    expected = 100.0 * pixel_weight / cell_weight

    out, _ = remap(remapper, rain, cnt)
    assert out[i, j] == pytest.approx(expected, rel=1e-12)

    # and the spike must not leak into the cell to the north or the east
    assert out[i - 1, j] == pytest.approx(0.0, abs=1e-12)
    assert out[i, j + 1] == pytest.approx(0.0, abs=1e-12)


def test_area_weighted_total_is_conserved(remapper, window):
    """Rain of 1 mm over lat 10-20 N, lon 70-80 E, nothing elsewhere.

    Those edges are whole degrees, so they fall exactly on IMERG pixel edges
    and the wet region is an exact whole number of pixels. The region is also
    strictly inside the India box, so every wet pixel is fully inside the
    tiling of cells and the weighted total must come out exactly.
    """
    rain, cnt = window
    lat_centres, lon_centres = window_pixel_centres(remapper)
    wet = (((lat_centres > 10.0) & (lat_centres < 20.0))[:, None]
           & ((lon_centres > 70.0) & (lon_centres < 80.0))[None, :])
    rain[wet] = 1.0

    out, _ = remap(remapper, rain, cnt)
    total = float(np.nansum(out.ravel() * remapper.cell_area))
    expected = 10.0 * (math.sin(math.radians(20.0))
                       - math.sin(math.radians(10.0)))
    assert total == pytest.approx(expected, rel=1e-12)


# ------------------------------------------------------------ completeness

def test_incomplete_pixels_are_excluded_and_not_treated_as_zero(
        remapper, window):
    rain, cnt = window
    lat_centres, lon_centres = window_pixel_centres(remapper)
    rain[:] = 4.0

    # One pixel column inside the grid is incomplete and carries nonsense.
    b = int(np.argmin(np.abs(lon_centres - 80.05)))
    cnt[:, b] = 30
    rain[:, b] = 999.0

    out, fraction = remap(remapper, rain, cnt)
    affected = fraction < 1.0 - 1e-12
    assert affected.any(), "the incomplete column should affect some cells"
    # Excluded, not zero: every usable cell still reads exactly 4 mm.
    usable = np.isfinite(out)
    assert np.allclose(out[usable], 4.0, rtol=0, atol=1e-12)


def test_the_ninety_percent_boundary_is_exact(remapper, window):
    """A cell centred on a pixel edge has longitude overlaps 0.1/0.4/0.4/0.1.

    So knocking out its outermost pixel column removes exactly 10% of the
    cell's area, whatever the latitude, and the cell must still be usable.
    One more pixel removed takes it below the line.
    """
    rain, cnt = window
    lat_centres, lon_centres = window_pixel_centres(remapper)
    rain[:] = 3.0

    j = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LONS) - 70.0)))
    i = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LATS) - 20.0)))
    cell_left = cfg.INDIA_LONS[j] - HALF            # 69.875
    # The column holding the cell's left edge contributes 0.025 of 0.25.
    b_edge = int(np.argmin(np.abs(lon_centres - (cell_left - 0.025))))
    assert lon_centres[b_edge] == pytest.approx(69.85, abs=1e-9)

    cnt[:, b_edge] = 10
    out, fraction = remap(remapper, rain, cnt)
    assert fraction[i, j] == pytest.approx(MIN_COMPLETE_FRACTION, abs=1e-12)
    assert np.isfinite(out[i, j]), "exactly 90% must pass"
    assert out[i, j] == pytest.approx(3.0, rel=1e-12)

    # Now remove one more pixel from the same cell: below the line, so NaN.
    a = int(np.argmin(np.abs(lat_centres - 19.95)))
    cnt[a, b_edge + 1] = 10
    out2, fraction2 = remap(remapper, rain, cnt)
    assert fraction2[i, j] < MIN_COMPLETE_FRACTION
    assert np.isnan(out2[i, j]), "below 90% must be missing"


# ------------------------------------------------------------ date mapping

def test_imerg_date_for_matches_the_lead_day_windows():
    assert imerg_date_for("20260801", 1) == "20260802"
    assert imerg_date_for("20260801", 5) == "20260806"
    assert lead_day_steps(1) == (24, 48)
    assert lead_day_steps(5) == (120, 144)


def test_imerg_date_for_crosses_months_and_years():
    assert imerg_date_for("20260830", 5) == "20260904"
    assert imerg_date_for("20261230", 5) == "20270104"
    assert imerg_date_for("20260226", 3) == "20260301"   # 2026 is not a leap


def test_imerg_date_for_rejects_impossible_lead_days():
    for bad in (0, -1, N_LEAD_DAYS + 1, 1.0, True):
        with pytest.raises(NasaProcessError):
            imerg_date_for("20260801", bad)


# ---------------------------------------------- the independent second pass

def brute_force(rain_window, cnt_window, remapper, n_sub=50):
    """A deliberately different implementation, for cross-checking.

    Supersamples each ECMWF cell on an n_sub x n_sub grid of points, takes
    the pixel each point lands in by nearest neighbour, and weights the
    points by cos(latitude). Shares no code with the sparse-matrix path: no
    overlap arithmetic, no sine areas, no bincount.
    """
    n_lat_w, n_lon_w = rain_window.shape
    step = cfg.GRID_STEP / n_sub
    offsets = (np.arange(n_sub) + 0.5) * step

    out = np.full((cfg.N_LAT, cfg.N_LON), np.nan)
    frac = np.zeros((cfg.N_LAT, cfg.N_LON))

    # window row 0 is the northernmost pixel
    top_pixel_global = remapper.lat_slice.stop - 1

    for i in range(cfg.N_LAT):
        sub_lat = cfg.INDIA_LATS[i] - HALF + offsets
        ilat_global = np.floor((sub_lat + 90.0) / PIXEL).astype(int)
        rows = top_pixel_global - ilat_global
        assert rows.min() >= 0 and rows.max() < n_lat_w
        w_lat = np.cos(np.deg2rad(sub_lat))

        for j in range(cfg.N_LON):
            sub_lon = cfg.INDIA_LONS[j] - HALF + offsets
            cols = np.floor((sub_lon + 180.0) / PIXEL).astype(int)
            cols = cols - remapper.lon_slice.start
            assert cols.min() >= 0 and cols.max() < n_lon_w

            values = rain_window[np.ix_(rows, cols)]
            counts = cnt_window[np.ix_(rows, cols)]
            good = (counts == COMPLETE_CNT) & np.isfinite(values)

            w = np.repeat(w_lat[:, None], n_sub, axis=1)
            total = w.sum()
            kept = (w * good).sum()
            frac[i, j] = kept / total
            if frac[i, j] >= MIN_COMPLETE_FRACTION - 1e-12 and kept > 0:
                out[i, j] = (w * good * np.where(good, values, 0.0)).sum() / kept
    return out, frac


def real_date_with_a_file():
    for date in ("20260714", "20260715", "20260801"):
        if existing_file(date) is not None:
            return date
    return None


def test_brute_force_agrees_on_real_data(remapper):
    """Second implementation against the first, on a real IMERG day.

    Skipped where the raw IMERG files are not present, because data/ is never
    committed. It was run against 14 July 2026 on 12 November 2026.
    """
    import h5py

    date = real_date_with_a_file()
    if date is None:
        pytest.skip("no raw IMERG file present to cross-check against")
    path = existing_file(date)

    with h5py.File(path, "r") as f:
        rain_w, cnt_w, _ = read_window(f, remapper, date, path.name)

    mine, my_frac = remap(remapper, rain_w, cnt_w)
    theirs, their_frac = brute_force(rain_w, cnt_w, remapper)

    # The completeness fractions must agree closely; where they straddle the
    # 90% line the usable masks may legitimately differ, nowhere else.
    assert np.allclose(my_frac, their_frac, rtol=0, atol=1e-6)

    mine_ok, theirs_ok = np.isfinite(mine), np.isfinite(theirs)
    disagree = mine_ok != theirs_ok
    if disagree.any():
        near = np.abs(my_frac - MIN_COMPLETE_FRACTION) < 1e-6
        assert (disagree & ~near).sum() == 0, "usable masks differ off the line"

    both = mine_ok & theirs_ok
    assert both.sum() > 0.99 * mine.size
    worst = float(np.max(np.abs(mine[both] - theirs[both])))
    assert worst < 1e-3, f"worst disagreement {worst} mm on {date}"


# --------------------------------------------------------------- the output

def test_the_saved_file_has_what_spec_3_7_promises():
    date = real_date_with_a_file()
    if date is None or not nasa_path(date).exists():
        pytest.skip("no processed IMERG date present")
    with np.load(nasa_path(date)) as f:
        assert set(f.keys()) == {"rain", "complete_fraction", "lat", "lon"}
        assert f["rain"].shape == (cfg.N_LAT, cfg.N_LON)
        assert f["rain"].dtype == np.float32
        assert f["complete_fraction"].shape == (cfg.N_LAT, cfg.N_LON)
        assert f["complete_fraction"].dtype == np.float32
        assert f["lat"][0] == cfg.LAT_MAX and f["lat"][-1] == cfg.LAT_MIN
        assert f["lon"][0] == cfg.LON_MIN and f["lon"][-1] == cfg.LON_MAX
        rain = f["rain"]
        assert np.nanmin(rain) >= 0.0
