"""Publishing a built run to the Vercel Blob store. SPEC section 8.

Three things this module is careful about:

1. **It makes every decision and touches no network.** Everything that
   reaches the store goes through the `Store` interface below: three verbs,
   `put_many`, `list` and `delete`, plus `fetch` for reading a public URL
   back. `BlobStore` runs the Node script; `FakeStore` keeps the lot in a
   dictionary and records the order of every call, which is how the rules in
   SPEC 8.5 to 8.7 are tested without a network or a token.
2. **It never sees the write token.** `BLOB_READ_WRITE_TOKEN` is read from
   the environment by the Node SDK, inside Actions, on the two steps that
   talk to the store. Nothing here reads it, prints it or passes it on.
3. **An empty store and a broken store are not the same thing** (SPEC 8.6).
   Only a `list` that succeeds and finds nothing published means "nothing has
   been published yet". A failed list is a failure and publishes nothing.
4. **Nothing is decided from a CDN-served body** (SPEC 8.5, 8.6). What is
   published is read from `list`, which is an API call and is never cached,
   by taking the newest immutable marker under `published/`. A public `fetch`
   can be up to 60 seconds behind an overwrite by Vercel's own documentation,
   and was measured serving a 60 second manifest at `Age: 583`, so it is used
   only to check bytes on pathnames that are never overwritten.

Usage
  python -m pipeline.publish                  publish the newest built run
  python -m pipeline.publish --dry-run        build and check the payload,
                                              upload nothing, need no token
  python -m pipeline.publish remote-run-id    print the store's current run id
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from . import config as cfg
from .run_live import (
    DOT_NAMES,
    IST,
    LIVE,
    THRESHOLDS,
    counts_from,
    dots_from,
    parse_run_id,
    run_dir,
)

# ------------------------------------------------------------------ numbers

# SPEC 8.12. These live here and not in config.py because config.py is
# imported by Pile A, which is still running and is not being touched.
KEEP_RUNS = 8                    # SPEC 8.7
MANIFEST_MAX_AGE = 60            # SPEC 8.4, the documented minimum
RUN_FILE_MAX_AGE = 2_592_000     # SPEC 8.4, one month
TILE_DEGREES = 4.0               # SPEC 8.4
NOT_INDIA = 255                  # SPEC 8.4
MEMBER_STEP = 0.0625             # SPEC 8.4, mm per stored integer
MEMBER_MAX_CODE = 65_535         # what an unsigned 16-bit value holds
STEPS_PER_MM = 16                # 1 mm / MEMBER_STEP, exactly

MANIFEST = "manifest.json"
MARKERS = "published/"           # SPEC 8.5, one immutable marker a run
RUNS = "runs/"
PUBLISH = cfg.DATA / "publish"
NODE_SCRIPT = cfg.ROOT / "scripts" / "publish" / "blob.mjs"

JSON_TYPE = "application/json"
BYTES_TYPE = "application/octet-stream"


class PublishError(RuntimeError):
    """Anything that must stop a publish."""


# ------------------------------------------------------------------ the store

@dataclass(frozen=True)
class Upload:
    """One blob: its pathname in the store and the exact bytes for it."""

    pathname: str
    data: bytes
    content_type: str
    max_age: int

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


class Store(Protocol):
    """The only way this module reaches the store."""

    def put_many(self, uploads: list[Upload]) -> list[dict]: ...

    def list(self, prefix: str = "") -> list[dict]: ...

    def delete(self, pathnames: list[str]) -> None: ...

    def fetch(self, url: str) -> bytes: ...


class BlobStore:
    """The real store, through `scripts/publish/blob.mjs`.

    The token never appears here: the Node SDK reads it from the environment
    this process was given. There is no token argument and no token flag.
    """

    def __init__(self, work_dir: Path, script: Path = NODE_SCRIPT) -> None:
        self.work_dir = work_dir
        self.script = script

    def _node(self, request: dict) -> dict:
        if not self.script.exists():
            raise PublishError(f"{self.script} is missing")
        try:
            done = subprocess.run(
                ["node", str(self.script)],
                input=json.dumps(request),
                capture_output=True, text=True, check=False,
            )
        except OSError as exc:
            raise PublishError(f"could not run node: {exc}") from exc
        if done.stderr.strip():
            for line in done.stderr.strip().splitlines():
                log(f"  node: {line}")
        try:
            reply = json.loads(done.stdout or "{}")
        except ValueError:
            raise PublishError(
                f"node exited {done.returncode} without a JSON reply") from None
        if done.returncode != 0 or not reply.get("ok"):
            error = reply.get("error", {})
            raise PublishError(
                f"{request['op']} failed: {error.get('name', 'Unknown')}: "
                f"{error.get('message', 'no message')}")
        return reply

    def put_many(self, uploads: list[Upload]) -> list[dict]:
        items = []
        for upload in uploads:
            local = self.work_dir / upload.pathname
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(upload.data)
            items.append({
                "pathname": upload.pathname,
                "file": str(local),
                "contentType": upload.content_type,
                "maxAge": upload.max_age,
            })
        return self._node({"op": "put", "items": items})["results"]

    def list(self, prefix: str = "") -> list[dict]:
        return self._node({"op": "list", "prefix": prefix})["blobs"]

    def delete(self, pathnames: list[str]) -> None:
        if not pathnames:
            return
        for start in range(0, len(pathnames), 1000):      # SDK limit
            self._node({"op": "delete",
                        "pathnames": pathnames[start:start + 1000]})

    def fetch(self, url: str) -> bytes:
        """Read a public URL. No token: this is what the website does.

        There is no cache-busting here any more, because there is no cache
        busting to be had: measured on the real store, `?cb=<nonce>` and a
        `Cache-Control: no-cache` request header both came back
        `X-Vercel-Cache: HIT` with the same `Age` and the same `ETag`. The
        query-parameter trick in Vercel's own documentation is for defeating
        a **browser** cache, not theirs (SPEC 8.10).
        """
        request = urllib.request.Request(url, headers={
            "User-Agent": "precipitation-forecast/publish",
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 200:
                    raise PublishError(f"{url} returned {response.status}")
                return response.read()
        except urllib.error.HTTPError as exc:
            raise PublishError(f"{url} returned {exc.code}") from exc
        except OSError as exc:
            raise PublishError(f"{url} could not be read: {exc}") from exc


@dataclass
class FakeStore:
    """An in-memory store. No network, no token, and it remembers the order.

    `calls` is the point of it: SPEC 8.5 says the manifest is written last and
    SPEC 8.7 says no deletion happens before that write, and both are claims
    about order rather than about contents.
    """

    base: str = "https://fake.public.blob.vercel-storage.com"
    data: dict[str, bytes] = field(default_factory=dict)
    meta: dict[str, dict] = field(default_factory=dict)
    calls: list[tuple] = field(default_factory=list)
    list_error: str | None = None
    fetch_status: dict[str, int] = field(default_factory=dict)
    # SPEC 8.10: what the edge is still serving, pathname -> bytes. `data` is
    # the store itself, which `list` reads; `stale` is what a public `fetch`
    # of that pathname answers instead. This is how a CDN that is up to 60
    # seconds behind an overwrite is reproduced without a network.
    stale: dict[str, bytes] = field(default_factory=dict)
    stale_etag: dict[str, str] = field(default_factory=dict)

    def url_for(self, pathname: str) -> str:
        return f"{self.base}/{pathname}"

    def _pathname_of(self, url: str) -> str:
        return url.split("?", 1)[0][len(self.base) + 1:]

    @staticmethod
    def etag_of(data: bytes) -> str:
        return hashlib.md5(data, usedforsecurity=False).hexdigest()

    def put_many(self, uploads: list[Upload]) -> list[dict]:
        results = []
        for upload in uploads:
            self.calls.append(("put", upload.pathname))
            self.data[upload.pathname] = upload.data
            self.meta[upload.pathname] = {
                "content_type": upload.content_type,
                "max_age": upload.max_age,
                "size": upload.size,
                "uploadedAt": f"fake-{len(self.calls):06d}",
            }
            results.append({"pathname": upload.pathname,
                            "url": self.url_for(upload.pathname),
                            "size": upload.size,
                            "etag": self.etag_of(upload.data)})
        return results

    def list(self, prefix: str = "") -> list[dict]:
        self.calls.append(("list", prefix))
        if self.list_error is not None:
            raise PublishError(f"list failed: {self.list_error}")
        return [{"pathname": p, "url": self.url_for(p),
                 "size": len(self.data[p]),
                 "etag": self.stale_etag.get(p, self.etag_of(self.data[p])),
                 "uploadedAt": self.meta.get(p, {}).get("uploadedAt", "")}
                for p in sorted(self.data) if p.startswith(prefix)]

    def delete(self, pathnames: list[str]) -> None:
        for pathname in pathnames:
            self.calls.append(("delete", pathname))
            self.data.pop(pathname, None)
            self.meta.pop(pathname, None)

    def fetch(self, url: str) -> bytes:
        self.calls.append(("fetch", url))
        pathname = self._pathname_of(url)
        status = self.fetch_status.get(pathname)
        if status is not None and status != 200:
            raise PublishError(f"{url} returned {status}")
        if pathname in self.stale:
            return self.stale[pathname]
        if pathname not in self.data:
            raise PublishError(f"{url} returned 404")
        return self.data[pathname]


# ------------------------------------------------------------------ the local run

def local_runs() -> list[str]:
    """Run ids under data/live, newest first. A run id sorts as text."""
    if not LIVE.is_dir():
        return []
    found = []
    for path in LIVE.iterdir():
        if not path.is_dir():
            continue
        try:
            parse_run_id(path.name)
        except Exception:                                   # noqa: BLE001
            continue
        found.append(path.name)
    return sorted(found, reverse=True)


def local_manifest(run_id: str) -> dict:
    path = run_dir(run_id) / MANIFEST
    if not path.exists():
        raise PublishError(f"{path} is missing, so {run_id} is not finished")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PublishError(f"{path} is not valid JSON: {exc}") from exc


def newest_publishable() -> tuple[str | None, str]:
    """The newest local run that finished its checks and is not published."""
    runs = local_runs()
    if not runs:
        return None, "no run has been built yet"
    for run_id in runs:
        if not (run_dir(run_id) / MANIFEST).exists():
            continue
        manifest = local_manifest(run_id)
        if manifest.get("published"):
            return None, f"{run_id} is the newest built run and is published"
        return run_id, f"{run_id} is built, checked and not published"
    return None, (f"{runs[0]} has no manifest, so it did not finish its "
                  "checks; nothing is publishable")


# ------------------------------------------------------------------ the payload

def tile_corner(lat: float, lon: float) -> tuple[float, float]:
    return (math.floor(lat / TILE_DEGREES) * TILE_DEGREES,
            math.floor(lon / TILE_DEGREES) * TILE_DEGREES)


def tile_id(lat: float, lon: float) -> str:
    """SPEC 8.4: the tile is named after its south-west corner."""
    lat_s, lon_w = tile_corner(lat, lon)
    ns = "N" if lat_s >= 0 else "S"
    ew = "E" if lon_w >= 0 else "W"
    return f"{abs(int(lat_s))}{ns}_{abs(int(lon_w))}{ew}"


def member_codes(member_totals: np.ndarray) -> np.ndarray:
    """mm to integer steps of MEMBER_STEP, rounded down (SPEC 8.4)."""
    if member_totals.min() < 0:
        raise PublishError(
            f"a member total of {float(member_totals.min())} mm is negative; "
            "SPEC 3.6 negatives are set to 0 in daily_totals, so this run "
            "did not come through that path")
    codes = np.floor(member_totals.astype(np.float64) / MEMBER_STEP + 1e-9)
    if codes.max() > MEMBER_MAX_CODE:
        raise PublishError(
            f"a member total of {float(member_totals.max())} mm needs code "
            f"{int(codes.max())}, which does not fit in 16 bits")
    return codes.astype(np.uint16)


def display_mm(codes: np.ndarray) -> np.ndarray:
    """What the panel shows: whole millimetres, rounded down (SPEC 8.4)."""
    return codes // STEPS_PER_MM


def check_codes(codes: np.ndarray, counts: np.ndarray,
                dots: np.ndarray) -> None:
    """The integers must rebuild the counts and the dots exactly."""
    back = (codes.astype(np.float64) * MEMBER_STEP).astype(np.float32)
    if not np.array_equal(counts_from(back), counts):
        raise PublishError("the published integers do not rebuild the counts")
    if not np.array_equal(dots_from(back), dots):
        raise PublishError("the published integers do not rebuild the dots")

    # SPEC 8.4: the displayed whole millimetre is on the same side of every
    # threshold as the count, because 1, 10 and 50 are whole numbers and
    # MEMBER_STEP divides a millimetre exactly.
    shown = display_mm(codes)
    for threshold in THRESHOLDS:
        if not np.array_equal(shown >= threshold, back >= threshold):
            raise PublishError(
                f"the whole-millimetre display disagrees with the "
                f"{threshold:g} mm threshold")


def counts_file_name(threshold: float, lead_day: int) -> str:
    return f"ge{threshold:g}mm_day{lead_day}.u8"


def counts_bytes(counts_2d: np.ndarray, india: np.ndarray) -> bytes:
    """One count a square, row major, 255 outside India (SPEC 8.4)."""
    if counts_2d.max() > cfg.N_MEMBERS:
        raise PublishError(f"a count of {int(counts_2d.max())} is above 51")
    out = np.where(india, counts_2d, NOT_INDIA).astype(np.uint8)
    return out.tobytes(order="C")


def tile_records(counts: np.ndarray, dots: np.ndarray, codes: np.ndarray,
                 india: np.ndarray) -> dict[str, dict]:
    """Per-square records, grouped into tiles, in grid order."""
    lats, lons = cfg.INDIA_LATS, cfg.INDIA_LONS
    tiles: dict[str, dict] = {}
    n_days = counts.shape[1]
    for i in range(len(lats)):
        for j in range(len(lons)):
            if not india[i, j]:
                continue
            lat, lon = lats[i], lons[j]
            name = tile_id(lat, lon)
            if name not in tiles:
                lat_s, lon_w = tile_corner(lat, lon)
                tiles[name] = {
                    "tile": name,
                    "lat_south": lat_s,
                    "lon_west": lon_w,
                    "degrees": TILE_DEGREES,
                    "step_mm": MEMBER_STEP,
                    "thresholds_mm": list(THRESHOLDS),
                    "dot_categories": list(DOT_NAMES),
                    "squares": [],
                }
            record = {
                "lat": round(float(lat), 2),
                "lon": round(float(lon), 2),
                "c": [[int(counts[k, d, i, j]) for k in range(len(THRESHOLDS))]
                      for d in range(n_days)],
                "d": [[int(dots[k, d, i, j]) for k in range(len(DOT_NAMES))]
                      for d in range(n_days)],
                "m": [[int(codes[d, m, i, j])
                       for m in range(codes.shape[1])]
                      for d in range(n_days)],
            }
            check_record(record)
            tiles[name]["squares"].append(record)
    return tiles


def check_record(record: dict) -> None:
    """SPEC 4.6's four identities, on the numbers actually being published,
    and the member integers against the square's own counts and dots."""
    for day, (counts, dots, codes) in enumerate(
            zip(record["c"], record["d"], record["m"]), start=1):
        where = f"{record['lat']} N {record['lon']} E day {day}"
        if sum(dots) != cfg.N_MEMBERS:
            raise PublishError(f"{where}: dots sum to {sum(dots)}, not 51")
        if counts[0] != dots[1] + dots[2] + dots[3]:
            raise PublishError(f"{where}: the 1 mm count and the dots differ")
        if counts[1] != dots[2] + dots[3]:
            raise PublishError(f"{where}: the 10 mm count and the dots differ")
        if counts[2] != dots[3]:
            raise PublishError(f"{where}: the 50 mm count and the dots differ")
        if len(codes) != cfg.N_MEMBERS:
            raise PublishError(f"{where}: {len(codes)} members, not 51")
        totals = [code * MEMBER_STEP for code in codes]
        for k, threshold in enumerate(THRESHOLDS):
            from_members = sum(1 for t in totals if t >= threshold)
            if from_members != counts[k]:
                raise PublishError(
                    f"{where}: {from_members} members reach {threshold:g} mm "
                    f"but the count says {counts[k]}")


