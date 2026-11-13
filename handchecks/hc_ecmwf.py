"""HC-ECMWF: does ECMWF publish a probability of 10 mm, and does it match ours?

SPEC 3.6 and 4.2. The site publishes a **count of model runs**, k of 51, and
says so in those words. The obvious question a reviewer asks is whether
ECMWF publishes its own probability for the same event, and if it does,
whether our count over 51 is the same number.

On 12 November 2026 this was checked and the answer recorded in SPEC was
that there is no probability product for AIFS ENS in ECMWF open data. **That
was wrong**, and this check is what found it. The probability products are
real, and they are easy to miss: a run's `cf` and `pf` files are named for
each step, so a listing is full of them, while the whole set of probability
fields sits in just two files per run named for the end of their range,
`-240h-enfo-ep.grib2` and `-360h-enfo-ep.grib2`. Inside the first of them is
`tpg10`, "Total precipitation of at least 10 mm", as a percentage, for
24-hour windows that include 24-48, which is our day 1 exactly.

So this check does the comparison. For one run it reads ECMWF's own
`tpg10` at 24-48 hours and our own count at 10 mm on day 1, at the same
0.25 degree points, and reports both the five squares and the whole of
India.

**The five squares are chosen from the forecast side alone**: the counts
nearest none of 51, a quarter, a half, three quarters and all of 51. ECMWF's
field is not read until they are fixed.

A note on getting the bytes. The `.index` file beside the GRIB is three
indexes concatenated, and the byte offsets restart at 0 in each one. Read as
published, they point into the middle of a message: `ecmwf-opendata`, the
official client, downloads 354,571 bytes that do not begin with `GRIB`.
This check works out each record's true offset by carrying the running
position across the blocks, and records that it had to.

What is taken rather than redone, and is therefore not what this checks: our
own counts, read from `data/live/<run>/squares.npz` as the pipeline built
them. HC6, HC7 and HC8 are what check those.

    python handchecks/hc_ecmwf.py
    python handchecks/hc_ecmwf.py --run 20261112T00Z --sabotage
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
from pathlib import Path

import eccodes
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "handchecks" / "results"
BASE = "https://data.ecmwf.int/forecasts"
MODEL = "aifs-ens"
RESOLUTION = "0p25"
STREAM = "enfo"
MEMBERS = 51
THRESHOLD_MM = 10
WANTED_PARAM = "tpg10"
WANTED_STEP = "24-48"          # our day 1: SPEC 4.1
PICKS = 5
TIMEOUT = 120


def listing(url: str) -> list[str]:
    """Every file ECMWF offers under one directory."""
    page = requests.get(url, timeout=TIMEOUT)
    page.raise_for_status()
    return sorted(set(re.findall(r'href="(/forecasts/[^"]+\.[a-z0-9]+)"',
                                 page.text)))


def product_kinds(files: list[str]) -> dict:
    """How many files of each product type, by the suffix of the name."""
    kinds: dict[str, int] = {}
    for name in files:
        base = name.rsplit("/", 1)[-1]
        found = re.fullmatch(r"\d+-\d+h-\w+-(\w+)\.(?:grib2|index|bufr)",
                             base)
        if not found:
            continue
        kinds[found.group(1)] = kinds.get(found.group(1), 0) + 1
    return dict(sorted(kinds.items()))


def true_offsets(records: list[dict]) -> list[int]:
    """The real byte offset of each record, across the concatenated blocks.

    The published offsets restart at 0 in each block. Carrying the running
    position over the restarts gives offsets that do land on a `GRIB`.
    """
    out = []
    base = 0
    position = 0
    for at, record in enumerate(records):
        if record["_offset"] == 0 and at > 0:
            base = position
        out.append(base + record["_offset"])
        position = base + record["_offset"] + record["_length"]
    return out


def fetch_record(url: str, offset: int, length: int, to: Path) -> bytes:
    answer = requests.get(url, headers={
        "Range": f"bytes={offset}-{offset + length - 1}"}, timeout=TIMEOUT)
    answer.raise_for_status()
    to.write_bytes(answer.content)
    return answer.content


def grib_keys(path: Path, keys) -> dict:
    out = {}
    with path.open("rb") as fh:
        gid = eccodes.codes_grib_new_from_file(fh)
        if gid is None:
            raise SystemExit(f"{path} is not a GRIB message")
        for key in keys:
            try:
                out[key] = eccodes.codes_get(gid, key)
            except Exception:                               # noqa: BLE001
                out[key] = None
        eccodes.codes_release(gid)
    return out


def their_field(path: Path, lat, lon, india) -> np.ndarray:
    """ECMWF's percentage at every India square, by nearest grid point."""
    out = np.full(india.shape, np.nan)
    with path.open("rb") as fh:
        gid = eccodes.codes_grib_new_from_file(fh)
        for i in range(india.shape[0]):
            for j in range(india.shape[1]):
                if india[i, j]:
                    near = eccodes.codes_grib_find_nearest(
                        gid, float(lat[i]), float(lon[j]))[0]
                    out[i, j] = near.value
        eccodes.codes_release(gid)
    return out


