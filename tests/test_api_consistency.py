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
const [file, name, args] = process.argv.slice(2);
const mod = await import(file);
const fn = mod[name];
if (typeof fn !== 'function') {
  throw new Error(`${file} exports no function called ${name}`);
}
const out = JSON.parse(args).map((call) => fn(...call));
process.stdout.write(JSON.stringify(out));
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

    def run(module: Path, name: str, calls: list[list]) -> list:
        done = subprocess.run(
            [node, str(path), Path(module).as_uri(), name, json.dumps(calls)],
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
