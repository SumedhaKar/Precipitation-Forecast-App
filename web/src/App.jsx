// The G2 page. SPEC 11.8.
//
// It reads /api/health and /api/place on its own origin and never the store
// (SPEC 11.4), so there is no store URL in this bundle and no CORS to depend
// on. Everything shown is a published number: the counts and the dots come
// from the tiles as they were published, and the member values are whole
// millimetres rounded down, which api/place computed from the published
// integers.
//
// No percentages. A percentage implies reliability, and that has to be
// earned by the record (SPEC 6), which does not exist yet.

import { useEffect, useState } from 'react';
import cityList from './cities.json';

const CITIES = cityList.cities;
const THRESHOLDS = [
  { key: 'ge1', label: '1 mm or more' },
  { key: 'ge10', label: '10 mm or more' },
  { key: 'ge50', label: '50 mm or more' },
];

// The parts below are exported so they can be rendered on their own,
// with a real /api/place answer, without a browser.
function degrees(value, positive, negative) {
  // Always two decimals: the grid is 0.25 degrees, so "73 E" and "73.00 E"
  // are the same square and one of them looks like a rounded-off guess.
  return `${Math.abs(value).toFixed(2)} ${value >= 0 ? positive : negative}`;
}

function square(lat, lon) {
  return `${degrees(lat, 'N', 'S')} ${degrees(lon, 'E', 'W')}`;
}

function istText(stamp) {
  // "2026-11-12T05:30:00+05:30" -> "12 Nov 2026, 5:30 am"
  if (!stamp) return null;
  const match = stamp.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return stamp;
  const [, year, month, day, hour, minute] = match;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const h = Number(hour);
  const suffix = h < 12 ? 'am' : 'pm';
  const twelve = h % 12 === 0 ? 12 : h % 12;
  return `${Number(day)} ${months[Number(month) - 1]} ${year}, `
    + `${twelve}:${minute} ${suffix}`;
}

function summarise(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    lowest: sorted[0],
    middle: sorted[Math.floor(sorted.length / 2)],
    highest: sorted[sorted.length - 1],
  };
}

export function StaleBanner({ run }) {
  if (!run || !run.stale) return null;
  return (
    <p className="stale">
      <strong>This forecast is {run.age_hours} hours old.</strong>{' '}
      A newer model run has not been published. Nothing on this page has been
      updated since {istText(run.run_time_ist)} IST.
    </p>
  );
}

export function RunLine({ run }) {
  if (!run) return null;
  return (
    <p className="run">
      Model run <strong>{istText(run.run_time_ist)} IST</strong> (00 UTC).
      {run.publish_time_ist
        ? ` Published ${istText(run.publish_time_ist)} IST.`
        : null}
      {run.age_hours === null || run.age_hours === undefined
        ? null
        : ` ${run.age_hours} hours ago.`}
      <span className="runid">Run {run.run_id}</span>
    </p>
  );
}

function Picker({ city, onCity, typed, onTyped, onSubmit, busy }) {
  return (
    <form
      className="picker"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="city">
        Place
        <select
          id="city"
          value={city}
          onChange={(event) => onCity(event.target.value)}
        >
          {CITIES.map((entry) => (
            <option key={entry.name} value={entry.name}>{entry.name}</option>
          ))}
          <option value="">a latitude and longitude</option>
        </select>
      </label>

      <label htmlFor="lat">
        Latitude N
        <input
          id="lat"
          inputMode="decimal"
          value={typed.lat}
          onChange={(event) => onTyped({ ...typed, lat: event.target.value })}
        />
      </label>

      <label htmlFor="lon">
        Longitude E
        <input
          id="lon"
          inputMode="decimal"
          value={typed.lon}
          onChange={(event) => onTyped({ ...typed, lon: event.target.value })}
        />
      </label>

      <button type="submit" disabled={busy}>
        {busy ? 'Reading...' : 'Show this square'}
      </button>
    </form>
  );
}

export function SquareLine({ place }) {
  const { square: where } = place;
  return (
    <p className="where">
      Showing <strong>{square(where.lat, where.lon)}</strong>, one 0.25 degree
      square, in tile {where.tile}.
      {where.moved ? (
        <span className="moved">
          {' '}{square(where.moved.from.lat, where.moved.from.lon)} is sea on
          this grid, so this is the nearest land square, one square away.
        </span>
      ) : null}
    </p>
  );
}

