// What the map asks the list of states and union territories. SPEC 11.29.
//
// Pure functions over a list handed in, with no imports at all, so `node` can
// load this file and a test can drive them against the real
// web/src/units.json (SPEC 11.24). web/src/places.js binds them to that file.
//
// The file's own order is the order the map tries to place the names in:
// largest polygon first, so the name that gives way when there is no room is
// a small union territory's and not Rajasthan's. Nothing here reorders it.

/**
 * The name to write inside a unit, where to write it, and the room there is.
 *
 * `fit` is how much room there is to write it: half the height in degrees of
 * the tallest box of each measured shape that is still inside the unit's own
 * polygon, centred on this very point (SPEC 11.31). The map measures the
 * word, unprojects its box, and draws the full name only where the box
 * passes. Where it does not, the unit gets `code`.
 */
export function unitLabels(units) {
  return units.map((unit) => ({
    name: unit.name,
    code: unit.code,
    lat: unit.lat,
    lon: unit.lon,
    fit: unit.fit,
  }));
}

/**
 * The one city each unit labels, largest population first.
 *
 * Population orders the labels and nothing else: on a phone there is room for
 * a handful of city names and this is which handful. It is Natural Earth's
 * own POP_MAX, which is a metropolitan figure of unstated year, so it is
 * never shown to anybody — ranking is all it is good for.
 *
 * Two of the 36 have no square to forecast, Kavaratti and Port Blair, and
 * they are still in this list. The islands exist; the map says where they are
 * and the panel says why there are no numbers for them (SPEC 11.28).
 */
export function cityLabels(units) {
  return units
    .filter((unit) => unit.city)
    .map((unit) => ({
      name: unit.city.name,
      unit: unit.name,
      lat: unit.city.lat,
      lon: unit.city.lon,
      pop: unit.city.pop,
      forecast: !unit.city.not_forecast,
    }))
    .sort((a, b) => b.pop - a.pop || a.name.localeCompare(b.name));
}
