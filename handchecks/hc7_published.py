"""HC7: what the store actually serves, against what this laptop built.

SPEC 8.13. Run after a real publish, from this laptop, with no token. Every
read here is a plain HTTPS GET of a public URL: no Authorization header, no
credential of any kind, and `BLOB_READ_WRITE_TOKEN` is never read. If that
name happens to be set in this shell the script says so and carries on
without touching the value, because a public URL that only works with a
token is not a published forecast.

What it compares. One India square, picked as the wettest square of lead day
1 so that the numbers are not all zero, and one square that is dry in every
member, so a 0 is checked as well as a 51. For each of them:

  * all fifteen published counts bytes, 3 thresholds x 5 days, read out of
    the raw `.u8` files at the byte the index arithmetic says;
  * that square's record in its published tile: the counts, the dots and the
    51 member integers for all five days;
  * the India mask byte, which must say 1 for a square we claim is in India.

against `data/live/<run_id>/squares.npz`, the file this laptop wrote.

The index arithmetic is written out longhand, in the output, so it can be
followed with a pencil:

    i = (38.0 - lat) / 0.25          row, north to south
    j = (lon - 68.0) / 0.25          column, west to east
    byte = i * 121 + j               row major, one byte a square

and the tile name likewise: floor(lat / 4) * 4, floor(lon / 4) * 4.

Nothing in pipeline/publish.py is used to locate or decode anything: the
bytes are indexed by hand here, the member integers are divided by 16 here,
and the only thing imported from the pipeline is the grid itself and the
local npz that is being checked against.

Usage: python handchecks/hc7_published.py <manifest-url> [run_id]

The manifest URL is the one public address this project has to be told,
because finding it in the store needs `list`, and `list` needs the write
token (SPEC 8.6). Everything else is read from the manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.run_live import run_dir                        # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "hc7_published.csv"
TOKEN_NAME = "BLOB_READ_WRITE_TOKEN"

THRESHOLDS = (1.0, 10.0, 50.0)       # written out here on purpose
N_DAYS = 5
N_MEMBERS = 51
STEPS_PER_MM = 16                    # 1 mm / 0.0625 mm
NOT_INDIA = 255


def get(url: str) -> bytes:
    """A plain public GET. No headers, no credential, nothing cached."""
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise SystemExit(f"{url} answered {response.status}")
        return response.read()


def bust(url: str, nonce: str) -> str:
    """The manifest is cached for 60 s, so ask for it by a fresh name."""
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}cb={nonce}"


def row_of(lat: float) -> float:
    return (cfg.LAT_MAX - lat) / cfg.GRID_STEP


def col_of(lon: float) -> float:
    return (lon - cfg.LON_MIN) / cfg.GRID_STEP


def tile_name(lat: float, lon: float) -> str:
    lat_s = math.floor(lat / 4.0) * 4.0
    lon_w = math.floor(lon / 4.0) * 4.0
    ns = "N" if lat_s >= 0 else "S"
    ew = "E" if lon_w >= 0 else "W"
    return f"{abs(int(lat_s))}{ns}_{abs(int(lon_w))}{ew}"


def pick_squares(totals: np.ndarray, india: np.ndarray) -> list[tuple[str, int, int]]:
    """The wettest India square on day 1, and one dry in every member."""
    day1 = totals[0].mean(axis=0)
    wet_pool = np.where(india, day1, -np.inf)
    wi, wj = np.unravel_index(int(np.argmax(wet_pool)), wet_pool.shape)

    dry_pool = np.where(india & (totals[0].max(axis=0) < 1.0), day1, np.inf)
    if np.isfinite(dry_pool).any():
        di, dj = np.unravel_index(int(np.argmin(dry_pool)), dry_pool.shape)
    else:
        fallback = np.where(india, day1, np.inf)
        di, dj = np.unravel_index(int(np.argmin(fallback)), fallback.shape)
    return [("wettest", int(wi), int(wj)), ("dry", int(di), int(dj))]


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__.strip().splitlines()[-4])
    manifest_url = sys.argv[1]
    want_run = sys.argv[2] if len(sys.argv) > 2 else None

    lines: list[str] = []

    def say(text: str) -> None:
        print(text)
        lines.append(text)

    # Presence only. The value is never read, printed or sent anywhere.
    if TOKEN_NAME in os.environ:
        say(f"note: {TOKEN_NAME} is set in this shell; it is not read and "
            f"not sent. Every request below is an anonymous GET.")

    base = manifest_url.split("?", 1)[0].rsplit("/", 1)[0]
    say(f"store base: {base}")
    say(f"manifest:   {manifest_url}")

    raw_manifest = get(bust(manifest_url, "hc7"))
    manifest = json.loads(raw_manifest.decode("utf-8"))
    run_id = manifest["run_id"]
    say(f"the store publishes {run_id}, "
        f"{len(manifest['files'])} files, {manifest['bytes_total']} bytes")
    if want_run is not None and want_run != run_id:
        raise SystemExit(f"the store publishes {run_id}, not {want_run}")

    local = run_dir(run_id) / "squares.npz"
    if not local.is_file():
        raise SystemExit(f"{local} is missing: this laptop did not build "
                         f"{run_id}, so there is nothing to compare against")
    say(f"local file: {local}")

    with np.load(local) as f:
        totals = f["member_totals"]       # (day, member, i, j), mm
        counts = f["counts"]              # (threshold, day, i, j)
        dots = f["dots"]                  # (category, day, i, j)
        india = f["india"]

    paths = manifest["paths"]
    squares = pick_squares(totals, india)

    # The India mask, fetched once.
    mask_bytes = get(f"{base}/{paths['india']}")
    say(f"india.u8:   {len(mask_bytes)} bytes fetched, "
        f"manifest says {manifest['files'][paths['india']]['bytes']}")

    # The fifteen counts files, fetched once each and indexed by hand.
    counts_bytes: dict[str, bytes] = {}
    for threshold in THRESHOLDS:
        for day in range(1, N_DAYS + 1):
            name = f"ge{threshold:g}mm_day{day}.u8"
            counts_bytes[name] = get(f"{base}/{paths['counts']}/{name}")

    # The tiles the chosen squares live in.
    tiles: dict[str, dict] = {}
    for _, i, j in squares:
        name = tile_name(cfg.INDIA_LATS[i], cfg.INDIA_LONS[j])
        if name not in tiles:
            tiles[name] = json.loads(
                get(f"{base}/{paths['tiles']}/{name}.json").decode("utf-8"))

    # Every byte fetched hashes to what the manifest says was published.
    rows: list[dict] = []
    bad = 0

    def check(label: str, what: str, published, ours, note: str = "") -> None:
        nonlocal bad
        same = published == ours
        if not same:
            bad += 1
        rows.append({
            "square": label,
            "check": what,
            "from_store": published,
            "from_laptop": ours,
            "same": int(same),
            "note": note,
        })

    for pathname in [paths["india"],
                     *(f"{paths['counts']}/{n}" for n in counts_bytes),
                     *(f"{paths['tiles']}/{n}.json" for n in tiles)]:
        data = (mask_bytes if pathname == paths["india"]
                else counts_bytes.get(pathname.rsplit("/", 1)[1]))
        if data is None:
            data = get(f"{base}/{pathname}")
        check("file", f"sha256 {pathname}",
              hashlib.sha256(data).hexdigest(),
              manifest["files"][pathname]["sha256"],
              "the bytes the CDN served, against the manifest's record")

    for label, i, j in squares:
        lat = cfg.INDIA_LATS[i]
        lon = cfg.INDIA_LONS[j]
        name = tile_name(lat, lon)

        # Longhand, and then checked against the i and j we started from.
        i_hand = row_of(lat)
        j_hand = col_of(lon)
        offset = int(i_hand) * cfg.N_LON + int(j_hand)
        say("")
        say(f"{label} square: {lat} N {lon} E")
        say(f"  i = (38.0 - {lat}) / 0.25 = {i_hand:g}            "
            f"(numpy index {i})")
        say(f"  j = ({lon} - 68.0) / 0.25 = {j_hand:g}            "
            f"(numpy index {j})")
        say(f"  byte = {int(i_hand)} * 121 + {int(j_hand)} = {offset}")
        say(f"  tile = floor({lat} / 4) * 4, floor({lon} / 4) * 4 -> {name}")
        if (int(i_hand), int(j_hand)) != (i, j):
            raise SystemExit("the longhand indices and the numpy indices "
                             "disagree; stopping")

        check(label, "india mask byte", mask_bytes[offset],
              int(india[i, j]), f"byte {offset} of india.u8")

        for k, threshold in enumerate(THRESHOLDS):
            for day in range(1, N_DAYS + 1):
                fname = f"ge{threshold:g}mm_day{day}.u8"
                served = counts_bytes[fname][offset]
                ours = int(counts[k, day - 1, i, j])
                check(label, f"count >= {threshold:g} mm day {day}",
                      served, ours, f"{fname} byte {offset}")
                if served == NOT_INDIA:
                    check(label, f"not 255 inside India, {fname}", 0, 1,
                          "255 means outside India, and this square is in it")

        record = None
        for candidate in tiles[name]["squares"]:
            if (abs(candidate["lat"] - lat) < 1e-9
                    and abs(candidate["lon"] - lon) < 1e-9):
                record = candidate
                break
        if record is None:
            check(label, f"square present in tile {name}", "missing",
                  f"{lat} N {lon} E", "the tile does not hold this square")
            continue

        for day in range(1, N_DAYS + 1):
            for k, threshold in enumerate(THRESHOLDS):
                check(label, f"tile count >= {threshold:g} mm day {day}",
                      record["c"][day - 1][k],
                      int(counts[k, day - 1, i, j]),
                      f"tile {name}, c[{day - 1}][{k}]")
            for c in range(4):
                check(label, f"tile dot {c} day {day}",
                      record["d"][day - 1][c],
                      int(dots[c, day - 1, i, j]),
                      f"tile {name}, d[{day - 1}][{c}]")

            members = record["m"][day - 1]
            check(label, f"members published day {day}", len(members),
                  N_MEMBERS, "51 integers a day a square")
            ours_mm = totals[day - 1, :, i, j]
            # The integer is floor(mm / 0.0625) and 0.0625 = 1/16 exactly,
            # so mm * 16 must land on the integer with nothing left over.
            hand = [int(math.floor(float(v) * 16.0 + 1e-9)) for v in ours_mm]
            check(label, f"member integers day {day}", members, hand,
                  "floor(mm * 16) for all 51 members")

            shown = [m // STEPS_PER_MM for m in members]
            for k, threshold in enumerate(THRESHOLDS):
                from_shown = sum(1 for s in shown if s >= threshold)
                check(label,
                      f"whole mm shown agrees with >= {threshold:g} mm "
                      f"day {day}",
                      from_shown, int(counts[k, day - 1, i, j]),
                      "rounded down, so the number shown and the count "
                      "cannot disagree")
            if day == 1:
                say(f"  day 1 members, whole mm as shown: {shown}")
                say(f"  day 1 counts from the store: "
                    f"{[record['c'][0][k] for k in range(3)]}, "
                    f"dots {record['d'][0]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        fh.write("# HC7: the published store against this laptop's "
                 "data/live/<run_id>/squares.npz\n")
        fh.write(f"# run,{run_id}\n")
        fh.write("# every read below was an anonymous HTTPS GET of a public "
                 "URL: no token, no Authorization header\n")
        fh.write("# i = (38.0 - lat) / 0.25, j = (lon - 68.0) / 0.25, "
                 "byte = i * 121 + j, row major\n")
        fh.write("# tile = floor(lat / 4) * 4, floor(lon / 4) * 4, named "
                 "after its south-west corner\n")
        fh.write("# member integer = floor(mm / 0.0625) = floor(mm * 16); "
                 "whole mm shown = integer // 16\n")
        for line in lines:
            fh.write("# " + line + "\n")
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("")
    print(f"wrote {OUT}")
    print(f"{len(rows)} comparisons, {bad} different")
    print("HC7 PASSED" if bad == 0 else "HC7 FAILED")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
