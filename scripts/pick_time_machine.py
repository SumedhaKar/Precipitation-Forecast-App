"""Choose the Time Machine's seven days. SPEC 11.38.

The rule is in SPEC 11.38 and was committed before this file existed. Nothing
here is chosen by hand: the script measures every eligible day, ranks three
lists, takes two from each, and draws one at random from what is left.

    python -m scripts.pick_time_machine            measure and print
    python -m scripts.pick_time_machine --json x   and write the scores there

The two halves are kept apart on purpose. `measure` reads Pile A and Pile B
and is the only part that needs the archive; `select` is a pure function of
the score table, so the rule itself can be checked, and checked against a
different seed, on a machine with no data at all.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
from pathlib import Path

import numpy as np

from pipeline import config as cfg
from pipeline import verify
from pipeline.ecmwf_process import daily_totals

# SPEC 11.38. The one threshold this page shows.
THRESHOLD_MM = 10.0

# The two error lists look at the one-day-ahead forecast, because that is the
# one a reader would have acted on.
ERROR_LEAD = 1

# "The model said rain" and "the model said next to nothing", as counts out
# of 51. Both are written here and nowhere else.
LOUD_COUNT = 26      # 26 or more runs reaching 10 mm
QUIET_COUNT = 5      # 5 or fewer
DRIZZLE_MM = 1.0     # the satellite estimate a false alarm has to be under

# SPEC 11.38. Two days from one monsoon surge are one event seen twice.
GAP_DAYS = 7

# SPEC 5.11 rule 12's date, reused: a seed fixed before any score existed.
SEED = 20261112

# In the order they are taken.
LISTS = (("wettest", 2), ("false_alarm", 2), ("surprise", 2))

# What the page says about each. The forbidden words of 11.20 hold here, so
# the rainiest days are named by what was counted rather than by a judgement.
WHY = {
    "wettest": "picked as a day with the most 10 mm squares",
    "false_alarm": "picked as a false alarm",
    "surprise": "picked as a surprise",
    "random": "picked at random",
}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

LONG_MONTHS = ("January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November",
               "December")


def as_date(stamp: str) -> dt.date:
    return dt.datetime.strptime(stamp, "%Y%m%d").date()


def as_stamp(day: dt.date) -> str:
    return day.strftime("%Y%m%d")


def run_for(observed: str, lead: int) -> str:
    """The 00 UTC run whose lead day `lead` is this observed day. SPEC 3.7."""
    return as_stamp(as_date(observed) - dt.timedelta(days=lead))


def window_text(observed: str) -> str:
    """"5:30 am 22 Jul to 5:30 am 23 Jul IST", the day the estimate covers.

    IMERG's day is 00 UTC to 00 UTC, which in India is 5:30 am to 5:30 am.
    """
    first = as_date(observed)
    second = first + dt.timedelta(days=1)
    return (f"5:30 am {first.day} {MONTHS[first.month - 1]} to "
            f"5:30 am {second.day} {MONTHS[second.month - 1]} IST")


def day_text(observed: str) -> str:
    """"22 July 2026"."""
    day = as_date(observed)
    return f"{day.day} {LONG_MONTHS[day.month - 1]} {day.year}"


# ------------------------------------------------------------- the measuring

def eligible(runs: set[str], observed: set[str], leads: int = 5) -> list[str]:
    """Observed days with all five runs behind them and an estimate of their own.

    SPEC 11.38. The window is not a choice: it is what the archive allows.
    """
    out = []
    for stamp in sorted(observed):
        if all(run_for(stamp, lead) in runs for lead in range(1, leads + 1)):
            out.append(stamp)
    return out


def counts_for(run: str, lead: int, india: np.ndarray,
               threshold: float = THRESHOLD_MM) -> np.ndarray:
    """How many of the 51 runs reach `threshold` on `lead`, India squares only.

    The same recomputation verification does (5): the stored accumulations
    differenced by `ecmwf_process.daily_totals`, and the same "greater than
    or equal to" rule as everywhere else on this site.
    """
    totals = daily_totals(verify.load_forecast(run))
    reached = (totals[lead - 1] >= threshold).sum(axis=0).astype(np.int16)
    return reached[india]


def measure(report=print) -> dict:
    """Score every eligible day. Reads Pile A and Pile B.

    Returns the score table `select` takes, and the mask it was measured on.
    """
    mask = verify.load_mask()
    india = mask["india"]
    runs = set(verify.run_dates())
    observed = verify.obs_dates()
    days = eligible(runs, observed)
    if not days:
        raise SystemExit("no day has five runs behind it and an estimate")
    report(f"  {len(days)} eligible days, {days[0]} to {days[-1]}")

    # The same remap and the same 90% rule as verification, from verification
    # itself: a square under 0.90 complete is NaN here, and is counted in
    # nothing at all.
    rain = verify.read_observations(mask, observed)

    rows = []
    for stamp in days:
        here = rain[stamp]
        valid = np.isfinite(here)
        first = counts_for(run_for(stamp, ERROR_LEAD), ERROR_LEAD, india)
        rows.append({
            "date": stamp,
            "squares_with_a_value": int(valid.sum()),
            "wettest": int((valid & (here >= THRESHOLD_MM)).sum()),
            "false_alarm": int((valid & (first >= LOUD_COUNT)
                                & (here < DRIZZLE_MM)).sum()),
            "surprise": int((valid & (first <= QUIET_COUNT)
                             & (here >= THRESHOLD_MM)).sum()),
        })
    return {"eligible": rows, "first": days[0], "last": days[-1]}


# ------------------------------------------------------------ the choosing

def select(rows: list[dict], seed: int = SEED, gap: int = GAP_DAYS,
           lists=LISTS) -> list[dict]:
    """The seven days, from the score table alone. SPEC 11.38.

    Pure: no file, no clock, no archive. The lists are taken in order, the
    highest score wins, a tie goes to the earlier date, and a day that is
    already taken or within `gap` days of one that is gives way to the next
    on its own list.
    """
    taken: list[dt.date] = []
    chosen: list[dict] = []
    used: set[str] = set()

    def allowed(stamp: str) -> bool:
        if stamp in used:
            return False
        day = as_date(stamp)
        return all(abs((day - other).days) >= gap for other in taken)

    def keep(stamp: str, reason: str, score) -> None:
        used.add(stamp)
        taken.append(as_date(stamp))
        chosen.append({"date": stamp, "reason": reason, "score": score,
                       "why": WHY[reason]})

    for reason, how_many in lists:
        ranked = sorted(rows, key=lambda row: (-row[reason], row["date"]))
        got = 0
        for row in ranked:
            if got == how_many:
                break
            if not allowed(row["date"]):
                continue
            keep(row["date"], reason, int(row[reason]))
            got += 1
        if got < how_many:
            raise SystemExit(
                f"only {got} of {how_many} days could be taken for {reason}")

    left = sorted(row["date"] for row in rows if allowed(row["date"]))
    if not left:
        raise SystemExit("no eligible day is left for the random one")
    keep(random.Random(seed).choice(left), "random", None)
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path,
                        help="write the score table and the choice here")
    parser.add_argument("--seed", type=int, default=SEED,
                        help="another seed, to show the choice moves")
    args = parser.parse_args()

    table = measure()
    chosen = select(table["eligible"], seed=args.seed)
    for row in chosen:
        score = "-" if row["score"] is None else row["score"]
        print(f"  {row['date']}  {row['reason']:<12} {score:>6}  "
              f"{day_text(row['date'])}")
    if args.json:
        args.json.write_text(json.dumps(
            {"seed": args.seed, "chosen": chosen, **table}, indent=1),
            encoding="utf-8")
        print(f"  wrote {args.json}")


if __name__ == "__main__":
    main()
