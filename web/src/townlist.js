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
/**
 * How many single-letter edits apart two words are, up to a limit.
 *
 * Plain Levenshtein — insert, delete, substitute — over two rows rather than
 * a whole matrix. `limit` is not an optimisation: a word is only offered as a
 * near miss when it is within a couple of edits, so anything further away can
 * stop early and report the limit.
 */
export function editDistance(a, b, limit = 3) {
  const from = String(a || '');
  const to = String(b || '');
  if (Math.abs(from.length - to.length) > limit) return limit + 1;
  let previous = Array.from({ length: to.length + 1 }, (_, n) => n);
  for (let i = 1; i <= from.length; i += 1) {
    const row = [i];
    let best = i;
    for (let j = 1; j <= to.length; j += 1) {
      const cost = from[i - 1] === to[j - 1] ? 0 : 1;
      row[j] = Math.min(previous[j] + 1, row[j - 1] + 1,
        previous[j - 1] + cost);
      if (row[j] < best) best = row[j];
    }
    if (best > limit) return limit + 1;
    previous = row;
  }
  return previous[to.length];
}

/**
 * The nearest town names to something that matched nothing. SPEC 11.29.
 *
 * Offered as buttons, never chosen: a misspelling is answered with "did you
 * mean" and the reader decides. Picking the nearest name automatically would
 * mean showing one place's numbers under another place's name, which is the
 * one thing a forecast page must not do.
 *
 * How near counts as near grows with the length of what was typed — one edit
 * for a short word, three for a long one — so "goa" cannot drag in "goal"'s
 * worth of neighbours while "tiruvanantapuram" still reaches
 * "Thiruvananthapuram".
 */
export function nearTowns(towns, text, most = 3) {
  const wanted = String(text || '').trim().toLowerCase();
  if (wanted.length < 3) return [];
  const limit = Math.min(3, 1 + Math.floor(wanted.length / 5));
  const near = [];
  for (const town of towns) {
    const away = editDistance(wanted, town.name.toLowerCase(), limit);
    if (away <= limit) near.push({ town, away });
  }
  near.sort((a, b) => a.away - b.away || a.town.name.localeCompare(b.town.name));
  return near.slice(0, most).map((found) => found.town);
}

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
