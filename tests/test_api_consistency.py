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

import http.server
import json
import os
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
