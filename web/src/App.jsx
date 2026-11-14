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

import {
  Component, Suspense, lazy, useCallback, useEffect, useRef, useState,
} from 'react';

import Panel, { Welcome, stillness } from './Panel';
import {
  HowToReadLink, ReportCardLink, SITE, plainClick,
} from './TopNav';
import MapKey from './Legend';
import { Clock, Logo, Warn } from './Icons';
import { DayChoice, MyLocation, Search, ThresholdChoice } from './Controls';
import { MEMBERS, countKey } from './palette';
import { inBox, snap, squareText } from './snap';
import { nameOfSquare, placeTitle } from './places';
import { notFoundNote } from './islands';
import { OUTSIDE, THE_BOX, mapProblem } from './messages';
import { keepAnswer, sameSquare } from './answers';

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

/* SPEC 11.40. The one thing this page used to ask the width for is gone
   with the floating key. It asked because whether the key was open on
   first sight was a fact the map had to know in order to pad its fit for
   it, and a stylesheet cannot tell a map anything; the key is off the
   canvas now, the fit pays nothing for it, and when it opens is the
   reader's business and the <details> element's. Nothing in this file
   asks how wide the screen is. */

const search = typeof window !== 'undefined'
  ? new URLSearchParams(window.location.search) : new URLSearchParams();

const handcheck = search.get('handcheck') === '1';

// SPEC 11.29. `?nomap=webgl2`, `=maplibre` or `=chunk` draws the page as it
// is drawn for a reader whose browser cannot show the map, without having to
// find a browser that cannot. It is how the browser check for that case is
// made, and how its screenshot was taken: the map is simply never asked for,
// which is what happens for real when canDraw() says no.
const forced = search.get('nomap');

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

/** "2026-11-13T12:33:35+05:30" -> "13 Nov, 12:33 pm". SPEC 11.38. */
function shortIst(stamp) {
  const full = istText(stamp);
  if (!full) return null;
  // istText gives "13 Nov 2026, 12:33 pm"; the year is the only thing
  // dropped, and it is dropped by the shape of that string and not by a
  // second date parser.
  return full.replace(/^(\d+ \w+) \d{4},/, '$1,');
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
      <strong>This forecast is {hoursOld(run)} hours old;</strong>{' '}
      a newer one has not arrived yet. Nothing here has been updated since{' '}
      {istText(run.run_time_ist)} IST.
    </p>
  );
}

/**
 * How old this run is, counted from the time it names. SPEC 11.38, 11.39.
 *
 * The header had three facts in two sizes of grey -- the run time, the
 * publish time and the run ID -- and on a phone they were two of the lines
 * that pushed the map under the fold. A reader wants to know one thing: is
 * this fresh? So the header says that and nothing else, at every width,
 * and the run's own ID and its UTC time are inside More detail.
 *
 * 11.39 names the **run** time rather than the publish time, and counts
 * the age from the time it has just printed. Before this the line said
 * "Updated 13 Nov, 12:33 pm" -- the publish time -- beside an age counted
 * from the run time, so the two numbers on one line did not agree with
 * each other and the arithmetic a reader could do came out wrong by
 * however long the pipeline had taken.
 *
 * The age is worked out here rather than read from `age_hours`, for the
 * same reason `staleNow` is: a page served from a browser cache would
 * otherwise show an hours figure frozen at whatever it was when the JSON
 * was fetched.
 *
 * When the run is older than the 36 hours of 11.8 the line becomes the
 * warning itself. It never says a newer one is on its way, because nothing
 * here knows that: 11.8's banner used to say "a newer model run has not
 * been published", which is true, and the hopeful reading of it is not.
 */
export function hoursOld(run) {
  if (!run) return null;
  const at = Date.parse(run.run_time_utc);
  if (Number.isNaN(at)) {
    return Number.isFinite(run.age_hours) ? Math.round(run.age_hours) : null;
  }
  return Math.max(0, Math.round((Date.now() - at) / 3_600_000));
}

export function Freshness({ run }) {
  if (!run) return null;
  const hours = hoursOld(run);
  if (staleNow(run)) {
    return (
      <p className="fresh old" role="status">
        <Warn />
        <span>
          <strong>
            This forecast is {hours} hours old; a newer one has not arrived
            yet.
          </strong>
        </span>
      </p>
    );
  }
  return (
    <p className="fresh">
      <Clock />
      <span>
        Forecast from {shortIst(run.run_time_ist)} IST
        {hours === null ? null : ` · ${hours} h old`}
      </span>
    </p>
  );
}

