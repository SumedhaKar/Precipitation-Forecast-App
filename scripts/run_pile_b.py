"""Run Pile B: NASA IMERG Late daily files, one date at a time.

SPEC 2.3 and 2.4. Files are kept, not deleted: processing comes later.

Usage
  python scripts/run_pile_b.py                  everything from 14 May 2026
  python scripts/run_pile_b.py --dates 20260514
  python scripts/run_pile_b.py --limit 5
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                         # noqa: E402
from pipeline.nasa_download import (                       # noqa: E402
    download_date,
    existing_file,
    force_requests_timeout,
    imerg_dir,
    imerg_done_path,
    imerg_failure_path,
)

PILE_B_START = "20260514"   # SPEC 2.4: one day after Pile A starts
CONNECTIONS = 4

_print_lock = threading.Lock()
_stop = threading.Event()
LOG_FILE = cfg.LOGS / "pile_b.log"


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    with _print_lock:
        print(line, flush=True)
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def date_range(start: str, end: str) -> list[str]:
    d = dt.datetime.strptime(start, "%Y%m%d").date()
    last = dt.datetime.strptime(end, "%Y%m%d").date()
    out = []
    while d <= last:
        out.append(d.strftime("%Y%m%d"))
        d += dt.timedelta(days=1)
    return out


def free_gb() -> float:
    return shutil.disk_usage(cfg.ROOT).free / 1e9


def clear_parts() -> int:
    """Throw away leftovers from an interrupted run."""
    removed = 0
    d = imerg_dir()
    if d.is_dir():
        for p in list(d.glob("*.part")) + list(d.glob("imerg_*")):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
            removed += 1
    return removed


def run_date(date: str) -> str:
    t0 = time.time()
    try:
        record = download_date(date)
    except Exception as exc:
        imerg_failure_path(date).write_text(json.dumps({
            "date": date,
            "failed_at": dt.datetime.now().isoformat(timespec="seconds"),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "seconds": round(time.time() - t0, 2),
        }, indent=2), encoding="utf-8")
        log(f"imerg {date}  FAILED: {type(exc).__name__}: {exc}")
        return "failed"

    record["date"] = date
    record["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
    record["seconds"] = round(time.time() - t0, 2)
    record["free_gb_after"] = round(free_gb(), 2)
    imerg_failure_path(date).unlink(missing_ok=True)
    imerg_done_path(date).write_text(json.dumps(record, indent=2),
                                     encoding="utf-8")
    log(f"imerg {date}  done in {record['seconds']:.0f}s, "
        f"{record['bytes'] / 1e6:.1f} MB, {free_gb():.1f} GB free")
    return "done"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*")
    ap.add_argument("--start", default=PILE_B_START)
    ap.add_argument("--end-date")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    cfg.ensure_dirs()
    imerg_dir().mkdir(parents=True, exist_ok=True)
    force_requests_timeout()

    import earthaccess
    earthaccess.login(strategy="netrc")
    log("authenticated to Earthdata from netrc")

    removed = clear_parts()
    if removed:
        log(f"cleared {removed} leftover part file(s) or temp folder(s)")

    if args.dates:
        wanted = list(args.dates)
    else:
        end = args.end_date
        if not end:
            from scripts.run_pile_a import latest_imerg_date
            end = latest_imerg_date()
            log(f"latest IMERG day available is {end}")
        wanted = date_range(args.start, end)
    log(f"{len(wanted)} date(s) from {wanted[0]} to {wanted[-1]}")

    (cfg.LOGS / "pile_b_manifest.json").write_text(json.dumps({
        "written_at": dt.datetime.now().isoformat(timespec="seconds"),
        "total": len(wanted),
        "first_date": wanted[0],
        "last_date": wanted[-1],
    }, indent=2), encoding="utf-8")

    # Skip a date that already has a done record and whose file is still there.
    pending = [
        d for d in wanted
        if not (imerg_done_path(d).exists() and existing_file(d))
    ]
    if len(wanted) - len(pending):
        log(f"skipping {len(wanted) - len(pending)} date(s) already downloaded")
    if args.limit:
        pending = pending[: args.limit]

    if not pending:
        log("nothing to do")
        return 0

    log(f"starting: {len(pending)} date(s), {CONNECTIONS} connections, "
        f"{free_gb():.1f} GB free")

    counts = {"done": 0, "failed": 0, "skipped": 0}
    t0 = time.time()

    def worker(date: str) -> None:
        if _stop.is_set():
            counts["skipped"] += 1
            return
        if free_gb() < cfg.MIN_FREE_GB:
            log(f"STOPPING: only {free_gb():.1f} GB free, below the "
                f"{cfg.MIN_FREE_GB} GB floor")
            _stop.set()
            counts["skipped"] += 1
            return
        counts[run_date(date)] += 1
        n = counts["done"] + counts["failed"]
        if n % 10 == 0 or n == len(pending):
            rate = (time.time() - t0) / max(n, 1)
            log(f"progress {n}/{len(pending)}  done={counts['done']} "
                f"failed={counts['failed']}  "
                f"about {(len(pending) - n) * rate / 60:.0f} min left")

    with ThreadPoolExecutor(CONNECTIONS) as pool:
        try:
            list(pool.map(worker, pending))
        except KeyboardInterrupt:
            _stop.set()
            log("interrupted, finishing dates already in flight")

    log(f"finished: done={counts['done']} failed={counts['failed']} "
        f"skipped={counts['skipped']} in {(time.time() - t0) / 60:.1f} min")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
