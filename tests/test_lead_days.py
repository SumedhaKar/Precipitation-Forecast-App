"""Lead days, their steps, and the IST day labels (SPEC 1.2 and 1.3).

The label is the one piece of text a reader sees most often, and it is the
easiest thing to get wrong by half a day. "5:30 am Thu to 5:30 am Fri" is not
Thursday.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                      # noqa: E402
from pipeline.run_live import (                         # noqa: E402
    IST,
    LiveRunError,
    day_label,
    day_records,
    lead_day_steps,
    lead_days,
    window_ist,
    window_utc,
)


def test_there_are_five_lead_days():
    assert lead_days() == (1, 2, 3, 4, 5)
    assert cfg.N_DAYS == 5


def test_lead_day_n_is_steps_24n_to_24n_plus_24():
    assert lead_day_steps(1) == (24, 48)
    assert lead_day_steps(2) == (48, 72)
    assert lead_day_steps(3) == (72, 96)
    assert lead_day_steps(4) == (96, 120)
    assert lead_day_steps(5) == (120, 144)


def test_every_lead_day_uses_two_downloaded_steps():
    for lead in lead_days():
        for step in lead_day_steps(lead):
            assert step in cfg.STEPS


def test_the_zero_to_24_window_is_never_a_lead_day():
    """SPEC 1.3: day 1 is tomorrow, never today."""
    for lead in lead_days():
        assert lead_day_steps(lead)[0] >= 24


def test_lead_day_out_of_range_is_refused():
    for bad in (0, -1, 6, 1.0, True, "1"):
        with pytest.raises(LiveRunError):
            lead_day_steps(bad)


def test_the_window_is_00_utc_to_00_utc():
    start, end = window_utc("20261112", 1)
    assert start == dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc)
    assert end == dt.datetime(2026, 11, 14, tzinfo=dt.timezone.utc)
    assert end - start == dt.timedelta(days=1)


def test_the_window_in_ist_starts_at_0530():
    start, end = window_ist("20261112", 1)
    assert (start.hour, start.minute) == (5, 30)
    assert (end.hour, end.minute) == (5, 30)
    assert start.utcoffset() == dt.timedelta(hours=5, minutes=30)


def test_lead_day_5_is_five_days_after_the_run():
    start, _ = window_utc("20261112", 5)
    assert start.date() == dt.date(2026, 11, 17)


def test_the_label_is_exactly_the_spec_wording():
    assert day_label("20261112", 1) == (
        "5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov")


def test_the_label_crosses_a_month_end():
    # 30 November 2026 run, lead day 1 lands wholly in December.
    assert day_label("20261130", 1) == (
        "5:30 am Tue 1 Dec to 5:30 am Wed 2 Dec")
    # and a run whose window straddles the month boundary
    assert day_label("20261130", 0 + 1).startswith("5:30 am Tue 1 Dec")
    assert day_label("20261129", 1) == (
        "5:30 am Mon 30 Nov to 5:30 am Tue 1 Dec")


def test_the_label_crosses_a_year_end():
    assert day_label("20261230", 2) == (
        "5:30 am Fri 1 Jan to 5:30 am Sat 2 Jan")


def test_the_label_never_prints_a_bare_date():
    """SPEC 1.2 forbids "Thursday" on its own for a forecast day."""
    label = day_label("20261112", 3)
    assert "5:30 am" in label
    assert " to " in label
    assert label.count("5:30 am") == 2


def test_day_records_cover_all_five_days_in_order():
    records = day_records("20261112")
    assert [r["lead_day"] for r in records] == [1, 2, 3, 4, 5]
    assert records[0]["steps"] == [24, 48]
    assert records[-1]["steps"] == [120, 144]
    assert records[0]["label"] == "5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov"
    # consecutive windows meet exactly, no gap and no overlap
    for a, b in zip(records, records[1:]):
        assert a["to_utc"] == b["from_utc"]
        assert a["to_ist"] == b["from_ist"]


def test_ist_is_a_fixed_offset_with_no_daylight_saving():
    for month in range(1, 13):
        when = dt.datetime(2026, month, 15, tzinfo=IST)
        assert when.utcoffset() == dt.timedelta(hours=5, minutes=30)
