"""HC9: one reliability bucket, recomputed from the files by hand.

SPEC 5.6 and 5.11. `pipeline/verify.py` says that in one region, at one lead
day and one threshold, the forecasts in one bucket were right so often. This
script works that same number out again without importing any of the project,
and the two have to agree exactly.

What is redone here, from scratch:

  * the daily total, as step 48 minus step 24 of the stored accumulation,
    with the negative-difference rule of SPEC 3.6 written out again;
  * the member count at the threshold, "greater than or equal to";
  * the observed value, from the **raw** IMERG `.nc4`: transposed, flipped,
    area-weighted onto the 0.25 degree box with the spherical weights of
    SPEC 3.3, and the 90% completeness rule of SPEC 3.4 with the remaining
    weights renormalised;
  * which bucket each case falls in, and the bucket's case count, mean
    forecast and observed frequency.

What is taken rather than redone, and is therefore not what this checks: the
India mask and the IMD region, both read from the committed `config/` files,
and the daily grid geometry of SPEC 1.4. Those have their own checks (HC-
ALIGN, and the mask and region tests).

**The bucket is chosen from the forecast side only.** The twelve dates are
every fifteenth run date of Pile A, and the bucket is the highest band of `k`
that holds at least 30 cases over them. No observation is read until the
bucket is fixed, so there is no way to pick a bucket that flatters the
result.

    python handchecks/hc9_bucket.py
    python handchecks/hc9_bucket.py --group "South Peninsula" --lead 1
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
OUT = ROOT / "handchecks" / "results" / "hc9_bucket.csv"

# Written out here rather than imported, on purpose.
GRID = 0.25
HALF = GRID / 2
LAT_FIRST, LAT_LAST = 38.0, 6.0
LON_FIRST, LON_LAST = 68.0, 98.0
N_LAT, N_LON = 129, 121
MEMBERS = 51
PIXEL = 0.1
PIXEL_HALF = PIXEL / 2
PIX_LAT_FIRST, PIX_LON_FIRST = -89.95, -179.95
N_PIX_LAT, N_PIX_LON = 1800, 3600
COMPLETE_CNT = 48
MIN_COMPLETE = 0.90
FILL = -9999.9

EVERY = 15                      # every fifteenth run date
MIN_CASES = 30                  # a bucket worth checking
TOLERANCE = -0.5                # SPEC 3.6's loosest, for 12-bit packing

# What this check can and cannot catch, measured on 13 November 2026 by
# breaking each rule in this file in turn and rerunning. Recorded because a
# hand check that is not known to bite proves nothing, and because three of
# these six say plainly what the bucket cannot test.
BITES = [
    ("the observation read a quarter degree north", "CAUGHT",
     "observed 0.931034 instead of 0.965517"),
    ("the daily total taken as step 24 rather than 48 minus 24", "CAUGHT",
     "67 cases instead of 58, observed 0.507463"),
    ("a member exactly at the threshold not counted", "missed",
     "no member total in these cases sits on 10.0 mm, and one that did "
     "would leave the k = 51 bucket rather than change its score"),
    ("incomplete IMERG pixels counted as no rain", "missed",
     "none of these 58 box-days had an incomplete pixel, so the rule had "
     "nothing to change here"),
    ("plain degrees instead of spherical weights", "missed",
     "within one 0.25 degree box at these latitudes the two weightings "
     "differ by under half a per cent, which moved no value across 10 mm"),
]


def india_squares(region: str):
    """The India squares of one IMD region, from the committed files."""
    mask = json.loads((ROOT / "config" / "india_mask.json").read_text("utf-8"))
    regions = json.loads((ROOT / "config" / "regions.json").read_text("utf-8"))
    code = regions["regions"].index(region) + 1
    lat = mask["lat"]
    lon = mask["lon"]
    if len(lat) != N_LAT or len(lon) != N_LON:
        raise SystemExit("the grid in the mask is not the grid of SPEC 1.4")
    out = []
    for i, row in enumerate(regions["region_rows"]):
        for j, value in enumerate(row):
            if int(value) == code:
                out.append((i, j, float(lat[i]), float(lon[j])))
    if not out:
        raise SystemExit(f"no squares in {region}")
    return out


def daily_total(date: str) -> np.ndarray:
    """Day 1 totals for every member, step 48 minus step 24, by hand."""
    with np.load(ROOT / "data" / "india" / "ecmwf" / f"{date}.npz") as box:
        tp = box["tp"]
        steps = list(box["steps"])
        members = list(box["members"])
    if steps[:2] != [24, 48]:
        raise SystemExit(f"{date}: steps are {steps}")
    if sorted(members) != list(range(MEMBERS)):
        raise SystemExit(f"{date}: members are not 0 to 50")
    difference = tp[1].astype(np.float64) - tp[0].astype(np.float64)
    worst = float(difference.min())
    if worst < TOLERANCE:
        raise SystemExit(f"{date}: a daily difference of {worst} mm")
    return np.where(difference < 0.0, 0.0, difference)


def imerg_name(date: str) -> Path:
    return (ROOT / "data" / "raw" / "imerg" /
            f"3B-DAY-L.MS.MRG.3IMERG.{date}-S000000-E235959.V07C.nc4")


def observed(date: str, squares) -> dict:
    """The observed daily total for each square, from the raw IMERG file.

    SPEC 3.3's spherical weights and SPEC 3.4's completeness rule, both
    written out again here rather than imported.
    """
    path = imerg_name(date)
    if not path.exists():
        raise SystemExit(f"no raw IMERG file for {date}: {path.name}")
    with h5py.File(path, "r") as handle:
        rain = np.array(handle["precipitation"][0])        # (lon, lat)
        count = np.array(handle["precipitation_cnt"][0])
        pix_lat = np.array(handle["lat"])
        pix_lon = np.array(handle["lon"])
    if rain.shape != (N_PIX_LON, N_PIX_LAT):
        raise SystemExit(f"{date}: precipitation is shaped {rain.shape}")
    if abs(pix_lat[0] - PIX_LAT_FIRST) > 1e-4 or pix_lat[1] < pix_lat[0]:
        raise SystemExit(f"{date}: latitude does not ascend from -89.95")
    if abs(pix_lon[0] - PIX_LON_FIRST) > 1e-4:
        raise SystemExit(f"{date}: longitude does not start at -179.95")

    out = {}
    for i, j, lat, lon in squares:
        south, north = lat - HALF, lat + HALF
        west, east = lon - HALF, lon + HALF
        lat_from = max(0, int(math.floor(
            (south - PIX_LAT_FIRST - PIXEL_HALF) / PIXEL)))
        lat_to = min(N_PIX_LAT - 1, int(math.ceil(
            (north - PIX_LAT_FIRST + PIXEL_HALF) / PIXEL)))
        lon_from = max(0, int(math.floor(
            (west - PIX_LON_FIRST - PIXEL_HALF) / PIXEL)))
        lon_to = min(N_PIX_LON - 1, int(math.ceil(
            (east - PIX_LON_FIRST + PIXEL_HALF) / PIXEL)))

        whole = 0.0
        good = 0.0
        total = 0.0
        for a in range(lat_from, lat_to + 1):
            low = max(south, float(pix_lat[a]) - PIXEL_HALF)
            high = min(north, float(pix_lat[a]) + PIXEL_HALF)
            if high <= low:
                continue
            band = (math.sin(math.radians(high))
                    - math.sin(math.radians(low)))
            for b in range(lon_from, lon_to + 1):
                left = max(west, float(pix_lon[b]) - PIXEL_HALF)
                right = min(east, float(pix_lon[b]) + PIXEL_HALF)
                if right <= left:
                    continue
                weight = (right - left) * band
                whole += weight
                value = float(rain[b, a])
                if (int(count[b, a]) != COMPLETE_CNT
                        or abs(value - FILL) < 0.01
                        or not math.isfinite(value)):
                    continue
                good += weight
                total += weight * value
        if whole <= 0:
            raise SystemExit(f"{date}: no IMERG pixel covers {lat}, {lon}")
        out[(i, j)] = (total / good if good / whole >= MIN_COMPLETE
                       else float("nan"))
    return out


def bucket_of(k: int, members: int = MEMBERS) -> tuple[int, int]:
    """The band of `k` this forecast falls in, as (from, to)."""
    if k == 0:
        return (0, 0)
    if k == members:
        return (members, members)
    band = min(9, (k * 10) // members)
    lowest = [x for x in range(1, members)
              if min(9, (x * 10) // members) == band]
    return (lowest[0], lowest[-1])


def next_day(date: str) -> str:
    import datetime as dt
    return (dt.date.fromisoformat(date)
            + dt.timedelta(days=1)).strftime("%Y%m%d")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="South Peninsula")
    parser.add_argument("--lead", type=int, default=1)
    parser.add_argument("--threshold", type=float, default=10.0)
    args = parser.parse_args()
    if args.lead != 1:
        raise SystemExit("this check redoes day 1 only, steps 24 to 48")

    everything = sorted(p.stem for p in
                        (ROOT / "data" / "india" / "ecmwf").glob("*.npz"))
    dates = everything[::EVERY][:12]
    if len(dates) != 12:
        raise SystemExit(f"{len(dates)} dates, not 12")
    squares = india_squares(args.region)
    print(f"  {args.region}, lead {args.lead}, {args.threshold:g} mm")
    print(f"  {len(squares)} squares, 12 dates: {dates[0]} to {dates[-1]}")

    # ---- the forecast side, and the bucket, before any observation is read
    counts = {}
    for date in dates:
        totals = daily_total(date)
        for i, j, _, _ in squares:
            counts[(date, i, j)] = int(
                np.count_nonzero(totals[:, i, j] >= args.threshold))
    tally = {}
    for k in counts.values():
        band = bucket_of(k)
        tally[band] = tally.get(band, 0) + 1
    big = sorted(band for band, n in tally.items() if n >= MIN_CASES)
    if not big:
        raise SystemExit(f"no bucket holds {MIN_CASES} cases")
    chosen = big[-1]
    print(f"  buckets with at least {MIN_CASES} cases: "
          + ", ".join(f"{a}-{b} ({tally[(a, b)]})" for a, b in big))
    print(f"  chosen, on case counts alone: k {chosen[0]} to {chosen[1]}")

    # ---- now, and only now, the observations
    mine = [(date, i, j, k) for (date, i, j), k in counts.items()
            if bucket_of(k) == chosen]
    cases, events, forecast_sum = 0, 0, 0.0
    missing = 0
    for date in dates:
        here = [row for row in mine if row[0] == date]
        if not here:
            continue
        values = observed(next_day(date),
                          [(i, j, lat, lon) for i, j, lat, lon in squares
                           if any(r[1] == i and r[2] == j for r in here)])
        for _, i, j, k in here:
            value = values[(i, j)]
            if not math.isfinite(value):
                missing += 1
                continue
            cases += 1
            forecast_sum += k / MEMBERS
            events += 1 if value >= args.threshold else 0
    if cases == 0:
        raise SystemExit("every case of the bucket was excluded")
    by_hand = {"cases": cases,
               "mean_forecast": forecast_sum / cases,
               "observed": events / cases}
    print(f"  by hand: {cases} cases ({missing} excluded as incomplete), "
          f"mean forecast {by_hand['mean_forecast']:.6f}, "
          f"observed {by_hand['observed']:.6f}")

    # ---- the pipeline's own answer, over the same twelve dates
    with tempfile.TemporaryDirectory() as folder:
        where = Path(folder) / "hc9.json"
        done = subprocess.run(
            [PY, "-m", "pipeline.verify", "--dates", ",".join(dates),
             "--out", str(where)],
            cwd=ROOT, capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"verify failed:\n{done.stdout}\n{done.stderr}")
        result = json.loads(where.read_text("utf-8"))
    theirs = None
    for group in result["groups_scored"]:
        if (group["variant"] == "all51" and group["region"] == args.region
                and group["lead_day"] == args.lead
                and group["threshold_mm"] == args.threshold):
            for band in group["buckets"]:
                if (band["k_from"], band["k_to"]) == chosen:
                    theirs = band
    if theirs is None:
        raise SystemExit("the pipeline has no such bucket")
    print(f"  pipeline: {theirs['cases']} cases, mean forecast "
          f"{theirs['mean_forecast']:.6f}, observed "
          f"{theirs['observed']:.6f}")

    rows = [
        ("cases", by_hand["cases"], theirs["cases"],
         by_hand["cases"] - theirs["cases"]),
        ("mean_forecast", by_hand["mean_forecast"], theirs["mean_forecast"],
         by_hand["mean_forecast"] - theirs["mean_forecast"]),
        ("observed", by_hand["observed"], theirs["observed"],
         by_hand["observed"] - theirs["observed"]),
    ]
    # The pipeline writes six decimal places, so that is all we can ask of
    # the two numbers that are not counts.
    bad = [row for row in rows
           if abs(row[3]) > (0 if row[0] == "cases" else 5e-7)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["hc9", "one reliability bucket, SPEC 5.6"])
        writer.writerow(["region", args.region])
        writer.writerow(["lead_day", args.lead])
        writer.writerow(["threshold_mm", args.threshold])
        writer.writerow(["dates", " ".join(dates)])
        writer.writerow(["date_rule", f"every {EVERY}th run date of Pile A"])
        writer.writerow(["bucket_k_from", chosen[0]])
        writer.writerow(["bucket_k_to", chosen[1]])
        writer.writerow(["bucket_rule",
                         f"highest band of k with at least {MIN_CASES} "
                         "cases, chosen from the forecast side alone"])
        writer.writerow(["excluded_incomplete", missing])
        writer.writerow([])
        writer.writerow(["what", "by hand", "pipeline", "difference"])
        for row in rows:
            writer.writerow(row)
        writer.writerow([])
        writer.writerow(["sabotage", "outcome", "note"])
        for row in BITES:
            writer.writerow(row)
        writer.writerow([])
        writer.writerow(["verdict", "FAIL" if bad else "PASS"])
    print(f"  wrote {OUT.relative_to(ROOT)}")
    if bad:
        raise SystemExit(f"HC9 FAILED: {bad}")
    print("  HC9 PASSED: every number agrees")


if __name__ == "__main__":
    main()
