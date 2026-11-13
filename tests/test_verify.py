"""Verification, checked against answers worked out by hand.

SPEC 5 and 5.11. Nothing here reads the real archive: every test builds a
handful of squares and a handful of dates whose Brier score, reference and
skill can be written down on paper, and then asks the code for them.

The toy archive is three squares on one row, two run dates and one lead day,
and it is the same one throughout:

    square 0, region A        square 1, region A        square 2, region B
    date A  k=51  obs 20 mm   k=0   obs 0 mm           k=25  obs 20 mm
    date B  k=0   obs 0 mm    k=51  obs 20 mm          k=25  obs 0 mm

At a 10 mm threshold every square sees the event once in two days, so every
reference group's rate is 0.5 and every reference Brier score is 0.25.
Region A forecast both days perfectly, so its Brier score is 0 and its skill
is exactly 1. Region B said 25 of 51 both days and the event happened once,
so its Brier score is ((26/51)^2 + (25/51)^2) / 2 and its skill is one minus
that over 0.25.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import verify
from pipeline.run_live import THRESHOLDS, counts_from

ROOT = Path(__file__).resolve().parent.parent

MEMBERS = 51
N_STEPS = 6


def toy_mask(coastal=(False, False, False)) -> dict:
    return {
        "india": np.array([[True, True, True]]),
        "coastal": np.array([list(coastal)]),
        "lat": np.array([20.0]),
        "lon": np.array([70.0, 70.25, 70.5]),
    }


def toy_regions(codes=(1, 1, 2)) -> dict:
    return {"regions": ["Region A", "Region B"],
            "codes": np.array([list(codes)], dtype=np.int8)}


def forecast_of(counts) -> np.ndarray:
    """A stored accumulation whose day 1 totals give these member counts.

    `counts[j]` members reach 20 mm in square j on day 1; the rest get 0.
    Later days are flat, so their totals are 0.
    """
    tp = np.zeros((N_STEPS, MEMBERS, 1, 3), dtype=np.float32)
    for j, k in enumerate(counts):
        tp[1:, :k, 0, j] = 20.0
    return tp


def toy_setup(dates=("20260601", "20260602"), thresholds=(10.0,),
              leads=(1,), coastal=(False, False, False),
              codes=(1, 1, 2), available=None) -> verify.Setup:
    if available is None:
        available = {"20260602", "20260603"}
    return verify.Setup(toy_mask(coastal), toy_regions(codes), list(dates),
                        set(available), thresholds=thresholds, leads=leads)


def toy_run(**kwargs):
    """The whole toy archive through `verify.build`."""
    forecasts = kwargs.pop("forecasts", {"20260601": (51, 0, 25),
                                         "20260602": (0, 51, 25)})
    obs = kwargs.pop("obs", {"20260602": [20.0, 0.0, 20.0],
                             "20260603": [0.0, 20.0, 0.0]})
    setup = toy_setup(**kwargs)
    cache = {date: np.array(values, dtype=np.float64)
             for date, values in obs.items()}
    return verify.build(setup, cache, report=lambda *a: None,
                        load=lambda date: forecast_of(forecasts[date]))


def group_of(result, region, variant="all51", lead=1, threshold=10.0):
    for row in result["groups_scored"]:
        if (row["region"] == region and row["variant"] == variant
                and row["lead_day"] == lead
                and row["threshold_mm"] == threshold):
            return row
    return None


# --------------------------------------------------------- the pairing

def test_a_case_is_scored_against_the_day_its_forecast_was_for():
    """SPEC 5.1 and 3.7. Run date R, lead n, the IMERG day R + n."""
    result = toy_run()
    perfect = group_of(result, "Region A")
    middling = group_of(result, "Region B")
    assert perfect["cases"] == 4 and middling["cases"] == 2

    # Region A got both days exactly right, so there is nothing to score.
    assert perfect["bs"] == 0.0
    assert perfect["bss"] == 1.0

    # Region B said 25 of 51 twice and was right once.
    want = ((26 / 51) ** 2 + (25 / 51) ** 2) / 2
    assert middling["bs"] == pytest.approx(want, abs=1e-12)
    assert middling["reference_bs"] == pytest.approx(0.25, abs=1e-12)
    assert middling["bss"] == pytest.approx(1 - want / 0.25, abs=1e-12)


def test_the_reference_is_keyed_on_the_month_of_the_day_forecast():
    """SPEC 5.3. A run on the last of the month is scored against the next.

    The run of 30 June, lead day 1, is a forecast of 1 July, so its reference
    group is July's, not June's. Here the two dates straddle the month end
    and the code must put them in different months.
    """
    setup = toy_setup(dates=("20260629", "20260630"),
                      available={"20260630", "20260701"})
    cache = {"20260630": np.array([20.0, 0.0, 0.0]),
             "20260701": np.array([0.0, 20.0, 0.0])}
    ref = verify.reference(setup, cache)
    assert setup.months == [6, 7]
    # Square 0 saw the event in June and not in July; square 1 the other way.
    assert ref["rate"][0, setup.month_index[6], 0, 0] == 1.0
    assert ref["rate"][0, setup.month_index[7], 0, 0] == 0.0
    assert ref["rate"][1, setup.month_index[6], 0, 0] == 0.0
    assert ref["rate"][1, setup.month_index[7], 0, 0] == 1.0
    # Each group holds exactly the one case that belongs to it.
    assert ref["cases"].sum() == 6
    assert set(np.unique(ref["cases"][ref["cases"] > 0])) == {1}


def test_the_threshold_is_greater_than_or_equal_on_both_sides():
    """SPEC 4.2 and 5.11 rule 4. Exactly 10.0 mm counts, with no epsilon."""
    setup = toy_setup(thresholds=(10.0,))
    cache = {"20260602": np.array([10.0, 9.999999, 20.0]),
             "20260603": np.array([0.0, 0.0, 0.0])}
    ref = verify.reference(setup, cache)
    first = ref["rate"][:, setup.month_index[6], 0, 0]
    assert list(first) == [0.5, 0.0, 0.5], "10.0 mm observed is the event"

    totals = verify.daily_totals(forecast_of((0, 0, 0)))
    totals[0, :10, 0, 0] = 10.0
    totals[0, :10, 0, 1] = 9.999999
    counts = verify.count_at(totals[:, :, setup.india], (10.0,))
    assert counts[0, 0, 0] == 10 and counts[0, 0, 1] == 0


def test_the_counting_is_the_same_counting_the_site_publishes():
    """SPEC 5.11 rule 1. One counting rule, not two that look alike."""
    rng = np.random.default_rng(7)
    totals = rng.gamma(0.3, 20.0, size=(5, 51, 4, 3)).astype(np.float32)
    mine = verify.count_at(totals, THRESHOLDS)
    theirs = counts_from(totals)
    assert np.array_equal(mine, theirs)


# ------------------------------------------------------------ exclusions

def test_a_box_day_below_ninety_per_cent_is_excluded_and_counted():
    """SPEC 3.4 and 5.2. Missing is missing, never zero rainfall."""
    result = toy_run(obs={"20260602": [20.0, float("nan"), 20.0],
                          "20260603": [0.0, 20.0, 0.0]})
    assert result["cases"]["excluded"]["observation_incomplete"] == 1
    assert result["cases"]["used"] == 5
    assert result["cases"]["possible"] == 2 * 1 * 3 * 1

    # Square 1 is in Region A and lost one of its two days.
    assert group_of(result, "Region A")["cases"] == 3
    # Its reference group now has one case, not two, and that case is the
    # one it was scored against: an event, so the rate is 1.
    assert group_of(result, "Region A")["dates"] == 2


def test_a_lead_day_with_no_observation_is_excluded_and_counted():
    """SPEC 5.11 rule 2. No IMERG file, no case."""
    result = toy_run(available={"20260602"})
    assert result["cases"]["excluded"]["no_imerg_date"] == 3
    assert result["cases"]["used"] == 3
    assert result["cases"]["used"] + result["cases"]["excluded_total"] == (
        result["cases"]["possible"])


def test_used_and_excluded_add_up_to_possible():
    """SPEC 5.11 rule 7. The identity is the proof nothing was dropped."""
    result = toy_run(obs={"20260602": [20.0, float("nan"), 20.0],
                          "20260603": [float("nan"), 20.0, 0.0]},
                     available={"20260602", "20260603"})
    tally = result["cases"]
    assert tally["used"] + tally["excluded_total"] == tally["possible"]
    assert tally["excluded"]["observation_incomplete"] == 2


def test_the_coastal_rerun_leaves_the_coastal_squares_out():
    """SPEC 5.11 rule 6. Coastal squares are in the headline and checked."""
    result = toy_run(coastal=(False, False, True))
    assert result["squares"] == {"india": 3, "coastal": 1, "inland": 2}
    assert group_of(result, "Region B", variant="all51")["cases"] == 2
    # Region B is nothing but its one coastal square, so inland it is gone.
    assert group_of(result, "Region B", variant="inland51") is None
    assert group_of(result, "Region A", variant="inland51")["cases"] == 4


# ------------------------------------------------------------- reference

def test_a_reference_that_was_never_wrong_gives_no_skill_at_all():
    """SPEC 5.11 rule 8. 1 - x/0 is not a number, and we do not print one."""
    # The event never happens anywhere, so every reference rate is 0 and
    # every reference Brier score is 0 too.
    result = toy_run(obs={"20260602": [0.0, 0.0, 0.0],
                          "20260603": [0.0, 0.0, 0.0]})
    for region in ("Region A", "Region B"):
        row = group_of(result, region)
        assert row["reference_bs"] == 0.0
        assert row["bss"] is None, "no reference to divide by"
        assert row["bss_lo"] is None and row["bss_hi"] is None
        assert row["resamples_discarded"] == verify.RESAMPLES
        assert row["cases_with_flat_reference"] == row["cases"]
    assert verify.bss_of(0.3, 0.0) is None


def test_a_case_is_inside_its_own_reference_group():
    """SPEC 5.11 rule 9. In-sample, with no leave-one-out."""
    setup = toy_setup(dates=("20260601",), available={"20260602"})
    cache = {"20260602": np.array([20.0, 0.0, 0.0])}
    ref = verify.reference(setup, cache)
    # One case per square, and the rate is that case's own outcome.
    assert list(ref["rate"][:, 0, 0, 0]) == [1.0, 0.0, 0.0]
    assert ref["smallest"] == 1 and ref["largest"] == 1


# --------------------------------------------------------------- buckets

def test_the_twelve_buckets_are_the_k_ranges_spec_writes_out():
    """SPEC 5.11, the bucket table. Five counts each, and the ends alone."""
    table = verify.bucket_table(51)
    assert len(table) == 12
    assert table[0] == {"name": "none", "k_from": 0, "k_to": 0}
    assert table[-1] == {"name": "all", "k_from": 51, "k_to": 51}
    bands = [(row["k_from"], row["k_to"]) for row in table[1:-1]]
    assert bands == [(1, 5), (6, 10), (11, 15), (16, 20), (21, 25), (26, 30),
                     (31, 35), (36, 40), (41, 45), (46, 50)]

    index = verify.bucket_index(51)
    assert index[0] == 0 and index[51] == 11
    assert index[5] == 1 and index[6] == 2, "the edge is k, not a float"
    assert index[50] == 10
    # Every k is in the band the table claims.
    for b, row in enumerate(table):
        for k in range(row["k_from"], row["k_to"] + 1):
            assert index[k] == b


def test_the_fifty_member_buckets_hold_four_then_five():
    """SPEC 5.11 rule 22. 50 does divide by 10, so the first band is short."""
    table = verify.bucket_table(50)
    bands = [(row["k_from"], row["k_to"]) for row in table[1:-1]]
    assert bands[0] == (1, 4)
    assert all(b - a == 4 for a, b in bands[1:])
    assert table[-1]["k_from"] == 50


def test_a_bucket_is_counted_only_with_enough_cases_from_enough_days():
    """SPEC 6.4. 100 cases from 10 start dates, or it is drawn and ignored."""
    result = toy_run()
    for row in result["groups_scored"]:
        for bucket in row["buckets"]:
            assert bucket["counted"] is False, "two days is never enough"
            if bucket["cases"]:
                assert bucket["dates"] <= 2
    assert result["bucket_floor"] == {"cases": 100, "dates": 10}

    # The mean forecast is the mean of the cases' own k/51, not a midpoint.
    region_b = group_of(result, "Region B")
    band = [b for b in region_b["buckets"] if b["cases"]][0]
    assert band["mean_forecast"] == pytest.approx(25 / 51, abs=1e-12)
    assert band["observed"] == 0.5


# -------------------------------------------------------- the decomposition

def test_the_decomposition_adds_up_to_the_brier_score_of_the_cases():
    """SPEC 5.7 and 5.11 rule 23. REL - RES + UNC = BS, to the last bit.

    The point of binning on the exact `k/51` values is that nothing is lost
    in the binning. So the test scores the cases one at a time, without any
    bins at all, and asks the decomposition to match that number.
    """
    rng = np.random.default_rng(11)
    for _ in range(20):
        k = rng.integers(0, 52, size=5000)
        observed = (rng.random(5000) < (k / 51) * 0.8 + 0.05).astype(float)
        bin_n = np.bincount(k, minlength=52)
        bin_o = np.bincount(k, weights=observed, minlength=52).astype(np.int64)
        parts = verify.decomposition(bin_n, bin_o, 51)
        case_by_case = float((((k / 51) - observed) ** 2).mean())
        assert parts["brier"] == pytest.approx(case_by_case, abs=1e-12)
        residual = (parts["reliability"] - parts["resolution"]
                    + parts["uncertainty"] - parts["brier"])
        assert abs(residual) <= verify.DECOMPOSITION_TOLERANCE
        assert parts["residual"] == pytest.approx(residual, abs=1e-18)


def test_a_decomposition_that_does_not_add_up_stops_the_run():
    """The identity is only a proof if failing it stops everything."""
    bin_n = np.zeros(52, dtype=np.int64)
    bin_o = np.zeros(52, dtype=np.int64)
    bin_n[10], bin_o[10] = 100, 40
    assert verify.decomposition(bin_n, bin_o, 51) is not None
    assert verify.DECOMPOSITION_TOLERANCE == 1e-12
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(verify, "DECOMPOSITION_TOLERANCE", -1.0)
        with pytest.raises(SystemExit, match="does not add up"):
            verify.decomposition(bin_n, bin_o, 51)


# ----------------------------------------------------------- the bootstrap

def test_the_draws_are_the_same_every_time_and_resample_whole_dates():
    """SPEC 5.5 and 5.11 rules 12 and 13."""
    first = verify.draws(177)
    second = verify.draws(177)
    assert np.array_equal(first, second), "the seed is fixed"
    assert first.shape == (verify.RESAMPLES, 177)
    assert (first.sum(axis=1) == 177).all(), "every draw is 177 whole dates"
    assert verify.SEED == 20261112 and verify.RESAMPLES == 1000
    assert verify.PERCENTILE_METHOD == "linear"
    # A different seed would be a different set, which is why ours is fixed.
    assert not np.array_equal(first, verify.draws(177, seed=1))


def test_the_range_comes_from_the_resampled_dates_and_nothing_else():
    """SPEC 5.5. A group's range is a percentile of its own resamples."""
    # Two dates, one group: one date scores 0, the other scores 0.25 against
    # a reference of 0.25 both days. So a resample is 1, 0.5 or 0 depending
    # on how many of each date it drew.
    row_bs = np.array([[0.0, 0.25]])
    row_ref = np.array([[0.25, 0.25]])
    counts = verify.draws(2)
    span = verify.bootstrap(row_bs, row_ref, counts)[0]
    assert span["discarded"] == 0
    assert -1e-12 <= span["bss_lo"] <= 1.0
    assert span["bss_hi"] == pytest.approx(1.0, abs=1e-12)

    values = 1 - (row_bs @ counts.T)[0] / (row_ref @ counts.T)[0]
    lo, hi = np.percentile(values, [2.5, 97.5], method="linear")
    assert span["bss_lo"] == pytest.approx(lo, abs=1e-15)
    assert span["bss_hi"] == pytest.approx(hi, abs=1e-15)


