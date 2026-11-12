// Which answer the page is allowed to show. SPEC 11.30.
//
// The fault this is for, reproduced on the built page before it was fixed:
// "use my location" put the ring and the search box on 22.75 N 88.25 E, and
// the panel went on showing 34.50 N 74.25 E with 51 of 51 model runs at
// 1 mm. Two requests were in the air, the older one answered last, and
// whichever answered last won. A reader was looking at one square's name
// over another square's numbers, which is the single worst thing this site
// can do.
//
// So an answer is shown only when both of these hold:
//
//   it is the answer to the most recent request, by ticket, and
//   it is about the square that is chosen now.
//
// The second is not redundant. The ticket catches two requests crossing;
// the square catches everything else — a retry, a request made before the
// reader moved on, a square chosen while nothing was in flight at all.
//
// No imports, so `node` can load this file and a test can drive it against
// the orders the page can actually get them in (SPEC 11.24).

/** Are these the same 0.25 degree square? */
export function sameSquare(one, two) {
  if (!one || !two) return false;
  if (!Number.isFinite(one.lat) || !Number.isFinite(one.lon)) return false;
  if (!Number.isFinite(two.lat) || !Number.isFinite(two.lon)) return false;
  // A square centre is a multiple of 0.25, so this compares exactly; the
  // tolerance is for the last bit of a float, not for nearness.
  return Math.abs(one.lat - two.lat) < 1e-9
    && Math.abs(one.lon - two.lon) < 1e-9;
}

/**
 * May this answer be shown?
 *
 * `ticket` is the number this request was given when it was sent, `latest`
 * the number of the most recent request sent since. `asked` is the square
 * the page is showing now, and `answered` the square the answer says it was
 * asked about — `square.asked` from api/place, which is what was sent,
 * rather than `square`, which may be one step away when the asked-for square
 * is sea (SPEC 11.7).
 */
export function keepAnswer(ticket, latest, asked, answered) {
  if (!Number.isInteger(ticket) || !Number.isInteger(latest)) return false;
  if (ticket !== latest) return false;
  return sameSquare(asked, answered);
}
