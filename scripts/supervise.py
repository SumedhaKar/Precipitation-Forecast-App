"""Watch a pile run and restart it if it stalls.

Written after the night of 11-12 November 2026, when a Wi-Fi drop at 02:05
froze Pile A for 7 hours 24 minutes. The 120 second socket read timeout did
not catch it: the .part files simply stopped growing at 02:11 and nothing
moved or errored until the sockets finally aborted at 09:35.

This runs as its own detached process so that the download code is never
edited while a run is using it. It only ever kills and relaunches; it does
not touch data.

Usage
  python scripts/supervise.py a        supervise Pile A
  python scripts/supervise.py b        supervise Pile B
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg  # noqa: E402

CHECK_EVERY = 120          # seconds between checks
STALL_LIMIT = 600          # no progress for this long means stalled
MAX_RESTARTS = 10

NETWORK_ERRORS = (
    "ConnectionError",
    "ConnectionAbortedError",
    "ConnectionAborted",
    "IncompleteRead",
    "Timeout",
    "ReadTimeout",
    "ConnectionResetError",
)

LOG = cfg.LOGS / "supervisor.log"

PILES = {
    "a": {
        "name": "Pile A",
        "script": "scripts/run_pile_a.py",
        "log": cfg.LOGS / "pile_a.log",
        "pid": cfg.LOGS / "pile_a.pid",
        "out": cfg.LOGS / "pile_a.out",
        "err": cfg.LOGS / "pile_a.err",
        "manifest": cfg.LOGS / "pile_a_manifest.json",
        "done_glob": "2*.json",
        "failure_glob": "2*.json",
        "part_globs": ["raw/2*/*.part", "india/ecmwf/*.part"],
    },
    "b": {
        "name": "Pile B",
        "script": "scripts/run_pile_b.py",
        "log": cfg.LOGS / "pile_b.log",
        "pid": cfg.LOGS / "pile_b.pid",
        "out": cfg.LOGS / "pile_b.out",
        "err": cfg.LOGS / "pile_b.err",
        "manifest": cfg.LOGS / "pile_b_manifest.json",
        "done_glob": "imerg_*.json",
        "failure_glob": "imerg_*.json",
        "part_globs": ["raw/imerg/*.part"],
    },
}


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def newest_activity(pile: dict) -> float:
    """Most recent sign of life: the log file, or any .part still growing.

    Returns a unix timestamp. Uses modification times rather than parsing the
    log, so a run that is downloading steadily but has not finished a date for
    ten minutes still counts as alive.
    """
    newest = 0.0
    if pile["log"].exists():
        newest = max(newest, pile["log"].stat().st_mtime)
    for pattern in pile["part_globs"]:
        for p in cfg.DATA.glob(pattern):
            try:
                newest = max(newest, p.stat().st_mtime)
            except OSError:
                pass
    return newest


def is_running(pile: dict) -> tuple[bool, int | None]:
    if not pile["pid"].exists():
        return False, None
    try:
        process_id = int(pile["pid"].read_text().strip())
    except (ValueError, OSError):
        return False, None

    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {process_id}", "/NH"],
        capture_output=True, text=True,
    )
    return (str(process_id) in result.stdout), process_id


def kill(process_id: int) -> None:
    subprocess.run(["taskkill", "/PID", str(process_id), "/F", "/T"],
                   capture_output=True, text=True)


def launch(pile: dict) -> int:
    """Relaunch the pile detached. It resumes from its done records."""
    out = open(pile["out"], "ab")
    err = open(pile["err"], "ab")
    process = subprocess.Popen(
        [str(cfg.ROOT / ".venv" / "Scripts" / "python.exe"), pile["script"]],
        cwd=str(cfg.ROOT), stdout=out, stderr=err, stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
    pile["pid"].write_text(str(process.pid), encoding="ascii")
    return process.pid


def counts(pile: dict) -> tuple[int, int, int]:
    """(done, failed, total)."""
    done = len(list(cfg.DONE.glob(pile["done_glob"])))
    failed = len(list(cfg.FAILURES.glob(pile["failure_glob"])))
    total = 0
    if pile["manifest"].exists():
        try:
            total = json.loads(pile["manifest"].read_text())["total"]
        except (ValueError, KeyError, OSError):
            total = 0
    return done, failed, total


def failure_error_types(pile: dict) -> list[str]:
    types = []
    for p in cfg.FAILURES.glob(pile["failure_glob"]):
        try:
            record = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            types.append("unreadable")
            continue
        types.append(f"{record.get('error_type', '')}: {record.get('error', '')}")
    return types


def is_network_error(text: str) -> bool:
    return any(marker in text for marker in NETWORK_ERRORS)


def archive_failures(pile: dict) -> int:
    """Move failure records aside so the dates are retried. Evidence is kept."""
    archived_dir = cfg.FAILURES / "archived"
    archived_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    moved = 0
    for p in list(cfg.FAILURES.glob(pile["failure_glob"])):
        p.rename(archived_dir / f"{p.stem}_{stamp}{p.suffix}")
        moved += 1
    return moved


def main() -> int:
    key = (sys.argv[1] if len(sys.argv) > 1 else "a").lower()
    if key not in PILES:
        sys.exit(f"unknown pile {key!r}, expected 'a' or 'b'")
    pile = PILES[key]

    restarts = 0
    retried_network_failures = False

    log(f"supervisor started for {pile['name']}: checking every "
        f"{CHECK_EVERY}s, stall limit {STALL_LIMIT}s, "
        f"at most {MAX_RESTARTS} restarts")

    while True:
        time.sleep(CHECK_EVERY)

        done, failed, total = counts(pile)
        running, process_id = is_running(pile)

        # Everything finished.
        if total and done >= total:
            log(f"{pile['name']} complete: {done}/{total} done. Supervisor stopping.")
            return 0

        if running:
            quiet = time.time() - newest_activity(pile)
            if quiet <= STALL_LIMIT:
                continue

            if restarts >= MAX_RESTARTS:
                log(f"STALLED for {quiet / 60:.1f} min but already restarted "
                    f"{restarts} times, the limit. Supervisor stopping without "
                    "restarting. This needs a person.")
                return 1

            restarts += 1
            log(f"watchdog restart {restarts}/{MAX_RESTARTS}: reason = no "
                f"progress for {quiet / 60:.1f} min (log and every .part file "
                f"untouched); killing PID {process_id}")
            kill(process_id)
            time.sleep(5)
            new_pid = launch(pile)
            log(f"watchdog restart {restarts}/{MAX_RESTARTS}: relaunched "
                f"{pile['name']} as PID {new_pid}, it resumes from "
                f"{done} done")
            continue

        # Not running, and not finished.
        if failed:
            types = failure_error_types(pile)
            all_network = all(is_network_error(t) for t in types)
            if all_network and not retried_network_failures:
                retried_network_failures = True
                moved = archive_failures(pile)
                log(f"{pile['name']} ended with {failed} failure(s), all "
                    f"network errors. Archived {moved} record(s) and "
                    "relaunching once more.")
                new_pid = launch(pile)
                log(f"relaunched {pile['name']} as PID {new_pid}")
                continue
            if not all_network:
                other = sorted({t.split(':')[0] for t in types
                                if not is_network_error(t)})
                log(f"{pile['name']} ended with {failed} failure(s) including "
                    f"non-network errors ({', '.join(other)}). Leaving them "
                    "for a person. Supervisor stopping.")
                return 1
            log(f"{pile['name']} ended with {failed} network failure(s) and "
                "the one extra attempt is already used. Supervisor stopping.")
            return 1

        if restarts >= MAX_RESTARTS:
            log(f"{pile['name']} is not running and the restart limit of "
                f"{MAX_RESTARTS} is reached. Supervisor stopping.")
            return 1

        restarts += 1
        log(f"watchdog restart {restarts}/{MAX_RESTARTS}: reason = process not "
            f"running, {done}/{total} done, no failure records")
        new_pid = launch(pile)
        log(f"watchdog restart {restarts}/{MAX_RESTARTS}: relaunched "
            f"{pile['name']} as PID {new_pid}")


if __name__ == "__main__":
    sys.exit(main())