def build_payload(run_id: str) -> tuple[list[Upload], dict]:
    """Every blob of a run, and the parts of the manifest that describe it."""
    from .india_mask import load as load_mask

    source = run_dir(run_id)
    run_manifest = local_manifest(run_id)
    days_bytes = (source / "days.json").read_bytes()
    days = json.loads(days_bytes.decode("utf-8"))

    with np.load(source / "squares.npz") as f:
        member_totals = f["member_totals"]
        counts = f["counts"]
        dots = f["dots"]
        india = f["india"]
        lat = f["lat"]
        lon = f["lon"]

    mask = load_mask()["india"]
    if not np.array_equal(india, mask):
        raise PublishError("the run's India mask is not the current mask")

    codes = member_codes(member_totals)
    check_codes(codes, counts, dots)

    prefix = f"runs/{run_id}"
    uploads: list[Upload] = []

    def add(pathname: str, data: bytes, content_type: str) -> None:
        uploads.append(Upload(pathname, data, content_type, RUN_FILE_MAX_AGE))

    published_at = dt.datetime.now(IST)
    run_record = dict(run_manifest)
    run_record["published"] = True
    run_record["published_at_ist"] = published_at.isoformat(timespec="seconds")
    add(f"{prefix}/run.json", as_json(run_record), JSON_TYPE)

    grid = {
        "n_lat": len(cfg.INDIA_LATS),
        "n_lon": len(cfg.INDIA_LONS),
        "grid_step_degrees": cfg.GRID_STEP,
        "lat": [round(float(v), 2) for v in lat],
        "lon": [round(float(v), 2) for v in lon],
        "order": f"row major, index = i * {len(cfg.INDIA_LONS)} + j, "
                 "i north to south, j west to east",
        "not_india": NOT_INDIA,
        "thresholds_mm": list(THRESHOLDS),
        "dot_categories": list(DOT_NAMES),
        "member_step_mm": MEMBER_STEP,
        "member_display": "whole millimetres, rounded down: "
                          "floor(code / 16)",
        "tile_degrees": TILE_DEGREES,
        "tile_rule": "a tile is named after its south-west corner in whole "
                     "degrees: floor(lat / 4) * 4, floor(lon / 4) * 4",
    }
    add(f"{prefix}/grid.json", as_json(grid), JSON_TYPE)
    add(f"{prefix}/days.json", days_bytes, JSON_TYPE)
    add(f"{prefix}/india.u8", india.astype(np.uint8).tobytes(order="C"),
        BYTES_TYPE)

    counts_files = []
    for k, threshold in enumerate(THRESHOLDS):
        for day in range(counts.shape[1]):
            name = counts_file_name(threshold, day + 1)
            counts_files.append(name)
            add(f"{prefix}/counts/{name}",
                counts_bytes(counts[k, day], india), BYTES_TYPE)

    tiles = tile_records(counts, dots, codes, india)
    square_count = sum(len(t["squares"]) for t in tiles.values())
    if square_count != int(india.sum()):
        raise PublishError(
            f"the tiles hold {square_count} squares but the mask has "
            f"{int(india.sum())}")
    for name in sorted(tiles):
        add(f"{prefix}/tiles/{name}.json", as_json(tiles[name]), JSON_TYPE)

    core = {
        "run_id": run_id,
        "model": run_manifest.get("model"),
        "stream": run_manifest.get("stream"),
        "param": run_manifest.get("param"),
        "steps": run_manifest.get("steps"),
        "members": run_manifest.get("members"),
        "run_time_utc": run_manifest.get("run_time_utc"),
        "run_time_ist": run_manifest.get("run_time_ist"),
        "built_time_ist": run_manifest.get("publish_time_ist"),
        "publish_time_ist": published_at.isoformat(timespec="seconds"),
        "thresholds_mm": list(THRESHOLDS),
        "dot_categories": list(DOT_NAMES),
        "member_step_mm": MEMBER_STEP,
        "member_display": "whole millimetres, rounded down",
        "grid": {k: grid[k] for k in ("n_lat", "n_lon", "grid_step_degrees",
                                      "order", "not_india", "tile_degrees")},
        "days": days,
        "counts_files": counts_files,
        "tiles": sorted(tiles),
        "india_squares": int(india.sum()),
        "india": run_manifest.get("india"),
        "paths": {
            "run": f"{prefix}/run.json",
            "grid": f"{prefix}/grid.json",
            "days": f"{prefix}/days.json",
            "india": f"{prefix}/india.u8",
            "counts": f"{prefix}/counts",
            "tiles": f"{prefix}/tiles",
        },
    }
    return uploads, core


