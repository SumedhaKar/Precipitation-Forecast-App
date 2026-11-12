"""HC6: all 51 members' tp at steps 24 and 48, from the raw GRIB.

Why this shape of check. HC6 was specified as "compare our counts against
ECMWF's own published probabilities, and if there are none, dump the members
instead". There are none: on 11 November 2026 the only AIFS ENS products in
the 0.25 degree `enfo` stream on ECMWF open data are `cf` and `pf`. There is
no `ep` file and no threshold-probability parameter; the `pf` index lists 29
parameters with `tp` the only precipitation total. So this is the members
branch.

One deviation from the instruction, stated rather than hidden. The ecCodes
**command line** tools are not shipped in the Windows pip wheel, there are no
executables in the package and none on PATH, so `grib_get` cannot be used
here. This reads the values through `codes_grib_find_nearest` in the ecCodes
C library instead: ecCodes walks its own grid description to answer, so
nothing in pipeline/ takes part in locating the value. That is the same
independent route HC1 uses, for the same reason.

Usage: python handchecks/hc6_members.py [run_id]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import eccodes as ec
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.india_mask import load as load_mask            # noqa: E402
from pipeline.run_live import (                              # noqa: E402
    DOT_EDGES,
    THRESHOLDS,
    LIVE,
    last_built,
    run_dir,
)

OUT = Path(__file__).resolve().parent / "results" / "hc6_members.csv"
STEPS_TO_DUMP = (24, 48)          # lead day 1 is their difference


def members_at(path: Path, lat: float, lon: float) -> dict[int, float]:
    """perturbationNumber -> value at this point, straight from ecCodes."""
    out: dict[int, float] = {}
    with open(path, "rb") as f:
        while True:
            h = ec.codes_grib_new_from_file(f)
            if h is None:
                break
            try:
                number = ec.codes_get(h, "perturbationNumber")
                near = ec.codes_grib_find_nearest(h, lat, lon)[0]
                out[int(number)] = float(near["value"])
            finally:
                ec.codes_release(h)
    return out


def pick_squares(product_path: Path) -> list[tuple[str, int, int]]:
    """One rainy and one dry India square, chosen from the run itself."""
    india = load_mask()["india"]
    with np.load(product_path) as f:
        totals = f["member_totals"]

    day1 = totals[0].mean(axis=0)
    rainy_pool = np.where(india, day1, -np.inf)
    ri, rj = np.unravel_index(int(np.argmax(rainy_pool)), rainy_pool.shape)

    # Dry means dry in every member, and the driest such square.
    dry_pool = np.where(india & (totals[0].max(axis=0) < 1.0), day1, np.inf)
    if np.isfinite(dry_pool).any():
        di, dj = np.unravel_index(int(np.argmin(dry_pool)), dry_pool.shape)
    else:
        fallback = np.where(india, day1, np.inf)
        di, dj = np.unravel_index(int(np.argmin(fallback)), fallback.shape)

    return [("rainy", int(ri), int(rj)), ("dry", int(di), int(dj))]


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else last_built()
    if run_id is None:
        raise SystemExit("no live run has been built yet")
    out_dir = run_dir(run_id)
    raw_dir = out_dir / "raw"
    if not raw_dir.is_dir():
        raise SystemExit(f"{raw_dir} is missing; run pipeline.run_live first")

    squares = pick_squares(out_dir / "squares.npz")
    with np.load(out_dir / "squares.npz") as f:
        totals = f["member_totals"]
        counts = f["counts"]
        dots = f["dots"]

    rows = []
    notes = []
    for label, i, j in squares:
        lat, lon = cfg.INDIA_LATS[i], cfg.INDIA_LONS[j]
        per_step: dict[int, dict[int, float]] = {}
        for step in STEPS_TO_DUMP:
            values: dict[int, float] = {}
            for typ in cfg.TYPES:
                values.update(members_at(raw_dir / f"{typ}_{step:03d}.grib2",
                                         lat, lon))
            if sorted(values) != list(cfg.MEMBERS):
                raise SystemExit(
                    f"{label} step {step}: got {len(values)} members")
            per_step[step] = values

        for member in cfg.MEMBERS:
            a = per_step[24][member]
            b = per_step[48][member]
            day1 = b - a
            rows.append({
                "square": label,
                "lat_N": lat,
                "lon_E": lon,
                "member": member,
                "tp_step24_mm": repr(a),
                "tp_step48_mm": repr(b),
                "day1_total_mm": repr(day1),
                "at_or_above_1mm": int(day1 >= THRESHOLDS[0]),
                "at_or_above_10mm": int(day1 >= THRESHOLDS[1]),
                "at_or_above_50mm": int(day1 >= THRESHOLDS[2]),
                "dot_category": (
                    "under 1 mm" if day1 < DOT_EDGES[0] else
                    "1 to under 10 mm" if day1 < DOT_EDGES[1] else
                    "10 to under 50 mm" if day1 < DOT_EDGES[2] else
                    "50 mm or more"),
            })

        notes.append({
            "square": label,
            "lat": lat,
            "lon": lon,
            "our_count_ge_1mm": int(counts[0, 0, i, j]),
            "our_count_ge_10mm": int(counts[1, 0, i, j]),
            "our_count_ge_50mm": int(counts[2, 0, i, j]),
            "our_dots": [int(x) for x in dots[:, 0, i, j]],
            "our_mean_mm": float(totals[0, :, i, j].mean()),
            "our_max_mm": float(totals[0, :, i, j].max()),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        fh.write("# HC6: every member's tp at steps 24 and 48, read by "
                 "ecCodes find_nearest\n")
        fh.write(f"# run,{run_id}\n")
        fh.write("# ECMWF open data publishes no AIFS ENS probability "
                 "product: enfo has cf and pf only, no ep file\n")
        fh.write("# so this is the members branch of HC6\n")
        fh.write("# the ecCodes command line tools are not in the Windows "
                 "pip wheel, so codes_grib_find_nearest is used instead; "
                 "no pipeline code locates these values\n")
        fh.write("# day1_total_mm = tp_step48_mm - tp_step24_mm\n")
        fh.write("# check: SUM(at_or_above_10mm) over a square's 51 rows "
                 "should equal that square's our_count_ge_10mm below\n")
        for note in notes:
            fh.write("# " + json.dumps(note) + "\n")
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUT}")
    ok = True
    for note in notes:
        label = note["square"]
        subset = [r for r in rows if r["square"] == label]
        for k, threshold in enumerate(THRESHOLDS):
            key = f"at_or_above_{threshold:g}mm".replace(".0", "")
            from_csv = sum(r[key] for r in subset)
            ours = note[f"our_count_ge_{threshold:g}mm"]
            mark = "ok " if from_csv == ours else "MISMATCH"
            if from_csv != ours:
                ok = False
            print(f"  {mark} {label:6s} {threshold:5g} mm: CSV rows say "
                  f"{from_csv}, our count says {ours}")
        print(f"       {label:6s} at {note['lat']} N {note['lon']} E, "
              f"dots {note['our_dots']}, mean {note['our_mean_mm']:.3f} mm, "
              f"max {note['our_max_mm']:.3f} mm")
    print("HC6 PASSED" if ok else "HC6 FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
