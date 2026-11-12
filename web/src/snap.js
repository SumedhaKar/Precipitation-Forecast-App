// Which 0.25 degree square a latitude and longitude is in. SPEC 11.19.
//
// The page snaps before it asks. A map click and the browser's own location
// are both turned into the centre of their square here, and only that centre
// is sent to /api/place, so the finest thing that ever reaches a request URL
// or a server log is a 28 km square rather than somebody's position.
//
// This duplicates arithmetic that SPEC 11.4 says should live in one place, so
// it is tested rather than trusted: tests/test_api_consistency.py drives this
// file and api/place.mjs over a grid of points under plain `node` and fails if
// they ever name different squares (SPEC 11.24). One copy with a test that the
// two agree is honest; two copies that merely look alike are not.
//
// No imports, so `node` can load it as it stands.

export const LAT_MAX = 38.0; // SPEC 1.4, the India box
export const LAT_MIN = 6.0;
export const LON_MIN = 68.0;
export const LON_MAX = 98.0;
export const STEP = 0.25;
export const TILE = 4.0; // SPEC 8.4

function round2(value) {
  return Math.round(value * 100) / 100;
}

/** Is this inside the India box at all? The mask is a separate question. */
export function inBox(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= LAT_MIN && lat <= LAT_MAX
    && lon >= LON_MIN && lon <= LON_MAX;
}

/**
 * The square containing a point: its row, column and own centre.
 *
 * The same two lines as api/place.mjs, which is the point of the test.
 */
export function snap(lat, lon) {
  const i = Math.round((LAT_MAX - lat) / STEP);
  const j = Math.round((lon - LON_MIN) / STEP);
  return {
    i,
    j,
    lat: round2(LAT_MAX - STEP * i),
    lon: round2(LON_MIN + STEP * j),
  };
}

/** The 4 degree tile a square is in, named after its south-west corner. */
export function tileName(lat, lon) {
  const south = Math.floor(lat / TILE) * TILE;
  const west = Math.floor(lon / TILE) * TILE;
  return `${Math.abs(south)}${south >= 0 ? 'N' : 'S'}`
    + `_${Math.abs(west)}${west >= 0 ? 'E' : 'W'}`;
}

/** Where a square's byte is in a counts file. SPEC 8.4: row major. */
export function byteIndex(i, j, nLon) {
  return i * nLon + j;
}

/** "28.50 N 77.25 E". Two decimals always: the grid is 0.25 degrees. */
export function squareText(lat, lon) {
  const ns = `${Math.abs(lat).toFixed(2)} ${lat >= 0 ? 'N' : 'S'}`;
  const ew = `${Math.abs(lon).toFixed(2)} ${lon >= 0 ? 'E' : 'W'}`;
  return `${ns} ${ew}`;
}

/**
 * Two numbers typed into the search box: "28.5, 77.25" or "28.5 77.25".
 *
 * Returns null for anything else, including one number, three numbers, or a
 * city name, so the caller can fall back to searching the city list.
 */
export function parseLatLon(text) {
  if (typeof text !== 'string') return null;
  const numbers = text.trim().match(
    /^(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!numbers) return null;
  const lat = Number(numbers[1]);
  const lon = Number(numbers[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return { lat, lon };
}
