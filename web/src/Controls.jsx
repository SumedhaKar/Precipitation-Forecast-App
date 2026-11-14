// Day, threshold, search and "use my location". SPEC 11.19 and 11.28.
//
// Every control is a real button or input in a labelled group, because the
// map is a canvas and cannot be the only way to reach a square (SPEC 11.22).

import { useEffect, useRef, useState } from 'react';
import { parseLatLon, squareText } from './snap';
import {
  findTowns, findUnit, namesOf, nearTowns, noMatch, tooBig, townLabel,
  townsIn,
} from './places';
import { NO_LOCATION, OUTSIDE, locationProblem } from './messages';
import { colourOf, pillNote, pillSentence } from './palette';
import { Pin } from './Icons';
import {
  dayAndDate, dayDate, dayWord, istToday, startsTomorrow,
} from './days';

const THRESHOLDS = [1, 10, 50];

/**
 * Said beside "Which day?" on the mornings when today is not day one.
 *
 * SPEC 11.40, reworded by 11.41. One string, because the How to read this
 * map page explains the same line and quotes it: two copies of a sentence
 * are two sentences to keep in step.
 *
 * It used to say "the forecast arrives around midday", which answers a
 * question a reader has not asked yet -- they want to know why today is
 * missing, not what time a file lands. "Today is already under way" is
 * the reason: by the time the 00 UTC run has been downloaded, added up
 * and published, the day it would forecast has been going for hours.
 * What time that happens is on the How to read this map page, in the
 * fine print, where somebody who wants it will look for it.
 */
export const STARTS_TOMORROW = '(starts tomorrow, because today is '
  + 'already under way when the forecast arrives)';

/**
 * The day buttons. SPEC 11.38, 11.40.
 *
 * A control asks a question, so the label is one. The buttons are named
 * from the reader's own IST date rather than from a lead day, which is why
 * `days.js` exists: lead day 1 runs 5:30 am to 5:30 am, so naming it
 * "Tomorrow" would be wrong for the hour and a half before 5:30 every
 * morning.
 *
 * SPEC 11.39: the line under them, which said where a day starts and ends,
 * is on the How to read this map page now.
 *
 * SPEC 11.40: once a place is chosen, each pill carries that place's own
 * count for the chosen amount as a third line -- a bare number with a
 * small square in the map's colour for it. There were two rows of days on
 * the page before that: these five pills, and the card's own five-day
 * strip saying the same five days with the same five counts, 400 pixels
 * further down. The forecast is five days long, so one row of five is the
 * whole of it.
 *
 * `counts` is the chosen place's five counts by lead day, or null where
 * nothing has been chosen -- and then the pills are the day and the date
 * and nothing else, because a count with no place is not a count.
 */
export function DayChoice({ days, day, onDay, today, counts, threshold,
  members }) {
  const now = today || istToday();
  const of = (entry) => (counts && Number.isInteger(counts[entry.lead_day])
    ? counts[entry.lead_day] : null);
  return (
    <div className="group days">
      {/* SPEC 11.40. The question, and on the mornings when the five days
          do not include today, why. Five date pills cannot say it: a
          reader who opens the page at 9 am and is given Sun to Thu has no
          way of knowing whether Saturday is missing or wrong. It is drawn
          only when the first pill really does read "Tomorrow". */}
      <span className="labelrow">
        <span className="grouplabel" id="daylabel">Which day?</span>
        {startsTomorrow(days, now) ? (
          <span className="startsnote">{STARTS_TOMORROW}</span>
        ) : null}
      </span>
      <div className="radios" role="radiogroup" aria-labelledby="daylabel">
        {days.map((entry) => (
          <button
            key={entry.lead_day}
            type="button"
            role="radio"
            aria-checked={entry.lead_day === day}
            className={entry.lead_day === day ? 'on' : ''}
            aria-label={pillSentence(
              dayAndDate(entry.from_ist, now, entry.short_ist),
              of(entry), threshold, members)
              + (entry.label ? `. ${entry.label} IST` : '')}
            onClick={() => onDay(entry.lead_day)}
          >
            {/* SPEC 11.39. Two lines: the name over the date. "Sat 15"
                put two facts on one line and the date was the one that
                got cut; "Today" with no date under it left a reader
                counting days on their fingers.

                SPEC 11.40 adds the third line once there is a place to
                count for: the number, and a square in the map's own
                colour for that number. The square has a white hairline
                round it so that it is still a square on the navy of the
                chosen pill; the pill's own fill goes on meaning nothing
                but "chosen". */}
            <span className="pilltop">
              {dayWord(entry.from_ist, now, entry.short_ist)}
            </span>
            <span className="pillunder">{dayDate(entry.short_ist)}</span>
            {of(entry) === null ? null : (
              <span className="pillcount">
                <span
                  className="daysq"
                  aria-hidden="true"
                  style={{ background: colourOf(of(entry)) }}
                />
                {of(entry)}
              </span>
            )}
          </button>
        ))}
      </div>
      {/* SPEC 11.39. The line that said where a day starts and ends is on
          the How to read this map page, with every other help sentence this
          page used to carry.

          SPEC 11.40. What is here instead is the one caption the numbers
          on the pills need, and only once there are numbers: five bare
          numbers with no sentence are five numbers a reader has to guess
          the meaning of. Each pill says the same sentence in full to a
          screen reader. */}
      {counts ? (
        <p className="pillnote">{pillNote(threshold, members)}</p>
      ) : null}
    </div>
  );
}

