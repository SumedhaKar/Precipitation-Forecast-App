"""Run selection (SPEC 4.6).

No network and no disk: every case is a made-up listing. The three rules
being tested are the ones that decide whether a wrong or a stale forecast can
ever reach the site.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                      # noqa: E402
from pipeline.run_live import (                         # noqa: E402
    LiveRunError,
    RunOption,
    parse_run_id,
    run_id_for,
    select_run,
)


def listing(*rows):
    return [RunOption(run_id, complete) for run_id, complete in rows]


# --------------------------------------------------------------- the happy path

def test_the_newest_complete_run_is_chosen():
    chosen, reason = select_run(listing(
        ("20261110T00Z", True),
        ("20261111T00Z", True),
        ("20261112T00Z", True),
    ))
    assert chosen == "20261112T00Z"
    assert "newest complete" in reason


def test_order_in_the_listing_does_not_matter():
    rows = (("20261111T00Z", True), ("20261112T00Z", True),
            ("20261110T00Z", True))
    assert select_run(listing(*rows))[0] == "20261112T00Z"
    assert select_run(listing(*reversed(rows)))[0] == "20261112T00Z"


# ------------------------------------------------------- only 00 UTC runs

def test_runs_at_other_hours_are_ignored():
    chosen, _ = select_run(listing(
        ("20261112T06Z", True),
        ("20261112T12Z", True),
        ("20261111T00Z", True),
    ))
    assert chosen == "20261111T00Z"


def test_a_listing_with_no_00_utc_run_builds_nothing():
    chosen, reason = select_run(listing(
        ("20261112T06Z", True), ("20261112T18Z", True)))
    assert chosen is None
    assert "no 00 UTC run" in reason


def test_a_06z_run_cannot_win_even_when_it_is_the_newest():
    chosen, _ = select_run(listing(
        ("20261113T06Z", True), ("20261112T00Z", True)))
    assert chosen == "20261112T00Z"


def test_malformed_ids_are_ignored_not_crashed_on():
    chosen, _ = select_run(listing(
        ("not-a-run", True), ("20261112", True), ("2026111200", True),
        ("20261112T00Z", True)))
    assert chosen == "20261112T00Z"


# ------------------------------------------- an incomplete run is never used

def test_an_incomplete_newest_run_falls_back_to_the_previous_one():
    chosen, reason = select_run(listing(
        ("20261112T00Z", False),
        ("20261111T00Z", True),
    ))
    assert chosen == "20261111T00Z"
    assert "20261112T00Z" in reason and "incomplete" in reason


def test_several_incomplete_runs_in_a_row_still_fall_back():
    chosen, _ = select_run(listing(
        ("20261112T00Z", False),
        ("20261111T00Z", False),
        ("20261110T00Z", True),
    ))
    assert chosen == "20261110T00Z"


def test_nothing_is_built_when_every_run_is_incomplete():
    chosen, reason = select_run(listing(
        ("20261112T00Z", False), ("20261111T00Z", False)))
    assert chosen is None
    assert "incomplete" in reason


def test_an_incomplete_run_is_never_chosen_even_with_nothing_published():
    for complete in (False,):
        chosen, _ = select_run(listing(("20261112T00Z", complete)))
        assert chosen is None


# --------------------------------------- an older run never replaces a newer

def test_an_older_complete_run_does_not_replace_a_newer_published_one():
    chosen, reason = select_run(
        listing(("20261111T00Z", True)), published="20261112T00Z")
    assert chosen is None
    assert "older than the run already built" in reason


def test_a_newer_run_does_replace_an_older_published_one():
    chosen, _ = select_run(
        listing(("20261112T00Z", True)), published="20261111T00Z")
    assert chosen == "20261112T00Z"


def test_an_incomplete_newer_run_does_not_unseat_the_published_one():
    chosen, reason = select_run(listing(
        ("20261113T00Z", False),
        ("20261112T00Z", True),
    ), published="20261112T00Z")
    assert chosen is None
    assert "already been built" in reason


# ----------------------------------------- the same run is never republished

def test_the_same_run_is_never_built_twice():
    chosen, reason = select_run(
        listing(("20261112T00Z", True)), published="20261112T00Z")
    assert chosen is None
    assert "already been built" in reason


def test_the_published_run_id_must_itself_be_a_run_id():
    with pytest.raises(LiveRunError):
        select_run(listing(("20261112T00Z", True)), published="rubbish")


# ------------------------------------------------------------- the id itself

def test_run_ids_round_trip():
    assert run_id_for("20261112") == "20261112T00Z"
    assert run_id_for("20261112", 12) == "20261112T12Z"
    assert parse_run_id("20261112T00Z") == ("20261112", 0)
    assert parse_run_id("20261112T06Z") == ("20261112", 6)


def test_run_ids_sort_chronologically_as_text():
    ids = ["20261112T00Z", "20251231T00Z", "20260101T00Z", "20261112T06Z"]
    assert sorted(ids) == ["20251231T00Z", "20260101T00Z",
                           "20261112T00Z", "20261112T06Z"]


def test_bad_run_ids_are_refused():
    for bad in ("", "20261112", "20261112T00", "2026111200Z", "20261332T00Z",
                "20261112Z00T", "20261112T0Z"):
        with pytest.raises(LiveRunError):
            parse_run_id(bad)


def test_the_run_hour_comes_from_config():
    assert cfg.RUN_TIME == 0
    chosen, _ = select_run(listing((run_id_for("20261112"), True)))
    assert chosen == f"20261112T{cfg.RUN_TIME:02d}Z"


# --------------------------------------------- listings in dict form also work

def test_a_listing_of_plain_dicts_is_accepted():
    chosen, _ = select_run([
        {"run_id": "20261112T00Z", "complete": True},
        {"run_id": "20261111T00Z", "complete": True},
    ])
    assert chosen == "20261112T00Z"


def test_an_empty_listing_builds_nothing():
    chosen, reason = select_run([])
    assert chosen is None
    assert "no 00 UTC run" in reason
