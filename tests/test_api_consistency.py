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

import gzip
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

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
            capture_output=True, text=True, check=False)
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
        capture_output=True, text=True, check=False, env=environment)
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
    assert said[0] == ("These are counts out of 51 model runs, not a "
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


@pytest.mark.skipif(
    not (ROOT / "data" / "raw" / "ne"
         / "ne_10m_populated_places.shp").exists(),
    reason="the Natural Earth populated places shapefile is not here; "
           "data/ is never committed")
def test_the_committed_town_list_is_what_the_script_writes():
    """SPEC 11.28: the file is built, not hand-edited."""
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_towns.py"), "--check"],
        capture_output=True, text=True, check=False, cwd=ROOT)
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

    # Never more than three, and never an answer: the ones that are offered
    # a near miss are exactly the ones the search itself could not match, so
    # the page is always asking rather than resolving.
    for word, answer, matches in zip(asked, near, found):
        assert len(answer) <= 3, word
        if answer:
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
        assert "town" in line

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
        assert "search for a town" in line
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
    # The search and the panel are outside the map's area, so they are drawn
    # whatever happened to it.
    assert app.index("mapProblem(noMap)") < app.index("<Search")


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


def test_the_title_in_the_tab_is_the_title_on_the_page():
    """SPEC 11.29. One sentence, in both places, word for word."""
    wanted = "India rain forecast: how many of 51 model runs say rain"
    html = INDEX_HTML.read_text("utf-8")
    app = APP.read_text("utf-8")

    assert f"<title>{wanted}</title>" in html
    # The page's own <h1> is the same sentence in two spans, so that a phone
    # can drop the clause.
    assert '<span className="title-what">India rain forecast</span>' in app
    assert ": how many of 51 model runs say rain" in app
    # The noscript page, which is all a reader without JavaScript sees, says
    # it too.
    assert f"<h1>{wanted}</h1>" in html


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

    assert "export function dayTab(" in controls
    assert "{dayTab(entry.short_ist, entry.lead_day)}" in controls
    assert "`${chosen.label} IST`" in controls
    # And the row is laid out so that it cannot overflow however wide the
    # words turn out to be.
    assert ".days .radios button { flex: 1 1 0;" in styles
    # Nothing in the map page's own rules may scroll sideways. The report
    # card's label grid may (SPEC 11.34): it is a table of 5 columns on a
    # document page, and scrolling it is better than shrinking the words.
    shell = styles.split("/* --------------------------------- the three "
                         "pages, SPEC 11.34 */")[0]
    assert "overflow-x: auto" not in shell
    assert styles.count("overflow-x: auto") == 1


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
    assert "Loading {squareText(square.lat, square.lon)}…" in panel


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
    assert "White: inside India but not forecast at this grid size" in legend
    assert 'className="legend-white"' in legend


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

    for name in ("Legend.jsx", "Panel.jsx"):
        text = (ROOT / "web" / "src" / name).read_text("utf-8")
        parts = text.split('className="swatch"')
        assert len(parts) == 3, name          # two swatches, three pieces
        assert text.count('aria-hidden="true"') == 2, name
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
def test_the_part_of_the_map_under_the_bottom_sheet_is_not_in_view(exports):
    """SPEC 11.32. A phone's map is only as tall as the window leaves it.

    The sheet takes the bottom of the window, so the bottom of the canvas
    can be past the end of it. What a reader can see is the canvas clipped
    to the window, and a square below that line is not in view however
    firmly the canvas says it is there.
    """
    # A 390 by 844 phone, the map starting 270 pixels down (SPEC 11.31) and
    # 464 tall, with the sheet open so the window ends part way down it.
    canvas = {"left": 0, "top": 270, "width": 390, "height": 464}
    whole = exports(INVIEW, "visibleBox",
                    [[canvas, {"width": 390, "height": 844}]])[0]
    assert whole == {"left": 0, "top": 0, "right": 390, "bottom": 464}

    cut = exports(INVIEW, "visibleBox",
                  [[canvas, {"width": 390, "height": 560}]])[0]
    assert cut["bottom"] == 290, cut

    # A square 350 pixels down the canvas is on the canvas and under the
    # sheet. In the whole box it is in view; in the cut box it is not.
    said = exports(INVIEW, "nudge", [
        [{"x": 195, "y": 350}, whole],
        [{"x": 195, "y": 350}, cut],
    ])
    assert said[0] is None
    assert said[1] is not None and said[1][0] == 0 and said[1][1] > 0
    assert 350 - said[1][1] <= cut["bottom"] - 40


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
            capture_output=True, text=True, check=False)
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
                    assert not re.search(r"certain", low), text
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
        return [path.name for path in src.glob("*.js*")
                if f"from './{name}'" in path.read_text(encoding="utf-8")]

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
    """SPEC 11.33, in the page's own structure."""
    panel = PANEL.read_text(encoding="utf-8")

    # The region is the API's, not the page's: the panel names the file in a
    # comment and never reads a square out of it.
    assert "const region = place.square.region;" in panel
    assert "region_rows" not in panel
    assert "import" not in panel.split("const region = place.square.region;")[0]        .split("const THRESHOLDS")[1]

    # A chip on every threshold row, and one for the chosen day and
    # threshold with its line and its expander.
    assert panel.count("<Chip trust={trust} small />") == 1
    assert "<Chip trust={trust} />" in panel
    assert "<summary>Why this label?</summary>" in panel
    assert "<TrustBlock place={place} day={chosen} threshold={threshold} />" \
        in panel
    # The sentence sits under the chosen count and nowhere else.
    assert panel.count('className="pastline"') == 1
    assert "{chosen && trust && trust.past ? (" in panel

    # Nothing in the panel decides a label or a frequency.
    for word in ("Good track record", "Treat as a rough guide",
                 "Not enough past data", "times in 10", "bss", "Math.round"):
        assert word not in panel, word

    css = (ROOT / "web" / "src" / "styles.css").read_text(encoding="utf-8")
    # The sentence is the same size as the count it is under, wide and narrow.
    row = css.split("\n.countrow {")[1].split("}")[0]
    past = css.split("\n.pastline {")[1].split("}")[0]
    assert "font-size: 0.88rem;" in row and "font-size: 0.88rem;" in past
    narrow = css.split("  .countrow { grid-template-columns:")[1]
    assert "font-size: 0.84rem; }" in narrow.split("\n")[0]
    assert ".pastline { font-size: 0.84rem; }" in narrow
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
            capture_output=True, text=True, check=False)
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
        capture_output=True, text=True, check=False, cwd=web, shell=False)
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
        capture_output=True, text=True, check=False, cwd=web)
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
                shown = (f'aria-label="{region}, day {cell["lead"]}, '
                         f'{row["threshold"]} mm: {group["label"]}"')
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
                # "Not an official warning" is the footer's, and it is the
                # one warning word this site is required to say.
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
    """SPEC 11.34: three paths, and the one being read marked in words."""
    navs = rendered["pages"]["nav"]
    assert sorted(navs) == ["/", "/how-we-checked", "/report-card"]
    for path, html in navs.items():
        for other in navs:
            assert f'href="{other}"' in html, (path, other)
        assert html.count('aria-current="page"') == 1
        assert html.count("(you are here)") == 1
        here = html.split('aria-current="page"')[0]
        assert here.rstrip().endswith(f'class="navlink here"') or \
            f'href="{path}"' in here.split("<a")[-1]
    assert "Forecast" in navs["/"]
    assert "Report card" in navs["/report-card"]
    assert "How we checked" in navs["/how-we-checked"]


def test_the_rewrite_sends_every_page_but_the_api_to_one_file():
    """SPEC 11.34. Three paths, one index.html, and api/ untouched."""
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    rewrites = config["rewrites"]
    assert len(rewrites) == 1
    assert rewrites[0]["destination"] == "/index.html"
    pattern = re.compile(rewrites[0]["source"])
    for path in ("/report-card", "/how-we-checked", "/anything"):
        assert pattern.fullmatch(path.lstrip("/")) or pattern.match(path), path
    for path in ("api/place", "api/health"):
        assert not re.fullmatch(rewrites[0]["source"].replace("/(", "("),
                                path), path
    assert config["functions"]["api/*.mjs"]["includeFiles"] == \
        "config/{store,regions}.json"


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
