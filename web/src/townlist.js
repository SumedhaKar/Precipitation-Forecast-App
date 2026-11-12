// What the page asks the town list. SPEC 11.28.
//
// Pure functions over a list handed in, with no imports at all, so `node` can
// load this file and a test can drive every one of them against the real
// web/src/towns.json (SPEC 11.24). web/src/places.js is the one line of glue
// that binds them to that file for the components.

/** A town's name, with the state only where two towns share the name. */
export function townLabel(town) {
  if (!town) return null;
  return town.state ? `${town.name}, ${town.state}` : town.name;
}

/**
 * Every town whose square is exactly this square.
 *
 * Four squares hold two towns each — Bhiwandi with Kalyan, Dispur with
 * Guwahati, Faridabad with New Delhi, and Haora with Kolkata — so this
 * returns a list and the page names both. Claiming one of a pair would be
 * saying something the grid does not know: at 0.25 degrees they are the same
 * 28 km square and get the same numbers.
 */
export function townsAt(towns, lat, lon) {
  return towns.filter(
    (town) => !town.not_forecast
      && Math.abs(town.lat - lat) < 1e-9 && Math.abs(town.lon - lon) < 1e-9);
}

/** "Faridabad and New Delhi", or null where no town is in the square. */
export function nameOfSquare(towns, lat, lon) {
  const here = townsAt(towns, lat, lon).map((town) => town.name);
  if (!here.length) return null;
  if (here.length === 1) return here[0];
  return `${here.slice(0, -1).join(', ')} and ${here[here.length - 1]}`;
}

/**
 * Towns matching what has been typed: the ones that start with it first.
 *
 * Nothing here guesses or corrects spelling. A town that starts with the
 * typed letters is offered before one that merely contains them, and an
 * unmatched word is reported as unmatched rather than resolved to something
 * near it. An empty box matches nothing, which is what keeps the page from
 * saying "no town starts with """ before anything has been typed.
 */
export function findTowns(towns, text, most = 8) {
  const wanted = String(text || '').trim().toLowerCase();
  if (!wanted) return [];
  const starts = [];
  const holds = [];
  for (const town of towns) {
    const name = town.name.toLowerCase();
    if (name.startsWith(wanted)) starts.push(town);
    else if (name.includes(wanted)) holds.push(town);
  }
  return [...starts, ...holds].slice(0, most);
}