def as_json(value) -> bytes:
    """One formatting of JSON everywhere, so a sha256 means something."""
    return json.dumps(value, separators=(",", ":"),
                      sort_keys=False).encode("utf-8")


def manifest_upload(core: dict, uploads: list[Upload], retention: dict,
                    previous: str | None) -> Upload:
    manifest = dict(core)
    manifest["previous_run_id"] = previous
    manifest["retention"] = retention
    manifest["files"] = {u.pathname: {"bytes": u.size, "sha256": u.sha256}
                         for u in uploads}
    manifest["bytes_total"] = sum(u.size for u in uploads)
    return Upload(MANIFEST, as_json(manifest), JSON_TYPE, MANIFEST_MAX_AGE)


def immutable_manifest_upload(run_id: str, manifest: Upload) -> Upload:
    """The same bytes as `manifest.json`, on a pathname never overwritten.

    SPEC 8.10: the bytes of the current manifest can then be read back and
    hashed like everything else, because nothing has ever been served from
    this pathname before.
    """
    return Upload(f"{RUNS}{run_id}/{MANIFEST}", manifest.data,
                  JSON_TYPE, RUN_FILE_MAX_AGE)


def marker_upload(run_id: str, manifest: Upload, manifest_etag: str | None,
                  uploads: list[Upload], retention: dict,
                  adopted: dict | None = None) -> Upload:
    """SPEC 8.5: the last write of a publish, and the only one that counts.

    It is immutable, so `list` can be trusted about it forever, and its
    pathname carries the run id, so run selection needs no body at all.
    """
    marker = {
        "run_id": run_id,
        "published_at_ist": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "manifest_sha256": manifest.sha256,
        "manifest_etag": manifest_etag,
        "manifest_copy": f"{RUNS}{run_id}/{MANIFEST}",
        "files": len(uploads) + 2,
        "bytes_total": sum(u.size for u in uploads) + manifest.size * 2,
        "retention": retention,
        "note": "written last, after the manifest and after the read-back. "
                "Its presence means this publish finished.",
    }
    if adopted is not None:
        marker.update(adopted)
    return Upload(marker_name(run_id), as_json(marker), JSON_TYPE,
                  RUN_FILE_MAX_AGE)


