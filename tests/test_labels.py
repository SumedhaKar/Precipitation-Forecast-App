"""The three trust labels, checked against answers decided in advance.

SPEC 6 and 6.9. Every group here is made up, with numbers chosen so that the
right label is obvious before the code is asked for it: one group that passes
all four conditions of 6.2, and then the same group with one condition broken
at a time.
"""
from __future__ import annotations

import json

import pytest

from pipeline import labels
from pipeline.verify import PERIOD

RESAMPLES = 1000


def bucket(k_from, k_to, cases=500, dates=40, mean=0.5, observed=0.52):
    return {"bucket": f"{k_from}-{k_to}", "k_from": k_from, "k_to": k_to,
            "cases": cases, "dates": dates,
            "counted": cases >= 100 and dates >= 10,
            "mean_forecast": mean, "observed": observed,
            "error": abs(observed - mean)}


def group(**kwargs) -> dict:
    """A group that earns a good track record, before anything is broken."""
    out = {
        "variant": "all51", "region": "Central India", "lead_day": 1,
        "threshold_mm": 10.0,
        "cases": 50_000, "dates": 177, "event_dates": 120, "events": 4_000,
        "base_rate": 0.08, "bs": 0.05, "reference_bs": 0.07,
        "bss": 0.28, "bss_lo": 0.21, "bss_hi": 0.35, "bss_halfwidth": 0.07,
        "resamples_discarded": 0, "cases_with_flat_reference": 0,
        "decomposition": None,
        "buckets": [bucket(0, 0, mean=0.0, observed=0.02),
                    bucket(1, 5, mean=0.06, observed=0.10),
                    bucket(26, 30, mean=0.55, observed=0.60),
                    bucket(51, 51, mean=1.0, observed=0.93)],
    }
    out.update(kwargs)
    return out


def label_of(**kwargs) -> dict:
    return labels.label_for(group(**kwargs), RESAMPLES)


# ------------------------------------------------------------ the labels

def test_all_four_conditions_pass_and_the_label_is_green():
    """SPEC 6.2. Enough data, skill above 0, a narrow range, small error."""
    row = label_of()
    assert row["label"] == labels.GOOD
    assert row["colour"] == "green"
    conditions = row["conditions"]
    assert conditions["1_enough_data"]["pass"] is True
    assert conditions["2_skill_above_zero"]["pass"] is True
    assert conditions["3_range_narrow_enough"]["pass"] is True
    assert conditions["4_small_honesty_error"]["pass"] is True
    assert row["shows"]["percentage_rounded_to_10"] is True
    assert "wording" not in row


def test_a_range_that_includes_zero_drops_to_amber_with_the_fixed_words():
    """SPEC 6.2 condition 2 and 6.5. The sentence is not to be improved."""
    row = label_of(bss=0.03, bss_lo=-0.02, bss_hi=0.08, bss_halfwidth=0.05)
    assert row["label"] == labels.ROUGH
    assert row["colour"] == "amber"
    assert row["conditions"]["2_skill_above_zero"]["pass"] is False
    assert row["wording"] == labels.LUCK
    assert "could be luck" in row["wording"]
    assert row["shows"]["percentage_rounded_to_10"] is False


def test_skill_of_exactly_zero_is_not_above_zero():
    """SPEC 5.11 rule 16. Condition 2 is strict."""
    assert label_of(bss_lo=0.0)["label"] == labels.ROUGH
    assert label_of(bss_lo=1e-9)["label"] == labels.GOOD


def test_a_range_too_wide_to_be_knowledge_drops_to_amber():
    """SPEC 6.2 condition 3. Plus or minus 0.4 above 0 is not knowledge."""
    wide = label_of(bss_lo=0.05, bss_hi=0.85, bss_halfwidth=0.40)
    assert wide["label"] == labels.ROUGH
    assert wide["conditions"]["3_range_narrow_enough"]["pass"] is False
    # Exactly 0.10 passes: condition 3 is "0.10 or less".
    assert label_of(bss_halfwidth=0.10)["label"] == labels.GOOD
    assert label_of(bss_halfwidth=0.1000001)["label"] == labels.ROUGH


def test_a_bucket_that_misses_by_more_than_a_tenth_drops_to_amber():
    """SPEC 6.4. "About 40%" that happens 60% of the time is not that."""
    row = label_of(buckets=[bucket(26, 30, mean=0.55, observed=0.70)])
    assert row["label"] == labels.ROUGH
    error = row["conditions"]["4_small_honesty_error"]
    assert error["pass"] is False
    assert error["worst_error"] == pytest.approx(0.15)
    # Exactly 0.10 passes; a hair more does not.
    assert label_of(buckets=[bucket(26, 30, mean=0.5, observed=0.6)])[
        "label"] == labels.GOOD


