// The page. SPEC 11.12 to 11.22, with the design fixes of 11.28.
//
// What talks to what:
//
//   the page  -> /api/health and /api/place, on its own origin
//             -> the store's public counts files, which the map colours from
//   api/      -> the store's public URLs, with no token
//
// The store's address is not in this bundle. api/health gives it at runtime
// (SPEC 11.16), so config/store.json stays the one place it is written down.
//
// Everything shown is a published number. The counts the map paints are the
// bytes of SPEC 8.4, read at i * n_lon + j with n_lon from the run itself;
// the panel's numbers come from api/place, which reads the same run's tiles.
// A test checks the two agree for every square and all fifteen day and
// threshold combinations, so the colour and the number cannot drift apart.
//
// No percentages, anywhere. A percentage implies a reliability that has to be
// earned by the record (SPEC 6), and no track record exists yet.

import { Suspense, lazy, useCallback, useEffect, useState } from 'react';

import Panel from './Panel';
import Legend from './Legend';
import { DayChoice, MyLocation, Search, ThresholdChoice } from './Controls';
import { countKey } from './palette';
import { inBox, snap, squareText } from './snap';
import { nameOfSquare } from './places';
import { notFoundNote } from './islands';

// SPEC 11.16: MapLibre is 295 KB gzipped, so it is a chunk of its own and
// the run line, the stale banner and the panel paint without waiting for it.
const ForecastMap = lazy(() => import('./Map'));

const THRESHOLDS = [1, 10, 50];
const STALE_HOURS = 36; // SPEC 11.8

// SPEC 11.28. The page opens on day 1 at 1 mm with nothing chosen, so the
// first thing shown is the whole country and an explanation of what a colour
// is, rather than one city's numbers nobody asked for.
const FIRST_DAY = 1;
const FIRST_THRESHOLD = 1;

const handcheck = typeof window !== 'undefined'
  && new URLSearchParams(window.location.search).get('handcheck') === '1';

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

/**
 * Is this run too old to show without saying so?
 *
 * api/health says so too, and the page works it out again from
 * `run_time_utc`, so a page served from a browser cache cannot show a
 * fresh-looking banner over an old forecast (SPEC 11.8).
 */
function staleNow(run) {
  if (!run || !run.run_time_utc) return false;
  const at = Date.parse(run.run_time_utc);
  if (Number.isNaN(at)) return Boolean(run.stale);
  return (Date.now() - at) / 3_600_000 > STALE_HOURS;
}

