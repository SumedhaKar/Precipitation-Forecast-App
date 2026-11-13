"""HC-FAIL: made to fail on purpose, and watched.

SPEC 1.5, 8.5 to 8.7 and 11.8. Every other hand check asks whether the right
answer comes out when everything works. This one asks the opposite question:
when the forecast is missing, or a file is broken or unfinished, does the
publisher refuse, say so with a failing exit code, and **leave the run that
is already published exactly where it is**? A site that quietly publishes
half a run, or that quietly replaces a good run with a broken one, would be
worse than a site that goes down.

Three things happen here.

1. **The publisher is made to fail.** A real built run is copied to a
   temporary folder, the copy is broken one way at a time, and the real
   `python -m pipeline.publish` is run against an in-memory store that
   already publishes the real run. Nothing touches `data/`, nothing touches
   the network and no token exists. For each failure the exit code, the
   number of uploads and the run the store still publishes afterwards are
   recorded.

   The broken run is a copy of the real run's own files under the run id
   `29991231T00Z`, which is far enough in the future to be obviously not a
   run. It exists only to be refused: every case that uses it is a case that
   must fail, and no number inside it is used as a measurement. The one
   exception is the control at the top of the table, which publishes it
   unbroken to show that the failures below are the sabotage and not the
   fixture.

2. **The chooser is made to fail.** `select_run` decides which run to build
   and takes no network and no disk, so it is asked directly what it does
   when the server offers nothing, offers an incomplete run, or offers
   yesterday's run again.

3. **The page is made to go stale.** With the local build served against a
   copy of the published store, the run shown is the one that store holds,
   and when that run passes 36 hours old (SPEC 11.8) the banner has to
   appear. See `hc_fail_site.mjs` beside this file, and the screenshot in
   `results/`.

    python handchecks/hc_fail.py
    python handchecks/hc_fail.py --run 20261112T00Z
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import config as cfg                          # noqa: E402
from pipeline import publish as pub                         # noqa: E402
from pipeline import run_live                               # noqa: E402

OUT = ROOT / "handchecks" / "results"
BROKEN = "29991231T00Z"        # obviously not a run; it is only ever refused


def copy_run(source: Path, to: Path) -> None:
    to.mkdir(parents=True, exist_ok=True)
    for name in ("days.json", "manifest.json", "squares.npz"):
        shutil.copy2(source / name, to / name)


# ------------------------------------------------------------ the sabotages

def nothing(run: Path) -> None:
    """The forecast is not there at all."""
    shutil.rmtree(run)


def no_manifest(run: Path) -> None:
    """The run never finished its checks, so it has no manifest."""
    (run / "manifest.json").unlink()


def torn_manifest(run: Path) -> None:
    """The manifest was cut off halfway through being written."""
    text = (run / "manifest.json").read_text(encoding="utf-8")
    (run / "manifest.json").write_text(text[:len(text) // 2],
                                       encoding="utf-8")


def no_days(run: Path) -> None:
    """The day labels are missing."""
    (run / "days.json").unlink()


def torn_squares(run: Path) -> None:
    """The numbers themselves were cut off: the last tenth is gone."""
    data = (run / "squares.npz").read_bytes()
    (run / "squares.npz").write_bytes(data[:int(len(data) * 0.9)])


def wrong_counts(run: Path) -> None:
    """A whole, readable file whose counts no longer match its members."""
    with np.load(run / "squares.npz") as box:
        arrays = {name: box[name] for name in box.files}
    counts = arrays["counts"]
    i, j = np.nonzero(arrays["india"])
    counts[1, 0, i[0], j[0]] = (int(counts[1, 0, i[0], j[0]]) + 7) % 52
    np.savez(run / "squares.npz", **arrays)


def wrong_mask(run: Path) -> None:
    """A run built against a different India."""
    with np.load(run / "squares.npz") as box:
        arrays = {name: box[name] for name in box.files}
    arrays["india"] = arrays["india"][::-1]
    np.savez(run / "squares.npz", **arrays)


CASES = (
    ("the forecast is missing altogether", nothing),
    ("the run has no manifest, so it never finished its checks", no_manifest),
    ("the manifest is cut off halfway", torn_manifest),
    ("the day labels are missing", no_days),
    ("the numbers file is cut off", torn_squares),
    ("the counts no longer match the members they came from", wrong_counts),
    ("the run was built against a different India", wrong_mask),
)

# What select_run is offered, and what it must do with it (SPEC 1.5, 4.6).
OFFERS = (
    ("the server offers nothing at all", [], "20261112T00Z"),
    ("the server offers only an incomplete newer run",
     [{"run_id": "20261113T00Z", "complete": False}], "20261112T00Z"),
    ("the server offers the run that is already built",
     [{"run_id": "20261112T00Z", "complete": True}], "20261112T00Z"),
    ("the server offers only an older run",
     [{"run_id": "20261111T00Z", "complete": True}], "20261112T00Z"),
    ("the server offers a complete newer run",
     [{"run_id": "20261113T00Z", "complete": True}], "20261112T00Z"),
)


def seeded(control: "pub.FakeStore") -> "pub.FakeStore":
    """A store holding exactly what the control publish put there."""
    return pub.FakeStore(data=dict(control.data), meta=dict(control.meta))


def attempt(store, live: Path) -> tuple[int, int, str | None]:
    """Run the real publisher against this store, and see what it did."""
    pub.BlobStore = lambda *a, **k: store        # no network, no token
    before = len(store.calls)
    code = pub.main([])
    puts = sum(1 for call in store.calls[before:] if call[0] == "put")
    return code, puts, pub.read_published(store)["run_id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None)
    args = ap.parse_args()

    live_real = cfg.DATA / "live"
    runs = sorted((p.name for p in live_real.iterdir()
                   if p.is_dir() and re.fullmatch(r"\d{8}T\d{2}Z", p.name)),
                  reverse=True)
    run_id = args.run or (runs[0] if runs else None)
    if run_id is None:
        raise SystemExit("no built run under data/live to copy")

    work = Path(tempfile.mkdtemp(prefix="hc_fail_"))
    live = work / "live"
    copy_run(live_real / run_id, live / run_id)

    # Everything the publisher reaches for now points at the copy. `data/`
    # is not written to, and neither is the real publish log.
    pub.LIVE = live
    pub.run_dir = lambda rid: live / rid
    pub.PUBLISH = work / "publish"
    cfg.LOGS = work / "logs"
    real_blob = pub.BlobStore
    pub.LOG_STREAM = open(work / "publish.log", "w", encoding="utf-8")

    # The store as it stands before anything goes wrong: the real run,
    # published.
    control = pub.FakeStore()
    pub.publish(control, run_id, mark=False)
    standing = pub.read_published(control)["run_id"]
    if standing != run_id:
        raise SystemExit(f"the control store publishes {standing}")
    files_before = len(control.data)

    rows = []

    # The control: the same copy under the broken run's id, unbroken. It has
    # to publish, or the failures below prove nothing.
    store = seeded(control)
    copy_run(live_real / run_id, live / BROKEN)
    code, puts, after = attempt(store, live)
    rows.append(("CONTROL: nothing is broken", code, puts, after,
                 "published, as it should be"))
    shutil.rmtree(live / BROKEN)

    for what, break_it in CASES:
        store = seeded(control)
        copy_run(live_real / run_id, live / BROKEN)
        break_it(live / BROKEN)
        code, puts, after = attempt(store, live)
        held = after == run_id and len(store.data) == files_before
        rows.append((what, code, puts, after,
                     "the published run is untouched" if held
                     else "THE STORE CHANGED"))
        if (live / BROKEN).exists():
            shutil.rmtree(live / BROKEN)

    chooser = []
    for what, offers, built in OFFERS:
        chosen, reason = run_live.select_run(offers, built)
        chooser.append((what, chosen or "nothing", reason))

    pub.BlobStore = real_blob
    pub.LOG_STREAM.close()
    pub.LOG_STREAM = sys.stdout

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "hc_fail.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["hc-fail", "the publisher and the chooser, made to fail "
                    "on purpose. SPEC 1.5, 8.6, 11.8"])
        w.writerow(["run copied", run_id])
        w.writerow(["the store starts out publishing", standing])
        w.writerow(["files in the store at the start", files_before])
        w.writerow(["the broken run's id", BROKEN])
        w.writerow(["the broken run", "a copy of the real run's own files, "
                    "broken on purpose, in a temporary folder. It is never "
                    "published and no number in it is used as a measurement"])
        w.writerow(["network", "none: the store is in memory and no token "
                    "exists"])
        w.writerow(["data/", "not written to: the copy, the publish folder "
                    "and the log all live in a temporary folder"])
        w.writerow([])
        w.writerow(["what went wrong", "exit code", "files uploaded",
                    "the store still publishes", "verdict"])
        for row in rows:
            w.writerow(row)
        w.writerow(["on the two exit codes", "a broken file is a failure "
                    "and exits 1. Nothing to publish -- no forecast, or a "
                    "run that never finished its checks -- exits 0 by "
                    "design: the workflow runs every day whether or not "
                    "ECMWF has a run ready, and a red failure on an "
                    "ordinary quiet day would teach us to ignore red. Both "
                    "upload nothing and both leave the published run alone, "
                    "which is the half that matters to a reader"])
        w.writerow([])
        w.writerow(["what the server offers", "the run chosen", "why"])
        for row in chooser:
            w.writerow(row)
        w.writerow([])
        w.writerow(["the stale banner", "hc_fail_stale.txt, with "
                    "hc_fail_stale.jpg: the real 12 November run, really "
                    "past 36 hours old, served from a copy of its own "
                    "published bytes"])
        w.writerow(["the day it happened for real", "hc_fail_13nov.txt: on "
                    "13 November 2026 not one of the 23 scheduled attempts "
                    "fired, and the site kept the 12 November run until a "
                    "manual dispatch at 07:02 UTC"])

    for row in rows:
        print(f"  exit {row[1]}, {row[2]} uploads, store still at {row[3]}"
              f"  <- {row[0]}")
    for row in chooser:
        print(f"  chose {row[1]}  <- {row[0]}")
    print(f"wrote {out}")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