def test_a_resample_with_no_reference_to_divide_by_is_discarded():
    """SPEC 5.11 rule 15."""
    row_bs = np.array([[0.1, 0.0]])
    row_ref = np.array([[0.0, 0.0]])
    span = verify.bootstrap(row_bs, row_ref, verify.draws(2))[0]
    assert span["bss_lo"] is None and span["discarded"] == verify.RESAMPLES


# ------------------------------------------------------------ the blocks

def test_the_date_blocks_are_thirty_runs_and_the_last_one_is_short():
    """SPEC 5.11 rule 24, the temporal sense of block."""
    dates = [f"{d:08d}" for d in range(20260513, 20260513 + 177)]
    blocks = verify.date_blocks(dates)
    assert [b["dates"] for b in blocks] == [30, 30, 30, 30, 30, 27]
    assert [b["short"] for b in blocks] == [False] * 5 + [True]
    assert blocks[0]["from"] == dates[0] and blocks[-1]["to"] == dates[-1]
    assert sum(b["dates"] for b in blocks) == 177


def test_the_two_degree_blocks_are_floored_and_carry_their_square_count():
    """SPEC 5.11 rule 24, the spatial sense of block."""
    setup = toy_setup()
    assert setup.blocks == [(20.0, 70.0)]
    assert list(setup.sq_block) == [0, 0, 0]
    result = toy_run()
    row = result["two_degree"][0]
    assert row["lat"] == 20.0 and row["lon"] == 70.0
    assert row["squares"] == 3
    assert row["enough_squares"] is False, "three squares is not twenty"
    assert row["base_rate"] == pytest.approx(0.5, abs=1e-12)


