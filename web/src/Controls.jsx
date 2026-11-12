// Day, threshold, search and "use my location". SPEC 11.19 and 11.28.
//
// Every control is a real button or input in a labelled group, because the
// map is a canvas and cannot be the only way to reach a square (SPEC 11.22).

import { useState } from 'react';
import { parseLatLon, squareText } from './snap';
import { findTowns, townLabel } from './places';

const THRESHOLDS = [1, 10, 50];

export function DayChoice({ days, day, onDay }) {
  const chosen = days.find((entry) => entry.lead_day === day) || days[0];
  return (
    <div className="group">
      <span className="grouplabel" id="daylabel">Day</span>
      <div className="radios" role="radiogroup" aria-labelledby="daylabel">
        {days.map((entry) => (
          <button
            key={entry.lead_day}
            type="button"
            role="radio"
            aria-checked={entry.lead_day === day}
            className={entry.lead_day === day ? 'on' : ''}
            onClick={() => onDay(entry.lead_day)}
          >
            {entry.short_ist || `Day ${entry.lead_day}`}
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
export function Search({ onTown, onPoint, busy, shown }) {
  const [text, setText] = useState(null); // null means "not typing"
  const [said, setSaid] = useState(null);

  const typing = text !== null;
  const value = typing ? text : (shown || '');
  const matches = typing ? findTowns(text) : [];
  const typed = typing ? parseLatLon(text) : null;

  function done() {
    setText(null);
    setSaid(null);
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
    setSaid(asked
      ? `No town in the list starts with "${asked}". The list is the 215 `
        + 'Natural Earth towns in India; a latitude and longitude works too, '
        + 'as 28.5, 77.25.'
      : null);
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      <label htmlFor="place">A town, or a latitude and longitude</label>
      <div className="searchrow">
        <input
          id="place"
          type="text"
          autoComplete="off"
          placeholder="Search a town, or type lat, lon"
          value={value}
          onFocus={() => { if (!typing) setText(''); }}
          onChange={(event) => { setText(event.target.value); setSaid(null); }}
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
export function MyLocation({ onLocation, snapTo }) {
  const [said, setSaid] = useState(null);
  const [asking, setAsking] = useState(false);

  function ask() {
    if (!navigator.geolocation) {
      setSaid('This browser cannot give a location.');
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
          setSaid('That is outside the forecast area, which covers 6 to 38 '
            + 'degrees north and 68 to 98 degrees east.');
          return;
        }
        setSaid(`Your location: square ${squareText(here.lat, here.lon)}. `
          + 'Your exact position was not sent anywhere.');
        onLocation(here.lat, here.lon);
      },
      (error) => {
        setAsking(false);
        setSaid(error.code === error.PERMISSION_DENIED
          ? 'Location permission was not given, which is fine: search for a '
            + 'town instead.'
          : `Your location could not be read: ${error.message}`);
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
