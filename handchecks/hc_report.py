"""HC-REPORT: the report card's own Brier score, worked out again by hand.

SPEC 5.1, 5.2 and 5.11. The report card says that in one region, at one lead
day and one threshold, the forecasts scored a certain Brier score against the
satellite. This check works that number out again from the stored arrays,
importing nothing from `pipeline/`, and the two have to agree.

What is redone here, from scratch:

  * which run dates and which squares make a case, and the pairing of a run
    date and a lead day with the IMERG day it is a forecast for;
  * the daily total, as the difference of two stored accumulations, with the
    negative-difference rule of SPEC 3.6 written out again;
  * the count of members at or above the threshold, and the forecast as that
    count over 51;
  * the observed outcome, 1 when the satellite's daily total for that square
    reaches the threshold and 0 when it does not;
  * the squared error of every case, and the mean of them, which is the
    Brier score the report card prints.

Ten of those cases are written out in full, so a reader can redo the whole
chain for one square and one day on paper. **They are chosen from the
forecast side alone**: ten counts spread evenly from 0 of 51 to 51 of 51, and
for each the first case in date and then square order that says it. No
observation is looked at while they are being chosen, so there is no way to
pick ten cases that flatter the score.

**The region is chosen by rule, not picked**: the one whose published groups
hold the most cases, and the most events, of the 60 on the report card. All
15 of its groups are redone, 5 lead days by 3 thresholds, because the stored
arrays are read for the first one anyway.

What is taken rather than redone, and is therefore not what this checks: the
remapped IMERG field (HC5, HC9 and HC-GHATS), the stored ECMWF
accumulations (HC1, HC2, HC3), the India mask and the IMD regions, both read
from the committed `config/` files.

The other half of this check is two unit tests, run here and reported with
their outcome, because they say what no recomputation of a real group can:
that a perfect forecast scores 0, and that forecasting the usual rain for the
place and the month, every day, scores no skill at all. Those are the two
ends the report card's numbers sit between.

    python handchecks/hc_report.py
    python handchecks/hc_report.py --region "Central India" --sabotage
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "handchecks" / "results"
MEMBERS = 51
LEADS = (1, 2, 3, 4, 5)
THRESHOLDS = (1.0, 10.0, 50.0)
STEPS = (24, 48, 72, 96, 120, 144)
# SPEC 3.6: a negative daily difference inside this many mm is packing noise
# and becomes 0; anything worse stops the check. The real tolerance is
# derived from each file's own packing quantum; this is the loosest it can
# be, for 12-bit packing, as HC9 uses.
TOLERANCE = -0.5
EXAMPLES = 10

# The two unit tests this check reports, and what each one says.
TESTS = (
    ("test_a_case_is_scored_against_the_day_its_forecast_was_for",
     "a region that forecast both days perfectly scores a Brier score of 0 "
     "and a skill of exactly 1"),
    ("test_the_usual_rain_every_day_is_a_forecast_with_no_skill_at_all",
     "forecasting the reference itself, the usual rain for that place and "
     "month, scores a skill of exactly 0"),
)

# Sabotages of `pipeline/verify.py`, to show the two tests bite.
SABOTAGE = (
    ("the forecast shared out over one member too few",
     "        forecast = k[keep] / self.members",
     "        forecast = k[keep] / (self.members - 1)"),
    ("the reference rate rounded to two decimals",
     "        rbs = (here - truth) ** 2",
     "        rbs = (here.round(2) - truth) ** 2"),
)


def grid() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The India mask and the grid, from the committed files."""
    mask = json.loads((ROOT / "config" / "india_mask.json")
                      .read_text(encoding="utf-8"))
    india = np.array([[c == "1" for c in row] for row in mask["india_rows"]])
    return india, np.array(mask["lat"]), np.array(mask["lon"])


def region_squares(region: str, india: np.ndarray) -> np.ndarray:
    """The India squares of one IMD region, as a mask of the whole grid."""
    regions = json.loads((ROOT / "config" / "regions.json")
                         .read_text(encoding="utf-8"))
    if region not in regions["regions"]:
        raise SystemExit(f"{region} is not one of {regions['regions']}")
    code = regions["regions"].index(region) + 1
    here = np.array([[int(c) == code for c in row]
                     for row in regions["region_rows"]])
    if here.shape != india.shape:
        raise SystemExit("the region grid is not the mask's grid")
    return here & india


