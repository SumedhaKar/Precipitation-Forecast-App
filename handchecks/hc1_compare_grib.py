"""HC1: compare the saved India file against the original GRIB.

The point of this check is to catch an error in our own index arithmetic, so
it must not reuse it. It asks ecCodes itself, through
``codes_grib_find_nearest``, what the value is at a given latitude and
longitude. ecCodes walks its own grid description to answer, so nothing in
pipeline/ is involved on that side of the comparison.

Note on tooling: the ecCodes command line programs (grib_get, grib_ls) are not
shipped in the Windows pip wheel, only the library. ``find_nearest`` is the
closest independent equivalent available here, and it tests the riskiest part
more directly than grib_get would, because grib_get would still leave us to do
the index arithmetic ourselves.

Usage: python handchecks/hc1_compare_grib.py 20260513
"""
from __future__ import annotations

import sys
from pathlib import Path

import eccodes as ec
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config as cfg  # noqa: E402

STEPS_TO_CHECK = (24, 144)
MEMBERS_TO_CHECK = (0, 38)
TOLERANCE_MM = 1e-4


def read_india_lsm() -> np.ndarray | None:
    """India land-sea mask, used only to pick a coastal square."""
    path = cfg.RAW / "probe_lsm_aifs-ens.grib2"
    if not path.exists():
        return None
    with open(path, "rb") as f:
        h = ec.codes_grib_new_from_file(f)
        values = ec.codes_get_values(h)
        rows, cols = cfg.india_slice(
            ec.codes_get(h, "latitudeOfFirstGridPointInDegrees"),
            ec.codes_get(h, "longitudeOfFirstGridPointInDegrees"),
        )
        ec.codes_release(h)
    return values.reshape(cfg.GLOBAL_NJ, cfg.GLOBAL_NI)[rows, cols]


def pick_squares(tp: np.ndarray) -> list[tuple[str, int, int]]:
    """Choose a rainy, a dry and a coastal square. Returns (label, i, j)."""
    day1 = tp[1, 0] - tp[0, 0]  # member 0, step 24 -> 48
    rainy = np.unravel_index(int(np.argmax(day1)), day1.shape)

    total144 = tp[-1].sum(axis=0)  # summed over members, driest overall
    dry = np.unravel_index(int(np.argmin(total144)), total144.shape)

    lsm = read_india_lsm()
    if lsm is None:
        coastal = (cfg.N_LAT // 2, 0)
    else:
        coastal = np.unravel_index(int(np.argmin(np.abs(lsm - 0.5))), lsm.shape)

    return [
        ("rainy  ", int(rainy[0]), int(rainy[1])),
        ("dry    ", int(dry[0]), int(dry[1])),
        ("coastal", int(coastal[0]), int(coastal[1])),
    ]


def grib_value_at(path: Path, member: int, lat: float, lon: float) -> float:
    """Ask ecCodes for the value nearest this lat/lon, for one member."""
    with open(path, "rb") as f:
        while True:
            h = ec.codes_grib_new_from_file(f)
            if h is None:
                raise LookupError(f"member {member} not found in {path.name}")
            try:
                if ec.codes_get(h, "perturbationNumber") != member:
                    continue
                near = ec.codes_grib_find_nearest(h, lat, lon)[0]
                return float(near["value"]), float(near["lat"]), float(near["lon"])
            finally:
                ec.codes_release(h)


def main() -> int:
    date = sys.argv[1]
    npz_path = cfg.india_path(date)
    if not npz_path.exists():
        print(f"no saved file for {date}")
        return 1

    with np.load(npz_path) as f:
        tp = f["tp"]
        steps = list(f["steps"])
        members = list(f["members"])
        lats = f["lat"]
        lons = f["lon"]

    squares = pick_squares(tp)

    print(f"HC1  date {date}")
    print(f"     saved file {npz_path.name}, shape {tp.shape}")
    print(f"     comparing against raw GRIB via ecCodes find_nearest")
    print(f"     tolerance {TOLERANCE_MM} mm\n")

    print("     squares chosen:")
    for label, i, j in squares:
        print(f"       {label}  row {i:3d} col {j:3d}  "
              f"lat {lats[i]:6.2f}  lon {lons[j]:6.2f}")
    print()

    header = (f"     {'square':8s} {'step':>5s} {'mem':>4s} "
              f"{'saved mm':>11s} {'grib mm':>11s} {'diff':>11s}  result")
    print(header)
    print("     " + "-" * (len(header) - 5))

    failures = 0
    for label, i, j in squares:
        lat = float(lats[i])
        lon = float(lons[j])
        for step in STEPS_TO_CHECK:
            si = steps.index(step)
            for member in MEMBERS_TO_CHECK:
                mi = members.index(member)
                saved = float(tp[si, mi, i, j])

                typ = "cf" if member == 0 else "pf"
                raw = cfg.raw_path(date, typ, step)
                if not raw.exists():
                    print(f"     {label} {step:5d} {member:4d}  "
                          f"raw file missing: {raw.name}")
                    failures += 1
                    continue

                got, glat, glon = grib_value_at(raw, member, lat, lon)
                diff = saved - got
                ok = abs(diff) <= TOLERANCE_MM
                failures += 0 if ok else 1

                # The nearest point must be the square we asked about,
                # otherwise the comparison is meaningless.
                if abs(glat - lat) > 1e-6 or abs(glon - lon) > 1e-6:
                    print(f"     {label} {step:5d} {member:4d}  "
                          f"ecCodes returned lat {glat} lon {glon}, "
                          f"not {lat}/{lon}")
                    failures += 1
                    continue

                print(f"     {label} {step:5d} {member:4d} "
                      f"{saved:11.5f} {got:11.5f} {diff:11.2e}  "
                      f"{'MATCH' if ok else 'MISMATCH'}")

    print()
    if failures:
        print(f"HC1 FAILED: {failures} mismatch(es)")
        return 1
    print(f"HC1 PASSED: all {len(squares) * len(STEPS_TO_CHECK) * len(MEMBERS_TO_CHECK)} "
          "comparisons matched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