/**
 * The header, on every page. SPEC 11.39.
 *
 * The mark, the site's name, how old this run is, and the pages, in one
 * band; under it, across the whole width, the warning. It is drawn by
 * Site.jsx above whichever page is being read, because the two rules it
 * carries -- freshness, and "not an official warning" -- are rules about
 * every page and not about the forecast.
 *
 * The mark and the name are the way back to the forecast, which is what
 * the back link on the two document pages used to be.
 */
export function PageHead({ run, nav, onGo }) {
  return (
    <header className="pagehead">
      <div className="band">
        <a
          className="brand"
          href="/"
          onClick={(event) => {
            if (!onGo || !plainClick(event)) return;
            event.preventDefault();
            onGo('/');
          }}
        >
          <Logo />
          {/* The page's one h1. The card's question is an h2 under it, and
              the place name takes that h2 once there is an answer, so the
              document has one outline either way. */}
          <h1 className="sitename">{SITE}</h1>
        </a>
        <Freshness run={run} />
        {/* SPEC 11.34 and 11.39: the pages, in the header of all four.
            Three of them are written out as text where there is width for
            it; a phone gets the Menu button, which holds all four. */}
        {nav}
      </div>
      {/* SPEC 11.28: this was in the footer only, below the fold on every
          screen. The footer still carries it; this is the copy a reader
          cannot miss, and 11.39 makes it a bar across the width rather
          than a chip squeezed in beside the name. */}
      <p className="headwarn">
        <Warn />
        <span>
          <strong>Not an official warning.</strong> For alerts:{' '}
          <a href="https://mausam.imd.gov.in/">IMD</a>
        </span>
      </p>
    </header>
  );
}

/**
 * The footer, on every page. SPEC 11.28, cut back by 11.40.
 *
 * Two things were said twice. The warning was here and in the header --
 * 11.39 made the header's copy a bar across the width of all four pages,
 * so this one was the second time a reader met the same sentence on the
 * same screen, several screens apart. And "Credits and licences in full"
 * was a link that opened the disclosure whose own handle, two lines
 * below, read "Credits and licences": two controls for one thing.
 *
 * What is left is the attribution ECMWF's licence asks for, visible
 * whatever a reader does, and one handle to the full form of it.
 */
