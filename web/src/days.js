// What to call a day. SPEC 11.38.
//
// The five buttons read "Sat 14", "Sun 15" and so on, which is right and is
// not what a reader asks. The first of the five is usually today and the
// second usually tomorrow, and "usually" is the whole problem: the run is
// the 00 UTC run, lead day 1 is 5:30 am today to 5:30 am tomorrow IST, and
// a reader opening the page at 4 am IST is inside the previous day's lead
// day 1. Naming the buttons by their lead day would print "Tomorrow" over
// today's forecast for an hour and a half every morning.
//
// So the names come from the dates themselves: the day's own IST date,
// compared with the reader's own IST date. Nothing here is a lead day.
//
// IST is UTC+05:30 the whole year round and has no daylight saving, so the
// arithmetic is a fixed offset and no timezone database is needed -- the
// same reason api/health formats its labels itself (SPEC 11.12).
//
// No imports, so `node` can load this file and a test can drive every one of
// these against the dates a reader can actually have (SPEC 11.24).

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

/** The reader's own date in IST, as "2026-11-14". */
export function istToday(now = Date.now()) {
  return new Date(now + IST_OFFSET_MS).toISOString().slice(0, 10);
}

/** The date after this one. "2026-12-31" -> "2027-01-01". */
export function dayAfter(ymd) {
  const at = Date.parse(`${ymd}T00:00:00Z`);
  if (Number.isNaN(at)) return null;
  return new Date(at + DAY_MS).toISOString().slice(0, 10);
}

/**
 * What to call one of the five days: "Today", "Tomorrow", or its date.
 *
 * `fromIst` is the day's own start in IST, as api/health publishes it;
 * `todayYmd` is the reader's own IST date; `shortIst` is the published
 * "Sat 14 Nov" that is used wherever neither word applies. Nothing is
 * invented: with no usable date the published label is what is shown.
 */
export function dayName(fromIst, todayYmd, shortIst = null) {
  const ymd = String(fromIst || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(ymd)) return shortIst;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(todayYmd || ''))) return shortIst;
  if (ymd === todayYmd) return 'Today';
  if (ymd === dayAfter(todayYmd)) return 'Tomorrow';
  return shortIst;
}

/**
 * The first line of a two-line pill: "Today", "Tomorrow" or "Sat".
 *
 * SPEC 11.39. The pills carry the name above and the date below, so the
 * weekday is wanted on its own: "Sat 15" put two facts on one line and the
 * date was the one that got cut.
 */
export function dayWord(fromIst, todayYmd, shortIst = null) {
  const name = dayName(fromIst, todayYmd, shortIst);
  if (name === 'Today' || name === 'Tomorrow') return name;
  const words = String(name || '').trim().split(/\s+/);
  return words[0] || null;
}

/**
 * The second line of a two-line pill: "15 Nov", from "Sat 15 Nov".
 *
 * SPEC 11.39. The published `short_ist` is the only date on the page, and
 * the weekday is taken off the front of it rather than formatted again
 * here: a second date formatter is a second chance to disagree with the
 * run about which day this is.
 */
export function dayDate(shortIst) {
  const words = String(shortIst || '').trim().split(/\s+/);
  if (!words[0]) return null;
  if (words.length < 2) return words[0];
  return /^\d/.test(words[0]) ? words.join(' ') : words.slice(1).join(' ');
}

/**
 * The same name, short enough for one of five buttons on a 390 pixel phone.
 *
 * "Today" and "Tomorrow" are already short. A date is cut to its weekday
 * and its number -- "Sat 14 Nov" becomes "Sat 14" -- because five buttons
 * reading "Sat 14 Nov" come to 418 pixels and the row would scroll sideways
 * with days 4 and 5 off the edge (SPEC 11.29). Within five consecutive days
 * the dates cannot be confused: "Sat 31" then "Sun 1" is as clear as the
 * line underneath.
 */
export function dayButton(fromIst, todayYmd, shortIst = null) {
  const name = dayName(fromIst, todayYmd, shortIst);
  if (name === 'Today' || name === 'Tomorrow') return name;
  const words = String(name || '').trim().split(/\s+/);
  if (words.length < 2) return name;
  return `${words[0]} ${words[1]}`;
}
