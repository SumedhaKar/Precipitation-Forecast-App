// Day, threshold, search and "use my location". SPEC 11.19.
//
// Every control is a real button or input in a labelled group, because the
// map is a canvas and cannot be the only way to reach a square (SPEC 11.22).

import { useState } from 'react';
import { parseLatLon, squareText } from './snap';
import cityList from './cities.json';

const CITIES = cityList.cities;
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
      <p className="window">{chosen ? chosen.label : null}</p>
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
 * One box for both a city name and a typed latitude and longitude.
 *
 * Two numbers are a place; anything else is treated as a name and matched
 * against the twenty cities. Nothing here guesses: an unmatched name says so.
 */
export function Search({ onPick, busy }) {
  const [text, setText] = useState('');
  const [said, setSaid] = useState(null);

  const matches = text.trim().length
    ? CITIES.filter((city) => city.name.toLowerCase()
      .startsWith(text.trim().toLowerCase()))
    : [];

  function choose(city) {
    setText('');
    setSaid(null);
    onPick(city.lat, city.lon);
  }

  function submit(event) {
    event.preventDefault();
    const typed = parseLatLon(text);
    if (typed) {
      setSaid(null);
      setText('');
      onPick(typed.lat, typed.lon);
      return;
    }
    if (matches.length) {
      choose(matches[0]);
      return;
    }
    setSaid(`No city in the list starts with "${text.trim()}". `
      + 'A latitude and longitude works too, as 28.5, 77.25.');
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      <label htmlFor="place">A city, or a latitude and longitude</label>
      <div className="searchrow">
        <input
          id="place"
          type="text"
          autoComplete="off"
          placeholder="Delhi, or 28.5, 77.25"
          value={text}
          onChange={(event) => { setText(event.target.value); setSaid(null); }}
        />
        <button type="submit" disabled={busy}>Show</button>
      </div>
      {matches.length && text.trim() && !parseLatLon(text) ? (
        <ul className="matches">
          {matches.slice(0, 6).map((city) => (
            <li key={city.name}>
              <button type="button" onClick={() => choose(city)}>
                {city.name}
                <span className="small">
                  {squareText(city.lat, city.lon)}
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
 */
export function MyLocation({ onPick, snapTo }) {
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
        setSaid(`Showing ${squareText(here.lat, here.lon)}, the square you `
          + 'are in. Your exact position was not sent anywhere.');
        onPick(here.lat, here.lon);
      },
      (error) => {
        setAsking(false);
        setSaid(error.code === error.PERMISSION_DENIED
          ? 'Location permission was not given, which is fine: search for a '
            + 'city instead.'
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