export function CountsTable({ place }) {
  return (
    <table className="counts">
      <caption>
        How many of the {place.members} model runs reach each amount, for each
        day
      </caption>
      <thead>
        <tr>
          <th scope="col">Day</th>
          {THRESHOLDS.map((threshold) => (
            <th scope="col" key={threshold.key}>{threshold.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {place.days.map((day) => (
          <tr key={day.lead_day}>
            <th scope="row">
              <span className="daynum">Day {day.lead_day}</span>
              <span className="daylabel">{day.label}</span>
            </th>
            {THRESHOLDS.map((threshold) => (
              <td key={threshold.key}>
                <strong>{day.counts[threshold.key]}</strong> of {place.members}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Members({ place }) {
  return (
    <section className="members">
      <h2>What each model run gives, in whole millimetres</h2>
      <p className="small">
        51 numbers a day: the control run first, then the 50 perturbed runs, in
        the order the model publishes them. Rounded down, so 9.9 mm shows as 9
        and <strong>0 mm means under 1 mm</strong>.
      </p>
      {place.days.map((day) => {
        const spread = summarise(day.members_mm);
        return (
          <div className="memberday" key={day.lead_day}>
            <h3>
              Day {day.lead_day}
              <span className="daylabel">{day.label}</span>
            </h3>
            <p className="spread">
              lowest {spread.lowest} mm, middle {spread.middle} mm, highest{' '}
              {spread.highest} mm
            </p>
            <ol className="values">
              {day.members_mm.map((value, index) => (
                // eslint-disable-next-line react/no-array-index-key
                <li key={index} className={index === 0 ? 'control' : undefined}>
                  <span className="who">
                    {index === 0 ? 'control' : index}
                  </span>
                  <span className="mm">{value}</span>
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </section>
  );
}

function Footer() {
  return (
    <footer>
      <p className="warning">
        <strong>Not an official warning.</strong> For warnings and advisories,
        see the{' '}
        <a href="https://mausam.imd.gov.in/">
          India Meteorological Department
        </a>
        .
      </p>
      <h2>Credits and licences</h2>
      <p>
        Forecast: ECMWF AIFS ENS open data, 51 members, the 00 UTC run.
        Copyright &copy; 2026 European Centre for Medium-Range Weather
        Forecasts (ECMWF). This data is published under a Creative Commons
        Attribution 4.0 International (CC BY 4.0). ECMWF does not accept any
        liability whatsoever for any error or omission in the data, their
        availability, or for any loss or damage arising from their use.
        Source: <a href="https://www.ecmwf.int">www.ecmwf.int</a>. Modified:
        daily totals and member counts computed from AIFS ENS open data.
      </p>
      <p>
        Observations, used for the track record and not shown on this page:
        NASA GPM IMERG Late Precipitation L3 1 day V07C, DOI
        10.5067/GPM/IMERGDL/DAY/07, a satellite estimate and not ground truth.
      </p>
      <p>
        Built by Sumedha Kar. The code, the specification and the hand checks
        are at{' '}
        <a href="https://github.com/SumedhaKar/Precipitation-Forecast-App">
          github.com/SumedhaKar/Precipitation-Forecast-App
        </a>
        .
      </p>
    </footer>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [city, setCity] = useState(CITIES[0].name);
  const [typed, setTyped] = useState({
    lat: String(CITIES[0].lat),
    lon: String(CITIES[0].lon),
  });
  const [place, setPlace] = useState(null);
  const [placeError, setPlaceError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load(lat, lon) {
    setBusy(true);
    setPlaceError(null);
    try {
      const response = await fetch(
        `/api/place?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
      );
      const body = await response.json();
      if (!response.ok || !body.ok) {
        setPlace(null);
        setPlaceError(body.error || `the forecast could not be read (${response.status})`);
      } else {
        setPlace(body);
      }
    } catch (error) {
      setPlace(null);
      setPlaceError(`the forecast could not be read: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    fetch('/api/health')
      .then((response) => response.json())
      .then((body) => {
        if (body.ok) setHealth(body);
        else setHealthError(body.store || 'the store could not be read');
      })
      .catch((error) => setHealthError(error.message));
    load(CITIES[0].lat, CITIES[0].lon);
    // Once, on load. The forecast changes once a day.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function chooseCity(name) {
    setCity(name);
    const found = CITIES.find((entry) => entry.name === name);
    if (found) {
      setTyped({ lat: String(found.lat), lon: String(found.lon) });
      load(found.lat, found.lon);
    }
  }

  const run = place ? place.run : health;

  return (
    <main>
      <h1>How many model runs say rain</h1>
      <p className="lede">
        One ECMWF AIFS ENS forecast is 51 model runs of the same day. This page
        counts how many of them give 1 mm, 10 mm and 50 mm of rain over each of
        the next five days, for one 0.25 degree square of India. They are
        <strong> model-run counts, not probabilities</strong>.
      </p>

      <StaleBanner run={run} />
      {healthError ? (
        <p className="stale">The store could not be read: {healthError}</p>
      ) : null}
      <RunLine run={run} />

      <Picker
        city={city}
        onCity={chooseCity}
        typed={typed}
        onTyped={(next) => { setTyped(next); setCity(''); }}
        onSubmit={() => load(typed.lat, typed.lon)}
        busy={busy}
      />

      {placeError ? <p className="error">{placeError}</p> : null}

      {place ? (
        <>
          <SquareLine place={place} />
          <CountsTable place={place} />
          <p className="small">
            <strong>0 mm means under 1 mm.</strong> These are model-run counts,
            not probabilities: a count of 40 out of 51 is not a chance of
            rain. A percentage would claim a reliability this forecast has not
            earned yet, and one will only appear beside a published track
            record.
          </p>
          <Members place={place} />
        </>
      ) : null}

      <Footer />
    </main>
  );
}
