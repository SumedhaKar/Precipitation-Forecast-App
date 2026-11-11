"""Turn one date's raw GRIB files into one checked India subset file.

SPEC 2.6 point 2: the saved file holds ACCUMULATED tp for 51 members at 6
steps, not daily differences. Differences are computed afterwards only to run
the SPEC 3.6 negative check.

The file is written as .part, reopened and checked, and only then renamed.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from . import config as cfg
from .checks import CheckFailed, check_daily_differences, read_india_subset


def build_india_array(date: str):
    """Read all 12 raw files for one date into one array.

    Returns (tp, packing) where tp is float32 shaped
    (6 steps, 51 members, 129 lat, 121 lon) holding accumulated mm.
    """
    tp = np.full(
        (cfg.N_STEPS, cfg.N_MEMBERS, cfg.N_LAT, cfg.N_LON),
        np.nan,
        dtype=np.float32,
    )
    packing: dict[str, list] = {}

    for si, step in enumerate(cfg.STEPS):
        seen: set[int] = set()
        for typ in cfg.TYPES:
            path = cfg.raw_path(date, typ, step)
            if not path.exists():
                raise CheckFailed(f"missing raw file {path.name}")
            members, pack = read_india_subset(path, date, step, typ)
            packing[f"{typ}_{step}"] = pack
            for number, field in members.items():
                if number in seen:
                    raise CheckFailed(
                        f"step {step}: perturbationNumber {number} seen twice"
                    )
                seen.add(number)
                tp[si, number] = field

        # SPEC 2.6 point 1: members 0-50, each exactly once, at every step.
        if seen != set(cfg.MEMBERS):
            missing = sorted(set(cfg.MEMBERS) - seen)
            extra = sorted(seen - set(cfg.MEMBERS))
            raise CheckFailed(
                f"step {step}: members wrong. missing={missing} extra={extra}"
            )

    if not np.isfinite(tp).all():
        raise CheckFailed("assembled array still contains non-finite values")

    return tp, packing


def write_and_verify(date: str, tp: np.ndarray) -> Path:
    """Write the .part file, reopen it, check it, then rename it.

    Returns the final path. Raises CheckFailed if the reopened file does not
    match what was written.
    """
    part = cfg.part_path(date)
    final = cfg.india_path(date)
    part.parent.mkdir(parents=True, exist_ok=True)

    if part.exists():
        part.unlink()

    np.savez(
        part,
        tp=tp,
        steps=np.asarray(cfg.STEPS, dtype=np.int32),
        members=np.asarray(cfg.MEMBERS, dtype=np.int32),
        lat=np.asarray(cfg.INDIA_LATS, dtype=np.float64),
        lon=np.asarray(cfg.INDIA_LONS, dtype=np.float64),
    )

    # np.savez appends .npz if the name does not already end in it. Our name
    # ends in .part, so it becomes <date>.npz.part.npz. Normalise that.
    written = part if part.exists() else Path(str(part) + ".npz")
    if written != part:
        written.replace(part)

    # Reopen from disk and check, rather than trusting what we just wrote.
    with np.load(part) as f:
        got = f["tp"]
        if got.shape != tp.shape:
            raise CheckFailed(f"reopened shape {got.shape} != {tp.shape}")
        if got.dtype != np.float32:
            raise CheckFailed(f"reopened dtype {got.dtype} is not float32")
        if not np.isfinite(got).all():
            raise CheckFailed("reopened file contains non-finite values")
        if not np.array_equal(got, tp):
            raise CheckFailed("reopened values differ from what was written")
        if not np.array_equal(f["steps"], np.asarray(cfg.STEPS)):
            raise CheckFailed("reopened steps are wrong")
        if not np.array_equal(f["members"], np.asarray(cfg.MEMBERS)):
            raise CheckFailed("reopened member ids are wrong")

    part.replace(final)
    return final


def process_date(date: str) -> dict:
    """Build, verify and save one date. Returns a record for the done file."""
    t0 = time.time()

    raw_sizes = {
        p.name: p.stat().st_size
        for p in sorted(cfg.raw_dir(date).glob("*.grib2"))
    }

    tp, packing = build_india_array(date)
    t_read = time.time()

    diff_summary = check_daily_differences(tp)

    final = write_and_verify(date, tp)
    t_write = time.time()

    # Packing is logged, never a failure reason (SPEC 2.6 point 1).
    bits = sorted({m["bitsPerValue"] for v in packing.values() for m in v})
    types = sorted({m["packingType"] for v in packing.values() for m in v})
    origins = sorted({m["longitudeOfFirstGridPoint"]
                      for v in packing.values() for m in v})

    return {
        "date": date,
        "india_file": final.name,
        "india_bytes": final.stat().st_size,
        "raw_files": len(raw_sizes),
        "raw_bytes": sum(raw_sizes.values()),
        "raw_sizes": raw_sizes,
        "shape": list(tp.shape),
        "shape_meaning": "(step, member, lat, lon), accumulated mm",
        "steps": list(cfg.STEPS),
        "members": [min(cfg.MEMBERS), max(cfg.MEMBERS)],
        "accumulated_max_mm": round(float(tp.max()), 4),
        "daily_differences": diff_summary,
        "packing": {"bitsPerValue": bits, "packingType": types},
        "longitude_origin": origins,
        "seconds_read_and_check": round(t_read - t0, 2),
        "seconds_write_and_verify": round(t_write - t_read, 2),
    }


def daily_totals(tp: np.ndarray) -> np.ndarray:
    """Daily totals from the accumulated field, with the SPEC 3.6 clamp.

    Returns float32 shaped (5 days, 51 members, 129, 121).
    """
    diffs = np.diff(tp, axis=0)
    # From -0.1 to 0 is 16-bit packing noise and becomes 0 (SPEC 3.6).
    return np.where(diffs < 0, 0.0, diffs).astype(np.float32)
