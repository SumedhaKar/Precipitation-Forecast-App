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
