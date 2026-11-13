"""Write the Time Machine's one data file. SPEC 11.38.

    python -m scripts.build_time_machine

Reads Pile A and Pile B, picks the seven days with `pick_time_machine`, and
writes `web/src/time-machine.json`: for each day the five count maps, the
satellite estimate in the same squares, and the day's own record.

It writes that file and nothing else. No file in `results/` is touched.

The maps are stored for the 4,613 India squares only, in the mask's own
row-major order, with each square's flat index into the 129 by 121 grid given
once at the top. The page expands them back to the full grid, which is the
layout the map already reads (8.4). Storing the full grid with 255 outside
India would be four times the size and carry nothing more.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from pipeline import config as cfg
from pipeline import verify
from scripts import pick_time_machine as pick

OUT = cfg.ROOT / "web" / "src" / "time-machine.json"

LEADS = (5, 4, 3, 2, 1)

# SPEC 11.38. A square with no satellite value is this, and it is never shown
# as no rain.
NO_VALUE = -1

# The satellite estimate is kept to the tenth of a millimetre, which is what
# the page prints, and it is **floored** rather than rounded.
#
# Rounding was the first version and it put six squares in the wrong class.
# The three edges that matter -- 1, 10 and 50 mm -- are all whole tenths, so
# flooring to a tenth cannot move a value across one of them: floor(x * 10)
# reaches 100 exactly when x reaches 10. Rounding can, and did: a square at
# 9.96 mm was scored as under 10 by the selection and drawn as 10.0 mm by the
# page, which is the map disagreeing with the rule that chose the day.
# Flooring costs at most a tenth of a millimetre on the number shown and
# makes that disagreement impossible.
TENTHS = 10.0


def tenths_of(rain: np.ndarray) -> list[int]:
    """Tenths of a millimetre, with NO_VALUE where the 90% rule excluded it."""
    valid = np.isfinite(rain)
    out = np.full(rain.shape, NO_VALUE, dtype=np.int32)
    out[valid] = np.floor(rain[valid] * TENTHS).astype(np.int32)
    return [int(v) for v in out]


def build(report=print) -> dict:
    table = pick.measure(report=report)
    chosen = pick.select(table["eligible"])
    mask = verify.load_mask()
    india = mask["india"]
    rows, cols = np.nonzero(india)
    squares = [int(i) * cfg.N_LON + int(j) for i, j in zip(rows, cols)]
    rain = verify.read_observations(mask, verify.obs_dates())

    days = []
    for row in sorted(chosen, key=lambda item: item["date"]):
        stamp = row["date"]
        report(f"  {stamp}  {row['reason']}")
        counts = {}
        for lead in LEADS:
            run = pick.run_for(stamp, lead)
            counts[str(lead)] = [
                int(v) for v in pick.counts_for(run, lead, india)]
        days.append({
            "date": stamp,
            "day": pick.day_text(stamp),
            "window": pick.window_text(stamp),
            "reason": row["reason"],
            "why": row["why"],
            "score": row["score"],
            "runs": {str(lead): pick.run_for(stamp, lead) for lead in LEADS},
            "counts": counts,
            "satellite_tenths": tenths_of(rain[stamp]),
        })

    return {
        "spec": "11.38",
        "threshold_mm": int(pick.THRESHOLD_MM),
        "members": cfg.N_MEMBERS,
        "no_value": NO_VALUE,
        "rule": {
            "seed": pick.SEED,
            "gap_days": pick.GAP_DAYS,
            "error_lead": pick.ERROR_LEAD,
            "loud_count": pick.LOUD_COUNT,
            "quiet_count": pick.QUIET_COUNT,
            "drizzle_mm": pick.DRIZZLE_MM,
            "lists": [[name, how_many] for name, how_many in pick.LISTS],
            "first_eligible": table["first"],
            "last_eligible": table["last"],
        },
        "grid": {
            "n_lat": cfg.N_LAT,
            "n_lon": cfg.N_LON,
            "grid_step_degrees": cfg.GRID_STEP,
            "lat_max": cfg.LAT_MAX,
            "lon_min": cfg.LON_MIN,
            "not_india": cfg.NOT_INDIA,
        },
        "squares": squares,
        # Every eligible day's score, not only the seven. It is 173 rows and
        # a few kilobytes, and it is what lets the rule be checked against
        # the file on a machine with no archive: `select` over this table has
        # to give back these seven days, and with another seed it must not.
        "eligible": table["eligible"],
        "chosen": [{"date": item["date"], "reason": item["reason"],
                    "score": item["score"]} for item in chosen],
        "days": days,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    record = build()
    text = json.dumps(record, separators=(",", ":")) + "\n"
    args.out.write_bytes(text.encode())
    print(f"  wrote {args.out.name}, {len(text.encode()) / 1e6:.3f} MB")


if __name__ == "__main__":
    main()
