"""The live forecast run: fetch one 00 UTC AIFS ENS run and build the product.

SPEC 2 for the data and its checks, SPEC 4 for the product, SPEC 4.6 for what
this writes. Nothing here publishes anything.

Three things this module is careful about:

1. It reuses the Pile A downloader and the Pile A checks unchanged. The whole
   point of an honest track record is that the live forecast is produced by
   the same code that produced the archive it is judged against.
2. A run is used only when it is complete. 51 members at all 6 steps, or the
   run is abandoned and the previous one stays (SPEC 1.5).
3. It runs on Linux in GitHub Actions with no login. ECMWF open data needs no
   credential, there is no netrc, no token and no interactive step.

Usage
  python -m pipeline.run_live                 build the latest complete run
  python -m pipeline.run_live --dry-run       decide which run, download none
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config as cfg
from .checks import (
    CheckFailed,
    check_daily_differences,
    check_quantum_cap,
)
from .ecmwf_download import download_one, files_for_date, make_client
from .ecmwf_process import build_india_array, daily_totals, quantum_summary

# ------------------------------------------------------------------ numbers

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")

# SPEC 4.2. ">=" throughout: 10.0 mm counts towards the 10 mm threshold.
THRESHOLDS = (1.0, 10.0, 50.0)

# SPEC 4.3. Four categories, left-closed, so the edges belong upwards and
# every member falls in exactly one.
DOT_EDGES = (1.0, 10.0, 50.0)
DOT_NAMES = ("under 1 mm", "1 to under 10 mm", "10 to under 50 mm",
             "50 mm or more")

LIVE = cfg.DATA / "live"
STATE = LIVE / "last_run.json"

LIVE_CONNECTIONS = 4        # polite while Pile A is using the other four
LOOK_BACK_DAYS = 3          # how far back a listing is built


class LiveRunError(Exception):
    """The live run cannot produce a complete, checked forecast."""


# --------------------------------------------------- lead days and IST labels

def lead_days() -> tuple[int, ...]:
    return tuple(range(1, cfg.N_DAYS + 1))


def lead_day_steps(lead_day: int) -> tuple[int, int]:
    """Lead day n is forecast steps 24n to 24(n+1) (SPEC 1.3)."""
    if not isinstance(lead_day, int) or isinstance(lead_day, bool):
        raise LiveRunError(f"lead day must be an int, got {lead_day!r}")
    if not 1 <= lead_day <= cfg.N_DAYS:
        raise LiveRunError(
            f"lead day {lead_day} is outside 1 to {cfg.N_DAYS}")
    return 24 * lead_day, 24 * (lead_day + 1)


def window_utc(run_date: str, lead_day: int) -> tuple[dt.datetime, dt.datetime]:
    """The 00 UTC to 00 UTC window this lead day covers."""
    lead_day_steps(lead_day)
    start = (dt.datetime.strptime(run_date, "%Y%m%d")
             .replace(tzinfo=dt.timezone.utc)
             + dt.timedelta(days=lead_day))
    return start, start + dt.timedelta(days=1)


def window_ist(run_date: str, lead_day: int) -> tuple[dt.datetime, dt.datetime]:
    start, end = window_utc(run_date, lead_day)
    return start.astimezone(IST), end.astimezone(IST)


def clock_ist(when: dt.datetime) -> str:
    """"5:30 am", derived from the time rather than written out."""
    hour = when.hour % 12 or 12
    suffix = "am" if when.hour < 12 else "pm"
    return f"{hour}:{when.minute:02d} {suffix}"


def day_label(run_date: str, lead_day: int) -> str:
    """SPEC 1.2: "5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov"."""
    start, end = window_ist(run_date, lead_day)
    return (f"{clock_ist(start)} {start:%a} {start.day} {start:%b} to "
            f"{clock_ist(end)} {end:%a} {end.day} {end:%b}")


def day_records(run_date: str) -> list[dict]:
    out = []
    for lead in lead_days():
        from_step, to_step = lead_day_steps(lead)
        start_utc, end_utc = window_utc(run_date, lead)
        start_ist, end_ist = window_ist(run_date, lead)
        out.append({
            "lead_day": lead,
            "steps": [from_step, to_step],
            "from_utc": start_utc.isoformat(),
            "to_utc": end_utc.isoformat(),
            "from_ist": start_ist.isoformat(),
            "to_ist": end_ist.isoformat(),
            "label": day_label(run_date, lead),
        })
    return out


# ------------------------------------------------------------------ run ids

def run_id_for(date: str, hour: int = cfg.RUN_TIME) -> str:
    return f"{date}T{hour:02d}Z"


def parse_run_id(run_id: str) -> tuple[str, int]:
    """("20261112", 0) from "20261112T00Z". Raises on anything else."""
    text = str(run_id)
    if len(text) != 12 or text[8] != "T" or text[11] != "Z":
        raise LiveRunError(f"{run_id!r} is not a run id like 20261112T00Z")
    date, hour = text[:8], text[9:11]
    try:
        dt.datetime.strptime(date, "%Y%m%d")
        return date, int(hour)
    except ValueError as exc:
        raise LiveRunError(f"{run_id!r} is not a run id: {exc}") from exc


def run_time_ist(run_id: str) -> dt.datetime:
    date, hour = parse_run_id(run_id)
    return (dt.datetime.strptime(date, "%Y%m%d")
            .replace(hour=hour, tzinfo=dt.timezone.utc)
            .astimezone(IST))


# ------------------------------------------------------------ run selection

@dataclass(frozen=True)
class RunOption:
    """One run the server offers, and whether every file of it is there."""
    run_id: str
    complete: bool


def select_run(listing, published: str | None = None) -> tuple[str | None, str]:
    """Which run to build, and why. Pure: no network, no disk (SPEC 4.6).

    The three rules, in the order they bite:

    - only 00 UTC runs are eligible at all,
    - an incomplete run is never used; the previous complete one stays,
    - a run is never built if one at least as new has already been built,
      which covers both "no older run replaces a newer one" and "the same
      run is never republished".
    """
    options = [RunOption(o.run_id, o.complete) if isinstance(o, RunOption)
               else RunOption(str(o["run_id"]), bool(o["complete"]))
               for o in listing]

    valid = []
    for option in options:
        try:
            _, hour = parse_run_id(option.run_id)
        except LiveRunError:
            continue
        if hour != cfg.RUN_TIME:
            continue
        valid.append(option)

    if not valid:
        return None, f"no {cfg.RUN_TIME:02d} UTC run in the listing"

    valid.sort(key=lambda o: o.run_id, reverse=True)
    complete = [o for o in valid if o.complete]
    if not complete:
        return None, (f"the only {cfg.RUN_TIME:02d} UTC run(s) offered "
                      f"({', '.join(o.run_id for o in valid)}) are incomplete")

    newest = complete[0]
    skipped = [o.run_id for o in valid if o.run_id > newest.run_id]

    if published is not None:
        parse_run_id(published)
        if newest.run_id == published:
            return None, f"{newest.run_id} has already been built"
        if newest.run_id < published:
            return None, (f"{newest.run_id} is older than the run already "
                          f"built, {published}; an older run never replaces "
                          "a newer one")

    reason = f"{newest.run_id} is the newest complete {cfg.RUN_TIME:02d} UTC run"
    if skipped:
        reason += (f"; {', '.join(skipped)} offered but incomplete, so the "
                   "previous run is used")
    if published is not None:
        reason += f"; last built was {published}"
    return newest.run_id, reason


def last_built() -> str | None:
    if not STATE.exists():
        return None
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))["run_id"]
    except (ValueError, KeyError, OSError):
        return None


def record_built(run_id: str) -> None:
    LIVE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "run_id": run_id,
        "built_at_ist": dt.datetime.now(IST).isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")


def server_listing(source: str = cfg.LIVE_SOURCE,
                   look_back: int = LOOK_BACK_DAYS) -> list[RunOption]:
    """What the server offers, as a listing select_run can decide on.

    ``Client.latest`` walks back from today and returns the most recent run
    for which **every** file of the request is present, which is exactly the
    file-level completeness test. Any 00 UTC day newer than that is therefore
    offered but incomplete, and is listed as such so the decision and its
    reason are visible rather than implied.
    """
    client = make_client(source)
    latest = client.latest(
        time=cfg.RUN_TIME,
        stream=cfg.STREAM,
        type=list(cfg.TYPES),
        param=cfg.PARAM,
        step=list(cfg.STEPS),
    )
    latest_date = latest.strftime("%Y%m%d")

    listing = [RunOption(run_id_for(latest_date), True)]
    today = dt.datetime.now(dt.timezone.utc).date()
    day = dt.datetime.strptime(latest_date, "%Y%m%d").date()
    while day < today:
        day += dt.timedelta(days=1)
        listing.append(RunOption(run_id_for(day.strftime("%Y%m%d")), False))
    return listing[:look_back + 1]


# ------------------------------------------------------------------ the run

def download_run(date: str, source: str = cfg.LIVE_SOURCE,
                 connections: int = LIVE_CONNECTIONS) -> dict:
    """Fetch every file of one run with the Pile A downloader, unchanged."""
    wanted = files_for_date(date)
    started = time.time()
    with ThreadPoolExecutor(max_workers=connections) as pool:
        paths = list(pool.map(
            lambda job: download_one(*job, source=source), wanted))
    elapsed = time.time() - started
    sizes = {p.name: p.stat().st_size for p in paths}
    return {
        "files": len(paths),
        "bytes": sum(sizes.values()),
        "sizes": sizes,
        "seconds": round(elapsed, 2),
        "connections": connections,
        "source": source,
    }


def check_run(date: str) -> tuple[np.ndarray, dict]:
    """Every Pile A check, on the live files. Returns (daily totals, record).

    Exactly the SPEC 2.5 and 3.6 checks, in the same code: units and identity
    per message, the India window from each file's own longitude origin,
    exactly 51 members at every step, the quantum-derived tolerance, the
    0.5 mm quantum cap and the negative-difference rule.
    """
    tp, packing = build_india_array(date)

    quanta = quantum_summary(packing)
    check_quantum_cap(quanta["coarsest_mm"])
    tolerance = cfg.tolerance_for(quanta["coarsest_mm"])
    differences = check_daily_differences(tp, tolerance)

    totals = daily_totals(tp, tolerance)

    members = sorted({m["perturbationNumber"]
                      for v in packing.values() for m in v})
    record = {
        "accumulated_shape": list(tp.shape),
        "accumulated_max_mm": round(float(tp.max()), 4),
        "daily_totals_shape": list(totals.shape),
        "daily_differences": differences,
        "packing": {
            "bitsPerValue": sorted({m["bitsPerValue"]
                                    for v in packing.values() for m in v}),
            "packingType": sorted({m["packingType"]
                                   for v in packing.values() for m in v}),
            "quantum_per_step_mm": quanta["per_step_mm"],
            "coarsest_quantum_mm": quanta["coarsest_mm"],
            "quantum_cap_mm": cfg.MAX_TRUSTED_QUANTUM,
            "tolerance_mm": tolerance,
        },
        "longitude_origin": sorted({m["longitudeOfFirstGridPoint"]
                                    for v in packing.values() for m in v}),
        "members_seen": len(members),
        "member_ids": [min(members), max(members)] if members else [],
    }
    if sorted(members) != list(cfg.MEMBERS):
        raise CheckFailed(
            f"{len(members)} distinct members, expected exactly "
            f"{cfg.N_MEMBERS} numbered 0 to {cfg.N_MEMBERS - 1}")
    return totals, record


# ------------------------------------------------------------- the product

def counts_from(totals: np.ndarray) -> np.ndarray:
    """Members at or above each threshold. (3, days, lat, lon) uint8."""
    if totals.ndim != 4 or totals.shape[1] != cfg.N_MEMBERS:
        raise LiveRunError(f"totals shaped {totals.shape}, expected "
                           f"(days, {cfg.N_MEMBERS}, lat, lon)")
    stacked = [np.count_nonzero(totals >= t, axis=1) for t in THRESHOLDS]
    return np.stack(stacked).astype(np.uint8)


def dots_from(totals: np.ndarray) -> np.ndarray:
    """SPEC 4.3's four categories. (4, days, lat, lon) uint8."""
    if totals.ndim != 4 or totals.shape[1] != cfg.N_MEMBERS:
        raise LiveRunError(f"totals shaped {totals.shape}, expected "
                           f"(days, {cfg.N_MEMBERS}, lat, lon)")
    low, mid, high = DOT_EDGES
    bands = [
        totals < low,
        (totals >= low) & (totals < mid),
        (totals >= mid) & (totals < high),
        totals >= high,
    ]
    return np.stack([np.count_nonzero(b, axis=1) for b in bands]).astype(np.uint8)


