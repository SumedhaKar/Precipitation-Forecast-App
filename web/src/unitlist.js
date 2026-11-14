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

/**
 * Does what was typed name a state or union territory? SPEC 11.38.
 *
 * Two ways in, and only two. The **name**, in full and in any case, with
 * "and" and "&" treated as the same word and punctuation ignored, so
 * "Jammu & Kashmir" and "jammu and kashmir" are one query. And the
 * **short form** -- WB, UP, MP, TN -- but only when it is the whole query,
 * because two letters inside a longer word are not an abbreviation: "up"
 * on its own is Uttar Pradesh and "udaipur" is a city.
 *
 * Old names of units are here too. A reader who learned "Orissa" has not
 * been told it is "Odisha" by this page, and a page that answers "we don't
 * have Orissa" is wrong rather than unhelpful.
 *
 * Returns the unit, or null. The caller decides what wins where a name is
 * both a city and a unit -- Delhi, Chandigarh, Puducherry -- and SPEC
 * 11.38 says the city does.
 */
export const UNIT_ALSO_KNOWN_AS = {
  Odisha: ['Orissa'],
  Uttarakhand: ['Uttaranchal'],
  Delhi: ['NCT of Delhi', 'National Capital Territory of Delhi'],
  Puducherry: ['Pondicherry'],
  'Tamil Nadu': ['Tamilnadu'],
  'Andaman and Nicobar': ['Andaman and Nicobar Islands', 'Andamans'],
  'Dadra and Nagar Haveli and Daman and Diu': ['Dadra and Nagar Haveli',
    'Daman and Diu'],
  Karnataka: ['Mysore State'],
  Kerala: [],
  Telangana: [],
};

/** "Jammu & Kashmir" and "jammu and kashmir" are one query. */
export function plainName(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function findUnit(units, text) {
  const asked = String(text || '').trim();
  if (!asked) return null;
  const plain = plainName(asked);
  if (!plain) return null;
  for (const unit of units) {
    const names = [unit.name, ...(UNIT_ALSO_KNOWN_AS[unit.name] || [])];
    if (names.some((name) => plainName(name) === plain)) return unit;
  }
  // The short form, and only as the whole query.
  for (const unit of units) {
    if (unit.code && plainName(unit.code) === plain) return unit;
  }
  return null;
}

/** The cities this site forecasts inside one unit, in name order. */
export function townsIn(towns, unitName) {
  return towns
    .filter((town) => town.unit === unitName)
    .slice()
    .sort((one, two) => one.name.localeCompare(two.name));
}

// SPEC 11.38. What a state search says. A state is not a square: rain over
// Rajasthan on one day is not one number, and a page that answered a state
// with a count would be inventing an average nobody asked for.
export function tooBig(unitName) {
  return `${unitName} is too big for one forecast: rain can differ a lot `
    + 'across it. Tap the map, or pick a city:';
}