def test_an_uncounted_bucket_is_ignored_by_the_test_and_still_drawn():
    """SPEC 6.4. Set aside for the test, visible on the diagram."""
    row = label_of(buckets=[
        bucket(26, 30, mean=0.55, observed=0.60),
        bucket(31, 35, cases=40, dates=3, mean=0.65, observed=0.99),
    ])
    assert row["label"] == labels.GOOD, "the thin bucket does not decide"
    error = row["conditions"]["4_small_honesty_error"]
    assert error["counted_buckets"] == 1
    assert error["drawn_buckets"] == 2
    assert [p["k_from"] for p in row["phrases"]] == [26]


def test_a_group_with_no_counted_bucket_cannot_be_green():
    """SPEC 5.11 rule 20. A rule true of no evidence has not been tested."""
    thin = [bucket(26, 30, cases=99, dates=40),
            bucket(31, 35, cases=400, dates=9)]
    row = label_of(buckets=thin)
    assert row["label"] == labels.ROUGH
    error = row["conditions"]["4_small_honesty_error"]
    assert error["counted_buckets"] == 0
    assert error["worst_error"] is None
    assert error["pass"] is False
    assert row["phrases"] == []


# -------------------------------------------------------- not enough data

def test_each_of_the_three_data_rules_alone_makes_it_grey():
    """SPEC 6.3. All three must hold, and the third is the one that binds."""
    assert label_of(cases=999)["label"] == labels.THIN
    assert label_of(dates=29)["label"] == labels.THIN
    assert label_of(event_dates=19)["label"] == labels.THIN
    # And the figures themselves, so a change in SPEC has to change this.
    assert (labels.MIN_CASES, labels.MIN_DATES, labels.MIN_EVENT_DATES) == (
        1000, 30, 20)
    assert label_of(cases=1000, dates=30, event_dates=20)["label"] == (
        labels.GOOD)


def test_a_group_with_eighty_thousand_cases_and_three_wet_days_is_grey():
    """SPEC 6.3. The 20-dates rule stops a label resting on one freak week."""
    row = label_of(cases=80_000, dates=177, event_dates=3)
    assert row["label"] == labels.THIN
    assert row["conditions"]["1_enough_data"]["event_dates"]["pass"] is False
    assert row["conditions"]["1_enough_data"]["cases"]["pass"] is True


def test_no_skill_number_at_all_is_grey_not_amber():
    """SPEC 5.11 rules 8 and 15."""
    none = label_of(bss=None, bss_lo=None, bss_hi=None, bss_halfwidth=None,
                    resamples_discarded=RESAMPLES)
    assert none["label"] == labels.THIN
    assert none["skill_known"] is False
    # One per cent of resamples discarded is allowed; more is not.
    assert label_of(resamples_discarded=10)["label"] == labels.GOOD
    assert label_of(resamples_discarded=11)["label"] == labels.THIN


# ------------------------------------------------------------- what shows

def test_what_each_label_is_allowed_to_print():
    """SPEC 6.7. A percentage is earned by the record, never printed by
    default, and the two numbers on an amber label are different things."""
    assert labels.shows_for(labels.GOOD) == {
        "percentage_rounded_to_10": True, "count_of_51": True,
        "came_true_phrase": False}
    assert labels.shows_for(labels.ROUGH) == {
        "percentage_rounded_to_10": False, "count_of_51": True,
        "came_true_phrase": True}
    assert labels.shows_for(labels.THIN) == {
        "percentage_rounded_to_10": False, "count_of_51": True,
        "came_true_phrase": False}
    for label, colour in (("Good track record", "green"),
                          ("Treat as a rough guide", "amber"),
                          ("Not enough past data", "grey")):
        assert labels.COLOURS[label] == colour


def test_the_came_true_phrase_is_the_bucket_rounded_to_a_whole_ten():
    """SPEC 6.7. "came true about 2 times in 10"."""
    row = label_of(buckets=[bucket(16, 20, mean=0.35, observed=0.24)])
    assert row["phrases"][0]["times_in_10"] == 2
    assert row["phrases"][0]["observed"] == 0.24


# ------------------------------------------------------- the whole record

def whole(groups) -> dict:
    return labels.build({
        "regions": ["Region A", "Region B"],
        "leads": [1, 2],
        "bootstrap": {"resamples": RESAMPLES},
        "bucket_floor": {"cases": 100, "dates": 10},
        "wording": "agreed with the satellite estimate",
        "crps_compared": False,
        "not_computed": {"corp": "not computed",
                          "random_error": "not computed"},
        "crps": {"baseline": "the 30 days before the run", "rows": [],
                 "disagreement": []},
        "frequency_check": {"wording": "", "ratio": "", "rows": []},
        "groups_scored": groups,
    })