def build_product(totals: np.ndarray) -> dict:
    """One per-square record, with counts and dots derived from it.

    The member totals are the record. Counts and dots are both computed from
    that same array here, so the site cannot ever show a count that
    disagrees with its dots. The four identities below are asserted every
    run, not only in the tests.
    """
    counts = counts_from(totals)
    dots = dots_from(totals)

    if not np.all(dots.sum(axis=0) == cfg.N_MEMBERS):
        raise LiveRunError("the four dot categories do not add up to 51")
    if not np.array_equal(counts[0], dots[1] + dots[2] + dots[3]):
        raise LiveRunError("the 1 mm count disagrees with the dots")
    if not np.array_equal(counts[1], dots[2] + dots[3]):
        raise LiveRunError("the 10 mm count disagrees with the dots")
    if not np.array_equal(counts[2], dots[3]):
        raise LiveRunError("the 50 mm count disagrees with the dots")

    return {
        "member_totals": totals.astype(np.float32),
        "counts": counts,
        "dots": dots,
    }


def india_summary(product: dict) -> dict:
    """The highest count per threshold and day, over India squares only."""
    from .india_mask import load as load_mask

    india = load_mask()["india"]
    out = {}
    for k, threshold in enumerate(THRESHOLDS):
        per_day = []
        for d in range(product["counts"].shape[1]):
            layer = product["counts"][k, d]
            per_day.append(int(layer[india].max()))
        out[f"max_count_ge_{threshold:g}mm_by_lead_day"] = per_day
    out["india_squares"] = int(india.sum())
    return out


