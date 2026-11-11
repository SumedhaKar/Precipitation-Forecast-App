"""Tests for the India window, the packing tolerance and the quantum cap.

These cover the two real defects found on 12 November 2026:
the longitude origin moving from 0 to 180, and the packing quantum becoming
coarser than the old fixed -0.1 mm tolerance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                                  # noqa: E402
from pipeline.checks import (                                       # noqa: E402
    CheckFailed,
    check_daily_differences,
    check_quantum_cap,
)
from pipeline.ecmwf_process import daily_totals, quantum_summary    # noqa: E402


# ----------------------------------------------------- the India window

def _axes_for(origin: float):
    """Longitudes and latitudes the India slice actually selects."""
    rows, cols = cfg.india_slice(90.0, origin)
    lons = [(origin + cfg.GRID_STEP * k) % 360.0
            for k in range(cols.start, cols.stop)]
    lats = [90.0 - cfg.GRID_STEP * k for k in range(rows.start, rows.stop)]
    return lats, lons


@pytest.mark.parametrize("origin, expected_col_start", [(0.0, 272), (180.0, 992)])
def test_india_window_is_correct_for_both_origins(origin, expected_col_start):
    """ECMWF moved the origin from 0 to 180 around 20 October 2026."""
    rows, cols = cfg.india_slice(90.0, origin)

    assert cols.start == expected_col_start
    assert cols.stop - cols.start == cfg.N_LON
    assert rows.stop - rows.start == cfg.N_LAT

    lats, lons = _axes_for(origin)
    assert lats[0] == cfg.LAT_MAX
    assert lats[-1] == cfg.LAT_MIN
    assert lons[0] == cfg.LON_MIN
    assert lons[-1] == cfg.LON_MAX


def test_both_origins_select_the_same_patch_of_the_world():
    """The same India data, at a different offset, must come back identical."""
    rng = np.random.default_rng(0)
    world = rng.random((cfg.GLOBAL_NJ, cfg.GLOBAL_NI)).astype(np.float32)

    rows_a, cols_a = cfg.india_slice(90.0, 0.0)
    india_old = world[rows_a, cols_a]

    # A file with origin 180 holds the same world rolled by half its width.
    rolled = np.roll(world, -cfg.GLOBAL_NI // 2, axis=1)
    rows_b, cols_b = cfg.india_slice(90.0, 180.0)
    india_new = rolled[rows_b, cols_b]

    assert np.array_equal(india_old, india_new)


def test_off_grid_origin_is_rejected():
    with pytest.raises(cfg.GridLayoutError):
        cfg.india_cols_for(68.125)


def test_origin_that_would_wrap_is_rejected():
    """India must be contiguous; a wrapping window is refused, not wrapped."""
    with pytest.raises(cfg.GridLayoutError):
        # Puts longitude 68 at column 1430, so India would run off the end.
        cfg.india_cols_for((cfg.LON_MIN - 1430 * cfg.GRID_STEP) % 360.0)


# ------------------------------------------------------ the tolerance

def _packing(quantum: float, per_step: dict[int, float] | None = None) -> dict:
    out = {}
    for step in cfg.STEPS:
        q = (per_step or {}).get(step, quantum)
        out[f"cf_{step}"] = [{"quantum": q}]
        out[f"pf_{step}"] = [{"quantum": q} for _ in range(50)]
    return out


def test_tolerance_is_twice_the_coarsest_quantum():
    assert cfg.tolerance_for(0.125) == pytest.approx(-0.25)
    assert cfg.tolerance_for(0.015625) == pytest.approx(-0.03125)


def test_coarsest_quantum_is_the_maximum_over_all_steps():
    """13 May really did vary from 0.0039 to 0.015625 across its steps."""
    packing = _packing(0.00390625, per_step={120: 0.015625, 144: 0.0078125})
    summary = quantum_summary(packing)

    assert summary["coarsest_mm"] == pytest.approx(0.015625)
    assert summary["per_step_mm"]["24"] == pytest.approx(0.00390625)
    assert summary["per_step_mm"]["120"] == pytest.approx(0.015625)
    assert cfg.tolerance_for(summary["coarsest_mm"]) == pytest.approx(-0.03125)


def test_real_october_quantum_accepts_the_real_october_difference():
    """25 October: quantum 0.25, worst difference -0.125. Must pass now."""
    tolerance = cfg.tolerance_for(0.25)
    assert tolerance == pytest.approx(-0.5)

    tp = np.zeros((2, 1, 1, 1), dtype=np.float32)
    tp[1, 0, 0, 0] = -0.125  # the real worst value seen on 25 October

    summary = check_daily_differences(tp, tolerance)
    assert summary["most_negative_difference_mm"] == pytest.approx(-0.125)
    assert summary["values_set_to_zero"] == 1


def test_difference_below_tolerance_fails():
    tolerance = cfg.tolerance_for(0.015625)  # -0.03125, the May figure
    tp = np.zeros((2, 1, 1, 1), dtype=np.float32)
    tp[1, 0, 0, 0] = -0.125  # October-sized noise in a May-precision file

    with pytest.raises(CheckFailed, match="below the tolerance"):
        check_daily_differences(tp, tolerance)


def test_values_between_tolerance_and_zero_become_zero():
    tp = np.zeros((2, 1, 1, 2), dtype=np.float32)
    tp[1, 0, 0, 0] = -0.125   # noise, becomes 0
    tp[1, 0, 0, 1] = 7.5      # real rain, kept

    totals = daily_totals(tp, tolerance=cfg.tolerance_for(0.25))
    assert totals[0, 0, 0, 0] == 0.0
    assert totals[0, 0, 0, 1] == pytest.approx(7.5)
    assert (totals >= 0).all()


# -------------------------------------------------------- the 0.5 mm cap

def test_cap_allows_the_real_october_date():
    check_quantum_cap(0.25)  # must not raise


def test_cap_allows_exactly_the_limit():
    check_quantum_cap(cfg.MAX_TRUSTED_QUANTUM)  # must not raise


def test_cap_triggers_above_the_limit():
    with pytest.raises(CheckFailed, match="above the 0.5 mm cap"):
        check_quantum_cap(0.5000001)


def test_cap_triggers_on_a_much_coarser_file():
    with pytest.raises(CheckFailed, match="too coarse to trust"):
        check_quantum_cap(1.0)


def test_cap_uses_the_coarsest_step_not_the_average():
    """One coarse step is enough to fail the date."""
    packing = _packing(0.125, per_step={144: 1.0})
    summary = quantum_summary(packing)

    assert summary["coarsest_mm"] == pytest.approx(1.0)
    with pytest.raises(CheckFailed):
        check_quantum_cap(summary["coarsest_mm"])
