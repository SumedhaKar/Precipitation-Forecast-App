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
   Only a `list` that succeeds and finds no manifest means "nothing has been
   published yet". A failed list, or a manifest that cannot be fetched or
   parsed, is a failure and publishes nothing.

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
import time
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
        """Read a public URL. No token: this is what the website does."""
        request = urllib.request.Request(url, headers={
            "User-Agent": "precipitation-forecast/publish",
            "Cache-Control": "no-cache",
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

    def url_for(self, pathname: str) -> str:
        return f"{self.base}/{pathname}"

    def _pathname_of(self, url: str) -> str:
        return url.split("?", 1)[0][len(self.base) + 1:]

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
                            "size": upload.size})
        return results

    def list(self, prefix: str = "") -> list[dict]:
        self.calls.append(("list", prefix))
        if self.list_error is not None:
            raise PublishError(f"list failed: {self.list_error}")
        return [{"pathname": p, "url": self.url_for(p),
                 "size": len(self.data[p]),
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
        if pathname not in self.data:
            raise PublishError(f"{url} returned 404")
        return self.data[pathname]


def cache_busted(url: str, nonce: str | None = None) -> str:
    """SPEC 8.6 and 8.10: never read a manifest the CDN has been holding."""
    nonce = nonce or str(time.time_ns())
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}cb={nonce}"


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


# ------------------------------------------------------------------ the store side

def read_remote_manifest(store: Store) -> tuple[dict | None, str]:
    """SPEC 8.6. Returns (manifest or None, reason).

    None only when `list` succeeded and there is no manifest. Every other
    way this can go wrong raises.
    """
    blobs = store.list(MANIFEST)
    exact = [b for b in blobs if b.get("pathname") == MANIFEST]
    if not exact:
        return None, "the store has no manifest.json; nothing is published yet"

    url = exact[0].get("url")
    if not url:
        raise PublishError("the store listed manifest.json with no URL")
    raw = store.fetch(cache_busted(url))
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
    return manifest, f"the store currently publishes {run_id}"


def retention_plan(listing: list[dict], current: str,
                   keep: int = KEEP_RUNS) -> dict:
    """SPEC 8.7. Which run prefixes to keep, which blobs to delete."""
    by_run: dict[str, list[dict]] = {}
    for blob in listing:
        pathname = blob.get("pathname", "")
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
                "run_id": b["pathname"].split("/")[1]}
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


def read_back(store: Store, uploads: list[Upload], results: dict[str, str],
              manifest: Upload) -> dict:
    """SPEC 8.10: fetch every published file from its public URL, no token."""
    checked = 0
    for upload in [*uploads, manifest]:
        url = results.get(upload.pathname)
        if not url:
            raise PublishError(f"{upload.pathname} came back with no URL")
        if upload.pathname == MANIFEST:
            url = cache_busted(url)
        got = store.fetch(url)
        if hashlib.sha256(got).hexdigest() != upload.sha256:
            raise PublishError(
                f"{upload.pathname} read back different from what was sent")
        checked += 1
    return {"files": checked,
            "bytes": sum(u.size for u in [*uploads, manifest])}


# ------------------------------------------------------------------ the publish

def publish(store: Store, run_id: str | None = None,
            work_dir: Path | None = None, mark: bool = True) -> dict:
    """Publish one run. SPEC 8.5 to 8.10, in that order."""
    remote, reason = read_remote_manifest(store)
    log(f"store: {reason}")
    published = remote.get("run_id") if remote else None

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

    listing = store.list("runs/")
    plan = retention_plan(listing, run_id)
    manifest = manifest_upload(core, uploads, plan, published)

    if work_dir is not None:
        write_locally(work_dir, [*uploads, manifest])

    results = {r["pathname"]: r["url"] for r in store.put_many(uploads)}
    log(f"{run_id}: run files uploaded, manifest not yet moved")
    results.update({r["pathname"]: r["url"]
                    for r in store.put_many([manifest])})
    log(f"{run_id}: manifest written last; the site now shows this run")

    for entry in plan["deleted"]:
        log(f"retention: deleting {entry['pathname']} "
            f"({entry['bytes']} bytes, run {entry['run_id']})")
    store.delete([entry["pathname"] for entry in plan["deleted"]])
    for run in plan["left_alone"]:
        log(f"retention: left alone, {run!r} is not a run id")
    verify_retention(store, plan)

    checked = read_back(store, uploads, results, manifest)
    log(f"{run_id}: read back {checked['files']} files from their public "
        f"URLs, {checked['bytes'] / 1e6:.2f} MB, every sha256 matched")

    if mark:
        mark_published(run_id)
    return {"published": True, "run_id": run_id, "files": len(uploads) + 1,
            "bytes": sum(u.size for u in [*uploads, manifest]),
            "retention": plan, "read_back": checked,
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


def log(message: str) -> None:
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} IST  {message}"
    print(line, flush=True)
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
        # store, and exits 1 on anything else.
        try:
            remote, reason = read_remote_manifest(BlobStore(PUBLISH))
        except PublishError as exc:
            log(f"FAILED reading the store's manifest: {exc}")
            return 1
        print(remote["run_id"] if remote else "")
        log(reason)
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