# ---------------------------------------------------------------- outputs

def run_dir(run_id: str) -> Path:
    return LIVE / run_id


def write_outputs(run_id: str, product: dict, days: list[dict],
                  checks: dict, download: dict) -> dict:
    """Write the run directory. The manifest is written last, on purpose.

    A reader can treat the presence of manifest.json as the only signal that
    everything else in the directory is finished and checked.
    """
    date, _ = parse_run_id(run_id)
    out = run_dir(run_id)
    out.mkdir(parents=True, exist_ok=True)

    from .india_mask import load as load_mask
    india = load_mask()["india"]

    squares = out / "squares.npz"
    part = squares.with_suffix(".npz.part")
    if part.exists():
        part.unlink()
    with open(part, "wb") as fh:
        np.savez_compressed(
            fh,
            member_totals=product["member_totals"],
            counts=product["counts"],
            dots=product["dots"],
            india=india,
            lat=np.asarray(cfg.INDIA_LATS, dtype=np.float64),
            lon=np.asarray(cfg.INDIA_LONS, dtype=np.float64),
        )
    with np.load(part) as f:
        for key in ("member_totals", "counts", "dots"):
            if not np.array_equal(f[key], product[key]):
                raise LiveRunError(f"{key} changed on the way to disk")
        if not np.array_equal(f["india"], india):
            raise LiveRunError("the India mask changed on the way to disk")
    part.replace(squares)

    (out / "days.json").write_text(json.dumps(days, indent=2),
                                   encoding="utf-8")

    # Keep the raw GRIB with the run rather than in Pile A's directory.
    raw_out = out / "raw"
    raw_out.mkdir(exist_ok=True)
    moved = []
    for path in sorted(cfg.raw_dir(date).glob("*.grib2")):
        target = raw_out / path.name
        path.replace(target)
        moved.append(target.name)
    try:
        cfg.raw_dir(date).rmdir()
    except OSError:
        pass

    published_at = dt.datetime.now(IST)
    manifest = {
        "run_id": run_id,
        "model": cfg.MODEL,
        "stream": cfg.STREAM,
        "param": cfg.PARAM,
        "steps": list(cfg.STEPS),
        "members": cfg.N_MEMBERS,
        "run_time_utc": run_time_ist(run_id).astimezone(
            dt.timezone.utc).isoformat(),
        "run_time_ist": run_time_ist(run_id).isoformat(),
        "publish_time_ist": published_at.isoformat(timespec="seconds"),
        "thresholds_mm": list(THRESHOLDS),
        "dot_categories": list(DOT_NAMES),
        "download": download,
        "checks": checks,
        "product": {
            "member_totals_shape": list(product["member_totals"].shape),
            "counts_shape": list(product["counts"].shape),
            "dots_shape": list(product["dots"].shape),
            "squares_file": squares.name,
            "squares_bytes": squares.stat().st_size,
        },
        "india": india_summary(product),
        "raw_files_kept": moved,
        "published": False,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                       encoding="utf-8")
    return manifest