def adoption_marker(published: dict) -> Upload:
    """SPEC 8.6: the marker a pre-marker publish never wrote.

    Written when `list` finds a manifest and no marker at all. It records
    what the store itself says, claims nothing about bytes this job did not
    write, and deletes and republishes nothing.
    """
    run_id = published["run_id"]
    marker = {
        "run_id": run_id,
        "published_at_ist": None,
        "adopted_at_ist": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "adopted_from": MANIFEST,
        "manifest_sha256": published.get("manifest_sha256"),
        "manifest_etag": None,
        "note": "This run was published before publish.py wrote markers, so "
                "no marker existed for it. This one was written from the "
                "store's own manifest.json, which named this run. Nothing "
                "was republished and nothing was deleted.",
    }
    return Upload(marker_name(run_id), as_json(marker), JSON_TYPE,
                  RUN_FILE_MAX_AGE)


# ------------------------------------------------------------------ the store side

def marker_name(run_id: str) -> str:
    return f"{MARKERS}{run_id}.json"


def run_id_of_marker(pathname: str) -> str | None:
    """`published/20261112T00Z.json` -> `20261112T00Z`, or None."""
    if not pathname.startswith(MARKERS) or not pathname.endswith(".json"):
        return None
    name = pathname[len(MARKERS):-len(".json")]
    if "/" in name:
        return None
    try:
        parse_run_id(name)
    except Exception:                                       # noqa: BLE001
        return None
    return name


