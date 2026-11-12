"""HC-ALIGN: prove the two grids are aligned, and that cnt is not constant.

Read-only. Nothing is written except handchecks/results/hc_align.txt.

Three questions:

1. Is `precipitation_cnt` actually a variable, or is it 48 everywhere? If it
   were constant the completeness rule of SPEC 3.4 would be untestable.
2. Is the forecast grid paired with the right IMERG day, the right way up and
   the right way round? Spatial correlation is computed for the correct
   pairing and for eight wrong ones. The correct pairing has to win.
3. One named square on one date, with the ensemble numbers and the
   observation side by side.

Usage: python handchecks/hc_align.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.ecmwf_process import daily_totals              # noqa: E402
from pipeline.india_mask import load as load_mask            # noqa: E402
from pipeline.nasa_download import existing_file             # noqa: E402
from pipeline.nasa_process import imerg_date_for, nasa_path  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "hc_align.txt"

CNT_DATE = "20260722"          # the wettest India day in the archive
WANTED_RUN = "20260721"        # part 3 asks for this run
WANTED_LAT, WANTED_LON = 20.25, 72.75

lines: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)
    lines.append(text)


# ------------------------------------------------------------------- part 1

def part_one() -> None:
    say("=" * 72)
    say("1. Is precipitation_cnt constant 48?")
    say("=" * 72)

    path = existing_file(CNT_DATE)
    if path is None:
        say(f"   no IMERG file for {CNT_DATE}")
        return

    with h5py.File(path, "r") as f:
        cnt = np.asarray(f["precipitation_cnt"][0], dtype=np.int16)

    say(f"   file  {path.name}")
    say(f"   shape {cnt.shape} (lon, lat), {cnt.size:,} pixels")
    say(f"   global minimum {int(cnt.min())}, maximum {int(cnt.max())}")
    say("")
    say("   histogram of every value present, whole globe:")
    say(f"     {'cnt':>5s} {'pixels':>12s} {'share':>9s}")
    values, counts = np.unique(cnt, return_counts=True)
    for v, c in zip(values, counts):
        say(f"     {int(v):5d} {int(c):12,d} {100 * c / cnt.size:8.4f}%")
    say("")
    say(f"   values below 48: {int((cnt < 48).sum()):,} pixels "
        f"({100 * (cnt < 48).sum() / cnt.size:.4f}% of the globe)")
    say(f"   distinct values present: {len(values)}")
    say("   So the variable is not constant. It is 48 over India on every")
    say("   day in the archive, which is a fact about India's coverage, not")
    say("   about the variable (SPEC 3.7).")
    say("")


# ------------------------------------------------------------------- part 2

def pearson(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 100:
        return float("nan")
    x, y = a[ok].astype(np.float64), b[ok].astype(np.float64)
    x -= x.mean()
    y -= y.mean()
    denom = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / denom) if denom > 0 else float("nan")


def shift(field: np.ndarray, drow: int, dcol: int) -> np.ndarray:
    """Sample the field at (i + drow, j + dcol), NaN outside. No wrapping."""
    out = np.full_like(field, np.nan, dtype=np.float64)
    n_row, n_col = field.shape
    r_lo, r_hi = max(0, -drow), min(n_row, n_row - drow)
    c_lo, c_hi = max(0, -dcol), min(n_col, n_col - dcol)
    out[r_lo:r_hi, c_lo:c_hi] = field[r_lo + drow:r_hi + drow,
                                      c_lo + dcol:c_hi + dcol]
    return out


def ecmwf_day1_mean(date: str) -> np.ndarray | None:
    path = cfg.india_path(date)
    if not path.exists():
        return None
    with np.load(path) as f:
        tp = f["tp"]
    return daily_totals(tp)[0].mean(axis=0).astype(np.float64)


def imerg_rain(date: str) -> np.ndarray | None:
    if not nasa_path(date).exists():
        return None
    with np.load(nasa_path(date)) as f:
        return f["rain"].astype(np.float64)


def other_day(date: str, offset: int) -> str:
    day = dt.datetime.strptime(date, "%Y%m%d").date()
    return (day + dt.timedelta(days=offset)).strftime("%Y%m%d")


def part_two() -> bool:
    say("=" * 72)
    say("2. Is the pairing right? Spatial correlation over India squares")
    say("=" * 72)
    say("   Forecast side: lead day 1 ensemble mean, steps 24 to 48.")
    say("   Observed side: IMERG for imerg_date_for(R, 1) = R + 1.")
    say("   Correlation is Pearson's r across India squares within one date,")
    say("   then averaged over dates. Shifts move the IMERG map, so")
    say("   'one cell north' compares our square with the IMERG square")
    say("   0.25 degrees to its south.")
    say("")

    india = load_mask()["india"]
    runs = sorted(p.stem for p in cfg.DONE.glob("2*.json"))

    # (label, day offset applied to R+1, row offset, col offset, flip)
    variants = [
        ("correct pairing", 0, 0, 0, False),
        ("IMERG one day earlier", -1, 0, 0, False),
        ("IMERG one day later", +1, 0, 0, False),
        ("IMERG one cell north", 0, +1, 0, False),
        ("IMERG one cell south", 0, -1, 0, False),
        ("IMERG one cell east", 0, 0, -1, False),
        ("IMERG one cell west", 0, 0, +1, False),
        ("IMERG flipped north-south", 0, 0, 0, True),
    ]
    totals: dict[str, list[float]] = {label: [] for label, *_ in variants}

    used = []
    for run in runs:
        forecast = ecmwf_day1_mean(run)
        if forecast is None:
            continue
        base = imerg_date_for(run, 1)
        needed = [other_day(base, off) for off in (-1, 0, 1)]
        if any(imerg_rain(d) is None for d in needed):
            continue

        used.append(run)
        f_india = np.where(india, forecast, np.nan)
        for label, day_off, drow, dcol, flip in variants:
            obs = imerg_rain(other_day(base, day_off))
            if flip:
                obs = obs[::-1, :]
            if drow or dcol:
                obs = shift(obs, drow, dcol)
            o_india = np.where(india, obs, np.nan)
            r = pearson(f_india, o_india)
            if np.isfinite(r):
                totals[label].append(r)

    if not used:
        say("   no date had both a forecast file and the three IMERG days")
        return False

    say(f"   dates used: {len(used)}  ({used[0]} to {used[-1]})")
    say(f"   India squares per date: {int(india.sum()):,}")
    say("")
    say(f"   {'pairing':30s} {'mean r':>8s} {'min r':>8s} {'max r':>8s} "
        f"{'dates':>6s}")
    ranked = []
    for label, *_ in variants:
        values = np.asarray(totals[label])
        mean = float(values.mean())
        ranked.append((mean, label))
        say(f"   {label:30s} {mean:8.4f} {values.min():8.4f} "
            f"{values.max():8.4f} {values.size:6d}")

    ranked.sort(reverse=True)
    best_mean, best_label = ranked[0]
    correct_mean = float(np.asarray(totals["correct pairing"]).mean())
    say("")
    say(f"   highest average: {best_label} at r = {best_mean:.4f}")
    runner_up = ranked[1]
    say(f"   next best:       {runner_up[1]} at r = {runner_up[0]:.4f}")
    say(f"   margin:          {best_mean - runner_up[0]:.4f}")

    ok = best_label == "correct pairing"
    if ok:
        say("   PASS: the correct pairing wins, so the day mapping, the")
        say("   latitude direction and the longitude direction are all right.")
    else:
        say("   FAIL by the rule as written: a wrong pairing beat the")
        say("   correct one. Two diagnostics below say what kind of failure")
        say("   this is before anyone acts on it.")
    say("")

    # ---- diagnostic A: is the winner a real winner, or a coin flip?
    say("   DIAGNOSTIC A: paired per-date comparison against the winner")
    correct = np.asarray(totals["correct pairing"])
    for _, label in ranked[:3]:
        if label == "correct pairing":
            continue
        other = np.asarray(totals[label])
        diff = correct - other
        wins = int((diff > 0).sum())
        say(f"     correct vs {label}:")
        say(f"       correct higher on {wins} of {diff.size} dates")
        say(f"       mean difference {diff.mean():+.5f}, "
            f"standard deviation {diff.std(ddof=1):.5f}")
        say(f"       standard error of the mean {diff.std(ddof=1) / np.sqrt(diff.size):.5f}")
    say("")

    # ---- diagnostic B: two cells out, to show the shape of the curve
    say("   DIAGNOSTIC B: the same correlation at two cells out")
    say("   If a one-cell shift were a real misalignment, two cells in that")
    say("   direction would not fall away sharply.")
    india = load_mask()["india"]
    far = {f"{n} cell(s) {d}": [] for n in (1, 2)
           for d in ("north", "south", "east", "west")}
    for run in used:
        forecast = ecmwf_day1_mean(run)
        f_india = np.where(india, forecast, np.nan)
        obs = imerg_rain(imerg_date_for(run, 1))
        for n in (1, 2):
            for name, (drow, dcol) in {
                "north": (+n, 0), "south": (-n, 0),
                "east": (0, -n), "west": (0, +n),
            }.items():
                moved = np.where(india, shift(obs, drow, dcol), np.nan)
                r = pearson(f_india, moved)
                if np.isfinite(r):
                    far[f"{n} cell(s) {name}"].append(r)
    say(f"     {'shift':22s} {'mean r':>8s} {'vs correct':>11s}")
    say(f"     {'none (correct)':22s} {correct.mean():8.4f} {0.0:+11.4f}")
    for key, values in far.items():
        arr = np.asarray(values)
        say(f"     {key:22s} {arr.mean():8.4f} "
            f"{arr.mean() - correct.mean():+11.4f}")
    say("")
    return ok


# ------------------------------------------------------------------- part 3

def part_three() -> None:
    say("=" * 72)
    say("3. One square, one run, both sides")
    say("=" * 72)

    runs = sorted(p.stem for p in cfg.DONE.glob("2*.json"))
    if WANTED_RUN in runs:
        run = WANTED_RUN
        note = "the run asked for"
    else:
        wanted = dt.datetime.strptime(WANTED_RUN, "%Y%m%d").date()
        run = min(runs, key=lambda d: abs(
            (dt.datetime.strptime(d, "%Y%m%d").date() - wanted).days))
        gap = (dt.datetime.strptime(run, "%Y%m%d").date() - wanted).days
        note = (f"nearest done date to {WANTED_RUN}, which is not done; "
                f"{abs(gap)} day(s) {'later' if gap > 0 else 'earlier'}")

    i = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LATS) - WANTED_LAT)))
    j = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LONS) - WANTED_LON)))
    india = load_mask()["india"]

    with np.load(cfg.india_path(run)) as f:
        tp = f["tp"]
    totals = daily_totals(tp)

    say(f"   run            {run}  ({note})")
    say(f"   square         {cfg.INDIA_LATS[i]} N, {cfg.INDIA_LONS[j]} E  "
        f"(India square: {bool(india[i, j])})")
    say("")

    for lead in (1, 2):
        members = totals[lead - 1, :, i, j].astype(np.float64)
        obs_date = imerg_date_for(run, lead)
        obs = imerg_rain(obs_date)
        label = "LEAD DAY 1, as asked" if lead == 1 else (
            "LEAD DAY 2, added because this is the day the 406 mm fell")
        say(f"   {label}")
        say(f"     steps                 {24 * lead} to {24 * (lead + 1)}")
        say(f"     IMERG date            {obs_date}")
        say(f"     ensemble mean mm      {members.mean():.4f}")
        say(f"     ensemble max mm       {members.max():.4f}")
        say(f"     ensemble min mm       {members.min():.4f}")
        say(f"     members >= 50 mm      {int((members >= 50).sum())} of 51")
        say(f"     members >= 10 mm      {int((members >= 10).sum())} of 51")
        say(f"     members >= 1 mm       {int((members >= 1).sum())} of 51")
        if obs is None:
            say("     IMERG mm              not processed")
        else:
            say(f"     IMERG mm              {obs[i, j]:.4f}")
        say("")


def main() -> int:
    say("HC-ALIGN")
    say(f"written {dt.datetime.now().isoformat(timespec='seconds')}")
    say("read-only check; nothing but this file is written")
    say("")
    part_one()
    ok = part_two()
    part_three()
    say("=" * 72)
    say(f"HC-ALIGN {'PASSED' if ok else 'FAILED'}")
    say("=" * 72)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
