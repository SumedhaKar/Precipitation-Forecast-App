"""Counts and dots (SPEC 4.2 and 4.3).

The site shows a count out of 51 on the map and 51 dots in the place panel.
If those two ever disagree the site is lying to the reader about its own
numbers, so the relationship between them is tested on every square of a
whole grid, not on a sample.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                      # noqa: E402
from pipeline.run_live import (                         # noqa: E402
    DOT_EDGES,
    THRESHOLDS,
    LiveRunError,
    build_product,
    counts_from,
    dots_from,
)

SHAPE = (cfg.N_DAYS, cfg.N_MEMBERS, cfg.N_LAT, cfg.N_LON)


@pytest.fixture(scope="module")
def totals():
    """A field with every interesting value in it, over the whole grid."""
    rng = np.random.default_rng(20261112)
    data = rng.gamma(shape=0.35, scale=28.0, size=SHAPE).astype(np.float32)

    # Plant the exact boundary values so the >= rule is exercised directly.
    data[0, 0, 0, 0] = 1.0
    data[0, 1, 0, 0] = 10.0
    data[0, 2, 0, 0] = 50.0
    data[0, 3, 0, 0] = 0.9999999
    data[0, 4, 0, 0] = 9.999999
    data[0, 5, 0, 0] = 49.999996
    data[0, 6, 0, 0] = 0.0
    data[1, :, 5, 5] = 10.0          # a whole square of exactly 10.0
    data[2, :, 7, 7] = 0.0           # a dry square
    data[3, :, 9, 9] = 120.0         # a very wet square
    return data


def test_counts_and_dots_have_the_right_shapes(totals):
    counts = counts_from(totals)
    dots = dots_from(totals)
    assert counts.shape == (3, cfg.N_DAYS, cfg.N_LAT, cfg.N_LON)
    assert dots.shape == (4, cfg.N_DAYS, cfg.N_LAT, cfg.N_LON)
    assert counts.dtype == np.uint8 and dots.dtype == np.uint8


def test_the_dots_always_add_up_to_51_on_every_square(totals):
    dots = dots_from(totals)
    assert np.all(dots.sum(axis=0) == cfg.N_MEMBERS)
    assert dots.sum() == cfg.N_DAYS * cfg.N_LAT * cfg.N_LON * cfg.N_MEMBERS


def test_dots_at_or_above_each_threshold_equal_that_count(totals):
    """The identity the site depends on, on every square of every day."""
    counts = counts_from(totals)
    dots = dots_from(totals)
    assert np.array_equal(counts[0], dots[1] + dots[2] + dots[3])
    assert np.array_equal(counts[1], dots[2] + dots[3])
    assert np.array_equal(counts[2], dots[3])


def test_the_dot_edges_are_the_thresholds(totals):
    assert tuple(DOT_EDGES) == tuple(THRESHOLDS)


def test_counts_never_exceed_51_and_are_monotone(totals):
    counts = counts_from(totals)
    assert counts.max() <= cfg.N_MEMBERS
    # more members reach 1 mm than 10 mm, and more reach 10 mm than 50 mm
    assert np.all(counts[0] >= counts[1])
    assert np.all(counts[1] >= counts[2])


def test_exactly_ten_counts_towards_the_ten_mm_threshold():
    """SPEC 4.2: the rule is >=, so 10.0 is in."""
    data = np.full((1, cfg.N_MEMBERS, 1, 1), 10.0, dtype=np.float32)
    counts = counts_from(data)
    dots = dots_from(data)
    assert counts[1, 0, 0, 0] == cfg.N_MEMBERS, "10.0 must count at 10 mm"
    assert counts[0, 0, 0, 0] == cfg.N_MEMBERS, "10.0 also counts at 1 mm"
    assert counts[2, 0, 0, 0] == 0, "10.0 must not count at 50 mm"
    assert dots[2, 0, 0, 0] == cfg.N_MEMBERS, "10.0 is in the 10 to 50 band"
    assert dots[1, 0, 0, 0] == 0


def test_each_threshold_boundary_exactly(totals):
    for k, edge in enumerate(THRESHOLDS):
        exactly = np.full((1, cfg.N_MEMBERS, 1, 1), edge, dtype=np.float64)
        just_under = np.nextafter(exactly, 0.0)
        assert counts_from(exactly)[k, 0, 0, 0] == cfg.N_MEMBERS
        assert counts_from(just_under)[k, 0, 0, 0] == 0


def test_a_dry_square_is_all_in_the_first_dot_category(totals):
    dots = dots_from(totals)
    assert dots[0, 2, 7, 7] == cfg.N_MEMBERS
    counts = counts_from(totals)
    assert counts[0, 2, 7, 7] == 0


def test_a_very_wet_square_is_all_in_the_last_dot_category(totals):
    dots = dots_from(totals)
    counts = counts_from(totals)
    assert dots[3, 3, 9, 9] == cfg.N_MEMBERS
    assert counts[2, 3, 9, 9] == cfg.N_MEMBERS


def test_build_product_keeps_the_member_totals_as_the_record(totals):
    product = build_product(totals)
    assert np.array_equal(product["member_totals"], totals.astype(np.float32))
    assert np.array_equal(product["counts"], counts_from(totals))
    assert np.array_equal(product["dots"], dots_from(totals))


def test_build_product_refuses_a_wrong_member_count():
    wrong = np.zeros((cfg.N_DAYS, 50, 4, 4), dtype=np.float32)
    with pytest.raises(LiveRunError):
        build_product(wrong)
    with pytest.raises(LiveRunError):
        counts_from(np.zeros((cfg.N_MEMBERS, 4, 4), dtype=np.float32))


def test_counts_are_what_a_longhand_loop_gives():
    """A small grid, counted one member at a time in plain Python."""
    rng = np.random.default_rng(7)
    data = rng.gamma(0.4, 25.0, size=(2, cfg.N_MEMBERS, 3, 4)).astype(np.float32)
    counts = counts_from(data)
    dots = dots_from(data)

    for d in range(2):
        for i in range(3):
            for j in range(4):
                members = [float(data[d, m, i, j]) for m in range(cfg.N_MEMBERS)]
                for k, edge in enumerate(THRESHOLDS):
                    assert counts[k, d, i, j] == sum(
                        1 for v in members if v >= edge)
                bands = [
                    sum(1 for v in members if v < 1.0),
                    sum(1 for v in members if 1.0 <= v < 10.0),
                    sum(1 for v in members if 10.0 <= v < 50.0),
                    sum(1 for v in members if v >= 50.0),
                ]
                assert list(dots[:, d, i, j]) == bands