# ------------------------------------------------------------ the writing

def test_every_float_is_rounded_the_same_way_on_the_way_out():
    """SPEC 5.11 rule 31. Two runs, the same bytes."""
    value = {"a": 1 / 3, "b": [2 / 3, {"c": 1e-9}], "d": "untouched", "e": 7}
    assert verify.round_floats(value) == {
        "a": 0.333333, "b": [0.666667, {"c": 0.0}], "d": "untouched", "e": 7}
    first = json.dumps(verify.round_floats(toy_run()), indent=1)
    second = json.dumps(verify.round_floats(toy_run()), indent=1)
    assert first == second


def test_the_spec_hash_is_of_the_committed_bytes():
    """SPEC 5.11 rule 28. CRLF here, LF in the repository."""
    raw = (ROOT / "SPEC.md").read_bytes()
    assert verify.spec_sha256() == hashlib.sha256(
        raw.replace(b"\r\n", b"\n")).hexdigest()
    if b"\r\n" in raw:
        assert verify.spec_sha256() != hashlib.sha256(raw).hexdigest()


def test_the_period_is_stated_and_says_what_it_does_not_cover():
    """SPEC 5.11, the period on everything."""
    result = toy_run()
    assert result["period"] == verify.PERIOD
    for word in ("13 May", "5 November 2026", "IMERG", "monsoon", "winter"):
        assert word in verify.PERIOD
    assert "understated" in result["note_small_reference_groups"]
    assert result["crps_compared"] is False