def log(message: str) -> None:
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} IST  {message}"
    print(line, flush=True)
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    with open(cfg.LOGS / "run_live.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry_run = "--dry-run" in argv

    try:
        listing = server_listing()
        log("server offers: " + ", ".join(
            f"{o.run_id}{'' if o.complete else ' (incomplete)'}"
            for o in listing))
        run_id, reason = select_run(listing, last_built())
        log(f"decision: {reason}")
        if run_id is None:
            log("nothing to build; the previous run stays as it is")
            return 0
        if dry_run:
            log(f"--dry-run, so {run_id} was not downloaded")
            return 0

        date, _ = parse_run_id(run_id)
        log(f"{run_id}: downloading {len(files_for_date(date))} files from "
            f"{cfg.LIVE_SOURCE}")
        download = download_run(date)
        log(f"{run_id}: {download['bytes'] / 1e6:.1f} MB in "
            f"{download['seconds']}s on {download['connections']} connections")

        totals, checks = check_run(date)
        log(f"{run_id}: checks passed, tolerance "
            f"{checks['packing']['tolerance_mm']} mm, origin "
            f"{checks['longitude_origin']}")

        product = build_product(totals)
        manifest = write_outputs(run_id, product, day_records(date), checks,
                                 download)
        record_built(run_id)

        india = manifest["india"]
        log(f"{run_id}: built. day 1 highest count at 10 mm over India = "
            f"{india['max_count_ge_10mm_by_lead_day'][0]} of 51")
        log(f"{run_id}: wrote {run_dir(run_id)}, manifest last, not published")
        return 0
    except Exception as exc:                                # noqa: BLE001
        log(f"FAILED {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