/**
 * The three amounts, with this site's own nicknames. SPEC 11.38.
 *
 * The nicknames are written down in the specification and are nobody
 * else's categories -- in particular they are not IMD's, whose "heavy
 * rain" names a band this site does not measure. Two of them had to give
 * way to the forbidden-word list of 11.20: "a wet day" and "very heavy"
 * are the natural English and both words are banned, so the buttons read
 * "A rainy day" and "A lot of rain".
 *
 * The millimetres are on the button beside the nickname, always, so the
 * nickname is never the only thing a reader is given.
 */
export const AMOUNTS = [
  { mm: 1, nickname: 'Some rain' },
  { mm: 10, nickname: 'A rainy day' },
  { mm: 50, nickname: 'A lot of rain' },
];

/**
 * This site's own words for the three amounts. SPEC 11.39, moved by 11.40.
 *
 * Everyday English, written down here and in the specification and nowhere
 * else. They are nobody's official categories -- in particular not IMD's,
 * whose "heavy rain" names a band this site does not measure -- and the
 * millimetres are beside every one of them, always.
 *
 * The first of them was "enough to wet the ground" in the brief and could
 * not be: "wet" is on the forbidden list of 11.20, which is there because
 * "a wet day" is a forecast of what the day will be like and this site
 * does not make one. "Damp" says the same thing about the ground and
 * claims nothing about the day.
 *
 * They were on the How to read this map page and are here now, beside the
 * nicknames they explain, because the answer opens under the pills as well
 * as appearing on that page and the two may not drift apart.
 */
export const AMOUNT_WORDS = {
  1: 'enough to leave the ground damp.',
  10: 'a proper shower; you would want an umbrella.',
  50: 'a very rainy day; water can collect on roads.',
};

/** The one thing true of all three: what is added up, and over what. */
export const WHOLE_DAY = 'Each is the total over the whole day, averaged '
  + 'over the square.';

/**
 * The four lines that answer "What does mm mean?". SPEC 11.40.
 *
 * One component, drawn under the amount pills and on the How to read this
 * map page, so a reader who opens it under the pills and a reader who
 * reads the page are given the same words.
 */
export function AmountWords() {
  return (
    <ul className="amountwords">
      {AMOUNTS.map((amount) => (
        <li key={amount.mm}>
          <strong>
            {amount.nickname} ({amount.mm} mm+):
          </strong>{' '}
          <span className="meaning">{AMOUNT_WORDS[amount.mm]}</span>
        </li>
      ))}
      <li className="wholeday">{WHOLE_DAY}</li>
    </ul>
  );
}

export function ThresholdChoice({ threshold, onThreshold }) {
  return (
    <div className="group amounts">
      <span className="grouplabel" id="amountlabel">How much rain?</span>
      <div className="amountline">
        <div className="radios" role="radiogroup"
          aria-labelledby="amountlabel"
        >
          {AMOUNTS.map((amount) => (
            <button
              key={amount.mm}
              type="button"
              role="radio"
              aria-checked={amount.mm === threshold}
              className={amount.mm === threshold ? 'on' : ''}
              aria-label={`${amount.nickname}, ${amount.mm} mm or more`}
              onClick={() => onThreshold(amount.mm)}
            >
              <span className="pilltop">{amount.nickname}</span>
              <span className="pillunder">{amount.mm} mm+</span>
            </button>
          ))}
        </div>
      {/* SPEC 11.40. The question is answered where it is asked.

          It was a link to the How to read this map page, which took a
          reader off the forecast to read three lines and left them to
          find their way back -- and on a phone the page it landed on
          opens with the map, so the answer was below the fold of a page
          the reader had not asked for.

          A real <details>: it opens under the pills, it shuts on a second
          tap, nothing navigates, and the page it used to point at keeps
          the same four lines in the same words. The lines are in the page
          either way, so the forbidden-word sweep reads them whether or
          not a reader has opened them.

          On its own line under the pills, at the end of it, with no rule
          above it and no icon beside it: the three pills keep the whole
          width between them. */}
        <details className="mmwhat">
          <summary>What does mm mean?</summary>
          <AmountWords />
        </details>
      </div>
    </div>
  );
}