def test_the_gaps_in_pile_a_are_listed_by_date():
    """SPEC 5.11 rule 5. A failed date is named, not merely absent."""
    assert verify.gaps(["20260513", "20260514", "20260515"]) == []
    assert verify.gaps(["20260513", "20260516"]) == ["20260514", "20260515"]
    assert verify.gaps(["20260630", "20260702"]) == ["20260701"]


def test_the_fifty_member_card_drops_the_control_and_nothing_else():
    """SPEC 2.1 and 5.11 rule 22."""
    # Member 0 alone reaches 10 mm, so 51 members count 1 and 50 count 0.
    tp = np.zeros((N_STEPS, MEMBERS, 1, 3), dtype=np.float32)
    tp[1:, 0, 0, :] = 20.0
    setup = toy_setup(dates=("20260601",), available={"20260602"})
    cache = {"20260602": np.array([20.0, 20.0, 20.0])}
    built = verify.build(setup, cache, report=lambda *a: None,
                         load=lambda date: tp)
    with_control = group_of(built, "Region A", variant="all51")
    without = group_of(built, "Region A", variant="all50")
    assert with_control["bs"] == pytest.approx((1 - 1 / 51) ** 2, abs=1e-12)
    assert without["bs"] == 1.0, "without the control, nothing forecast rain"
    assert built["variants"][1]["members"] == 50