def read_published(store: Store) -> dict:
    """SPEC 8.6: what the store publishes, decided from `list` alone.

    `list` is an API call. It is not served by the CDN, it cannot be stale,
    and a marker pathname carries its own run id, so in the normal case this
    answers without fetching anything at all.

    Returns a dict with `run_id` (None for an empty store), `source`
    (`marker`, `manifest` or `empty`), `legacy` and `reason`. Only a `list`
    that succeeds and finds neither a marker nor a manifest is an empty
    store; every other failure raises.
    """
    blobs = store.list(MARKERS)
    markers, strays = [], []
    for blob in blobs:
        pathname = blob.get("pathname", "")
        run_id = run_id_of_marker(pathname)
        if run_id is None:
            strays.append(pathname)
        else:
            markers.append(run_id)

    if markers:
        run_id = max(markers)
        return {
            "run_id": run_id,
            "source": "marker",
            "legacy": False,
            "strays": sorted(strays),
            "reason": (f"the store publishes {run_id}, from "
                       f"{marker_name(run_id)} of {len(markers)} marker(s)"),
        }

    # No marker. Either the store is empty, or it was published by the code
    # that existed before markers did, in which case manifest.json is the
    # only record of it. This branch is the one place a CDN-served body is
    # believed, and it is believed once: the next publish writes the marker
    # that was missing (SPEC 8.6).
    listed = store.list(MANIFEST)
    exact = [b for b in listed if b.get("pathname") == MANIFEST]
    if not exact:
        return {"run_id": None, "source": "empty", "legacy": False,
                "strays": sorted(strays),
                "reason": "the store has no marker and no manifest.json; "
                          "nothing is published yet"}

    url = exact[0].get("url")
    if not url:
        raise PublishError("the store listed manifest.json with no URL")
    raw = store.fetch(url)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise PublishError(
            f"the store's manifest.json is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PublishError("the store's manifest.json is not an object")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise PublishError("the store's manifest.json has no run_id")
    try:
        parse_run_id(run_id)
    except Exception as exc:                                # noqa: BLE001
        raise PublishError(
            f"the store's manifest.json has run_id {run_id!r}, which is not "
            f"a run id: {exc}") from exc
    return {
        "run_id": run_id,
        "source": "manifest",
        "legacy": True,
        "strays": sorted(strays),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "reason": (f"the store publishes {run_id}, from manifest.json at "
                   f"{url}, with no marker: published before markers existed"),
    }


def retention_plan(listing: list[dict], current: str,
                   keep: int = KEEP_RUNS) -> dict:
    """SPEC 8.7. Which run prefixes to keep, which blobs to delete.

    The listing may hold both `runs/<run_id>/...` files and the
    `published/<run_id>.json` markers of 8.5. A run that is dropped loses
    both; a marker whose run has already gone is dropped with it, so markers
    cannot pile up for runs that no longer exist.
    """
    by_run: dict[str, list[dict]] = {}
    for blob in listing:
        pathname = blob.get("pathname", "")
        marker_run = run_id_of_marker(pathname)
        if marker_run is not None:
            by_run.setdefault(marker_run, []).append(blob)
            continue
        parts = pathname.split("/")
        if len(parts) < 3 or parts[0] != "runs":
            continue
        by_run.setdefault(parts[1], []).append(blob)

    valid, invalid = [], []
    for run_id in by_run:
        try:
            parse_run_id(run_id)
        except Exception:                                   # noqa: BLE001
            invalid.append(run_id)
            continue
        valid.append(run_id)

    # The listing is taken before this run is uploaded, so its own blobs are
    # not in it yet. It still counts as one of the eight.
    if current not in valid:
        valid.append(current)

    ordered = sorted(valid, reverse=True)
    kept = ordered[:keep]
    if current not in kept:                 # rule 2, whatever its position
        kept = [current] + [r for r in kept if r != current][:keep - 1]
    dropped = [r for r in ordered if r not in kept]

    deleted = [{"pathname": b["pathname"], "bytes": int(b.get("size", 0)),
                "run_id": run_id}
               for run_id in dropped for b in by_run[run_id]]
    deleted.sort(key=lambda d: d["pathname"])
    return {
        "keep_runs": keep,
        "current_run_id": current,
        "kept": sorted(kept, reverse=True),
        "deleted_runs": dropped,
        "deleted": deleted,
        "deleted_bytes": sum(d["bytes"] for d in deleted),
        "left_alone": sorted(invalid),
    }


def read_back(store: Store, uploads: list[Upload],
              results: dict[str, str]) -> dict:
    """SPEC 8.10: fetch every immutable file from its public URL, no token.

    Every pathname here is written once and never overwritten, so the CDN
    cannot be holding an older version of it: a byte that comes back wrong
    is wrong. `manifest.json` is **not** in this list, because it is the one
    blob that is rewritten and the edge may legitimately serve the previous
    copy for up to 60 seconds. It is checked by its ETag instead, in
    `verify_manifest`.
    """
    checked = 0
    for upload in uploads:
        if upload.pathname == MANIFEST:
            raise PublishError("manifest.json cannot be byte-verified from a "
                               "public URL; see verify_manifest")
        url = results.get(upload.pathname)
        if not url:
            raise PublishError(f"{upload.pathname} came back with no URL")
        got = store.fetch(url)
        if hashlib.sha256(got).hexdigest() != upload.sha256:
            raise PublishError(
                f"{upload.pathname} read back different from what was sent")
        checked += 1
    return {"files": checked, "bytes": sum(u.size for u in uploads)}


def verify_manifest(store: Store, manifest: Upload,
                    put_result: dict) -> dict:
    """SPEC 8.10: did the manifest write land? Decided by ETag, not by bytes.

    `put` returns the ETag the store recorded and `list` returns the ETag the
    store holds now. Both come from the API, neither is served by the CDN, so
    agreement between them means the write landed, whatever the edge is still
    handing out. The public body is fetched too, but a difference there is
    **logged and not failed**: by Vercel's documentation an overwrite takes
    up to 60 seconds to propagate, and failing a publish for that would mean
    failing a publish that was entirely correct.
    """
    put_etag = put_result.get("etag")
    listed = [b for b in store.list(MANIFEST)
              if b.get("pathname") == MANIFEST]
    if not listed:
        raise PublishError(
            "manifest.json is not in the store after being written")
    list_etag = listed[0].get("etag")
    if not put_etag or not list_etag:
        raise PublishError(
            "the store returned no ETag for manifest.json, so there is no "
            "way to confirm the write without trusting a cached body")
    if put_etag != list_etag:
        raise PublishError(
            f"manifest.json was written with ETag {put_etag} but the store "
            f"now holds {list_etag}: another publish overwrote it")

    stale = False
    url = put_result.get("url") or listed[0].get("url")
    if url:
        try:
            got = store.fetch(url)
        except PublishError as exc:
            log(f"manifest.json could not be read from its public URL "
                f"({exc}); the ETags agree, so the write landed")
        else:
            stale = hashlib.sha256(got).hexdigest() != manifest.sha256
    return {"put_etag": put_etag, "list_etag": list_etag,
            "etags_agree": True, "edge_stale": stale}


# ------------------------------------------------------------------ the publish

def publish(store: Store, run_id: str | None = None,
            work_dir: Path | None = None, mark: bool = True) -> dict:
    """Publish one run. SPEC 8.5 to 8.10, in that order."""
    remote = read_published(store)
    log(f"store: {remote['reason']}")
    for stray in remote["strays"]:
        log(f"store: {stray!r} under {MARKERS} is not a marker; left alone")
    published = remote["run_id"]

    # SPEC 8.6. A store published before markers existed gets the marker it
    # never had, written from its own manifest. This is an addition and
    # nothing else: no file is overwritten, nothing is deleted, and the run
    # it names is not republished.
    if remote["legacy"]:
        marker = adoption_marker(remote)
        store.put_many([marker])
        log(f"store: wrote the missing marker {marker.pathname} for "
            f"{published}, which was published before markers existed")

    if run_id is None:
        run_id, local_reason = newest_publishable()
        log(f"local: {local_reason}")
        if run_id is None:
            return {"published": False, "reason": local_reason}

    if published is not None:
        if run_id == published:
            reason = f"{run_id} is already published"
            log(f"decision: {reason}")
            return {"published": False, "reason": reason}
        if run_id < published:
            reason = (f"{run_id} is older than the published run "
                      f"{published}; an older run never replaces a newer one")
            log(f"decision: {reason}")
            return {"published": False, "reason": reason}

    uploads, core = build_payload(run_id)
    log(f"{run_id}: {len(uploads)} run files, "
        f"{sum(u.size for u in uploads) / 1e6:.2f} MB, "
        f"{len(core['tiles'])} tiles")

    listing = store.list(RUNS) + store.list(MARKERS)
    plan = retention_plan(listing, run_id)
    manifest = manifest_upload(core, uploads, plan, published)
    copy = immutable_manifest_upload(run_id, manifest)

    if work_dir is not None:
        write_locally(work_dir, [*uploads, copy, manifest])

    # 1. The run's own files, then the immutable copy of the manifest. The
    #    store still describes the previous run throughout.
    results = {r["pathname"]: r["url"]
               for r in store.put_many([*uploads, copy])}
    log(f"{run_id}: {len(uploads) + 1} run files uploaded, including the "
        f"immutable copy of the manifest; manifest not yet moved")

    # 2. The one mutable blob. This is the moment the site changes.
    manifest_result = store.put_many([manifest])[0]
    results[MANIFEST] = manifest_result["url"]
    log(f"{run_id}: manifest written; the site now shows this run")
    # The public address of the manifest, logged because the store id is
    # nowhere in the repository (SPEC 8.14) and the site and HC7 both need
    # it. It is a read-only public URL and not a credential.
    log(f"manifest URL: {results[MANIFEST]}")

    for entry in plan["deleted"]:
        log(f"retention: deleting {entry['pathname']} "
            f"({entry['bytes']} bytes, run {entry['run_id']})")
    store.delete([entry["pathname"] for entry in plan["deleted"]])
    for run in plan["left_alone"]:
        log(f"retention: left alone, {run!r} is not a run id")
    verify_retention(store, plan)

    checked = read_back(store, [*uploads, copy], results)
    log(f"{run_id}: read back {checked['files']} immutable files from their "
        f"public URLs, {checked['bytes'] / 1e6:.2f} MB, every sha256 matched")

    manifest_check = verify_manifest(store, manifest, manifest_result)
    log(f"{run_id}: manifest confirmed by ETag {manifest_check['put_etag']}, "
        f"the same one list returns")
    if manifest_check["edge_stale"]:
        log("note: the public manifest.json is still the previous one. "
            "Vercel documents up to 60 s for an overwrite to propagate, the "
            "ETags agree, and the immutable copy read back exactly, so this "
            "is not a failure")

    # 3. The marker, last of all, because it means "this publish finished".
    #    A publish that died before here is retried by the next run rather
    #    than remembered as done.
    marker = marker_upload(run_id, manifest, manifest_check["put_etag"],
                           uploads, plan)
    if work_dir is not None:
        write_locally(work_dir, [marker])
    store.put_many([marker])
    log(f"{run_id}: {marker.pathname} written last; the store now says this "
        f"run is published")

    if mark:
        mark_published(run_id)
    return {"published": True, "run_id": run_id, "files": len(uploads) + 3,
            "bytes": sum(u.size for u in [*uploads, copy, manifest, marker]),
            "retention": plan, "read_back": checked,
            "manifest": manifest_check, "marker": marker.pathname,
            "reason": f"{run_id} published"}


def verify_retention(store: Store, plan: dict) -> None:
    if not plan["deleted"]:
        return
    left = {b["pathname"] for b in store.list("runs/")}
    still = sorted(d["pathname"] for d in plan["deleted"]
                   if d["pathname"] in left)
    if still:
        raise PublishError(
            f"{len(still)} blob(s) the manifest says were deleted are still "
            f"there, the first being {still[0]}")


def write_locally(work_dir: Path, uploads: list[Upload]) -> None:
    """Keep the exact bytes that were published (SPEC 8.1)."""
    for upload in uploads:
        path = work_dir / upload.pathname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(upload.data)


def mark_published(run_id: str) -> None:
    path = run_dir(run_id) / MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["published"] = True
    manifest["published_at_ist"] = dt.datetime.now(IST).isoformat(
        timespec="seconds")
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


LOG_STREAM = sys.stdout      # remote-run-id moves this to stderr


def log(message: str) -> None:
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} IST  {message}"
    print(line, file=LOG_STREAM, flush=True)
    try:
        cfg.LOGS.mkdir(parents=True, exist_ok=True)
        with open(cfg.LOGS / "publish.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ the CLI

def work_dir_for(run_id: str) -> Path:
    path = PUBLISH / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "remote-run-id" in argv:
        # SPEC 8.6 step 1. Prints the run id, or an empty line for an empty
        # store, and exits 1 on anything else. Standard output carries the
        # run id and nothing else, so the workflow can read it straight;
        # every log line goes to standard error.
        global LOG_STREAM
        LOG_STREAM = sys.stderr
        try:
            remote = read_published(BlobStore(PUBLISH))
        except PublishError as exc:
            log(f"FAILED reading what the store publishes: {exc}")
            return 1
        print(remote["run_id"] or "")
        log(remote["reason"])
        return 0

    dry_run = "--dry-run" in argv
    try:
        if dry_run:
            run_id, reason = newest_publishable()
            log(f"local: {reason}")
            if run_id is None:
                return 0
            store = FakeStore()
            result = publish(store, run_id, work_dir_for(run_id), mark=False)
            log("--dry-run: nothing left this laptop; the uploads went to an "
                "in-memory store")
            log(f"--dry-run: the exact bytes are in {work_dir_for(run_id)}")
        else:
            run_id, reason = newest_publishable()
            if run_id is None:
                log(f"nothing to publish: {reason}")
                return 0
            result = publish(BlobStore(work_dir_for(run_id)), run_id)
        if not result["published"]:
            log(f"nothing published: {result['reason']}")
            return 0
        log(f"{result['run_id']}: published {result['files']} files, "
            f"{result['bytes'] / 1e6:.2f} MB, "
            f"{len(result['retention']['deleted'])} old blob(s) deleted")
        return 0
    except Exception as exc:                                # noqa: BLE001
        log(f"FAILED {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
