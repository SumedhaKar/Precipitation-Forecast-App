// Day, threshold, search and "use my location". SPEC 11.19 and 11.28.
//
// Every control is a real button or input in a labelled group, because the
// map is a canvas and cannot be the only way to reach a square (SPEC 11.22).

import { useEffect, useRef, useState } from 'react';
import { parseLatLon, squareText } from './snap';
import { findTowns, nearTowns, townLabel } from './places';
import { NO_LOCATION, OUTSIDE, locationProblem } from './messages';

const THRESHOLDS = [1, 10, 50];

/**
 * "Fri 13 Nov" -> "Fri 13". SPEC 11.29.
 *
 * The month is dropped from the buttons, and from them only. Five buttons
 * reading "Fri 13 Nov" are 418 pixels wide on a 390 pixel phone, so the row
 * scrolled sideways and the last two days were off the edge of a screen with
 * no hint that they were there. The full window, with the month and the
 * times and IST on it, is the line underneath, and api/place repeats it for
 * the chosen day in the panel, so nothing is only in the short form.
 *
 * Five days never span two months in a way this could confuse: within a
 * five-day run the dates are consecutive, so "Sat 31" then "Sun 1" is as
 * clear as the date line below it.
 */
export function dayTab(short, lead) {
  const words = String(short || '').trim().split(/\s+/);
  if (words.length < 2) return short || `Day ${lead}`;
  return `${words[0]} ${words[1]}`;
}

export function DayChoice({ days, day, onDay }) {
  const chosen = days.find((entry) => entry.lead_day === day) || days[0];
  return (
    <div className="group days">
      <span className="grouplabel" id="daylabel">Day</span>
      <div className="radios" role="radiogroup" aria-labelledby="daylabel">
        {days.map((entry) => (
          <button
            key={entry.lead_day}
            type="button"
            role="radio"
            aria-checked={entry.lead_day === day}
            className={entry.lead_day === day ? 'on' : ''}
            aria-label={entry.label ? `${entry.label} IST` : undefined}
            onClick={() => onDay(entry.lead_day)}
          >
            {dayTab(entry.short_ist, entry.lead_day)}
          </button>
        ))}
      </div>
      {/* SPEC 11.28: every clock time on this page carries IST. The label
          itself comes from the manifest and holds no timezone, so the page
          adds it rather than reformatting a published string. */}
      <p className="window">{chosen ? `${chosen.label} IST` : null}</p>
    </div>
  );
}

export function ThresholdChoice({ threshold, onThreshold }) {
  return (
    <div className="group">
      <span className="grouplabel" id="amountlabel">
        At least this much rain in the day
      </span>
      <div className="radios" role="radiogroup" aria-labelledby="amountlabel">
        {THRESHOLDS.map((amount) => (
          <button
            key={amount}
            type="button"
            role="radio"
            aria-checked={amount === threshold}
            className={amount === threshold ? 'on' : ''}
            onClick={() => onThreshold(amount)}
          >
            {amount} mm
          </button>
        ))}
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
export function Search({ onTown, onPoint, busy, shown, askFocus }) {
  const [text, setText] = useState(null); // null means "not typing"
  const [said, setSaid] = useState(null);
  const [near, setNear] = useState([]);
  const box = useRef(null);

  // SPEC 11.37. The bottom bar's "Search" button opens the panel and asks
  // for the keyboard by counting up; nothing else focuses this box, so the
  // line beside it can open the panel without a keyboard appearing.
  useEffect(() => {
    if (askFocus) box.current?.focus();
  }, [askFocus]);

  const typing = text !== null;
  const value = typing ? text : (shown || '');
  const matches = typing ? findTowns(text) : [];
  const typed = typing ? parseLatLon(text) : null;

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
    // SPEC 11.29. A misspelling is answered with the nearest few names as
    // buttons, and never by choosing one: showing one place's numbers under
    // another place's name is the single worst thing this page could do.
    // Natural Earth's spellings are its own, too — Simla, Dehra Dun — so a
    // reader who types the name they know needs the offer, not a refusal.
    const close = nearTowns(asked);
    setNear(close);
    setSaid(`No town in the list starts with "${asked}". The list is the 215 `
      + 'Natural Earth towns in India; a latitude and longitude works too, '
      + 'as 28.5, 77.25.');
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      <label htmlFor="place">A town, or a latitude and longitude</label>
      <div className="searchrow">
        <input
          id="place"
          ref={box}
          type="text"
          autoComplete="off"
          placeholder="Search a town, or type lat, lon"
          value={value}
          onFocus={() => { if (!typing) setText(''); }}
          onChange={(event) => {
            setText(event.target.value);
            setSaid(null);
            setNear([]);
          }}
        />
        <button type="submit" disabled={busy}>Show</button>
      </div>
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

  return (
    <div className="mine">
      <button type="button" onClick={ask} disabled={asking}>
        {asking ? 'Asking…' : 'Use my location'}
      </button>
      {said ? <p className="note">{said}</p> : null}
    </div>
  );
}