def daily_totals(date: str) -> np.ndarray:
    """Every member's rain in each of the five days, by hand.

    Day d is the stored accumulation at the end of day d minus the one at its
    start, so day 1 is step 48 minus step 24.
    """
    with np.load(ROOT / "data" / "india" / "ecmwf" / f"{date}.npz") as box:
        tp = box["tp"].astype(np.float64)
        steps = [int(s) for s in box["steps"]]
        members = [int(m) for m in box["members"]]
    if tuple(steps) != STEPS:
        raise SystemExit(f"{date}: steps are {steps}, not {list(STEPS)}")
    if sorted(members) != list(range(MEMBERS)):
        raise SystemExit(f"{date}: members are not 0 to 50")
    out = np.empty((len(LEADS), MEMBERS) + tp.shape[2:], dtype=np.float64)
    for lead in LEADS:
        difference = tp[lead] - tp[lead - 1]
        worst = float(difference.min())
        if worst < TOLERANCE:
            raise SystemExit(f"{date} day {lead}: a daily difference of "
                             f"{worst} mm")
        out[lead - 1] = np.where(difference < 0.0, 0.0, difference)
    return out


def observed_for(date: str, lead: int) -> str:
    """SPEC 5.1: the run of date D, lead n, is a forecast for day D + n."""
    return (dt.date.fromisoformat(date)
            + dt.timedelta(days=lead)).strftime("%Y%m%d")


def published(region: str) -> dict:
    """The 15 groups of this region as `results/verification.json` has them."""
    result = json.loads((ROOT / "results" / "verification.json")
                        .read_text(encoding="utf-8"))
    out = {}
    for row in result["groups_scored"]:
        if row["variant"] == "all51" and row["region"] == region:
            out[(row["lead_day"], row["threshold_mm"])] = row
    return out


def busiest_region() -> str:
    """The region of the published group with the most cases, then events."""
    result = json.loads((ROOT / "results" / "verification.json")
                        .read_text(encoding="utf-8"))
    rows = [r for r in result["groups_scored"] if r["variant"] == "all51"]
    best = max(rows, key=lambda r: (r["cases"], r["events"]))
    return best["region"]


def example_targets() -> list[int]:
    """Ten counts spread evenly from none of 51 to all of 51."""
    return sorted({round(MEMBERS * m / (EXAMPLES - 1))
                   for m in range(EXAMPLES)})


def run_tests(names) -> list[tuple[str, str]]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header",
         "-p", "no:cacheprovider", "tests/test_verify.py",
         "-k", " or ".join(names)],
        capture_output=True, text=True, cwd=ROOT)
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    return [("passed" if done.returncode == 0 else "FAILED"), last]