# ------------------------------------------------------------- the regions

def test_the_committed_regions_match_what_spec_54_counts():
    """SPEC 5.4. The region of every India square, as a committed fact.

    `config/regions.json` is built from the Natural Earth admin-1 file, which
    lives in `data/` and is never committed, so this reads the artefact and
    not the shapefile -- which is the point of having the artefact.
    """
    regions = verify.load_regions()
    mask = verify.load_mask()
    assert regions["regions"] == [
        "Northwest India", "Central India", "South Peninsula",
        "East & Northeast India"]
    assert regions["counts"] == {"Northwest India": 1501,
                                 "Central India": 1510,
                                 "South Peninsula": 857,
                                 "East & Northeast India": 745}
    assert regions["total"] == 4613 == sum(regions["counts"].values())

    codes = regions["codes"]
    india = mask["india"]
    assert ((codes > 0) == india).all(), "a region exactly where India is"
    assert codes.max() == 4 and codes[india].min() == 1

    # Rule 3, which is only safe while every square it catches is in the far
    # northwest and none of them is coastal (SPEC 5.4).
    back = regions["fallback"]
    assert back["squares"] == 183 and back["coastal"] == 0
    assert (back["lat_min"], back["lat_max"]) == (33.0, 37.0)
    assert (back["lon_min"], back["lon_max"]) == (72.75, 80.25)

    # All 36 admin-1 units, each in exactly one region.
    states = [name for region in regions["regions"]
              for name in regions["states"][region]]
    assert len(states) == 36 == len(set(states))
    assert sum(len(regions["subdivisions"][r])
               for r in regions["regions"]) == 36


def test_the_twelve_places_land_in_the_region_imd_puts_them_in():
    """SPEC 5.4's region tests, read back from the committed file."""
    regions = verify.load_regions()
    want = {"Delhi": "Northwest India", "Jaipur": "Northwest India",
            "Srinagar": "Northwest India", "Mumbai": "Central India",
            "Bhopal": "Central India", "Ahmedabad": "Central India",
            "Chennai": "South Peninsula", "Bengaluru": "South Peninsula",
            "Thiruvananthapuram": "South Peninsula",
            "Kolkata": "East & Northeast India",
            "Patna": "East & Northeast India",
            "Guwahati": "East & Northeast India"}
    got = {place: row["region"]
           for place, row in regions["place_tests"].items()}
    assert got == want
    # Mumbai's own square is sea, so the test is on the nearest India square.
    assert regions["place_tests"]["Mumbai"]["lat"] == 19.25
    # Odisha is Central India and the islands are South Peninsula: IMD's
    # placements, not ones we would have guessed.
    assert "Odisha" in regions["states"]["Central India"]
    assert "Andaman and Nicobar" in regions["states"]["South Peninsula"]
