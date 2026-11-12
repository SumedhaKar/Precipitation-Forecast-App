// The island groups this 0.25 degree grid cannot carry. SPEC 11.28.
//
// Lakshadweep has a town in the search list (Kavaratti) and no square in the
// forecast at all, and the south of the Andaman Islands has a town (Port
// Blair) whose square the model calls sea. Both used to answer "that is
// outside the forecast area", which is true and useless: it reads as though
// the reader had clicked the ocean.
//
// So each group gets one plain sentence saying what is actually the case.
// Every number in them was measured against config/india_mask.json and the
// model's own land-sea mask, and the measurements are written out in
// SPEC 11.28 next to the commands that produced them.
//
// api/place.mjs carries the same table, because it answers the same question
// for a reader with no JavaScript, and a test drives both files under `node`
// over the island boxes and fails if one word differs. Two copies that merely
// look alike would not be worth having; two copies a test keeps identical is
// the same arrangement SPEC 11.24 already uses for the snapping arithmetic.
//
// No imports, so `node` can load this file as it stands.

// `lat` and `lon` are inclusive bounds, the same boxes as the
// `island_groups` of config/india_mask.json.
export const ISLANDS = [
  {
    group: 'Lakshadweep',
    lat: [8.0, 12.5],
    lon: [71.5, 74.0],
    note: 'Lakshadweep is not forecast. Every island in the group is far '
      + 'smaller than one square of this grid, which is about 28 km across: '
      + 'of the 209 squares covering Lakshadweep, not one has its centre on '
      + 'land, so there is no square here to forecast. This is a limit of '
      + 'the grid, not a forecast of no rain.',
  },
  {
    group: 'Andaman & Nicobar',
    lat: [6.0, 14.0],
    lon: [92.0, 94.5],
    note: 'This part of the Andaman and Nicobar Islands is not forecast. The '
      + 'islands here are narrower than one square of this grid, about 28 km, '
      + 'so the model treats the square as sea. Three squares in the group '
      + 'are land on this grid and are forecast: 12.75 N 92.75 E, '
      + '12.50 N 92.75 E and 10.75 N 92.50 E. This is a limit of the grid, '
      + 'not a forecast of no rain.',
  },
];

/**
 * The sentence for a point no square could be found for, or null.
 *
 * Only ever called once the search for a square has already failed, so a
 * forecast Andaman square is never described by the Andaman sentence: it has
 * numbers of its own and they are what the reader is shown.
 */
export function notFoundNote(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const found = ISLANDS.find(
    (island) => lat >= island.lat[0] && lat <= island.lat[1]
      && lon >= island.lon[0] && lon <= island.lon[1]);
  return found ? found.note : null;
}

/** The group a point is in, for a short label beside the sentence. */
export function islandGroup(lat, lon) {
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const found = ISLANDS.find(
    (island) => lat >= island.lat[0] && lat <= island.lat[1]
      && lon >= island.lon[0] && lon <= island.lon[1]);
  return found ? found.group : null;
}