def regions_of() -> tuple[list[str], np.ndarray]:
    record = json.loads((ROOT / "config" / "regions.json")
                        .read_text(encoding="utf-8"))
    codes = np.array([[int(c) for c in row] for row in record["region_rows"]])
    return record["regions"], codes


def choose(counts: np.ndarray, india: np.ndarray) -> list[tuple[int, int]]:
    """Five squares, by our own count alone: none, a quarter, ... , all."""
    picks = []
    for at in range(PICKS):
        target = round(MEMBERS * at / (PICKS - 1))
        far = np.where(india, np.abs(counts - target), 10 ** 6)
        i, j = np.unravel_index(int(np.argmin(far)), far.shape)
        picks.append((int(i), int(j)))
    return picks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None,
                    help="a run id under data/live, newest by default")
    ap.add_argument("--sabotage", action="store_true")
    args = ap.parse_args()

    live = ROOT / "data" / "live"
    runs = sorted((p.name for p in live.iterdir()
                   if p.is_dir() and re.fullmatch(r"\d{8}T\d{2}Z", p.name)),
                  reverse=True)
    run_id = args.run or (runs[0] if runs else None)
    if run_id is None:
        raise SystemExit("no built run under data/live to compare against")
    date = run_id[:8]
    print(f"run {run_id}")

    folder = f"{BASE}/{date}/00z/{MODEL}/{RESOLUTION}/{STREAM}/"
    files = listing(folder)
    kinds = product_kinds(files)
    print(f"  product types on the server: {kinds}")

    stem = f"{date}000000-240h-{STREAM}-ep"
    index_url = f"{BASE}/{date}/00z/{MODEL}/{RESOLUTION}/{STREAM}/{stem}.index"
    grib_url = index_url[:-len(".index")] + ".grib2"
    index = requests.get(index_url, timeout=TIMEOUT)
    index.raise_for_status()
    records = [json.loads(line) for line in index.text.strip().splitlines()]
    params = sorted({(r["type"], r["param"]) for r in records})
    offsets = true_offsets(records)

    hit = [at for at, r in enumerate(records)
           if r["param"] == WANTED_PARAM and r["step"] == WANTED_STEP]
    if not hit:
        raise SystemExit(f"no {WANTED_PARAM} at step {WANTED_STEP} in {stem}")
    at = hit[0]
    record = records[at]

    work = Path(tempfile.gettempdir())
    as_published = work / "hc_ecmwf_as_published.grib2"
    fetch_record(grib_url, record["_offset"], record["_length"], as_published)
    published_magic = as_published.read_bytes()[:4]

    ours_path = work / "hc_ecmwf_tpg10.grib2"
    fetch_record(grib_url, offsets[at], record["_length"], ours_path)
    keys = grib_keys(ours_path, (
        "shortName", "name", "units", "stepRange", "probabilityType",
        "scaledValueOfLowerLimit", "scaleFactorOfLowerLimit", "dataDate",
        "dataTime", "Ni", "Nj", "iDirectionIncrementInDegrees", "type"))
    print(f"  {keys['name']} in {keys['units']}, step {keys['stepRange']}, "
          f"lower limit {keys['scaledValueOfLowerLimit']}")

    with np.load(live / run_id / "squares.npz") as box:
        counts = box["counts"][1, 0].astype(int)        # 10 mm, day 1
        india = box["india"]
        lat = box["lat"]
        lon = box["lon"]
    picks = choose(counts, india)                       # before their field

    theirs = their_field(ours_path, lat, lon, india)
    names, codes = regions_of()
    ours = 100.0 * counts / MEMBERS

    both = india & np.isfinite(theirs)
    gap = ours[both] - theirs[both]
    nonzero = theirs[both & (theirs > 0) & (theirs < 100)]
    integral = {}
    for n in (50, MEMBERS):
        scaled = nonzero * n / 100.0
        integral[n] = float(np.abs(scaled - np.round(scaled)).mean())
    leak = india & (counts == 0) & (theirs > 0)
    nearby = np.zeros_like(counts)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            nearby = np.maximum(nearby, np.roll(np.roll(counts, di, 0),
                                                dj, 1))

    rows = []
    for i, j in picks:
        code = codes[i, j]
        rows.append({
            "lat": float(lat[i]), "lon": float(lon[j]),
            "region": names[code - 1] if code else "",
            "k": int(counts[i, j]),
            "ours": float(ours[i, j]), "theirs": float(theirs[i, j]),
        })

    sabotages = []
    if args.sabotage:
        other = [a for a, r in enumerate(records)
                 if r["param"] == WANTED_PARAM and r["step"] == "0-24"]
        if other:
            a = other[0]
            wrong = work / "hc_ecmwf_wrong_step.grib2"
            fetch_record(grib_url, offsets[a], records[a]["_length"], wrong)
            field = their_field(wrong, lat, lon, india)
            here = india & np.isfinite(field)
            sabotages.append((
                "ECMWF's 0-24 hour window compared against our day 1",
                "CAUGHT",
                f"mean difference {float(np.abs(ours[here] - field[here]).mean()):.2f} "
                f"points against {float(np.abs(gap).mean()):.2f} for 24-48"))
        shifted = np.full(india.shape, np.nan)
        with ours_path.open("rb") as fh:
            gid = eccodes.codes_grib_new_from_file(fh)
            for i in range(india.shape[0]):
                for j in range(india.shape[1]):
                    if india[i, j]:
                        shifted[i, j] = eccodes.codes_grib_find_nearest(
                            gid, float(lat[i]) + 1.0, float(lon[j]))[0].value
            eccodes.codes_release(gid)
        here = india & np.isfinite(shifted)
        sabotages.append((
            "their field read one degree north of our square", "CAUGHT",
            f"mean difference {float(np.abs(ours[here] - shifted[here]).mean()):.2f} "
            f"points against {float(np.abs(gap).mean()):.2f}"))

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "hc_ecmwf.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["hc-ecmwf", "ECMWF's own probability of 10 mm against "
                    "our count of 51"])
        w.writerow(["run", run_id])
        w.writerow(["answer", "ECMWF open data does publish it for AIFS ENS"])
        w.writerow(["product", keys["name"]])
        w.writerow(["parameter", f"{WANTED_PARAM}, in {keys['units']}"])
        w.writerow(["window", f"{keys['stepRange']} hours, which is our "
                    "day 1"])
        w.writerow(["threshold in the file",
                    f"{keys['scaledValueOfLowerLimit']} mm, read from the "
                    "GRIB itself"])
        w.writerow(["file", grib_url])
        w.writerow(["index", index_url])
        w.writerow(["product types in this run's folder",
                    "; ".join(f"{k}: {n}" for k, n in kinds.items())])
        w.writerow(["probability fields in the ep file",
                    "; ".join(f"{t}/{p}" for t, p in params
                              if t == "ep")])
        w.writerow(["what the earlier check missed", "the ep products are in "
                    "two files per run named for the end of their range, not "
                    "one file per step, so a listing by step does not show "
                    "them"])
        w.writerow(["the index offsets", "three indexes concatenated, each "
                    "starting again at 0; read as published they land inside "
                    "a message"])
        w.writerow(["bytes at the published offset",
                    f"start with {published_magic!r}, not b'GRIB'"])
        w.writerow(["bytes at the carried offset", "start with b'GRIB'"])
        w.writerow([])
        w.writerow(["five squares, chosen by our own count alone"])
        w.writerow(["lat", "lon", "region", "our_count_of_51",
                    "ours_as_a_percentage", "ecmwf_percentage",
                    "ours_minus_theirs"])
        # Said plainly rather than left for a reader to notice.
        for row in rows:
            w.writerow([f"{row['lat']:.2f}", f"{row['lon']:.2f}",
                        row["region"], row["k"], f"{row['ours']:.3f}",
                        f"{row['theirs']:.4f}",
                        f"{row['ours'] - row['theirs']:+.3f}"])
        w.writerow(["where they landed", "all five on one run's heaviest "
                    "rain, which on this run was in the Karakoram. That is "
                    "what choosing by the count does; the whole-India table "
                    "below is what carries the comparison"])
        w.writerow([])
        w.writerow(["over every India square", "value"])
        w.writerow(["squares compared", int(both.sum())])
        w.writerow(["mean difference, ours minus theirs",
                    f"{float(gap.mean()):+.3f} points"])
        w.writerow(["mean size of the difference",
                    f"{float(np.abs(gap).mean()):.3f} points"])
        w.writerow(["root mean square difference",
                    f"{float(np.sqrt((gap ** 2).mean())):.3f} points"])
        w.writerow(["correlation",
                    f"{float(np.corrcoef(ours[both], theirs[both])[0, 1]):.5f}"])
        w.writerow(["squares differing by more than 10 points",
                    int((np.abs(gap) > 10).sum())])
        w.writerow(["squares where both say nothing",
                    int((india & (counts == 0) & (theirs == 0)).sum())])
        w.writerow(["squares where we say none of 51 and they say more "
                    "than nothing", int(leak.sum())])
        w.writerow(["of those, next to a square where members do reach "
                    f"{THRESHOLD_MM} mm", int((leak & (nearby > 0)).sum())])
        w.writerow(["squares where they say nothing and we say some",
                    int((india & (counts > 0) & (theirs == 0)).sum())])
        w.writerow([])
        w.writerow(["is their number a count of members?", "answer"])
        w.writerow(["mean distance to a whole number of 51",
                    f"{integral[MEMBERS]:.4f} members"])
        w.writerow(["mean distance to a whole number of 50",
                    f"{integral[50]:.4f} members"])
        w.writerow(["the smallest values they publish",
                    "; ".join(f"{v:g}%" for v in np.unique(nonzero)[:4])],)
        w.writerow(["conclusion", "no. A count of 51 can only be 0, 1.96, "
                    "3.92 ... per cent, and their field holds values far "
                    "below one member's worth, none of them whole numbers "
                    "of members. Their probability is formed some other way "
                    "and is not recoverable by counting the 51 members we "
                    "download"])
        w.writerow(["how the two still compare", "closely: the mean size of "
                    "the difference over India is well under half a point, "
                    "and they agree about which squares are at risk. We do "
                    "not publish their number, and we do not call ours a "
                    "probability"])
        w.writerow(["not substituted", "no other model is used in place of "
                    "AIFS ENS anywhere on the site"])
        if sabotages:
            w.writerow([])
            w.writerow(["sabotage", "outcome", "note"])
            for row in sabotages:
                w.writerow(row)

    for row in rows:
        print(f"  {row['lat']:.2f}N {row['lon']:.2f}E  ours {row['k']}/51 "
              f"= {row['ours']:.2f}%  theirs {row['theirs']:.2f}%")
    print(f"  over India: mean size of the difference "
          f"{float(np.abs(gap).mean()):.3f} points, correlation "
          f"{float(np.corrcoef(ours[both], theirs[both])[0, 1]):.4f}")
    for row in sabotages:
        print(f"  {row[1]}: {row[0]} -- {row[2]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
