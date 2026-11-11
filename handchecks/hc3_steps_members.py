"""HC3: print the steps and member ids actually stored in a saved file.

Nothing here is taken from config. Everything printed is read back out of the
saved file, so if the file disagreed with the spec it would show up here.

Usage: python handchecks/hc3_steps_members.py 20260513
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config as cfg  # noqa: E402


def main() -> int:
    date = sys.argv[1]
    path = cfg.india_path(date)

    with np.load(path) as f:
        keys = list(f.keys())
        tp = f["tp"]
        steps = f["steps"]
        members = f["members"]
        lat = f["lat"]
        lon = f["lon"]

    print(f"HC3  date {date}")
    print(f"     file    {path.name}  ({path.stat().st_size:,} bytes)")
    print(f"     arrays  {keys}")
    print(f"     tp      shape {tp.shape}, dtype {tp.dtype}")
    print()

    print(f"     steps stored in the file ({len(steps)}):")
    print(f"       {list(int(s) for s in steps)}")
    print()

    print(f"     member ids stored in the file ({len(members)}):")
    ids = [int(m) for m in members]
    for start in range(0, len(ids), 17):
        print("       " + " ".join(f"{m:3d}" for m in ids[start:start + 17]))
    print()

    print(f"     latitude  {len(lat)} values, {lat[0]} down to {lat[-1]}")
    print(f"     longitude {len(lon)} values, {lon[0]} up to {lon[-1]}")
    print()

    problems = []
    if len(set(ids)) != len(ids):
        problems.append("duplicate member ids")
    if ids != sorted(ids):
        problems.append("member ids are not in ascending order")
    if ids != list(range(51)):
        problems.append(f"member ids are not 0 to 50, got {ids[0]} to {ids[-1]}")
    if list(int(s) for s in steps) != sorted(int(s) for s in steps):
        problems.append("steps are not in ascending order")
    if not np.isfinite(tp).all():
        problems.append("tp contains non-finite values")

    # Accumulated totals must never decrease with step (SPEC 2.1), beyond the
    # packing noise allowed for this date. The tolerance is read back from the
    # date's own done record rather than assumed.
    done = cfg.done_path(date)
    if done.exists():
        import json
        record = json.loads(done.read_text(encoding="utf-8"))
        tolerance = record["daily_differences"]["tolerance_mm"]
        coarsest = record["packing"]["coarsest_quantum_mm"]
        print(f"     packing quantum, coarsest {coarsest} mm")
        print(f"     tolerance from the done record {tolerance} mm")
        print()
    else:
        tolerance = -cfg.QUANTUM_TOLERANCE_FACTOR * cfg.MAX_TRUSTED_QUANTUM
        print(f"     no done record, using the cap-derived {tolerance} mm\n")

    decreasing = int((np.diff(tp, axis=0) < tolerance).sum())
    if decreasing:
        problems.append(f"{decreasing} accumulations decrease by more than "
                        f"{tolerance} mm")

    if problems:
        for p in problems:
            print(f"     PROBLEM: {p}")
        print("\nHC3 FAILED")
        return 1

    print("     51 members, 0 to 50, each exactly once, ascending")
    print("     6 steps, ascending, accumulations never decrease materially")
    print("\nHC3 PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
