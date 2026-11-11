"""HC2: work out step 48 minus step 24 by hand and check the code agrees.

Day 1 is the 24 to 48 hour window (SPEC 1.3), and tp accumulates from the
forecast start (SPEC 2.1), so Day 1 equals tp(48) minus tp(24). This check
does that subtraction in the open, on screen, at one square, and compares it
with what pipeline.ecmwf_process.daily_totals produces.

Usage: python handchecks/hc2_difference.py 20260513
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config as cfg                      # noqa: E402
from pipeline.ecmwf_process import daily_totals         # noqa: E402

TOLERANCE_MM = 1e-6


def main() -> int:
    date = sys.argv[1]
    member = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    with np.load(cfg.india_path(date)) as f:
        tp = f["tp"]
        steps = list(f["steps"])
        members = list(f["members"])
        lats = f["lat"]
        lons = f["lon"]

    mi = members.index(member)

    # Pick the square with the largest Day 1 total, so the numbers are big
    # enough to read rather than a row of zeros.
    day1_all = tp[steps.index(48), mi] - tp[steps.index(24), mi]
    i, j = np.unravel_index(int(np.argmax(day1_all)), day1_all.shape)

    a = float(tp[steps.index(24), mi, i, j])
    b = float(tp[steps.index(48), mi, i, j])
    by_hand = b - a

    from_code = float(daily_totals(tp)[0, mi, i, j])

    print(f"HC2  date {date}, member {member}")
    print(f"     square row {i} col {j}, "
          f"lat {float(lats[i]):.2f} lon {float(lons[j]):.2f}\n")
    print(f"     accumulated to step 24 : {a:12.6f} mm")
    print(f"     accumulated to step 48 : {b:12.6f} mm")
    print(f"     by hand, 48 minus 24   : {by_hand:12.6f} mm")
    print(f"     from daily_totals()    : {from_code:12.6f} mm")
    print(f"     difference             : {by_hand - from_code:12.3e} mm\n")

    if abs(by_hand - from_code) > TOLERANCE_MM:
        print("HC2 FAILED: the code does not agree with the hand calculation")
        return 1

    # Also show the full five days at this square, so the day boundaries are
    # visible rather than taken on trust.
    print("     all five days at this square:")
    print(f"       {'day':>4s} {'window':>10s} {'accum from':>12s} "
          f"{'accum to':>12s} {'daily mm':>10s}")
    codes_days = daily_totals(tp)
    for d in range(cfg.N_DAYS):
        s0, s1 = steps[d], steps[d + 1]
        print(f"       {d + 1:4d} {f'{s0}-{s1}':>10s} "
              f"{float(tp[d, mi, i, j]):12.6f} "
              f"{float(tp[d + 1, mi, i, j]):12.6f} "
              f"{float(codes_days[d, mi, i, j]):10.6f}")

    print("\nHC2 PASSED: hand calculation matches the code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