def spread(region, lead, threshold, variant="all51", **kwargs):
    return group(region=region, lead_day=lead, threshold_mm=threshold,
                 variant=variant, **kwargs)


def test_every_group_appears_even_when_nothing_was_scored():
    """SPEC 6.9 rule 1. A gap reads "Not enough past data", not nothing."""
    record = whole([spread("Region A", 1, 10.0)])
    assert len(record["labels"]) == 2 * 2 * 3, "2 regions x 2 leads x 3 mm"
    found = {(r["region"], r["lead_day"], r["threshold_mm"]): r["label"]
             for r in record["labels"]}
    assert found[("Region A", 1, 10.0)] == labels.GOOD
    assert found[("Region B", 2, 50.0)] == labels.THIN
    assert len(found) == len(record["labels"])
    assert record["counts"][labels.THIN] == 11


def test_the_period_is_on_every_single_label():
    """SPEC 5.11, the period on everything."""
    record = whole([spread("Region A", 1, 10.0)])
    assert record["period"] == PERIOD
    for row in record["labels"]:
        assert row["period"] == PERIOD
    assert "monsoon" in PERIOD and "winter" in PERIOD


def test_a_label_that_changes_at_eight_or_twelve_millimetres_is_disclosed():
    """SPEC 5.6. A result that only holds at exactly 10 mm is not a result."""
    record = whole([
        spread("Region A", 1, 10.0),
        spread("Region A", 1, 8.0),
        spread("Region A", 1, 12.0, bss_lo=-0.1, bss_hi=0.2,
               bss_halfwidth=0.15),
    ])
    row = [r for r in record["labels"]
           if r["region"] == "Region A" and r["lead_day"] == 1
           and r["threshold_mm"] == 10.0][0]
    assert row["also"] == {"8 mm": labels.GOOD, "12 mm": labels.ROUGH}
    assert row["disclose"] == {"12 mm": labels.ROUGH}
    assert record["sensitivity_changes"][0]["differs"] == {
        "12 mm": labels.ROUGH}


def test_a_label_that_changes_without_the_control_or_the_coast_is_disclosed():
    """SPEC 2.1 and 5.11 rules 6 and 22."""
    record = whole([
        spread("Region A", 1, 10.0),
        spread("Region A", 1, 10.0, variant="all50", event_dates=5),
        spread("Region A", 1, 10.0, variant="inland51"),
    ])
    row = [r for r in record["labels"] if r["threshold_mm"] == 10.0
           and r["region"] == "Region A" and r["lead_day"] == 1][0]
    assert row["also"]["inland only"] == labels.GOOD
    assert row["disclose"] == {"50 members": labels.THIN}


def test_the_rules_that_decided_the_labels_are_written_beside_them():
    """SPEC 6.8. Nobody can move a threshold after seeing the answer."""
    record = whole([spread("Region A", 1, 10.0)])
    assert record["rules"] == {
        "min_cases": 1000, "min_dates": 30, "min_event_dates": 20,
        "max_halfwidth": 0.10, "max_bucket_error": 0.10,
        "bucket_floor": {"cases": 100, "dates": 10}}
    assert record["crps_compared"] is False
    assert record["luck_wording"] == labels.LUCK

# -------------------------------------------------------- the site file

def built(groups=None, crps=True) -> tuple:
    """A whole record and its site file, from one made-up group."""
    groups = groups or [spread("Region A", 1, 10.0)]
    result = {
        "regions": ["Region A", "Region B"],
        "leads": [1, 2],
        "bootstrap": {"resamples": RESAMPLES},
        "bucket_floor": {"cases": 100, "dates": 10},
        "wording": "agreed with the satellite estimate",
        "crps_compared": crps,
        "not_computed": {"corp": "not computed",
                         "random_error": "not computed"},
        "crps": {
            "baseline": "the 30 days before the run",
            "rows": [{"variant": "all51", "region": "Region A",
                      "lead_day": 1, "crpss_fair": 0.3, "crpss_lo": 0.2,
                      "crpss_hi": 0.4}],
            "disagreement": [{"region": "Region A", "lead_day": 1,
                              "threshold_mm": 10.0,
                              "brier_above_zero": False,
                              "crps_above_zero": True, "disagrees": True}],
        },
        "frequency_check": {
            "wording": "the model says this much rain more often than the "
                       "satellite sees it",
            "ratio": "mean forecast over observed frequency",
            "rows": [{"variant": "all51", "region": "Region A",
                      "lead_day": 1, "threshold_mm": 10.0, "cases": 10,
                      "mean_forecast": 0.6, "observed": 0.5, "ratio": 1.2,
                      "wording": "the model says this much rain more often "
                                 "than the satellite sees it"},
                     {"variant": "all51", "region": "All India",
                      "lead_day": 1, "threshold_mm": 10.0, "cases": 20,
                      "mean_forecast": 0.55, "observed": 0.5, "ratio": 1.1,
                      "wording": "the model says this much rain more often "
                                 "than the satellite sees it"}],
        },
        "groups_scored": groups,
    }
    record = labels.build(result)
    return result, record, labels.site_summary(result, record)


