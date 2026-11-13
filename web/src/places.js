// The town list, bound to the file it lives in. SPEC 11.28.
//
// 215 towns from Natural Earth 1:10m populated places, public domain, kept
// where the point falls inside the drawn India point-of-view outline — the
// same geometry the forecast mask was cut with. scripts/build_towns.py writes
// the file and refuses to write it if that stops being true.
//
// Every entry holds the 0.25 degree square the page shows, never the town's
// own position, so nothing finer than 28 km is in this bundle at all.
//
// The thinking is all in web/src/townlist.js, which has no imports so that
// `node` can test it against this very file. This is the glue.

import townList from './towns.json';
import unitList from './units.json';
import * as list from './townlist';
import * as units from './unitlist';

export const TOWNS = townList.towns;

// SPEC 11.29. The 36 states and union territories, largest first, and the one
// city each of them labels, largest population first. Both are only ever
// drawn as names on the map; the search still reads all 215 towns.
export const UNITS = unitList.units;

// SPEC 11.31. The shapes of box the room inside each unit was measured for,
// which the map needs to read a unit's `fit` at all. One list for all 36, in
// the file the numbers came from, so the two cannot drift apart.
export const FIT_ASPECTS = unitList.fit.aspects;
export const STATE_LABELS = units.unitLabels(UNITS);
export const CITY_LABELS = units.cityLabels(UNITS);

export const townLabel = list.townLabel;

export function townsAt(lat, lon) {
  return list.townsAt(TOWNS, lat, lon);
}

export function nameOfSquare(lat, lon) {
  return list.nameOfSquare(TOWNS, lat, lon);
}

/** SPEC 11.38. The city's name, "near <city>", or "this area". */
export function placeName(lat, lon) {
  return list.placeName(TOWNS, lat, lon);
}

/** The nearest city within 50 km, or null. */
export function nearestTown(lat, lon, withinKm) {
  return list.nearestTown(TOWNS, lat, lon, withinKm);
}

export function findTowns(text, most) {
  return list.findTowns(TOWNS, text, most);
}

/** The nearest names to something that matched nothing. Never auto-picked. */
export function nearTowns(text, most) {
  return list.nearTowns(TOWNS, text, most);
}
