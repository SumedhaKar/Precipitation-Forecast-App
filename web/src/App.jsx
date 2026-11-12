// The page. SPEC 11.12 to 11.22.
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

import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react';

import Panel from './Panel';
import { DayChoice, MyLocation, Search, ThresholdChoice } from './Controls';
import { countKey } from './palette';
import { inBox, snap } from './snap';
import cityList from './cities.json';

// SPEC 11.16: MapLibre is 295 KB gzipped, so it is a chunk of its own and
// the run line, the stale banner and the panel paint without waiting for it.
const ForecastMap = lazy(() => import('./Map'));

const CITIES = cityList.cities;
const HOME = CITIES[0];
const THRESHOLDS = [1, 10, 50];
const STALE_HOURS = 36; // SPEC 11.8

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
      <details>
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
          domain, the same geometry the forecast squares were cut with. Map
          rendering: MapLibre GL JS 6.17.0, BSD-3-Clause. No basemap, so
          nothing on the map comes from anywhere else.
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
  const [busy, setBusy] = useState(false);
  const [day, setDay] = useState(1);
  const [threshold, setThreshold] = useState(1);
  const [square, setSquare] = useState(() => snap(HOME.lat, HOME.lon));
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
    try {
      const response = await fetch(
        `/api/place?lat=${encodeURIComponent(lat)}`
        + `&lon=${encodeURIComponent(lon)}`);
      const body = await response.json();
      if (!response.ok || !body.ok) {
        setPlace(null);
        setPlaceError(body.error
          || `the forecast could not be read (${response.status})`);
      } else {
        setPlace(body);
      }
    } catch (error) {
      setPlace(null);
      setPlaceError(`the forecast could not be read: ${error.message}`);
    } finally {
      setBusy(false);
    }
  }, []);

  // SPEC 11.19: snapped here, so only a square centre is ever sent.
  const pick = useCallback((lat, lon) => {
    if (!inBox(lat, lon)) {
      setPlace(null);
      setPlaceError('That is outside the forecast area, which covers 6 to 38 '
        + 'degrees north and 68 to 98 degrees east.');
      return;
    }
    const here = snap(lat, lon);
    setSquare(here);
    setSheetOpen(true);
    load(here.lat, here.lon);
  }, [load]);

  const snapTo = useCallback(
    (lat, lon) => (inBox(lat, lon) ? snap(lat, lon) : null), []);

  useEffect(() => { load(HOME.lat, HOME.lon); }, [load]);

  const run = place ? place.run : health;
  const days = (place ? place.days : (health ? health.days : [])) || [];
  const padding = useMemo(() => ({
    top: 10, bottom: 10, left: 10, right: 10,
  }), []);

  return (
    <div className={sheetOpen ? 'shell open' : 'shell'}>
      <header>
        <h1>How many model runs say rain</h1>
        <RunLine run={run} />
      </header>

      <StaleBanner run={run} />
      {healthError ? (
        <p className="stale" role="status">
          The store could not be read: {healthError}
        </p>
      ) : null}

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
                onPick={pick}
                padding={padding}
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

        {/* A child of the stage, not of the map: over the map on a wide
            screen, and a strip between the map and the sheet on a phone,
            where floating it covered both the country and the legend
            (SPEC 11.18). One copy, two places, no duplicated markup. */}
        <div className="controls">
          {days.length ? (
            <DayChoice days={days} day={day} onDay={setDay} />
          ) : null}
          <ThresholdChoice
            threshold={threshold}
            onThreshold={setThreshold}
          />
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
            <Search onPick={pick} busy={busy} />
            <MyLocation onPick={pick} snapTo={snapTo} />
          </div>
          <Panel
            place={place}
            error={placeError}
            busy={busy}
            day={day}
            threshold={threshold}
            onDay={setDay}
          />
          <Footer />
        </aside>
      </div>
    </div>
  );
}