/**
 * One box for both a town name and a typed latitude and longitude.
 *
 * Two numbers are a place; anything else is treated as a name and matched
 * against the 215 towns of SPEC 11.28. Nothing here guesses: an unmatched
 * name says so, and says so only once something has actually been typed.
 *
 * SPEC 11.28: after any pick — a town, typed coordinates, a click on the map
 * or "use my location" — the box shows what is being shown, so the question
 * and the answer never disagree. `shown` is that text and the box falls back
 * to it whenever the reader is not in the middle of typing.
 */
export function Search({
  onTown, onPoint, onUnit, busy, shown, onLocation, snapTo, from,
}) {
  const [text, setText] = useState(null); // null means "not typing"
  const [said, setSaid] = useState(null);
  const [near, setNear] = useState([]);
  const box = useRef(null);

  // SPEC 11.39. Nothing asks this box for the keyboard any more: the two
  // buttons that did -- "Find my city" and the bar's "Search" -- are gone,
  // and a reader puts the keyboard where they want it.

  const typing = text !== null;
  const value = typing ? text : (shown || '');
  const matches = typing ? findTowns(text) : [];
  const typed = typing ? parseLatLon(text) : null;

  /* SPEC 11.38. A state or union territory, and the city wins where a name
     is both -- Delhi, Chandigarh, Puducherry and Goa are all four. A state
     is never answered with a count: rain over Rajasthan on one day is not
     one number, and an average nobody asked for is not an answer. */
  const named = typing && !typed
    ? String(text).trim().toLowerCase() : null;
  // Alias-aware: "Pondicherry" is the city Puducherry's older name as well
  // as the union territory's, and the city wins there too.
  const asCity = named
    && matches.some((town) => namesOf(town)
      .some((name) => name.toLowerCase() === named));
  const unit = named && !asCity ? findUnit(text) : null;
  const inside = unit ? townsIn(unit.name) : [];

  // The map goes to the state as soon as its name is recognised. It is the
  // only thing this box does to the map, and it draws no square and no
  // count: what the reader is given is the outline and a list of cities.
  useEffect(() => {
    if (unit && onUnit) onUnit(unit);
  }, [unit && unit.name]); // eslint-disable-line react-hooks/exhaustive-deps

  function done() {
    setText(null);
    setSaid(null);
    setNear([]);
  }

  function choose(town) {
    done();
    onTown(town);
  }

  function submit(event) {
    event.preventDefault();
    if (!typing) return;
    if (typed) {
      done();
      onPoint(typed.lat, typed.lon);
      return;
    }
    if (matches.length) {
      choose(matches[0]);
      return;
    }
    // Only ever after typing: an empty box has nothing to be sorry about.
    const asked = text.trim();
    if (!asked) {
      setSaid(null);
      setNear([]);
      return;
    }
    // A state is not a miss: it has its own block under the box.
    if (findUnit(asked)) return;
    // SPEC 11.29. A misspelling is answered with the nearest few names as
    // buttons, and never by choosing one: showing one place's numbers under
    // another place's name is the single worst thing this page could do.
    // Natural Earth's spellings are its own, too — Simla, Dehra Dun — and
    // SPEC 11.38 added the older names as search keys, so a reader who
    // types the name they know is usually answered before this line.
    const close = nearTowns(asked);
    setNear(close);
    setSaid(noMatch(asked));
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      {/* SPEC 11.39. The label is for a screen reader only: the box says
          what it is for in its own placeholder, and a label over a box
          that already says it was one more line of grey text above the
          map. It is not removed, because a placeholder is not a label --
          it goes the moment anybody types. */}
      <label htmlFor="place" className="offscreen">
        Search a city or state, or type a latitude and longitude
      </label>
      <div className="searchrow">
        <input
          id="place"
          ref={box}
          type="text"
          autoComplete="off"
          placeholder="Search a city or state"
          value={value}
          onFocus={() => { if (!typing) setText(''); }}
          onChange={(event) => {
            setText(event.target.value);
            setSaid(null);
            setNear([]);
          }}
        />
        {/* SPEC 11.39. At the right end of the box, because it answers the
            same question the box does. The icon is a picture of a pin and
            the button's name is words: "Use my location". */}
        <MyLocation onLocation={onLocation} snapTo={snapTo} from={from} />
      </div>
      {/* SPEC 11.39. The other way in, said once, under the box. */}
      <p className="ortap">or tap the map</p>
      {/* SPEC 11.38. A whole state, which is never one forecast. */}
      {unit ? (
        <div className="unitfound">
          <p>{tooBig(unit.name)}</p>
          <ul className="matches">
            {inside.map((town) => (
              <li key={`${town.name}/${town.lat}/${town.lon}`}>
                <button type="button" onClick={() => choose(town)}>
                  {townLabel(town)}
                  <span className="small">
                    {town.not_forecast
                      ? 'not forecast'
                      : squareText(town.lat, town.lon)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {matches.length && !typed ? (
        <ul className="matches">
          {matches.map((town) => (
            <li key={`${town.name}/${town.lat}/${town.lon}`}>
              <button type="button" onClick={() => choose(town)}>
                {townLabel(town)}
                <span className="small">
                  {town.not_forecast
                    ? 'not forecast'
                    : squareText(town.lat, town.lon)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {said ? <p className="note">{said}</p> : null}
      {near.length ? (
        <div className="didyoumean">
          <span className="small">Did you mean</span>
          <ul>
            {near.map((town) => (
              <li key={`${town.name}/${town.lat}/${town.lon}`}>
                <button type="button" onClick={() => choose(town)}>
                  {townLabel(town)}?
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  );
}

/**
 * The browser's own location, snapped before it is sent.
 *
 * SPEC 11.19: the fix is rounded to its 0.25 degree square here, in the page,
 * and only the square's centre goes to /api/place, so a position never
 * reaches a request URL or a server log. api/place would snap it to the same
 * square anyway, and a test drives both to prove they agree.
 *
 * SPEC 11.28: what the reader is told is the square, never the fix. There is
 * no reverse geocoding and no third-party service of any kind here — the only
 * way a name appears is when the square is exactly some town's own square,
 * which the page looks up in its own list.
 */
export function MyLocation({ onLocation, snapTo, from }) {
  const [said, setSaid] = useState(null);
  const [asking, setAsking] = useState(false);

  // SPEC 11.29. Whatever this control had to say is about the last time it
  // was asked, so it goes when the reader chooses a place some other way.
  // Searching for Kavaratti used to leave "Your location: square 28.50 N
  // 77.25 E" sitting under the search box next to Kavaratti's answer.
  useEffect(() => {
    if (from !== 'location') setSaid(null);
  }, [from]);

  function ask() {
    if (!navigator.geolocation) {
      setSaid(NO_LOCATION);
      return;
    }
    setAsking(true);
    setSaid(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setAsking(false);
        const here = snapTo(position.coords.latitude,
          position.coords.longitude);
        if (!here) {
          setSaid(OUTSIDE);
          return;
        }
        // Nothing is said here on success: the panel says it, once
        // (SPEC 11.29). This control only ever reports what went wrong.
        onLocation(here.lat, here.lon);
      },
      // SPEC 11.29. All three of the standard's failures get a line of their
      // own, from messages.js: permission refused, position unavailable, and
      // timed out. The browser's own `message` is never shown; it is written
      // for a developer and differs between browsers.
      (error) => {
        setAsking(false);
        setSaid(locationProblem(error && error.code));
      },
      { timeout: 10_000, maximumAge: 600_000 },
    );
  }

  // SPEC 11.39. The button and its message are siblings inside the search
  // row rather than a box of their own: the button is at the right end of
  // the search box, and anything it has to say wraps onto the line under
  // the two of them.
  return (
    <>
      <button
        type="button"
        className="locate"
        onClick={ask}
        disabled={asking}
        title="Use my location"
        aria-label={asking ? 'Finding your location' : 'Use my location'}
      >
        <Pin />
      </button>
      {said ? <p className="note locatenote">{said}</p> : null}
    </>
  );
}
