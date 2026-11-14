"""SPEC 11.10: `api/place` and `api/health` against the published tiles.

No network and no token. A run is built on the small grid of
`test_publish.py`, published into a temporary directory through `FakeStore`,
and served by a plain `http.server` on 127.0.0.1. `STORE_BASE_URL` points the
functions at that server, which is the override of SPEC 11.5.

The functions are driven by `node` directly. They export the Web standard
`{ fetch(request) }`, so six lines of harness can import one and call it with
a `Request`: no Vercel runtime, no emulator, no deploy. The harness is written
into the test's own temporary directory rather than committed, because it is
part of this test and nothing else.

What is actually checked is the thing that matters for the page: **every
number `api/place` returns is a number that was published**. The counts, the
dots and the 51 member integers are compared against the tile JSON in the
store, square by square and day by day, and the whole millimetres against
`m // 16` computed here.
"""
from __future__ import annotations

import datetime as dt
import gzip
import http.server
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

from pipeline import config as cfg
from pipeline import publish
from pipeline.publish import FakeStore

from test_publish import N_DAYS, small_grid, write_run

ROOT = Path(__file__).resolve().parent.parent
RUN = "20261112T00Z"
STEPS_PER_MM = 16

node = shutil.which("node")
needs_node = pytest.mark.skipif(
    node is None,
    reason="node is not on PATH, so the api/ functions cannot be driven")

HARNESS = """
// Drive one Vercel function: import it and call its fetch export.
const [file, url] = process.argv.slice(2);
const mod = await import(file);
const response = await mod.default.fetch(new Request(url));
const body = await response.text();
process.stdout.write(JSON.stringify({
  status: response.status,
  cacheControl: response.headers.get('cache-control'),
  body,
}));
"""

# SPEC 11.24. The same trick one level down: call a named export with
# arguments instead of driving a whole request. This is how the sentence
# rule, the IST labels, the palette and the snap are tested as functions
# rather than inferred from a response.
EXPORT_HARNESS = """
// The arguments arrive in a file, not on the command line: Windows caps a
// command line at about 32,000 characters and the town list alone is 15,000
// (SPEC 11.28), so passing it as an argument failed outright.
import { readFileSync } from 'node:fs';
const [file, name, argsFile] = process.argv.slice(2);
const mod = await import(file);
const fn = mod[name];
if (typeof fn !== 'function') {
  throw new Error(`${file} exports no function called ${name}`);
}
const calls = JSON.parse(readFileSync(argsFile, 'utf8'));
process.stdout.write(JSON.stringify(calls.map((call) => fn(...call))));
"""


# ------------------------------------------------------------------ the store

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):          # noqa: D102 - keep pytest readable
        pass


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A real HTTP server over the exact bytes a publish would upload."""
    india = small_grid(monkeypatch)
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setattr(publish, "LIVE", live)
    monkeypatch.setattr(publish, "run_dir", lambda run_id: live / run_id)
    write_run(live, RUN, india)

    served = tmp_path / "store"
    fake = FakeStore()
    result = publish.publish(fake, RUN, work_dir=served, mark=False)
    assert result["published"] is True

    handler = type("Rooted", (Quiet,),
                   {"directory": str(served),
                    "__init__": lambda self, *a, **kw: Quiet.__init__(
                        self, *a, directory=str(served), **kw)})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield {"base": base, "dir": served, "india": india,
               "manifest": json.loads((served / "manifest.json").read_text())}
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def harness(tmp_path):
    path = tmp_path / "harness.mjs"
    path.write_text(HARNESS, encoding="utf-8")
    return path


@pytest.fixture()
def exports(tmp_path):
    """Call a named export of any .mjs file in the project under node."""
    path = tmp_path / "exports.mjs"
    path.write_text(EXPORT_HARNESS, encoding="utf-8")

    args = tmp_path / "args.json"

    def run(module: Path, name: str, calls: list[list]) -> list:
        args.write_text(json.dumps(calls), encoding="utf-8")
        done = subprocess.run(
            [node, str(path), Path(module).as_uri(), name, str(args)],
            capture_output=True, text=True, encoding="utf-8", check=False)
        assert done.returncode == 0, f"node failed: {done.stderr}"
        return json.loads(done.stdout)

    return run


def call(harness: Path, function: str, query: str, base: str,
         env: dict | None = None) -> dict:
    """Run one api/ function under node and return status and parsed body."""
    url = f"https://forecast.example/api/{function}{query}"
    environment = dict(os.environ)
    environment["STORE_BASE_URL"] = base
    environment.update(env or {})
    done = subprocess.run(
        [node, str(harness), (ROOT / "api" / f"{function}.mjs").as_uri(), url],
        capture_output=True, text=True, encoding="utf-8", check=False, env=environment)
    assert done.returncode == 0, f"node failed: {done.stderr}"
    reply = json.loads(done.stdout)
    reply["json"] = json.loads(reply["body"])
    return reply


def tile_record(store: dict, lat: float, lon: float) -> dict:
    name = publish.tile_id(lat, lon)
    tile = json.loads(
        (store["dir"] / "runs" / RUN / "tiles" / f"{name}.json").read_text())
    for record in tile["squares"]:
        if abs(record["lat"] - lat) < 1e-9 and abs(record["lon"] - lon) < 1e-9:
            return record
    raise AssertionError(f"{lat} N {lon} E is not in tile {name}")


def india_squares(store: dict) -> list[tuple[float, float]]:
    from pipeline import config as cfg
    india = store["india"]
    return [(cfg.INDIA_LATS[i], cfg.INDIA_LONS[j])
            for i in range(india.shape[0]) for j in range(india.shape[1])
            if india[i, j]]


# ------------------------------------------------------------------ api/place

@needs_node
def test_every_india_square_matches_its_published_tile(store, harness):
    squares = india_squares(store)
    assert len(squares) == 30, "the small grid has 30 India squares"

    for lat, lon in squares:
        reply = call(harness, "place", f"?lat={lat}&lon={lon}", store["base"])
        assert reply["status"] == 200, reply["body"]
        answer = reply["json"]
        record = tile_record(store, lat, lon)

        assert answer["square"]["lat"] == pytest.approx(lat)
        assert answer["square"]["lon"] == pytest.approx(lon)
        assert answer["square"]["moved"] is None
        assert answer["run"]["run_id"] == RUN
        assert len(answer["days"]) == N_DAYS

        for day, published_c, published_d, published_m in zip(
                answer["days"], record["c"], record["d"], record["m"]):
            assert [day["counts"]["ge1"], day["counts"]["ge10"],
                    day["counts"]["ge50"]] == published_c
            assert day["dots"] == published_d
            assert [entry["count"] for entry in day["counts_by_threshold"]] \
                == published_c
            # The published integers, as whole millimetres rounded down.
            assert day["members_mm"] == [code // STEPS_PER_MM
                                         for code in published_m]
            assert len(day["members_mm"]) == 51


@needs_node
def test_the_whole_millimetres_never_disagree_with_the_counts(store, harness):
    """SPEC 8.4 arriving at the page: the number shown and the count agree."""
    for lat, lon in india_squares(store):
        answer = call(harness, "place", f"?lat={lat}&lon={lon}",
                      store["base"])["json"]
        for day in answer["days"]:
            shown = day["members_mm"]
            assert sum(1 for mm in shown if mm >= 1) == day["counts"]["ge1"]
            assert sum(1 for mm in shown if mm >= 10) == day["counts"]["ge10"]
            assert sum(1 for mm in shown if mm >= 50) == day["counts"]["ge50"]
            assert sum(day["dots"]) == 51


@needs_node
def test_a_request_half_a_square_off_snaps_and_says_so(store, harness):
    from pipeline import config as cfg
    lat, lon = india_squares(store)[0]
    reply = call(harness, "place", f"?lat={lat - 0.1}&lon={lon + 0.1}",
                 store["base"])

    answer = reply["json"]
    assert reply["status"] == 200
    assert answer["square"]["lat"] == pytest.approx(lat)
    assert answer["square"]["lon"] == pytest.approx(lon)
    assert answer["square"]["asked"]["lat"] == pytest.approx(lat - 0.1)
    assert answer["square"]["moved"] is None
    # i and j are consistent with the square that came back.
    i, j = answer["square"]["i"], answer["square"]["j"]
    assert cfg.LAT_MAX - cfg.GRID_STEP * i == pytest.approx(lat)
    assert cfg.LON_MIN + cfg.GRID_STEP * j == pytest.approx(lon)
    assert answer["square"]["tile"] == publish.tile_id(lat, lon)


@needs_node
def test_a_sea_square_moves_one_square_and_names_both(store, harness):
    """SPEC 11.7: the same rule as a coastal city in the list."""
    from pipeline import config as cfg
    india = store["india"]
    # Row 0 of the small grid is outside the mask; row 1 is inside.
    sea_lat, sea_lon = cfg.INDIA_LATS[0], cfg.INDIA_LONS[2]
    assert not india[0, 2] and india[1, 2]

    reply = call(harness, "place", f"?lat={sea_lat}&lon={sea_lon}",
                 store["base"])
    answer = reply["json"]

    assert reply["status"] == 200
    assert answer["square"]["lat"] == pytest.approx(cfg.INDIA_LATS[1])
    assert answer["square"]["moved"]["from"]["lat"] == pytest.approx(sea_lat)
    assert answer["square"]["moved"]["to"]["lat"] == pytest.approx(
        cfg.INDIA_LATS[1])
    assert answer["square"]["moved"]["squares"] == 1
    # And the numbers are that neighbour's published numbers, not the sea's.
    record = tile_record(store, cfg.INDIA_LATS[1], sea_lon)
    assert [answer["days"][0]["counts"]["ge1"],
            answer["days"][0]["counts"]["ge10"],
            answer["days"][0]["counts"]["ge50"]] == record["c"][0]


@needs_node
def test_a_square_with_no_india_within_one_square_is_outside_the_area(store,
                                                                     harness):
    # 21.00 N 72.50 E is inside the India box and inside the tile this run
    # publishes, but neither it nor any of its eight neighbours is one of the
    # squares in that tile, so there is nothing honest to show.
    lat, lon = 21.0, 72.5
    assert publish.tile_id(lat, lon) == store["manifest"]["tiles"][0]
    assert all(abs(known_lat - lat) > 0.3 or abs(known_lon - lon) > 0.3
               for known_lat, known_lon in india_squares(store))

    reply = call(harness, "place", f"?lat={lat}&lon={lon}", store["base"])

    assert reply["status"] == 404
    assert reply["json"]["error"] == "outside the forecast area"
    assert "sea or outside India" in reply["json"]["detail"]


@needs_node
@pytest.mark.parametrize("query", [
    "",
    "?lat=20",
    "?lon=74",
    "?lat=abc&lon=74",
    "?lat=50&lon=74",          # north of 38
    "?lat=20&lon=120",         # east of 98
    "?lat=&lon=",
])
def test_a_request_that_cannot_be_answered_is_a_400(store, harness, query):
    reply = call(harness, "place", query, store["base"])
    assert reply["status"] == 400
    assert reply["json"]["ok"] is False
    assert reply["json"]["error"]


@needs_node
def test_an_unreachable_store_is_a_503(store, harness):
    reply = call(harness, "place", "?lat=20&lon=74", store["base"],
                 env={"STORE_BASE_URL": "http://127.0.0.1:1"})
    assert reply["status"] == 503
    assert "could not be read" in reply["json"]["error"]
def test_the_committed_store_config_is_the_fallback():
    """SPEC 11.5: one committed source of truth, and no credential in it."""
    config = json.loads((ROOT / "config" / "store.json").read_text())
    assert config["base_url"].startswith("https://")
    assert config["base_url"].endswith(".public.blob.vercel-storage.com")
    assert not config["base_url"].endswith("/")

    text = json.dumps(config).lower()
    for forbidden in ("token", "secret", "password", "_rw_"):
        assert forbidden not in text, f"{forbidden} has no business in here"

    # The environment override is read before the file, in both functions.
    for name in ("health", "place"):
        source = (ROOT / "api" / f"{name}.mjs").read_text(encoding="utf-8")
        assert "process.env.STORE_BASE_URL" in source
        assert source.index("process.env.STORE_BASE_URL") < \
            source.index("config/store.json")


@needs_node
def test_the_answer_is_cacheable_for_a_minute(store, harness):
    reply = call(harness, "place", "?lat=20&lon=74", store["base"])
    assert reply["cacheControl"] == "public, max-age=60"


# ------------------------------------------------------------------ api/health

@needs_node
def test_health_reports_the_manifest_unchanged(store, harness):
    reply = call(harness, "health", "", store["base"])
    answer = reply["json"]
    manifest = store["manifest"]

    assert reply["status"] == 200
    assert reply["cacheControl"] == "public, max-age=60"
    assert answer["ok"] is True
    assert answer["store"] == "reachable"
    for field in ("run_id", "run_time_utc", "run_time_ist",
                  "publish_time_ist", "india_squares", "member_display"):
        assert answer[field] == manifest[field], field
    assert answer["thresholds_mm"] == manifest["thresholds_mm"]
    assert [day["label"] for day in answer["days"]] == \
        [day["label"] for day in manifest["days"]]
    assert answer["stale_after_hours"] == 36


@needs_node
def test_health_is_503_when_the_store_cannot_be_read(store, harness):
    reply = call(harness, "health", "", store["base"],
                 env={"STORE_BASE_URL": "http://127.0.0.1:1"})
    assert reply["status"] == 503
    assert reply["json"]["ok"] is False
    assert "unreachable" in reply["json"]["store"]


@needs_node
def test_stale_flips_at_thirty_six_hours_and_not_before(store, harness,
                                                        tmp_path):
    """The run time is moved, nothing else, and the flag follows it."""
    import datetime as dt

    served = store["dir"]
    original = json.loads((served / "manifest.json").read_text())

    def health_with_age(hours: float) -> dict:
        when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
        changed = dict(original)
        changed["run_time_utc"] = when.isoformat()
        (served / "manifest.json").write_text(json.dumps(changed))
        return call(harness, "health", "", store["base"])["json"]

    try:
        young = health_with_age(35.5)
        assert young["stale"] is False
        assert young["age_hours"] == pytest.approx(35.5, abs=0.2)

        old = health_with_age(36.5)
        assert old["stale"] is True
        assert old["age_hours"] == pytest.approx(36.5, abs=0.2)

        # And api/place says the same thing about the same manifest.
        lat, lon = india_squares(store)[0]
        place = call(harness, "place", f"?lat={lat}&lon={lon}",
                     store["base"])["json"]
        assert place["run"]["stale"] is True
    finally:
        (served / "manifest.json").write_text(json.dumps(original))


# --------------------------------------------------- the published bytes agree

@needs_node
def test_the_counts_files_agree_with_what_the_api_returns(store, harness):
    """The map of G3 will read these bytes; the page reads the API. One run."""
    from pipeline import config as cfg
    india = store["india"]
    n_lon = india.shape[1]
    lat, lon = india_squares(store)[7]
    # The counts files are indexed against the grid they were written for,
    # which here is the small test grid, not the real India box. api/place
    # reports i and j against the real box, and that is right in production;
    # this test is about the bytes, so it uses the grid that wrote them.
    i = cfg.INDIA_LATS.index(lat)
    j = cfg.INDIA_LONS.index(lon)

    answer = call(harness, "place", f"?lat={lat}&lon={lon}",
                  store["base"])["json"]

    for k, threshold in enumerate((1.0, 10.0, 50.0)):
        for day in range(N_DAYS):
            name = publish.counts_file_name(threshold, day + 1)
            data = (store["dir"] / "runs" / RUN / "counts" / name).read_bytes()
            byte = np.frombuffer(data, dtype=np.uint8)[i * n_lon + j]
            key = ("ge1", "ge10", "ge50")[k]
            assert int(byte) == answer["days"][day]["counts"][key]


# ------------------------------------------- SPEC 11.23: where the store is

@needs_node
def test_health_says_where_the_map_should_read_its_bytes(store, harness):
    """SPEC 11.16: the page learns the store from its origin, not from a build."""
    reply = call(harness, "health", "", store["base"])
    block = reply["json"]["source"]
    manifest = store["manifest"]

    assert block["base_url"] == store["base"], "the override of SPEC 11.5"
    assert block["paths"] == manifest["paths"]
    assert block["counts_files"] == manifest["counts_files"]
    assert len(block["counts_files"]) == 15, "3 thresholds x 5 days"
    assert block["grid"] == manifest["grid"]
    # The numbers the map indexes with come from the run, not from the page.
    for key in ("n_lat", "n_lon", "not_india", "grid_step_degrees"):
        assert key in block["grid"], key
    assert block["grid"]["not_india"] == 255


@needs_node
def test_the_store_block_carries_no_credential(store, harness):
    block = call(harness, "health", "", store["base"])["json"]["source"]
    text = json.dumps(block).lower()
    for secret in ("token", "secret", "password", "readwrite"):
        assert secret not in text, f"{secret} appears in the store block"


# -------------------------------------------- SPEC 11.23: the short IST label

@needs_node
def test_short_ist_appears_inside_the_manifests_own_label(store, harness):
    """The label the manifest publishes starts with the time and this date."""
    lat, lon = india_squares(store)[0]
    for function, query in (("health", ""), ("place", f"?lat={lat}&lon={lon}")):
        reply = call(harness, function, query, store["base"])
        assert reply["status"] == 200, (function, reply["body"])
        answer = reply["json"]
        assert len(answer["days"]) == N_DAYS
        for day, published in zip(answer["days"], store["manifest"]["days"]):
            assert day["short_ist"], function
            assert day["short_ist"] in published["label"], (
                function, day["short_ist"], published["label"])
    # And it is the real date of the real run, not just any substring.
    assert [day["short_ist"] for day in answer["days"]] == [
        "Fri 13 Nov", "Sat 14 Nov", "Sun 15 Nov", "Mon 16 Nov", "Tue 17 Nov"]


@needs_node
@pytest.mark.parametrize(("from_ist", "expected"), [
    ("2026-11-13T05:30:00+05:30", "Fri 13 Nov"),
    ("2026-01-01T05:30:00+05:30", "Thu 1 Jan"),
    ("2026-12-31T05:30:00+05:30", "Thu 31 Dec"),
    # The same instant written in UTC must still give the IST date.
    ("2026-11-13T00:00:00+00:00", "Fri 13 Nov"),
    ("2026-11-12T19:00:00+00:00", "Fri 13 Nov"),
    ("2026-11-12T18:29:00+00:00", "Thu 12 Nov"),
    ("not a date", None),
])
def test_the_ist_label_needs_no_time_zone_database(exports, from_ist, expected):
    for module in ("health", "place"):
        got = exports(ROOT / "api" / f"{module}.mjs", "shortIst",
                      [[from_ist]])[0]
        assert got == expected, (module, from_ist, got)


# --------------------------------------- SPEC 11.20: one sentence for one day

FORBIDDEN = ("dry", "wet", "heavy", "likely", "unlikely", "chance",
             "probability", "probable", "expect", "risk", "warn", "%",
             "percent", "certain", "safe", "danger", "storm", "flood")


def expected_sentence(counts, thresholds, members) -> str:
    """The rule of SPEC 11.20, written out again rather than imported."""
    def mm(threshold):
        whole = float(threshold).is_integer()
        return f"{int(threshold) if whole else threshold} mm"

    def verb(count):
        return "reaches" if count == 1 else "reach"

    if counts[0] == 0:
        return f"0 of {members} model runs reach {mm(thresholds[0])}."
    out = (f"{counts[0]} of {members} model runs "
           f"{verb(counts[0])} {mm(thresholds[0])}")
    for count, threshold in zip(counts[1:], thresholds[1:]):
        if count == 0:
            out += f", none reach {mm(threshold)}"
            break
        out += f", {count} {verb(count)} {mm(threshold)}"
    return out + "."


@needs_node
@pytest.mark.parametrize(("counts", "expected"), [
    ([0, 0, 0], "0 of 51 model runs reach 1 mm."),
    ([18, 0, 0], "18 of 51 model runs reach 1 mm, none reach 10 mm."),
    ([40, 12, 0],
     "40 of 51 model runs reach 1 mm, 12 reach 10 mm, none reach 50 mm."),
    ([51, 48, 3],
     "51 of 51 model runs reach 1 mm, 48 reach 10 mm, 3 reach 50 mm."),
    ([1, 0, 0], "1 of 51 model runs reaches 1 mm, none reach 10 mm."),
    ([1, 1, 1],
     "1 of 51 model runs reaches 1 mm, 1 reaches 10 mm, 1 reaches 50 mm."),
    ([51, 1, 0],
     "51 of 51 model runs reach 1 mm, 1 reaches 10 mm, none reach 50 mm."),
])
def test_the_day_sentence_is_exactly_the_rule(exports, counts, expected):
    got = exports(ROOT / "api" / "place.mjs", "daySentence",
                  [[counts, [1, 10, 50], 51]])[0]
    assert got == expected
    assert got == expected_sentence(counts, [1, 10, 50], 51)


@needs_node
def test_the_day_sentence_never_says_dry_or_likely(exports):
    """SPEC 11.20: no judgement words, for any counts the data can hold."""
    calls = [[[c1, c10, c50], [1, 10, 50], 51]
             for c1 in range(0, 52, 3)
             for c10 in range(0, c1 + 1, 7)
             for c50 in range(0, c10 + 1, 11)]
    assert len(calls) > 100, "a thin sweep proves nothing"
    said = exports(ROOT / "api" / "place.mjs", "daySentence", calls)
    for sentence in said:
        low = sentence.lower()
        for word in FORBIDDEN:
            assert word not in low, f"{word} appears in: {sentence}"
        assert sentence.endswith("."), sentence
        assert "model runs" in sentence


@needs_node
def test_the_day_sentence_matches_the_counts_of_every_square(store, harness):
    manifest = store["manifest"]
    thresholds = manifest["thresholds_mm"]
    members = manifest["members"]
    for lat, lon in india_squares(store):
        answer = call(harness, "place", f"?lat={lat}&lon={lon}",
                      store["base"])["json"]
        record = tile_record(store, lat, lon)
        for day in range(N_DAYS):
            counts = record["c"][day]
            assert answer["days"][day]["sentence"] == expected_sentence(
                counts, thresholds, members), (lat, lon, day, counts)
def test_the_published_counts_are_monotone(store):
    """SPEC 4.2, which is what lets the sentence stop at the first zero."""
    for lat, lon in india_squares(store):
        record = tile_record(store, lat, lon)
        for day, counts in enumerate(record["c"]):
            assert counts[0] >= counts[1] >= counts[2], (lat, lon, day, counts)


# ------------------------------- SPEC 11.24: what the map reads, all fifteen

@needs_node
def test_the_map_byte_matches_the_api_for_every_square_and_combination(
        store, harness):
    """The map colours from these bytes and the panel prints the API's number.

    Part one of SPEC 11 checked one square and one combination. The map reads
    all fifteen files, so all fifteen are checked, for every India square.
    """
    from pipeline import config as cfg
    n_lon = store["india"].shape[1]
    counts_dir = store["dir"] / "runs" / RUN / "counts"
    loaded = {
        (threshold, day): np.frombuffer(
            (counts_dir / publish.counts_file_name(threshold, day)).read_bytes(),
            dtype=np.uint8)
        for threshold in (1.0, 10.0, 50.0) for day in range(1, N_DAYS + 1)
    }

    squares = india_squares(store)
    assert len(squares) == 30
    checked = 0
    for lat, lon in squares:
        answer = call(harness, "place", f"?lat={lat}&lon={lon}",
                      store["base"])["json"]
        # The published bytes are indexed against the grid that wrote them,
        # which here is the small test grid; api/place reports i and j against
        # the real India box, which is right in production.
        i = cfg.INDIA_LATS.index(lat)
        j = cfg.INDIA_LONS.index(lon)
        for k, threshold in enumerate((1.0, 10.0, 50.0)):
            for day in range(1, N_DAYS + 1):
                byte = int(loaded[(threshold, day)][i * n_lon + j])
                assert byte != 255, "an India square is never 255"
                answered = answer["days"][day - 1]["counts_by_threshold"][k]
                assert byte == answered["count"], (lat, lon, threshold, day)
                checked += 1
    assert checked == 30 * 15, checked


def test_the_mask_is_identical_in_every_counts_file(store):
    """SPEC 11.16: one counts file gives the mask, so india.u8 is not fetched."""
    run_dir = store["dir"] / "runs" / RUN
    mask = np.frombuffer((run_dir / "india.u8").read_bytes(), dtype=np.uint8)
    expected = (mask == 1)
    assert expected.sum() == 30

    for threshold in (1.0, 10.0, 50.0):
        for day in range(1, N_DAYS + 1):
            name = publish.counts_file_name(threshold, day)
            data = np.frombuffer((run_dir / "counts" / name).read_bytes(),
                                 dtype=np.uint8)
            assert data.shape == mask.shape
            assert ((data != 255) == expected).all(), name
            assert (data[expected] <= 51).all(), name


# ------------------------------------- SPEC 11.17: the palette and the legend

PALETTE = ROOT / "web" / "src" / "palette.js"
SNAP = ROOT / "web" / "src" / "snap.js"

# SPEC 11.17, written out again here rather than imported, so the test holds
# the published table and not whatever the file happens to say.
PUBLISHED_CLASSES = [
    (0, 0, "#eceff1", "0"),
    (1, 10, "#c7e9b4", "1-10"),
    (11, 20, "#7fcdbb", "11-20"),
    (21, 30, "#41b6c4", "21-30"),
    (31, 40, "#1d91c0", "31-40"),
    (41, 50, "#225ea8", "41-50"),
    (51, 51, "#0c2c84", "51"),
]


@needs_node
def test_every_count_falls_in_exactly_one_published_class(exports):
    """0 to 51, no gap and no overlap, and the boundaries of SPEC 11.17."""
    colours = exports(PALETTE, "colourOf", [[c] for c in range(52)])
    labels = exports(PALETTE, "labelOf", [[c] for c in range(52)])

    for count in range(52):
        wanted = [row for row in PUBLISHED_CLASSES
                  if row[0] <= count <= row[1]]
        assert len(wanted) == 1, f"{count} is in {len(wanted)} classes"
        assert colours[count] == wanted[0][2], count
        assert labels[count] == wanted[0][3], count

    # Contiguous and complete: every class is used and they run end to end.
    assert len(set(colours)) == len(PUBLISHED_CLASSES)
    assert colours[0] != colours[1], "0 has its own class"
    assert colours[51] != colours[50], "51 has its own class"


@needs_node
def test_nothing_that_is_not_a_count_gets_a_colour(exports):
    """255 is "outside India" (SPEC 8.4) and must never be painted."""
    # No NaN here: JSON cannot carry it, so the harness could not pass one.
    # classOf rejects it anyway, because Number.isInteger(NaN) is false.
    cases = [[255], [52], [-1], [0.5], ["7"], [None], [True]]
    for colour in exports(PALETTE, "colourOf", cases):
        assert colour is None, colour
    for label in exports(PALETTE, "labelOf", cases):
        assert label is None, label


@needs_node
def test_the_step_expression_paints_what_the_palette_says(exports):
    """The map's fill expression, evaluated here the way MapLibre would.

    A `step` expression is a base colour and then (stop, colour) pairs: the
    colour of the last stop at or below the value. If that ever disagreed with
    classOf, the map and the panel would describe the same square differently.
    """
    expression = exports(PALETTE, "fillExpression", [["ge1_d1"]])[0]
    assert expression[0] == "step"
    assert expression[1] == ["get", "ge1_d1"]

    base = expression[2]
    stops = [(expression[k], expression[k + 1])
             for k in range(3, len(expression), 2)]
    assert len(stops) == len(PUBLISHED_CLASSES) - 1

    colours = exports(PALETTE, "colourOf", [[c] for c in range(52)])
    for count in range(52):
        painted = base
        for stop, colour in stops:
            if count >= stop:
                painted = colour
        assert painted == colours[count], count


@needs_node
def test_the_count_key_is_the_one_the_map_reads(exports):
    keys = exports(PALETTE, "countKey", [[1, 1], [10, 3], [50, 5]])
    assert keys == ["ge1_d1", "ge10_d3", "ge50_d5"]


@needs_node
def test_the_not_a_probability_sentence_is_the_approved_wording(exports):
    """SPEC 11.21, amended by 11.28.

    It used to take the count and read "1 of 51 model runs, which is not a
    calibrated probability." — a fragment with no verb, and one that reads as
    a claim about the number next to it. It is one sentence now, the same
    whatever the count is, so there is nothing for it to disagree with.
    """
    said = exports(PALETTE, "notProbability", [[], [40]])
    # SPEC 11.38 amends it once more: "model runs" was one of four names
    # this page had for the 51, and the page has one now.
    assert said[0] == ("These are counts out of 51 runs, not a "
                       "calibrated probability.")
    assert said[1] == said[0], "the count must not change the sentence"
    # It is a sentence: a verb, and nothing to complete.
    assert said[0].startswith("These are ") and said[0].endswith(".")
    # This is the one sentence on the site that is *allowed* to say
    # "probability", because its whole job is to say these numbers are not
    # one. The forbidden-word list of the day sentence does not apply to it.
    for sentence in said:
        low = sentence.lower()
        assert "%" not in sentence and "percent" not in low
        assert "chance of rain" not in low, "the sentence this replaced"
        assert low.count("probability") == 1
        assert "not a calibrated probability" in low


# ------------------------------ SPEC 11.19: the page snaps before it asks

@needs_node
def test_the_page_and_the_function_agree_on_every_square(exports):
    """The reason it is safe for the page to round a location itself.

    If these two ever named different squares, the page would show one
    square's numbers under another square's coordinates.
    """
    points = []
    lat = 6.0
    while lat <= 38.0001:
        lon = 68.0
        while lon <= 98.0001:
            points.append([round(lat, 4), round(lon, 4)])
            lon += 1.3
        lat += 1.1
    # And a sweep of awkward offsets around one square's edges.
    for d in (-0.1249, -0.125, -0.1251, -0.0001, 0.0, 0.0001, 0.1249,
              0.125, 0.1251):
        points.append([round(28.5 + d, 6), round(77.25 + d, 6)])
    assert len(points) > 300

    page = exports(SNAP, "snap", [[lat, lon] for lat, lon in points])
    api = exports(ROOT / "api" / "place.mjs", "snapSquare",
                  [[lat, lon] for lat, lon in points])
    for (lat, lon), mine, theirs in zip(points, page, api):
        assert mine == theirs, (lat, lon, mine, theirs)


@needs_node
def test_snapping_lands_on_the_grid_and_reports_its_own_centre(exports):
    got = exports(SNAP, "snap", [[28.5, 77.25], [28.6, 77.3], [38.0, 68.0]])
    assert got[0] == {"i": 38, "j": 37, "lat": 28.5, "lon": 77.25}
    assert got[1] == got[0], "a tenth of a degree is the same square"
    assert got[2] == {"i": 0, "j": 0, "lat": 38.0, "lon": 68.0}


@needs_node
def test_the_tile_name_and_byte_index_match_the_published_layout(exports):
    """SPEC 8.4: tiles are named after their south-west corner, row major."""
    tiles = exports(SNAP, "tileName",
                    [[34.25, 73.5], [28.5, 77.25], [8.5, 77.0]])
    assert tiles == ["32N_72E", "28N_76E", "8N_76E"]
    index = exports(SNAP, "byteIndex", [[15, 22, 121]])[0]
    assert index == 15 * 121 + 22


@needs_node
@pytest.mark.parametrize(("typed", "expected"), [
    ("28.5, 77.25", {"lat": 28.5, "lon": 77.25}),
    ("28.5 77.25", {"lat": 28.5, "lon": 77.25}),
    ("  -8.5,77  ", {"lat": -8.5, "lon": 77.0}),
    ("Delhi", None),
    ("28.5", None),
    ("28.5, 77.25, 3", None),
    ("", None),
])
def test_two_typed_numbers_are_a_place_and_anything_else_is_a_name(
        exports, typed, expected):
    assert exports(SNAP, "parseLatLon", [[typed]])[0] == expected


@needs_node
def test_the_box_test_is_the_india_box_of_spec_one_four(exports):
    cases = [[28.5, 77.25, True], [6.0, 68.0, True], [38.0, 98.0, True],
             [5.99, 77.0, False], [38.01, 77.0, False],
             [20.0, 67.99, False], [20.0, 98.01, False]]
    answers = exports(SNAP, "inBox", [[lat, lon] for lat, lon, _ in cases])
    for (lat, lon, wanted), got in zip(cases, answers):
        assert got is wanted, (lat, lon, got)


@needs_node
def test_the_square_text_always_shows_two_decimals(exports):
    said = exports(SNAP, "squareText", [[28.5, 77.25], [8.0, 73.0]])
    assert said == ["28.50 N 77.25 E", "8.00 N 73.00 E"]


# ------------------- SPEC 11.28: the islands this grid cannot carry at all

ISLANDS = ROOT / "web" / "src" / "islands.js"
PLACE_FN = ROOT / "api" / "place.mjs"
TOWNLIST = ROOT / "web" / "src" / "townlist.js"
TOWNS_FILE = ROOT / "web" / "src" / "towns.json"
MASK_FILE = ROOT / "config" / "india_mask.json"


def india_box_points(step: float = 0.5) -> list[list[float]]:
    """A sweep of the whole India box, plus the squares that matter."""
    points = []
    lat = 6.0
    while lat <= 38.0001:
        lon = 68.0
        while lon <= 98.0001:
            points.append([round(lat, 2), round(lon, 2)])
            lon += step
        lat += step
    points += [[10.5, 72.75], [11.75, 92.75], [12.75, 92.75], [12.5, 92.75],
               [10.75, 92.5], [8.0, 71.5], [12.5, 74.0], [6.0, 92.0],
               [14.0, 94.5], [12.51, 74.01], [7.99, 71.49], [28.5, 77.25]]
    return points


@needs_node
def test_the_page_and_the_api_say_the_same_thing_about_the_islands(exports):
    """Two copies of one table, kept honest the way SPEC 11.24 keeps the snap.

    The page answers for a reader who clicked Lakshadweep; api/place answers
    for a reader with no JavaScript asking the same question. If the two ever
    disagreed, the site would say one thing and its own API another.
    """
    points = india_box_points()
    page = exports(ISLANDS, "notFoundNote", points)
    api = exports(PLACE_FN, "notFoundNote", points)
    assert page == api
    groups_page = exports(ISLANDS, "islandGroup", points)
    groups_api = exports(PLACE_FN, "islandGroup", points)
    assert groups_page == groups_api

    # And it fires where it should and nowhere else.
    said = dict(zip([tuple(p) for p in points], page))
    assert said[(10.5, 72.75)].startswith("Lakshadweep is not forecast.")
    assert said[(11.75, 92.75)].startswith("This part of the Andaman")
    assert said[(28.5, 77.25)] is None       # Delhi
    assert said[(25.0, 80.0)] is None        # the middle of the country
    assert said[(12.51, 74.01)] is None      # one step outside the box
    assert said[(7.99, 71.49)] is None


@needs_node
def test_the_island_sentences_say_what_was_measured_and_judge_nothing(
        exports):
    notes = exports(ISLANDS, "notFoundNote", [[10.5, 72.75], [11.75, 92.75]])
    lakshadweep, andaman = notes

    # The measurements these sentences rest on are in SPEC 11.28: 209 squares
    # cover Lakshadweep and none has its centre on land, and exactly three
    # squares in the Andaman box pass SPEC 3.5's rule.
    assert "209" in lakshadweep
    assert "28 km" in lakshadweep and "28 km" in andaman
    for square in ("12.75 N 92.75 E", "12.50 N 92.75 E", "10.75 N 92.50 E"):
        assert square in andaman, square

    # It is a limit of the grid, and must never read as a forecast.
    for note in notes:
        low = note.lower()
        assert "not a forecast of no rain" in low
        assert "%" not in note
        for word in ("dry", "likely", "chance", "probability", "unlikely",
                     "expect", "safe"):
            assert word not in low, (word, note)


@needs_node
def test_a_point_in_lakshadweep_is_not_called_the_open_ocean(store, harness):
    """The whole point of SPEC 11.28's table, through the real function.

    The test store holds a small grid near 38 N 68 E, so every one of these
    asks for a tile the store does not have, which is exactly the "no square
    here" case a real Lakshadweep click produces.
    """
    island = call(harness, "place", "?lat=10.5&lon=72.75", store["base"])
    assert island["status"] == 404
    assert island["json"]["island_group"] == "Lakshadweep"
    assert island["json"]["error"].startswith("Lakshadweep is not forecast.")

    andaman = call(harness, "place", "?lat=11.75&lon=92.75", store["base"])
    assert andaman["status"] == 404
    assert andaman["json"]["island_group"] == "Andaman & Nicobar"
    assert "narrower than one square" in andaman["json"]["error"]

    # Somewhere with no island story: the old sentence, unchanged.
    plain = call(harness, "place", "?lat=25&lon=80", store["base"])
    assert plain["status"] == 404
    assert plain["json"]["island_group"] is None
    assert plain["json"]["error"] == "outside the forecast area"
    assert "all eight squares around it" in plain["json"]["detail"]


# ---------------------------- SPEC 11.28: the towns the search box offers

def load_towns() -> list[dict]:
    return json.loads(TOWNS_FILE.read_text("utf-8"))["towns"]


def load_mask() -> dict:
    return json.loads(MASK_FILE.read_text("utf-8"))
def test_the_town_list_is_the_natural_earth_list_it_says_it_is():
    body = json.loads(TOWNS_FILE.read_text("utf-8"))
    assert body["source"]["layer"] == "ne_10m_populated_places"
    assert body["source"]["licence"] == "public domain"
    assert "India point-of-view" in body["source"]["rule"]
    assert len(body["towns"]) == 215


def test_the_town_list_holds_nothing_finer_than_one_square():
    """SPEC 11.19 in the data as well as in the code.

    A town's own position is never written down: the file holds the square
    the page shows, so a coordinate finer than 28 km is not in the bundle at
    all and cannot leak into a URL by accident.
    """
    for town in load_towns():
        for lat, lon in [(town["lat"], town["lon"])] + (
                [(town["moved_from"]["lat"], town["moved_from"]["lon"])]
                if "moved_from" in town else []):
            assert 6.0 <= lat <= 38.0 and 68.0 <= lon <= 98.0, town
            assert abs(round(lat * 4) / 4 - lat) < 1e-9, town
            assert abs(round(lon * 4) / 4 - lon) < 1e-9, town


@needs_node
def test_every_town_resolves_to_an_india_square_or_says_plainly_why(exports):
    """What the search box promises. SPEC 11.28.

    Every one of the 215 towns either lands on a square that is in the India
    mask — so /api/place has numbers for it — or carries the island group it
    is in, and that group has a sentence of its own. There is no third
    outcome, and in particular no town that can be searched and then answered
    with "outside the forecast area".
    """
    rows = load_mask()["india_rows"]
    towns = load_towns()

    def square_in_mask(lat: float, lon: float) -> bool:
        i = round((38.0 - lat) / 0.25)
        j = round((lon - 68.0) / 0.25)
        return (0 <= i < len(rows) and 0 <= j < len(rows[i])
                and rows[i][j] == "1")

    missing = [t for t in towns if "not_forecast" in t]
    notes = exports(ISLANDS, "notFoundNote",
                    [[t["lat"], t["lon"]] for t in missing])
    groups = exports(ISLANDS, "islandGroup",
                     [[t["lat"], t["lon"]] for t in missing])

    for town, note, group in zip(missing, notes, groups):
        assert note and len(note) > 60, town
        assert group == town["not_forecast"], town

    for town in towns:
        if "not_forecast" in town:
            continue
        assert square_in_mask(town["lat"], town["lon"]), town

    # The two that cannot be forecast are the two measured in SPEC 11.28, and
    # no others have crept in.
    assert {t["name"]: t["not_forecast"] for t in missing} == {
        "Kavaratti": "Lakshadweep",
        "Port Blair": "Andaman & Nicobar",
    }


@needs_node
def test_the_page_and_the_api_agree_on_every_town_s_square(exports):
    """The stored square is the square api/place would pick for that town.

    A town is stored as a square centre, so snapping it must be a no-op, in
    the page and in the function alike. If this drifted, the search box would
    show one square's name over another square's numbers.
    """
    towns = [t for t in load_towns() if "not_forecast" not in t]
    calls = [[t["lat"], t["lon"]] for t in towns]
    page = exports(SNAP, "snap", calls)
    api = exports(PLACE_FN, "snapSquare", calls)
    assert page == api
    for town, got in zip(towns, page):
        assert (got["lat"], got["lon"]) == (town["lat"], town["lon"]), town


@needs_node
def test_an_empty_search_box_matches_nothing(exports):
    """SPEC 11.28. The page said 'No town in the list starts with ""'.

    findTowns is what that message was built on, so the fix is tested here:
    nothing typed, nothing matched, nothing to apologise for.
    """
    towns = load_towns()
    answers = exports(TOWNLIST, "findTowns",
                      [[towns, ""], [towns, "   "], [towns, None]])
    assert answers == [[], [], []]


@needs_node
def test_the_search_offers_what_starts_with_the_letters_first(exports):
    towns = load_towns()
    found = exports(TOWNLIST, "findTowns",
                    [[towns, "kavar"], [towns, "delh"], [towns, "zzzz"],
                     [towns, "aurangabad"]])
    kavaratti, delhi, nothing, aurangabad = found

    assert [t["name"] for t in kavaratti] == ["Kavaratti"]
    assert kavaratti[0]["not_forecast"] == "Lakshadweep"
    assert [t["name"] for t in delhi][0] == "Delhi"
    assert nothing == []
    # Both Aurangabads are offered, and each says which state it is in.
    assert [t["state"] for t in aurangabad] == ["Bihar", "Maharashtra"]


@needs_node
def test_a_square_with_two_towns_in_it_names_both(exports):
    """Four squares hold two towns each, and the page claims neither alone."""
    towns = load_towns()
    said = exports(TOWNLIST, "nameOfSquare",
                   [[towns, 28.5, 77.25], [towns, 22.5, 88.25],
                    [towns, 26.25, 91.75], [towns, 19.25, 73.25],
                    [towns, 13.0, 80.25], [towns, 10.5, 72.75]])
    assert said[0] == "Faridabad and New Delhi"
    assert said[1] == "Haora and Kolkata"
    assert said[2] == "Dispur and Guwahati"
    assert said[3] == "Bhiwandi and Kalyan"
    assert said[4] == "Chennai"
    # A town the grid cannot carry never names a square.
    assert said[5] is None


@needs_node
def test_a_square_is_named_near_its_city_or_called_this_area(exports):
    """SPEC 11.38. Three answers, in order: the city, "near", "this area".

    The limit is 50 km, which is under two squares, so "near Nagpur" is
    never said about somewhere a reader would call a different place. The
    distances below are measured here, with the same great-circle formula
    written out again, so the test knows which side of the limit each
    square is on rather than assuming it.
    """
    towns = load_towns()

    def km(one, two):
        lat1, lon1 = one
        lat2, lon2 = two
        rad = math.pi / 180
        a = (math.sin((lat2 - lat1) * rad / 2) ** 2
             + math.cos(lat1 * rad) * math.cos(lat2 * rad)
             * math.sin((lon2 - lon1) * rad / 2) ** 2)
        return 2 * 6371 * math.asin(min(1, math.sqrt(a)))

    # A list, not a dict: two towns share a name (both Aurangabads), and a
    # dict would quietly drop one of them and so one of the distances.
    forecast = [town for town in towns if not town.get("not_forecast")]
    names = {town["name"] for town in forecast}
    nagpur = next(town for town in forecast if town["name"] == "Nagpur")
    here = (nagpur["lat"], nagpur["lon"])

    # Its own square: the city's name, with no "near" in front of it.
    own = exports(TOWNLIST, "placeName", [[towns, here[0], here[1]]])[0]
    assert own == "Nagpur", own

    # One square away. Measured, not assumed: this is under 50 km.
    close = (round(here[0] - 0.25, 2), here[1])
    assert km(here, close) < 50, km(here, close)
    said = exports(TOWNLIST, "placeName", [[towns, close[0], close[1]]])[0]
    assert said.startswith("near "), said

    # Somewhere with no city within 50 km at all, found rather than guessed.
    far = None
    lat = 24.0
    while lat < 30.0 and far is None:
        lon = 70.0
        while lon < 90.0:
            if all(km((lat, lon), (town["lat"], town["lon"])) > 50
                   for town in forecast):
                far = (lat, lon)
                break
            lon += 0.25
        lat += 0.25
    assert far is not None, "no square in the sweep is 50 km from every city"
    assert exports(TOWNLIST, "placeName",
                   [[towns, far[0], far[1]]])[0] == "this area"

    # And the rule itself, over a sweep: whatever is said, it agrees with
    # the distances. Every square of the India box at half a degree.
    points = india_box_points()
    said_all = exports(TOWNLIST, "placeName", [[towns, *p] for p in points])
    for point, name in zip(points, said_all):
        nearest = min(km(tuple(point), (town["lat"], town["lon"]))
                      for town in forecast)
        if name == "this area":
            assert nearest > 50, (point, nearest)
        elif name.startswith("near "):
            assert nearest <= 50, (point, nearest)
            assert name[5:] in names, name
        else:
            assert nearest == 0, (point, name, nearest)


@needs_node
def test_an_island_the_grid_cannot_carry_never_names_a_square(exports):
    """SPEC 11.38. "near Port Blair" where there is no Port Blair forecast.

    Kavaratti and Port Blair are in the city list and have no square. A
    square in the sea beside them must not be named after them, because the
    name would promise numbers that do not exist.
    """
    towns = load_towns()
    islands = [town for town in towns if town.get("not_forecast")]
    assert islands, "the list has no island cities to check"
    for town in islands:
        said = exports(TOWNLIST, "placeName",
                       [[towns, town["lat"], town["lon"]]])[0]
        assert town["name"] not in said, (town["name"], said)


@pytest.mark.skipif(
    not (ROOT / "data" / "raw" / "ne"
         / "ne_10m_populated_places.shp").exists(),
    reason="the Natural Earth populated places shapefile is not here; "
           "data/ is never committed")
def test_the_committed_town_list_is_what_the_script_writes():
    """SPEC 11.28: the file is built, not hand-edited."""
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_towns.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "byte for byte" in done.stdout


# ------------------------- SPEC 11.28: the sea is not the colour of nothing

@needs_node
def test_the_sea_can_be_told_apart_from_a_square_no_run_reached(exports):
    """The fault this was: #eaf0f4 sea against the #eceff1 zero class.

    A contrast ratio of 1.005 is the same colour. The difference it hid is
    the difference between "the forecast says no model run reaches 1 mm here"
    and "there is no forecast here", which is the whole point of the mask.
    """
    sea = exports(PALETTE, "colourOf", [[0]])  # keeps the import honest
    assert sea == ["#eceff1"]

    text = (ROOT / "web" / "src" / "palette.js").read_text("utf-8")
    assert "export const SEA = '#aec6da'" in text
    # The old colour is named in the comment that records the fault, and
    # nowhere else: no line that is not a comment may still mention it.
    for line in text.splitlines():
        if "#eaf0f4" in line:
            assert line.strip().startswith("//"), line

    def channel(value: float) -> float:
        value /= 255
        return (value / 12.92 if value <= 0.04045
                else ((value + 0.055) / 1.055) ** 2.4)

    def luminance(colour: str) -> float:
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * channel(r) + 0.7152 * channel(g)
                + 0.0722 * channel(b))

    def ratio(one: str, two: str) -> float:
        a, b = luminance(one), luminance(two)
        return (max(a, b) + 0.05) / (min(a, b) + 0.05)

    assert ratio("#aec6da", "#eceff1") > 1.4, "the sea against the 0 class"
    assert ratio("#aec6da", "#ffffff") > 1.5, "the sea against the land"
    assert ratio("#eaf0f4", "#eceff1") < 1.02, "what this replaced"


@needs_node
def test_every_class_is_written_in_an_ink_that_can_be_read_on_it(exports):
    """SPEC 11.28. The five-day strip paints each cell its count's colour.

    It wrote the number on it in the page's own dark ink, so a day where all
    51 runs reach the threshold was near-black on navy. The table has carried
    an ink per class since 11.17 and nothing was reading it.
    """
    inks = exports(PALETTE, "inkOf", [[count] for count in range(52)])
    colours = exports(PALETTE, "colourOf", [[count] for count in range(52)])

    def channel(value: float) -> float:
        value /= 255
        return (value / 12.92 if value <= 0.04045
                else ((value + 0.055) / 1.055) ** 2.4)

    def luminance(colour: str) -> float:
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * channel(r) + 0.7152 * channel(g)
                + 0.0722 * channel(b))

    for count, (ink, colour) in enumerate(zip(inks, colours)):
        assert ink is not None, count
        a, b = luminance(ink), luminance(colour)
        ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        # WCAG AA for text that is not large.
        assert ratio >= 4.5, (count, colour, ink, round(ratio, 2))

    assert exports(PALETTE, "inkOf", [[52], [-1], [None]]) == [None] * 3


# ------------- SPEC 11.29: the names the map draws, and what it says when


# ------------- something it does not control fails

UNITS_FILE = ROOT / "web" / "src" / "units.json"
UNITLIST = ROOT / "web" / "src" / "unitlist.js"
MESSAGES = ROOT / "web" / "src" / "messages.js"
APP = ROOT / "web" / "src" / "App.jsx"
MAP = ROOT / "web" / "src" / "Map.jsx"
CONTROLS = ROOT / "web" / "src" / "Controls.jsx"
INDEX_HTML = ROOT / "web" / "index.html"


def load_units() -> list[dict]:
    return json.loads(UNITS_FILE.read_text("utf-8"))["units"]
def test_the_unit_list_is_the_natural_earth_list_it_says_it_is():
    body = json.loads(UNITS_FILE.read_text("utf-8"))
    assert body["source"]["units"] == "ne_10m_admin_1_states_provinces"
    assert body["source"]["cities"] == "ne_10m_populated_places"
    assert body["source"]["licence"] == "public domain"

    units = body["units"]
    assert len(units) == 36          # 28 states and 8 union territories
    for unit in units:
        assert unit["name"] and unit["code"], unit
        assert len(unit["code"]) == 2, unit
        assert 6.0 <= unit["lat"] <= 38.0, unit
        assert 68.0 <= unit["lon"] <= 98.0, unit
        assert unit["city"]["name"], unit
        # SPEC 11.31: the room to write the name in, measured against the
        # polygon. `span`, the unit's width at the label point, is gone: a
        # width was never the question, a box inside a polygon was.
        assert "span" not in unit, unit
        assert len(unit["fit"]) == len(body["fit"]["aspects"]), unit

    # Largest polygon first, which is the order the map places names in.
    assert units[0]["name"] == "Rajasthan"
    assert units[-1]["name"] == "Lakshadweep"


def test_a_unit_s_city_is_a_square_the_page_can_already_answer_for():
    """SPEC 11.29. The map's city labels are towns, not a second list.

    Every city the map labels is in towns.json, snapped to the same square by
    the same rule, so clicking its dot and searching its name land on one set
    of numbers. The two that have no square at all are the two of SPEC 11.28,
    and they are labelled anyway, because the islands are there.
    """
    towns = {t["name"]: t for t in load_towns()}
    missing = {}
    for unit in load_units():
        city = unit["city"]
        town = towns.get(city["name"])
        assert town is not None, city
        assert (city["lat"], city["lon"]) == (town["lat"], town["lon"]), city
        assert city.get("moved_from") == town.get("moved_from"), city
        if city.get("not_forecast"):
            missing[city["name"]] = city["not_forecast"]
    assert missing == {"Kavaratti": "Lakshadweep",
                       "Port Blair": "Andaman & Nicobar"}


def test_the_unit_list_holds_no_position_finer_than_a_square():
    """A city's own position never reaches the bundle. SPEC 11.19.

    The unit's own label point is not a place anybody is: it is where a word
    is written. The city's is a square centre, like every other coordinate
    the page holds.
    """
    for unit in load_units():
        city = unit["city"]
        assert abs(round(city["lat"] * 4) / 4 - city["lat"]) < 1e-9, unit
        assert abs(round(city["lon"] * 4) / 4 - city["lon"]) < 1e-9, unit


@needs_node
def test_the_map_is_given_the_names_in_the_order_it_places_them(exports):
    """SPEC 11.29. Largest unit first, largest city first.

    The order is the whole of the "which name matters" question. There is no
    list of important places: a unit's name is tried before a smaller unit's,
    a city's before a smaller city's, and what does not fit is not drawn.
    """
    units = load_units()
    labels = exports(UNITLIST, "unitLabels", [[units]])[0]
    cities = exports(UNITLIST, "cityLabels", [[units]])[0]

    assert [u["name"] for u in labels] == [u["name"] for u in units]
    for label in labels:
        # The room there is to write the name in has to reach the map, or it
        # cannot tell a name from a word written across the neighbours.
        assert label["fit"] and label["fit"][0] > 0, label
        assert label["code"], label

    pops = [c["pop"] for c in cities]
    assert pops == sorted(pops, reverse=True)
    assert len(cities) == len(units)
    assert cities[0]["name"] == "Mumbai"
    absent = [c["name"] for c in cities if not c["forecast"]]
    assert sorted(absent) == ["Kavaratti", "Port Blair"]


@needs_node
def test_a_misspelled_town_is_offered_the_nearest_names_and_never_given_one(
        exports):
    """SPEC 11.29. "Did you mean", as buttons, and nothing chosen for you.

    Natural Earth's spellings are its own — Simla, Dehra Dun — so a reader
    who types the name they know gets nothing from a search that only matches
    the start of a name. The offer is the fix. Choosing for them is not: it
    would put one place's numbers under another place's name.
    """
    towns = load_towns()
    asked = ["Kavarati", "Chenai", "Dehli", "Bengalore", "Shimla",
             "Dehradun", "Kolkota", "zzzzzz", "go", ""]
    near = exports(TOWNLIST, "nearTowns", [[towns, word] for word in asked])
    found = exports(TOWNLIST, "findTowns", [[towns, word] for word in asked])

    offered = {word: [t["name"] for t in answer]
               for word, answer in zip(asked, near)}
    assert offered["Kavarati"] == ["Kavaratti"]
    assert offered["Chenai"] == ["Chennai"]
    assert offered["Dehli"] == ["Delhi"]
    assert offered["Bengalore"] == ["Bengaluru"]
    assert offered["Shimla"] == ["Simla"]
    assert offered["Dehradun"] == ["Dehra Dun"]
    assert offered["Kolkota"] == ["Kolkata"]
    # Nothing near enough, and nothing to be near: no guesses from two
    # letters, and none at all from gibberish.
    assert offered["zzzzzz"] == []
    assert offered["go"] == []
    assert offered[""] == []

    # SPEC 11.38. Shimla and Dehradun are not misspellings any more: they
    # are the current names of places Natural Earth spells Simla and Dehra
    # Dun, and the search holds both. The page offers "did you mean" only
    # where the search itself found nothing, so these two never reach it.
    matched = {word: [t["name"] for t in answer]
               for word, answer in zip(asked, found)}
    assert matched["Shimla"] == ["Simla"], matched["Shimla"]
    assert matched["Dehradun"] == ["Dehra Dun"], matched["Dehradun"]

    # Never more than three, and never an answer: where the search itself
    # found nothing, the near miss is a question and not a resolution.
    for word, answer, matches in zip(asked, near, found):
        assert len(answer) <= 3, word
        if answer and word not in ("Shimla", "Dehradun"):
            assert matches == [], word


@needs_node
def test_the_edit_distance_is_the_plain_one_and_stops_when_told(exports):
    pairs = [["", ""], ["delhi", "delhi"], ["dehli", "delhi"],
             ["chenai", "chennai"], ["goa", "goal"], ["kavaratti", "x"],
             ["abc", "abcdefghij"]]
    away = exports(TOWNLIST, "editDistance", pairs)
    assert away[0] == 0
    assert away[1] == 0
    assert away[2] == 2          # one transposition, two single edits
    assert away[3] == 1
    assert away[4] == 1
    assert away[5] == 4          # over the limit of 3, reported as 4
    assert away[6] == 4          # the lengths alone are further than 3


@needs_node
def test_every_way_a_location_can_fail_says_one_clear_line(exports):
    """SPEC 11.29. The three failures of the standard, and no browser text.

    Permission refused, position unavailable, timed out. Each gets a line of
    its own that says what happened and what to do instead. The browser's own
    `message` is never shown: it is written for a developer.
    """
    codes = [[1], [2], [3], [0], [None], [99]]
    said = exports(MESSAGES, "locationProblem", codes)
    for line in said:
        assert line and "\n" not in line
        assert line.endswith(".")
        assert len(line) < 160
        # Every one of them leaves the reader somewhere to go.
        assert "city" in line

    assert said[0] != said[1] != said[2]
    assert "permission" in said[0].lower()
    assert "too long" in said[2]
    # Anything that is not one of the three is the no-location line.
    assert said[3] == said[4] == said[5]


@needs_node
def test_the_map_failing_says_the_numbers_are_still_there(exports):
    """SPEC 11.29. No WebGL 2, no MapLibre, or no chunk: the same promise.

    A reader cannot act on which of them it was, so each line says the two
    things that matter: the map is not drawn, and everything it would have
    shown is in words and numbers below.
    """
    said = exports(MESSAGES, "mapProblem",
                   [["webgl2"], ["maplibre"], ["chunk"], ["anything else"]])
    for line in said:
        assert "\n" not in line
        assert "search for a city" in line
        assert "latitude and longitude" in line
    assert "WebGL 2" in said[0]
    assert said[0] != said[1] != said[2]


def test_the_page_draws_the_map_only_when_it_can_and_says_so_when_it_cannot():
    """SPEC 11.29, in the page's own structure.

    `canDraw` is asked before MapLibre is constructed, the constructor is
    caught, and React's lazy chunk is behind an error boundary — three ways
    the map can fail to appear, all three ending in a message in the map's
    own area rather than an empty rectangle.
    """
    map_src = MAP.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert "export function canDraw()" in map_src
    assert "getContext('webgl2')" in map_src
    assert "onProblem('webgl2')" in map_src
    assert "onProblem('maplibre')" in map_src
    assert "catch (error) {" in map_src

    assert "class MapFrame extends Component" in app
    assert "getDerivedStateFromError" in app
    assert "onProblem('chunk')" in app
    assert "mapProblem(noMap)" in app
    # SPEC 11.39. The message is inside the map's own box and the search
    # row and the card are outside it, so the two of them are drawn
    # whatever happened to the map. Before, the order of the two in the
    # file said this; now the boxes do.
    wrap = app.split('<div className="mapwrap">')[1].split("</div>")[0]
    assert "mapProblem(noMap)" in wrap
    assert "<Search" not in wrap and "<Panel" not in wrap


@needs_node
def test_the_grid_and_the_mark_are_not_data_and_say_so(exports):
    """SPEC 11.25 and 11.29. What HC8 may sample, and what it may not.

    The grid lines and everything that marks the chosen square are drawn in
    colours that are not in the palette, and they are named in one exported
    list so the hand check can assert it is not sampling them rather than
    being trusted not to.
    """
    map_src = MAP.read_text("utf-8")
    palette = PALETTE.read_text("utf-8")

    assert "export const NOT_DATA_LAYERS" in map_src
    for layer in ["squares-grid", "picked-casing", "picked-line",
                  "picked-ring-halo", "picked-ring"]:
        assert f"id: '{layer}'" in map_src
        assert f"'{layer}'" in map_src.split("NOT_DATA_LAYERS")[1]

    # The grid appears only where a square is at least twelve pixels across,
    # and the whole-India view is nowhere near that.
    assert "const GRID_VISIBLE_PX = 12;" in map_src
    assert "export const GRID_FROM_ZOOM" in map_src
    assert map_src.count("GRID_FROM_ZOOM") >= 6

    # None of the marks is a palette colour. The palette is asked for its
    # own colours rather than read with a regular expression, which would
    # also have found the hexes written down in its comments.
    hexes = {colour for colour in exports(PALETTE, "colourOf",
                                          [[count] for count in range(52)])}
    marks = re.findall(r"const (?:MARK|GRID_LINE|HALO) = '(#[0-9a-f]{6})'",
                       map_src)
    assert len(marks) == 3, marks
    for colour in marks:
        assert colour not in hexes, colour


def test_each_page_has_its_own_tab_title():
    """SPEC 11.38. Three pages, three titles, all naming the site.

    One shared title meant a reader with the forecast, the report card and
    How we checked open could not tell the three tabs apart. The titles are
    one list, in TopNav.jsx, and the first of them is also the static title
    in index.html, which is the tab before any script has run.
    """
    html = INDEX_HTML.read_text("utf-8")
    app = APP.read_text("utf-8")
    nav = (ROOT / "web" / "src" / "TopNav.jsx").read_text("utf-8")
    site = (ROOT / "web" / "src" / "Site.jsx").read_text("utf-8")

    assert "<title>India Rain Outlook · next 5 days</title>" in html
    # The page names itself with the same constant the tabs are built from.
    assert "export const SITE = 'India Rain Outlook';" in nav
    assert "<h1 className=\"sitename\">{SITE}</h1>" in app
    # And the tab follows pushState, which is the only thing that changes
    # the path on this site.
    assert "document.title = titleOf(path);" in site
    # The noscript page, which is all a reader without JavaScript sees,
    # names the site too.
    assert "<h1>India Rain Outlook: how many of 51 runs bring rain</h1>" in html




# ------------------- SPEC 11.38: a tap on nothing is not the reader's fault

@needs_node
def test_a_tap_outside_india_is_a_calm_line_and_not_an_error(forecast_words):
    """SPEC 11.38. It read "That is outside the forecast area, which covers
    6 to 38 degrees north and 68 to 98 degrees east" -- in a red box, in
    the coordinates of a box nobody can see, to a reader whose finger
    slipped onto the sea or onto Nepal. Nothing went wrong."""
    calm = "That's outside India. Tap the map over India or find a city."
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or calm not in words_of(html):
            continue
        # The plain box, never the red one.
        assert 'class="notice"' in html, html[:200]
        assert 'class="error"' not in html, html[:200]
        # And the limits are still said, quietly, for whoever wants them.
        assert "6 to 38 degrees north" in words_of(html)
        seen += 1
    assert seen >= 1, "the calm line was never rendered"


def test_the_outside_line_clears_the_box_and_takes_the_calm_route():
    """SPEC 11.38, in the page that routes it."""
    app = APP.read_text("utf-8")
    assert "setNotice({ where: null, note: OUTSIDE, why: THE_BOX })" in app
    assert ("setNotice({ where: null, note: OUTSIDE, why: body.detail "
            "|| null })" in app)
    # The name of the place the reader has just left goes out of the search
    # box with it, by both routes.
    assert app.count("setShown('')") == 2, app.count("setShown('')")
    # And no red box is raised for it any more.
    assert "setPlaceError({ said: OUTSIDE" not in app


# ------------------------- SPEC 11.38: the legend, and the colours it names

@needs_node
def test_the_legend_names_both_ends_and_both_other_colours(forecast_words):
    """SPEC 11.38, as SPEC 11.39 leaves it: the key, shut and open.

    The beige had no entry at all. A reader who tapped Nepal got a red
    error about a colour the page had never named, which is the page
    blaming the reader for its own omission.

    Shut, what a reader sees is the question, the strip and the two ends
    in words; open, the nine rows. Both states hold every row, because a
    shut <details> keeps its children in the page -- which is the point of
    using one: the rows are in the document, reachable and searchable,
    whether or not the box is open. Which of the two a reader is given at
    which width is measured in a browser, below.
    """
    shut = 0
    opened = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="mapkey"' not in html:
            continue
        text = words_of(html)
        assert "How many of the 51 runs bring rain?" in text
        assert "None" in text and "All 51" in text
        assert "White: no forecast for this spot" in text
        assert "Beige: land outside India, not forecast" in text
        # The counts in between are still the counts, and each says what
        # it is a count of.
        for band in ("1-10 runs", "11-20 runs", "21-30 runs",
                     "31-40 runs", "41-50 runs", "All 51 runs"):
            assert band in text, band
        # The amount is in the summary's own name, because the colours are
        # counts of it and a reader using a screen reader cannot see which
        # pill is filled.
        assert "mm or more. The colours, in words." in html
        # And no band word of 11.38 is drawn beside a colour. SPEC 11.40
        # puts "About half" on the shut strip, where it names the middle
        # of a scale of counts as "None" and "All 51" name its ends --
        # not a colour, and not what a colour means on the ground. So it
        # is allowed there and checked to be there and nowhere else.
        ends = html.split('class="keyends"')[1].split("</span></span>")[0]
        assert "About half" in ends, ends
        rest = text.lower().replace("about half", "", 1)
        for word in ("a few", "about half", "almost all"):
            assert word not in rest, (word, text)
        # SPEC 11.40. The key is shut, and nothing controls it: one tap
        # either way is the whole of it, and there is no `open` for a
        # renderer to pass. Which is the state that matters here -- the
        # nine rows are in the page while it is shut, reachable and
        # searchable -- and the opened state is measured in a browser,
        # where a reader's own tap opens it.
        assert ' open=""' not in html, html[:120]
        shut += 1
    assert shut >= 3, shut
    assert opened == 0, opened

    # SPEC 11.41. And the other key: the whole of it, open, over the map
    # at 1280 pixels and over. Same rows, same title, no handle and no
    # strip words -- with the rows in front of a reader, "None" and
    # "All 51" over the colours would be the same facts twice.
    over = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="mapkey overmap"' not in html:
            continue
        text = words_of(html)
        assert "How many of the 51 runs bring rain?" in text
        assert "mm or more. The colours, in words." in html
        assert "<summary" not in html, html[:160]
        assert 'class="keyends"' not in html
        for band in ("None", "1-10 runs", "41-50 runs", "All 51 runs",
                     "White: no forecast for this spot",
                     "Beige: land outside India, not forecast"):
            assert band in text, band
        for word in ("a few", "about half", "almost all"):
            assert word not in text.lower(), (word, text)
        over += 1
    assert over >= 3, over


@needs_node
def test_the_amount_buttons_carry_the_nickname_and_the_millimetres(
        forecast_words):
    """SPEC 11.38. The nickname is never the only thing on the button."""
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="group amounts"' not in html:
            continue
        text = words_of(html)
        assert "How much rain?" in text
        for nickname, mm in (("Some rain", 1), ("A rainy day", 10),
                             ("A lot of rain", 50)):
            assert nickname in text, nickname
            assert f"{mm} mm+" in text, mm
        # SPEC 11.39. "10 mm of rain is water 1 cm deep if none of it ran
        # away" was the line under these buttons. It is not under a control
        # any more: what 10 mm is like is on the How to read this map page,
        # in everyday words, and the page's own test below pins it there.
        assert "water 1 cm deep" not in text
        seen += 1
    assert seen >= 3, seen


def test_the_nicknames_are_ours_and_are_written_down():
    """SPEC 11.38. Two of them had to give way to the forbidden list.

    "A wet day" and "very heavy" are the natural English for 10 mm and
    50 mm, and "wet" and "heavy" are both on 11.20's list -- "heavy rain"
    is IMD's own class name for a band this site does not measure, so a
    page that borrowed it would be claiming a warning it has not issued.
    """
    controls = CONTROLS.read_text("utf-8")
    spec = (ROOT / "SPEC.md").read_text("utf-8")
    section = spec.split("### 11.38")[1].split("## The hand checks")[0]

    for nickname in ("Some rain", "A rainy day", "A lot of rain"):
        assert f"'{nickname}'" in controls or f'"{nickname}"' in controls, (
            nickname)
        assert nickname in section, nickname
    # The words they replaced are on 11.20's list, and the word sweep over
    # every rendered state is what keeps them off the screen; here it is
    # enough that the specification says why these three were chosen.
    for banned in ("wet", "heavy"):
        assert banned in section.lower(), banned
    # The page says they are ours, where it says them: SPEC 11.39 moved
    # that from the panel to How to read this map.
    said = (ROOT / "web" / "src" / "HowToRead.jsx").read_text("utf-8")
    assert "not an official category" in said.lower()


# ------------------------- SPEC 11.38: the search box, states and old names

UNITLIST = ROOT / "web" / "src" / "unitlist.js"


@needs_node
def test_every_state_and_union_territory_is_recognised(exports):
    """SPEC 11.38. All 36, in any case, with `&` and "and" one word."""
    units = load_units()
    assert len(units) == 36, len(units)

    calls = []
    wanted = []
    for unit in units:
        name = unit["name"]
        for written in (name, name.lower(), name.upper(),
                        name.replace(" and ", " & "), f"  {name}  "):
            calls.append([units, written])
            wanted.append(name)
    got = exports(UNITLIST, "findUnit", calls)
    for call, want, found in zip(calls, wanted, got):
        assert found is not None, call[1]
        assert found["name"] == want, (call[1], found["name"], want)

    # Older names of units are keys too.
    for written, want in (("Orissa", "Odisha"),
                          ("Uttaranchal", "Uttarakhand"),
                          ("Pondicherry", "Puducherry"),
                          ("tamilnadu", "Tamil Nadu")):
        found = exports(UNITLIST, "findUnit", [[units, written]])[0]
        assert found and found["name"] == want, (written, found)


@needs_node
def test_a_short_form_counts_only_as_the_whole_query(exports):
    """SPEC 11.38. "up" is Uttar Pradesh; "udaipur" is a city.

    Two letters inside a longer word are not an abbreviation. If they
    were, a reader looking for Udaipur would be shown a state.
    """
    units = load_units()
    towns = load_towns()
    for code, name in (("WB", "West Bengal"), ("UP", "Uttar Pradesh"),
                       ("MP", "Madhya Pradesh"), ("TN", "Tamil Nadu"),
                       ("up", "Uttar Pradesh"), ("  tn  ", "Tamil Nadu")):
        found = exports(UNITLIST, "findUnit", [[units, code]])[0]
        assert found and found["name"] == name, (code, found)

    # Every one of the 36 codes, as the whole query.
    calls = [[units, unit["code"]] for unit in units]
    got = exports(UNITLIST, "findUnit", calls)
    for unit, found in zip(units, got):
        assert found and found["name"] == unit["name"], unit["code"]

    # And a word that merely contains a code is not that state.
    for word in ("udaipur", "upper", "tnagar", "mphasis"):
        assert exports(UNITLIST, "findUnit", [[units, word]])[0] is None, word
    # Udaipur is still found as a city.
    found = exports(TOWNLIST, "findTowns", [[towns, "udaipur"]])[0]
    assert [town["name"] for town in found] == ["Udaipur"], found


@needs_node
def test_a_name_that_is_both_a_city_and_a_territory_is_the_city(exports):
    """SPEC 11.38. Delhi, Chandigarh, Puducherry -- and Pondicherry.

    The page's rule: a city one of whose names is exactly the query wins,
    and the state block is not drawn. This checks the two halves the rule
    reads -- the city list and the names each city answers to.
    """
    towns = load_towns()
    for query, city in (("Delhi", "Delhi"), ("delhi", "Delhi"),
                        ("Chandigarh", "Chandigarh"),
                        ("Puducherry", "Puducherry"),
                        ("Pondicherry", "Puducherry")):
        found = exports(TOWNLIST, "findTowns", [[towns, query]])[0]
        names = [town["name"] for town in found]
        assert city in names, (query, names)
        every = exports(TOWNLIST, "namesOf", [[town] for town in found])
        assert any(query.lower() in [n.lower() for n in names_of]
                   for names_of in every), (query, every)
        # And the one that matched exactly is the city we meant.
        exact = [names[i] for i, names_of in enumerate(every)
                 if query.lower() in [n.lower() for n in names_of]]
        assert exact == [city], (query, exact)


@needs_node
def test_every_old_city_name_finds_its_city(exports):
    """SPEC 11.38. The list's spelling is not always the reader's."""
    towns = load_towns()
    known = {town["name"] for town in towns}
    table = exports(TOWNLIST, "namesOf",
                    [[{"name": name}] for name in sorted(known)])
    aliases = {}
    for names in table:
        for alias in names[1:]:
            aliases[alias] = names[0]
    assert len(aliases) >= 40, len(aliases)

    # The ones named in the brief, by name.
    for alias, city in (("Bombay", "Mumbai"), ("Calcutta", "Kolkata"),
                        ("Madras", "Chennai"), ("Bangalore", "Bengaluru"),
                        ("Gurugram", "Gurgaon"), ("Poona", "Pune"),
                        ("Trivandrum", "Thiruvananthapuram"),
                        ("Cochin", "Kochi"), ("Baroda", "Vadodara"),
                        ("Benares", "Varanasi")):
        assert aliases.get(alias) == city, (alias, aliases.get(alias))

    # Every alias names a city that is actually in the list, and finds it
    # in any case. The city is offered under the list's own name.
    for alias, city in aliases.items():
        assert city in known, (alias, city)
    calls = []
    for alias in sorted(aliases):
        calls.append([towns, alias])
        calls.append([towns, alias.lower()])
    for call, found in zip(calls, exports(TOWNLIST, "findTowns", calls)):
        names = [town["name"] for town in found]
        want = aliases[[a for a in aliases
                        if a.lower() == call[1].lower()][0]]
        assert want in names, (call[1], names)


@needs_node
def test_a_match_in_the_middle_of_a_name_works_and_comes_second(exports):
    """SPEC 11.38. "agar" finds four, with the ones that start first."""
    towns = load_towns()
    found = exports(TOWNLIST, "findTowns", [[towns, "agar"]])[0]
    names = [town["name"] for town in found]
    assert "Agartala" in names, names
    assert "Ahmednagar" in names and "Bhavnagar" in names, names
    starts = [n for n in names if n.lower().startswith("agar")]
    holds = [n for n in names if not n.lower().startswith("agar")]
    assert names == starts + holds, names


@needs_node
def test_nothing_matched_offers_four_ways_on(exports):
    """SPEC 11.38. Not a refusal, and not about the reader's spelling."""
    said = exports(TOWNLIST, "noMatch", [["Ooty"], ["  zzz  "]])
    assert said[0] == ("We don't have Ooty yet. Try a nearby city or your "
                       "state, tap the map, or type a latitude and "
                       "longitude such as 22.5, 88.4.")
    assert "zzz" in said[1] and "  zzz  " not in said[1]
    for text in said:
        low = text.lower()
        for word in FORBIDDEN:
            assert word not in low, (word, text)
        for way in ("nearby city", "your state", "tap the map",
                    "latitude and longitude"):
            assert way in low, (way, text)


@needs_node
def test_a_state_is_a_list_of_cities_and_never_a_count(exports):
    """SPEC 11.38. Rain over Rajasthan on one day is not one number."""
    units = load_units()
    towns = load_towns()
    said = exports(UNITLIST, "tooBig", [[unit["name"]] for unit in units])
    for unit, text in zip(units, said):
        assert text.startswith(f"{unit['name']} is too big for one forecast")
        assert "of 51" not in text and "%" not in text
        low = text.lower()
        for word in FORBIDDEN:
            assert word not in low, (word, text)

    # Every unit has at least one city inside it, and every city it lists
    # says it is in that unit.
    inside = exports(UNITLIST, "townsIn",
                     [[towns, unit["name"]] for unit in units])
    for unit, mine in zip(units, inside):
        assert mine, unit["name"]
        for town in mine:
            assert town["unit"] == unit["name"], (unit["name"], town)
    listed = sum(len(mine) for mine in inside)
    assert listed == sum(1 for town in towns if town.get("unit")), listed


def test_every_unit_box_holds_every_city_in_it():
    """SPEC 11.38. The box the map is fitted to, against the cities."""
    units = load_units()
    towns = load_towns()
    for unit in units:
        box = unit["box"]
        assert len(box) == 4, unit["name"]
        west, south, east, north = box
        assert west < east and south < north, (unit["name"], box)
        for town in [t for t in towns if t.get("unit") == unit["name"]]:
            # towns.json holds the square the page shows and not the city's
            # own point, and that square can be an eighth of a degree away
            # from it by snapping and a further quarter by the sea rule of
            # SPEC 11.7 -- Diu's square is 21.00 N and its unit's box ends
            # at 20.74. Half a degree covers both and is still tight
            # enough to catch a city filed under the wrong state.
            slack = 0.5
            assert west - slack <= town["lon"] <= east + slack, (
                unit["name"], town["name"], box)
            assert south - slack <= town["lat"] <= north + slack, (
                unit["name"], town["name"], box)
        # The unit's own label point is inside its own box.
        assert west <= unit["lon"] <= east, unit["name"]
        assert south <= unit["lat"] <= north, unit["name"]


# ------------------------------- SPEC 11.38: how old this forecast is

@needs_node
def test_the_freshness_line_says_when_and_how_old(forecast_words):
    """SPEC 11.38 and 11.39. One line, where the run line was three.

    It names the run's own time and counts the age from the time it has
    just printed. It used to print the publish time beside an age counted
    from the run time, so the two numbers on one line disagreed with each
    other by however long the pipeline had taken.
    """
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="fresh"' not in html:
            continue
        line = re.search(r'<p class="fresh[^"]*"[^>]*>(.*?)</p>', html)
        assert line, html[:200]
        text = words_of(line.group(1)).strip()
        assert text.startswith("Forecast from "), text
        assert " IST" in text and "h old" in text, text
        # No year: on a phone it is a word nobody reads.
        assert not re.search(r"20\d\d", text), text
        seen += 1
    assert seen >= 1, "the freshness line was never rendered"


@needs_node
def test_the_stale_wording_never_promises_a_newer_run(forecast_words):
    """SPEC 11.8 and 11.38.

    The banner used to read "A newer model run has not been published",
    which is true and reads as a promise that one is coming. Nothing here
    knows that: the store may be behind, ECMWF may be late, the run may
    never arrive. It says how old this one is and stops.
    """
    said = []
    for html in forecast_words:
        if not isinstance(html, str):
            continue
        text = words_of(html)
        if "hours old" in text:
            said.append(text)
    assert said, "no stale wording was rendered"
    for text in said:
        low = text.lower()
        assert "a newer one has not arrived yet" in low, text
        for promise in ("will be", "on its way", "coming", "shortly",
                        "soon", "due", "shall"):
            assert promise not in low, (promise, text)
        # And it never implies one has been published either.
        assert "has not been published" not in low, text


# ---------------------------- SPEC 11.38: what the day buttons are called

DAYS_JS = ROOT / "web" / "src" / "days.js"


@needs_node
def test_a_day_is_named_from_the_readers_own_date(exports):
    """SPEC 11.38. "Today" and "Tomorrow" come from the dates, not the lead.

    Lead day 1 runs 5:30 am to 5:30 am IST, so a reader opening the page at
    4 am is inside the previous day's lead day 1. Naming the buttons by
    their lead day would print "Tomorrow" over today's forecast for an hour
    and a half every morning, which is the one thing these two words must
    never do.
    """
    first = "2026-11-14T05:30:00+05:30"
    short = "Sat 14 Nov"

    # The reader's date equal to the first day's, one before, two before.
    assert exports(DAYS_JS, "dayName",
                   [[first, "2026-11-14", short]])[0] == "Today"
    assert exports(DAYS_JS, "dayName",
                   [[first, "2026-11-13", short]])[0] == "Tomorrow"
    assert exports(DAYS_JS, "dayName",
                   [[first, "2026-11-12", short]])[0] == short
    # And a day already past is its date, never "Today".
    assert exports(DAYS_JS, "dayName",
                   [[first, "2026-11-15", short]])[0] == short

    # Across a month end and a year end, where string arithmetic breaks.
    assert exports(DAYS_JS, "dayName",
                   [["2026-12-01T05:30:00+05:30", "2026-11-30",
                     "Tue 1 Dec"]])[0] == "Tomorrow"
    assert exports(DAYS_JS, "dayName",
                   [["2027-01-01T05:30:00+05:30", "2026-12-31",
                     "Fri 1 Jan"]])[0] == "Tomorrow"

    # Nothing is invented: with no usable date the published label stands.
    for bad in [["", "2026-11-14", short], [None, "2026-11-14", short],
                [first, "not a date", short], [first, None, short]]:
        assert exports(DAYS_JS, "dayName", [bad])[0] == short, bad


@needs_node
def test_the_five_buttons_are_short_enough_for_a_phone(exports):
    """SPEC 11.29 and 11.38. "Today", "Tomorrow", then "Sat 14"."""
    days = [f"2026-11-{14 + n:02d}T05:30:00+05:30" for n in range(5)]
    shorts = ["Sat 14 Nov", "Sun 15 Nov", "Mon 16 Nov", "Tue 17 Nov",
              "Wed 18 Nov"]
    got = exports(DAYS_JS, "dayButton",
                  [[day, "2026-11-14", short]
                   for day, short in zip(days, shorts)])
    assert got == ["Today", "Tomorrow", "Mon 16", "Tue 17", "Wed 18"]
    # The month is dropped from the buttons and from them only.
    for button in got:
        assert "Nov" not in button, button


@needs_node
def test_the_readers_own_date_is_ist_and_needs_no_timezone_database(exports):
    """SPEC 11.38. A fixed +05:30, as api/health's own labels are."""
    # 2026-11-13 18:29 UTC is still 13 November in IST; one minute later it
    # is the 14th. Both sides of the boundary, in milliseconds.
    before = exports(DAYS_JS, "istToday", [[1794594540000]])[0]
    after = exports(DAYS_JS, "istToday", [[1794594600000]])[0]
    assert (before, after) == ("2026-11-13", "2026-11-14"), (before, after)


# ------------------------------- SPEC 11.38: the headline and its band words

RECORD_JS = ROOT / "web" / "src" / "record.js"

# The table of SPEC 11.38, written out again here rather than imported, so
# the test is a second statement of the rule and not a copy of the code.
BAND_WORDS = (
    (0, 0, "none"),
    (1, 10, "a few"),
    (11, 20, "some"),
    (21, 30, "about half"),
    (31, 45, "most"),
    (46, 50, "almost all"),
    (51, 51, "all"),
)


def expected_band(count: int) -> str | None:
    for low, high, word in BAND_WORDS:
        if low <= count <= high:
            return word
    return None


@needs_node
def test_every_band_boundary_is_the_word_the_spec_says(exports):
    """SPEC 11.38. All 52 counts, and both sides of all six boundaries.

    An off-by-one here is the page saying "most" where the record says
    "about half", which is the one thing a band word could get wrong that a
    reader could not catch.
    """
    counts = list(range(0, 52))
    got = exports(RECORD_JS, "bandWord", [[count, 51] for count in counts])
    for count, word in zip(counts, got):
        assert word == expected_band(count), (count, word)

    # Both sides of every boundary, named, so a failure says which edge.
    for low, high, word in BAND_WORDS:
        assert got[low] == word, (low, got[low])
        assert got[high] == word, (high, got[high])
        if low:
            assert got[low - 1] != word, (low - 1, word)

    # Anything that is not a count of runs is not a band.
    for bad in ([-1, 51], [52, 51], [1.5, 51], ["7", 51], [None, 51]):
        assert exports(RECORD_JS, "bandWord", [bad])[0] is None, bad


@needs_node
def test_the_headline_is_the_same_shape_every_time(exports):
    """SPEC 11.38: place, day, band, amount, count, in that order."""
    calls = [
        ["Sat, 14 Nov", 7, 51, 10],
        ["Today, 15 Nov", 0, 51, 50],
        ["Tomorrow, 16 Nov", 51, 51, 1],
        ["Mon, 16 Nov", 31, 51, 10],
    ]
    wanted = [
        "Sat, 14 Nov: a few of the 51 runs bring 10 mm or more (7 of 51).",
        "Today, 15 Nov: none of the 51 runs bring 50 mm or more (0 of 51).",
        "Tomorrow, 16 Nov: all of the 51 runs bring 1 mm or more "
        "(51 of 51).",
        "Mon, 16 Nov: most of the 51 runs bring 10 mm or more (31 of 51).",
    ]
    assert exports(RECORD_JS, "headline", calls) == wanted

    # SPEC 11.40. The place is not in the sentence: it is the heading
    # directly above it, and the card said it four times over.
    for said in wanted:
        assert "Kolkata" not in said and "near " not in said, said

    # Nothing to say is said as nothing, never as a sentence with a hole.
    for bad in ([None, 7, 51, 10], ["", 7, 51, 10],
                ["Today, 15 Nov", None, 51, 10],
                ["Today, 15 Nov", 99, 51, 10]):
        assert exports(RECORD_JS, "headline", [bad])[0] is None, bad


@needs_node
def test_the_headline_never_says_a_forbidden_word(exports):
    """SPEC 11.20's list, over every count and every amount it can carry."""
    calls = [["Sat, 14 Nov", count, 51, threshold]
             for count in range(0, 52)
             for threshold in (1, 10, 50)]
    for said in exports(RECORD_JS, "headline", calls):
        low = said.lower()
        for word in FORBIDDEN:
            assert word not in low, f"{word} appears in: {said}"
        assert said.endswith(")."), said
        # The band word and the count are both there, always.
        assert " of 51)" in said and " of the 51 runs bring " in said, said


def test_the_band_words_are_never_drawn_on_the_legend():
    """SPEC 11.38. A word on the colour key would be a claim about a square.

    The bands describe the runs. On the legend, beside a colour, the same
    word would read as a name for what that colour means on the ground,
    which is a forecast this site does not make.
    """
    legend = (ROOT / "web" / "src" / "Legend.jsx").read_text("utf-8")
    palette = PALETTE.read_text("utf-8")
    record_js = RECORD_JS.read_text("utf-8")

    assert "BANDS" in record_js and "bandWord" in record_js
    # The legend does not have the table to draw from. What the rendered
    # legend actually says is checked in the word sweep, which reads the
    # drawn text rather than the source and so cannot be fooled by a
    # comment that happens to use one of the words.
    for name in ("bandWord", "BANDS", "headline"):
        assert name not in legend, name
        assert name not in palette, name


def test_the_day_buttons_are_short_and_the_window_is_not():
    """SPEC 11.29. "Fri 13" on the button, the whole window under it.

    Five buttons reading "Fri 13 Nov" came to 418 pixels on a 390 pixel
    phone, so the row scrolled sideways and days 4 and 5 were off the edge.
    Nothing is lost by shortening the button: the line under it carries the
    month, the times and IST, and api/place repeats the whole label for the
    chosen day in the panel.
    """
    controls = CONTROLS.read_text("utf-8")
    styles = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")

    # SPEC 11.38 renamed it: the short form is `dayButton`, in days.js,
    # and it names the day from the reader's own IST date rather than from
    # a lead day.
    assert "{dayWord(entry.from_ist, now, entry.short_ist)}" in controls
    assert "{dayDate(entry.short_ist)}" in controls
    assert "export function dayButton(" in (
        ROOT / "web" / "src" / "days.js").read_text("utf-8")
    # And the row is laid out so that it cannot overflow however wide the
    # words turn out to be.
    assert ".days .radios button { flex: 1 1 0;" in styles
    # Nothing in the map page's own rules may scroll sideways. The report
    # card's label grid may (SPEC 11.34): it is a table of 5 columns on a
    # document page, and scrolling it is better than shrinking the words.
    shell = styles.split("/* --------------------------------- the three "
                         "pages, SPEC 11.34 */")[0]
    assert "overflow-x: auto" not in shell
    # Everything that may scroll sideways is on the two document pages, and
    # each one says in the stylesheet what it is: the wrapper around the
    # 60-label grid at full width (11.34), and the sentence tables under 560
    # pixels, whose columns come out as wide as the machine's font makes
    # them (11.36). The label grid itself may not scroll at any width.
    document = styles[len(shell):]
    assert document.count("overflow-x: auto") == styles.count(
        "overflow-x: auto") == 2
    assert ".gridwrap { margin: 0.8rem 0; overflow-x: auto; }" in document
    assert ".plain, .bands {" in document


# ----------------- SPEC 11.30: the land around India, the names in the


# ----------------- order they are placed, and one answer at a time

ANSWERS = ROOT / "web" / "src" / "answers.js"
LAND_FILE = ROOT / "web" / "src" / "geo" / "land.geo.json"
LEGEND = ROOT / "web" / "src" / "Legend.jsx"
PANEL = ROOT / "web" / "src" / "Panel.jsx"


def contrast(one: str, two: str) -> float:
    """The WCAG ratio between two hex colours."""
    def channel(value: float) -> float:
        value /= 255
        return (value / 12.92 if value <= 0.04045
                else ((value + 0.055) / 1.055) ** 2.4)

    def luminance(colour: str) -> float:
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        return (0.2126 * channel(r) + 0.7152 * channel(g)
                + 0.0722 * channel(b))

    a, b = luminance(one), luminance(two)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@needs_node
def test_an_answer_is_shown_only_for_the_square_that_is_chosen(exports):
    """The fault this is for, reproduced on the built page. SPEC 11.30.

    "Use my location" put the ring and the box on 22.75 N 88.25 E while the
    panel went on showing 34.50 N 74.25 E and 51 of 51 model runs at 1 mm:
    two requests were in the air, the older one answered last, and whichever
    answered last won.

    The rule is both halves. The ticket catches two requests crossing; the
    square catches a request that was answered after the reader moved on for
    any other reason.
    """
    kolkata = {"lat": 22.75, "lon": 88.25}
    srinagar = {"lat": 34.5, "lon": 74.25}

    # The exact shape of the bug: request 1 was for Srinagar's square,
    # request 2 for Kolkata's, and 1 answers last.
    late = exports(ANSWERS, "keepAnswer", [[1, 2, srinagar, srinagar]])
    assert late == [False], "a stale answer must not be shown"

    # The one that is current and is about the square now chosen.
    good = exports(ANSWERS, "keepAnswer", [[2, 2, kolkata, kolkata]])
    assert good == [True]

    # Current ticket, wrong square: also refused.
    wrong = exports(ANSWERS, "keepAnswer", [[2, 2, kolkata, srinagar]])
    assert wrong == [False]

    # Nothing, nonsense and half-answers are refused rather than guessed at.
    odd = exports(ANSWERS, "keepAnswer", [
        [2, 2, kolkata, None],
        [2, 2, None, kolkata],
        [None, 2, kolkata, kolkata],
        [2, 2, kolkata, {"lat": 22.75, "lon": None}],
    ])
    assert odd == [False, False, False, False]


@needs_node
def test_two_squares_are_the_same_square_only_when_they_are(exports):
    same = exports(ANSWERS, "sameSquare", [
        [{"lat": 22.75, "lon": 88.25}, {"lat": 22.75, "lon": 88.25}],
        [{"lat": 22.75, "lon": 88.25}, {"lat": 22.75, "lon": 88.5}],
        [{"lat": 22.75, "lon": 88.25}, {"lat": 22.5, "lon": 88.25}],
        [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0}],
    ])
    assert same == [True, False, False, True]


def test_the_panel_cannot_draw_numbers_for_another_square():
    """SPEC 11.30, in the page's own structure.

    Two defences, because one of them is a rule about time and the other is
    a rule about identity: the request that answers must be the latest one,
    and what is on the screen must be about the square that is chosen.
    """
    app = APP.read_text("utf-8")
    panel = PANEL.read_text("utf-8")

    # The ticket, and the three places it is checked.
    assert "const ticket = asked.current + 1;" in app
    assert app.count("ticket !== asked.current") >= 2
    assert "keepAnswer(ticket, asked.current" in app
    # The old numbers go the moment a new square is picked, before the
    # request for the new ones is even sent.
    sent = app.index("`/api/place?lat=${encodeURIComponent(lat)}`")
    assert app.index("setPlace(null);") < sent

    # And the panel will not render numbers whose square is not the chosen
    # one, whatever reaches it.
    assert "sameSquare(place.square.asked, square)" in panel
    assert "if (!place || !answered)" in panel
    # SPEC 11.38 reworded it: "Reading the 51 runs for this square",
    # with the square itself on the quiet line beside it.
    assert "Reading the 51 runs for this square" in panel
    assert "{squareText(square.lat, square.lon)}" in panel


def test_the_city_a_unit_is_labelled_with_follows_the_three_times_rule():
    """SPEC 11.30. The capital, unless a neighbour has outgrown it.

    Gandhinagar is 195,891 beside Ahmedabad's 5,375,000; Dispur is 16,140
    beside Guwahati's 983,000; New Delhi is 317,797 beside Delhi's
    15,926,000. Three times is wide enough that a capital merely smaller than
    a neighbour keeps its label — Bhopal over Indore, Lucknow over Kanpur,
    Thiruvananthapuram over Kochi, Raipur over Bhilai, Ranchi over Jamshedpur.
    """
    labelled = {unit["name"]: unit["city"]["name"] for unit in load_units()}

    assert labelled["Gujarat"] == "Ahmedabad"
    assert labelled["Assam"] == "Guwahati"
    assert labelled["Delhi"] == "Delhi"

    # The ones the rule deliberately leaves alone.
    assert labelled["Madhya Pradesh"] == "Bhopal"
    assert labelled["Uttar Pradesh"] == "Lucknow"
    assert labelled["Kerala"] == "Thiruvananthapuram"
    assert labelled["Chhattisgarh"] == "Raipur"
    assert labelled["Jharkhand"] == "Ranchi"

    # Natural Earth's POP_MAX is the figure for the built-up area, which is
    # why Andhra Pradesh keeps Amaravati: 5,800,000 against
    # Vishakhapatnam's 1,529,000. The rule is applied to the field this
    # project uses for size everywhere else, not to a field chosen to move
    # one label.
    assert labelled["Andhra Pradesh"] == "Amaravati"

    # Chandigarh is a union territory of its own, so the two states it is the
    # capital of are labelled with their largest towns.
    assert labelled["Punjab"] == "Ludhiana"
    assert labelled["Haryana"] == "Faridabad"


def test_the_land_around_india_is_coastline_and_nothing_else():
    """SPEC 11.30 and the amendment to 11.14.

    Natural Earth's land layer has no border in it of any kind: it is one
    multipolygon of coastline. That is why it is the layer used. The only
    line this map draws between India and anywhere else is still the India
    point-of-view outline.
    """
    body = json.loads(LAND_FILE.read_text("utf-8"))
    about = body["properties"]

    assert about["source"] == "ne_10m_land"
    assert "coastlines only" in about["note"]
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) > 100
    for part in body["features"]:
        assert part["geometry"]["type"] == "Polygon", "fills, never lines"
        assert part["properties"] == {}, "no name, no country, no border"

    # It covers everywhere the map can be panned to, which is the box
    # web/src/Map.jsx sets as maxBounds. A coast that stopped inside that box
    # would be a shoreline that is not there.
    limits = re.search(
        r"const LIMITS = \[\[LON_MIN - (\d+), LAT_MIN - (\d+)\], "
        r"\[LON_MAX \+ (\d+), LAT_MAX \+ (\d+)\]\];",
        MAP.read_text("utf-8"))
    assert limits, "web/src/Map.jsx no longer sets LIMITS the expected way"
    west, south, east, north = (int(n) for n in limits.groups())
    assert about["box"] == [68.0 - west, 6.0 - south, 98.0 + east, 38.0 + north]

    raw = LAND_FILE.read_bytes().replace(b"\r\n", b"\n")
    assert len(gzip.compress(raw, 9)) < 40_000, "the land file is in the "\
        "map's chunk and has a budget"


@needs_node
def test_the_land_the_sea_and_a_square_no_run_reached_are_three_colours(
        exports):
    """SPEC 11.30. Neighbouring land used to be painted the sea's colour.

    Nepal, Bangladesh, Myanmar and Pakistan read as ocean, because the page
    drew no land it has no squares for. The new fill has to be told apart
    from two colours at once, and they are only so far apart: between a sea
    at 0.5445 relative luminance and a 0 class at 0.8592, the best any colour
    can do is the square root of their product, which is 1.237 from both.
    """
    zero = exports(PALETTE, "colourOf", [[0]])[0]
    palette = PALETTE.read_text("utf-8")
    assert zero == "#eceff1"
    assert "export const NEIGHBOURS = '#dcd7cb'" in palette
    assert "export const SEA = '#aec6da'" in palette
    assert "export const LAND = '#ffffff'" in palette

    land, sea, white = "#dcd7cb", "#aec6da", "#ffffff"
    assert contrast(land, sea) > 1.2, "the land against the sea"
    assert contrast(land, zero) > 1.2, "the land against the 0 class"
    # And against the white squares inside the outline that are not
    # forecast, which the legend now explains.
    assert contrast(land, white) > 1.4, "the land against a white square"
    # As near the best a colour between those two can do as makes no
    # difference.
    best = (contrast(sea, zero)) ** 0.5
    assert abs(contrast(land, sea) - best) < 0.02
    assert abs(contrast(land, zero) - best) < 0.02

    # The map paints it under India's own fill and draws no line on it.
    map_src = MAP.read_text("utf-8")
    assert "id: 'land-fill'" in map_src
    assert map_src.index("id: 'land-fill'") < map_src.index("id: 'india-fill'")
    assert "'fill-color': NEIGHBOURS" in map_src
    assert "type: 'line',\n        source: 'land'" not in map_src


def test_the_white_squares_inside_india_are_explained():
    """SPEC 11.30. A hole in the map with nothing to say what it is.

    A square inside the outline whose land fraction is under the half of
    SPEC 3.5 is not forecast, so nothing is painted and India's own white
    shows through. The legend says so in one line.
    """
    legend = LEGEND.read_text("utf-8")
    assert "White: no forecast for this spot" in legend
    # SPEC 11.39: it is one of the nine rows of the key, which the map and
    # How to read this map both draw from this one list.
    assert 'className="keywhite"' in legend
    assert "export function KeyRows()" in legend


def test_the_names_are_placed_cities_first_and_no_unit_is_left_unlabelled():
    """SPEC 11.30. The order, and the promise that comes with it.

    States first cost too much: 36 unit names took the room and eight city
    names fitted around them, on a map whose point is the places people look
    for. Cities go first now, and the price — a unit's name not fitting — is
    paid in the two letter code, never in no label at all.
    """
    map_src = MAP.read_text("utf-8")
    assert "const items = [chosen, ...cities, ...states];" in map_src
    # The last resort: a code written at the unit's own point, inside the
    # canvas, even where it has to sit on something else.
    assert "how: 'forced'" in map_src
    assert "if (!put && item.code) {" in map_src
    assert map_src.index("if (!put && item.code) {") \
        < map_src.index("if (!put) {\n        hide(item);")
def test_the_twenty_city_list_is_gone_and_nothing_looks_for_it():
    """SPEC 11.30. web/src/cities.json is deleted.

    It was replaced by one city per state and union territory in 11.29 and
    had been read by nothing since. Earlier parts of section 11 still
    describe it, which is history and stays: 11.30 records the deletion.
    """
    assert not (ROOT / "web" / "src" / "cities.json").exists()
    here = Path(__file__).resolve()
    for folder, suffixes in ((ROOT / "web" / "src", (".js", ".jsx")),
                             (ROOT / "api", (".mjs",)),
                             (ROOT / "tests", (".py",))):
        for path in folder.rglob("*"):
            # Every file but this one, which has to name it to say it is
            # gone.
            if path.suffix not in suffixes or path.resolve() == here:
                continue
            assert "cities.json" not in path.read_text("utf-8"), path

# ------------- SPEC 11.31: a unit's name is never written outside the unit

FITS = ROOT / "web" / "src" / "fits.js"
ADMIN1 = ROOT / "data" / "raw" / "ne" / "ne_10m_admin_1_states_provinces.shp"
ON_SCREEN = Path(__file__).parent / "sample" / "names_on_screen.json"

needs_admin1 = pytest.mark.skipif(
    not ADMIN1.exists(),
    reason="the Natural Earth admin-1 shapefile is not here; "
           "data/ is never committed")


def india_units() -> dict:
    """The India admin-1 polygons, by name, straight from the shapefile."""
    import shapefile
    from shapely.geometry import shape

    reader = shapefile.Reader(str(ADMIN1.with_suffix("")))
    fields = [f[0] for f in reader.fields[1:]]
    found = {}
    for item in reader.iterShapeRecords():
        record = dict(zip(fields, item.record))
        if str(record.get("admin")) != "India":
            continue
        found[str(record["name"]).strip()] = shape(
            item.shape.__geo_interface__)
    return found


def test_the_fit_table_is_there_for_every_unit_and_never_rises():
    """SPEC 11.31. The room to write a name in, one number per shape of box.

    A wider box of the same height contains a narrower one, so the room can
    only shrink as the box widens. If this list ever rose, a name could pass
    the test by claiming to be wider than it is.
    """
    body = json.loads(UNITS_FILE.read_text("utf-8"))
    aspects = body["fit"]["aspects"]
    assert aspects == [2.0, 4.0, 6.0, 9.0, 13.0, 18.0, 25.0]
    assert aspects == sorted(aspects)
    for unit in body["units"]:
        room = unit["fit"]
        assert len(room) == len(aspects), unit["name"]
        assert room[0] > 0, unit["name"]
        assert room == sorted(room, reverse=True), unit["name"]


@needs_admin1
def test_the_room_for_a_name_is_the_polygon_and_not_an_estimate_of_it():
    """SPEC 11.31. Every number in the table is a box inside the unit.

    The page cannot hold the polygons -- 3 MB of shapefile for 36 words -- so
    it holds the answer instead, and this is what makes the answer worth
    holding: for every unit and every shape of box, the box the table allows
    is inside the unit's own polygon, and a box a tenth taller is not. Tight
    from both sides, so the table can neither write a name on the neighbours
    nor refuse a name there is room for.
    """
    from shapely.geometry import box as make_box

    polygons = india_units()
    body = json.loads(UNITS_FILE.read_text("utf-8"))
    aspects = body["fit"]["aspects"]
    for unit in body["units"]:
        poly = polygons[unit["name"]]
        lon, lat = unit["lon"], unit["lat"]
        for aspect, room in zip(aspects, unit["fit"]):
            fits = make_box(lon - room * aspect, lat - room,
                            lon + room * aspect, lat + room)
            assert fits.within(poly), (unit["name"], aspect, room)
            # Tight to a tenth plus one rounding step. The step matters only
            # for the islands, whose room is a few ten-thousandths of a
            # degree: four decimal places is most of the number there.
            over = room * 1.1 + 1e-4
            bigger = make_box(lon - over * aspect, lat - over,
                              lon + over * aspect, lat + over)
            assert not bigger.within(poly), (unit["name"], aspect, room)


@needs_admin1
def test_every_name_the_map_drew_is_inside_the_unit_it_names():
    """SPEC 11.31, and the fault it is for.

    Seen on the page: HIMACHAL PRADESH written across Uttarakhand, ARUNACHAL
    PRADESH across Bhutan and Sikkim, JAMMU AND KASHMIR beginning outside the
    country, UTTARAKHAND hanging over Nepal. A name on the wrong state is not
    an untidy label, it is a false statement about where a place is, on a map
    whose only subject is where things are.

    tests/sample/names_on_screen.json is every unit name the built page
    actually drew, with the box it drew it in, at the desktop default view,
    the phone default view and a view three zoom steps in. Only a browser
    knows how wide a word came out, so the boxes are recorded from the page;
    what they are checked against is the polygon itself.
    """
    from shapely.geometry import box as make_box

    polygons = india_units()
    body = json.loads(ON_SCREEN.read_text("utf-8"))
    views = {view["view"]: view for view in body["views"]}
    assert "desktop default" in views and "phone default" in views
    drawn = 0
    for view in body["views"]:
        assert [one["name"] for one in view["boxes"]] == view["names"], view
        for one in view["boxes"]:
            poly = polygons[one["name"]]
            assert make_box(*one["box"]).within(poly), (view["view"], one)
            drawn += 1
        # Every unit is labelled somehow, at both views a reader starts at.
        if view["view"].endswith("default"):
            counts = view["counts"]
            assert (counts["full"] + counts["coded"] + counts["forced"]
                    == 36), view
    # A rule that drew nothing anywhere would pass the loop above. Zoomed in,
    # names are drawn, and those are the ones with something to prove.
    assert drawn >= 3


@needs_node
def test_a_name_is_drawn_only_when_it_is_provably_inside(exports):
    """SPEC 11.31. The lookup is conservative in every direction.

    The shape asked about is rounded up to the first shape measured, so the
    box tested is never narrower than the box drawn; anything wider than the
    widest shape measured has no answer, so the answer is no.
    """
    body = json.loads(UNITS_FILE.read_text("utf-8"))
    aspects = body["fit"]["aspects"]
    unit = next(u for u in body["units"] if u["name"] == "Rajasthan")
    room = unit["fit"]

    # Rounded up: a box of shape 5 is tested against the entry for 6.
    said = exports(FITS, "roomFor",
                   [[aspects, room, 5], [aspects, room, 6],
                    [aspects, room, 6.0001], [aspects, room, 1],
                    [aspects, room, 25], [aspects, room, 25.0001],
                    [aspects, room, 0], [aspects, room, -3]])
    assert said[0] == room[2] == said[1]
    assert said[2] == room[3]
    assert said[3] == room[0]
    assert said[4] == room[-1]
    assert said[5] == 0            # wider than anything measured
    assert said[6] == 0 and said[7] == 0

    # At the limit and a hair over it, for a box of exactly a measured shape.
    tall = room[2]
    said = exports(FITS, "fitsInside",
                   [[aspects, room, tall * 6, tall],
                    [aspects, room, tall * 6, tall * 1.001],
                    [aspects, room, tall * 25.1, tall / 4],
                    [aspects, room, 0, tall],
                    [aspects, room, tall * 6, 0],
                    [aspects, room, None, tall],
                    [aspects, [], tall * 6, tall],
                    [[], room, tall * 6, tall]])
    assert said == [True, False, False, False, False, False, False, False]


def test_the_map_offers_a_unit_s_name_one_place_and_only_one():
    """SPEC 11.31. Centre, inside, or the two letter code.

    The old rule let a name hang over the unit by its own width on each side
    and nudged it eight or sixteen pixels to dodge a clash, which at the
    whole-India view is half a degree -- the width of a small state. Both are
    gone: a name has one placement, the middle of the unit, and it is drawn
    there only if the box is inside the unit's own polygon.
    """
    text = (ROOT / "web" / "src" / "Map.jsx").read_text("utf-8")
    assert "const NAME_TRIES = [['centre', 0]];" in text
    assert "NAME_OVERHANG" not in text
    assert "item.span" not in text and "unit.span" not in text
    # The name is offered to the placement loop only after the box test.
    assert "if (nameInside(map, at, item)) {" in text
    assert "import { fitsInside, roomFor } from './fits';" in text
    # The code may still look around: it is two letters and it is not a name
    # for anybody else.
    assert ("words.push([item.code, item.codeW, 'coded', CODE_TRIES, 1]);"
            in text)
def test_a_colour_swatch_is_not_a_control():
    """SPEC 11.31. Seen on the page: swatches that look like tick boxes.

    A 0.95rem square with a hairline border and a 2px radius is what an empty
    checkbox looks like in every browser there is, and the one in the panel
    sits inside a row that really is a radio button. They are spans with no
    handler and nothing focusable in them, and now they do not look like
    controls either: wider than they are tall, square cornered, and
    `pointer-events: none` so a click goes to whatever is behind them.
    """
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    base = css.split("\n.swatch {")[1].split("}")[0]
    assert "border-radius: 0;" in base
    assert "pointer-events: none;" in base
    width = float(base.split("width: ")[1].split("rem")[0])
    height = float(base.split("height: ")[1].split("rem")[0])
    assert width >= height * 2, (width, height)
    # The one round swatch is the key to the round dots, and says so.
    assert (".dotkey .swatch { width: 0.8rem; height: 0.8rem; "
            "border-radius: 50%; }") in css

    # Three in the key -- a class, the white and the beige, which is the
    # one list the map and How to read this map both draw -- and two in
    # the card. Every one of them, wherever they are, is a hidden span
    # with nothing pressable near it.
    for name, many in (("Legend.jsx", 3), ("Panel.jsx", 2)):
        text = (ROOT / "web" / "src" / name).read_text("utf-8")
        parts = text.split('className="swatch"')
        assert len(parts) == many + 1, name
        # Every swatch is hidden from the reading order. SPEC 11.39 adds
        # two more hidden spans to the key -- the colour strip and the two
        # end labels, both of which the nine rows say in words -- so this
        # is a floor and the loop below is what checks each swatch.
        assert text.count('aria-hidden="true"') >= many, name
        for before, after in zip(parts[:-1], parts[1:]):
            # A span, hidden from the reading order, with nothing that can be
            # pressed or tabbed to anywhere near it.
            assert before.rstrip().endswith("<span"), name
            assert "aria-hidden=\"true\"" in after[:120], name
            assert "tabIndex" not in after[:200], name
            assert "onClick" not in after[:200], name

# --------------------------- SPEC 11.25: the page can be hand checked at all

def test_the_hand_check_flag_reaches_the_canvas():
    """SPEC 11.25. ?handcheck=1 must actually turn the read-back on.

    It did not. MapLibre 6 takes the WebGL attributes as one
    `canvasContextAttributes` object and ignores a top level
    `preserveDrawingBuffer` **in silence**, which is how this was written
    first: the flag changed nothing, every pixel HC8 read back was
    transparent black, and the one check that looks at what a reader looks
    at could not run. Nothing in the page breaks when this regresses, so a
    test holds it instead.
    """
    text = (ROOT / "web" / "src" / "Map.jsx").read_text("utf-8")
    assert "canvasContextAttributes: {" in text
    inside = text.split("canvasContextAttributes: {")[1].split("}")[0]
    assert "preserveDrawingBuffer: Boolean(handcheck)" in inside
    # Not as a sibling of `container` and `style`, where it does nothing.
    # Comments are dropped first: this one is explained at length in a
    # comment right above it, and a test that reads comments reads nothing.
    code = "\n".join(line for line in text.split("\n")
                     if not line.strip().startswith("//"))
    options = code.split("new maplibregl.Map({")[1].split("});")[0]
    assert options.count("preserveDrawingBuffer") == 1
    assert "canvasContextAttributes: {" in options
    # And the page says what it got, so HC8 can refuse to believe a pixel
    # that was never preserved.
    assert "preserveDrawingBuffer: Boolean(created.getCanvas()" in text

    pinned = json.loads(
        (ROOT / "web" / "package.json").read_text("utf-8"))
    assert pinned["dependencies"]["maplibre-gl"].startswith("6.")
def test_the_page_says_what_the_hand_check_has_to_assert():
    """SPEC 11.25. HC8 asserts the two conditions rather than assuming them.

    A sampled pixel equals an unblended palette hex only while the basemap
    slot is empty and the squares are drawn at full opacity, and only if no
    layer of NOT_DATA_LAYERS is painting over the square being sampled. The
    hand check cannot see the source, so the live page says all of it.
    """
    text = (ROOT / "web" / "src" / "Map.jsx").read_text("utf-8")
    facts = text.split("mapFacts = () => {")[1].split("\n    };")[0]
    for said in ("basemapSlot", "slotOpacity", "squareOpacity", "picked",
                 "notData", "gridFromZoom", "preserveDrawingBuffer"):
        assert said in facts, said
    # Read-only: nothing in there sets anything.
    for wrote in ("setPaintProperty", "setData", "addLayer", "removeLayer",
                  "setStyle", "jumpTo", "easeTo", "flyTo"):
        assert wrote not in facts, wrote

    check = (ROOT / "handchecks" / "hc8_map_square.py").read_text("utf-8")
    # The palette is copied out in the hand check, not imported from the
    # page: a second opinion is only an opinion if it is a second one.
    assert "from pipeline" not in check and "import pipeline" not in check
    for _, _, label, colour in [
            (0, 0, "0", "#eceff1"), (1, 10, "1-10", "#c7e9b4"),
            (11, 20, "11-20", "#7fcdbb"), (21, 30, "21-30", "#41b6c4"),
            (31, 40, "31-40", "#1d91c0"), (41, 50, "41-50", "#225ea8"),
            (51, 51, "51", "#0c2c84")]:
        assert f'"{label}", "{colour}"' in check, label

# ------------------ SPEC 11.32: the square you chose is the square you see

INVIEW = ROOT / "web" / "src" / "inview.js"


@needs_node
def test_a_square_in_view_is_left_alone_and_one_off_screen_is_brought_back(
        exports):
    """SPEC 11.32. The map moves when it has to and never when it does not.

    The box is the desktop map of 11.31: 1,060 by 572, all of it on the
    screen. A square in the middle of it is already in view, so the answer
    is to stay put; a square off the edge of it, or within the 40 pixel
    margin, is brought back in -- and the answer says how far to pan, so the
    test can check the square really ends up inside the margin and not on it.
    """
    box = {"left": 0, "top": 0, "right": 1060, "bottom": 572}
    said = exports(INVIEW, "nudge", [
        [{"x": 530, "y": 286}, box],       # the middle of the map
        [{"x": 41, "y": 41}, box],         # a pixel inside the margin
        [{"x": 1019, "y": 531}, box],      # a pixel inside the far margin
        [{"x": -200, "y": 286}, box],      # off the left edge entirely
        [{"x": 1400, "y": 900}, box],      # off the bottom right corner
        [{"x": 20, "y": 286}, box],        # inside the margin, still on it
    ])
    assert said[0] is None, "a square in the middle must not move the map"
    assert said[1] is None and said[2] is None, "40 pixels in is in view"
    assert said[3] is not None and said[4] is not None

    # Where the square ends up: inside the margin, by the resting distance.
    for at, answer in [({"x": -200, "y": 286}, said[3]),
                       ({"x": 1400, "y": 900}, said[4]),
                       ({"x": 20, "y": 286}, said[5])]:
        x = at["x"] - answer[0]
        y = at["y"] - answer[1]
        assert 40 <= x <= 1060 - 40, (at, answer, x)
        assert 40 <= y <= 572 - 40, (at, answer, y)
    # Off the left edge, the pan is sideways only: nothing moves that need
    # not move.
    assert said[3][1] == 0


@needs_node
def test_a_map_too_small_for_a_margin_still_centres_the_square(exports):
    """SPEC 11.32. The answer is never "nowhere to put it".

    With the sheet open the map can be shorter than two margins. Rather than
    give up, or pick an edge, the square goes in the middle of what there is.
    """
    thin = {"left": 0, "top": 0, "right": 390, "bottom": 60}
    said = exports(INVIEW, "nudge", [[{"x": 195, "y": 55}, thin]])[0]
    assert said is not None
    assert 55 - said[1] == 30


def test_the_map_pans_when_a_square_is_chosen_and_not_otherwise():
    """SPEC 11.32. The ease, the zoom, and the reader who asked for less.

    `panBy` and not `flyTo` or `fitBounds`: the zoom is the reader's, or the
    fit's, and a map that changes scale every time a town is searched for is
    a worse map than one that pans. 600 ms, and no journey at all for a
    reader who has asked for reduced motion.
    """
    text = (ROOT / "web" / "src" / "Map.jsx").read_text("utf-8")
    code = "\n".join(line for line in text.split("\n")
                     if not line.strip().startswith("//"))
    assert "created.panBy(offset, { duration: still ? 0 : EASE_MS });" in code
    assert "prefers-reduced-motion: reduce" in code
    # It is the chosen square that is brought into view, and it runs when
    # that square changes and on nothing else.
    assert "created.project([square.lon, square.lat])" in code
    assert "}, [square]);" in code
    # Nothing here changes the zoom.
    piece = code.split("useEffect(() => {\n    const created = map.current;"
                       "\n    if (!created || !square")[1].split("}, [square]")[0]
    for zoomy in ("setZoom", "zoomTo", "fitBounds", "flyTo", "jumpTo",
                  "easeTo"):
        assert zoomy not in piece, zoomy

    inview = INVIEW.read_text("utf-8")
    assert "export const EDGE = 40;" in inview
    assert "export const EASE_MS = 600;" in inview


# ------------------------- SPEC 11.33: the trust label in the place panel
#
# The record is frozen (tag results-v1) and the page must say exactly what is
# in it. So the expectations below are written out again from
# results/site_summary.json rather than imported from web/src/record.js: if
# the page's wording and the file ever disagree, one of these fails.

RECORD = ROOT / "results" / "site_summary.json"
BUNDLED = ROOT / "web" / "src" / "summary.json"
REGIONS = ROOT / "config" / "regions.json"
MASK = ROOT / "config" / "india_mask.json"

# The harness of 11.24 cannot be used here: it passes the arguments to every
# call, and the summary is 94,000 bytes. This one reads the summary once and
# puts it in front of every call, so 3,120 calls cost one copy.
RECORD_HARNESS = """
import { readFileSync } from 'node:fs';
const [file, summaryFile, argsFile] = process.argv.slice(2);
const mod = await import(file);
const summary = JSON.parse(readFileSync(summaryFile, 'utf8'));
const calls = JSON.parse(readFileSync(argsFile, 'utf8'));
process.stdout.write(JSON.stringify(calls.map(
  (call) => mod[call[0]](summary, ...call.slice(1)))));
"""

TOO_FEW = ("Too few past cases with this many runs agreeing to say how often "
           "the satellite saw it.")

# SPEC 11.33, the four checks said as what went wrong, in 6.2's order.
MISSED = (
    ("enough_data", "too few past cases"),
    ("skill_above_zero",
     "not clearly better than the usual rain for this place and month"),
    ("range_narrow_enough", "too uncertain to tell"),
    ("small_honesty_error",
     "the counts were too confident: when many runs agreed, the satellite "
     "saw it less often"),
)
SKILL_PASSED = "Better than the usual rain for this place and month, but "
MEMBERS = 51
COUNTS = list(range(MEMBERS + 1))


@pytest.fixture()
def record(tmp_path):
    """Call record.js with one summary in front of every call."""
    harness = tmp_path / "record.mjs"
    harness.write_text(RECORD_HARNESS, encoding="utf-8")
    args = tmp_path / "record-args.json"

    def run(calls: list[list], summary: Path = BUNDLED) -> list:
        args.write_text(json.dumps(calls), encoding="utf-8")
        done = subprocess.run(
            [node, str(harness),
             (ROOT / "web" / "src" / "record.js").as_uri(),
             str(summary), str(args)],
            capture_output=True, text=True, encoding="utf-8", check=False)
        assert done.returncode == 0, f"node failed: {done.stderr}"
        return json.loads(done.stdout)

    return run


def summary_file() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def bucket_of(group: dict, count: int) -> dict | None:
    """The counted bucket holding this count. Only counted ones are here."""
    for bucket in group["buckets"]:
        if bucket["k_from"] <= count <= bucket["k_to"]:
            return bucket
    return None


def expected_past(group: dict, count: int) -> str:
    """The sentence of SPEC 11.33, written out again."""
    bucket = bucket_of(group, count)
    if bucket is None:
        return TOO_FEW
    low, high = bucket["k_from"], bucket["k_to"]
    if low == high == 0:
        many = f"none of the {MEMBERS} runs"
    elif low == high == MEMBERS:
        many = f"all {MEMBERS} runs"
    elif low == high:
        many = f"{low} of {MEMBERS} runs"
    else:
        many = f"{low} to {high} of {MEMBERS} runs"
    times = bucket["times_in_10"]
    if times <= 0:
        often = "fewer than 1 time in 10"
    elif times >= 10:
        often = "nearly every time"
    else:
        often = f"about {times} {'time' if times == 1 else 'times'} in 10"
    threshold = group["threshold_mm"]
    amount = int(threshold) if float(threshold).is_integer() else threshold
    return (f"In May to November 2026, when {many} said {amount} mm or more "
            f"in {group['region']} on day {group['lead_day']}, the satellite "
            f"saw it {often}.")


def expected_reason(group: dict, count: int) -> str:
    """SPEC 11.38's chip reason, written out again rather than imported."""
    bucket = bucket_of(group, count)
    if bucket is None:
        return TOO_FEW
    times = bucket["times_in_10"]
    if times <= 0:
        often = "fewer than 1 time in 10"
    elif times >= 10:
        often = "nearly every time"
    else:
        often = f"about {times} {'time' if times == 1 else 'times'} in 10"
    threshold = group["threshold_mm"]
    amount = int(threshold) if float(threshold).is_integer() else threshold
    return (f"When the runs said this before in {group['region']}, the "
            f"satellite saw rain of {amount} mm or more {often}.")


BETTER = "This is better than the usual rain for this place and month."


@needs_node
def test_the_chip_reason_is_the_track_record(record):
    """SPEC 11.38. Every group, every count, against the rule rewritten.

    The chip used to be followed by the name of whichever of the four
    checks the group failed, which is a sentence about our method. What a
    first-time reader can use is what the record measured: when the runs
    said this here before, how often did the satellite see it?

    Driven through `trustFor`, which is what the panel calls, so what is
    checked is the sentence the panel is handed.
    """
    summary = summary_file()
    calls = []
    wanted = []
    for group in summary["groups"]:
        for count in COUNTS:
            calls.append(["trustFor", group["region"], group["lead_day"],
                          group["threshold_mm"], count, MEMBERS])
            wanted.append(expected_reason(group, count))
    assert len(calls) > 3000, len(calls)
    got = [answer["reason"] for answer in record(calls)]
    assert got == wanted

    # "the satellite saw rain", never "it rained" (SPEC 5.9), and never a
    # forbidden word, over every group and count there is.
    for said in wanted:
        low = said.lower()
        assert "it rained" not in low, said
        for word in FORBIDDEN:
            assert word not in low, (word, said)


@needs_node
def test_the_good_sentence_is_said_only_where_the_check_passed(record):
    """SPEC 11.38. One sentence, and only for the groups that earned it."""
    summary = summary_file()
    calls = [["trustFor", group["region"], group["lead_day"],
              group["threshold_mm"], 25, MEMBERS]
             for group in summary["groups"]]
    got = [answer["better"] for answer in record(calls)]
    passed = 0
    for group, said in zip(summary["groups"], got):
        if group["conditions"]["skill_above_zero"]["pass"]:
            assert said == BETTER, group["region"]
            passed += 1
        else:
            assert said is None, group["region"]
    # A test that never saw the sentence would pass whatever it said.
    assert passed > 0, "no group passed the skill check, so nothing was shown"
    assert passed < len(got), "every group passed, so nothing was withheld"


def expected_why(group: dict) -> str:
    """The one line under the chip, SPEC 11.33, written out again."""
    missed = [words for key, words in MISSED
              if not group["conditions"][key]["pass"]]
    if not missed:
        return "All four checks passed."
    joined = missed[0] if len(missed) == 1         else f"{', '.join(missed[:-1])}, and {missed[-1]}"
    if group["conditions"]["skill_above_zero"]["pass"]:
        return f"{SKILL_PASSED}{joined}."
    return joined[0].upper() + joined[1:] + "."


def every_group_and_count() -> list[list]:
    groups = summary_file()["groups"]
    return [["trustFor", group["region"], group["lead_day"],
             group["threshold_mm"], count, MEMBERS]
            for group in groups for count in COUNTS]


def strings_in(value) -> list[str]:
    """Every string anywhere in an answer, for the wording checks."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings_in(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings_in(item)]
    return []


@needs_node
def test_every_square_gets_the_region_config_gives_it(exports):
    """SPEC 11.33. api/place answers from config/regions.json and nothing else.

    All 15,609 squares of the India box, not a sample: the 4,613 inside India
    get their own region, and every other square gets null, because there is
    no record to show for the sea.
    """
    rows = json.loads(REGIONS.read_text(encoding="utf-8"))
    names = rows["codes"]
    grid = rows["region_rows"]
    points = [[38.0 - 0.25 * i, 68.0 + 0.25 * j]
              for i in range(129) for j in range(121)]
    assert len(points) == 15609

    got = exports(ROOT / "api" / "place.mjs", "regionOf", points)
    india = 0
    for (lat, lon), answer in zip(points, got):
        i = round((38.0 - lat) / 0.25)
        j = round((lon - 68.0) / 0.25)
        code = int(grid[i][j])
        if code == 0:
            assert answer is None, (lat, lon, answer)
        else:
            assert answer == {"code": code, "region": names[str(code)]}, \
                (lat, lon, answer)
            india += 1
    assert india == 4613, india

    # And those 4,613 are exactly the squares the site publishes (SPEC 3.5),
    # so no square the page can show has no label to show with it.
    mask = json.loads(MASK.read_text(encoding="utf-8"))["india_rows"]
    for i, row in enumerate(mask):
        for j, here in enumerate(row):
            assert (here == "1") == (grid[i][j] != "0"), (i, j)


@needs_node
def test_the_twelve_places_of_five_four_land_in_their_own_region(exports):
    """The place tests config/regions.json was built against, through the API.

    build_regions.py checks them when it writes the file. This checks the
    function the website actually asks, which is a different program reading
    the same file.
    """
    places = json.loads(REGIONS.read_text(encoding="utf-8"))["place_tests"]
    assert len(places) == 12
    points = [[place["lat"], place["lon"]] for place in places.values()]
    got = exports(ROOT / "api" / "place.mjs", "regionOf", points)
    for (name, place), answer in zip(places.items(), got):
        assert answer is not None, name
        assert answer["region"] == place["region"], (name, answer)


@needs_node
def test_the_api_answers_with_the_square_s_region(store, harness, exports):
    """Every square the store holds comes back with its region beside it."""
    squares = india_squares(store)
    got = exports(ROOT / "api" / "place.mjs", "regionOf",
                  [[lat, lon] for lat, lon in squares])
    for (lat, lon), region in zip(squares, got):
        answer = call(harness, "place", f"?lat={lat}&lon={lon}",
                      store["base"])["json"]
        assert "region" in answer["square"], answer["square"]
        if region is None:
            # This fixture's grid sits in the far north west, outside India
            # on the real mask, so the honest answer is no region at all.
            assert answer["square"]["region"] is None
            assert answer["square"]["region_code"] is None
        else:
            assert answer["square"]["region"] == region["region"]
            assert answer["square"]["region_code"] == region["code"]


@needs_node
def test_the_label_and_the_sentence_are_the_record_for_every_count(record):
    """SPEC 11.33, all 60 groups at all 52 counts: 3,120 answers checked.

    The label, its colour, the past-frequency sentence and the four condition
    lines all have to be what results/site_summary.json says, because the page
    is not allowed to work any of them out for itself.
    """
    groups = summary_file()["groups"]
    rules = summary_file()["rules"]
    calls = every_group_and_count()
    answers = record(calls)
    assert len(answers) == 60 * 52 == len(calls)

    seen_too_few = 0
    for (group, count), got in zip(
            [(group, count) for group in groups for count in COUNTS],
            answers):
        where = (group["region"], group["lead_day"], group["threshold_mm"],
                 count)
        assert got["label"] == group["label"], where
        assert got["colour"] == group["colour"], where
        assert got["past"] == expected_past(group, count), where
        if got["past"] == TOO_FEW:
            seen_too_few += 1

        names = [line["name"] for line in got["conditions"]]
        assert names == [
            "Enough past cases",
            "Better than the usual rain for this place and month",
            "A narrow enough range",
            "Counts that matched what happened"], where
        assert got["label"] != "Good track record" or "but" not in got["why"]
        passed = [line["pass"] for line in got["conditions"]]
        assert passed == [group["conditions"][key]["pass"] for key in (
            "enough_data", "skill_above_zero", "range_narrow_enough",
            "small_honesty_error")], where

        data = group["conditions"]["enough_data"]
        assert f"{data['dates']} start dates" in got["conditions"][0]["got"]
        assert f"{data['event_dates']} of them" in got["conditions"][0]["got"]
        assert str(rules["min_dates"]) in got["conditions"][0]["rule"]
        assert f"{group['bss']:.2f}" in got["conditions"][1]["got"] \
            or f"{group['bss']:.2f}".lstrip("-") in got["conditions"][1]["got"]
        worst = group["conditions"]["small_honesty_error"]["worst_error"]
        assert f"{worst:.2f}" in got["conditions"][3]["got"], where

        # The line under the chip names the checks that were not passed,
        # and the half that was passed where there is one.
        assert got["why"] == expected_why(group), where

    assert seen_too_few > 0, "no group has an uncounted band, so the floor " \
        "of 6.4 was never exercised"


@needs_node
def test_the_sentence_is_withheld_exactly_where_the_bucket_is_not_counted(
        record):
    """SPEC 6.4's floor governs what is said out loud, not only what is tested.

    Seven of the 60 groups -- all of them 50 mm -- have no counted band above
    some count, because fifty millimetres in a day from 30 or more agreeing
    runs did not happen a hundred times in six months. Those counts get the
    plain line and no number at all.
    """
    groups = summary_file()["groups"]
    answers = record(every_group_and_count())
    thin = 0
    for (group, count), got in zip(
            [(group, count) for group in groups for count in COUNTS],
            answers):
        counted = bucket_of(group, count) is not None
        assert (got["past"] != TOO_FEW) == counted, (group["region"], count)
        if not counted:
            thin += 1
            assert "times in 10" not in got["past"]
            assert "about" not in got["past"]
    assert thin > 100, thin


@needs_node
def test_no_share_of_ten_appears_until_a_label_is_green(record, tmp_path):
    """SPEC 6.7. A percentage is earned by the record, not printed by default.

    No group is green today, so nothing on the site may read as a share of
    ten. The rule for the day one is green is tested against a made-up green
    group, so it is already right then.
    """
    answers = record(every_group_and_count())
    for got in answers:
        assert got["percent"] is None, got["label"]
        for text in strings_in(got):
            assert "%" not in text, text
            assert "percent" not in text.lower(), text

    # The same file with one group made green, and nothing else touched.
    doctored = summary_file()
    green = doctored["groups"][0]
    green["label"] = "Good track record"
    green["colour"] = "green"
    for condition in green["conditions"].values():
        condition["pass"] = True
    path = tmp_path / "green.json"
    path.write_text(json.dumps(doctored), encoding="utf-8")

    got = record([["trustFor", green["region"], green["lead_day"],
                   green["threshold_mm"], count, MEMBERS]
                  for count in (0, 20, 26, 51)], summary=path)
    assert [answer["percent"] for answer in got] == [
        "about 0 in 10", "about 4 in 10", "about 5 in 10", "about 10 in 10"]
    assert got[1]["why"] == "All four checks passed."
    for answer in got:
        assert "%" not in json.dumps(answer)


@needs_node
def test_the_trust_wording_never_says_dry_or_likely(record):
    """SPEC 11.20's forbidden list, over everything the label can say.

    The sentence under the counts was held to this from the first day. The
    track record says more, so it has more ways to slip: "risk", "likely",
    "chance", a percentage. Every string of all 3,120 answers is checked,
    which is the labels, the lines, the four conditions and the notes.
    """
    answers = record(every_group_and_count())
    checked = 0
    for got in answers:
        for text in strings_in(got):
            low = text.lower()
            for word in FORBIDDEN:
                if word == "certain":
                    # SPEC 11.33. The ban is on the claim "certain". "too
                    # uncertain to tell" is the opposite of that claim -- a
                    # confession that the range is too wide to say anything --
                    # so the whole word is what is forbidden, not the letters.
                    assert not re.search(r"\bcertain\b", low), text
                    continue
                assert word not in low, f"{word} appears in: {text}"
            checked += 1
    assert checked > 10000, checked

    # And the one thing it must always say rather than "it rained" (SPEC 5.9).
    said = [got["past"] for got in answers if got["past"] != TOO_FEW]
    assert len(said) > 2000
    for sentence in said:
        assert "the satellite saw it" in sentence
        assert "it rained" not in sentence
        assert sentence.startswith("In May to November 2026, when ")


@needs_node
def test_the_two_ends_of_the_rounded_share_are_said_in_words(
        record, exports, tmp_path):
    """SPEC 11.33. 0 is not never and 10 is not always.

    A band rounded to 0 times in 10 holds hundreds of cases in which it did
    happen -- 1.2 in 100 in the real record's driest band -- and "about 0
    times in 10" reads as a promise that it never happens. 10 reads as a
    promise that it always does. Both ends say what the rounding is.
    """
    ends = exports(ROOT / "web" / "src" / "record.js", "howOften",
                   [[{"times_in_10": times}] for times in (0, 1, 2, 9, 10)])
    assert ends == ["fewer than 1 time in 10", "about 1 time in 10",
                    "about 2 times in 10", "about 9 times in 10",
                    "nearly every time"]

    # The real record reaches 0 but never 10, so the top end is driven with a
    # band moved there by hand, and the whole sentence checked around it.
    groups = summary_file()["groups"]
    low = [expected_past(group, count) for group in groups for count in COUNTS]
    assert sum("fewer than 1 time in 10" in said for said in low) > 100
    assert not any("nearly every time" in said for said in low)

    doctored = summary_file()
    group = doctored["groups"][0]
    group["buckets"][-1]["times_in_10"] = 10
    path = tmp_path / "high.json"
    path.write_text(json.dumps(doctored), encoding="utf-8")
    got = record([["trustFor", group["region"], group["lead_day"],
                   group["threshold_mm"], 51, MEMBERS]], summary=path)
    assert got[0]["past"].endswith("the satellite saw it nearly every time.")
    assert "about 10" not in got[0]["past"]


@needs_node
def test_the_line_under_the_chip_says_both_halves_when_there_are_two(record):
    """SPEC 11.33. A group that beat the usual rain and is still amber.

    Twenty of the sixty did: their skill range is wholly above 0 and they fail
    only on the honesty check. Saying only what went wrong would describe a
    worse record than the one we measured, so the line says both. The other
    forty did not beat it, and their line names only the failed checks.
    """
    groups = summary_file()["groups"]
    answers = record([["trustFor", group["region"], group["lead_day"],
                       group["threshold_mm"], 25, MEMBERS]
                      for group in groups])
    both, failed_only = 0, 0
    for group, got in zip(groups, answers):
        where = (group["region"], group["lead_day"], group["threshold_mm"])
        assert got["why"] == expected_why(group), where
        if group["conditions"]["skill_above_zero"]["pass"]:
            both += 1
            assert got["why"].startswith(
                "Better than the usual rain for this place and month, but "
                "the counts were too confident:"), where
            assert "not clearly better" not in got["why"], where
        else:
            failed_only += 1
            assert got["why"].startswith(
                "Not clearly better than the usual rain"), where
            assert ", but " not in got["why"], where
        assert got["why"].endswith("."), where
    assert (both, failed_only) == (20, 40), (both, failed_only)

    # Every line is built from the four fixed phrases and nothing else.
    for group, got in zip(groups, answers):
        for key, words in MISSED:
            said = words in got["why"]
            missed = not group["conditions"][key]["pass"]
            if key != "skill_above_zero":
                assert said == missed, (group["region"], key)


@needs_node
def test_a_run_with_other_than_fifty_one_members_is_given_no_sentence(record):
    """SPEC 11.33. The bands are counts out of 51 (SPEC 2.1).

    If a run ever publishes a different number of members, "36 to 40 of 51
    runs" is no longer the question this forecast answers, and the honest
    thing is to say nothing rather than something close.
    """
    group = summary_file()["groups"][0]
    args = [group["region"], group["lead_day"], group["threshold_mm"]]
    got = record([["trustFor", *args, 38, members]
                  for members in (51, 50, 20, 0)])
    assert got[0]["past"].startswith("In May to November 2026")
    for answer in got[1:3]:
        assert answer["past"] is None, answer["past"]
    assert got[3] is not None and got[3]["past"] is None


def test_the_site_reads_one_file_and_it_is_the_frozen_one():
    """SPEC 11.33. One copy in the build, and never the big files."""
    assert BUNDLED.read_bytes() == RECORD.read_bytes()
    assert len(BUNDLED.read_bytes()) < 100_000

    src = ROOT / "web" / "src"

    def importers(name: str) -> list[str]:
        # sorted, because glob's order is the filesystem's and this test
        # has to say the same thing on Windows and on the CI runner.
        return sorted(path.name for path in src.glob("*.js*")
                      if f"from './{name}'" in path.read_text(
                          encoding="utf-8"))

    # SPEC 11.34. The summary is in the bundle already, so the report card
    # reads it directly; the 126 KB of working is imported by How we checked
    # and by nothing else, which is what keeps it in that page's own chunk.
    assert importers("summary.json") == [
        "HowWeChecked.jsx", "ReportCard.jsx", "ssr.jsx", "trust.js"]
    assert importers("details.json") == ["HowWeChecked.jsx"]
    assert BUNDLED_DETAILS.read_bytes() == DETAILS.read_bytes()

    # And in the built site: the working is in a chunk of its own, not in
    # the entry every reader downloads.
    dist = ROOT / "web" / "dist" / "assets"
    if dist.exists():
        mark = json.loads(
            DETAILS.read_text(encoding="utf-8"))["meta"]["spec_sha256"]
        carry = sorted(path.name for path in dist.glob("*.js")
                       if mark in path.read_text(encoding="utf-8",
                                                 errors="ignore"))
        assert carry == ["HowWeChecked-" + carry[0].split("-", 1)[1]], carry
    # The two big result files are named in a comment and imported nowhere:
    # the whole of the record the browser is sent is summary.json.
    loaded = sorted({name for path in src.glob("*.js*")
                     for name in re.findall(r"from '\./([\w./]+\.json)'",
                                            path.read_text(encoding="utf-8"))})
    assert loaded == ["details.json", "geo/india.geo.json",
                      "geo/land.geo.json", "geo/states.geo.json",
                      "summary.json", "towns.json", "units.json"], loaded

    # record.js is the thinking and has no imports, so node can drive it
    # against the real file, which is what the tests above do.
    source = (src / "record.js").read_text(encoding="utf-8")
    assert "\nimport " not in source
    assert "require(" not in source


def test_the_panel_shows_the_chip_the_sentence_and_the_expander():
    """SPEC 11.33, as SPEC 11.38 leaves it."""
    panel = PANEL.read_text(encoding="utf-8")

    # The region is the API's, not the page's: the panel reads it off the
    # answer and never works it out.
    assert "place.square.region" in panel
    assert "region_rows" not in panel

    # SPEC 11.38: one chip, not four. It was drawn once per amount row and
    # once more under them, which is a wall of "Rough guide" and not a
    # label.
    assert "<Chip trust={trust} small />" not in panel
    assert panel.count("<Chip trust={trust} />") == 1
    assert "<summary>Why this label?</summary>" in panel
    assert ("<TrustBlock place={place} day={chosen} threshold={threshold}"
            in panel)
    # SPEC 11.39. Which of the four checks it was, and the long sentence,
    # are both inside More detail: one is a paragraph about our method and
    # the other names the period, the band, the region and the day number.
    # The chip's own line carries the reason and the link and nothing else.
    assert panel.count('className="pastline"') == 1
    why = panel.split("export function TrustWhy")[1].split(
        "export function MoreDetail")[0]
    assert 'className="pastline"' in why
    assert '<summary>Why this label?</summary>' in why
    # SPEC 11.40. The section is controlled now, so that its handle can
    # read "Hide detail" while it is open: the component is what is split
    # on rather than the opening tag.
    more = panel.split("export function MoreDetail")[1]
    assert "<TrustWhy trust={trust} />" in more
    assert "{open ? 'Hide detail' : 'More detail'}" in more

    # Nothing in the panel decides a label or a frequency.
    for word in ("Good track record", "Treat as a rough guide",
                 "Not enough past data", "times in 10", "bss", "Math.round"):
        assert word not in panel, word

    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
    # SPEC 11.39. The card has three text sizes and they are the same three
    # at every width, so the sentence and the count it is under are the
    # same size by construction and there is no narrow-screen copy of
    # either rule to keep in step.
    row = css.split("\n.countrow {")[1].split("}")[0]
    past = css.split("\n.pastline {")[1].split("}")[0]
    assert "font-size: var(--card-md);" in row
    assert "font-size: var(--card-sm);" in past
    for token in ("--card-lg:", "--card-md:", "--card-sm:"):
        assert token in css, token
    # Three chips, three colours, each one a word as well as a colour.
    for colour in ("green", "amber", "grey"):
        assert f".chip.{colour} {{" in css


# ------------- SPEC 11.34: the report card and How we checked
#
# Two kinds of check. The pages' own functions are driven against the two
# files, as the panel's are; and both pages are rendered to HTML by React's
# own server renderer, for every choice a reader can make, so what is checked
# is the page itself rather than a description of it.

DETAILS = ROOT / "results" / "site_details.json"
BUNDLED_DETAILS = ROOT / "web" / "src" / "details.json"
VERIFICATION = ROOT / "results" / "verification.json"
DETAILS_LIMIT = 150_000

PAGES_HARNESS = """
import { readFileSync } from 'node:fs';
const [file, summaryFile, detailsFile, argsFile] = process.argv.slice(2);
const mod = await import(file);
const summary = JSON.parse(readFileSync(summaryFile, 'utf8'));
const details = JSON.parse(readFileSync(detailsFile, 'utf8'));
const files = { summary, details };
const calls = JSON.parse(readFileSync(argsFile, 'utf8'));
process.stdout.write(JSON.stringify(calls.map(
  (call) => mod[call[0]](files[call[1]], ...call.slice(2)))));
"""


@pytest.fixture()
def pages(tmp_path):
    """Call web/src/pages.js with one of the two files in front of it."""
    harness = tmp_path / "pages.mjs"
    harness.write_text(PAGES_HARNESS, encoding="utf-8")
    args = tmp_path / "pages-args.json"

    def run(calls: list[list]) -> list:
        args.write_text(json.dumps(calls), encoding="utf-8")
        done = subprocess.run(
            [node, str(harness),
             (ROOT / "web" / "src" / "pages.js").as_uri(),
             str(BUNDLED), str(BUNDLED_DETAILS), str(args)],
            capture_output=True, text=True, encoding="utf-8", check=False)
        assert done.returncode == 0, f"node failed: {done.stderr}"
        return json.loads(done.stdout)

    return run


@pytest.fixture(scope="module")
def rendered():
    """Both pages as HTML, built by vite and rendered by react-dom/server.

    The build goes under web/node_modules so that node resolves react and
    react-dom from where they are installed; it is a test artefact and is
    never part of what `npm run build` emits.
    """
    web = ROOT / "web"
    if node is None or not (web / "node_modules" / "vite").exists():
        pytest.skip("node and the web dependencies are needed to render")
    out = web / "node_modules" / ".ssr-test"
    vite = web / "node_modules" / ".bin" / (
        "vite.cmd" if os.name == "nt" else "vite")
    done = subprocess.run(
        [str(vite), "build", "--ssr", "src/ssr.jsx", "--outDir",
         "node_modules/.ssr-test", "--logLevel", "error"],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=web, shell=False)
    assert done.returncode == 0, f"vite failed: {done.stdout}\n{done.stderr}"

    script = """
const mod = await import(process.argv[2]);
process.stdout.write(JSON.stringify({
  pages: mod.pages(),
  choices: mod.everyChoice(),
}));
"""
    runner = out / "run-pages.mjs"
    runner.write_text(script, encoding="utf-8")
    done = subprocess.run(
        [node, str(runner), (out / "ssr.js").as_uri()],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=web)
    assert done.returncode == 0, f"node failed: {done.stderr}"
    return json.loads(done.stdout)


def words_of(html: str) -> str:
    """The text a reader sees, with the tags and the entities taken out."""
    text = re.sub(r"<[^>]+>", " ", html)
    for entity, plain in (("&amp;", "&"), ("&quot;", '"'), ("&#x27;", "'"),
                          ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(entity, plain)
    return re.sub(r"\s+", " ", text)


def details_file() -> dict:
    return json.loads(DETAILS.read_text(encoding="utf-8"))


def verification() -> dict:
    return json.loads(VERIFICATION.read_text(encoding="utf-8"))
def test_the_details_file_holds_what_the_verification_holds():
    """SPEC 11.34. Derived again here, and compared row by row.

    The page must not be able to show a score the verification did not
    produce, so this walks results/verification.json and asks the derived
    file for the same numbers, rather than trusting the deriving code.
    """
    result = verification()
    details = details_file()
    assert BUNDLED_DETAILS.read_bytes() == DETAILS.read_bytes()
    assert len(DETAILS.read_bytes()) < DETAILS_LIMIT

    # Every group every variant was scored on, with its decomposition.
    scored = {(row["variant"], row["region"], row["lead_day"],
               row["threshold_mm"]): row for row in result["groups_scored"]}
    assert len(scored) == 300
    columns = details["scored"]["columns"]
    seen = 0
    for row in details["scored"]["rows"]:
        got = dict(zip(columns, row))
        want = scored[(got["variant"], got["region"], got["lead_day"],
                       got["threshold_mm"])]
        parts = want["decomposition"]
        for name in ("cases", "dates", "event_dates", "base_rate", "bs",
                     "reference_bs", "bss", "bss_lo", "bss_hi",
                     "bss_halfwidth", "cases_with_flat_reference",
                     "resamples_discarded"):
            assert got[name] == want[name], (name, got["region"])
        for name in ("reliability", "resolution", "uncertainty", "brier",
                     "residual"):
            assert got[name] == parts[name], (name, got["region"])
        seen += 1
    assert seen == 300

    # Skill by date block, for the variant the labels come from.
    blocks = [row for row in result["skill_by_date_block"]
              if row["variant"] == "all51"]
    assert len(blocks) == 360
    columns = details["by_date_block"]["columns"]
    for row, want in zip(details["by_date_block"]["rows"], blocks):
        got = dict(zip(columns, row))
        assert (got["region"], got["lead_day"], got["threshold_mm"]) == (
            want["region"], want["lead_day"], want["threshold_mm"])
        assert got["cases"] == want["cases"] and got["bss"] == want["bss"]
        block = details["date_blocks"][got["block"]]
        assert (block["from"], block["to"]) == (want["from"], want["to"])

    # The 2-degree map: the same 1,635 rows, written as cells and pictures.
    cells = {(cell[0], cell[1]): at for at, cell
             in enumerate(details["two_degree"]["cells"])}
    assert len(cells) == 109
    for want in result["two_degree"]:
        key = f"{want['lead_day']}_{int(want['threshold_mm'])}"
        at = cells[(want["lat"], want["lon"])]
        got = details["two_degree"]["pictures"][key][at]
        assert got == [want["cases"], want["base_rate"], want["bss"]], want
        cell = details["two_degree"]["cells"][at]
        assert cell[2] == want["squares"]
        assert cell[3] == want["enough_squares"]
    assert sum(len(one) for one in
               details["two_degree"]["pictures"].values()) == 15 * 109

    # CRPS, and everything that is carried over whole.
    columns = details["crps"]["columns"]
    for row, want in zip(details["crps"]["rows"], result["crps"]["rows"]):
        got = dict(zip(columns, row))
        for name in columns:
            assert got[name] == want[name], name
    assert details["crps"]["disagreement"] == result["crps"]["disagreement"]
    for name in ("period", "wording", "note_small_reference_groups",
                 "crps_note", "crps_compared", "not_computed", "regions",
                 "leads", "thresholds_mm", "published_thresholds_mm",
                 "variants", "buckets", "bucket_floor", "bootstrap",
                 "reference", "dates", "date_blocks", "squares", "cases"):
        assert details[name] == result[name], name

    meta = json.loads(
        (ROOT / "results" / "verification_meta.json").read_text("utf-8"))
    for name in ("spec_sha256", "git_commit", "imerg", "inputs"):
        assert details["meta"][name] == meta[name], name


@needs_node
def test_every_chip_in_the_grid_is_the_label_the_record_gives(pages,
                                                              rendered):
    """All 60 cells of the four grids, and the key above them."""
    summary = summary_file()
    grids = pages([["gridFor", "summary", region]
                   for region in summary["regions"]])
    html = rendered["pages"]["report_card"]
    seen = 0
    for region, grid in zip(summary["regions"], grids):
        assert [row["threshold"] for row in grid] == summary["thresholds_mm"]
        for row in grid:
            assert [cell["lead"] for cell in row["cells"]] == summary["leads"]
            for cell in row["cells"]:
                group = next(
                    one for one in summary["groups"]
                    if one["region"] == region
                    and one["lead_day"] == cell["lead"]
                    and one["threshold_mm"] == row["threshold"])
                assert cell["label"] == group["label"]
                assert cell["colour"] == group["colour"]
                assert cell["short"] == {
                    "Good track record": "Good",
                    "Treat as a rough guide": "Rough guide",
                    "Not enough past data": "Too few"}[group["label"]]
                # And the page carries the full label where a reader who
                # cannot see the colour will find it.
                extra = (", better than the usual rain for this "
                         "place and month") if cell["beat"] else ""
                shown = (f'aria-label="{region}, day {cell["lead"]}, '
                         f'{row["threshold"]} mm: {group["label"]}{extra}"')
                assert shown.replace("&", "&amp;") in html
                seen += 1
    assert seen == 60
    for label in ("Good track record", "Treat as a rough guide",
                  "Not enough past data"):
        assert label in html, label


@needs_node
def test_every_point_and_whisker_is_its_group_s_own(pages, rendered):
    """The twelve plots: five points each, with the file's own range."""
    summary = summary_file()
    want = [(region, threshold) for region in summary["regions"]
            for threshold in summary["thresholds_mm"]]
    got = pages([["skillSeries", "summary", region, threshold]
                 for region, threshold in want])
    assert len(got) == 12
    for (region, threshold), series in zip(want, got):
        assert [point["lead"] for point in series] == summary["leads"]
        for point in series:
            group = next(
                one for one in summary["groups"]
                if one["region"] == region and one["lead_day"] == point["lead"]
                and one["threshold_mm"] == threshold)
            assert point["bss"] == group["bss"]
            assert point["lo"] == group["bss_lo"]
            assert point["hi"] == group["bss_hi"]
            assert point["above"] == group[
                "conditions"]["skill_above_zero"]["pass"]
            assert point["above"] == (point["lo"] > 0)

    # Twelve plots on the page, each with five dots and five bars.
    html = rendered["pages"]["report_card"]
    assert html.count("<figure class=\"plot\"") == 12
    assert html.count("<circle") == 60


@needs_node
def test_every_band_row_is_a_counted_band_with_the_panel_s_sentence(pages):
    """The pickable table, for all 60 choices, against the file.

    The sentence is the place panel's own function, so a band cannot read one
    way on the forecast page and another way here.
    """
    summary = summary_file()
    want = [(group["region"], group["lead_day"], group["threshold_mm"])
            for group in summary["groups"]]
    got = pages([["bandRows", "summary", region, lead, threshold]
                 for region, lead, threshold in want])
    rows_seen = 0
    for (region, lead, threshold), rows in zip(want, got):
        group = next(one for one in summary["groups"]
                     if one["region"] == region and one["lead_day"] == lead
                     and one["threshold_mm"] == threshold)
        assert len(rows) == len(group["buckets"])
        for row, bucket in zip(rows, group["buckets"]):
            assert (row["k_from"], row["k_to"]) == (
                bucket["k_from"], bucket["k_to"])
            assert row["cases"] == bucket["cases"]
            assert row["times_in_10"] == bucket["times_in_10"]
            assert row["sentence"] == expected_past(group, bucket["k_from"])
            assert row["often"] in row["sentence"]
            rows_seen += 1
    assert rows_seen == sum(len(g["buckets"]) for g in summary["groups"])


@needs_node
def test_the_frequency_and_crps_sentences_carry_the_file_s_figures(pages):
    """Both one-sentence summaries, for every choice, from the file."""
    summary = summary_file()
    india = summary["frequency_check"]["all_india"]
    want = [(row["lead_day"], row["threshold_mm"]) for row in india]
    said = pages([["frequencySentence", "summary", lead, threshold]
                  for lead, threshold in want])
    for row, got in zip(india, said):
        assert got["row"] == row
        assert f"{row['ratio']:.2f} times as often" in got["sentence"]
        assert f"{row['mean_forecast']:.3f} against " \
               f"{row['observed']:.3f}" in got["sentence"]
        assert f"day {row['lead_day']}" in got["sentence"]
        assert ("more often" if row["ratio"] >= 1 else "less often") \
            in got["sentence"]

    crps = summary["crps"]
    said = pages([["crpsSentence", "summary", row["region"], row["lead_day"]]
                  for row in crps])
    assert len(said) == 20
    for row, got in zip(crps, said):
        assert got["row"] == row
        assert f"{row['crpss_fair']:.3f}" in got["sentence"]
        assert f"from {row['crpss_lo']:.3f} to {row['crpss_hi']:.3f}" \
            in got["sentence"]
        assert summary["crps_baseline"] in got["sentence"]
        beat = "beat that baseline" in got["sentence"]
        assert beat == (row["crpss_lo"] > 0), row


@needs_node
def test_the_decomposition_shown_adds_up(pages):
    """SPEC 5.3, for every group of every variant: REL - RES + UNC = BS."""
    details = details_file()
    rows = [dict(zip(details["scored"]["columns"], row))
            for row in details["scored"]["rows"]]
    got = pages([["decomposition", "details", row["variant"], row["region"],
                  row["lead_day"], row["threshold_mm"]] for row in rows])
    assert len(got) == 300
    # The identity is exact in float64 and is asserted to 1e-12 while the
    # scores are computed (tests/test_verify.py). What is published is
    # rounded to six decimals, so what a reader adds up can differ from the
    # printed Brier score by half of the last digit, and does in 102 of the
    # 300 groups. More than that would mean the parts are not the parts.
    off = 0
    for want, parts in zip(rows, got):
        assert parts["brier"] == want["brier"] == want["bs"]
        assert parts["sum"] == pytest.approx(want["brier"], abs=1.5e-6)
        assert parts["gap"] <= 1.5e-6
        if parts["gap"] > 5e-7:
            off += 1
        assert parts["bss"] == want["bss"]
        assert parts["cases"] == want["cases"]
    # Measured: 102 of the 300, and the worst gap is 1.0e-6, which is one
    # unit in the last published digit. A gap bigger than that would mean
    # the parts are not the parts.
    assert off == 102, off


@needs_node
def test_the_maps_draw_one_rectangle_per_cell(pages, rendered):
    """Fifteen pictures over the same 109 cells, and nothing invented."""
    details = details_file()
    want = [(lead, threshold) for lead in details["leads"]
            for threshold in details["published_thresholds_mm"]]
    got = pages([["mapCells", "details", lead, int(threshold)]
                 for lead, threshold in want])
    assert len(got) == 15
    for (lead, threshold), cells in zip(want, got):
        assert len(cells) == 109
        for cell in cells:
            source = next(
                row for row in verification()["two_degree"]
                if row["lat"] == cell["lat"] and row["lon"] == cell["lon"]
                and row["lead_day"] == lead
                and row["threshold_mm"] == threshold)
            assert cell["bss"] == source["bss"]
            assert cell["base_rate"] == source["base_rate"]
            assert cell["enough"] == source["enough_squares"]

    # Two maps on the page, 109 rectangles each. One cell -- 36 N 76 E, in
    # the Karakoram -- never saw 10 mm in six months, so it has a base rate
    # of 0 and no skill at all, and it is drawn white and says "no number"
    # rather than being left out.
    html = rendered["pages"]["how_we_checked"]
    assert html.count("<rect") == 218
    blank = [cell for cell in pages(
        [["mapCells", "details", 1, 10]])[0] if cell["bss"] is None]
    assert len(blank) == 1 and (blank[0]["lat"], blank[0]["lon"]) == (36.0,
                                                                     76.0)
    assert html.count('fill="#ffffff"') == len(blank)
    assert "no number" in html


@needs_node
def test_the_report_card_opens_with_four_sentences_and_the_files_numbers(
        pages, rendered):
    """SPEC 11.41. TL;DR, then The full details.

    The page's one plain line about the whole record was under the
    period, the sixty labels, the skill plot and twelve reliability
    bands, and the readers who were asked to use this site never reached
    it. The answer to "can I believe this?" is four sentences at the top
    now, and every number in them is counted from summary.json by
    `tldr` rather than written into the page.

    Both are checked: the function against the file, and the rendered
    page against the function.
    """
    said = pages([["tldr", "summary"]])[0]

    # The numbers, worked out here from the same file the function reads.
    bundled = summary_file()
    groups = bundled["groups"]
    runs = max(group["conditions"]["enough_data"]["dates"]
               for group in groups)
    beat = len([group for group in groups
                if group["conditions"]["skill_above_zero"]["pass"]])
    confident = len([group for group in groups
                     if not group["conditions"]["small_honesty_error"]
                     ["pass"]])
    labels = {group["label"] for group in groups}
    assert said["runs"] == runs, (said["runs"], runs)
    assert said["total"] == len(groups) == 60, said["total"]
    assert said["beat"] == beat, (said["beat"], beat)
    assert said["confident"] == confident, (said["confident"], confident)
    # The period is quoted out of the file's own period line, so the
    # dates in the four sentences are the dates under the heading.
    assert said["period"] and said["period"] in bundled["period"], (
        said["period"], bundled["period"])

    # Four sentences, and what each of them has to say.
    four = said["sentences"]
    assert len(four) == 4, four
    assert four[0] == (f"We saved {runs} old forecasts from "
                       f"{said['period']}, and checked each one against "
                       "what satellites saw afterwards."), four[0]
    assert f"{beat} of the 60" in four[1], four[1]
    # "everywhere" is only allowed while every label really is the one
    # label: the sentence counts them rather than claiming it.
    if labels == {"Treat as a rough guide"}:
        assert "worked as a rough guide everywhere: all 60 labels say so" \
            in four[1], four[1]
    else:
        assert "everywhere" not in four[1], (labels, four[1])
    if confident == len(groups):
        assert four[2] == ("But when most of the 51 runs agreed on rain, "
                           "the satellite saw rain less often than they "
                           "suggested."), four[2]
    assert four[3] == ("So treat them as a helpful hint, not a "
                       "promise."), four[3]

    # And the page itself: the heading, the four sentences in order, and
    # the second heading above everything that was there before.
    html = rendered["pages"]["report_card"]
    text = words_of(html)
    assert "TL;DR" in text, text[:200]
    at = text.index("TL;DR")
    # Nothing but the page's own title is above it.
    assert words_of(html[:html.index("TL;DR")]).strip() == (
        "The report card"), words_of(html[:html.index("TL;DR")])
    for sentence in four:
        where = text.index(sentence, at)
        at = where
    full = text.index("The full details")
    assert full > at, (full, at)
    # The period line, the sixty labels and the skill plot are all under
    # it: that is what "the full details" names.
    assert text.index(bundled["period"]) > full
    assert text.index("All 60 labels") > full
    # Both headings are the one style, in the site's navy.
    assert '<h2 class="tldrhead">TL;DR</h2>' in html
    assert '<h2 class="tldrhead">The full details</h2>' in html


@needs_node
def test_how_we_checked_says_who_it_is_for_before_the_method(rendered):
    """SPEC 11.41. One line at the top, and the way to the plain version.

    This is the hardest page on the site -- Brier skill, a bootstrap, a
    reference climatology, a decomposition -- and the menu offered it to
    a first-time visitor with nothing to say what it was. The report card
    answers the same question in four sentences, so the line says so and
    links to it.
    """
    html = rendered["pages"]["how_we_checked"]
    text = words_of(html)
    # The link's own tag becomes a space in `words_of`, so the full stop
    # after it is read with a space in front of it: the sentence is
    # checked up to the link, and the link itself just below.
    said = ("For experts: the method and the numbers behind the report "
            "card. For the plain version, see the Report card")
    assert said in text, text[:300]
    # At the top: above the method, and with nothing but the page's own
    # heading above it.
    assert text.index(said) < text.index("The method"), text[:300]
    assert words_of(html[:html.index("For experts")]).strip() == (
        "How we checked"), words_of(html[:html.index("For experts")])
    # The link is a real path this site answers, and it is the one the
    # words name. The nav of that page is rendered in the same fixture,
    # which is how the path is known to exist.
    assert '<a href="/report-card">Report card</a>' in html
    assert "/report-card" in rendered["pages"]["nav"]["/report-card"]


@needs_node
def test_the_period_sentence_is_on_both_pages(rendered):
    """SPEC 5.11: everything that shows the record shows the period."""
    period = summary_file()["period"]
    assert len(period) > 150
    for name in ("report_card", "how_we_checked"):
        assert period in words_of(rendered["pages"][name]), name


@needs_node
def test_no_percentage_appears_on_either_page(rendered):
    """SPEC 6.7 and 11.33. No label is green, so nothing may read as one."""
    for name, html in rendered["pages"].items():
        if name == "nav":
            continue
        assert "%" not in html, name
        assert "percent" not in html.lower(), name
    for html in rendered["choices"]:
        assert "%" not in html
        assert "percent" not in html.lower()
    assert len(rendered["choices"]) == 159


@needs_node
def test_the_forbidden_words_hold_on_both_pages(rendered):
    """SPEC 11.20's list, over every word either page can put on a screen."""
    seen = []
    for name in ("report_card", "how_we_checked"):
        seen.append(words_of(rendered["pages"][name]))
    seen.extend(words_of(html) for html in rendered["choices"])
    for text in seen:
        low = text.lower()
        for word in FORBIDDEN:
            if word == "certain":
                assert not re.search(r"\bcertain\b", low), text[:200]
                continue
            if word == "warn":
                # "Not an official warning" is the header's, and it is
                # the one warning word this site is required to say.
                # SPEC 11.40 took the footer's second copy of it out.
                assert "warn" not in low.replace("official warning", ""), \
                    text[:200]
                continue
            assert word not in low, f"{word} in: {text[:200]}"
    # And the wording that must be there.
    both = " ".join(seen)
    assert "satellite" in both
    assert "it rained" not in both


@needs_node
def test_the_menu_is_three_real_links(rendered):
    """SPEC 11.34: three paths, and the one being read marked as itself.

    The words "(you are here)" are out of the laptop bar: the link's own
    style says which page this is -- bold, underlined and the navy, which
    is more than a colour (11.22) -- and `aria-current` is what a screen
    reader is given. So the words are checked gone and the
    attribute is checked present, on exactly one link of the three.
    """
    navs = rendered["pages"]["nav"]
    assert sorted(navs) == ["/", "/how-we-checked", "/report-card"]
    for path, html in navs.items():
        for other in navs:
            assert f'href="{other}"' in html, (path, other)
        assert html.count('aria-current="page"') == 1
        assert "(you are here)" not in html, path
        here = html.split('aria-current="page"')[0]
        assert here.rstrip().endswith(f'class="navlink here"') or \
            f'href="{path}"' in here.split("<a")[-1]
    assert "Forecast" in navs["/"]
    assert "Report card" in navs["/report-card"]
    assert "How we checked" in navs["/how-we-checked"]
def test_the_rewrite_sends_the_pages_and_only_the_pages_to_one_file():
    """SPEC 11.34. Three paths, one index.html, and two things left alone.

    A catch-all that swallows /assets/ as well turns a missing or renamed
    chunk into index.html with a 200: a <script src> then gets HTML back and
    the browser reports a syntax error instead of the 404 that would say what
    is really wrong. Measured on the preview deployment of e18781b, 13
    November 2026: /assets/does-not-exist.js answered 200 with the forecast
    page in it.
    """
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    rewrites = config["rewrites"]
    assert len(rewrites) == 1
    assert rewrites[0]["destination"] == "/index.html"
    pattern = re.compile("^" + rewrites[0]["source"] + "$")

    # The pages, and anything else that is not a file: these are the site.
    for path in ("/", "/report-card", "/how-we-checked", "/anything",
                 "/deep/er/still"):
        assert pattern.match(path), path

    # The two functions, and every asset: Vercel answers these from the
    # filesystem, and where there is no such file it answers 404.
    for path in ("/api/place", "/api/health", "/assets/index-Dji49BPm.js",
                 "/assets/does-not-exist.js", "/assets/nothing/here.css"):
        assert not pattern.match(path), path

    assert config["functions"]["api/*.mjs"]["includeFiles"] == (
        "config/{store,regions}.json")

    # Every same-origin thing the built page points at is under /assets/ or
    # under /api/ -- the two the rule above leaves alone. Nothing the page
    # loads or links to on this origin depends on the rewrite.
    dist = ROOT / "web" / "dist" / "index.html"
    if dist.exists():
        links = re.findall('(?:src|href)="(/[^"]+)"',
                           dist.read_text(encoding="utf-8"))
        assert links, "the built page asks for nothing at all"
        assert any(link.endswith(".js") for link in links)
        for link in links:
            assert link.startswith(("/assets/", "/api/")), link
            assert not pattern.match(link), link


def test_with_no_script_the_page_links_to_the_files_themselves():
    """SPEC 11.34. Both new paths serve this file; it must not be empty."""
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    noscript = html.split("<noscript>")[1].split("</noscript>")[0]
    for name in ("site_summary.json", "site_details.json",
                 "verification.json", "labels.json",
                 "verification_meta.json", "SPEC.md"):
        assert name in noscript, name
    assert "/api/place?lat=28.5" in noscript
    assert "/api/health" in noscript


# --------------------------------------------- SPEC 11.35, the phone's bars

VIEWPORT_HARNESS = r"""
// SPEC 11.35 to 11.37. The built site measured in a real browser at a
// phone's size, driven over the DevTools protocol with nothing installed:
// node's own WebSocket and http server, and whatever Chrome the machine has.
//
// It serves `web/dist` itself, because the page loads its modules with
// `type="module"` and a file:// page may not, and it answers /api/health and
// /api/place by importing the real api/*.mjs files. With STORE_BASE_URL set
// those read the small published run the test built; without it they fail,
// and the page is measured as a reader with no network sees it.
//
// Prints one JSON object. `{"skip": "..."}` means no browser was found.

import { createServer } from 'node:http';
import { readFile, mkdtemp, readFile as read } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, extname, normalize, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const DIST = process.argv[2];
const PLAN = JSON.parse(process.argv[3] || '{}');
const API = PLAN.api ? resolve(PLAN.api) : null;

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

function say(value) {
  process.stdout.write(JSON.stringify(value));
  process.exit(0);
}

const chrome = CANDIDATES.find((path) => existsSync(path));
if (!chrome) say({ skip: 'no Chrome on this machine' });

const fns = {};
if (API) {
  fns.health = await import(pathToFileURL(join(API, 'health.mjs')));
  fns.place = await import(pathToFileURL(join(API, 'place.mjs')));
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/')) {
    const fn = url.pathname.endsWith('health') ? fns.health : fns.place;
    if (!fn) {
      response.writeHead(503, { 'content-type': 'application/json' });
      response.end('{"ok":false,"store":"not served by this check"}');
      return;
    }
    try {
      const answer = await fn.default.fetch(
        new Request(`https://local.test${request.url}`));
      const body = await answer.text();
      response.writeHead(answer.status, {
        'content-type': answer.headers.get('content-type')
          || 'application/json',
        'cache-control': 'no-store',
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: false, error: String(error) }));
    }
    return;
  }
  const asset = /\.[a-z0-9]+$/i.test(url.pathname);
  const file = normalize(join(DIST, asset ? url.pathname : '/index.html'));
  if (!file.startsWith(normalize(DIST))) {
    response.writeHead(403).end('no');
    return;
  }
  try {
    const bytes = await readFile(file);
    response.writeHead(200, {
      'content-type': TYPES[extname(file)] || 'application/octet-stream',
    });
    response.end(bytes);
  } catch {
    response.writeHead(404).end('no');
  }
});
await new Promise((go) => server.listen(0, '127.0.0.1', go));
const port = server.address().port;

const profile = await mkdtemp(join(tmpdir(), 'hcview-'));
const child = spawn(chrome, [
  '--headless=new', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-extensions',
  '--disable-dev-shm-usage', '--no-sandbox', '--use-gl=swiftshader',
  `--user-data-dir=${profile}`, '--remote-debugging-port=0', 'about:blank',
], { stdio: ['ignore', 'ignore', 'ignore'] });

async function devtoolsPort() {
  const file = join(profile, 'DevToolsActivePort');
  for (let tries = 0; tries < 120; tries += 1) {
    try {
      const text = await read(file, 'utf8');
      const first = text.split('\n')[0].trim();
      if (first) return Number(first);
    } catch { /* not written yet */ }
    await new Promise((go) => setTimeout(go, 250));
  }
  return null;
}

function stop(value) {
  try { child.kill(); } catch { /* already gone */ }
  server.close();
  say(value);
}

const cdpPort = await devtoolsPort();
if (!cdpPort) stop({ skip: 'Chrome did not open a DevTools port' });

const where = await fetch(`http://127.0.0.1:${cdpPort}/json/version`)
  .then((r) => r.json());
const socket = new WebSocket(where.webSocketDebuggerUrl);
await new Promise((go, no) => {
  socket.addEventListener('open', go, { once: true });
  socket.addEventListener('error', no, { once: true });
});

let next = 0;
const waiting = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.id && waiting.has(message.id)) {
    waiting.get(message.id)(message);
    waiting.delete(message.id);
  }
});

function send(method, params = {}, sessionId) {
  next += 1;
  const id = next;
  return new Promise((go, no) => {
    waiting.set(id, (message) => (message.error
      ? no(new Error(`${method}: ${message.error.message}`))
      : go(message.result)));
    socket.send(JSON.stringify({ id, method, params, sessionId }));
  });
}

const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget',
  { targetId, flatten: true });

async function evaluate(expression) {
  const answer = await send('Runtime.evaluate', {
    expression, returnByValue: true, awaitPromise: true,
  }, sessionId);
  if (answer.exceptionDetails) {
    throw new Error(answer.exceptionDetails.exception?.description
      || 'the page threw');
  }
  return answer.result.value;
}

async function tap(x, y) {
  for (const type of ['mousePressed', 'mouseReleased']) {
    await send('Input.dispatchMouseEvent', {
      type, x, y, button: 'left', clickCount: 1,
    }, sessionId);
  }
  await new Promise((go) => setTimeout(go, 900));
}

async function size(width, height) {
  await send('Emulation.setDeviceMetricsOverride', {
    width, height, deviceScaleFactor: 1, mobile: true,
  }, sessionId);
  // SPEC 11.39. A screen with two fingers on it, so that one finger and
  // two can be told apart: without this the page has no touch at all and
  // the gesture checks below would be measuring a mouse.
  await send('Emulation.setTouchEmulationEnabled',
    { enabled: true, maxTouchPoints: 2 }, sessionId);
  await new Promise((go) => setTimeout(go, 400));
}

/** A drag with `many` fingers, from (x, y), by (dx, dy), in six steps. */
async function drag(x, y, dx, dy, many) {
  const at = (step) => Array.from({ length: many }, (_, n) => ({
    x: x + n * 40 + (dx * step) / 6,
    y: y + (dy * step) / 6,
  }));
  await send('Input.dispatchTouchEvent',
    { type: 'touchStart', touchPoints: at(0) }, sessionId);
  for (let step = 1; step <= 6; step += 1) {
    await send('Input.dispatchTouchEvent',
      { type: 'touchMove', touchPoints: at(step) }, sessionId);
    await new Promise((go) => setTimeout(go, 40));
  }
  await send('Input.dispatchTouchEvent',
    { type: 'touchEnd', touchPoints: [] }, sessionId);
  await new Promise((go) => setTimeout(go, 500));
}

/**
 * A screenshot, when SHOTS names a directory to put it in.
 *
 * Off in a test run and on when somebody is looking: the measurements
 * below are what the checks read, and a picture is what a person reads.
 * SPEC 11.39's own numbers were taken from these.
 */
async function shoot(name) {
  if (!PLAN.shots) return;
  const shot = await send('Page.captureScreenshot', { format: 'png' },
    sessionId);
  const { writeFile } = await import('node:fs/promises');
  await writeFile(`${PLAN.shots}/${name}.png`,
    Buffer.from(shot.data, 'base64'));
}

async function open(path) {
  await send('Page.navigate', { url: `http://127.0.0.1:${port}${path}` },
    sessionId);
  await new Promise((go) => setTimeout(go, PLAN.settle || 1800));
}

// What every page is asked for: the shape of it, with no interaction.
const LOOK = `(async () => {
  const box = (s) => {
    const e = document.querySelector(s);
    if (!e) return null;
    const b = e.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom),
             height: Math.round(b.height * 10) / 10,
             // SPEC 11.41. The left edge, because item 6 is about three
             // boxes beginning in the same place.
             left: Math.round(b.left),
             right: Math.round(b.right), width: Math.round(b.width) };
  };
  const lines = (s) => {
    const e = document.querySelector(s);
    if (!e) return null;
    const range = document.createRange();
    range.selectNodeContents(e);
    return range.getClientRects().length;
  };
  const seen = {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    docScrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    sideways: [...document.querySelectorAll('.gridwrap, .labelgrid')]
      .filter((e) => e.scrollWidth > e.clientWidth + 1).length,
    chipsCut: [...document.querySelectorAll('.labelgrid .chip')]
      .filter((e) => e.scrollWidth > e.clientWidth + 1
        || e.scrollHeight > e.clientHeight + 1).length,
    chips: document.querySelectorAll('.labelgrid .chip').length,
    marks: document.querySelectorAll('.labelgrid .beat').length,
    rowHeads: [...document.querySelectorAll('.labelgrid tbody th')]
      .map((e) => ({ text: e.textContent.trim(),
        nowrap: getComputedStyle(e).whiteSpace === 'nowrap',
        fits: e.scrollWidth <= e.clientWidth + 1 })),
    // SPEC 11.39. The page scrolls, so every box below is where it is on
    // the screen and scrollY says where the screen is on the page. The
    // drawer and its handle are gone; they are still asked for, so a
    // check can say so rather than assume it.
    scrollY: Math.round(window.scrollY),
    docHeight: document.documentElement.scrollHeight,
    maxScroll: document.documentElement.scrollHeight - window.innerHeight,
    header: box('.pagehead'),
    band: box('.band'),
    brand: box('.brand'),
    fresh: box('.fresh'),
    freshText: (document.querySelector('.fresh') || {}).textContent || null,
    warn: box('.headwarn'),
    // SPEC 11.41. Where the header's own contents begin and end, which
    // on a desktop must be where the page's column begins and ends.
    warnIcon: box('.headwarn .icon'),
    topnav: box('.topnav'),
    warnText: (document.querySelector('.headwarn') || {}).textContent || null,
    controls: box('.controls'),
    asks: box('.asks'),
    searchBox: box('.searchrow input'),
    searchValue: document.querySelector('.searchrow input')
      ? document.querySelector('.searchrow input').value : null,
    searchPlaceholder: document.querySelector('.searchrow input')
      ? document.querySelector('.searchrow input').placeholder : null,
    matches: [...document.querySelectorAll('.matches button')]
      .map((e) => e.textContent.trim().slice(0, 40)),
    locate: box('.locate'),
    locateName: document.querySelector('.locate')
      ? document.querySelector('.locate').getAttribute('aria-label') : null,
    locateTitle: document.querySelector('.locate')
      ? document.querySelector('.locate').getAttribute('title') : null,
    ortap: box('.ortap'),
    pillrow: box('.pills'),
    // SPEC 11.40. The line beside "Which day?", which is drawn only on
    // the mornings when the five days do not include today.
    startsNote: (document.querySelector('.startsnote') || {})
      .textContent || null,
    days: box('.days'),
    dayRow: box('.days .radios'),
    amounts: box('.amounts'),
    amountRow: box('.amounts .radios'),
    amountLine: box('.amountline'),
    pillWidths: [...document.querySelectorAll(
      '.days .radios button, .amounts .radios button')]
      // Which group a pill is in, asked of the group rather than of the
      // pill's grandparent: SPEC 11.40 put a box between the amount
      // pills and their group, so that the handle after them can share
      // their line on a desktop.
      .map((e) => [e.closest('.group').className,
        Math.round(e.getBoundingClientRect().width)]),
    // SPEC 11.40. "What does mm mean?" is a disclosure now: the handle,
    // whether it is open, the four lines it opens, and whether there is a
    // link in it at all -- there must not be, because nothing navigates.
    path: window.location.pathname,
    mmwhat: box('.mmwhat'),
    mmSummary: box('.mmwhat > summary'),
    mmOpen: document.querySelector('.mmwhat')
      ? document.querySelector('.mmwhat').open : null,
    mmLinks: document.querySelectorAll('.mmwhat a').length,
    mmLines: [...document.querySelectorAll('.mmwhat .amountwords li')]
      .map((e) => e.textContent.replace(/[ ]+/g, ' ').trim()),
    // SPEC 11.40. The count on each day pill, the colour of the square
    // before it, and the caption under the row.
    dayCounts: [...document.querySelectorAll('.days .radios button')]
      .map((e) => {
        const seen = e.querySelector('.pillcount');
        const sq = e.querySelector('.daysq');
        return {
          name: e.getAttribute('aria-label'),
          on: /(^| )on( |$)/.test(e.className),
          count: seen ? seen.textContent.trim() : null,
          colour: sq ? getComputedStyle(sq).backgroundColor : null,
          edge: sq ? getComputedStyle(sq).borderTopColor : null,
        };
      }),
    pillNote: (document.querySelector('.pillnote') || {})
      .textContent || null,
    dayPills: [...document.querySelectorAll('.days .radios button')]
      .map((e) => [e.querySelector('.pilltop')
        ? e.querySelector('.pilltop').textContent : null,
      e.querySelector('.pillunder')
        ? e.querySelector('.pillunder').textContent : null,
      /(^| )on( |$)/.test(e.className)]),
    amountPills: [...document.querySelectorAll('.amounts .radios button')]
      .map((e) => [e.querySelector('.pilltop')
        ? e.querySelector('.pilltop').textContent : null,
      e.querySelector('.pillunder')
        ? e.querySelector('.pillunder').textContent : null,
      /(^| )on( |$)/.test(e.className)]),
    mapcard: box('.mapcard'),
    mapkey: box('.mapkey'),
    // SPEC 11.40. The key is the top of the panel on a desktop and
    // directly under the map on a phone; SPEC 11.41 puts the whole of it
    // back over the map's left side at 1280 pixels and over, so where it
    // is is asked of the document rather than assumed.
    keyInPanel: !!document.querySelector('.panelcol > .mapkey'),
    keyOverMap: !!document.querySelector('.mapcard .mapkey'),
    keyHandles: document.querySelectorAll('.mapkey summary').length,
    // SPEC 11.41. Anything on the page with a scrollbar of its own, and
    // how the map card and the key are positioned: the desktop page has
    // one scrollbar, the window's, and the map keeps its place by being
    // sticky rather than by boxing the card in.
    scrollers: [...document.querySelectorAll('.panelcol, .panelcol *')]
      .filter((e) => {
        const how = getComputedStyle(e).overflowY;
        return (how === 'auto' || how === 'scroll')
          && e.scrollHeight > e.clientHeight + 1;
      })
      .map((e) => String(e.className || e.tagName)),
    canScroll: [...document.querySelectorAll('.panelcol, .panelcol *')]
      .filter((e) => {
        const how = getComputedStyle(e).overflowY;
        return how === 'auto' || how === 'scroll';
      })
      .map((e) => String(e.className || e.tagName)),
    stick: {
      mapcard: document.querySelector('.mapcard')
        ? getComputedStyle(document.querySelector('.mapcard')).position
        : null,
      mapkey: document.querySelector('.mapkey')
        ? getComputedStyle(document.querySelector('.mapkey')).position
        : null,
    },
    keyEnds: [...document.querySelectorAll('.mapkey .keyends span')]
      .map((e) => e.textContent.trim()),
    keyTitle: (document.querySelector('.mapkey .keytitle') || {})
      .textContent || null,
    // Anything of ours drawn over the canvas. MapLibre's own controls are
    // its own and are named, not counted.
    overTheMap: [...document.querySelectorAll('.mapcard *')]
      .filter((e) => !e.closest('.maplibregl-control-container')
        && !e.closest('.map')
        && getComputedStyle(e).position === 'absolute'
        && e.getBoundingClientRect().height > 0)
      .map((e) => String(e.className || e.tagName)),
    keyOpen: document.querySelector('.mapkey')
      ? document.querySelector('.mapkey').open : null,
    keyText: (document.querySelector('.mapkey') || {}).textContent || null,
    keyRows: [...document.querySelectorAll('.mapkey .keyrows li')]
      .map((e) => e.textContent.trim()),
    // Where the key is, in the map canvas's own pixels, so a check can ask
    // what of India is behind it. SPEC 11.39.
    keyOver: (() => {
      const k = document.querySelector('.mapkey');
      const m = document.querySelector('.map');
      if (!k || !m) return null;
      const kb = k.getBoundingClientRect();
      const mb = m.getBoundingClientRect();
      return {
        position: getComputedStyle(k).position,
        box: [Math.round(kb.left - mb.left), Math.round(kb.top - mb.top),
          Math.round(kb.right - mb.left), Math.round(kb.bottom - mb.top)],
        map: [Math.round(mb.width), Math.round(mb.height)],
      };
    })(),
    card: box('.fcard'),
    // SPEC 11.40. The one closed section: what its handle says, and
    // whether it is open, so a check can say the words follow the state.
    moreLabel: (document.querySelector('.more > summary') || {})
      .textContent || null,
    moreOpen: document.querySelector('.more')
      ? document.querySelector('.more').open : null,
    backlink: box('.backtomap a'),
    cardLinks: [...document.querySelectorAll('.cardlinks a')]
      .map((e) => [e.textContent.trim(), e.getAttribute('href')]),
    // SPEC 11.40. One footer, with no second copy of the warning and one
    // handle to the credits, and on a desktop it is inside the panel.
    footer: box('footer'),
    footerInPanel: !!document.querySelector('.cardcol footer'),
    warnings: [...document.querySelectorAll('p')]
      .filter((e) => e.textContent.trim()
        .startsWith('Not an official warning')).length,
    creditControls: document.querySelectorAll(
      'footer summary, footer a[href="#credits"]').length,
    creditText: (document.querySelector('footer .credit') || {})
      .textContent || null,
    sheet: box('.sheetbar'),
    handle: box('.handle'),
    summaryRow: box('.summaryline'),
    mapError: (document.querySelector('.loading')
      || {}).textContent || null,
    map: box('.mapwrap'),
    // SPEC 11.39. Nothing on this page may overlap anything else on it:
    // every pair of controls, measured against every other.
    overlapping: (() => {
      const items = [...document.querySelectorAll(
        '.searchrow input, .locate, .radios button, .mmwhat > summary,'
        + ' .topnav .navlink, .cardlinks a, .mapkey summary, .brand')];
      const bad = [];
      for (let i = 0; i < items.length; i += 1) {
        for (let j = i + 1; j < items.length; j += 1) {
          const a = items[i].getBoundingClientRect();
          const b = items[j].getBoundingClientRect();
          if (!a.height || !b.height) continue;
          if (a.right > b.left + 1 && b.right > a.left + 1
            && a.bottom > b.top + 1 && b.bottom > a.top + 1) {
            bad.push([String(items[i].className || items[i].tagName),
              String(items[j].className || items[j].tagName)]);
          }
        }
      }
      return bad;
    })(),
    // SPEC 11.39, the calm look: a pill is a fill and not an outline,
    // the chosen one is filled navy, the search box keeps its border, and
    // nothing on the page is set in capitals.
    pills: [...document.querySelectorAll(
      '.radios button, .countrow')].map((e) => {
      const s = getComputedStyle(e);
      return { what: e.className, on: /(^| )on( |$)/.test(e.className),
        fill: s.backgroundColor, border: s.borderTopWidth,
        ink: s.color };
    }),
    inputBorder: document.querySelector('.searchrow input')
      ? getComputedStyle(document.querySelector('.searchrow input'))
        .borderTopWidth : null,
    // Every card and every note. The one closed section is not in the
    // list: a rule above a heading is a divider and not an outline, and
    // SPEC 11.39 asks for the boxes to be opened up, not for the page to
    // stop separating one thing from another.
    outlined: [...document.querySelectorAll(
      '.welcome, .notice, .headwarn, .mapgone span, .fcard, .mapcard')]
      .map((e) => [e.className, getComputedStyle(e).borderTopWidth,
        getComputedStyle(e).borderLeftWidth]),
    allCaps: [...document.querySelectorAll('*')].filter((e) => {
      if (!e.getBoundingClientRect().height) return false;
      if (![...e.childNodes].some(
        (n) => n.nodeType === 3 && n.textContent.trim())) return false;
      return getComputedStyle(e).textTransform === 'uppercase';
    }).map((e) => [String(e.className || e.tagName),
      e.textContent.trim().slice(0, 30)]),
    whiteHere: !!document.querySelector('.whitehere'),
    // SPEC 11.38: what the map is actually showing, from the map itself.
    view: (document.querySelector('.map') && document.querySelector('.map').mapView)
      ? document.querySelector('.map').mapView() : null,
    // SPEC 11.38: the three rows a thumb has to hit, and the page's own
    // 12 pixel floor over everything it writes. MapLibre's controls are
    // its own and are not ours to set, so they are named and skipped.
    // Every row a thumb has to hit, as drawn: the ones the stylesheet
    // has hidden at this width are not rows a reader can hit, and the
    // menu button and the three links are each other's copy.
    rows: [...document.querySelectorAll(
      '.days .radios button, .amounts .radios button, .topnav .navlink,'
      + ' .menubutton, .locate, .searchrow input')]
      .filter((e) => e.getBoundingClientRect().height > 0)
      .map((e) => {
        const r = e.getBoundingClientRect();
        return [e.className || e.tagName, Math.round(r.height * 10) / 10,
          Math.round(parseFloat(getComputedStyle(e).fontSize) * 10) / 10,
          e.textContent.trim().slice(0, 20)];
      }),
    underTwelve: [...document.querySelectorAll('*')].filter((e) => {
      if (e.closest('.maplibregl-ctrl')) return false;
      const r = e.getBoundingClientRect();
      if (!r.height || !r.width) return false;
      if (![...e.childNodes].some(
        (n) => n.nodeType === 3 && n.textContent.trim())) return false;
      return parseFloat(getComputedStyle(e).fontSize) < 12;
    }).map((e) => [e.className || e.tagName,
      Math.round(parseFloat(getComputedStyle(e).fontSize) * 10) / 10,
      e.textContent.trim().slice(0, 30)]),
    focus: document.activeElement ? (document.activeElement.id
      || document.activeElement.className || document.activeElement.tagName)
      : null,
  };
  const wide = document.createElement('style');
  wide.textContent = '*{letter-spacing:0.5px !important}';
  document.head.appendChild(wide);
  await new Promise((go) => requestAnimationFrame(go));
  seen.wideFontScrollWidth = document.documentElement.scrollWidth;
  seen.wideFontGridOverflow = [...document.querySelectorAll('.gridwrap')]
    .filter((e) => e.scrollWidth > e.clientWidth + 1).length;
  wide.remove();
  return seen;
})()`;

// What the card is asked for: type sizes, tap targets, and its own words.
const INSIDE = `(() => {
  const px = (s) => {
    const e = document.querySelector(s);
    return e ? Math.round(parseFloat(getComputedStyle(e).fontSize) * 10) / 10
      : null;
  };
  const card = document.querySelector('.fcard');
  if (!card) return null;
  const small = [];
  const short = [];
  const used = {};
  card.querySelectorAll('*').forEach((e) => {
    const r = e.getBoundingClientRect();
    if (r.height === 0) return;
    // Chrome hides the contents of a shut <details> with
    // content-visibility, which keeps their layout boxes, so a height of
    // its own is not enough to tell what a reader can see. Everything
    // inside the shut section is still measured -- a reader who opens it
    // is using the same eyes and the same thumb -- and this says which.
    const shut = !!e.closest('details:not([open])');
    const text = [...e.childNodes].some(
      (n) => n.nodeType === 3 && n.textContent.trim());
    const fs = Math.round(parseFloat(getComputedStyle(e).fontSize) * 10) / 10;
    if (text) {
      used[fs] = (used[fs] || 0) + 1;
      if (fs < 13) {
        small.push([e.className || e.tagName, fs,
          e.textContent.trim().slice(0, 30), shut]);
      }
    }
    if (['BUTTON', 'SUMMARY', 'INPUT'].includes(e.tagName) && r.height < 43.5) {
      short.push([e.className || e.tagName, Math.round(r.height * 10) / 10,
        e.textContent.trim().slice(0, 24), shut]);
    }
  });
  return {
    sizes: {
      placeName: px('.placeline h2'),
      yours: px('.yours'),
      atSquare: px('.atsquare'),
      headline: px('.headline'),
      chosenRow: px('.countrow.on'),
      chosenCount: px('.countrow.on .rowcount'),
      rowWhat: px('.countrow .rowwhat'),
      trustChip: px('.trustline .chip'),
      trustLine: px('.trustline'),
      pastLine: px('.pastline'),
      notPromise: px('.notpromise'),
      dotKey: px('.dotkey li'),
      moreSummary: px('.more > summary'),
    },
    // SPEC 11.39: at most three text sizes in the card, counted from what
    // the browser actually resolved on every element that holds words.
    textSizes: used,
    // SPEC 11.40. The heading is the place and nothing else, and for a
    // location the two small lines under it.
    title: (document.querySelector('.placeline h2') || {})
      .textContent || null,
    yoursLine: (document.querySelector('.yours') || {})
      .textContent || null,
    noShare: (document.querySelector('.noshare') || {})
      .textContent || null,
    has: {
      counts: !!document.querySelector('.countrow'),
      trust: !!document.querySelector('.trustline .chip'),
      past: !!document.querySelector('.pastline'),
      moreShut: document.querySelector('.more')
        ? !document.querySelector('.more').open : null,
    },
    // The backslash is doubled on purpose: this whole expression is a
    // template literal in the harness, and a template literal eats an
    // unknown escape -- so a single backslash arrived at the browser as
    // /s+/g, which replaced every letter s in the card with a space.
    // The backslash is doubled on purpose. This whole expression is a
    // template literal in the harness, and a template literal eats an
    // escape it does not know: written with one backslash it reached the
    // browser as /s+/g, which replaced every letter s in the card with a
    // space, so the card's own words came back as "the 51 run ".
    cardText: card.textContent.replace(/\\s+/g, ' ').slice(0, 260),
    belowThirteen: small,
    tapTargetsUnder44: short,
  };
})()`;

try {
  await send('Page.enable', {}, sessionId);
  await send('Runtime.enable', {}, sessionId);

  const out = { pages: {}, phone: {} };

  // The three document pages, at a phone's width.
  await size(390, 664);
  for (const path of ['/report-card', '/how-we-checked', '/how-to-read']) {
    await open(path);
    out.pages[path] = await evaluate(LOOK);
    await shoot(`page${path.replace(/\//g, '-')}`);
  }

  // The forecast page, at each size the tests ask about.
  for (const [width, height] of (PLAN.sizes || [[390, 664]])) {
    const key = `${width}x${height}`;
    const here = {};
    await size(width, height);
    await open('/');
    // SPEC 11.39. The page as it opens, at the top of it, with nothing
    // chosen: there is no drawer to open and no handle to find, so this is
    // the one state every "without scrolling" measurement is made in.
    here.first = await evaluate(LOOK);
    await shoot(`${key}-first`);

    // SPEC 11.41. The colour key, opened and shut again -- wherever
    // there is anything to press. Over the map at 1280 pixels and over
    // it is the whole key, open, with no handle at all, so there both
    // states are the state the page opens in.
    if (here.first.keyHandles) {
      await evaluate("document.querySelector('.mapkey summary').click()");
      await new Promise((go) => setTimeout(go, 1200));
      here.keyToggled = await evaluate(LOOK);
      await evaluate("document.querySelector('.mapkey summary').click()");
      await new Promise((go) => setTimeout(go, 1200));
      here.keyBack = await evaluate(LOOK);
    }

    // SPEC 11.41. And the map zoomed in one step by its own button, which
    // is the other thing the key has to survive: it is drawn over the
    // canvas and the canvas has just repainted under it.
    const zoomed = await evaluate(
      "!!document.querySelector('.maplibregl-ctrl-zoom-in')"
      + " && (document.querySelector('.maplibregl-ctrl-zoom-in').click()"
      + " || true)");
    if (zoomed) {
      await new Promise((go) => setTimeout(go, 1200));
      here.afterZoom = await evaluate(LOOK);
      await open('/');
      await new Promise((go) => setTimeout(go, 400));
    }

    // SPEC 11.40. "What does mm mean?", opened and shut again. Every
    // measurement after this is made with it shut, which is how the page
    // opens and the state the map's own height is measured in.
    if (here.first.mmSummary && here.first.mmSummary.height) {
      await evaluate("document.querySelector('.mmwhat > summary').click()");
      await new Promise((go) => setTimeout(go, 600));
      here.mmShown = await evaluate(LOOK);
      await evaluate("document.querySelector('.mmwhat > summary').click()");
      await new Promise((go) => setTimeout(go, 600));
      here.mmHidden = await evaluate(LOOK);
    }

    // SPEC 11.39. One finger scrolls the page and two move the map.
    //
    // The scroll is asked for as a gesture rather than as raw touch
    // events, because scrolling is the browser's own answer to a touch
    // drag and not the page's; the two-finger drag is raw touch, because
    // that one is the map's own handler answering.
    if (here.first.map && here.first.map.height > 40) {
      const middle = {
        x: Math.round(here.first.map.width / 2),
        y: Math.round(here.first.map.top + here.first.map.height / 2),
      };
      const before = await evaluate(`(() => ({
        scrollY: Math.round(window.scrollY),
        max: document.documentElement.scrollHeight - window.innerHeight,
        bounds: document.querySelector('.map').mapView().bounds,
      }))()`);
      await drag(middle.x, middle.y, 0, -90, 1);
      const oneFinger = await evaluate(`(() => ({
        scrollY: Math.round(window.scrollY),
        bounds: document.querySelector('.map').mapView().bounds,
        hint: (document.querySelector(
          '.maplibregl-cooperative-gesture-screen') || {}).textContent
          || null,
      }))()`);
      await evaluate('window.scrollTo(0, 0)');
      await new Promise((go) => setTimeout(go, 400));
      await drag(middle.x, middle.y, 70, 0, 2);
      const twoFingers = await evaluate(`(() => ({
        scrollY: Math.round(window.scrollY),
        bounds: document.querySelector('.map').mapView().bounds,
      }))()`);
      here.gestures = { before, oneFinger, twoFingers };
      // Put the map back where it started, so what follows is measured
      // on the view the page opens with.
      await open('/');
    }

    // SPEC 11.39. The search box, used: a city typed and the form
    // submitted, which is one of the three ways a place is chosen.
    const typed = PLAN.city || 'Bhopal';
    await evaluate(`(() => {
      const box = document.querySelector('#place');
      if (!box) return false;
      const set = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value').set;
      box.focus();
      set.call(box, ${JSON.stringify(typed)});
      box.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    })()`);
    await new Promise((go) => setTimeout(go, 500));
    here.whileTyping = await evaluate(LOOK);
    await evaluate(
      "document.querySelector('form.search').requestSubmit()");
    await new Promise((go) => setTimeout(go, 1500));
    here.afterSearch = await evaluate(LOOK);
    here.searchCard = await evaluate(INSIDE);
    await shoot(`${key}-searched`);

    // SPEC 11.40. The handle of the one closed section, both ways
    // round. It is opened and shut again, so everything measured after
    // this is measured on the card as a reader first meets it.
    if (here.afterSearch.moreLabel) {
      await evaluate("document.querySelector('.more > summary').click()");
      await new Promise((go) => setTimeout(go, 500));
      here.moreShown = await evaluate(LOOK);
      await evaluate("document.querySelector('.more > summary').click()");
      await new Promise((go) => setTimeout(go, 500));
      here.moreHidden = await evaluate(LOOK);
    }

    // SPEC 11.41. The page scrolled to the end of itself with the one
    // closed section open, which is the tallest the card ever is: on a
    // desktop the map card is sticky and has to be whole on the screen
    // there too.
    if (here.afterSearch.moreLabel) {
      await evaluate("document.querySelector('.more > summary').click()");
      await new Promise((go) => setTimeout(go, 400));
      await evaluate(
        'window.scrollTo(0, document.documentElement.scrollHeight)');
      await new Promise((go) => setTimeout(go, 800));
      here.atBottom = await evaluate(LOOK);
      await evaluate("document.querySelector('.more > summary').click()");
      await evaluate('window.scrollTo(0, 0)');
      await new Promise((go) => setTimeout(go, 400));
    }

    // SPEC 11.41. The wheel over the map. On a desktop a wheel is how a
    // reader scrolls a page, so it scrolls the page; Ctrl and the wheel
    // together are what zooms, which is MapLibre's own cooperative
    // gestures and its own hint.
    if (width >= 1024 && here.first.map && here.first.map.height > 40) {
      // Where the canvas is now, not where it was when the page opened:
      // choosing a place makes the row above the map taller (item 10 of
      // the last batch), so the middle of the map has moved down.
      const at = await evaluate(`(() => {
        const b = document.querySelector('.map').getBoundingClientRect();
        return { x: Math.round(b.left + b.width / 2),
                 y: Math.round(b.top + b.height / 2) };
      })()`);
      const state = `(() => ({
        scrollY: Math.round(window.scrollY),
        max: document.documentElement.scrollHeight - window.innerHeight,
        bounds: document.querySelector('.map').mapView().bounds,
        hint: (document.querySelector(
          '.maplibregl-cooperative-gesture-screen') || {}).textContent
          || null,
      }))()`;
      const before = await evaluate(state);
      await send('Input.dispatchMouseEvent', {
        type: 'mouseWheel', x: at.x, y: at.y, deltaX: 0, deltaY: 240,
        modifiers: 0,
      }, sessionId);
      await new Promise((go) => setTimeout(go, 900));
      const plain = await evaluate(state);
      await evaluate('window.scrollTo(0, 0)');
      await new Promise((go) => setTimeout(go, 400));
      await send('Input.dispatchMouseEvent', {
        type: 'mouseWheel', x: at.x, y: at.y, deltaX: 0, deltaY: -240,
        modifiers: 2,
      }, sessionId);
      await new Promise((go) => setTimeout(go, 1200));
      const ctrl = await evaluate(state);
      here.wheels = { before, plain, ctrl };
      // Put the view and the page back where they were.
      await open('/');
    }

    // SPEC 11.39. And the way back to the map, from the card.
    const back = await evaluate(
      "!!document.querySelector('.backtomap a')"
      + " && (document.querySelector('.backtomap a').click() || true)");
    await new Promise((go) => setTimeout(go, 1200));
    here.afterBack = await evaluate(LOOK);
    here.hasBack = back;

    // SPEC 11.39. The third way of choosing a place: the location
    // button. The position is the square the run covers, handed to the
    // page by the browser as a real fix, and the permission is granted
    // the way a reader grants it -- the page never asks for it twice and
    // never sees the position itself leave the page (11.19).
    if (PLAN.target) {
      await send('Browser.grantPermissions', {
        origin: `http://127.0.0.1:${port}`,
        permissions: ['geolocation'],
      });
      await send('Emulation.setGeolocationOverride', {
        latitude: PLAN.target[0] + 0.02,
        longitude: PLAN.target[1] - 0.03,
        accuracy: 40,
      }, sessionId);
      await evaluate("window.scrollTo(0, 0)");
      await new Promise((go) => setTimeout(go, 300));
      await evaluate("document.querySelector('.locate').click()");
      await new Promise((go) => setTimeout(go, 1800));
      here.afterLocate = await evaluate(LOOK);
      here.locateCard = await evaluate(INSIDE);
      await shoot(`${key}-located`);
    }

    // Back to the top of the page before the map is tapped: the tap is
    // aimed with the canvas's own screen coordinates, and after a search
    // the page has scrolled.
    await evaluate("window.scrollTo(0, 0)");
    await new Promise((go) => setTimeout(go, 400));

    // A tap on the map itself.
    const map = here.first.map;
    if (map && map.height > 40) {
      // Where a square is on the screen, worked out from the map's own
      // bounds: the view is all of India and the run a test publishes
      // covers a two degree box inside it, so the middle of the map is
      // open sea and only a published square will do.
      //
      // The square tapped is the first of that run's own squares that
      // nothing is covering. Which square it was, and what was in the way
      // of the others, is reported, so a check can say that none was
      // reachable rather than quietly passing.
      const wanted = PLAN.squares && PLAN.squares.length
        ? PLAN.squares : (PLAN.target ? [PLAN.target] : []);
      const pick = await evaluate(`(() => {
        const el = document.querySelector('.map');
        if (!el || !el.mapView) return { at: null, blocked: [] };
        const b = el.getBoundingClientRect();
        const [west, south, east, north] = el.mapView().bounds;
        const m = (lat) => Math.log(Math.tan(Math.PI / 4
          + (lat * Math.PI) / 360));
        const blocked = [];
        for (const [lat, lon] of ${JSON.stringify(wanted)}) {
          const x = b.left + ((lon - west) / (east - west)) * b.width;
          const y = b.top
            + ((m(north) - m(lat)) / (m(north) - m(south))) * b.height;
          if (x < b.left + 2 || x > b.right - 2
            || y < b.top + 2 || y > b.bottom - 2) {
            blocked.push([lat, lon, 'off the map']);
            continue;
          }
          const over = document.elementFromPoint(x, y);
          const free = over && over.closest('.mapwrap')
            && !over.closest('.mapkey') && !over.closest('.maplibregl-ctrl');
          if (free) {
            return { square: [lat, lon],
              at: [Math.round(x), Math.round(y)], blocked };
          }
          blocked.push([lat, lon,
            over ? String(over.className || over.tagName) : null]);
        }
        return { square: null, at: null, blocked };
      })()`);
      here.tappedFor = pick;
      if (pick.at) await tap(pick.at[0], pick.at[1]);
      here.afterMapTap = await evaluate(LOOK);
      here.card = await evaluate(INSIDE);
      await shoot(`${key}-tapped`);

      // SPEC 11.40. And a day pill, tapped: the pills carry counts now
      // and they are still the control that chooses the day. The one
      // tapped is the last of the five, which is never the one the page
      // opens on.
      const pills = await evaluate(
        "document.querySelectorAll('.days .radios button').length");
      if (pills > 1) {
        await evaluate(`(() => {
          const all = document.querySelectorAll('.days .radios button');
          all[all.length - 1].click();
          return true;
        })()`);
        await new Promise((go) => setTimeout(go, 1200));
        here.afterDayTap = await evaluate(LOOK);
        here.dayTapCard = await evaluate(INSIDE);
        await shoot(`${key}-dayTapped`);
      }
    }
    out.phone[key] = here;
  }

  // SPEC 11.41. The note beside "Which day?" is drawn only on the
  // mornings when the five days do not include today, and that is a fact
  // about the reader's own clock -- so the only way to measure it is to
  // set the clock. The page is opened twice with the visitor's own Date
  // replaced: once on the first forecast day, where the first pill reads
  // "Today" and the note must be absent, and once on the day before it,
  // where the pill reads "Tomorrow" and the note must be there.
  //
  // Date is replaced rather than the run being rewritten, because the
  // run is the same run in both cases: what changes between a reader at
  // 9 am and the same reader at 1 pm is only which day they are in.
  if (PLAN.clocks) {
    out.clock = {};
    await size(1366, 768);
    for (const [when, at] of Object.entries(PLAN.clocks)) {
      const shim = await send('Page.addScriptToEvaluateOnNewDocument', {
        source: `(() => {
          const fixed = ${at};
          const Real = Date;
          const Fake = new Proxy(Real, {
            construct: (target, args) => (args.length
              ? new target(...args) : new target(fixed)),
            apply: () => new Real(fixed).toString(),
          });
          Fake.now = () => fixed;
          window.Date = Fake;
        })()`,
      }, sessionId);
      await open('/');
      out.clock[when] = await evaluate(LOOK);
      await shoot(`clock-${when}`);
      await send('Page.removeScriptToEvaluateOnNewDocument',
        { identifier: shim.identifier }, sessionId);
    }
  }
  stop(out);
} catch (error) {
  stop({ skip: `the browser check could not run: ${error.message}` });
}
"""



def nearest_city(square: list[float]) -> str:
    """The city of SPEC 11.28 nearest a square, for the search to find.

    The run a test publishes covers a two degree box, and a search for a
    city outside it answers "outside the forecast area" -- which is a
    true answer and not the one the check is about. So the city searched
    for is the nearest one to the square the same run is tapped at.
    """
    towns = load_towns()
    lat, lon = square
    best = min(towns, key=lambda town: (town["lat"] - lat) ** 2
               + (town["lon"] - lon) ** 2)
    return best["name"]


@pytest.fixture(scope="module")
def viewport(tmp_path_factory):
    """The built site, measured in a real browser at a phone's size.

    A headless browser has no address bar and no system bar, so this is a
    check of a short screen and not of the bug of SPEC 11.35 itself: what it
    proves is that the bar, the panel and the map are laid out inside the
    viewport they are given, which is the rule that bug broke. The bug's own
    measurement, on the real geometry, is in SPEC 11.35.

    The API is real: a small run is written and published through the real
    publisher into a directory, served over HTTP, and `api/health` and
    `api/place` are imported and run against it. So the panel measured here
    holds real counts, a real chip and a real sentence, and not a drawing of
    them.

    Chrome is driven over the DevTools protocol by node's own WebSocket, so
    nothing is installed for this. With no browser on the machine the test
    skips and says so.
    """
    web = ROOT / "web"
    if node is None or not (web / "node_modules" / "vite").exists():
        pytest.skip("node and the web dependencies are needed to measure")

    tmp = tmp_path_factory.mktemp("viewport")
    with pytest.MonkeyPatch.context() as mp:
        india = small_grid(mp)
        live = tmp / "live"
        live.mkdir()
        mp.setattr(publish, "LIVE", live)
        mp.setattr(publish, "run_dir", lambda run_id: live / run_id)
        write_run(live, RUN, india)
        # Every India square of that run, for the tap on the map to aim
        # at: the harness takes the first of them that nothing on the map
        # is covering, and says what was over the others (SPEC 11.39).
        rows, cols = np.nonzero(india)
        every = [[float(cfg.INDIA_LATS[row]), float(cfg.INDIA_LONS[col])]
                 for row, col in zip(rows, cols)]
        middle = len(every) // 2
        target = every[middle]
        # The middle one first, so the square tapped is the same square it
        # has always been wherever nothing is in the way of it.
        squares = [target] + [one for one in every if one != target]
        # The run is given a run time two hours ago. Everything else about
        # it is the fixture's own, but a run time from last week would put
        # the stale banner of 11.8 across the page, and this is a
        # measurement of the page a reader sees on an ordinary day.
        where = live / RUN / "manifest.json"
        manifest = json.loads(where.read_text(encoding="utf-8"))
        fresh = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
        manifest["run_time_utc"] = fresh.isoformat()
        manifest["run_time_ist"] = fresh.astimezone(
            dt.timezone(dt.timedelta(hours=5, minutes=30))).isoformat()
        where.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # SPEC 11.41. The first of the five days, which is what the day
        # note is about: the browser is opened once with its clock on
        # that day and once on the day before it.
        first_day = str(json.loads((live / RUN / "days.json")
                                   .read_text(encoding="utf-8"))
                       [0]["from_ist"])[:10]
        served = tmp / "store"
        answer = publish.publish(FakeStore(), RUN, work_dir=served,
                                 mark=False)
        assert answer["published"] is True

    # The page fetches the counts files from the store itself, which is a
    # different origin from the page: the real store sends the header that
    # allows it (SPEC 11.13) and this one has to as well, or the browser
    # blocks them and the map never draws.
    class Open(Quiet):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

    handler = type("Rooted", (Open,),
                   {"__init__": lambda self, *a, **kw: Open.__init__(
                       self, *a, directory=str(served), **kw)})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        out = web / "node_modules" / ".view-test"
        vite = web / "node_modules" / ".bin" / (
            "vite.cmd" if os.name == "nt" else "vite")
        done = subprocess.run(
            [str(vite), "build", "--outDir", "node_modules/.view-test",
             "--emptyOutDir", "--logLevel", "error"],
            capture_output=True, text=True, encoding="utf-8", check=False, cwd=web, shell=False)
        assert done.returncode == 0, f"vite failed: {done.stdout}{done.stderr}"

        runner = out / "measure.mjs"
        runner.write_text(VIEWPORT_HARNESS, encoding="utf-8")
        plan = {
            "api": str(ROOT / "api"),
            "sizes": [[390, 664], [390, 844], [360, 640],
                      [320, 568], [1440, 900], [1366, 768],
                      [1366, 650], [1280, 720], [1024, 768]],
            "target": target,
            "squares": squares,
            # A city inside the run a test publishes, so searching for it
            # answers with counts rather than with "not forecast".
            "city": nearest_city(target),
            # SPEC 11.41. Two readings of the same run by two readers:
            # 6 am IST on the run's own first day, where that day is
            # today, and 6 am the morning before, where it is tomorrow
            # and the day the reader is in is not one of the five.
            "clocks": {
                "today": int(dt.datetime.fromisoformat(
                    f"{first_day}T06:00:00+05:30").timestamp() * 1000),
                "tomorrow": int((dt.datetime.fromisoformat(
                    f"{first_day}T06:00:00+05:30")
                    - dt.timedelta(days=1)).timestamp() * 1000),
            },
            "firstDay": first_day,
            "shots": os.environ.get("SHOTS") or None,
        }
        done = subprocess.run(
            [node, str(runner), str(out), json.dumps(plan)],
            capture_output=True, text=True, encoding="utf-8", check=False, cwd=web,
            timeout=600, env={**os.environ, "STORE_BASE_URL": base})
        assert done.returncode == 0, f"the browser check failed: {done.stderr}"
        seen = json.loads(done.stdout)
        if "skip" in seen:
            pytest.skip(seen["skip"])
        return seen
    finally:
        server.shutdown()
        server.server_close()


# ------------------------- SPEC 11.41: the repository's own documents

README = ROOT / "README.md"
DECISIONS = ROOT / "DECISIONS.md"

# The last section of README.md: the author's own account of how this
# repository was built and what help was used. It is written out here in
# full on purpose -- a test that compared the file with a copy of itself
# would allow any edit at all -- and the README has to match it
# character for character.
DISCLOSURE = """\
## How this was built, and the help I used

All of the code, data processing, tests and deployment in this repository were produced by Claude Code in a single session, from 11 November 2026 at 11:56 pm IST to its final commit on 14 November 2026. The full session log is submitted with this application. Before the session I practised the downloads, map and checks on my own; none of that practice code or data was reused, and I said so in the session's first prompt.

Alongside the session, I used a separate Claude chat in the Claude desktop app as an advisor. I used it to review Claude Code's reports, point out risks and gaps, explain things I didn't understand, keep track of my schedule, and polish the prompts I sent to Claude Code. Every prompt went through me: I read it, questioned it, often asked for changes, and decided whether and when to send it. I asked it repeatedly to challenge me rather than agree with me. Some independent checks came from that chat, such as recomputing one remapped square by hand (HC5) and checking news reports of the 406 mm day.

For the user interface I also used ChatGPT and a second Claude chat to critique the site, compare it with other weather websites, and produce mock-up images that I used as design references. None of their code went into this repository.

The decisions were mine throughout. I read every report and prompt, asked questions until I understood them, stuck to my plan where I believed it was right, and changed it when the evidence said so. There were many more such decisions; these are some of the major ones:

- **Found a phone bug on my own Samsung A32** (and my mother's Oppo): the "Show the details" handle was hidden under the phone's bottom bar, so the forecast panel couldn't be opened. Desktop testing had not shown it. The cause turned out to be a layout rule, and it was fixed and tested on both phones.
- **Noticed the map didn't move to a searched place:** when I used "Use my location" or searched for Delhi, the map circled the place but didn't slide to it, so I asked for it to move there automatically.
- **Caught that the hand checks had drifted from my original plan:** several checks I had planned (failure handling, a comparison with ECMWF's own published figure, real report-card rows, a monsoon map) had been renumbered or not done. I had them added, and one of them found a mistake in the specification.
- **Asked for every line on the "How we checked" page to be verified against its file,** which corrected two entries (one check had run on three dates, not one; another covered five squares, not one).
- **Found gaps in the search:** it said "town" but only knew cities, and typing a state such as West Bengal found nothing. That led to the city wording, state search and old city names.
- **Pushed back on wording a beginner wouldn't understand:** for example "1 cm deep" for 10 mm, and "tap a square" when the squares aren't visible until you zoom in.
- **Made sure dry places read correctly and the track record states its period:** 0 of 51 runs in Delhi in November is the right answer, not missing data, and the report card says its record comes mostly from the monsoon.
- **Checked the GitHub scheduler myself,** found it firing late (in the evening or at night, never when the new forecast arrives around midday), ran the forecast by hand when needed, and designed a backup daily trigger, which I chose to leave as future work so the last hours went to the interface.
- **Dropped the Time Machine feature** I had planned, to spend the last day on the interface after real users struggled with it.
- **Kept the security rules myself:** I never put a password or token in a prompt; I created the secrets in the GitHub and Vercel dashboards by hand.

To test the interface, I asked my mother and several friends to use the site without help and tell me what they struggled with. They all said much the same: it was hard to see where to start, there was too much text, and the numbers were hard to understand. I also asked for the site to be compared with other weather apps. That feedback is the reason for the final, simpler design.

This section was drafted with the help of the same Claude chat and edited by me.
"""


def test_the_readme_last_section_is_the_disclosure_character_for_character():
    """SPEC 11.41. The author's own words, unchanged.

    This section is the one part of the repository that is not the
    project's own prose: it says who built what, which tools helped, and
    which decisions were the author's. Nothing may tidy it.
    """
    said = README.read_text(encoding="utf-8")
    at = said.find("## How this was built")
    assert at > 0, "the section is missing"
    assert said[at:] == DISCLOSURE, "the section does not match"
    # And it is the last thing in the file: nothing is appended after a
    # statement about who wrote the rest.
    assert said.count("## How this was built") == 1


def test_every_link_in_the_readme_resolves():
    """SPEC 11.41. Every relative link is a file that exists.

    The hand-check links are the point of this: a table of fourteen
    checks each naming its own output file is only evidence while the
    files are there.
    """
    said = README.read_text(encoding="utf-8")
    links = re.findall(r"\]\(([^)]+)\)", said)
    assert len(links) >= 20, len(links)
    checks = 0
    for link in links:
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = ROOT / link.split("#")[0]
        assert target.exists(), link
        if "handchecks/results/" in link:
            checks += 1
            assert target.stat().st_size > 0, link
    # Every hand check that wrote a file is linked to its file.
    assert checks >= 14, checks
    for name in ("hc1_20260513.txt", "hc5_cell.csv", "hc_align.txt",
                 "hc_fail.csv", "hc_ecmwf.csv", "hc_report.csv",
                 "hc_ghats.csv", "hc9_bucket.csv"):
        assert f"handchecks/results/{name}" in said, name
    # HC4 has no file of its own and says so rather than linking to
    # nothing; HC10 is the checklist at the end of the build.
    assert "the file was deleted after it was read" in said
    assert "the final checklist, done at the end" in said
    # The live site, by its one address.
    assert "https://precipitation-forecast-app.vercel.app" in said


def test_the_readme_counts_the_suite_it_claims():
    """SPEC 11.41. The number of tests in the README is the number there is.

    Both numbers: what `pytest` collects, which is what a reader would
    see, and how many `def test_` functions are behind them.
    """
    said = README.read_text(encoding="utf-8")
    functions = sum(
        len(re.findall(r"^def test_", path.read_text(encoding="utf-8"),
                       re.M))
        for path in sorted((ROOT / "tests").glob("test_*.py")))
    files = len(list((ROOT / "tests").glob("test_*.py")))
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--collect-only"],
        capture_output=True, text=True, encoding="utf-8", check=False,
        cwd=ROOT)
    assert done.returncode == 0, done.stdout[-2000:]
    found = re.search(r"(\d+) tests? collected", done.stdout)
    assert found, done.stdout[-2000:]
    collected = int(found.group(1))
    want = (f"runs {collected} tests from {functions} test functions in "
            f"{files} files")
    assert want in re.sub(r"\s+", " ", said), want


@needs_node
def test_the_readme_track_record_is_the_report_cards_own_summary(pages):
    """SPEC 11.41. One summary of the record, in two places.

    The README's track record paragraph is the report card's TL;DR,
    which is counted from summary.json -- so the repository cannot claim
    one thing about the record while the site says another.
    """
    flat = re.sub(r"\s+", " ", README.read_text(encoding="utf-8"))
    for sentence in pages([["tldr", "summary"]])[0]["sentences"]:
        assert sentence in flat, sentence


@needs_node
def test_the_readme_and_the_page_give_the_same_three_steps(forecast_words):
    """SPEC 11.41. The mini user manual, in the README and on the page."""
    flat = re.sub(r"\s+", " ", README.read_text(encoding="utf-8"))
    every = " ".join(words_of(html) for html in forecast_words
                     if isinstance(html, str))
    for step in ("Search your city, or just tap the map.",
                 "Pick the day and the amount of rain you care about.",
                 "That's it, your forecast shows up."):
        assert step in flat, ("README", step)
        assert step in every, ("the page", step)


def test_the_decisions_file_records_every_choice_it_was_asked_for():
    """SPEC 11.41. The architecture audit, one entry each with its reason.

    Seven things the code does not explain by itself. Each entry is
    checked for its subject and for something only its own reason would
    say, so an entry cannot pass by naming the subject alone.
    """
    flat = re.sub(r"\s+", " ", DECISIONS.read_text(encoding="utf-8"))
    for subject, reason in (
            ("api/health.mjs", "snap.js"),
            ("normal merge commits", "never been force-pushed"),
            ("config/regions.json", "SHA-256"),
            ("forecast.yml", "concurrency group"),
            ("config/features.json", "does not exist"),
            ("label_colours", "results-v1"),
            ("time-machine", "never merged")):
        assert subject in flat, subject
        assert reason in flat, (subject, reason)
    # The two claims about the repository that can be checked here.
    assert not (ROOT / "config" / "features.json").exists()
    assert (ROOT / "config" / "regions.json").exists()


def test_the_four_late_spec_sections_are_drafted():
    """SPEC 11.41. 7, 9, 10 and 12 were empty; each has its paragraph now.

    They were on the "Sections still to draft" list from the first draft
    to the last day: the sections that fix rules before results had to be
    written first, and these four describe what was built to carry them
    out.
    """
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    heads = re.findall(r"^## (\d+)\. ", spec, re.M)
    assert heads == [str(number) for number in range(1, 13)], heads
    for number, must in ((7, "pipeline/"), (9, "forecast.yml"),
                         (10, "DevTools protocol"), (12, "HC10")):
        body = spec.split(f"\n## {number}. ")[1].split("\n## ")[0]
        assert len(body) > 600, (number, len(body))
        assert must in body, (number, must)
        # Each says when it was drafted, because every other section of
        # this file was written before the thing it describes.
        assert "14 November 2026" in body, number
    # And nothing is left on the list.
    left = spec.split("## Sections still to draft")[1]
    assert left.strip().startswith("None."), left[:120]


@needs_node
@pytest.mark.parametrize("size", ["390x664", "1440x900"])
def test_the_whole_of_india_is_in_view_on_first_load(viewport, size):
    """SPEC 11.38. 6 to 38 N and both coasts, before anybody touches it.

    The zoom buttons are 58 pixels tall in the top right corner, and the
    fit padded the whole top edge by 68 of a phone's 261 pixel map. The
    fit then wanted a zoom below the minimum, was clamped there, and drew
    18.7 to 38.6 N: Kerala, Tamil Nadu, Karnataka and half of Andhra
    Pradesh were not on the screen at all when the page opened.
    """
    here = viewport["phone"][size]
    view = here["first"]["view"]
    assert view, f"the map did not report a view at {size}"
    west, south, east, north = view["bounds"]
    # The box of SPEC 1.4, with a tenth of a degree of slack for the
    # floating point of a projection and back.
    assert south <= 6.0 + 0.1, (size, south)
    assert north >= 38.0 - 0.1, (size, north)
    assert west <= 68.0 + 0.1, (size, west)
    assert east >= 98.0 - 0.1, (size, east)
    # And it is not fitted by zooming out to half of Asia either: the view
    # is never more than three times the box it is fitting.
    assert (north - south) <= 3 * 32, (size, north - south)
    assert (east - west) <= 3 * 30, (size, east - west)


@needs_node
def test_neither_document_page_is_cut_off_at_390_by_664(viewport):
    """SPEC 11.35. The other two pages are documents, not the shell."""
    for path in ("/report-card", "/how-we-checked"):
        page = viewport["pages"][path]
        assert page["docScrollWidth"] <= 390, path
        assert page["bodyScrollWidth"] <= 390, path
        # And with a font wider than this machine's, which is what another
        # machine is: a table may scroll inside itself, the page may not.
        assert page["wideFontScrollWidth"] <= 390, (
            path, page["wideFontScrollWidth"])


@needs_node
def test_the_report_card_grid_fits_a_390_pixel_screen(viewport):
    """SPEC 11.36. No sideways scroll, nothing cut, "1 mm" on one line."""
    page = viewport["pages"]["/report-card"]
    assert page["chips"] == 60
    assert page["sideways"] == 0, (
        "a grid scrolls sideways at 390 pixels, which hides days 4 and 5")
    assert page["chipsCut"] == 0, "a chip's words are cut off"
    assert page["rowHeads"], "no row headings were found"
    for head in page["rowHeads"]:
        assert head["nowrap"], head
        assert head["fits"], head
    assert [h["text"] for h in page["rowHeads"][:3]] == ["1 mm", "10 mm",
                                                         "50 mm"]
    # The 60-label grid is the one table that may not scroll sideways, at
    # this machine's font or any other.
    assert page["wideFontGridOverflow"] == 0
    assert page["wideFontScrollWidth"] <= 390, page["wideFontScrollWidth"]


@pytest.fixture(scope="module")
def built_css(tmp_path_factory):
    """The stylesheet as it is actually served, not as it is written.

    This exists because the two are not the same. The fallback of 11.35 was
    first written as a `100vh` line immediately before its `100dvh` line,
    which is the ordinary way to write one; the minifier dropped it, because
    a declaration the next line overrides is dead weight to it, and the
    stylesheet that went to readers carried `dvh` alone. A test that reads
    `src/styles.css` cannot see that. This one reads the build.
    """
    web = ROOT / "web"
    if node is None or not (web / "node_modules" / "vite").exists():
        pytest.skip("node and the web dependencies are needed to build")
    out = tmp_path_factory.mktemp("css")
    vite = web / "node_modules" / ".bin" / (
        "vite.cmd" if os.name == "nt" else "vite")
    done = subprocess.run(
        [str(vite), "build", "--outDir", str(out), "--emptyOutDir",
         "--logLevel", "error"],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=web, timeout=600)
    assert done.returncode == 0, f"vite failed: {done.stdout}{done.stderr}"
    sheets = sorted((out / "assets").glob("*.css"))
    assert sheets, "the build wrote no stylesheet"
    return "\n".join(path.read_text(encoding="utf-8")
                     for path in sheets)
def test_every_viewport_height_is_the_map_and_has_a_dvh_pair():
    """SPEC 11.35, as SPEC 11.39 leaves it.

    A phone's `100vh` includes the strip behind the browser's bars and
    `100dvh` does not, and 11.35 was that bug: the shell asked for 100dvh
    and the panel for a share of it, so the handle ended up behind the
    bars. The shell has no height at all now, and the one height on this
    page that is a share of anything is the map's -- which can be, because
    the page scrolls and the map cannot squeeze another block off it.

    Every `vh` rule must have a `dvh` rule beside it, in its own
    @supports block, because a minifier drops a declaration the next line
    overrides: written as two lines in one rule the built stylesheet
    carried the dvh alone and a browser that had never heard of it got no
    height at all.
    """
    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    # Nothing but the map's own height token asks for a share of the
    # viewport, and SPEC 11.41 leaves one box reading it. 11.40 had two:
    # the panel beside the map was exactly as tall as the map, so that
    # the key at its top could stay put while the card under it scrolled
    # inside itself. That was the second scrollbar item 8 took out -- the
    # panel is as tall as its own contents now and the map keeps its
    # place by being sticky -- so the only box whose height is a share of
    # the screen is the map's own.
    for rule in re.findall(r"[^{}]*\{[^{}]*?\d+d?vh[^{}]*\}", bare):
        head = rule.split("{")[0].strip().split("\n")[-1].strip()
        assert head == ".forecast", head
        assert "--maph:" in rule, rule
    # And the token is read by those two boxes and by nothing else.
    readers = set()
    for rule in re.findall(r"[^{}]*\{[^{}]*?var\(--maph\)[^{}]*\}", bare):
        readers.add(rule.split("{")[0].strip().split("\n")[-1].strip())
    assert readers == {".mapwrap"}, readers
    vh = re.findall(r"min\((\d+)vh", bare)
    dvh = re.findall(r"min\((\d+)dvh", bare)
    assert vh and vh == dvh, (vh, dvh)
    # And each dvh rule is inside an @supports that asks whether the unit
    # exists at all.
    for at in [m.start() for m in re.finditer(r"min\(\d+dvh", bare)]:
        before = bare[:at]
        assert "@supports (height: 1dvh)" in before
        assert before.rindex("@supports (height: 1dvh)") > before.rindex("}\n\n")


# ------------------------------------------- SPEC 11.36, the report card

@needs_node
def test_the_marked_groups_are_the_ones_the_file_says_beat_the_usual_rain(
        pages, rendered):
    """SPEC 11.36. Read from site_summary.json, never worked out again."""
    summary = summary_file()
    grids = pages([["gridFor", "summary", region]
                   for region in summary["regions"]])
    marked = 0
    for region, grid in zip(summary["regions"], grids):
        for row in grid:
            for cell in row["cells"]:
                group = next(
                    one for one in summary["groups"]
                    if one["region"] == region
                    and one["lead_day"] == cell["lead"]
                    and one["threshold_mm"] == row["threshold"])
                want = bool(group["conditions"]["skill_above_zero"]["pass"])
                assert cell["beat"] is want, (region, row["threshold"],
                                              cell["lead"])
                marked += want
    expected = sum(1 for group in summary["groups"]
                   if group["conditions"]["skill_above_zero"]["pass"])
    assert marked == expected
    assert expected == 20, "today's record; the rest of this test is general"

    html = rendered["pages"]["report_card"]
    # One mark per marked group, and one more in the key line that explains
    # what the mark means.
    assert html.count('class="beat"') == expected + 1
    assert (f"It is on {expected} of the {len(summary['groups'])}."
            in html), "the key line does not carry the count"
    assert "better than the usual rain for this place and month, but still" \
        in html
    # A mark, not a tick, and not a colour on its own.
    assert "&#x2713;" not in html and "\u2713" not in html
    for cell in re.findall(r'<span class="chip [a-z]+"[^>]*>(.*?)</span>',
                           html):
        assert "+" not in cell or '<span class="beat"' in cell


@needs_node
def test_the_headline_says_all_sixty_when_it_is_all_of_them(pages, rendered):
    """SPEC 11.36. "and all 60 were too confident", not "and 60 of them"."""
    summary = summary_file()
    said = pages([["headline", "summary"]])[0]
    honest = sum(1 for group in summary["groups"]
                 if not group["conditions"]["small_honesty_error"]["pass"])
    total = len(summary["groups"])
    if honest == total:
        assert f"all {total} were too confident" in said["sentence"]
        assert f"{honest} of them were too confident" not in said["sentence"]
    else:
        assert f"{honest} of them were too confident" in said["sentence"]
    assert said["sentence"] in rendered["pages"]["report_card"].replace(
        "&quot;", '"')


@needs_node
def test_a_thin_two_degree_cell_says_it_has_too_few_squares(rendered):
    """SPEC 11.36. The dashed edge, said in words a reader can act on."""
    html = rendered["pages"]["how_we_checked"]
    assert "shown, but too few squares to give a number" in html
    assert "drawn and not read from" not in html
    for page in rendered["pages"].values():
        assert "drawn and not read from" not in page


# ------------------------------- SPEC 11.36, the list of checks and ECMWF

@needs_node
def test_every_hand_check_on_the_page_links_to_something_that_exists(
        rendered):
    """SPEC 11.36. No count out of date, and no link to a missing file."""
    html = rendered["pages"]["how_we_checked"]
    assert "nine checks" not in html and "nine hand checks" not in html

    names = re.findall(r'<a href="([^"]+)"><strong>(HC[-A-Z0-9]+)</strong>',
                       html)
    found = [name for _, name in names]
    assert found == ["HC1", "HC2", "HC3", "HC4", "HC-ALIGN", "HC5", "HC6",
                     "HC7", "HC8", "HC9", "HC-FAIL", "HC-ECMWF", "HC-REPORT",
                     "HC-GHATS", "HC10"], found

    results = ROOT / "handchecks" / "results"
    for href, name in names:
        if "/handchecks/results/" in href:
            file = href.rsplit("/", 1)[-1]
            assert (results / file).exists(), (name, file)
        else:
            assert href.endswith("SPEC.md#the-hand-checks"), (name, href)
            assert name in ("HC4", "HC10"), name

    # HC10 is listed as what it is: not done, and nothing leaning on it.
    hc10 = html[html.index("HC10"):]
    assert "not done yet" in hc10[:400], hc10[:400]
    assert "passed" not in hc10[:400]


@needs_node
def test_the_list_names_every_file_each_check_wrote(rendered):
    """SPEC 11.36. A check run on three dates wrote three files; a line that
    links one of them tells a reader the check was done once.

    The guard is the directory, not the list: every result file that exists
    must be linked, so adding a run without adding its link fails here.
    """
    html = rendered["pages"]["how_we_checked"]
    linked = set(re.findall(r'/handchecks/results/([^"]+)"', html))
    on_disk = {path.name
               for path in (ROOT / "handchecks" / "results").iterdir()
               if path.is_file() and path.suffix in (".txt", ".csv")}
    # The images and the page dump are shown or linked elsewhere; the files
    # a reader is sent to read are these.
    missing = sorted(on_disk - linked - {"hc_fail_stale.txt",
                                         "hc_fail_13nov.txt"})
    assert missing == [], f"written but not linked: {missing}"

    # And the dates in the list are the dates in the file names.
    for name, dates in (("HC1", ["13 May 2026", "1 August 2026",
                                 "25 October 2026"]),
                        ("HC2", ["13 May 2026", "25 October 2026"]),
                        ("HC3", ["13 May 2026", "1 August 2026",
                                 "25 October 2026"])):
        line = html[html.index(f"<strong>{name}</strong>"):]
        line = line[:line.index("</li>")]
        for when in dates:
            assert when in line, (name, when, line[:300])
def test_the_list_says_how_many_squares_hc8_covered():
    """SPEC 11.25 and 11.36. Five squares, counted from the file itself."""
    import csv as csv_module

    with (ROOT / "handchecks" / "results" / "hc8_map_square.csv").open(
            encoding="utf-8", newline="") as fh:
        rows = list(csv_module.DictReader(fh))
    assert len(rows) == 5, len(rows)
    assert {row["verdict"] for row in rows} == {"pass"}

    page = (ROOT / "web" / "src" / "HowWeChecked.jsx").read_text("utf-8")
    assert "five squares on the live map" in page
    assert "one square on the live map" not in page
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    assert "| HC8 | five squares on the live map" in spec


@needs_node
def test_the_ecmwf_section_carries_the_hand_check_s_own_numbers(rendered):
    """SPEC 11.36. The page quotes HC-ECMWF, in runs and never in points."""
    import csv as csv_module

    rows = {}
    with (ROOT / "handchecks" / "results" / "hc_ecmwf.csv").open(
            encoding="utf-8") as fh:
        for row in csv_module.reader(fh):
            if len(row) >= 2:
                rows[row[0]] = row[1]

    squares = rows["squares compared"]
    runs = float(rows["mean size of the difference, as runs of 51"].split()[0])
    apart = rows["squares differing by more than 5 runs of 51"]

    html = rendered["pages"]["how_we_checked"]
    assert squares == "4613"
    assert "4,613" in html
    assert f"{apart} of the 4,613 squares were more than 5 runs apart" in html
    assert 0.05 <= runs < 0.15, runs
    assert "about a tenth of one run" in html
    assert ("This shows the counting is right. It does not show the model "
            "is right; that is what the report card checks.") in html

    # It is a check of our arithmetic, and it stays off the two pages that
    # answer "what is the forecast" and "how good has it been".
    assert "a tenth of one run" not in rendered["pages"]["report_card"]
    # The report card names the model, as the period sentence must; what it
    # must not carry is this comparison.
    assert "its own figure" not in rendered["pages"]["report_card"]
    assert "more than 5 runs apart" not in rendered["pages"]["report_card"]


# ------------------------------------------ SPEC 11.37, the phone's bottom bar

@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "1440x900"])
def test_tapping_the_map_answers_in_the_card(viewport, size):
    """SPEC 11.30 and 11.39. The answer is on the page, not in a drawer.

    A tap used to open the bottom sheet, which is what a result being
    hidden behind a closed bar looks like when it is fixed badly. There is
    no bar: the card is the last block of the page on a phone and the
    column beside the map on a desktop, and a tap fills it in.
    """
    here = viewport["phone"][size]
    assert here["tappedFor"]["square"], here["tappedFor"]["blocked"]
    card = here["card"]
    assert card, "no card was measured"
    assert card["has"]["counts"], "no counts in the card"
    assert card["has"]["trust"], "no trust label in the card"
    # The three amount rows are inside the closed section, and it is shut.
    assert card["has"]["moreShut"] is True
    # The place name and the headline are the card's first two lines.
    assert "of the 51 runs bring" in card["cardText"], card["cardText"]
    # And the map is still a map: nothing about choosing a place takes its
    # height away, because nothing is drawn over it.
    after = here["afterMapTap"]
    assert after["map"]["height"] >= 280, after["map"]
    assert after["map"]["height"] == here["first"]["map"]["height"]


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568"])
def test_the_card_can_be_read_on_a_phone(viewport, size):
    """SPEC 11.37 item by item, as SPEC 11.39 leaves it.

    Three text sizes and no more, every sentence at 15 pixels or over,
    nothing at all under 13, and every tap target in the card 44 pixels
    tall. The sizes are the same three at every width, which is why this
    runs at three widths and expects one answer.
    """
    inside = viewport["phone"][size]["card"]
    assert inside, "no card was measured"
    sizes = inside["sizes"]

    # At least 15px: the lines that carry the answer.
    for what in ("chosenRow", "rowWhat", "trustChip", "trustLine",
                 "notPromise", "headline", "placeName", "moreSummary"):
        assert sizes[what] is not None, what
        assert sizes[what] >= 15, (what, sizes[what])
    if sizes["pastLine"] is not None:
        assert sizes["pastLine"] >= 14, sizes["pastLine"]

    # The place name is the largest thing in it, because it is what the
    # card is about.
    assert sizes["placeName"] > sizes["headline"], sizes

    # SPEC 11.39: three text sizes in the card and no more. It had nine.
    used = sorted(float(px) for px in inside["textSizes"])
    assert len(set(used)) <= 3, inside["textSizes"]

    # Nothing in the card under 13px, and every tap target 44px tall.
    assert inside["belowThirteen"] == [], inside["belowThirteen"]
    assert inside["tapTargetsUnder44"] == [], inside["tapTargetsUnder44"]


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568"])
def test_the_three_rows_a_thumb_hits_are_44_pixels_and_15_point(
        viewport, size):
    """SPEC 11.38, as SPEC 11.39 leaves it. Every control above the card.

    The review measured the day buttons at 12.2 point and 29.8 pixels tall
    and the menu links at 13.6 and 30.4 -- on the one bar a reader has to
    use before they can read anything at all. The rows are the five days,
    the three amounts, the search box, the location button and the menu;
    on a desktop the menu is three links instead, and the sweep takes
    whichever of the two the stylesheet has drawn.
    """
    rows = viewport["phone"][size]["first"]["rows"]
    assert len(rows) >= 11, rows
    for name, height, size_px, text in rows:
        assert height >= 43.5, (size, name, height, text)
        assert size_px >= 15, (size, name, size_px, text)


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568"])
def test_nothing_on_the_forecast_page_is_under_twelve_pixels(viewport, size):
    """SPEC 11.38. The page's own floor, at every phone width.

    MapLibre's own controls are skipped: their type is the library's and
    is set by the stylesheet to 12 where it can be, but the buttons are
    not ours to lay out.
    """
    small = viewport["phone"][size]["first"]["underTwelve"]
    assert small == [], (size, small)


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568"])
def test_nothing_scrolls_sideways_on_a_phone(viewport, size):
    """SPEC 11.38, and 11.29 before it."""
    shut = viewport["phone"][size]["first"]
    width = int(size.split("x")[0])
    assert shut["docScrollWidth"] <= width, (size, shut["docScrollWidth"])
    assert shut["bodyScrollWidth"] <= width, (size, shut["bodyScrollWidth"])


@needs_node
def test_the_white_line_is_in_how_to_read_the_map_on_a_phone(viewport):
    """SPEC 11.37 item 5, as SPEC 11.39 leaves it: moved, never dropped.

    The line was in the legend, where a phone had no room for it, and
    11.37 moved it into the block of explanation in the panel. 11.39 made
    that block a page, so the line is on the page -- in the nine-row key,
    with the beige one beside it -- and the legend still carries both at
    desktop width and neither on a phone.
    """
    seen = viewport["phone"]["390x664"]["afterMapTap"]
    # SPEC 11.39: the line is one of the nine rows of the key, which is on
    # the map at every width -- under it on a phone -- and on the How to
    # read this map page. Nothing in the card explains a colour.
    assert seen["whiteHere"] is False
    assert "White: no forecast for this spot" in seen["keyRows"]
    assert "Beige: land outside India, not forecast" in seen["keyRows"]
    # And the page that does say it is a page a reader can reach from here.
    said = (ROOT / "web" / "src" / "Legend.jsx").read_text("utf-8")
    assert "White: no forecast for this spot" in said
    assert "Beige: land outside India, not forecast" in said
    page = (ROOT / "web" / "src" / "HowToRead.jsx").read_text("utf-8")
    assert "<KeyRows />" in page
    panel = PANEL.read_text("utf-8")
    # SPEC 11.39. The link lives with the menu, not in the card: the card,
    # the controls and the page's own footer all point at one page or the
    # other, and a component in the card that the controls import would be
    # a circle between two modules.
    nav = (ROOT / "web" / "src" / "TopNav.jsx").read_text("utf-8")
    assert "export function HowToReadLink" in nav
    assert "/how-to-read" in nav
    assert "<HowToReadLink onGo={onGo} />" in panel


# ------------------- SPEC 11.20 and 11.33: the panel's and the bar's own words

# What the forecast page may say that the two document pages may not. The
# panel's job is to stop a reader reading its counts as odds, and it does
# that by naming the thing they are not: the heading "It is not a
# probability." and the sentence of 11.21 under it. The word is allowed in
# those two sentences and nowhere else, and the test pins the sentences
# rather than the word so the allowance cannot spread.
FORECAST_ALLOWED = {
    "probability": ("it is not a probability.",
                    "these are counts out of 51 runs, not a "
                    "calibrated probability."),
}


@pytest.fixture(scope="module")
def forecast_words(tmp_path_factory):
    """The panel and the bar rendered to text, over every state they have.

    Real `/api/place` answers drive it: a small run is published through the
    real publisher into a temporary directory, served over HTTP, and the
    real `api/place.mjs` is asked for several squares. What is swept is
    therefore the panel a reader is given and not a drawing of one.
    """
    web = ROOT / "web"
    if node is None or not (web / "node_modules" / "vite").exists():
        pytest.skip("node and the web dependencies are needed to render")

    tmp = tmp_path_factory.mktemp("forecast")
    with pytest.MonkeyPatch.context() as mp:
        india = small_grid(mp)
        live = tmp / "live"
        live.mkdir()
        mp.setattr(publish, "LIVE", live)
        mp.setattr(publish, "run_dir", lambda run_id: live / run_id)
        write_run(live, RUN, india)
        served = tmp / "store"
        answer = publish.publish(FakeStore(), RUN, work_dir=served, mark=False)
        assert answer["published"] is True
        # Inside the context, where the small grid is the grid.
        squares = india_squares({"india": india})
        assert len(squares) == 30, len(squares)

    handler = type("Rooted", (Quiet,),
                   {"__init__": lambda self, *a, **kw: Quiet.__init__(
                       self, *a, directory=str(served), **kw)})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        harness = tmp / "harness.mjs"
        harness.write_text(HARNESS, encoding="utf-8")
        answers = []
        for lat, lon in squares[::7]:
            reply = call(harness, "place", f"?lat={lat}&lon={lon}", base)
            assert reply["status"] == 200, (lat, lon, reply["body"][:200])
            answers.append(reply["json"])
        assert len(answers) >= 3

        out = web / "node_modules" / ".ssr-test"
        vite = web / "node_modules" / ".bin" / (
            "vite.cmd" if os.name == "nt" else "vite")
        done = subprocess.run(
            [str(vite), "build", "--ssr", "src/ssr.jsx", "--outDir",
             "node_modules/.ssr-test", "--logLevel", "error"],
            capture_output=True, text=True, encoding="utf-8", check=False, cwd=web)
        assert done.returncode == 0, f"vite failed: {done.stdout}{done.stderr}"

        given = tmp / "answers.json"
        given.write_text(json.dumps(answers), encoding="utf-8")
        script = (
            "import { readFileSync } from 'node:fs';\n"
            "const mod = await import(process.argv[2]);\n"
            "const answers = JSON.parse(readFileSync(process.argv[3],"
            " 'utf-8'));\n"
            "process.stdout.write(JSON.stringify("
            "mod.forecastWords(answers)));\n")
        runner = out / "run-forecast.mjs"
        runner.write_text(script, encoding="utf-8")
        done = subprocess.run(
            [node, str(runner), (out / "ssr.js").as_uri(), str(given)],
            capture_output=True, text=True, encoding="utf-8", check=False, cwd=web)
        assert done.returncode == 0, f"node failed: {done.stderr}"
        said = json.loads(done.stdout)
        assert len(said) > 50, len(said)
        return said
    finally:
        server.shutdown()
        server.server_close()


def forbidden_in(text: str, allowed: dict) -> str | None:
    """The first forbidden word in `text`, or None. SPEC 11.20 and 11.33.

    `allowed` maps a word to the sentences it may appear in; those sentences
    are taken out before the sweep, so the word is allowed where it is
    written and nowhere else.
    """
    low = text.lower()
    for sentences in allowed.values():
        for sentence in sentences:
            low = low.replace(sentence, " ")
    for word in FORBIDDEN:
        if word == "certain":
            # SPEC 11.33. The ban is on the claim "certain"; "too uncertain
            # to tell" is a confession and the opposite of a claim, so the
            # whole word is what is forbidden and not the letters.
            if re.search(r"\bcertain\b", low):
                return word
        elif word == "warn":
            # "Not an official warning" is required of this site, and is the
            # one warning word it may say.
            if re.search(r"\bwarn", low.replace("official warning", "")):
                return word
        elif word == "%":
            if word in low:
                return word
        elif re.search(r"\b" + word, low):
            # SPEC 11.38. The boundary is at the **start** of the word only,
            # so "drying" and "warning" are still caught while Rajahmundry
            # and Dharwad are not: the search box now renders all 215 city
            # names and some of them end in these letters. A substring match
            # would make a city's name a forbidden word, which is a rule
            # about English applied to a proper noun.
            return word
    return None


# SPEC 11.38. The panel's order, by the class each block is drawn with.
ANSWER_FIRST = ("placeline", "headline", "dots",
                "notpromise", "trust", "more")

ONCE_ONLY = "A count of runs, not a promise of rain."


@needs_node
def test_the_panel_puts_the_answer_first(forecast_words):
    """SPEC 11.38. Place, headline, five days, dots, amounts, then the rest.

    The review measured the place line 193 pixels down a 258 pixel window
    and the five-day strip 936 pixels down. The order is the answer first
    and the working after it, and the one closed section is last.
    """
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="placeline"' not in html:
            continue
        at = []
        for name in ANSWER_FIRST:
            mark = f'class="{name}'
            assert mark in html, (name, html[:200])
            at.append(html.index(mark))
        assert at == sorted(at), list(zip(ANSWER_FIRST, at))
        seen += 1
    assert seen > 20, seen


@needs_node
def test_the_caveat_is_said_once(forecast_words):
    """SPEC 11.38. It was under the legend, under the counts and in How to
    read this map: three times on one screen, which is how a sentence stops
    being read."""
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="placeline"' not in html:
            continue
        text = words_of(html)
        assert text.count(ONCE_ONLY) == 1, text.count(ONCE_ONLY)
        # And it points at the record, which is the only thing that could
        # settle it.
        assert 'href="/report-card"' in html
        seen += 1
    assert seen > 20, seen


@needs_node
def test_the_dots_are_readable_without_opening_anything(forecast_words):
    """SPEC 11.38, as 11.40 leaves it. The counts, and what a dot is."""
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="dots"' not in html:
            continue
        # Outside the closed section, which comes after them.
        assert html.index('class="dots"') < html.index('class="more"')
        text = words_of(html)
        assert "The 51 runs, one dot each" in text
        # SPEC 11.40. One sentence, and it says what a run is: "each dot
        # is one run" is only a sentence to a reader who already knows.
        # It is directly under the heading, above the 51 squares, so it
        # is read before them and not after.
        assert ("Each dot is one of 51 slightly different guesses by the "
                "same weather model; its colour shows how much rain it "
                "brings that day." in text)
        assert (html.index("slightly different guesses by the same")
                < html.index('class="dotgrid"'))
        assert text.count("slightly different guesses by the same") == 1
        seen += 1
    assert seen > 20, seen


@needs_node
def test_the_page_has_one_name_for_the_fifty_one(forecast_words):
    """SPEC 11.38. "runs", everywhere, and never "model runs" or "members".

    The page had four names for the same thing. A reader who does not
    already know they are the same thing has no way to learn it here.
    """
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str):
            continue
        text = words_of(html).lower()
        if not text.strip():
            continue
        assert "model run" not in text, text[:200]
        assert "member" not in text, text[:200]
        assert "ensemble" not in text, text[:200]
        seen += 1
    assert seen > 50, seen
    every = " ".join(words_of(html) for html in forecast_words
                     if isinstance(html, str))
    assert "of 51 runs" in every


@needs_node
def test_the_panel_and_the_bar_say_no_percentage(forecast_words):
    """SPEC 6.7 and 11.33, over the forecast page's own words.

    A percentage implies a reliability the record has not earned. The counts
    and the day sentence were swept from the first day; this sweeps the
    panel's written text and the bar of 11.37 with them.
    """
    for html in forecast_words:
        text = words_of(html)
        assert "%" not in text, text[:200]
        assert "percent" not in text.lower(), text[:200]


@needs_node
def test_the_panel_and_the_bar_say_no_forbidden_word(forecast_words):
    """SPEC 11.20's list, over every state the panel and the bar have.

    The forecast page has one word of its own: it may say "It is not a
    probability.", because refusing the reading is the point of the
    sentence. Everything else on the list is banned here as it is on the two
    document pages.
    """
    seen = 0
    for html in forecast_words:
        text = words_of(html)
        if not text.strip():
            continue
        found = forbidden_in(text, FORECAST_ALLOWED)
        assert found is None, f"{found} in: {text[:300]}"
        seen += 1
    assert seen > 50, seen

    # The allowance is a sentence and not a licence: the word may appear
    # only in the sentence that refuses the reading, and that sentence has
    # to be there.
    every = " ".join(words_of(html) for html in forecast_words).lower()
    for sentence in FORECAST_ALLOWED["probability"]:
        assert sentence in every, sentence
    assert every.count("probability") == sum(
        every.count(sentence)
        for sentence in FORECAST_ALLOWED["probability"])
def test_the_forecast_sweep_would_catch_a_forbidden_word():
    """A sweep that cannot fail proves nothing. SPEC 11.38.

    The same words the panel really says, with one word put into them, and
    the sweep asked about each. The allowance is a sentence and not a
    licence, so "probability" outside its two sentences is caught too.
    """
    clean = ("Srinagar, Today: a few of the 51 runs bring 10 mm or more "
             "(7 of 51). It is not a probability.")
    assert forbidden_in(clean, FORECAST_ALLOWED) is None, clean

    for word in ("certain", "likely", "dry", "wet", "heavy", "chance",
                 "risk", "percent", "%"):
        spoiled = clean.replace("a few of", f"{word} of")
        assert forbidden_in(spoiled, FORECAST_ALLOWED) == word, word

    # SPEC 11.38. The boundary is at the start of the word, so a word
    # built on a forbidden one is still caught. A form that changes the
    # stem -- "heavier", "drier" -- is not, and was not caught by the
    # substring rule either, so nothing is lost by the boundary.
    for word, built in (("dry", "drying"), ("wet", "wetter"),
                        ("chance", "chances"), ("warn", "warning")):
        spoiled = clean.replace("a few of", f"{built} of")
        assert forbidden_in(spoiled, FORECAST_ALLOWED) == word, built
    # ...and a city whose name merely ends in one is not. The search box
    # renders all 215 names, and Rajahmundry is not a forbidden word.
    for name in ("Rajahmundry", "Dharwad", "Hathras", "Sholapur"):
        assert forbidden_in(f"{name} 21.00 N 81.75 E",
                            FORECAST_ALLOWED) is None, name

    # The allowance is for the sentence that refuses the reading, not for
    # the word wherever it turns up.
    loose = clean + " The probability is 4 in 10."
    assert forbidden_in(loose, FORECAST_ALLOWED) == "probability"

    # "too uncertain to tell" is a confession and not the claim "certain".
    assert forbidden_in("Rough guide: too uncertain to tell.",
                        FORECAST_ALLOWED) is None
    # And "Not an official warning" is the one warning word the site says.
    assert forbidden_in("Not an official warning.", FORECAST_ALLOWED) is None
    assert forbidden_in("We warn of rain.", FORECAST_ALLOWED) == "warn"


@needs_node
def test_the_panel_sweep_covers_the_states_it_claims_to(forecast_words):
    """A sweep that renders nothing passes. This says what it rendered."""
    every = " ".join(words_of(html) for html in forecast_words)
    for must in ("of 51 runs", "How to read this map", "It is not a "
                 "probability.", "Lakshadweep", "no WebGL 2",
                 # SPEC 11.39: the drawer's own two lines are gone with
                 # it, and this is the one that replaced them.
                 "Back to map",
                 # SPEC 11.38: a tap on the sea or on a neighbour's land is
                 # a calm line now, not a red box about a coordinate box.
                 "That's outside India. Tap the map over India or find a "
                 "city.",
                 # SPEC 11.38: the new blocks, so a sweep that stopped
                 # rendering them could not pass quietly.
                 "Will it rain where you are?",
                 "Tap the map or search a city to see its next five days.",
                 "The 51 runs, one dot each",
                 "A count of runs, not a promise of rain.",
                 "More detail", "5:30 am to 5:30 am IST",
                 "When the runs said this before in",
                 "Which day?", "How much rain?", "A rainy day",
                 "A lot of rain", "All 51",
                 # SPEC 11.39: the key's own title and its two ends.
                 "How many of the 51 runs bring rain?",
                 "What does mm mean?", "or tap the map",
                 "Beige: land outside India, not forecast",
                 "Today", "Tomorrow",
                 # SPEC 11.40: the line beside "Which day?" on the
                 # mornings when the five days do not include today, and
                 # the section of How to read this map that explains it.
                 "(starts tomorrow, because today is already under way "
                 "when the forecast arrives)",
                 "Why the days start tomorrow",
                 # SPEC 11.41: How to read this map, rewritten for
                 # somebody who has never seen the site before.
                 "Hello, first-time visitor!",
                 "This site works a little differently from other weather "
                 "apps, so here are a few quick points to get you going.",
                 "Darker means more of our 51 weather runs bring rain "
                 "there.",
                 "The same weather model, run 51 times from slightly "
                 "different starts: 51 slightly different guesses.",
                 "Some rain (1 mm or more): the ground gets damp.",
                 "A rainy day (10 mm or more): a proper shower, so take "
                 "an umbrella.",
                 "A lot of rain (50 mm or more): a very rainy day, and "
                 "water can collect on roads.",
                 "Search your city, or just tap the map.",
                 "Pick the day and the amount of rain you care about.",
                 "That's it, your forecast shows up.",
                 "The map uses a colour-blind-friendly scale.",
                 "Don't like technical stuff? Stop reading here. Nerdy "
                 "birdies, read on!",
                 "The fine print",
                 # SPEC 11.40: what the 51 are, said once in the empty
                 # card and once beside the dots.
                 "The same weather model is run 51 times, each starting "
                 "from slightly different conditions: 51 slightly "
                 "different guesses.",
                 "Each dot is one of 51 slightly different guesses by the "
                 "same weather model; its colour shows how much rain it "
                 "brings that day.",
                 # SPEC 11.39: the help sentences are on the How to read
                 # this map page, in these words, and the page is rendered
                 # into this sweep so they are still checked.
                 "Each day runs from 5:30 am to 5:30 am the next morning, "
                 "IST.",
                 # SPEC 11.40: the four lines "What does mm mean?" opens,
                 # which the How to read this map page also draws.
                 "Some rain (1 mm+): enough to leave the ground damp.",
                 "A rainy day (10 mm+): a proper shower; you would want "
                 "an umbrella.",
                 "A lot of rain (50 mm+): a very rainy day; water can "
                 "collect on roads.",
                 "Each is the total over the whole day, averaged over the "
                 "square.",
                 "1-10 runs", "41-50 runs", "All 51 runs",
                 "White: no forecast for this spot",
                 "Beige: land outside India, not forecast",
                 # SPEC 11.38: the search box's own two new answers.
                 "Kerala is too big for one forecast",
                 "We don't have Ooty yet."):
        assert must in every, must


# --------------------------- SPEC 11.39: the Location forecast card's order

# SPEC 11.40. The place, the answer, the five days, the dots, the one
# caveat, the label, and then the one closed section. The line that said
# the day and the amount and the square's own centre are not in it: the
# headline carries the day and the amount, and the square and the window
# are inside More detail.
CARD_ORDER = ("placeline", "headline", "dots", "notpromise", "trust",
              "more")

# SPEC 11.40. "Today, 15 Nov: about half of the 51 runs bring 10 mm or
# more (26 of 51)." The day as the pill names it, the band word, the
# amount and the count, and no place name: that is the heading above it.
HEADLINE = re.compile(
    r"^(Today|Tomorrow|Mon|Tue|Wed|Thu|Fri|Sat|Sun), "
    r"(\d{1,2} [A-Z][a-z]{2}): "
    r"(none|a few|some|about half|most|almost all|all) of the 51 runs "
    r"bring (1|10|50) mm or more \((\d{1,2}) of 51\)\.$")


@needs_node
def test_the_card_is_in_the_order_the_spec_sets(forecast_words):
    """SPEC 11.39, as 11.40 leaves it. Name, answer, working.

    The order is the whole of the card's design, so it is pinned by class in
    the rendered page rather than described in a comment: the place, the
    headline, the five days, the 51 dots, the caveat, the label, and then
    the one closed section.
    """
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="placeline"' not in html:
            continue
        at = []
        for name in CARD_ORDER:
            mark = f'class="{name}'
            assert mark in html, (name, html[:200])
            at.append(html.index(mark))
        assert at == sorted(at), list(zip(CARD_ORDER, at))
        seen += 1
    assert seen > 20, seen


@needs_node
def test_the_three_amount_rows_are_inside_more_detail(forecast_words):
    """SPEC 11.39. The choice is above the map; this was a second copy of it.

    They are kept -- the same three counts, the same radio group, in step
    with the buttons over the map -- and they are behind the one closed
    section, where a reader who has already chosen an amount is not shown
    the choice again in order to read the answer.
    """
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="placeline"' not in html:
            continue
        assert html.count('class="countrows"') == 1, html.count('countrows')
        assert html.index('class="more"') < html.index('class="counts"')
        # And the 51 values, the arithmetic and the run's name are in there
        # with them, which is what "nothing is deleted" means -- and so,
        # since 11.40, are the square's own centre and the day's window.
        for name in ("members", "arith", "atsquare"):
            assert html.index('class="more"') < html.index(f'class="{name}"')
        assert html.count('class="atsquare"') == 1, html.count("atsquare")
        assert "5:30 am to 5:30 am IST" in words_of(html)
        seen += 1
    assert seen > 20, seen


@needs_node
def test_the_headline_carries_the_day_and_the_amount(forecast_words):
    """SPEC 11.40. One sentence, and each fact in it once.

    The card had the place in the heading and in the headline, the day in
    a line of its own and in the headline, and the amount in that line
    and in the headline: four facts, eight copies. The headline is the
    one sentence now, and it carries the day as the pill names it, the
    amount in millimetres and the count out of 51.

    Checked against every day and every amount the page renders, and the
    place name is checked not to be in it.
    """
    found = []
    for html in forecast_words:
        if not isinstance(html, str) or 'class="headline"' not in html:
            continue
        said = html.split('class="headline">')[1].split("</p>")[0]
        said = re.sub(r"<[^>]+>", "", said).replace("&#x27;", "'")
        match = HEADLINE.match(said)
        assert match, said
        found.append((match.group(4), int(match.group(5))))
        # The place is the heading above it, and it is said once.
        name = html.split("<h2>")[1].split("</h2>")[0]
        assert name.lower() not in said.lower(), (name, said)
    # Every amount, and a count inside the 51 every time.
    assert len(found) > 20, len(found)
    assert {mm for mm, _ in found} == {"1", "10", "50"}, sorted(set(found))
    assert all(0 <= count <= 51 for _, count in found), found


@needs_node
def test_the_two_lines_of_a_day_pill_are_the_published_date(exports):
    """SPEC 11.39. "Today" over "15 Nov", and the date is never reformatted.

    The second line is the published `short_ist` with its weekday taken
    off. Formatting the date again here would be a second chance to
    disagree with the run about which day this is.
    """
    days = [f"2026-11-{14 + n:02d}T05:30:00+05:30" for n in range(5)]
    shorts = ["Sat 14 Nov", "Sun 15 Nov", "Mon 16 Nov", "Tue 17 Nov",
              "Wed 18 Nov"]
    calls = [[day, "2026-11-14", short]
             for day, short in zip(days, shorts)]
    assert exports(DAYS_JS, "dayWord", calls) == [
        "Today", "Tomorrow", "Mon", "Tue", "Wed"]
    assert exports(DAYS_JS, "dayDate", [[short] for short in shorts]) == [
        "14 Nov", "15 Nov", "16 Nov", "17 Nov", "18 Nov"]
    # Across a month end, where the weekday and the month both change.
    assert exports(DAYS_JS, "dayDate", [["Tue 1 Dec"]]) == ["1 Dec"]
    # Nothing is invented: no label, no date.
    assert exports(DAYS_JS, "dayDate", [[None], [""], ["14"]]) == [
        None, None, "14"]
    assert exports(DAYS_JS, "dayWord",
                   [["", "2026-11-14", None]]) == [None]



# ---------------------------- SPEC 11.39: How to read this map, as a page

HOWTOREAD = ROOT / "web" / "src" / "HowToRead.jsx"

# What the page holds, word for word. The forecast page may not say any of
# these: that is the point of moving them.
HOW_TO_READ_HOLDS = (
    "Each day runs from 5:30 am to 5:30 am the next morning, IST.",
    # SPEC 11.40: the four lines, in the words "What does mm mean?" opens
    # under the pills. One component draws them in both places.
    "Some rain (1 mm+): enough to leave the ground damp.",
    "A rainy day (10 mm+): a proper shower; you would want an umbrella.",
    "A lot of rain (50 mm+): a very rainy day; water can collect on roads.",
    "Each is the total over the whole day, averaged over the square.",
    "One square is 0.25 degrees, about 28 km across.",
    "It is not a probability.",
    "White: no forecast for this spot",
    "Beige: land outside India, not forecast",
)

# SPEC 11.41. The page, rewritten for a first-time visitor: the six
# answers in the order they are asked in, each with the words it must
# carry. The order is checked as well as the words -- a page that answers
# the right six questions in the specification's own order is the page
# this one replaced.
FIRST_TIME = (
    ("Hello, first-time visitor!",
     "This site works a little differently from other weather apps, so "
     "here are a few quick points to get you going."),
    ("The colours, in one line",
     "Darker means more of our 51 weather runs bring rain there."),
    ("What are the 51 runs?",
     "The same weather model, run 51 times from slightly different "
     "starts: 51 slightly different guesses."),
    ("The mm guide",
     "Some rain (1 mm or more): the ground gets damp."),
    ("Your mini user manual",
     "Search your city, or just tap the map."),
    ("No worries if you are colour-blind",
     "The map uses a colour-blind-friendly scale. If you're ever unsure "
     "about a shade, tap the square and you'll get the number."),
    ("Don't like technical stuff? Stop reading here. Nerdy birdies, read "
     "on!", "The fine print"),
)

# Nothing in this list may appear above the fine print: a first-time
# visitor meets none of it, and every one of them is a word that sent a
# tester looking for help on a page that was supposed to be the help.
TECHNICAL = ("UTC", "lead day", "grid", "calibrated", "probability",
             "0.25 degrees", "IMERG", "Brier", "5:30", "ECMWF", "AIFS",
             "satellite", "resample")


@needs_node
def test_how_to_read_this_map_holds_what_the_spec_says_it_holds(
        forecast_words):
    """SPEC 11.39. The page, rendered, with every sentence it must carry."""
    pages = [html for html in forecast_words
             if isinstance(html, str) and 'class="page howtoread"' in html]
    assert len(pages) == 1, len(pages)
    text = words_of(pages[0])
    for said in HOW_TO_READ_HOLDS:
        assert said in text, said
    # The nine rows of the key, in plain words, with "runs" on every one of
    # the seven that is a count.
    for row in ("None", "1-10 runs", "11-20 runs", "21-30 runs",
                "31-40 runs", "41-50 runs", "All 51 runs"):
        assert row in text, row
    # And the three amounts with their millimetres beside them, always.
    for nickname, mm in (("Some rain", 1), ("A rainy day", 10),
                         ("A lot of rain", 50)):
        assert nickname in text, nickname
        assert f"{nickname} ({mm} mm+)" in text, mm


@needs_node
def test_how_to_read_starts_with_hello_and_answers_six_questions(
        forecast_words):
    """SPEC 11.41. The page a first-time visitor is given.

    Every tester said the same thing about this site: they could not see
    where to start. The page that was supposed to help them was written in
    the specification's own order -- one square, one day, the mornings
    when the days start tomorrow -- which is the order for somebody who
    already knows what a square is.

    So: six short answers in the order the questions were asked, a line
    saying a reader may stop there, and one shut section with the rest.
    The order is checked and not only the words, because the words in any
    order are the page this one replaced.
    """
    pages = [html for html in forecast_words
             if isinstance(html, str) and 'class="page howtoread"' in html]
    assert len(pages) == 1, len(pages)
    html = pages[0]
    text = words_of(html)

    # The greeting is the first thing on the page.
    assert text.strip().startswith("Hello, first-time visitor!"), text[:120]

    # Every heading and its own first sentence, in this order and no
    # other: each one is found after the one before it.
    at = 0
    for heading, said in FIRST_TIME:
        where = text.find(heading, at)
        assert where >= 0, (heading, "not found after", at)
        body = text.find(said, where)
        assert body >= 0, (heading, said)
        at = body

    # The fine print is a section a reader opens, and it is shut.
    assert '<details class="fineprint">' in html, html[:200]
    assert 'fineprint" open' not in html

    # And nothing technical is above it. The page is split at the
    # section, and the half a first-time visitor reads is swept.
    above, below = html.split('<details class="fineprint">')
    plain = words_of(above)
    for word in TECHNICAL:
        assert word.lower() not in plain.lower(), (word, plain[-200:])
    # Not because the words are gone from the site: they are all below.
    deep = words_of(below).lower()
    for word in ("utc", "0.25 degrees", "probability", "calibrated",
                 "5:30"):
        assert word in deep, word


def test_the_amount_words_are_ours_and_are_written_down():
    """SPEC 11.39, moved by 11.40. Our words, in the code and in the spec.

    One of the three could not be written as it was asked for. "Enough to
    wet the ground" says it best in English and "wet" is on 11.20's list,
    which is there because "a wet day" forecasts what a day will be like
    and this site does not do that. "Damp" says the same thing about the
    ground and claims nothing about the day.

    The words are in Controls.jsx now, beside the nicknames they explain,
    because the same four lines are drawn under the amount pills as well
    as on the page.
    """
    said = (ROOT / "web" / "src" / "Controls.jsx").read_text("utf-8")
    page = HOWTOREAD.read_text("utf-8")
    spec = (ROOT / "SPEC.md").read_text("utf-8")
    section = spec.split("### 11.39")[1].split("## The hand checks")[0]
    for words in ("enough to leave the ground damp.",
                  "a proper shower; you would want an umbrella.",
                  "a very rainy day; water can collect on roads."):
        assert words in said, words
        assert words in section, words
    # The specification says why the first one is not the obvious English.
    assert "wet" in section.lower()
    # The millimetres are the rule and the words are not.
    assert "not an official category" in page.lower()
    assert "millimetres are the rule" in page


def test_the_fourth_page_is_a_real_path_with_its_own_tab():
    """SPEC 11.39. Linked to, bookmarked, and sent to somebody.

    It was a block inside the forecast panel, which is to say it had no
    address: a reader could not send it to anybody and could not come back
    to it. The header writes out three links and this is not one of them
    -- the band has room for three -- so it is reached from the page it
    explains, from the menu, and from "What does mm mean?".
    """
    nav = (ROOT / "web" / "src" / "TopNav.jsx").read_text("utf-8")
    site = (ROOT / "web" / "src" / "Site.jsx").read_text("utf-8")
    assert "path: '/how-to-read'," in nav
    assert "title: `How to read this map · ${SITE}`" in nav
    # Four pages, three of them written out in the header band.
    assert "export const BAR = PAGES.slice(0, 3);" in nav
    assert "{BAR.map((page) => {" in nav
    # The page itself is lazy, like the other two documents, so none of it
    # is in the forecast's download.
    assert "lazy(() => import('./HowToRead'))" in site
    # Every path in the list resolves to itself and nothing else.
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    pattern = re.compile("^" + config["rewrites"][0]["source"] + "$")
    assert pattern.match("/how-to-read")


@needs_node
def test_the_forecast_page_keeps_no_help_sentence_of_its_own(forecast_words):
    """SPEC 11.39. One line explains the answer; the rest is on the page.

    Three reviews called the forecast page too textual. Most of the words
    were help: a line under the day buttons, a line under the amount
    buttons, a line under the five-day strip, three bullets and two colour
    lines in the panel. The one that stays is the line under the place
    name, which says what the count in front of the reader is a count of.
    """
    gone = ("10 mm of rain is water 1 cm deep",
            "Each day runs from 5:30 am to 5:30 am the next morning (IST)",
            "Each cell is that day's count of runs",
            "One square is 0.25 degrees, about 28 km across",
            "Tap a square or search a city.")
    for html in forecast_words:
        if not isinstance(html, str) or 'class="page howtoread"' in html:
            continue
        text = words_of(html)
        for said in gone:
            assert said not in text, (said, text[:160])
    # And the line that stays is on every answered card: its own test
    # above pins its shape, this one pins that it is the only one left.
    # SPEC 11.40: that line is the headline, and the card no longer
    # carries a second one above it saying the day and the amount again.
    cards = [html for html in forecast_words
             if isinstance(html, str) and 'class="placeline"' in html]
    assert len(cards) > 20, len(cards)
    for html in cards:
        assert html.count('class="headline"') == 1
        assert "whenline" not in html


# ------------------------------------- SPEC 11.39: the calm look, measured

@needs_node
@pytest.mark.parametrize("size", ["390x664", "1440x900"])
def test_an_unchosen_pill_is_a_fill_and_the_chosen_one_is_navy(
        viewport, size):
    """SPEC 11.39. Fourteen outlined white boxes read as fourteen jobs.

    The controls bar was a row of white rectangles with hairline borders,
    which is what an empty form looks like; three of them were already
    answered and a reader could not see which at a glance. A pill is a
    pale fill with no outline, and the one that is chosen is filled navy
    -- the same navy the map marks the chosen square with.
    """
    for state in ("first", "afterMapTap"):
        pills = viewport["phone"][size][state]["pills"]
        if not pills:
            continue
        chosen = [pill for pill in pills if pill["on"]]
        assert chosen, (size, state)
        for pill in pills:
            assert pill["border"] == "0px", (pill["what"], pill["border"])
            # A fill, and not the page or a transparent nothing.
            assert pill["fill"] not in ("rgba(0, 0, 0, 0)", "transparent"), (
                pill["what"], pill["fill"])
        for pill in chosen:
            # #0b2b4a, the --picked of the map's own mark.
            assert pill["fill"] == "rgb(11, 43, 74)", pill
            assert pill["ink"] == "rgb(255, 255, 255)", pill
        for pill in pills:
            if not pill["on"]:
                assert pill["fill"] != "rgb(11, 43, 74)", pill


@needs_node
def test_the_search_box_keeps_its_border_and_the_cards_lose_theirs(viewport):
    """SPEC 11.39. The one control a reader puts something into.

    Every pill and every card lost its outline; the input did not, because
    a field with no edge reads as a line of text rather than somewhere to
    type.
    """
    seen = viewport["phone"]["390x664"]["afterMapTap"]
    assert seen["inputBorder"] == "1px", seen["inputBorder"]
    assert seen["outlined"], "no card was measured at all"
    for name, top, left in seen["outlined"]:
        assert top == "0px", (name, top)
        # A 3 pixel bar down one edge is how a quoted note is told from the
        # page and is not an outline; a border on all four sides is.
        if left != "0px":
            assert name in ("unitfound", "loadingsquare"), (name, left)


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "1440x900"])
def test_nothing_on_the_page_is_set_in_capitals(viewport, size):
    """SPEC 11.39. No all-caps labels, anywhere on the forecast page.

    Capitals were being used to make three ordinary questions look like
    system labels -- "DAY", "AMOUNT" -- and the map's state names were set
    in them too. Mixed case is read about a fifth faster, and the words
    say the same thing.
    """
    for state in ("first", "keyToggled", "afterMapTap"):
        page = viewport["phone"][size].get(state)
        if not page:
            continue
        assert page["allCaps"] == [], (size, state, page["allCaps"])
    # And the two document pages, which share the stylesheet.
    for path, page in viewport["pages"].items():
        assert page["allCaps"] == [], (path, page["allCaps"])
    # The rule itself is gone, rather than overridden somewhere.
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    assert "text-transform: uppercase" not in css


def test_every_control_keeps_a_focus_ring():
    """SPEC 11.39. The calm look never costs the keyboard its place.

    A fill with no outline is one keystroke away from a control nobody can
    see they are on, so the ring is declared once, for everything, and
    nothing on this site may turn an outline off.
    """
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    ring = css.split(":focus-visible {")[1].split("}")[0]
    assert "outline: 2px solid var(--picked);" in ring
    assert "outline-offset: 2px;" in ring
    # Nothing anywhere takes it away again.
    for killed in ("outline: none", "outline: 0", "outline-width: 0"):
        assert killed not in css, killed



# ------------------------------- SPEC 11.39: the header band and a desktop

def test_the_header_is_one_band_with_nothing_extra_in_it():
    """SPEC 11.39. The mark, the name, how old this is, and the pages.

    It used to be the name, a tagline, a run line of three facts in two
    sizes of grey, a run ID, the menu and a warning chip squeezed in beside
    the name -- which on a 390 pixel phone left the name, the tagline and
    the freshness line sharing 119 pixels with the chip taking 250.

    The tagline is gone: what the site is for is the question at the top of
    the card, where a reader who has chosen nothing yet is looking. The run
    ID and the 00 UTC time are in More detail.
    """
    app = APP.read_text("utf-8")
    band = app.split('<div className="band">')[1].split("</div>")[0]
    for piece in ("<Logo />", '<h1 className="sitename">{SITE}</h1>',
                  "<Freshness run={run} />", "{nav}"):
        assert piece in band, piece
    # The warning is under the band and across the width of it.
    head = app.split('<header className="pagehead">')[1].split("</header>")[0]
    assert head.index('className="band"') < head.index('className="headwarn"')
    assert "<strong>Not an official warning.</strong> For alerts:" in head
    assert 'href="https://mausam.imd.gov.in/"' in head

    # And the three things 11.39 took out of it are out of it. The
    # comments that say why they are gone are not code.
    code = re.sub(r"/\*.*?\*/", "", app, flags=re.S)
    code = "\n".join(line.split("//")[0] for line in code.split("\n"))
    for gone in ("tagline", "(00 UTC)", "runid", "RunLine"):
        assert gone not in code, gone
    # The run's own name and its UTC time are in the card's closed section.
    panel = PANEL.read_text("utf-8")
    # SPEC 11.40: the section is controlled, so its handle can say what
    # the next tap does. The component is what is split on.
    more = panel.split("export function MoreDetail")[1]
    assert "<RunDetail run={place.run} />" in more
    assert "the 00 UTC run of {run.run_time_utc}" in panel


@needs_node
@pytest.mark.parametrize("size", ["1440x900", "1024x768"])
def test_a_desktop_puts_the_controls_above_the_map_and_the_card_beside_it(
        viewport, size):
    """SPEC 11.39 item 7, as 11.40 leaves it. One grid, the other order.

    The three questions in one row across the top, the map on the left,
    the card in the column on the right. There is one copy of every
    control in the page: the order is the stylesheet's and not a second
    layout.
    """
    seen = viewport["phone"][size]["first"]
    width = int(size.split("x")[0])
    for what in ("controls", "asks", "pillrow", "mapcard", "card", "days",
                 "amounts"):
        assert seen[what], what

    # The row of controls is above the map, and the box comes first in it.
    assert seen["asks"]["top"] <= seen["pillrow"]["top"] + 6, (
        seen["asks"], seen["pillrow"])
    assert seen["controls"]["bottom"] <= seen["mapcard"]["top"] + 1, (
        seen["controls"], seen["mapcard"])
    # The map is on the left and the card on the right, side by side.
    assert seen["mapcard"]["right"] <= seen["card"]["right"] - 200, (
        seen["mapcard"], seen["card"])
    assert seen["card"]["top"] < seen["mapcard"]["bottom"], (
        seen["card"], seen["mapcard"])
    # The two questions share one row, because there is room for eight
    # pills on one line at this width.
    assert abs(seen["days"]["top"] - seen["amounts"]["top"]) <= 4, (
        seen["days"], seen["amounts"])
    # And nothing overlaps anything, at either width.
    assert seen["overlapping"] == [], seen["overlapping"]
    assert seen["docScrollWidth"] <= width + 1, seen["docScrollWidth"]

    # The three page links are visible text in the band, and the fourth
    # page is not one of them.
    assert seen["band"], "no header band"
    assert seen["brand"]["top"] >= 0
    assert seen["fresh"]["bottom"] <= seen["band"]["bottom"] + 1


@needs_node
def test_the_empty_card_asks_the_question_and_offers_the_page(
        forecast_words):
    """SPEC 11.39, item 7. What a desktop reader sees before choosing.

    The question, the one sentence that says what the 51 are, what to do
    next, and a link to How to read this map. Nothing else: no numbers for
    a place nobody asked about, and no second way in.
    """
    cards = [html for html in forecast_words
             if isinstance(html, str) and 'class="welcome"' in html]
    assert cards, "the empty card was never rendered"
    for html in cards:
        text = words_of(html)
        assert "Will it rain where you are?" in text
        # SPEC 11.40. The sentence says what the 51 come out as, in the
        # same words the dots and the How to read page use.
        assert ("The same weather model is run 51 times, each starting "
                "from slightly different conditions: 51 slightly "
                "different guesses." in text)
        assert ("Tap the map or search a city to see its next five days."
                in text)
        assert 'href="/how-to-read"' in html
        # No numbers, and no second way in.
        assert "of 51" not in text
        assert "Find my city" not in text
        assert "<button" not in html


@needs_node
def test_a_link_to_what_is_already_beneath_it_is_not_drawn(forecast_words):
    """SPEC 11.39, item 7. Two links under the card, and sometimes one.

    The empty card carries How to read this map itself, so under an empty
    card there is one link and not two of the same thing.
    """
    app = APP.read_text("utf-8")
    links = app.split('<p className="cardlinks">')[1].split("</p>")[0]
    assert "{nothingChosen ? null : <HowToReadLink onGo={onGo} />}" in links
    assert "<ReportCardLink onGo={onGo}>Report card</ReportCardLink>" in links
    # And the card that carries it is the empty one.
    panel = PANEL.read_text("utf-8")
    welcome = panel.split("export function Welcome(")[1].split("\n}")[0]
    assert "<HowToReadLink onGo={onGo} />" in welcome


# ----------------------------- SPEC 11.39: the key covers no India square

def india_points() -> list[tuple[float, float]]:
    """Every forecast square's centre, and every point of the outline.

    The squares are what the map paints, from config/india_mask.json, and
    the outline is the shape drawn around them -- which is what carries
    Lakshadweep, where there is no forecast square at all: of the 209
    squares covering the group not one has its centre on land (11.28). A
    key box over the map must be clear of both.
    """
    mask = load_mask()
    out = []
    for row, bits in zip(mask["lat"], mask["india_rows"]):
        for lon, bit in zip(mask["lon"], bits):
            if bit == "1":
                out.append((float(row), float(lon)))
    outline = json.loads((ROOT / "web" / "src" / "geo" / "india.geo.json")
                         .read_text(encoding="utf-8"))

    def walk(where):
        if (isinstance(where, list) and len(where) == 2
                and all(isinstance(n, (int, float)) for n in where)):
            out.append((float(where[1]), float(where[0])))
            return
        if isinstance(where, list):
            for part in where:
                walk(part)

    for feature in outline["features"]:
        walk(feature["geometry"]["coordinates"])
    return out


def on_screen(points, bounds, width, height):
    """Where each point lands in the map canvas, in its own pixels."""
    west, south, east, north = bounds

    def merc(lat):
        return math.log(math.tan(math.pi / 4 + (lat * math.pi) / 360))

    top = merc(north)
    span = top - merc(south)
    seen = []
    for lat, lon in points:
        x = ((lon - west) / (east - west)) * width
        y = ((top - merc(lat)) / span) * height
        seen.append((lat, lon, x, y))
    return seen


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568", "1440x900", "1366x768",
                                  "1366x650", "1280x720", "1024x768"])
def test_the_key_covers_no_india_square_at_any_width(viewport, size):
    """SPEC 11.39. The Arabian Sea, and nothing of the country.

    Where the key is over the map it is in the lower left corner, over the
    Arabian Sea, and open. It is paid for in the fit: the left edge is
    padded by the key's own measured width, so India starts to the right
    of it, and while the fit is limited by the height that padding costs
    the country nothing at all.

    SPEC 11.40 settles it by taking the key off the canvas at every
    width: it is the top of the panel on a desktop and directly under the
    map on a phone, so no square can be behind it and the fit pays
    nothing for it. What is checked here is that -- the key is laid out
    in the flow of the page and not over the canvas -- and that nothing
    else of ours is drawn over the map either.

    The 4,613 squares and every point of the drawn outline are still
    projected, against the box the key occupies, so that a key put back
    over the canvas would have to clear the country to pass.
    """
    seen = viewport["phone"][size]["first"]
    over = seen["keyOver"]
    assert over, "the key was not measured"
    wide = int(size.split("x")[0]) >= 1280
    # SPEC 11.41. Over the canvas at 1280 and over, and in the flow of
    # the page below that. The key is the only thing of ours that may be
    # over the map at any width: MapLibre's own zoom buttons and
    # attribution are its own and are not in this list.
    if wide:
        assert over["position"] == "absolute", over
        assert seen["overTheMap"] == ["mapkey overmap"], (
            size, seen["overTheMap"])
    else:
        # Not over the canvas: in the flow of the page, where SPEC 11.41
        # makes it sticky inside the panel on a desktop so that it stays
        # on the screen while the card scrolls past.
        assert over["position"] in ("static", "sticky"), over
        assert seen["overTheMap"] == [], (size, seen["overTheMap"])
    # And the box it does occupy is clear of every point of the country,
    # which for a box outside the canvas is true by where it is -- said
    # as a measurement so that moving it back would be caught here.
    left, top, right, bottom = over["box"]
    width, height = over["map"]
    hidden = []
    for lat, lon, x, y in on_screen(india_points(), seen["view"]["bounds"],
                                    width, height):
        if left <= x <= right and top <= y <= bottom:
            hidden.append((lat, lon, round(x), round(y)))
    assert not hidden, (
        f"{len(hidden)} points of India behind the key at {size}, "
        f"e.g. {hidden[:4]}; the key is {over['box']} in a "
        f"{width} by {height} map")


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "320x568"])
def test_the_key_sits_under_the_map_on_a_phone(viewport, size):
    """SPEC 11.39, and the measurement that decided it.

    At a phone's width India fills the map: the fit is limited by the
    width, not the height, so there is no dead space at the sides to put a
    box in. Paying for a key over the canvas would mean padding the fit by
    the key's width -- 226 of a 390 pixel map -- which would shrink the
    country to a third of the card. 11.39's own rule says the map's height
    may give way before the type does, and nothing says the map's *width*
    may; so on a phone the key is drawn directly under the map, which is
    what 11.39 allows for exactly this case.

    It is still the same key: the same nine rows, the same title, shut by
    default, and the strip of colours in the summary.
    """
    seen = viewport["phone"][size]["first"]
    over = seen["keyOver"]
    # On a phone it is in the flow of the page and sticks to nothing: the
    # page is one column and the key is a block of it.
    assert over and over["position"] == "static", over
    # Under the map, inside the card, and on the screen.
    assert seen["mapkey"]["top"] >= seen["map"]["bottom"] - 1, (
        seen["mapkey"], seen["map"])
    # SPEC 11.40: under the map and under the card it used to be inside,
    # which is one block of the page now.
    assert seen["mapkey"]["top"] >= seen["mapcard"]["bottom"] - 1, (
        seen["mapkey"], seen["mapcard"])
    # Shut, and the strip's three words are readable without opening it.
    assert seen["keyOpen"] is False
    assert "How many of the 51 runs bring rain?" in seen["keyText"]
    assert seen["keyEnds"] == ["None", "About half", "All 51"], (
        seen["keyEnds"])
    # And opening it does not move the map.
    opened = viewport["phone"][size]["keyToggled"]
    assert opened["keyOpen"] is True
    assert opened["map"]["height"] == seen["map"]["height"]
    assert len(opened["keyRows"]) == 9, opened["keyRows"]


@needs_node
@pytest.mark.parametrize("size", ["1024x768"])
def test_the_key_is_the_top_of_the_panel_on_a_desktop(viewport, size):
    """SPEC 11.40, as 11.41 leaves it. The strip, below 1280 pixels.

    11.39 floated the key in the map's lower left corner at 1280 and
    over and paid for it by padding the fit on that side; 11.40 took it
    off the canvas at every width; 11.41 puts it back over the map at
    1280 and over, where the measurement says the padding is free, and
    keeps the strip below that -- which is this test, at the one desktop
    width narrower than 1280.

    Here it is the top of the right-hand panel: the same collapsed strip
    the phone has, in the flow of the page, above the card. So it stays
    where it is when a place is chosen, when a search is made and when
    the map moves.
    """
    page = viewport["phone"][size]
    seen = page["first"]
    assert seen["keyInPanel"] is True, size
    # Sticky, so it stays on the screen while the card scrolls past it
    # (SPEC 11.41 item 8), and not over the canvas.
    assert seen["keyOver"]["position"] == "sticky", seen["keyOver"]
    assert seen["overTheMap"] == [], (size, seen["overTheMap"])
    # At the top of the panel: above the card, and beside the map.
    assert seen["mapkey"]["top"] <= seen["card"]["top"] + 1, (
        seen["mapkey"], seen["card"])
    assert seen["mapkey"]["top"] >= seen["mapcard"]["top"] - 1, (
        seen["mapkey"], seen["mapcard"])
    assert seen["mapkey"]["right"] > seen["mapcard"]["right"], (
        seen["mapkey"], seen["mapcard"])
    # Shut, with the three words of the strip, and the amount in its
    # title because the chosen pill is a row of controls away.
    assert seen["keyOpen"] is False, size
    assert seen["keyEnds"] == ["None", "About half", "All 51"], (
        seen["keyEnds"])
    assert seen["keyTitle"].strip() == (
        "How many of the 51 runs bring rain? (1 mm+)"), seen["keyTitle"]
    # One tap opens the nine rows, and another shuts them.
    opened = page["keyToggled"]
    assert opened["keyOpen"] is True
    assert len(opened["keyRows"]) == 9, opened["keyRows"]
    assert page["keyBack"]["keyOpen"] is False
    # Opening it does not move the map: it is not in the map's fit.
    assert opened["map"]["height"] == seen["map"]["height"]
    assert opened["view"]["bounds"] == seen["view"]["bounds"], (
        opened["view"]["bounds"], seen["view"]["bounds"])
    # And it stays where it is when a place is chosen three ways.
    for how in ("afterSearch", "afterLocate", "afterMapTap"):
        later = page.get(how)
        if not later:
            continue
        assert later["keyInPanel"] is True, how
        # Still the top of the panel, which is still the top of the map
        # beside it: both move together when the row above them grows,
        # and nothing of the card ever gets above the key.
        assert later["keyOpen"] is False, how
        assert abs(later["mapkey"]["top"]
                   - later["mapcard"]["top"]) <= 1, (
            how, later["mapkey"], later["mapcard"])
        assert later["mapkey"]["top"] <= later["card"]["top"] + 1, (
            how, later["mapkey"], later["card"])
        assert later["overTheMap"] == [], (how, later["overTheMap"])

    # SPEC 11.41 item 8. And it is still on the screen at the bottom of
    # the page: the panel is as tall as its own contents now and the page
    # is what scrolls, so the strip is sticky and stays where a reader
    # looking for what a colour means can find it.
    bottom = page.get("atBottom")
    assert bottom, "the bottom of the page was not measured"
    assert bottom["scrollY"] > 0, bottom["scrollY"]
    assert bottom["keyInPanel"] is True
    assert bottom["mapkey"]["top"] >= 0, bottom["mapkey"]
    assert bottom["mapkey"]["bottom"] <= int(size.split("x")[1]), (
        bottom["mapkey"], size)
    assert bottom["mapkey"]["height"] > 20, bottom["mapkey"]


@needs_node
@pytest.mark.parametrize("size", ["1366x768", "1440x900"])
def test_the_header_lines_up_with_the_column_under_it(viewport, size):
    """SPEC 11.41. One page, not two.

    The content is a centred column of at most 1280 pixels (11.40). The
    header band was the full width of the screen, so on a 1440 screen the
    mark stood 80 pixels to the left of the search box under it and the
    page links stood 80 to the right of the panel: three left edges and
    two right edges on one page.

    The band and the warning bar still run the whole width -- the colours
    are the point of them -- and it is their contents that are brought
    into the same column.
    """
    seen = viewport["phone"][size]["first"]
    for name in ("brand", "searchBox", "topnav", "card", "band", "warn",
                 "warnIcon", "mapcard"):
        assert seen[name], (size, name)
    # The mark's left edge is the search box's left edge.
    assert abs(seen["brand"]["top"] - seen["band"]["top"]) < 40, seen["band"]
    assert abs(seen["brand"]["left"] - seen["searchBox"]["left"]) <= 2, (
        seen["brand"], seen["searchBox"])
    # And the warning bar's text starts at the same place.
    assert abs(seen["warnIcon"]["left"]
               - seen["searchBox"]["left"]) <= 2, (
        seen["warnIcon"], seen["searchBox"])
    # The page links' right edge is the right-hand panel's.
    assert abs(seen["topnav"]["right"] - seen["card"]["right"]) <= 2, (
        seen["topnav"], seen["card"])
    # The bands themselves still run the whole width of the screen, so
    # the warning's colour and the header's white are edge to edge: it is
    # the contents that are brought in, and the warning's own colour is
    # on the bar and not on the row of words inside it.
    width = int(size.split("x")[0])
    assert seen["header"]["width"] >= width - 1, (seen["header"], width)
    assert seen["warn"]["width"] >= width - 1, (seen["warn"], width)
    assert seen["warn"]["left"] <= 0, seen["warn"]
    # The column is the one the grid uses, and it is 1280 at most.
    assert seen["controls"]["width"] <= 1280, seen["controls"]
    assert seen["mapcard"]["right"] <= seen["topnav"]["right"] + 2, (
        seen["mapcard"], seen["topnav"])


@needs_node
@pytest.mark.parametrize("size", ["1280x720", "1366x768", "1366x650",
                                  "1440x900"])
def test_the_key_is_the_whole_key_over_the_map_at_1280_and_over(viewport,
                                                               size):
    """SPEC 11.41. The nine rows, open, over the Arabian Sea.

    A reader comparing a colour on the map with the key was looking at
    two things 400 pixels apart, and the strip in the panel names three
    places on a scale of nine. Over the map it is the whole key, open,
    beside the thing it explains.

    It is paid for in the fit: Map.jsx measures this box and pads the
    left edge of the fit by its width, so the box of SPEC 1.4 starts to
    the right of it. That payment is free while the fit is limited by the
    height, which it is at 1280 and over -- and is not at 1024, which is
    why 11.40's measurement stands there and the strip stays.

    What is checked: where it is, that it is open with all nine rows and
    nothing to press, that no square of India is behind it in the view
    the page opens with, and that it is still there after a place is
    chosen, a search is made and the map is zoomed.
    """
    page = viewport["phone"][size]
    seen = page["first"]
    assert seen["keyOverMap"] is True, size
    assert seen["keyInPanel"] is False, size
    assert seen["keyOver"]["position"] == "absolute", seen["keyOver"]
    # Open, with nothing to open it: no summary anywhere in it.
    assert seen["keyHandles"] == 0, seen["keyHandles"]
    assert len(seen["keyRows"]) == 9, seen["keyRows"]
    assert seen["keyEnds"] == [], seen["keyEnds"]
    assert seen["keyTitle"].strip() == (
        "How many of the 51 runs bring rain? (1 mm+)"), seen["keyTitle"]
    # On the map's left side, and inside the map card.
    left, top, right, bottom = seen["keyOver"]["box"]
    width, height = seen["keyOver"]["map"]
    assert left >= 0, seen["keyOver"]
    assert right <= width / 2, seen["keyOver"]
    # The whole box is inside the canvas, top edge included. The card
    # clips what overflows it, so a key taller than the map loses its
    # first row rather than spilling over the pills: at 1366 by 650 the
    # canvas is 340 pixels tall and the box was 339 with its top at -10.
    assert bottom <= height + 1, seen["keyOver"]
    assert top >= 0, seen["keyOver"]
    # The country is clear of it, in the view the page opens with. The
    # projection is the same one test_the_key_covers_no_india_square
    # uses, and Lakshadweep is in india_points() with everything else.
    hidden = [(lat, lon) for lat, lon, x, y
              in on_screen(india_points(), seen["view"]["bounds"],
                           width, height)
              if left <= x <= right and top <= y <= bottom]
    assert not hidden, (size, len(hidden), hidden[:4], seen["keyOver"])
    # And it stays: a place chosen three ways, and a zoom.
    for how in ("afterSearch", "afterLocate", "afterMapTap", "afterZoom"):
        later = page.get(how)
        if not later:
            continue
        assert later["keyOverMap"] is True, how
        assert len(later["keyRows"]) == 9, (how, later["keyRows"])
        assert later["mapkey"]["height"] > 100, (how, later["mapkey"])
        # Still over the canvas, and still in the map's own lower left.
        assert later["keyOver"]["position"] == "absolute", how
        assert later["keyOver"]["box"][0] >= 0, (how, later["keyOver"])
        assert (later["keyOver"]["box"][2]
                <= later["keyOver"]["map"][0] / 2), (how, later["keyOver"])
    # The zoom really did move the map, so that "it stays" is a claim
    # about a canvas that repainted under it.
    zoom = page.get("afterZoom")
    assert zoom and zoom["view"]["bounds"] != seen["view"]["bounds"], (
        zoom["view"]["bounds"] if zoom else None)


@needs_node
@pytest.mark.parametrize("size", ["1366x768", "1440x900"])
def test_the_desktop_page_has_one_scrollbar_and_a_sticky_map(viewport, size):
    """SPEC 11.41. The window scrolls; nothing inside the page does.

    11.40 made the right-hand panel exactly as tall as the map and gave
    the card its own scrollbar, so the colour key above it could not
    scroll away. That is two scrollbars on one screen: a wheel over the
    card moved one and a wheel two pixels to the left moved the other,
    and a reader who reached the bottom of the card's box had no way of
    knowing the page went on.

    Now the page scrolls once and the map keeps its place by being
    sticky. Measured: nothing in the page has a scrollbar of its own
    before or after a place is chosen, and with the card at its tallest
    -- a place chosen, More detail open -- and the page scrolled to its
    end, the whole map card is still inside the window.
    """
    page = viewport["phone"][size]
    height = int(size.split("x")[1])
    for how in ("first", "afterSearch", "afterLocate", "afterMapTap",
                "atBottom"):
        seen = page.get(how)
        if not seen:
            continue
        assert seen["scrollers"] == [], (how, seen["scrollers"])
        assert seen["canScroll"] == [], (how, seen["canScroll"])
        assert seen["stick"]["mapcard"] == "sticky", (how, seen["stick"])

    # The page really does scroll once a place is chosen: a panel as tall
    # as its own contents is what makes that true, and it is the thing
    # 11.40 was avoiding.
    bottom = page.get("atBottom")
    assert bottom, "the bottom of the page was not measured"
    assert bottom["maxScroll"] > 0, bottom["maxScroll"]
    assert bottom["scrollY"] >= bottom["maxScroll"] - 2, (
        bottom["scrollY"], bottom["maxScroll"])
    assert bottom["moreOpen"] is True, "More detail was not open"
    # And the map is whole on the screen there, a little below the top.
    assert bottom["mapcard"]["top"] >= 0, bottom["mapcard"]
    assert bottom["mapcard"]["top"] <= 12, bottom["mapcard"]
    assert bottom["mapcard"]["bottom"] <= height, (
        bottom["mapcard"], height)
    # The map inside it is the same height it was at the top of the page:
    # sticky moves a box, it does not resize it.
    assert abs(bottom["map"]["height"]
               - page["first"]["map"]["height"]) <= 1, (
        bottom["map"], page["first"]["map"])


@needs_node
@pytest.mark.parametrize("size", ["1366x768", "1440x900", "1024x768"])
def test_a_wheel_over_the_desktop_map_scrolls_the_page(viewport, size):
    """SPEC 11.41. The wheel is how a page scrolls, so it scrolls.

    A map that eats the wheel traps a reader on a page it occupies most
    of: they turn the wheel to read the card and the map zooms instead.
    MapLibre's own cooperative gestures answer exactly this -- the wheel
    passes through and Ctrl with the wheel zooms -- and this measures it
    with real wheel events through the DevTools protocol, which is the
    only way to tell a handled wheel from an unhandled one.
    """
    page = viewport["phone"][size]
    wheels = page.get("wheels")
    assert wheels, f"no wheel was sent at {size}"
    before, plain, ctrl = wheels["before"], wheels["plain"], wheels["ctrl"]
    # The plain wheel did not zoom.
    assert plain["bounds"] == before["bounds"], (
        before["bounds"], plain["bounds"])
    # And it scrolled the page, wherever there was any page to scroll.
    if before["max"] > 4:
        assert plain["scrollY"] > before["scrollY"], (
            before["scrollY"], plain["scrollY"], before["max"])
    # MapLibre's own hint says what to do instead, which is how a reader
    # finds out that Ctrl is the other half of it.
    if plain["hint"]:
        assert "ctrl" in plain["hint"].lower(), plain["hint"]
    # Ctrl and the wheel together zoomed, from the top of the page.
    assert ctrl["bounds"] != before["bounds"], (
        before["bounds"], ctrl["bounds"])
    west, south, east, north = ctrl["bounds"]
    was = before["bounds"]
    assert east - west < was[2] - was[0], (was, ctrl["bounds"])
    assert north - south < was[3] - was[1], (was, ctrl["bounds"])


# ------------------------------- SPEC 11.39: the header, on every page

def test_the_mark_is_the_favicon_and_the_favicon_is_the_mark():
    """SPEC 11.39. One drawing, in two places, and a test between them.

    The tab icon is the same cloud and the same three drops as the logo in
    the band, written out as a data URI so there is no second file to
    fetch and nothing to 404. Two copies of a drawing drift apart unless
    something compares them.
    """
    icons = (ROOT / "web" / "src" / "Icons.jsx").read_text("utf-8")
    html = INDEX_HTML.read_text("utf-8")
    cloud = ("M7 14.5h9.5a3.5 3.5 0 0 0 .2-7 5 5 0 0 0-9.5-.8A3.9 3.9 0 0 0 "
             "7\n           14.5Z")
    assert cloud in icons, "the logo's own path changed"
    flat = " ".join(cloud.split())
    assert flat in html.replace("%20", " "), "the favicon is not the logo"
    for drop in ("M9 17.5v2.2", "M12.5 17.5v3.2", "M16 17.5v2.2"):
        assert drop in icons, drop
        assert drop in html, drop
    # An SVG data URI, so nothing is fetched and nothing can 404.
    assert 'href="data:image/svg+xml,' in html
    # And no emoji anywhere in the five icons, or in the page that draws
    # them: a rain cloud is a different picture on every platform, which
    # a site's own mark may not be. An em dash in a comment is not an
    # emoji, so this asks about the blocks the emoji are in.
    for where, text in (("Icons.jsx", icons), ("index.html", html)):
        for ch in text:
            assert not (0x1F000 <= ord(ch) <= 0x1FAFF
                        or 0x2600 <= ord(ch) <= 0x27BF), (where, ch)


@needs_node
@pytest.mark.parametrize("size", ["390x664", "320x568"])
def test_a_phone_gets_a_menu_button_and_a_desktop_gets_the_links(
        viewport, size):
    """SPEC 11.39, item 1. One word wide, and four pages behind it.

    Three links written out are a row 44 pixels tall across the top of a
    390 pixel screen, and on the forecast page that row was the fourth
    thing above the map.
    """
    seen = viewport["phone"][size]["first"]
    rows = dict((name, height) for name, height, _, _ in seen["rows"])
    assert "menubutton" in rows, seen["rows"]
    assert rows["menubutton"] >= 43.5, rows["menubutton"]
    assert "navlink" not in rows and "navlink here" not in rows, seen["rows"]
    # The mark, the name, the freshness line and the warning are all above
    # the fold, in that order, with nothing between them.
    assert seen["brand"]["top"] >= 0
    assert seen["fresh"]["top"] >= seen["brand"]["top"]
    assert seen["warn"]["top"] >= seen["fresh"]["top"]
    assert seen["warn"]["bottom"] <= int(size.split("x")[1])
    # Two rows and not three: the mark, the name and the button share one.
    assert abs(seen["brand"]["top"] - seen["mapkey"]["top"]) > 0
    assert seen["brand"]["bottom"] <= seen["fresh"]["top"] + 1
    assert seen["overlapping"] == [], seen["overlapping"]
def test_the_menu_holds_all_four_pages_and_can_be_got_out_of():
    """SPEC 11.39. Four entries, and three ways to shut it.

    A menu a reader cannot get out of is worse than no menu, so it shuts
    on Escape, on a tap anywhere outside it, and on following a link.
    """
    nav = (ROOT / "web" / "src" / "TopNav.jsx").read_text("utf-8")
    menu = nav.split("export function Menu(")[1].split(
        "export default function")[0]
    assert "{PAGES.map((page) => {" in menu, "the menu is not all the pages"
    assert "aria-expanded={open}" in menu
    assert "<Bars />" in menu and "Menu\n      </button>" in menu
    assert "'Escape'" in menu
    assert "document.addEventListener('pointerdown', away);" in menu
    assert "setOpen(false);" in menu
    # The three links the header writes out are the other half of the same
    # list, so a page cannot be in one and not the other.
    assert "{BAR.map((page) => {" in nav
    assert "export const BAR = PAGES.slice(0, 3);" in nav


@needs_node
def test_every_page_carries_the_freshness_line_and_the_warning(viewport):
    """SPEC 11.39. Both rules are rules about every page.

    They were the forecast page's: the report card and How we checked
    carried the warning in the footer only, which on either page is
    several screens down. The header is one component now, drawn above
    whichever page is being read.
    """
    for path, page in viewport["pages"].items():
        assert page["warn"], (path, "no warning bar")
        assert page["warnText"].startswith("Not an official warning."), path
        assert "For alerts:" in page["warnText"], path
        assert page["warn"]["top"] < 300, (path, page["warn"])
        assert page["fresh"], (path, "no freshness line")
        assert page["fresh"]["top"] < 300, (path, page["fresh"])
        assert page["brand"], (path, "no way back to the forecast")
    # And the forecast page itself.
    seen = viewport["phone"]["390x664"]["first"]
    assert seen["warnText"].startswith("Not an official warning.")
    assert seen["freshText"].startswith("Forecast from ")


# ------------------------------------------ SPEC 11.39: the search row

@needs_node
@pytest.mark.parametrize("size", ["390x664", "320x568", "1440x900"])
def test_the_search_row_is_a_box_and_a_location_button(viewport, size):
    """SPEC 11.39, item 2. One row, two controls, and a line under it.

    The box says what it is for in its own placeholder; the button at its
    right end says what it is for in its accessible name and in its
    tooltip, because a pin on its own is a picture and a picture is not a
    label (SPEC 11.22).
    """
    seen = viewport["phone"][size]["first"]
    assert seen["searchPlaceholder"] == "Search a city or state"
    assert seen["locateName"] == "Use my location"
    assert seen["locateTitle"] == "Use my location"
    # At the right end of the box, on the same line, both 44 pixels tall.
    assert seen["locate"]["top"] >= seen["searchBox"]["top"] - 2
    assert seen["locate"]["top"] <= seen["searchBox"]["bottom"] - 20
    assert seen["locate"]["right"] > seen["searchBox"]["right"], (
        seen["locate"], seen["searchBox"])
    assert seen["searchBox"]["height"] >= 43.5, seen["searchBox"]
    assert seen["locate"]["height"] >= 43.5, seen["locate"]
    # And the other way in, said once, under the row.
    assert seen["ortap"]["top"] >= seen["searchBox"]["bottom"] - 1
    # The three buttons SPEC 11.39 removed are not back, in the page or
    # in the source: the search row is the way in.
    for text, _ in seen["cardLinks"]:
        assert text not in ("Search", "Find my city", "Find a city")
    for name in ("App.jsx", "Panel.jsx", "Controls.jsx"):
        said = (ROOT / "web" / "src" / name).read_text("utf-8")
        # The comments that say why they are gone are not code.
        code = re.sub(r"/\*.*?\*/", "", said, flags=re.S)
        code = " ".join(line.split("//")[0] for line in code.split("\n"))
        for gone in ("sheetsearch", "findcity", "Find my city",
                     "Find a city"):
            assert gone not in code, (name, gone)


@needs_node
@pytest.mark.parametrize("size", ["390x664", "1440x900"])
def test_searching_for_a_city_answers_in_the_card(viewport, size):
    """SPEC 11.39, item 2. The box is the way in, and it works.

    A city is typed into the real box -- through the value setter React
    listens to, not by assigning past it -- and the form submitted, which
    is what pressing Enter does. The list of matches appears while the
    typing is going on and the card holds the answer afterwards.
    """
    here = viewport["phone"][size]
    typing = here["whileTyping"]
    assert typing["matches"], "nothing was offered while typing"
    card = here["searchCard"]
    assert card and card["has"]["counts"], "the search answered nothing"
    assert "of the 51 runs bring" in card["cardText"], card["cardText"]
    # The box shows what is being shown, so the question and the answer
    # agree (SPEC 11.28).
    assert here["afterSearch"]["searchValue"], here["afterSearch"]
    assert here["afterSearch"]["searchValue"] in card["cardText"]



# ------------------------------- SPEC 11.39: one finger, and two fingers

@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "1440x900"])
def test_one_finger_scrolls_the_page_and_two_move_the_map(viewport, size):
    """SPEC 11.39, item 3. A map inside a scrolling page is a trap.

    The map is 365 pixels of a 664 pixel screen, so a reader who puts a
    thumb down to scroll past it lands on the map more often than not --
    and if the map takes the drag, the page does not move and the reader
    is stuck. MapLibre's own cooperativeGestures is the answer, with its
    own hint: one finger scrolls, two move the map.

    Measured with real touch events on a screen with two touch points,
    not by reading the option back out of the source.
    """
    seen = viewport["phone"][size].get("gestures")
    assert seen, "the gestures were not measured"
    # One finger: the map did not move.
    assert seen["oneFinger"]["bounds"] == seen["before"]["bounds"], seen
    # And the page did, wherever there was any page to move. SPEC 11.40
    # fits the desktop map to the screen, so with nothing chosen the
    # whole page is one screen there and a drag has nothing to scroll --
    # which is the same answer as far as this rule goes: the map stays.
    if seen["before"]["max"] > 4:
        assert seen["oneFinger"]["scrollY"] > seen["before"]["scrollY"], seen
    # And the map said why, in the words MapLibre itself uses.
    assert "Use two fingers to move the map" in (seen["oneFinger"]["hint"]
                                                 or ""), seen["oneFinger"]
    # Two fingers: the map moved and the page did not.
    assert seen["twoFingers"]["scrollY"] == 0, seen["twoFingers"]
    moved = abs(seen["twoFingers"]["bounds"][0]
                - seen["before"]["bounds"][0])
    assert moved > 1, (seen["before"]["bounds"], seen["twoFingers"]["bounds"])


@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568"])
def test_the_map_card_is_the_size_the_spec_says(viewport, size):
    """SPEC 11.39, item 3. The smaller of 55 per cent and 480, never under
    280.

    A share of the viewport, which this page may have exactly once: it
    scrolls, so the map cannot squeeze another block off it -- which is
    what the old 52vh inside a fixed-height shell did, leaving the panel
    twenty pixels tall with its handle off the bottom of the screen.
    """
    width, height = (int(n) for n in size.split("x"))
    seen = viewport["phone"][size]["first"]
    want = max(min(0.55 * height, 480), 280)
    # Within a pixel: the browser rounds a percentage of a viewport to a
    # third of a pixel and the measurement is rounded to a tenth.
    assert abs(seen["map"]["height"] - want) <= 1, (
        size, seen["map"], want)
    # SPEC 11.40. The card is the map and nothing else: the key is the
    # block under it, not a corner of it, and nothing of ours is over
    # the canvas at any width.
    assert seen["mapkey"]["top"] >= seen["mapcard"]["bottom"] - 1, (
        seen["mapkey"], seen["mapcard"])
    assert seen["keyOver"]["position"] == "static"
    assert seen["overTheMap"] == [], seen["overTheMap"]


@needs_node
def test_the_map_card_is_whole_on_the_screen_at_390_by_844(viewport):
    """SPEC 11.39, item 3's own measurement.

    Everything from the header to the bottom of the map card, the
    collapsed key included, is on the screen before anybody scrolls.
    """
    seen = viewport["phone"]["390x844"]["first"]
    assert seen["scrollY"] == 0
    assert seen["mapcard"]["bottom"] <= 844, seen["mapcard"]
    assert seen["mapkey"]["bottom"] <= 844, seen["mapkey"]
    assert seen["warn"]["top"] >= 0 and seen["asks"]["top"] >= 0


@needs_node
def test_at_least_250_pixels_of_the_map_is_on_the_screen_at_390_by_664(
        viewport):
    """SPEC 11.39, item 3's other measurement."""
    seen = viewport["phone"]["390x664"]["first"]
    assert seen["scrollY"] == 0
    shown = min(seen["mapcard"]["bottom"], 664) - max(seen["mapcard"]["top"], 0)
    assert shown >= 250, (shown, seen["mapcard"])


# ---------------------------------------- SPEC 11.39: the day pills

@needs_node
@pytest.mark.parametrize("size", ["390x664", "320x568", "1440x900"])
def test_the_day_pills_are_two_lines_and_all_five_are_there(viewport, size):
    """SPEC 11.39, item 4. The name over the date.

    "Sat 15" put two facts on one line and the date was the one that got
    cut; "Today" with no date under it left a reader counting days on
    their fingers. Five pills, each with a name and a date, all of them
    on the screen without opening anything and without the row scrolling
    sideways.
    """
    seen = viewport["phone"][size]["first"]
    pills = seen["dayPills"]
    assert len(pills) == 5, pills
    for top, under, _ in pills:
        assert top, pills
        assert re.fullmatch(r"\d{1,2} [A-Z][a-z]{2}", under), pills
    tops = [top for top, _, _ in pills]
    # The reader's own date names two of the five, by the rule of 11.38.
    assert "Today" in tops and "Tomorrow" in tops, tops
    for top in tops:
        assert (top in ("Today", "Tomorrow")
                or re.fullmatch(r"[A-Z][a-z]{2}", top)), tops
    # Exactly one is chosen, and the fill is what says so.
    assert sum(1 for _, _, on in pills if on) == 1, pills
    # The five share the row rather than running off it.
    assert seen["dayRow"]["right"] <= int(size.split("x")[0]) + 1
    widths = [w for where, w in seen["pillWidths"] if "days" in where]
    assert len(widths) == 5
    if int(size.split("x")[0]) < 1024:
        # A fifth each, so the row cannot overflow however long the
        # longest word is. On a desktop they take the width of their own
        # words, because there is room for them.
        assert max(widths) - min(widths) <= 2, widths


# ------------------------- SPEC 11.39: the amount pills and the mm link

@needs_node
@pytest.mark.parametrize("size", ["390x664", "320x568", "1440x900"])
def test_the_amount_pills_are_two_lines_and_share_the_row(viewport, size):
    """SPEC 11.39, item 5. The nickname over the millimetres.

    The millimetres are on the pill with the nickname, always, so the
    nickname is never the only thing a reader is given (11.38). The three
    of them keep the whole width between them, which is what puts "What
    does mm mean?" on a line of its own.
    """
    seen = viewport["phone"][size]["first"]
    pills = seen["amountPills"]
    assert [top for top, _, _ in pills] == [
        "Some rain", "A rainy day", "A lot of rain"], pills
    assert [under for _, under, _ in pills] == [
        "1 mm+", "10 mm+", "50 mm+"], pills
    assert sum(1 for _, _, on in pills if on) == 1, pills
    widths = [w for where, w in seen["pillWidths"] if "amounts" in where]
    assert len(widths) == 3
    if int(size.split("x")[0]) < 1024:
        assert max(widths) - min(widths) <= 2, widths
        # The three of them, with their gaps, are the row.
        assert sum(widths) >= seen["amountRow"]["width"] - 12, (
            widths, seen["amountRow"])


@needs_node
@pytest.mark.parametrize("size", ["390x664", "320x568", "1440x900"])
def test_what_does_mm_mean_is_its_own_line_under_the_pills(viewport, size):
    """SPEC 11.39 item 5, remade by 11.40. On its own line, at the end.

    A reader who asks what a millimetre of rain is wants three
    sentences, and was given a page: the link took them off the forecast
    to a document that opens with its own heading, and on a phone the
    three sentences were below the fold of a page they had not asked
    for. It opens under the pills now.
    """
    seen = viewport["phone"][size]["first"]
    assert seen["mmwhat"], "the handle is not there"
    if int(size.split("x")[0]) < 1024:
        # Under the pills, and not beside them: on a phone the three
        # pills keep the whole width between them.
        assert seen["mmwhat"]["top"] >= seen["amountRow"]["bottom"] - 1, (
            seen["mmwhat"], seen["amountRow"])
        # At the end of the line, within a few pixels of the pills' edge.
        assert abs(seen["mmwhat"]["right"]
                   - seen["amountRow"]["right"]) <= 6, (
            seen["mmwhat"], seen["amountRow"])
    else:
        # SPEC 11.40: on a desktop it is on the pills' own line, right
        # after them, because the three questions are one row there.
        assert seen["mmwhat"]["top"] < seen["amountRow"]["bottom"], (
            seen["mmwhat"], seen["amountRow"])
    # SPEC 11.41. It is not a link to anything, and the page it used to
    # point at no longer has an anchor for it to land on: the same four
    # lines are in the fine print of How to read this map, which is
    # written for a reader who went there to read the page.
    page = (ROOT / "web" / "src" / "HowToRead.jsx").read_text("utf-8")
    assert 'id="amounts"' not in page
    assert "<h3>How much rain</h3>" in page
    nav = (ROOT / "web" / "src" / "TopNav.jsx").read_text("utf-8")
    assert "path: '/how-to-read'," in nav
    # And nothing is drawn between the pills and the link.
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    rule = css.split("\n.mmwhat {")[1].split("}")[0]
    assert "border" not in rule, rule
    assert "text-align: right;" in rule

    # SPEC 11.40. It is a disclosure, not a link: shut as the page opens,
    # open on one tap, shut again on a second, and nothing navigates.
    page = viewport["phone"][size]
    assert page["first"]["mmOpen"] is False, size
    assert page["first"]["mmLinks"] == 0, "there is a link in it"
    assert page["first"]["mmSummary"]["height"] >= 43.5, (
        size, page["first"]["mmSummary"])
    shown = page["mmShown"]
    assert shown["mmOpen"] is True, size
    assert shown["path"] == "/", shown["path"]
    # The four lines, in our own words, with the millimetres in every one.
    assert shown["mmLines"] == [
        "Some rain (1 mm+): enough to leave the ground damp.",
        "A rainy day (10 mm+): a proper shower; you would want an "
        "umbrella.",
        "A lot of rain (50 mm+): a very rainy day; water can collect on "
        "roads.",
        "Each is the total over the whole day, averaged over the square.",
    ], shown["mmLines"]
    # Open, they are under the amount pills, at every width: on a phone
    # the handle is already there, and on a desktop the handle takes a
    # line of its own under the pills when it is opened, which is the
    # only place there with the width to read four lines on four lines.
    assert shown["mmwhat"]["top"] >= shown["amountRow"]["bottom"] - 1, (
        shown["mmwhat"], shown["amountRow"])
    # And a second tap shuts it, with the page where it was.
    assert page["mmHidden"]["mmOpen"] is False, size
    assert page["mmHidden"]["path"] == "/", page["mmHidden"]["path"]


@needs_node
def test_the_amount_words_are_the_same_four_lines_in_both_places(
        forecast_words):
    """SPEC 11.40. One component under the pills and on the page.

    The three sentences were on the How to read this map page and the
    pills linked to them. They open under the pills now, and the page
    keeps the same words -- which is only true by construction if there
    is one copy of them, so there is: `AmountWords` in Controls.jsx,
    drawn in both places, reading one table of words.
    """
    controls = (ROOT / "web" / "src" / "Controls.jsx").read_text("utf-8")
    assert "export const AMOUNT_WORDS = {" in controls
    assert "export const WHOLE_DAY = " in controls
    assert "export function AmountWords()" in controls
    page = (ROOT / "web" / "src" / "HowToRead.jsx").read_text("utf-8")
    assert "<AmountWords />" in page
    assert "AMOUNT_WORDS" not in page, "the page has its own copy"

    # And in the rendered page the four lines appear wherever the pills
    # or the page are drawn, in those words.
    lines = [
        "Some rain (1 mm+): enough to leave the ground damp.",
        "A rainy day (10 mm+): a proper shower; you would want an umbrella.",
        "A lot of rain (50 mm+): a very rainy day; water can collect on "
        "roads.",
        "Each is the total over the whole day, averaged over the square.",
    ]
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or "amountwords" not in html:
            continue
        text = " ".join(words_of(html).split())
        for line in lines:
            assert line in text, (line, text[:200])
        seen += 1
    assert seen >= 2, seen


# ----------------------- SPEC 11.39: choosing a place brings the card up

@needs_node
@pytest.mark.parametrize("how", ["afterSearch", "afterLocate",
                                 "afterMapTap"])
def test_choosing_a_place_scrolls_to_the_pills_and_the_card(viewport, how):
    """SPEC 11.39, item 6. All three ways in, on a phone.

    The card is the last block of the page, so choosing a place fills in
    something a reader cannot see. The page scrolls to the day pills,
    which puts the pills, the amounts and the top of the card on the
    screen together: the answer, and the two controls that change it.

    The three ways are a city typed into the search box and submitted, the
    location button with a real fix handed to the page by the browser, and
    a tap on the map. Each is done for real here, not simulated.
    """
    here = viewport["phone"]["390x664"]
    page = here.get(how)
    assert page, f"{how} was never measured"
    # The page moved, and the pills and the card's top are on the screen.
    assert page["scrollY"] > 0, page["scrollY"]
    assert page["pillrow"]["top"] >= 0, page["pillrow"]
    assert page["pillrow"]["bottom"] <= 664, page["pillrow"]
    assert 0 < page["card"]["top"] < 664, page["card"]
    # The pills are at the top of the screen. SPEC 11.40: this was 123
    # pixels out, because `scrollIntoView` clamps to the height the page
    # has when it is asked -- and when it is asked the card still says
    # "Reading the 51 runs for this square". The scroll is a measured
    # target now, and it is made again when the answer has arrived.
    assert page["pillrow"]["top"] <= 80, (
        page["pillrow"], page["scrollY"], page["docHeight"])
    # And the card holds an answer rather than the prompt.
    card = here.get({"afterSearch": "searchCard",
                     "afterLocate": "locateCard"}.get(how, "card"))
    assert card and card["has"]["counts"], how


@needs_node
def test_nothing_scrolls_on_a_desktop_because_nothing_has_to(viewport):
    """SPEC 11.39, item 6. The card is the column beside the map there.

    The same rule, written once: the page scrolls only when the card is
    under the map, which on a desktop it is not. SPEC 11.40 reads that
    off the two boxes rather than off the card being on the screen --
    after a scroll that fell short the card is on the screen and still
    under the map -- and nothing in the code asks how wide the screen is.
    """
    here = viewport["phone"]["1440x900"]
    for how in ("afterSearch", "afterLocate", "afterMapTap"):
        page = here.get(how)
        assert page, how
        assert page["scrollY"] == 0, (how, page["scrollY"])
        assert page["card"]["top"] < 900, (how, page["card"])
    app = APP.read_text("utf-8")
    bring = app.split("const bringCardUp")[1].split("}, []);")[0]
    assert "matchMedia" not in bring
    assert "innerWidth" not in bring
    # The question it asks is where the card is in relation to the map.
    assert "document.querySelector('.mapcard')" in bring
    assert "getBoundingClientRect().bottom" in bring


@needs_node
def test_back_to_map_returns_and_is_not_drawn_where_the_map_is_in_view(
        viewport):
    """SPEC 11.39, item 6. One small link, and only where it is needed."""
    phone = viewport["phone"]["390x664"]
    assert phone["hasBack"] is True, "there is no way back to the map"
    back = phone["afterBack"]
    assert back["map"]["top"] <= 2, back["map"]
    assert back["map"]["bottom"] > 200, back["map"]
    # It is a tap target on a phone...
    assert phone["afterSearch"]["backlink"]["height"] >= 43.5, (
        phone["afterSearch"]["backlink"])
    # ...and not drawn at all where the map is already on the screen.
    wide = viewport["phone"]["1440x900"]["afterSearch"]
    assert wide["backlink"]["height"] == 0, wide["backlink"]


@needs_node
def test_no_bottom_sheet_and_no_summary_row_remain(forecast_words):
    """SPEC 11.39. The drawer, its handle and its one-line summary.

    Every one of them is gone from the page and from the code: the card
    is on the page, so there is nothing to open, nothing to drag, and no
    second copy of the answer to keep in step with the first.
    """
    for name in ("App.jsx", "Panel.jsx", "Controls.jsx", "Site.jsx"):
        said = (ROOT / "web" / "src" / name).read_text("utf-8")
        code = re.sub(r"/\*.*?\*/", "", said, flags=re.S)
        code = " ".join(line.split("//")[0] for line in code.split("\n"))
        for gone in ("sheetbar", "sheetbody", "summaryLine", "handle",
                     "sheetOpen", "panel-body\" onClick"):
            assert gone not in code, (name, gone)
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for gone in (".sheetbar", ".sheetbody", ".handle", ".sheetsearch",
                 ".shell.open", ".shell.answered", ".stage"):
        assert gone not in bare, gone
    for html in forecast_words:
        if not isinstance(html, str):
            continue
        for gone in ('class="sheetbar"', 'class="handle"',
                     'class="summaryline"'):
            assert gone not in html, gone


# ------------------ SPEC 11.39: the checks that run at every width

@needs_node
@pytest.mark.parametrize("size", ["390x664", "390x844", "360x640",
                                  "320x568", "1024x768", "1440x900"])
def test_no_two_controls_overlap_at_any_width(viewport, size):
    """SPEC 11.39. Two controls on the same pixels is one control lost.

    Every pair of the page's own controls -- the search box, the location
    button, the eight pills, "What does mm mean?", the menu, the links
    under the card and the key -- measured against every other, in the
    state the page opens in and after a place has been chosen.
    """
    for state in ("first", "afterSearch", "afterMapTap"):
        page = viewport["phone"][size].get(state)
        if not page:
            continue
        assert page["overlapping"] == [], (size, state, page["overlapping"])
        assert page["docScrollWidth"] <= int(size.split("x")[0]), (
            size, state, page["docScrollWidth"])


@needs_node
def test_the_age_is_counted_from_the_time_the_line_prints(exports):
    """SPEC 11.39. One line, two numbers, and they agree.

    The header said "Updated 13 Nov, 12:33 pm" -- the publish time --
    beside an age counted from the **run** time, so the arithmetic a
    reader could do came out wrong by however long the pipeline had
    taken. The line names the run and counts from the run.

    The age is worked out in the page rather than read from the API's
    `age_hours`, for the same reason the staleness is: a page served from
    a browser cache would otherwise show an hours figure frozen at
    whatever it was when the JSON was fetched.
    """
    app = APP.read_text("utf-8")
    fresh = app.split("export function Freshness(")[1].split("\n}")[0]
    assert "shortIst(run.run_time_ist)" in fresh
    assert "publish_time_ist" not in fresh
    assert "hoursOld(run)" in fresh
    counted = app.split("export function hoursOld(")[1].split("\n}")[0]
    assert "Date.parse(run.run_time_utc)" in counted
    assert "Date.now()" in counted
    # The stale banner counts the same way, from the same field.
    banner = app.split("export function StaleBanner(")[1].split("\n}")[0]
    assert "hoursOld(run)" in banner
    assert "staleNow(run)" in banner


@needs_node
def test_the_sweep_covers_the_header_and_the_menu(forecast_words):
    """A sweep that never renders a block cannot catch a word in it.

    SPEC 11.39 added a header, a menu, a colour key, a card and a page;
    every one of them is rendered into the sweep, and this says so by
    naming a sentence from each.
    """
    every = " ".join(words_of(html) for html in forecast_words
                     if isinstance(html, str))
    for must in ("India Rain Outlook", "Forecast from ", "Menu",
                 "How we checked", "How to read this map",
                 "Not an official warning.", "For alerts:",
                 "How many of the 51 runs bring rain?", "Back to map",
                 "Will it rain where you are?",
                 "enough to leave the ground damp.",
                 "hours old; a newer one has not arrived yet."):
        assert must in every, must


# ------------------------------ SPEC 11.40: the fixes after the rebuild


@needs_node
def test_the_detail_handle_says_what_the_next_tap_does(viewport):
    """SPEC 11.40. "More detail" shut, "Hide detail" open.

    The one closed section is the page's only disclosure, and its handle
    read "More detail" whether or not the detail was already there. The
    triangle beside it says which way it is pointing and a triangle is
    eight pixels of grey.

    Measured in the browser, both ways round: the card as a reader meets
    it, after one tap on the handle, and after a second.
    """
    for size in ("390x664", "1440x900"):
        page = viewport["phone"][size]
        shut = page["afterSearch"]
        assert shut["moreOpen"] is False, size
        assert shut["moreLabel"].strip() == "More detail", (
            size, shut["moreLabel"])
        shown = page["moreShown"]
        assert shown["moreOpen"] is True, size
        assert shown["moreLabel"].strip() == "Hide detail", (
            size, shown["moreLabel"])
        again = page["moreHidden"]
        assert again["moreOpen"] is False, size
        assert again["moreLabel"].strip() == "More detail", (
            size, again["moreLabel"])


@needs_node
def test_the_starts_tomorrow_note_is_drawn_only_when_it_is_true(exports,
                                                               viewport):
    """SPEC 11.40. The five days start tomorrow, and only then is it said.

    Between midnight IST and the run arriving around midday, the newest
    run's first day begins tomorrow morning and the day the reader is in
    is not one of the five. Five date pills cannot say that.

    The rule is driven directly, on the dates a reader can really have,
    and then the page is measured: wherever the first pill reads
    "Tomorrow" the note is there, and wherever it does not the note is
    not in the page at all.
    """
    days = [{"from_ist": f"2026-11-{14 + n:02d}T05:30:00+05:30",
             "short_ist": f"{'Sat Sun Mon Tue Wed'.split()[n]} "
                          f"{14 + n} Nov"}
            for n in range(5)]
    # The reader's own date one before the first of the five: it starts
    # tomorrow, and the note is drawn.
    assert exports(DAYS_JS, "startsTomorrow", [[days, "2026-11-13"]])[0]         is True
    # The ordinary case, and the two ways it can be neither.
    assert exports(DAYS_JS, "startsTomorrow", [[days, "2026-11-14"]])[0]         is False
    assert exports(DAYS_JS, "startsTomorrow", [[days, "2026-11-12"]])[0]         is False
    assert exports(DAYS_JS, "startsTomorrow", [[days, "2026-11-15"]])[0]         is False
    # Nothing to name is not an answer of "yes".
    for bad in ([[], "2026-11-13"], [None, "2026-11-13"],
                [days, "not a date"], [days, None]):
        assert exports(DAYS_JS, "startsTomorrow", [bad])[0] is False, bad

    # And the page itself, at every size it is measured at.
    said = ("(starts tomorrow, because today is already under way when "
            "the forecast arrives)")
    for size, page in viewport["phone"].items():
        first = page["first"]
        word = (first["dayPills"] or [[None]])[0][0]
        if word == "Tomorrow":
            assert first["startsNote"] is not None, size
            assert first["startsNote"].strip() == said, (
                size, first["startsNote"])
        else:
            assert first["startsNote"] is None, (size, word,
                                                 first["startsNote"])

    # SPEC 11.41. Both cases, in a real browser, on one run: the same
    # page opened by a reader whose own IST date is the first of the five
    # days and by a reader one day earlier. The clock is the only thing
    # that differs between them, so the note's being there is the
    # clock's doing and nothing else's.
    clock = viewport.get("clock")
    assert clock, "the two clock readings were not taken"

    now = clock["today"]
    assert now["dayPills"][0][0] == "Today", now["dayPills"]
    assert now["startsNote"] is None, now["startsNote"]

    before = clock["tomorrow"]
    assert before["dayPills"][0][0] == "Tomorrow", before["dayPills"]
    assert before["startsNote"] is not None, "the note was not drawn"
    assert before["startsNote"].strip() == said, before["startsNote"]
    # The same five days either way: the run has not changed, only the
    # reader's own day, so the dates on the pills are the same dates.
    assert ([pill[1] for pill in now["dayPills"]]
            == [pill[1] for pill in before["dayPills"]]), (
        now["dayPills"], before["dayPills"])


@needs_node
def test_what_the_fifty_one_are_is_written_down_once(forecast_words):
    """SPEC 11.40. Two sentences, one copy each, three readers.

    The empty card, the dots and the How to read this map page all have
    to say what the 51 are, and a page that says it three ways says it
    three times to anybody who reads two of them. Both sentences are
    strings in `palette.js`, beside MEMBERS and the sentence that refuses
    the probability reading, and nothing writes them out again.
    """
    palette = (ROOT / "web" / "src" / "palette.js").read_text("utf-8")
    assert "export const GUESSES = " in palette
    assert "export const ONE_DOT = " in palette
    # Nothing else writes either sentence out: the components take the
    # string. Comments are stripped first -- the reason a sentence is
    # worded the way it is belongs beside it.
    for name in ("Panel.jsx", "HowToRead.jsx", "Controls.jsx", "App.jsx"):
        said = (ROOT / "web" / "src" / name).read_text("utf-8")
        code = re.sub(r"/\*.*?\*/", "", said, flags=re.S)
        code = re.sub(r"\{/\*.*?\*/\}", "", code, flags=re.S)
        code = " ".join(line.split("//")[0] for line in code.splitlines())
        for gone in ("times, each starting from slightly different",
                     "slightly different guesses by the same weather"):
            assert gone not in code, (name, gone)

    # And in the rendered page each is said once wherever it is said.
    for html in forecast_words:
        if not isinstance(html, str):
            continue
        text = words_of(html)
        for sentence in (
            "The same weather model is run 51 times, each starting from "
            "slightly different conditions: 51 slightly different "
            "guesses.",
            "Each dot is one of 51 slightly different guesses by the same "
            "weather model; its colour shows how much rain it brings that "
            "day.",
        ):
            assert text.count(sentence) <= 1, sentence


@needs_node
def test_the_location_is_titled_by_its_place_and_says_so_once(viewport):
    """SPEC 11.40, with 11.28 unchanged. "Near Budaun", then the small lines.

    The card said "Your location" as its heading and put the square's own
    centre under it, and the search box showed "22.75 N 88.25 E
    (Kolkata)" -- a grid reference in the box a reader types city names
    into, with the name they would have typed in brackets after it.

    The heading is the place now, as a title. "your location" is the
    small line under it, and the one sentence that matters about a fix is
    under that: it never left the page (11.19 and 11.28 are unchanged --
    the fix is still snapped in the page and only a square centre is ever
    sent).
    """
    seen = 0
    for size, page in viewport["phone"].items():
        card = page.get("locateCard")
        if not card:
            continue
        title = (card["title"] or "").strip()
        assert title, size
        # A name, as a title: a city, "Near <city>", or "This area".
        assert title[0] == title[0].upper(), (size, title)
        assert not re.match(r"^\d", title), (size, title)
        assert "your location" == (card["yoursLine"] or "").strip(), (
            size, card["yoursLine"])
        assert ("Your exact position was not sent anywhere."
                == (card["noShare"] or "").strip()), (size, card["noShare"])
        # And it is said once: the heading is not repeated in the sentence
        # under it, and there is one copy of each small line.
        text = " ".join((card["cardText"] or "").split())
        assert text.count("your location") == 1, text[:200]
        assert text.count("Your exact position") == 1, text[:200]

        # The box shows that same name, not a coordinate.
        box = (page["afterLocate"]["searchValue"] or "").strip()
        assert box == title, (size, box, title)
        assert " N " not in box and box[-1] != "E", (size, box)
        seen += 1
    assert seen >= 4, seen


@needs_node
def test_only_the_dot_bands_that_happened_are_listed(forecast_words):
    """SPEC 11.40. A row with no dots behind it is not a reading.

    All 51 dots are drawn, always. The four band names under them were
    listed whatever their counts were, so in a quiet week the card read
    "Under 1 mm: 51, 1 to 10 mm: 0, 10 to 50 mm: 0, 50 mm or more: 0" --
    three facts about nothing and one about something.

    Every row in the rendered page is checked to carry a count above
    zero, the rows are checked to add up to the 51 dots drawn beside
    them, and at least one card with a hidden row is checked to exist, so
    this cannot pass by never meeting one.
    """
    seen = 0
    hidden = 0
    for html in forecast_words:
        if not isinstance(html, str) or 'class="dots"' not in html:
            continue
        block = html.split('class="dots"')[1].split("</div>")[0]
        rows = re.findall(r"<li>(.*?)</li>", block, flags=re.S)
        counts = []
        for row in rows:
            said = re.sub(r"<[^>]+>", "", row).strip()
            name, _, number = said.rpartition(": ")
            assert name, said
            assert number.isdigit(), said
            assert int(number) > 0, said
            counts.append(int(number))
        assert rows, block[:200]
        # The rows account for all 51 dots: nothing is dropped, only the
        # empty names.
        grid = block.split('class="dotgrid"')[1].split("</ol>")[0]
        drawn = grid.count("<li")
        assert drawn == 51, drawn
        assert sum(counts) == 51, (counts, drawn)
        if len(rows) < 4:
            hidden += 1
        seen += 1
    assert seen > 20, seen
    assert hidden, "no card had a band with no dots in it"


@needs_node
@pytest.mark.parametrize("size", ["390x664", "1440x900"])
def test_one_footer_with_no_second_warning_and_one_credits_handle(
        viewport, size):
    """SPEC 11.40. The same sentence twice is the second one unread.

    11.39 made the warning a bar across the width of the header on all
    four pages. The footer's copy of it was then the second time a reader
    met that sentence, and the footer also had two controls for one
    thing: a link reading "Credits and licences in full" that opened the
    disclosure whose own handle, two lines below, read "Credits and
    licences".

    What is left is the attribution ECMWF's licence asks for, visible
    whatever a reader does, and one handle to the full form of it.
    """
    seen = viewport["phone"][size]["first"]
    assert seen["warnings"] == 1, seen["warnings"]
    assert seen["warnText"].startswith("Not an official warning."), (
        seen["warnText"])
    assert seen["creditControls"] == 1, seen["creditControls"]
    # The attribution itself is still outside the disclosure.
    assert "ECMWF" in (seen["creditText"] or ""), seen["creditText"]
    assert "CC BY 4.0" in seen["creditText"], seen["creditText"]
    assert "in full" not in seen["creditText"], seen["creditText"]
    # And the two document pages carry the same footer, with one handle.
    for path, page in viewport["pages"].items():
        assert page["warnings"] == 1, (path, page["warnings"])
        assert page["creditControls"] == 1, (path, page["creditControls"])


@needs_node
def test_the_footer_is_inside_the_panel_on_a_desktop(viewport):
    """SPEC 11.40. Under the two links, at the bottom of the right column.

    On a phone the footer is the last block of the one column, which is
    where a footer goes. On a desktop it was a band under the map, which
    is a third thing competing for the width the map wants; it is the
    bottom of the right-hand panel now, under "How to read this map" and
    "Report card".
    """
    wide = viewport["phone"]["1440x900"]["first"]
    assert wide["footerInPanel"] is True
    assert wide["footer"], "no footer"
    # Inside the panel's own column: its left edge is the card's, not the
    # page's, and the map is to the left of it.
    assert wide["footer"]["right"] <= wide["card"]["right"] + 2, (
        wide["footer"], wide["card"])
    assert wide["footer"]["width"] <= wide["card"]["width"] + 2, (
        wide["footer"], wide["card"])
    assert wide["footer"]["top"] >= wide["card"]["bottom"] - 1, (
        wide["footer"], wide["card"])
    assert wide["mapcard"]["right"] < wide["footer"]["top"] + 10_000
    assert wide["footer"]["width"] < wide["innerWidth"] - 200, (
        wide["footer"], wide["innerWidth"])
    # On a phone it is the last block of the one column and has the width.
    narrow = viewport["phone"]["390x664"]["first"]
    assert narrow["footerInPanel"] is True
    assert narrow["footer"]["width"] >= narrow["card"]["width"] - 2, (
        narrow["footer"], narrow["card"])


# ------------------- SPEC 11.40: the desktop, and the map that fills it

# The four screens item 8 names. 1366 by 768 is the laptop; 1366 by 650 is
# that laptop after Chrome's own bars have taken their 118 pixels, which is
# what a reader actually has. 1024 by 768 is the narrowest desktop this
# site claims, and 1440 by 900 the widest it is measured at.
DESKTOPS = ("1366x768", "1366x650", "1440x900", "1024x768")

# How far down the map may start, and how tall it must be: measured, and
# written here rather than in a comment.
MAP_TOP = {"1366x768": 230, "1366x650": 230, "1440x900": 260,
           "1024x768": 300}
MAP_TALL = {"1440x900": 520}


@needs_node
@pytest.mark.parametrize("size", ["1366x768", "1440x900"])
def test_the_desktop_asks_everything_in_one_row(viewport, size):
    """SPEC 11.40. The box, the five days and the three amounts, in one row.

    They were three rows -- the search box, then "Which day?" and its five
    pills, then "How much rain?" and its three -- with the gaps between
    groups doubled, and together they took 300 pixels off the top of the
    screen before the map began. The three of them are one row now, each
    group with its own small label above it, at ordinary spacing.
    """
    seen = viewport["phone"][size]["first"]
    for what in ("controls", "asks", "days", "amounts", "mapcard"):
        assert seen[what], what
    # One row: the three groups start within a few pixels of each other.
    tops = [seen["asks"]["top"], seen["days"]["top"], seen["amounts"]["top"]]
    assert max(tops) - min(tops) <= 6, tops
    # And the row is one row high: no group is below another.
    assert seen["controls"]["height"] <= 110, seen["controls"]
    # "What does mm mean?" is on the amount pills' own line, after them.
    assert seen["mmwhat"]["top"] >= seen["amountRow"]["top"] - 4, (
        seen["mmwhat"], seen["amountRow"])
    assert seen["mmwhat"]["bottom"] <= seen["amountRow"]["bottom"] + 4, (
        seen["mmwhat"], seen["amountRow"])
    assert seen["mmwhat"]["top"] < seen["amountRow"]["bottom"], (
        seen["mmwhat"], seen["amountRow"])
    # The content is a centred column of at most 1280 pixels.
    assert seen["controls"]["width"] <= 1280, seen["controls"]
    assert seen["mapcard"]["width"] + seen["card"]["width"] <= 1280, (
        seen["mapcard"], seen["card"])
    assert seen["overlapping"] == [], seen["overlapping"]


@needs_node
@pytest.mark.parametrize("size", DESKTOPS)
def test_the_map_fills_what_is_left_of_the_screen(viewport, size):
    """SPEC 11.40. The map starts near the top and reaches the fold.

    What is above it is the header band, the warning bar and the one row
    of controls. The map takes the rest: `min(100dvh - 260px, 640px)`,
    with the 260 measured against these four screens and the ceiling
    there so that a tall screen does not stretch one square to the size
    of a town.

    "What does mm mean?" is shut, which is how the page opens.
    """
    seen = viewport["phone"][size]["first"]
    height = int(size.split("x")[1])
    assert seen["mmOpen"] is False, "the measurement is with it shut"
    assert seen["mapcard"]["top"] <= MAP_TOP[size], (
        size, seen["mapcard"], MAP_TOP[size])
    if size in MAP_TALL:
        assert seen["map"]["height"] >= MAP_TALL[size], (
            size, seen["map"])
    # The whole map card is on the screen: nothing of it needs a scroll.
    assert seen["mapcard"]["bottom"] <= height, (size, seen["mapcard"])
    assert seen["scrollY"] == 0, seen["scrollY"]


@needs_node
@pytest.mark.parametrize("size", DESKTOPS)
def test_every_india_square_is_in_the_visible_map_on_a_desktop(viewport,
                                                               size):
    """SPEC 11.40. Kerala and Ladakh, with no page scrolled.

    The map is fitted to the box of 1.4 and the box is the whole country,
    so this is not a check of the fit for its own sake: it is a check
    that the box the fit is given is entirely on the screen. All 4,613
    forecast squares and every point of the drawn outline are projected
    into the canvas's own pixels from the bounds the map reports, and
    every one of them has to land inside the part of the canvas a reader
    can see without scrolling the page.
    """
    seen = viewport["phone"][size]["first"]
    height = int(size.split("x")[1])
    view = seen["view"]
    if not view:
        pytest.skip("the map did not draw")
    box = seen["map"]
    width = box["width"]
    tall = box["height"]
    # How much of the canvas is above the fold.
    visible = min(tall, height - box["top"])
    assert visible >= tall - 1, (size, box, height)
    for lat, lon, x, y in on_screen(india_points(), view["bounds"],
                                    width, tall):
        assert -1 <= x <= width + 1, (size, lat, lon, x)
        assert -1 <= y <= visible + 1, (size, lat, lon, y, visible)
    # Kerala's south and Ladakh's north by name, so a failure says which.
    for name, (lat, lon) in {"Kerala": (8.25, 77.0),
                             "Ladakh": (34.75, 77.5)}.items():
        inside = on_screen([(lat, lon)], view["bounds"], width, tall)[0]
        assert 0 <= inside[2] <= width, (size, name, inside)
        assert 0 <= inside[3] <= visible, (size, name, inside)


@needs_node
def test_the_card_has_no_five_day_strip(forecast_words):
    """SPEC 11.40. Two rows of days was one row too many.

    The card drew the same five days as the pills above the map, with the
    same five counts for the same amount, 400 pixels further down, each
    with its own way of drawing a day and its own way of drawing a count.
    The forecast is five days long, so one row of five is the whole of
    it, and the row a reader is already using carries the numbers.
    """
    for html in forecast_words:
        if not isinstance(html, str) or 'class="placeline"' not in html:
            continue
        for gone in ('class="strip"', 'class="cell', "The next five days"):
            assert gone not in html, gone
    # And nothing in the page or the stylesheet draws one.
    panel = PANEL.read_text("utf-8")
    code = re.sub(r"/\*.*?\*/", "", panel, flags=re.S)
    code = "\n".join(line.split("//")[0] for line in code.splitlines())
    for gone in ("DayStrip", "cellcount", "cellday"):
        assert gone not in code, gone
    css = (ROOT / "web" / "src" / "styles.css").read_text("utf-8")
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for gone in (".strip", ".cellday", ".cellcount", ".cell {"):
        assert gone not in bare, gone


@needs_node
def test_a_day_pill_carries_its_own_count_and_says_it_in_words(exports,
                                                               forecast_words):
    """SPEC 11.40. A bare number, a square in the map's colour, a sentence.

    The number is what a reader came for and the square is what ties it
    to the map; neither says what it is, so the pill's accessible name is
    the whole sentence and the caption under the row says it once in
    writing. Both come from one function, so the two cannot differ.
    """
    said = exports(PALETTE, "pillSentence",
                   [["Today, 15 Nov", 26, 10, 51]])[0]
    assert said == ("Today, 15 Nov: 26 of the 51 runs bring 10 mm or more "
                    "here"), said
    # With no count -- nothing chosen -- the name is the day and no more.
    assert exports(PALETTE, "pillSentence",
                   [["Today, 15 Nov", None, 10, 51]])[0] == "Today, 15 Nov"
    note = exports(PALETTE, "pillNote", [[50, 51]])[0]
    assert note == ("The number on each day: how many of the 51 runs bring "
                    "50 mm or more here."), note

    # And in the rendered row: five pills, five counts inside the 51, the
    # caption once, and every pill naming its own count in its own name.
    seen = 0
    for html in forecast_words:
        if not isinstance(html, str) or "pillcount" not in html:
            continue
        counts = re.findall(r'class="pillcount">.*?</span>(\d+)</span>',
                            html)
        assert len(counts) == 5, counts
        assert all(0 <= int(n) <= 51 for n in counts), counts
        text = words_of(html)
        assert text.count("The number on each day:") == 1, text
        for number in counts:
            assert f": {number} of the 51 runs bring " in html, number
        seen += 1
    assert seen == 3, seen


@needs_node
@pytest.mark.parametrize("size", ["390x664", "1440x900"])
def test_the_pills_carry_the_counts_only_once_a_place_is_chosen(viewport,
                                                                exports,
                                                                size):
    """SPEC 11.40. No numbers before, the map's own colours after.

    Before a place is chosen a count would be a count of nothing, so the
    pills are the day and the date and there is no caption. After one,
    every pill carries that place's count for the chosen amount with a
    square in the palette's colour for it -- the map's colour, from the
    one table in palette.js -- and the chosen pill's number is the number
    the card's own sentence gives.
    """
    page = viewport["phone"][size]
    first = page["first"]
    # Before: no numbers, no caption.
    assert [p["count"] for p in first["dayCounts"]] == [None] * 5, (
        first["dayCounts"])
    assert first["pillNote"] is None, first["pillNote"]

    # After, by every way of choosing a place that this size measures.
    seen = 0
    for how, which in (("afterSearch", "searchCard"),
                       ("afterLocate", "locateCard"),
                       ("afterMapTap", "card")):
        later = page.get(how)
        card = page.get(which)
        if not later or not card:
            continue
        pills = later["dayCounts"]
        assert len(pills) == 5, pills
        counts = [int(p["count"]) for p in pills]
        assert all(0 <= n <= 51 for n in counts), counts
        # The caption, once, with the chosen amount in it.
        assert later["pillNote"].strip() == (
            "The number on each day: how many of the 51 runs bring 1 mm "
            "or more here."), later["pillNote"]
        # Each square is the palette's colour for its own count, which is
        # the colour the map paints that square.
        wanted = exports(PALETTE, "colourOf", [[n] for n in counts])
        for pill, hexed in zip(pills, wanted):
            red, green, blue = (int(hexed[at:at + 2], 16)
                                for at in (1, 3, 5))
            assert pill["colour"] == f"rgb({red}, {green}, {blue})", (
                how, pill, hexed)
            # And a white hairline, so the square is still a square on
            # the navy of the chosen pill.
            assert pill["edge"] == "rgb(255, 255, 255)", (how, pill)
            # The pill's own name says the sentence, not just the number.
            assert "of the 51 runs bring" in pill["name"], pill
        # The chosen pill's count is the card's own count.
        chosen = [p for p in pills if p["on"]]
        assert len(chosen) == 1, pills
        said = re.search(r"\((\d+) of 51\)", card["cardText"] or "")
        assert said, card["cardText"][:160]
        assert int(chosen[0]["count"]) == int(said.group(1)), (
            how, chosen, said.group(1))
        seen += 1
    assert seen >= 2, seen


@needs_node
def test_tapping_a_day_pill_still_changes_the_day(viewport):
    """SPEC 11.40. The pills are controls first and a reading second.

    Carrying a number is the new job; the old one -- choosing which day
    the map paints and the card answers for -- is unchanged. A pill is
    tapped for real and the map's own paint key, the card's sentence and
    which pill is filled all follow it.
    """
    page = viewport["phone"]["390x664"]
    after = page.get("afterDayTap")
    assert after, "the day tap was never measured"
    before = page["afterMapTap"]
    # A different day is chosen, and exactly one pill is filled.
    assert [p["on"] for p in after["dayCounts"]] != [
        p["on"] for p in before["dayCounts"]], after["dayCounts"]
    assert sum(1 for p in after["dayCounts"] if p["on"]) == 1
    # The card answers for the day that is now chosen.
    chosen = next(p for p in after["dayCounts"] if p["on"])
    said = re.search(r"\((\d+) of 51\)", page["dayTapCard"]["cardText"])
    assert said, page["dayTapCard"]["cardText"][:160]
    assert int(chosen["count"]) == int(said.group(1)), (chosen, said.group(1))
    # And the map is painting that day: its own key says which.
    assert after["view"]["paint"] != before["view"]["paint"], (
        after["view"]["paint"], before["view"]["paint"])


@needs_node
@pytest.mark.parametrize("size", DESKTOPS)
def test_the_desktop_map_is_whole_on_the_screen_after_a_choice_too(viewport,
                                                                  size):
    """SPEC 11.40. Choosing a place moves the map down; it stays on screen.

    Item 10 puts a third line on every day pill and a caption under the
    row, and both appear only once a place is chosen -- so the row above
    the map is 77 pixels tall before a choice and 154 after one, and the
    map's top goes from 199 to 275.

    The map's height is worked out from the taller of the two, so the
    whole of it is on the screen in both: that is what is checked here,
    at every size, by all four ways of choosing. Its height never
    changes, so the fit is untouched and India does not move inside it.
    """
    page = viewport["phone"][size]
    first = page["first"]
    height = int(size.split("x")[1])
    seen = 0
    for how in ("afterSearch", "afterLocate", "afterMapTap", "afterDayTap"):
        later = page.get(how)
        if not later:
            continue
        assert abs(later["map"]["height"] - first["map"]["height"]) <= 1, (
            how, later["map"], first["map"])
        assert later["mapcard"]["bottom"] <= height, (
            how, later["mapcard"], height)
        assert later["scrollY"] == 0, (how, later["scrollY"])
        # And the country is still inside the part of the canvas on the
        # screen, which is the whole of it.
        box = later["map"]
        visible = min(box["height"], height - box["top"])
        assert visible >= box["height"] - 1, (how, box, height)
        for lat, lon, x, y in on_screen(india_points(),
                                        later["view"]["bounds"],
                                        box["width"], box["height"]):
            assert -1 <= x <= box["width"] + 1, (how, lat, lon, x)
            assert -1 <= y <= visible + 1, (how, lat, lon, y)
        seen += 1
    assert seen >= 3, seen