export function StaleBanner({ run }) {
  if (!staleNow(run)) return null;
  return (
    <p className="stale" role="status">
      <strong>This forecast is {run.age_hours} hours old.</strong>{' '}
      A newer model run has not been published. Nothing here has been updated
      since {istText(run.run_time_ist)} IST.
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
      <span className="runid">Run {run.run_id}</span>
    </p>
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
      {/* SPEC 11.28: ECMWF's licence asks for attribution wherever the data
          is shown, so one line of it is outside the details and visible
          whatever the reader does. The full three-paragraph form is inside. */}
      <p className="credit">
        Forecast: ECMWF AIFS ENS, CC BY 4.0.{' '}
        <a
          href="#credits"
          onClick={() => {
            const details = document.getElementById('credits');
            if (details) details.open = true;
          }}
        >
          Credits and licences in full
        </a>
        .
      </p>
      <details id="credits">
        <summary>Credits and licences</summary>
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
          10.5067/GPM/IMERGDL/DAY/07, a satellite estimate and not ground
          truth.
        </p>
        <p>
          Outlines: Natural Earth 1:10m, India point-of-view edition, public
          domain, the same geometry the forecast squares were cut with. Towns:
          Natural Earth 1:10m populated places, public domain. Map rendering:
          MapLibre GL JS 6.17.0, BSD-3-Clause. No basemap, so nothing on the
          map comes from anywhere else.
        </p>
        <p>
          Built by Sumedha Kar. The code, the specification and the hand
          checks are at{' '}
          <a href="https://github.com/SumedhaKar/Precipitation-Forecast-App">
            github.com/SumedhaKar/Precipitation-Forecast-App
          </a>
          .
        </p>
      </details>
    </footer>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [healthError, setHealthError] = useState(null);
  const [counts, setCounts] = useState(null);
  const [countsError, setCountsError] = useState(null);
  const [place, setPlace] = useState(null);
  const [placeError, setPlaceError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [day, setDay] = useState(FIRST_DAY);
  const [threshold, setThreshold] = useState(FIRST_THRESHOLD);
  const [square, setSquare] = useState(null);
  const [from, setFrom] = useState(null);
  const [shown, setShown] = useState('');
  const [sheetOpen, setSheetOpen] = useState(false);

  // One request to our own origin: the run, the day labels, the staleness,
  // and where the store is.
  useEffect(() => {
    let alive = true;
    fetch('/api/health')
      .then((response) => response.json())
      .then((body) => {
        if (!alive) return;
        if (body.ok) setHealth(body);
        else setHealthError(body.store || 'the store could not be read');
      })
      .catch((error) => alive && setHealthError(error.message));
    return () => { alive = false; };
  }, []);

  // All fifteen counts files, in parallel, straight from the store: 14,441
  // bytes on the wire measured on the real run (SPEC 11.13). After this,
  // changing day or threshold costs no network at all.
  useEffect(() => {
    if (!health || !health.source) return undefined;
    const { base_url: base, paths, counts_files: files } = health.source;
    if (!base || !paths || !files) {
      setCountsError('api/health did not say where the store is');
      return undefined;
    }
    let alive = true;
    const wanted = [];
    for (const amount of THRESHOLDS) {
      for (let lead = 1; lead <= health.days.length; lead += 1) {
        wanted.push({
          key: countKey(amount, lead),
          file: `ge${amount}mm_day${lead}.u8`,
        });
      }
    }
    Promise.all(wanted.map(async (want) => {
      if (!files.includes(want.file)) {
        throw new Error(`the run does not publish ${want.file}`);
      }
      const response = await fetch(`${base}/${paths.counts}/${want.file}`);
      if (!response.ok) {
        throw new Error(`the store answered ${response.status} for `
          + want.file);
      }
      const bytes = new Uint8Array(await response.arrayBuffer());
      const expected = health.source.grid.n_lat * health.source.grid.n_lon;
      if (bytes.length !== expected) {
        throw new Error(`${want.file} is ${bytes.length} bytes, not `
          + `${expected}`);
      }
      return [want.key, bytes];
    }))
      .then((pairs) => alive && setCounts(Object.fromEntries(pairs)))
      .catch((error) => alive && setCountsError(error.message));
    return () => { alive = false; };
  }, [health]);

  const load = useCallback(async (lat, lon) => {
    setBusy(true);
    setPlaceError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/place?lat=${encodeURIComponent(lat)}`
        + `&lon=${encodeURIComponent(lon)}`);
      const body = await response.json();
      if (!response.ok || !body.ok) {
        setPlace(null);
        // SPEC 11.28: nothing was found, so nothing is marked. A ring around
        // a square with no numbers in it is a claim the page cannot support.
        setSquare(null);
        // An island group the grid cannot carry is not a failure, and
        // api/place answers with that group's own sentence.
        if (body.island_group) {
          setNotice({ where: body.island_group, note: body.error });
        } else {
          setPlaceError({
            said: body.error
              || `the forecast could not be read (${response.status})`,
            // The detail is the half that says why, and the first build
            // threw it away: "outside the forecast area" on its own reads
            // as a refusal rather than an explanation.
            detail: body.detail || null,
          });
        }
      } else {
        setPlace(body);
      }
    } catch (error) {
      setPlace(null);
      setPlaceError({
        said: `The forecast could not be read: ${error.message}`,
        detail: null,
      });
    } finally {
      setBusy(false);
    }
  }, []);

  /**
   * Every way of choosing a place ends up here. SPEC 11.19 and 11.28.
   *
   * The point is snapped in the page before anything is sent, so only a
   * square centre ever reaches a URL, and the search box is set to whatever
   * is now being shown so that the question and the answer agree.
   */
  const show = useCallback((lat, lon, how, label) => {
    if (!inBox(lat, lon)) {
      setPlace(null);
      setSquare(null);
      setNotice(null);
      setPlaceError({
        said: 'That is outside the forecast area.',
        detail: 'The forecast covers 6 to 38 degrees north and 68 to 98 '
          + 'degrees east.',
      });
      return;
    }
    const here = snap(lat, lon);
    setSquare(here);
    setFrom(how);
    setSheetOpen(true);
    setShown(label || squareText(here.lat, here.lon));
    load(here.lat, here.lon);
  }, [load]);

  const pick = useCallback(
    (lat, lon) => show(lat, lon, 'map'), [show]);

  const point = useCallback(
    (lat, lon) => show(lat, lon, 'typed'), [show]);

  const located = useCallback((lat, lon) => {
    const here = snap(lat, lon);
    const name = nameOfSquare(here.lat, here.lon);
    // SPEC 11.28: the square, never the fix, and a name only when the square
    // is exactly that town's own square.
    show(lat, lon, 'location',
      `Your location: square ${squareText(here.lat, here.lon)}`
      + (name ? ` (${name})` : ''));
  }, [show]);

  /** A town from the search list, which may be one the grid cannot carry. */
  const town = useCallback((chosen) => {
    if (chosen.not_forecast) {
      setPlace(null);
      setPlaceError(null);
      setSquare(null);
      setFrom('town');
      setSheetOpen(true);
      setShown(chosen.name);
      setNotice({
        where: `${chosen.name}, ${chosen.not_forecast}`,
        note: notFoundNote(chosen.lat, chosen.lon),
      });
      return;
    }
    show(chosen.lat, chosen.lon, 'town', chosen.name);
  }, [show]);

  const snapTo = useCallback(
    (lat, lon) => (inBox(lat, lon) ? snap(lat, lon) : null), []);

  const run = place ? place.run : health;
  const days = (place ? place.days : (health ? health.days : [])) || [];
  const squareName = square
    ? (from === 'location' ? 'Your location'
      : nameOfSquare(square.lat, square.lon))
    : null;

  return (
    <div className={sheetOpen ? 'shell open' : 'shell'}>
      <header>
        <div className="titles">
          <h1>How many model runs say rain</h1>
          <RunLine run={run} />
        </div>
        {/* SPEC 11.28: this was in the footer only, below the fold on every
            screen. The footer still carries it; this is the copy a reader
            cannot miss. */}
        <p className="headwarn">
          <strong>Not an official warning.</strong>{' '}
          <a href="https://mausam.imd.gov.in/">India Meteorological
            Department</a>
        </p>
      </header>

      <StaleBanner run={run} />
      {healthError ? (
        <p className="stale" role="status">
          The store could not be read: {healthError}
        </p>
      ) : null}

      {/* SPEC 11.28: a bar above the map, not a card floating on it. As a
          card the controls covered Tamil Nadu, Kerala and the tip of the
          country, and the legend covered the Bay of Bengal and the Andaman
          Islands. Nothing is over the map now but MapLibre's zoom buttons. */}
      <div className="controls">
        {days.length ? (
          <DayChoice days={days} day={day} onDay={setDay} />
        ) : null}
        <ThresholdChoice
          threshold={threshold}
          onThreshold={setThreshold}
        />
        <Legend threshold={threshold} />
      </div>

      <div className="stage">
        <div className="mapwrap">
          {counts && health ? (
            <Suspense fallback={<p className="loading">Drawing the map…</p>}>
              <ForecastMap
                counts={counts}
                grid={health.source.grid}
                threshold={threshold}
                day={day}
                square={square}
                squareName={squareName}
                onPick={pick}
                handcheck={handcheck}
              />
            </Suspense>
          ) : (
            <p className="loading">
              {countsError
                ? `The forecast could not be read: ${countsError}`
                : 'Reading the forecast…'}
            </p>
          )}
        </div>

        <aside className="panel" aria-label="The square you chose">
          <button
            type="button"
            className="handle"
            aria-expanded={sheetOpen}
            onClick={() => setSheetOpen(!sheetOpen)}
          >
            {sheetOpen ? 'Hide the details' : 'Show the details'}
          </button>
          <div className="finder">
            <Search
              onTown={town}
              onPoint={point}
              busy={busy}
              shown={shown}
            />
            <MyLocation onLocation={located} snapTo={snapTo} />
          </div>
          <Panel
            place={place}
            error={placeError}
            notice={notice}
            busy={busy}
            day={day}
            threshold={threshold}
            onDay={setDay}
            onThreshold={setThreshold}
            from={from}
          />
          <Footer />
        </aside>
      </div>
    </div>
  );
}