def sabotage_tests() -> list[tuple[str, str, str]]:
    """Break `verify.py` one way at a time and see which test notices."""
    source = ROOT / "pipeline" / "verify.py"
    keep = source.read_bytes()
    text = keep.decode("utf-8")
    out = []
    try:
        for what, old, new in SABOTAGE:
            if old not in text:
                out.append((what, "NOT APPLIED",
                            "verify.py no longer has that line"))
                continue
            source.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            bitten = [name for name, _ in TESTS
                      if run_tests([name])[0] == "FAILED"]
            source.write_bytes(keep)
            out.append((what, "CAUGHT" if bitten else "missed",
                        "; ".join(n.replace("test_", "") for n in bitten)
                        or "neither test noticed"))
    finally:
        source.write_bytes(keep)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=None)
    ap.add_argument("--sabotage", action="store_true")
    args = ap.parse_args()

    india, lat, lon = grid()
    region = args.region or busiest_region()
    squares = region_squares(region, india)
    rows, cols = np.nonzero(squares)
    print(f"{region}: {squares.sum()} squares")

    runs = sorted(p.stem for p in
                  (ROOT / "data" / "india" / "ecmwf").glob("*.npz"))
    available = {p.stem for p in
                 (ROOT / "data" / "india" / "nasa").glob("*.npz")}
    if not runs:
        raise SystemExit("no stored ECMWF runs in data/india/ecmwf")

    shape = (len(LEADS), len(THRESHOLDS))
    cases = np.zeros(shape, dtype=np.int64)
    events = np.zeros(shape, dtype=np.int64)
    squared = np.zeros(shape, dtype=np.float64)
    missing_days = 0
    incomplete = 0

    wanted = example_targets()
    examples: dict[int, dict] = {}

    for at, date in enumerate(runs):
        totals = daily_totals(date)[:, :, squares]        # (day, member, sq)
        for li, lead in enumerate(LEADS):
            day = observed_for(date, lead)
            if day not in available:
                missing_days += 1
                continue
            with np.load(ROOT / "data" / "india" / "nasa"
                         / f"{day}.npz") as box:
                obs = box["rain"][squares].astype(np.float64)
            usable = np.isfinite(obs)
            incomplete += int((~usable).sum())
            for ti, threshold in enumerate(THRESHOLDS):
                k = (totals[li] >= threshold).sum(axis=0)
                forecast = k[usable] / MEMBERS
                truth = (obs[usable] >= threshold).astype(np.float64)
                cases[li, ti] += truth.size
                events[li, ti] += int(truth.sum())
                squared[li, ti] += float(((forecast - truth) ** 2).sum())

                # The ten worked examples, from the first group of the
                # table, and chosen on k alone.
                if li == 0 and ti == 0:
                    for target in wanted:
                        if target in examples:
                            continue
                        where = np.nonzero((k == target) & usable)[0]
                        if not where.size:
                            continue
                        sq = int(where[0])
                        examples[target] = {
                            "run": date, "lead": lead, "day": day,
                            "lat": float(lat[rows[sq]]),
                            "lon": float(lon[cols[sq]]),
                            "threshold": threshold, "k": int(k[sq]),
                            "obs_mm": float(obs[sq]),
                        }
        if (at + 1) % 50 == 0:
            print(f"  {at + 1}/{len(runs)} run dates")

    theirs = published(region)
    comparison = []
    worst = 0.0
    for li, lead in enumerate(LEADS):
        for ti, threshold in enumerate(THRESHOLDS):
            mine_bs = squared[li, ti] / cases[li, ti]
            mine_rate = events[li, ti] / cases[li, ti]
            row = theirs[(lead, threshold)]
            gap = abs(mine_bs - row["bs"])
            worst = max(worst, gap)
            comparison.append({
                "lead": lead, "threshold": threshold,
                "cases": int(cases[li, ti]), "their_cases": row["cases"],
                "events": int(events[li, ti]), "their_events": row["events"],
                "base_rate": mine_rate, "their_base_rate": row["base_rate"],
                "bs": mine_bs, "their_bs": row["bs"], "gap": gap,
            })

    tests = [(name, says, *run_tests([name])) for name, says in TESTS]
    sabotages = sabotage_tests() if args.sabotage else []

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "hc_report.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["hc-report", "the report card's Brier scores, redone by "
                    "hand, SPEC 5.2"])
        w.writerow(["region", region])
        w.writerow(["region_rule", "the region of the published group with "
                    "the most cases, then the most events"])
        w.writerow(["squares", int(squares.sum())])
        w.writerow(["run_dates", len(runs)])
        w.writerow(["members", MEMBERS])
        w.writerow(["lead_days_without_an_imerg_day", missing_days])
        w.writerow(["square_days_the_satellite_could_not_measure", incomplete])
        w.writerow(["published_file", "results/verification.json"])
        w.writerow(["largest_difference_in_the_brier_score",
                    f"{worst:.2e}"])
        w.writerow(["rounding", "the published values are written to six "
                    "decimals, so a difference under 5e-7 is the rounding "
                    "and nothing else"])
        w.writerow([])
        w.writerow(["lead_day", "threshold_mm", "cases", "published_cases",
                    "events", "published_events", "base_rate",
                    "published_base_rate", "brier_score",
                    "published_brier_score", "difference"])
        for row in comparison:
            w.writerow([row["lead"], f"{row['threshold']:g}", row["cases"],
                        row["their_cases"], row["events"],
                        row["their_events"], f"{row['base_rate']:.6f}",
                        row["their_base_rate"], f"{row['bs']:.9f}",
                        row["their_bs"], f"{row['gap']:.2e}"])
        w.writerow([])
        w.writerow(["ten cases, chosen by the count alone, from "
                    f"{region} day 1 at 1 mm"])
        w.writerow(["run_date", "lead_day", "imerg_day", "lat", "lon",
                    "members_at_or_over_1mm", "forecast_k_over_51",
                    "observed_mm", "observed_event", "squared_error"])
        for target in wanted:
            case = examples.get(target)
            if case is None:
                w.writerow(["", "", "", "", "", target,
                            "no case in the whole record says this", "", "",
                            ""])
                continue
            p = case["k"] / MEMBERS
            y = 1.0 if case["obs_mm"] >= case["threshold"] else 0.0
            w.writerow([case["run"], case["lead"], case["day"],
                        f"{case['lat']:.2f}", f"{case['lon']:.2f}",
                        case["k"], f"{p:.6f}", f"{case['obs_mm']:.2f}",
                        int(y), f"{(p - y) ** 2:.6f}"])
        w.writerow(["the mean of all", comparison[0]["cases"],
                    "squared errors of this group is the Brier score above",
                    f"{comparison[0]['bs']:.6f}"])
        w.writerow([])
        w.writerow(["unit test", "what it says", "outcome", "pytest"])
        for name, says, outcome, last in tests:
            w.writerow([name, says, outcome, last])
        if sabotages:
            w.writerow([])
            w.writerow(["sabotage of pipeline/verify.py", "outcome",
                        "which test noticed"])
            for row in sabotages:
                w.writerow(row)

    for row in comparison[:3]:
        print(f"  day {row['lead']} at {row['threshold']:g} mm: "
              f"bs {row['bs']:.9f} against {row['their_bs']} published")
    print(f"  largest difference over the 15 groups: {worst:.2e}")
    for name, _, outcome, last in tests:
        print(f"  {outcome}: {name}")
    for row in sabotages:
        print(f"  {row[1]}: {row[0]} -- {row[2]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
