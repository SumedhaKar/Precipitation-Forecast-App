// GET /api/place?lat=<degrees north>&lon=<degrees east>
// One square's counts, dots and 51 member values, from the published tiles.
// SPEC 11.7.
//
// What this function does NOT do: arithmetic of its own on the forecast. The
// counts and the dots are the published ones, and the only number computed
// here is the whole millimetre, which is the published integer divided by 16
// and rounded down (SPEC 8.4). If the rounding rule ever changes, the counts
// on the page still cannot disagree with the counts in the store.
//
// No dependencies and no token, as api/health.mjs; see the note there about
// the shared lines.

import { readFileSync } from 'node:fs';

const LAT_MAX = 38.0; // SPEC 1.4, the India box
const LAT_MIN = 6.0;
const LON_MIN = 68.0;
const LON_MAX = 98.0;
const STEP = 0.25;
const TILE = 4.0; // SPEC 8.4
const STEPS_PER_MM = 16; // SPEC 8.4, 1 mm / 0.0625 mm
const STALE_HOURS = 36; // SPEC 11.8
const MAX_AGE = 60;

function storeBase() {
  const fromEnv = process.env.STORE_BASE_URL;
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  const candidates = [
    new URL('../config/store.json', import.meta.url),
    new URL('config/store.json', `file://${process.cwd()}/`),
  ];
  for (const candidate of candidates) {
    try {
      const base = JSON.parse(readFileSync(candidate, 'utf8')).base_url;
      if (base) return base.replace(/\/+$/, '');
    } catch {
      // Try the next one.
    }
  }
  return null;
}

function json(body, status, maxAge) {
  return new Response(JSON.stringify(body, null, 1), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': `public, max-age=${maxAge}`,
    },
  });
}

function istNow(now) {
  return new Date(now + 5.5 * 3_600_000).toISOString()
    .replace('T', ' ').slice(0, 19) + ' IST';
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// SPEC 11.23. The same function as in api/health.mjs; see the note above
// about the lines these two files share.
export function shortIst(fromIst) {
  const at = Date.parse(fromIst);
  if (Number.isNaN(at)) return null;
  const ist = new Date(at + 5.5 * 3_600_000);
  return `${DAYS[ist.getUTCDay()]} ${ist.getUTCDate()} `
    + `${MONTHS[ist.getUTCMonth()]}`;
}

function mm(threshold) {
  // 1.0 prints as "1 mm", and a fractional threshold would print as itself.
  return `${Number.isInteger(threshold) ? threshold : threshold} mm`;
}

// SPEC 11.20: one plain sentence for one day, built from that day's counts
// and nothing else.
//
// There is no judgement in here and there must never be: no "dry", no
// "likely", no "chance", no percentage, no banding. The thresholds come from
// the manifest rather than from a constant, so the sentence cannot describe
// a threshold the run did not publish. Counts are monotone by SPEC 4.2, so a
// higher threshold is named only once a lower one has been reached, and the
// first threshold nothing reaches ends the sentence.
export function daySentence(counts, thresholds, members) {
  const have = thresholds.map((threshold, k) => ({
    threshold,
    count: Number(counts[k]),
  }));
  if (!have.length || !Number.isFinite(have[0].count)) return null;

  const verb = (count) => (count === 1 ? 'reaches' : 'reach');
  const first = have[0];
  if (first.count === 0) {
    return `0 of ${members} model runs reach ${mm(first.threshold)}.`;
  }

  let sentence = `${first.count} of ${members} model runs `
    + `${verb(first.count)} ${mm(first.threshold)}`;
  for (const next of have.slice(1)) {
    if (!Number.isFinite(next.count)) break;
    if (next.count === 0) {
      sentence += `, none reach ${mm(next.threshold)}`;
      break;
    }
    sentence += `, ${next.count} ${verb(next.count)} ${mm(next.threshold)}`;
  }
  return `${sentence}.`;
}

// SPEC 8.4: a tile is named after its south-west corner in whole degrees.
function tileName(lat, lon) {
  const south = Math.floor(lat / TILE) * TILE;
  const west = Math.floor(lon / TILE) * TILE;
  const ns = south >= 0 ? 'N' : 'S';
  const ew = west >= 0 ? 'E' : 'W';
  return `${Math.abs(south)}${ns}_${Math.abs(west)}${ew}`;
}

// SPEC 11.7 step 2.
function snap(lat, lon) {
  const i = Math.round((LAT_MAX - lat) / STEP);
  const j = Math.round((lon - LON_MIN) / STEP);
  return { i, j, lat: round2(LAT_MAX - STEP * i), lon: round2(LON_MIN + STEP * j) };
}

function squareOf(i, j) {
  return { i, j, lat: round2(LAT_MAX - STEP * i), lon: round2(LON_MIN + STEP * j) };
}

async function getJson(url) {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`the store answered ${response.status} for ${url}`);
  }
  return response.json();
}

function findRecord(tile, square) {
  if (!tile || !Array.isArray(tile.squares)) return null;
  return tile.squares.find(
    (record) => Math.abs(record.lat - square.lat) < 1e-9
      && Math.abs(record.lon - square.lon) < 1e-9,
  ) || null;
}

// SPEC 11.7: the snapped square, then the eight neighbours one square out,
// nearest first, ties broken north then west. Nothing beyond one square.
function candidates(centre) {
  const ring = [];
  for (let di = -1; di <= 1; di += 1) {
    for (let dj = -1; dj <= 1; dj += 1) {
      if (di === 0 && dj === 0) continue;
      ring.push(squareOf(centre.i + di, centre.j + dj));
    }
  }
  ring.sort((a, b) => {
    const da = (a.i - centre.i) ** 2 + (a.j - centre.j) ** 2;
    const db = (b.i - centre.i) ** 2 + (b.j - centre.j) ** 2;
    if (da !== db) return da - db;
    if (a.i !== b.i) return a.i - b.i; // north first
    return a.j - b.j; // then west
  });
  return ring.filter(
    (square) => square.lat >= LAT_MIN && square.lat <= LAT_MAX
      && square.lon >= LON_MIN && square.lon <= LON_MAX,
  );
}

