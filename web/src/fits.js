// Does a unit's name fit inside the unit? SPEC 11.31.
//
// The fault this is for, seen on the page: on a phone HIMACHAL PRADESH was
// written across Uttarakhand and ARUNACHAL PRADESH across Bhutan and Sikkim,
// and on the desktop JAMMU AND KASHMIR began outside the country altogether
// and UTTARAKHAND hung over Nepal. A name written on the wrong state is not
// a label, it is a mistake about where a place is -- and this map is about
// where places are.
//
// So a full name is drawn at the unit's own label point, centred, with no
// sideways or diagonal nudge, and only when the whole word is inside the
// unit's own polygon. Everywhere else the unit gets its two letter code,
// which is small enough to look for a gap near the point and is never
// mistaken for a name for the neighbours.
//
// The polygons are not here. They are 3 MB of shapefile with no other use on
// this page, so scripts/build_towns.py answers the question where the
// polygons are and units.json carries the answer: for each of a few shapes
// of box, the tallest box of that shape, centred on the label point, that is
// still inside the unit. Boxes of one shape nest, so one number settles each
// shape, and a name is a box.
//
// No imports, so `node` can load this file and a test can drive it against
// the real web/src/units.json (SPEC 11.24).

/**
 * Half the height, in degrees, that a box of this shape has room for.
 *
 * `aspects` and `room` come from units.json -- the shapes measured, widest
 * last, and the unit's own room for each. The shape asked about is rounded
 * **up** to the first one measured, so the box tested is at least as wide as
 * the box drawn: a name that passes is inside the unit with room to spare,
 * never the other way round. Wider than the widest shape measured and there
 * is no answer, so the answer is no.
 */
export function roomFor(aspects, room, aspect) {
  if (!Array.isArray(aspects) || !Array.isArray(room)) return 0;
  if (aspects.length !== room.length || !aspects.length) return 0;
  if (!Number.isFinite(aspect) || aspect <= 0) return 0;
  for (let i = 0; i < aspects.length; i += 1) {
    if (aspect <= aspects[i]) return room[i];
  }
  return 0;
}

/**
 * Is a box this size, centred on the unit's label point, inside the unit?
 *
 * `halfLon` and `halfLat` are half the box's width and height in degrees.
 * The page measures the word in pixels and unprojects its corners, so these
 * are the real box on the real map at the zoom the reader is looking at.
 */
export function fitsInside(aspects, room, halfLon, halfLat) {
  if (!Number.isFinite(halfLon) || !Number.isFinite(halfLat)) return false;
  if (halfLon <= 0 || halfLat <= 0) return false;
  const have = roomFor(aspects, room, halfLon / halfLat);
  return have > 0 && halfLat <= have;
}