export function Footer() {
  return (
    <footer>
      {/* SPEC 11.28: ECMWF's licence asks for attribution wherever the data
          is shown, so one line of it is outside the details and visible
          whatever the reader does. The full three-paragraph form is inside. */}
      <p className="credit">
        Model data from ECMWF (AIFS ENS), CC BY 4.0. Checked against NASA
        satellite rain estimates.
      </p>
      <details id="credits">
        <summary>Credits and licences</summary>
        <p>
          Forecast: ECMWF AIFS ENS open data, 51 runs, the 00 UTC run.
          Copyright &copy; 2026 European Centre for Medium-Range Weather
          Forecasts (ECMWF). This data is published under a Creative Commons
          Attribution 4.0 International (CC BY 4.0). ECMWF does not accept any
          liability whatsoever for any error or omission in the data, their
          availability, or for any loss or damage arising from their use.
          Source: <a href="https://www.ecmwf.int">www.ecmwf.int</a>. Modified:
          daily totals and counts of runs computed from AIFS ENS open data.
        </p>
        <p>
          Observations, used for the track record and not shown on this page:
          NASA GPM IMERG Late Precipitation L3 1 day V07C, DOI
          10.5067/GPM/IMERGDL/DAY/07, a satellite estimate and not ground
          truth.
        </p>
        <p>
          Outlines: Natural Earth 1:10m, India point-of-view edition, public
          domain, the same geometry the forecast squares were cut with.
          Cities: Natural Earth 1:10m populated places, public domain. Map
          rendering:
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

/**
 * The map's own failures, caught. SPEC 11.29.
 *
 * React's `lazy` throws when the chunk does not arrive, and a throw during a
 * render takes the whole page down with it unless something catches it —
 * which would mean a network hiccup over 325 KB of map code costing a reader
 * the numbers as well as the picture. This is the only class component on the
 * site, because an error boundary cannot be written any other way.
 */
class MapFrame extends Component {
  constructor(props) {
    super(props);
    this.state = { broken: false };
  }

  static getDerivedStateFromError() {
    return { broken: true };
  }

  componentDidCatch() {
    this.props.onProblem('chunk');
  }

  render() {
    if (this.state.broken) return null;
    return this.props.children;
  }
}

export default function App({ health, healthError, onGo }) {
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
  // SPEC 11.38. The state or union territory the search box last named,
  // which the map is fitted to. It is never a chosen place and never a
  // count: a state is a list of cities here, not a square.
  const [unitBox, setUnitBox] = useState(null);
  // Why the map is not drawn, if it is not: 'webgl2', 'maplibre' or 'chunk'.
  const [noMap, setNoMap] = useState(forced || null);
  // The number of the most recent request for a square's numbers (11.30).
  const asked = useRef(0);

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

  /**
   * One square's numbers, with nothing stale left on the screen. SPEC 11.30.
   *
   * Every request is given a ticket, and an answer is used only if it is the
   * answer to the latest one **and** it is about the square that is chosen
   * now. Before this, two requests in the air meant whichever answered last
   * won: "use my location" put the ring on 22.75 N 88.25 E while the panel
   * went on showing 34.50 N 74.25 E and 51 of 51 model runs at 1 mm, because
   * the older request answered second.
   *
   * The old numbers also go the moment a new square is picked, rather than
   * sitting there under a new heading while the answer is fetched.
   */
  const load = useCallback(async (lat, lon) => {
    const ticket = asked.current + 1;
    asked.current = ticket;
    const here = { lat, lon };
    setPlace(null);
    setBusy(true);
    setPlaceError(null);
    setNotice(null);
    try {
      const response = await fetch(
        `/api/place?lat=${encodeURIComponent(lat)}`
        + `&lon=${encodeURIComponent(lon)}`);
      const body = await response.json();
      // A newer pick has happened while this was in the air: this answer is
      // about somewhere the reader has already left.
      if (ticket !== asked.current) return;
      if (!response.ok || !body.ok) {
        setPlace(null);
        // SPEC 11.28: nothing was found, so nothing is marked. A ring around
        // a square with no numbers in it is a claim the page cannot support.
        setSquare(null);
        // An island group the grid cannot carry is not a failure, and
        // api/place answers with that group's own sentence.
        if (body.island_group) {
          setNotice({ where: body.island_group, note: body.error });
        } else if (String(body.error || '')
          .startsWith('outside the forecast area')) {
          // SPEC 11.38. The sea, or a neighbour's land. Nothing went
          // wrong, so it is the calm line and not a red box, and the name
          // of the place the reader has just left goes out of the search
          // box with it.
          setShown('');
          setNotice({ where: null, note: OUTSIDE, why: body.detail || null });
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
      } else if (keepAnswer(ticket, asked.current, here,
        body.square && body.square.asked)) {
        setPlace(body);
      } else {
        // The ticket was current but the answer is about another square,
        // which should not be possible and is not going on the screen.
        setPlace(null);
        setPlaceError({
          said: 'The forecast could not be read for that square.',
          detail: 'The answer that came back was for a different square, so '
            + 'it was not shown. Try again.',
        });
      }
    } catch (error) {
      if (ticket !== asked.current) return;
      setPlace(null);
      setPlaceError({
        said: `The forecast could not be read: ${error.message}`,
        detail: null,
      });
    } finally {
      if (ticket === asked.current) setBusy(false);
    }
  }, []);

  /**
   * Bring the answer onto the screen. SPEC 11.39, mended by 11.40.
   *
   * On a phone the card is the last block of the page, so choosing a
   * place fills in something a reader cannot see. The page scrolls so
   * that the day pills are at the top of the screen, which puts the
   * pills, the amounts and the top of the card on the screen together:
   * the answer, and the two controls that change it, which is what a
   * reader reaches for next.
   *
   * Whether to scroll at all is read off the layout rather than off the
   * width: on a desktop the card is the column beside the map, so its top
   * is above the map's bottom and there is nothing to bring up. One rule,
   * and no second place where the width of a desktop is written down.
   *
   * The scroll is `window.scrollTo` on a measured target, and 11.40 made
   * it so. `pills.scrollIntoView` asks the browser for a scroll it
   * clamps to the page's height **at that moment** -- and at that moment
   * the card still says "Reading the 51 runs for this square", so the
   * page is a few hundred pixels shorter than it is about to be and the
   * scroll stopped short by exactly the height the card was about to
   * gain. It was measured: 123 pixels short at 390 by 664.
   *
   * Which is also why it is called twice -- once on the choice, so
   * something happens under the reader's thumb straight away, and once
   * when the answer has arrived and the page is its full height. The
   * second call does nothing if the first one landed.
   *
   * `smooth`, unless the reader has asked for less movement, because a
   * page that jumps on a tap is a page that has lost its place.
   */
  const bringCardUp = useCallback(() => {
    if (typeof window === 'undefined') return;
    window.requestAnimationFrame(() => {
      const card = document.querySelector('.fcard');
      const pills = document.querySelector('.pills');
      const map = document.querySelector('.mapcard');
      if (!card || !pills || !map) return;
      // Side by side: the card is not under the map, so nothing has to
      // move. This is the desktop, said as a fact about the layout.
      if (card.getBoundingClientRect().top
        < map.getBoundingClientRect().bottom - 40) return;
      const want = Math.round(pills.getBoundingClientRect().top
        + window.scrollY);
      if (Math.abs(window.scrollY - want) < 4) return;
      window.scrollTo({
        top: want,
        behavior: stillness() ? 'auto' : 'smooth',
      });
    });
  }, []);

  // SPEC 11.40. The second call, in the page the answer has filled in.
  // An effect rather than a line in `load`, because what it waits for is
  // the card being drawn and not the fetch returning.
  useEffect(() => {
    if (place || notice) bringCardUp();
  }, [place, notice, bringCardUp]);

  /**
   * Every way of choosing a place ends up here. SPEC 11.19 and 11.28.
   *
   * The point is snapped in the page before anything is sent, so only a
   * square centre ever reaches a URL, and the search box is set to whatever
   * is now being shown so that the question and the answer agree.
   */
  const show = useCallback((lat, lon, how, label) => {
    if (!inBox(lat, lon)) {
      // SPEC 11.38, as above: outside the box is the same calm line.
      setPlace(null);
      setSquare(null);
      setPlaceError(null);
      setShown('');
      setNotice({ where: null, note: OUTSIDE, why: THE_BOX });
      return;
    }
    const here = snap(lat, lon);
    setSquare(here);
    setFrom(how);
    setShown(label || squareText(here.lat, here.lon));
    load(here.lat, here.lon);
    bringCardUp();
  }, [load, bringCardUp]);

  const pick = useCallback(
    (lat, lon) => show(lat, lon, 'map'), [show]);

  const point = useCallback(
    (lat, lon) => show(lat, lon, 'typed'), [show]);

  const located = useCallback((lat, lon) => {
    const here = snap(lat, lon);
    // SPEC 11.28: the square, never the fix, and a name only when the square
    // is exactly that town's own square.
    //
    // SPEC 11.29: the box shows the square, and the sentence that says it is
    // your location and that your position was not sent anywhere is written
    // once, in the panel. It used to be written by this control as well as
    // by the panel, so it appeared twice, and the control's copy stayed on
    // screen after the reader had gone on to search for somewhere else.
    // SPEC 11.40: the box shows the name of the square, which is what
    // the card's heading says too. It used to show "22.75 N 88.25 E
    // (Kolkata)" -- a grid reference in the box a reader types city names
    // into, with the name they would have typed in brackets after it.
    show(lat, lon, 'location', placeTitle(here.lat, here.lon));
  }, [show]);

  /** A town from the search list, which may be one the grid cannot carry. */
  const town = useCallback((chosen) => {
    if (chosen.not_forecast) {
      setPlace(null);
      setPlaceError(null);
      setSquare(null);
      setFrom('town');
        setShown(chosen.name);
      setNotice({
        where: `${chosen.name}, ${chosen.not_forecast}`,
        note: notFoundNote(chosen.lat, chosen.lon),
      });
      bringCardUp();
      return;
    }
    show(chosen.lat, chosen.lon, 'town', chosen.name);
  }, [show, bringCardUp]);

  const snapTo = useCallback(
    (lat, lon) => (inBox(lat, lon) ? snap(lat, lon) : null), []);

  const toUnit = useCallback((unit) => {
    setUnitBox(unit && unit.box ? unit.box : null);
  }, []);

  // SPEC 11.38. Nothing chosen at all: no square, no island note and no
  // failure. The card is the page's whole answer to "what is this and what
  // do I do", so it is shown exactly while there is no answer to show, and
  // it comes back if the choice is cleared.
  const nothingChosen = !square && !notice && !placeError;

  const run = place ? place.run : health;
  const days = (place ? place.days : (health ? health.days : [])) || [];
  // SPEC 11.40. The chosen place's own count for each of the five days,
  // for the day pills to carry, and null until there is an answer for
  // the square that is chosen now. The rule of 11.30 is the same rule
  // the card follows: a number is shown for the chosen square or not at
  // all, so the pills ask `sameSquare` exactly as the card does.
  const answered = place && place.square
    && sameSquare(place.square.asked, square);
  const dayCounts = answered
    ? Object.fromEntries(place.days.map((entry) => [
      entry.lead_day,
      entry.counts_by_threshold[THRESHOLDS.indexOf(threshold)].count,
    ]))
    : null;
  const squareName = square
    ? (from === 'location' ? 'Your location'
      : nameOfSquare(square.lat, square.lon))
    : null;

  return (
    <>
      <StaleBanner run={run} />
      {healthError ? (
        <p className="stale" role="status">
          The store could not be read: {healthError}
        </p>
      ) : null}

      {/* SPEC 11.39. A page that scrolls, in five blocks. On a phone they
          are one column in this order: the search row, the map, the day
          pills, the amount pills, the card. On a desktop the two rows of
          controls go above the map and the card is the column beside it.
          The order is the stylesheet's, in one grid, so there is one copy
          of every control and no copy of anything. */}
      <main className="forecast">
        {/* SPEC 11.40. The search row and the two questions, in one box.
            On a desktop it is one compact row at the top of the page; on
            a phone the map goes between them, so there the box is
            `display: contents` and the grid places its two children
            itself. One copy of every control either way. */}
        <div className="controls">
          <div className="asks">
            <Search
              onTown={town}
              onPoint={point}
              onUnit={toUnit}
              busy={busy}
              shown={shown}
              onLocation={located}
              snapTo={snapTo}
              from={from}
            />
          </div>

          <div className="pills">
            {days.length ? (
              <DayChoice
                days={days}
                day={day}
                onDay={setDay}
                counts={dayCounts}
                threshold={threshold}
                members={place ? place.members : MEMBERS}
              />
            ) : null}
            <ThresholdChoice
              threshold={threshold}
              onThreshold={setThreshold}
            />
          </div>
        </div>

        <div className="mapcard" id="map">
          <div className="mapwrap">
            {/* SPEC 11.29. Three states, in this order: the map could not
                be drawn, the numbers have not arrived yet, or the map. The
                first is a message in the map's own area and nothing else
                on the page changes, because nothing else on the page needs
                the map: the search, the card, the five days and all 51
                values come from api/place. */}
            {noMap ? (
              <p className="loading mapgone" role="status">
                <span>{mapProblem(noMap)}</span>
              </p>
            ) : null}
            {!noMap && counts && health ? (
              <MapFrame onProblem={setNoMap}>
                <Suspense
                  fallback={<p className="loading">Drawing the map…</p>}
                >
                  <ForecastMap
                    counts={counts}
                    grid={health.source.grid}
                    threshold={threshold}
                    day={day}
                    square={square}
                    squareName={squareName}
                    onPick={pick}
                    onProblem={setNoMap}
                    unitBox={unitBox}
                    handcheck={handcheck}
                  />
                </Suspense>
              </MapFrame>
            ) : null}
            {!noMap && !(counts && health) ? (
              <p className="loading">
                {countsError
                  ? `The forecast could not be read: ${countsError}`
                  : 'Reading the 51 runs…'}
              </p>
            ) : null}
          </div>
        </div>

        {/* SPEC 11.40. The colour key and the card, in one box. On a
            desktop the box is the right-hand panel: the key is its top
            and stays there, and the card under it is what scrolls. On a
            phone the box is seen through, and the grid puts the key
            directly under the map and the card at the end of the page. */}
        <div className="panelcol">
          <MapKey threshold={threshold} />

          <div className="cardcol">
          <section className="fcard" aria-label="Location forecast">
            <Panel
              square={square}
              place={place}
              error={placeError}
              notice={notice}
              busy={busy}
              day={day}
              threshold={threshold}
              onThreshold={setThreshold}
              from={from}
              onGo={onGo}
            />
          </section>
          {/* SPEC 11.39. Two links under the card, and one of them is not
              drawn when the thing it points at is already on the screen:
              the empty card carries How to read this map itself. */}
          <p className="cardlinks">
            {nothingChosen ? null : <HowToReadLink onGo={onGo} />}
            <ReportCardLink onGo={onGo}>Report card</ReportCardLink>
          </p>
            {/* SPEC 11.40. Inside the card's own column, under those
                two links: on a phone that is the last block of the page,
                where a footer goes, and on a desktop it is the bottom of
                the right-hand panel rather than a band under the map. */}
            <Footer />
          </div>
        </div>
      </main>
    </>
  );
}