function daysFrom(manifest, record) {
  const thresholds = manifest.thresholds_mm || [1, 10, 50];
  return (manifest.days || []).map((day, index) => {
    const counts = record.c[index] || [];
    const codes = record.m[index] || [];
    return {
      lead_day: day.lead_day,
      label: day.label,
      short_ist: shortIst(day.from_ist),
      from_ist: day.from_ist,
      to_ist: day.to_ist,
      sentence: daySentence(counts, thresholds, manifest.members),
      counts: {
        ge1: counts[0],
        ge10: counts[1],
        ge50: counts[2],
      },
      counts_by_threshold: thresholds.map((threshold, k) => ({
        threshold_mm: threshold,
        count: counts[k],
        of: manifest.members,
      })),
      dots: record.d[index],
      members_mm: codes.map((code) => Math.floor(code / STEPS_PER_MM)),
    };
  });
}

export default {
  async fetch(request) {
    const base = storeBase();
    if (!base) {
      return json({
        ok: false,
        error: 'no base URL: STORE_BASE_URL is not set and '
          + 'config/store.json could not be read',
      }, 500, 0);
    }

    const asked = new URL(request.url).searchParams;
    const lat = Number(asked.get('lat'));
    const lon = Number(asked.get('lon'));
    if (!asked.get('lat') || !asked.get('lon')
      || !Number.isFinite(lat) || !Number.isFinite(lon)) {
      return json({
        ok: false,
        error: 'lat and lon are required, in degrees north and degrees east',
      }, 400, 0);
    }
    if (lat < LAT_MIN || lat > LAT_MAX || lon < LON_MIN || lon > LON_MAX) {
      return json({
        ok: false,
        error: `outside the forecast area: it covers ${LAT_MIN} to ${LAT_MAX} `
          + `degrees north and ${LON_MIN} to ${LON_MAX} degrees east`,
        asked: { lat, lon },
      }, 400, 0);
    }

    const now = Date.now();
    let manifest;
    try {
      manifest = await getJson(`${base}/manifest.json`);
      if (!manifest || typeof manifest.run_id !== 'string') {
        throw new Error('the store\'s manifest.json has no run_id');
      }
    } catch (error) {
      return json({ ok: false, error: `the store could not be read: ${error.message}` },
        503, 0);
    }

    const tiles = new Map();
    const loadTile = async (name) => {
      if (!tiles.has(name)) {
        tiles.set(name, await getJson(`${base}/${manifest.paths.tiles}/${name}.json`));
      }
      return tiles.get(name);
    };

    const centre = snap(lat, lon);
    let square = centre;
    let record;
    let moved = null;
    try {
      record = findRecord(await loadTile(tileName(centre.lat, centre.lon)), centre);
      if (!record) {
        for (const near of candidates(centre)) {
          // eslint-disable-next-line no-await-in-loop
          const found = findRecord(await loadTile(tileName(near.lat, near.lon)), near);
          if (found) {
            record = found;
            square = near;
            moved = {
              from: { lat: centre.lat, lon: centre.lon },
              to: { lat: near.lat, lon: near.lon },
              squares: 1,
              why: `${centre.lat} N ${centre.lon} E is sea or outside India on `
                + 'this 0.25 degree grid',
            };
            break;
          }
        }
      }
    } catch (error) {
      return json({ ok: false, error: `the store could not be read: ${error.message}` },
        503, 0);
    }

    if (!record) {
      return json({
        ok: false,
        error: 'outside the forecast area',
        detail: 'that square, and all eight squares around it, are sea or '
          + 'outside India on this 0.25 degree grid',
        asked: { lat, lon },
        square: { lat: centre.lat, lon: centre.lon, i: centre.i, j: centre.j },
        tile: tileName(centre.lat, centre.lon),
      }, 404, MAX_AGE);
    }

    const runTime = Date.parse(manifest.run_time_utc);
    const ageHours = Number.isNaN(runTime) ? null : (now - runTime) / 3_600_000;

    return json({
      ok: true,
      run: {
        run_id: manifest.run_id,
        run_time_utc: manifest.run_time_utc,
        run_time_ist: manifest.run_time_ist,
        publish_time_ist: manifest.publish_time_ist,
        age_hours: ageHours === null ? null : Math.round(ageHours * 10) / 10,
        stale: ageHours === null ? null : ageHours > STALE_HOURS,
        stale_after_hours: STALE_HOURS,
      },
      square: {
        lat: square.lat,
        lon: square.lon,
        i: square.i,
        j: square.j,
        tile: tileName(square.lat, square.lon),
        asked: { lat, lon },
        moved,
      },
      thresholds_mm: manifest.thresholds_mm,
      dot_categories: manifest.dot_categories,
      members: manifest.members,
      member_display: 'whole millimetres, rounded down',
      days: daysFrom(manifest, record),
      notes: {
        zero: '0 mm means under 1 mm.',
        // SPEC 11.21, amended 12 November 2026. This used to read "These are
        // model-run counts, not probabilities."
        counts: `N of ${manifest.members} model runs, which is not a `
          + 'calibrated probability.',
        warning: 'Not an official warning.',
      },
      checked_at_ist: istNow(now),
    }, 200, MAX_AGE);
  },
};
