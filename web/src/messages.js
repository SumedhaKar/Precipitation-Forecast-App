// What the page says when something it does not control fails. SPEC 11.29.
//
// Three things can fail without the forecast being wrong: the browser can
// refuse a location, the graphics card can refuse a map, and the map's own
// chunk can fail to arrive. Each of those used to be either silent or a
// console message, which leaves a reader looking at an empty rectangle with
// nothing to do.
//
// Every message here is one line, says what happened, and says what still
// works — because in all three cases everything except the drawing still
// works: the search box, the panel, the five days and all 51 values come from
// api/place and never touch the map (SPEC 11.22).
//
// No imports, so `node` can load this file and a test can read every string
// (SPEC 11.24).

/** The browser has no geolocation at all, or the page is not on https. */
export const NO_LOCATION = 'This browser will not give a location here. '
  + 'Search for a city, or type a latitude and longitude.';

/**
 * One line for a GeolocationPositionError code.
 *
 * The three codes are the standard's own: 1 permission denied, 2 position
 * unavailable, 3 timed out. The browser's `message` is not shown, because it
 * is written for a developer and differs between browsers.
 */
export function locationProblem(code) {
  if (code === 1) {
    return 'Location permission was not given, which is fine: search for a '
      + 'city instead.';
  }
  if (code === 2) {
    return 'This device could not work out where it is. Search for a city, '
      + 'or type a latitude and longitude.';
  }
  if (code === 3) {
    return 'Finding your location took too long, so it was given up on. '
      + 'Search for a city instead.';
  }
  return NO_LOCATION;
}

/**
 * A tap that landed on nothing this site forecasts. SPEC 11.38.
 *
 * It used to be a red error box reading "That is outside the forecast area,
 * which covers 6 to 38 degrees north and 68 to 98 degrees east" -- a
 * refusal, in the colour of a fault, written in the coordinates of a box
 * nobody can see, for a reader whose finger slipped onto the sea or onto
 * Nepal. Nothing went wrong. It is a plain line and it says what to do.
 */
export const OUTSIDE = "That's outside India. Tap the map over India or "
  + 'find a city.';

/** The forecast's own box, where a reader asked what the limits are. */
export const THE_BOX = 'The forecast covers 6 to 38 degrees north and 68 to '
  + '98 degrees east, and only the squares inside India.';

/**
 * One line for the map failing to start, by cause.
 *
 * `webgl2` is a browser or a machine that cannot draw it, `maplibre` is the
 * library refusing to start, and `chunk` is the 325 KB of map code not
 * arriving. A reader cannot act on which, so each one says the same two
 * things: the map is not drawn, and the numbers are still here.
 */
export function mapProblem(cause) {
  const why = {
    webgl2: 'This browser cannot draw the map: it has no WebGL 2.',
    maplibre: 'The map could not be started on this browser.',
    chunk: 'The map\'s code did not finish loading.',
  }[cause] || 'The map could not be drawn.';
  return `${why} Everything the map shows is also in words and numbers: `
    + 'search for a city below, or type a latitude and longitude.';
}
