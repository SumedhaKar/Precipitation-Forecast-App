"""Run Pile A: historical AIFS ENS 00 UTC forecasts, one date at a time.

SPEC 2.6. One date is one unit of work. A date is only "done" when its India
subset has been written, reopened, checked and renamed, and its raw GRIB files
deleted. Anything less leaves no done record, so a rerun simply redoes it.

Usage
  python scripts/run_pile_a.py                     run the whole pile
  python scripts/run_pile_a.py --dates 20260513    run named dates only
  python scripts/run_pile_a.py --limit 5           run the first 5 pending
  python scripts/run_pile_a.py --end-date 20261106 skip the IMERG lookup
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                      # noqa: E402
from pipeline.checks import CheckFailed                 # noqa: E402
from pipeline.ecmwf_download import (                   # noqa: E402
    ConnectionLimiter,
    download_one,
    files_for_date,
)
from pipeline.ecmwf_process import process_date         # noqa: E402

_print_lock = threading.Lock()
_stop = threading.Event()


LOG_FILE = cfg.LOGS / "pile_a.log"


def log(message: str) -> None:
    """Print, and append to pile_a.log.

    The file is opened in append mode on purpose. A detached restart would
    otherwise truncate the log and lose the history of what happened before
    the interruption, which is exactly what we need to inspect afterwards.
    """
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    with _print_lock:
        print(line, flush=True)
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # logging must never bring down the run


# --------------------------------------------------------------- date list

def date_range(start: str, end: str) -> list[str]:
    d = dt.datetime.strptime(start, "%Y%m%d").date()
    last = dt.datetime.strptime(end, "%Y%m%d").date()
    out = []
    while d <= last:
        out.append(d.strftime("%Y%m%d"))
        d += dt.timedelta(days=1)
    return out


def spread_order(dates: list[str]) -> list[str]:
    """Every 4th date, then every 2nd not yet taken, then the rest.

    SPEC 2.6: any prefix of this order is a roughly even sample of the whole
    period, so stopping early does not bias the track record towards one season.
    """
    taken: set[int] = set()
    order: list[str] = []
    for stride in (4, 2, 1):
        for i in range(0, len(dates), stride):
            if i not in taken:
                taken.add(i)
                order.append(dates[i])
    return order


def latest_imerg_date() -> str:
    """Latest IMERG Late daily date that exists right now, as YYYYMMDD."""
    import earthaccess

    earthaccess.login(strategy="netrc")
    today = dt.date.today()
    results = earthaccess.search_data(
        short_name="GPM_3IMERGDL",
        version="07",
        temporal=((today - dt.timedelta(days=30)).isoformat(), today.isoformat()),
    )
    if not results:
        raise RuntimeError("no IMERG granules found in the last 30 days")

    dates = []
    for r in results:
        try:
            start = r["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"]
            dates.append(start[:10].replace("-", ""))
        except (KeyError, TypeError):
            continue
    if not dates:
        raise RuntimeError("IMERG granules had no readable dates")
    return max(dates)


def last_start_date(latest_imerg: str) -> str:
    """A start date D needs IMERG for D+5, so the last usable D is latest - 5.

    SPEC 1.3: Day 5 covers steps 120-144, which is the 24 hours beginning
    5 days after the run date.
    """
    d = dt.datetime.strptime(latest_imerg, "%Y%m%d").date()
    return (d - dt.timedelta(days=5)).strftime("%Y%m%d")


# ------------------------------------------------------------------ safety

def free_gb() -> float:
    return shutil.disk_usage(cfg.ROOT).free / 1e9


def clear_parts(date: str) -> list[str]:
    """Throw away leftovers from an interrupted run (SPEC 2.6 point 5)."""
    removed = []
    part = cfg.part_path(date)
    if part.exists():
        part.unlink()
        removed.append(part.name)
    raw = cfg.raw_dir(date)
    if raw.is_dir():
        for p in raw.glob("*.part"):
            p.unlink()
            removed.append(p.name)
    return removed


def delete_raw(date: str) -> dict:
    """Delete one date's raw GRIB files. Only ever called after the rename.

    This is the single deletion covered by standing approval (SPEC 2.6).
    """
    raw = cfg.raw_dir(date)
    if not raw.is_dir():
        return {"deleted_files": 0, "deleted_bytes": 0}
    files = sorted(raw.glob("*.grib2"))
    total = sum(p.stat().st_size for p in files)
    names = [p.name for p in files]
    for p in files:
        p.unlink()
    try:
        raw.rmdir()
    except OSError:
        pass
    return {
        "deleted_files": len(names),
        "deleted_bytes": total,
        "deleted_names": names,
    }


# ------------------------------------------------------------- one date

def run_date(date: str, pool: ThreadPoolExecutor, limiter: ConnectionLimiter,
             keep_raw: bool) -> str:
    """Download, check, subset and save one date. Returns 'done' or 'failed'."""
    t0 = time.time()
    removed = clear_parts(date)
    if removed:
        log(f"{date}  cleared {len(removed)} leftover .part file(s)")

    try:
        futures = {
            pool.submit(download_one, d, typ, step,
                        cfg.ARCHIVE_SOURCE, limiter): (typ, step)
            for (d, typ, step) in files_for_date(date)
        }
        for fut in as_completed(futures):
            typ, step = futures[fut]
            try:
                fut.result()
            except Exception as exc:
                limiter.record_error(log)
                raise RuntimeError(
                    f"{typ} step {step} failed after "
                    f"{cfg.MAX_RETRIES} retries: {exc}"
                ) from exc

        record = process_date(date)

    except Exception as exc:
        failure = {
            "date": date,
            "failed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "raw_kept_for_inspection": True,
            "seconds": round(time.time() - t0, 2),
        }
        cfg.failure_path(date).write_text(
            json.dumps(failure, indent=2), encoding="utf-8"
        )
        log(f"{date}  FAILED: {type(exc).__name__}: {exc}")
        log(f"{date}  raw files kept for inspection in {cfg.raw_dir(date)}")
        return "failed"

    # Success. Raw files go only now, after the rename and all checks.
    if keep_raw:
        record["deletion"] = {"skipped": "kept by --keep-raw for hand checks"}
        log(f"{date}  raw files KEPT (--keep-raw)")
    else:
        record["deletion"] = delete_raw(date)
        log(f"{date}  deleted {record['deletion']['deleted_files']} raw files, "
            f"{record['deletion']['deleted_bytes'] / 1e6:.1f} MB")

    record["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    record["seconds_total"] = round(time.time() - t0, 2)
    record["free_gb_after"] = round(free_gb(), 2)
    record["connections"] = limiter.limit

    cfg.failure_path(date).unlink(missing_ok=True)
    cfg.done_path(date).write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    log(f"{date}  done in {record['seconds_total']:.0f}s, "
        f"{record['india_bytes'] / 1e6:.1f} MB saved, "
        f"{free_gb():.1f} GB free")
    return "done"


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", help="explicit dates, YYYYMMDD")
    ap.add_argument("--start", default=cfg.PILE_A_START)
    ap.add_argument("--end-date", help="last start date; skips the IMERG lookup")
    ap.add_argument("--limit", type=int, help="process at most this many dates")
    ap.add_argument("--keep-raw", action="store_true",
                    help="do not delete raw GRIB after success")
    args = ap.parse_args()

    cfg.ensure_dirs()

    if args.dates:
        wanted = list(args.dates)
        log(f"explicit dates: {', '.join(wanted)}")
    else:
        end = args.end_date
        if not end:
            latest = latest_imerg_date()
            end = last_start_date(latest)
            log(f"latest IMERG day is {latest}, so the last start date is {end}")
        wanted = spread_order(date_range(args.start, end))
        log(f"{len(wanted)} dates from {args.start} to {end}, spread order")

    # A manifest so the progress command knows the denominator.
    (cfg.LOGS / "pile_a_manifest.json").write_text(
        json.dumps({
            "written_at": dt.datetime.now().isoformat(timespec="seconds"),
            "total": len(wanted),
            "first_date": wanted[0] if wanted else None,
            "last_date": wanted[-1] if wanted else None,
            "order": "spread" if not args.dates else "explicit",
        }, indent=2),
        encoding="utf-8",
    )

    pending = [d for d in wanted if not cfg.done_path(d).exists()]
    already = len(wanted) - len(pending)
    if already:
        log(f"skipping {already} date(s) that already have a done record")
    if args.limit:
        pending = pending[: args.limit]
        log(f"limited to {len(pending)} date(s) this run")

    if not pending:
        log("nothing to do")
        return 0

    log(f"starting: {len(pending)} date(s), {cfg.MAX_CONNECTIONS} connections, "
        f"{cfg.DATES_IN_FLIGHT} dates in flight, {free_gb():.1f} GB free")

    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS)
    counts = {"done": 0, "failed": 0, "skipped": 0}
    t0 = time.time()

    with ThreadPoolExecutor(cfg.MAX_CONNECTIONS) as downloads, \
            ThreadPoolExecutor(cfg.DATES_IN_FLIGHT) as dates:

        def worker(date: str) -> None:
            if _stop.is_set():
                counts["skipped"] += 1
                return
            if free_gb() < cfg.MIN_FREE_GB:
                log(f"STOPPING: only {free_gb():.1f} GB free, "
                    f"below the {cfg.MIN_FREE_GB} GB floor (SPEC 2.6)")
                _stop.set()
                counts["skipped"] += 1
                return
            counts[run_date(date, downloads, limiter, args.keep_raw)] += 1
            n = counts["done"] + counts["failed"]
            rate = (time.time() - t0) / max(n, 1)
            left = len(pending) - n
            log(f"progress {n}/{len(pending)}  done={counts['done']} "
                f"failed={counts['failed']}  "
                f"about {left * rate / 3600:.1f} h left")

        try:
            list(dates.map(worker, pending))
        except KeyboardInterrupt:
            _stop.set()
            log("interrupted, finishing dates already in flight")

    log(f"finished: done={counts['done']} failed={counts['failed']} "
        f"skipped={counts['skipped']} in {(time.time() - t0) / 60:.1f} min")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