def test_the_site_file_is_small_enough_to_send():
    """A page that waits for a megabyte is a page nobody reads."""
    _, _, site = built()
    size = len(json.dumps(site, separators=(",", ":")).encode())
    assert size < labels.SITE_FILE_LIMIT
    assert labels.SITE_FILE_LIMIT == 100_000
    assert labels.SITE_FILE.name == "site_summary.json"


def test_the_site_file_carries_the_label_and_why_and_nothing_spare():
    """Everything a page needs to show a label honestly."""
    _, record, site = built()
    assert len(site["groups"]) == len(record["labels"])
    row = [g for g in site["groups"] if g["region"] == "Region A"
           and g["lead_day"] == 1 and g["threshold_mm"] == 10.0][0]
    assert row["label"] == labels.GOOD and row["colour"] == "green"
    for name in ("enough_data", "skill_above_zero", "range_narrow_enough",
                 "small_honesty_error"):
        assert name in row["conditions"]
    assert row["conditions"]["enough_data"]["event_dates"] == 120
    assert row["conditions"]["small_honesty_error"]["worst_error"] is not None
    assert (row["bss"], row["bss_lo"], row["bss_hi"]) == (0.28, 0.21, 0.35)
    assert row["buckets"] and all(
        set(b) == {"k_from", "k_to", "cases", "observed", "times_in_10"}
        for b in row["buckets"])
    assert row["frequency_check"]["ratio"] == 1.2
    # The period is stored once, for a file that goes down a wire.
    assert site["period"] == PERIOD and site["period_on_every_label"] is True
    assert "period" not in row
    assert site["shows_by_label"][labels.GOOD]["percentage_rounded_to_10"]
    assert site["frequency_check"]["all_india"][0]["ratio"] == 1.1


def test_the_site_file_only_carries_counted_buckets():
    """SPEC 6.4 and 6.7. The floor that governs the test governs the page."""
    thin = group(region="Region A", lead_day=1, threshold_mm=10.0,
                 buckets=[bucket(26, 30, mean=0.55, observed=0.60),
                          bucket(31, 35, cases=20, dates=2)])
    _, _, site = built([thin])
    row = [g for g in site["groups"] if g["lead_day"] == 1
           and g["region"] == "Region A"
           and g["threshold_mm"] == 10.0][0]
    assert [b["k_from"] for b in row["buckets"]] == [26]


def test_neither_the_frequency_check_nor_crps_can_move_a_label():
    """Both are reported beside the label. Neither decides it."""
    result, record, _ = built()
    before = {(r["region"], r["lead_day"], r["threshold_mm"]): r["label"]
              for r in record["labels"]}
    for row in record["labels"]:
        assert "frequency_check" in row and "crps" in row

    bare = dict(result)
    bare["crps_compared"] = False
    bare["frequency_check"] = {"wording": "", "ratio": "", "rows": []}
    after = {(r["region"], r["lead_day"], r["threshold_mm"]): r["label"]
             for r in labels.build(bare)["labels"]}
    assert before == after


def test_a_disagreement_with_crps_is_disclosed_beside_the_label():
    """SPEC 6.1 and 6.9 rule 3. Brier still decides."""
    _, record, site = built()
    row = [r for r in record["labels"] if r["region"] == "Region A"
           and r["lead_day"] == 1 and r["threshold_mm"] == 10.0][0]
    assert row["crps"]["disagrees"] is True
    assert row["crps"]["note"] == labels.CRPS_DISAGREES
    assert "follows the Brier score" in labels.CRPS_DISAGREES
    assert row["label"] == labels.GOOD, "the label is Brier's, not CRPS's"
    seen = [g for g in site["groups"] if g["region"] == "Region A"
            and g["lead_day"] == 1 and g["threshold_mm"] == 10.0][0]
    assert seen["crps_disagrees"] is True
    assert site["crps_disagrees_wording"] == labels.CRPS_DISAGREES
    assert site["crps"][0]["crpss_fair"] == 0.3


def test_when_crps_was_not_computed_the_site_file_says_nothing_of_it():
    """SPEC 6.9 rule 2."""
    _, record, site = built(crps=False)
    assert site["crps_compared"] is False and site["crps"] == []
    assert all(r["crps"] is None for r in record["labels"])
    assert all(g["crps_disagrees"] is False for g in site["groups"])
    assert site["not_computed"] == ["corp", "random_error"]
