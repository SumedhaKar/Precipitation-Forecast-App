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
import * as list from './townlist';

export const TOWNS = townList.towns;

export const townLabel = list.townLabel;

export function townsAt(lat, lon) {
  return list.townsAt(TOWNS, lat, lon);
}

export function nameOfSquare(lat, lon) {
  return list.nameOfSquare(TOWNS, lat, lon);
}

export function findTowns(text, most) {
  return list.findTowns(TOWNS, text, most);
}
