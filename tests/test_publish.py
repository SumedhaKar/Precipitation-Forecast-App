"""SPEC 8.13: the publish rules, against a fake store. No network, no token.

Everything here runs on a made-up run on a small grid, except the two tests
that read the real run on this laptop, which skip when `data/` is not there
(it is never committed, so they skip in CI).

The order tests are the point of the fake store: "the manifest is written
last" and "no deletion happens before that write" are claims about the order
of calls, not about their contents, so `FakeStore.calls` is what they check.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline import config as cfg
from pipeline import india_mask, publish
from pipeline.publish import (
    MANIFEST,
    MANIFEST_MAX_AGE,
    MEMBER_STEP,
    NOT_INDIA,
    RUN_FILE_MAX_AGE,
    FakeStore,
    PublishError,
    display_mm,
    member_codes,
    retention_plan,
    tile_id,
)
from pipeline.run_live import counts_from, dots_from

N_LAT, N_LON = 8, 7          # a small grid, so the tests are quick
N_DAYS = 5
LAT_MAX, LON_MIN = 24.0, 72.0
REAL_RUN = "20261112T00Z"


# ------------------------------------------------------------------ a made-up run

def small_grid(monkeypatch) -> np.ndarray:
    """Put a small grid and a small India mask in front of the real ones."""
    lats = tuple(LAT_MAX - cfg.GRID_STEP * i for i in range(N_LAT))
    lons = tuple(LON_MIN + cfg.GRID_STEP * j for j in range(N_LON))
    monkeypatch.setattr(cfg, "INDIA_LATS", lats)
    monkeypatch.setattr(cfg, "INDIA_LONS", lons)

    india = np.zeros((N_LAT, N_LON), dtype=bool)
    india[1:7, 1:6] = True                      # 30 India squares, not all
    monkeypatch.setattr(india_mask, "load", lambda: {"india": india})
    return india


def totals_for(india: np.ndarray, seed: int = 7) -> np.ndarray:
    """Member totals that land on exact multiples of MEMBER_STEP, as real
    ones do, and that straddle all three thresholds."""
    rng = np.random.default_rng(seed)
    codes = rng.integers(0, 1200, size=(N_DAYS, cfg.N_MEMBERS, *india.shape))
    totals = (codes * MEMBER_STEP).astype(np.float32)
    totals[:, :, ~india] = 0.0
    return totals


def write_run(root: Path, run_id: str, india: np.ndarray,
              totals: np.ndarray | None = None,
              published: bool = False, with_manifest: bool = True) -> Path:
    """A run directory shaped like the one SPEC 4.6 writes."""
    if totals is None:
        totals = totals_for(india)
    out = root / run_id
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "squares.npz",
        member_totals=totals,
        counts=counts_from(totals),
        dots=dots_from(totals),
        india=india,
        lat=np.asarray(cfg.INDIA_LATS, dtype=np.float64),
        lon=np.asarray(cfg.INDIA_LONS, dtype=np.float64),
    )
    (out / "days.json").write_text(json.dumps(
        [{"lead_day": d, "label": f"day {d}"} for d in range(1, N_DAYS + 1)],
        indent=2), encoding="utf-8")
    if with_manifest:
        (out / MANIFEST).write_text(json.dumps({
            "run_id": run_id,
            "model": "aifs-ens", "stream": "enfo", "param": "tp",
            "steps": list(cfg.STEPS), "members": cfg.N_MEMBERS,
            "run_time_utc": "2026-11-12T00:00:00+00:00",
            "run_time_ist": "2026-11-12T05:30:00+05:30",
            "publish_time_ist": "2026-11-12T12:36:12+05:30",
            "india": {"india_squares": int(india.sum())},
            "published": published,
        }, indent=2), encoding="utf-8")
    return out


@pytest.fixture()
def run_root(tmp_path, monkeypatch):
    """A fake data/live, with publish.py pointed at it."""
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(publish, "LIVE", live)
    monkeypatch.setattr(publish, "run_dir", lambda run_id: live / run_id)
    return live


@pytest.fixture()
def india(monkeypatch):
    return small_grid(monkeypatch)


def seed_store(store: FakeStore, run_id: str, runs: list[str] | None = None,
               manifest: dict | None = None) -> FakeStore:
    """A store that already publishes `run_id`, with blobs for `runs`."""
    for old in runs if runs is not None else [run_id]:
        for name in ("days.json", "grid.json"):
            store.data[f"runs/{old}/{name}"] = f"{old} {name}".encode()
    body = manifest if manifest is not None else {"run_id": run_id}
    store.data[MANIFEST] = json.dumps(body).encode()
    store.calls.clear()
    return store


def puts(store: FakeStore) -> list[str]:
    return [p for kind, p in ((c[0], c[1]) for c in store.calls)
            if kind == "put"]


def published_tiles(store: FakeStore, run_id: str) -> list[dict]:
    records = []
    for pathname, data in store.data.items():
        if pathname.startswith(f"runs/{run_id}/tiles/"):
            records.extend(json.loads(data.decode())["squares"])
    return records


# ------------------------------------------------------------------ order

def test_the_manifest_is_the_last_write(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    result = publish.publish(store, "20261112T00Z", mark=False)

    assert result["published"] is True
    written = puts(store)
    assert written[-1] == MANIFEST
    assert written.count(MANIFEST) == 1

    manifest = json.loads(store.data[MANIFEST].decode())
    order = {pathname: i for i, pathname in enumerate(written)}
    for pathname in manifest["files"]:
        assert order[pathname] < order[MANIFEST], pathname


def test_no_deletion_happens_before_the_manifest_write(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    old = [f"202610{day:02d}T00Z" for day in range(1, 11)]
    store = seed_store(FakeStore(), "20261111T00Z", runs=[*old, "20261111T00Z"])

    publish.publish(store, "20261112T00Z", mark=False)

    kinds = [c[0] for c in store.calls]
    manifest_at = store.calls.index(("put", MANIFEST))
    assert "delete" in kinds, "this run should have deleted something"
    assert kinds.index("delete") > manifest_at


# ------------------------------------------------------------------ which run

def test_an_older_local_run_never_replaces_a_newer_published_one(run_root,
                                                                 india):
    write_run(run_root, "20261110T00Z", india)
    store = seed_store(FakeStore(), "20261112T00Z")

    result = publish.publish(store, "20261110T00Z", mark=False)

    assert result["published"] is False
    assert "older" in result["reason"]
    assert puts(store) == []


def test_the_same_run_is_never_republished(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = seed_store(FakeStore(), "20261112T00Z")

    result = publish.publish(store, "20261112T00Z", mark=False)

    assert result["published"] is False
    assert "already published" in result["reason"]
    assert puts(store) == []


def test_a_run_with_no_manifest_is_not_publishable(run_root, india):
    write_run(run_root, "20261112T00Z", india, with_manifest=False)
    run_id, reason = publish.newest_publishable()
    assert run_id is None
    assert "did not finish its checks" in reason


def test_a_run_already_marked_published_is_not_publishable(run_root, india):
    write_run(run_root, "20261112T00Z", india, published=True)
    run_id, reason = publish.newest_publishable()
    assert run_id is None
    assert "is published" in reason


def test_the_newest_run_is_the_one_chosen(run_root, india):
    write_run(run_root, "20261110T00Z", india)
    write_run(run_root, "20261112T00Z", india)
    run_id, _ = publish.newest_publishable()
    assert run_id == "20261112T00Z"


def test_an_empty_store_publishes_the_first_run(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()

    remote, reason = publish.read_remote_manifest(store)
    assert remote is None
    assert "nothing is published yet" in reason

    assert publish.publish(store, "20261112T00Z", mark=False)["published"]


# ------------------------------------------------------------------ a broken store

def test_a_failed_list_is_a_failure_and_not_an_empty_store(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore(list_error="403 from the store")

    with pytest.raises(PublishError, match="list failed"):
        publish.read_remote_manifest(store)
    with pytest.raises(PublishError):
        publish.publish(store, "20261112T00Z", mark=False)
    assert puts(store) == []


@pytest.mark.parametrize("status", [404, 500])
def test_a_manifest_that_cannot_be_fetched_is_a_failure(status):
    store = seed_store(FakeStore(), "20261112T00Z")
    store.fetch_status[MANIFEST] = status

    with pytest.raises(PublishError, match=str(status)):
        publish.read_remote_manifest(store)


@pytest.mark.parametrize("body, complaint", [
    (b"not json at all", "not valid JSON"),
    (b"[1, 2, 3]", "not an object"),
    (b'{"run": "20261112T00Z"}', "no run_id"),
    (b'{"run_id": ""}', "no run_id"),
    (b'{"run_id": "yesterday"}', "not a run id"),
    (b'{"run_id": "20261112T00"}', "not a run id"),
])
def test_a_manifest_that_cannot_be_trusted_is_a_failure(body, complaint):
    store = FakeStore()
    store.data[MANIFEST] = body

    with pytest.raises(PublishError, match=complaint):
        publish.read_remote_manifest(store)


def test_the_run_selection_fetch_is_cache_busted():
    store = seed_store(FakeStore(), "20261112T00Z")
    publish.read_remote_manifest(store)

    fetches = [c[1] for c in store.calls if c[0] == "fetch"]
    assert len(fetches) == 1
    assert "?cb=" in fetches[0]
    assert fetches[0].split("?")[0].endswith(MANIFEST)


def test_the_read_back_notices_a_difference(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    uploads, core = publish.build_payload("20261112T00Z")
    manifest = publish.manifest_upload(core, uploads, {"deleted": []}, None)
    urls = {u.pathname: store.url_for(u.pathname) for u in [*uploads, manifest]}
    tampered = uploads[0]
    store.data[tampered.pathname] = store.data[tampered.pathname] + b" "

    with pytest.raises(PublishError, match="read back different"):
        publish.read_back(store, uploads, urls, manifest)


# ------------------------------------------------------------------ retention

def listing_for(runs: list[str], extra: list[str] | None = None) -> list[dict]:
    blobs = [{"pathname": f"runs/{run}/days.json", "size": 10, "url": ""}
             for run in runs]
    blobs += [{"pathname": p, "size": 10, "url": ""} for p in extra or []]
    return blobs


def test_retention_keeps_the_newest_eight_including_this_run():
    old = [f"202611{day:02d}T00Z" for day in range(1, 12)]     # 01 to 11
    plan = retention_plan(listing_for(old), "20261112T00Z")

    assert plan["kept"][0] == "20261112T00Z"
    assert len(plan["kept"]) == 8
    assert plan["deleted_runs"] == ["20261104T00Z", "20261103T00Z",
                                    "20261102T00Z", "20261101T00Z"]
    assert all(d["run_id"] in plan["deleted_runs"] for d in plan["deleted"])


def test_retention_never_deletes_the_run_the_manifest_points_at():
    # The current run is the ninth newest, which should not happen, and must
    # still survive (SPEC 8.7 rule 2).
    runs = [f"202611{day:02d}T00Z" for day in range(4, 13)]    # 04 to 12
    current = "20261104T00Z"
    plan = retention_plan(listing_for(runs), current)

    assert current in plan["kept"]
    assert current not in plan["deleted_runs"]
    assert all(d["run_id"] != current for d in plan["deleted"])
    assert len(plan["kept"]) == 8


def test_retention_leaves_prefixes_that_are_not_run_ids():
    plan = retention_plan(
        listing_for(["20261101T00Z"],
                    extra=["runs/scratch/notes.txt", "runs/old backup/x.json"]),
        "20261112T00Z")

    assert plan["left_alone"] == ["old backup", "scratch"]
    assert all("scratch" not in d["pathname"] for d in plan["deleted"])
    assert all("backup" not in d["pathname"] for d in plan["deleted"])


def test_retention_deletes_nothing_when_there_are_few_runs():
    plan = retention_plan(listing_for(["20261110T00Z", "20261111T00Z"]),
                          "20261112T00Z")
    assert plan["deleted"] == []
    assert plan["deleted_runs"] == []


# ------------------------------------------------------------------ the bytes

def test_every_sha256_in_the_manifest_matches_the_bytes(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    manifest = json.loads(store.data[MANIFEST].decode())
    assert manifest["files"]
    for pathname, record in manifest["files"].items():
        data = store.data[pathname]
        assert record["bytes"] == len(data)
        assert record["sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["bytes_total"] == sum(
        len(store.data[p]) for p in manifest["files"])


def test_the_cache_ages_are_sixty_seconds_and_one_month(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    assert store.meta[MANIFEST]["max_age"] == MANIFEST_MAX_AGE == 60
    for pathname, meta in store.meta.items():
        if pathname == MANIFEST:
            continue
        assert meta["max_age"] == RUN_FILE_MAX_AGE == 2_592_000


def test_the_content_types_are_set(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    for pathname, meta in store.meta.items():
        expected = ("application/json" if pathname.endswith(".json")
                    else "application/octet-stream")
        assert meta["content_type"] == expected, pathname


def test_counts_files_are_one_byte_a_square_with_255_outside_india(run_root,
                                                                   india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    with np.load(run_root / "20261112T00Z" / "squares.npz") as f:
        counts = f["counts"]

    seen = 0
    for k, threshold in enumerate((1.0, 10.0, 50.0)):
        for day in range(N_DAYS):
            name = publish.counts_file_name(threshold, day + 1)
            data = store.data[f"runs/20261112T00Z/counts/{name}"]
            assert len(data) == india.size
            grid = np.frombuffer(data, dtype=np.uint8).reshape(india.shape)
            assert np.array_equal(grid[~india],
                                  np.full((~india).sum(), NOT_INDIA, np.uint8))
            assert np.array_equal(grid[india], counts[k, day][india])
            assert grid[india].max() <= cfg.N_MEMBERS
            seen += 1
    assert seen == 15


def test_the_india_mask_is_published_as_bytes(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    data = store.data["runs/20261112T00Z/india.u8"]
    grid = np.frombuffer(data, dtype=np.uint8).reshape(india.shape)
    assert np.array_equal(grid.astype(bool), india)


# ------------------------------------------------------------------ the tiles

def test_every_india_square_is_in_exactly_one_tile(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    squares = published_tiles(store, "20261112T00Z")
    keys = [(r["lat"], r["lon"]) for r in squares]
    assert len(keys) == len(set(keys)) == int(india.sum())

    expected = {(round(cfg.INDIA_LATS[i], 2), round(cfg.INDIA_LONS[j], 2))
                for i in range(N_LAT) for j in range(N_LON) if india[i, j]}
    assert set(keys) == expected


def test_a_square_is_in_the_tile_the_formula_names(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    for pathname, data in store.data.items():
        if "/tiles/" not in pathname:
            continue
        tile = json.loads(data.decode())
        name = Path(pathname).stem
        assert tile["tile"] == name
        for record in tile["squares"]:
            # longhand, with no help from publish.py
            lat_south = int(record["lat"] // 4 * 4)
            lon_west = int(record["lon"] // 4 * 4)
            assert name == f"{lat_south}N_{lon_west}E"
            assert tile["lat_south"] == lat_south
            assert tile["lon_west"] == lon_west


def test_tile_id_naming_including_the_southern_and_western_cases():
    assert tile_id(20.25, 72.75) == "20N_72E"
    assert tile_id(23.75, 75.75) == "20N_72E"
    assert tile_id(24.00, 76.00) == "24N_76E"
    assert tile_id(6.00, 68.00) == "4N_68E"
    assert tile_id(-1.5, -2.5) == "4S_4W"


def test_the_four_identities_hold_in_the_published_tiles(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    for record in published_tiles(store, "20261112T00Z"):
        for counts, dots in zip(record["c"], record["d"]):
            assert sum(dots) == 51
            assert counts[0] == dots[1] + dots[2] + dots[3]
            assert counts[1] == dots[2] + dots[3]
            assert counts[2] == dots[3]


def test_the_member_integers_rebuild_the_counts_and_the_dots(run_root, india):
    write_run(run_root, "20261112T00Z", india)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    for record in published_tiles(store, "20261112T00Z"):
        for counts, dots, codes in zip(record["c"], record["d"], record["m"]):
            assert len(codes) == 51
            totals = [code * MEMBER_STEP for code in codes]
            assert [sum(1 for t in totals if t >= T) for T in (1.0, 10.0, 50.0)] \
                == counts
            assert [
                sum(1 for t in totals if t < 1.0),
                sum(1 for t in totals if 1.0 <= t < 10.0),
                sum(1 for t in totals if 10.0 <= t < 50.0),
                sum(1 for t in totals if t >= 50.0),
            ] == dots


def test_the_member_totals_survive_the_round_trip_exactly(run_root, india):
    totals = totals_for(india, seed=11)
    write_run(run_root, "20261112T00Z", india, totals=totals)
    store = FakeStore()
    publish.publish(store, "20261112T00Z", mark=False)

    codes = member_codes(totals)
    back = (codes.astype(np.float64) * MEMBER_STEP).astype(np.float32)
    assert np.array_equal(back, totals)


# ------------------------------------------------------------------ the integers

def test_member_codes_round_down():
    values = np.array([[[[0.0, 0.9375, 1.0, 9.9375, 10.0, 49.9375, 50.0]]]],
                      dtype=np.float32)
    codes = member_codes(values)
    assert list(codes.ravel()) == [0, 15, 16, 159, 160, 799, 800]
    assert list(display_mm(codes).ravel()) == [0, 0, 1, 9, 10, 49, 50]


def test_rounding_down_never_promotes_a_member_over_a_threshold():
    # Values that are NOT multiples of the step, to show the direction.
    values = np.array([[[[9.99, 0.99, 49.999, 10.001]]]], dtype=np.float32)
    shown = display_mm(member_codes(values))
    assert list(shown.ravel()) == [9, 0, 49, 10]


def test_every_whole_millimetre_agrees_with_every_threshold():
    codes = np.arange(0, 1601, dtype=np.uint16).reshape(1, 1, 1, -1)
    totals = codes.astype(np.float64) * MEMBER_STEP
    shown = display_mm(codes)
    for threshold in (1.0, 10.0, 50.0):
        assert np.array_equal(shown >= threshold, totals >= threshold)


def test_a_negative_member_total_fails_the_publish():
    values = np.array([[[[-0.125, 1.0]]]], dtype=np.float32)
    with pytest.raises(PublishError, match="negative"):
        member_codes(values)


def test_a_member_total_too_big_for_sixteen_bits_fails_the_publish():
    values = np.array([[[[4096.0]]]], dtype=np.float32)
    with pytest.raises(PublishError, match="16 bits"):
        member_codes(values)


def test_integers_that_disagree_with_the_counts_fail_the_publish(india):
    totals = totals_for(india)
    counts = counts_from(totals)
    dots = dots_from(totals)
    codes = member_codes(totals)
    publish.check_codes(codes, counts, dots)          # the honest case

    broken = counts.copy()
    broken[1, 0, 1, 1] = (broken[1, 0, 1, 1] + 1) % 52
    with pytest.raises(PublishError, match="rebuild the counts"):
        publish.check_codes(codes, broken, dots)

    broken_dots = dots.copy()
    broken_dots[0, 0, 1, 1] = (broken_dots[0, 0, 1, 1] + 1) % 52
    with pytest.raises(PublishError, match="rebuild the dots"):
        publish.check_codes(codes, counts, broken_dots)


def test_a_tile_record_whose_counts_and_dots_disagree_fails():
    record = {"lat": 20.25, "lon": 72.75,
              "c": [[2, 1, 0]], "d": [[49, 1, 1, 0]],
              "m": [[0] * 51]}
    with pytest.raises(PublishError):
        publish.check_record(record)


# ------------------------------------------------------------------ the local state

def test_a_dry_run_does_not_mark_the_local_run_published(run_root, india):
    out = write_run(run_root, "20261112T00Z", india)
    publish.publish(FakeStore(), "20261112T00Z", mark=False)
    assert json.loads((out / MANIFEST).read_text())["published"] is False


def test_a_real_publish_marks_the_local_run_published(run_root, india):
    out = write_run(run_root, "20261112T00Z", india)
    publish.publish(FakeStore(), "20261112T00Z", mark=True)
    manifest = json.loads((out / MANIFEST).read_text())
    assert manifest["published"] is True
    assert "published_at_ist" in manifest
    assert publish.newest_publishable()[0] is None


def test_the_payload_is_written_where_it_can_be_compared(run_root, india,
                                                         tmp_path):
    write_run(run_root, "20261112T00Z", india)
    work = tmp_path / "publish" / "20261112T00Z"
    store = FakeStore()
    publish.publish(store, "20261112T00Z", work_dir=work, mark=False)

    for pathname, data in store.data.items():
        assert (work / pathname).read_bytes() == data


# ------------------------------------------------------------------ the real run

real = pytest.mark.skipif(
    not (cfg.DATA / "live" / REAL_RUN / "squares.npz").exists(),
    reason="data/ is never committed, so the real run is not always here")


@real
def test_the_real_runs_display_agrees_with_its_counts_and_dots():
    """SPEC 8.4, on every member of every India square of a real run."""
    with np.load(cfg.DATA / "live" / REAL_RUN / "squares.npz") as f:
        totals = f["member_totals"]
        counts = f["counts"]
        dots = f["dots"]
        mask = f["india"]

    codes = member_codes(totals)
    publish.check_codes(codes, counts, dots)

    shown = display_mm(codes)[:, :, mask]
    true = totals[:, :, mask]
    for threshold in (1.0, 10.0, 50.0):
        assert np.array_equal(shown >= threshold, true >= threshold)
    assert int(shown.max()) == int(np.floor(true.max()))


@real
def test_the_real_run_has_no_negative_member_total():
    with np.load(cfg.DATA / "live" / REAL_RUN / "squares.npz") as f:
        totals = f["member_totals"]
    assert float(totals.min()) == 0.0
