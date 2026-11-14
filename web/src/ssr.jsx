// The two document pages, rendered to HTML with no browser. SPEC 11.34.
//
// This is a test entry, not part of the site: nothing imports it and
// `vite build` never reaches it. tests/test_api_consistency.py builds it with
// `vite build --ssr` and runs it under node, which is how every sentence and
// every number either page can show is checked against the files they came
// from -- including the ones a reader only sees after changing a picker,
// because the whole page is rendered for every choice.
//
// React's own server renderer is used because it is already a dependency and
// because it renders the real components. A second implementation of the
// pages in the test would only prove that the second implementation agrees
// with itself.

import { renderToStaticMarkup } from 'react-dom/server';

import summary from './summary.json';
import ReportCard, { Bands } from './ReportCard';
import HowWeChecked, {
  Blocks, Decomposition, Maps, Sensitivities,
} from './HowWeChecked';
import HowToRead from './HowToRead';
import TopNav, { Menu } from './TopNav';
import Panel, { Welcome } from './Panel';
import { DayChoice, MyLocation, Search, ThresholdChoice } from './Controls';
import { UNITS, noMatch, tooBig, townLabel, townsIn } from './places';
import MapKey from './Legend';
import { Footer, Freshness, PageHead, StaleBanner } from './App';
import { OUTSIDE, THE_BOX } from './messages';
import { ISLANDS, islandGroup } from './islands';
import { NO_LOCATION, locationProblem, mapProblem } from './messages';

/** Both pages as HTML, and the menu as it is drawn on each path. */
export function pages() {
  return {
    report_card: renderToStaticMarkup(<ReportCard />),
    how_we_checked: renderToStaticMarkup(<HowWeChecked />),
    nav: {
      '/': renderToStaticMarkup(<TopNav path="/" onGo={() => {}} />),
      '/report-card': renderToStaticMarkup(
        <TopNav path="/report-card" onGo={() => {}} />),
      '/how-we-checked': renderToStaticMarkup(
        <TopNav path="/how-we-checked" onGo={() => {}} />),
    },
  };
}

/** Every section that has a picker, rendered for every choice it offers. */
export function everyChoice() {
  const out = [];
  summary.regions.forEach((region) => {
    out.push(renderToStaticMarkup(<Blocks start={{ region }} />));
    summary.leads.forEach((lead) => {
      out.push(renderToStaticMarkup(
        <Sensitivities start={{ region, lead }} />));
      summary.thresholds_mm.forEach((threshold) => {
        out.push(renderToStaticMarkup(
          <Bands start={{ region, lead, threshold }} />));
        out.push(renderToStaticMarkup(
          <Decomposition start={{ region, lead, threshold }} />));
      });
    });
  });
  summary.leads.forEach((lead) => {
    summary.thresholds_mm.forEach((threshold) => {
      out.push(renderToStaticMarkup(<Maps start={{ lead, threshold }} />));
    });
  });
  return out;
}

/**
 * Every word the forecast page's panel and bar can put on a screen.
 *
 * The two document pages have had a forbidden-word sweep since they were
 * written. The panel had one only over the two strings it *computes* -- the
 * day sentence of api/place (11.20) and the track-record answers of
 * record.js -- and never over its own written text, which is most of what a
 * reader reads. Nor over the bar 11.37 added.
 *
 * `answers` are real `/api/place` replies, passed in rather than invented,
 * so what is rendered here is the panel a reader is actually given.
 */
export function forecastWords(answers) {
  const out = [];
  const nothing = () => {};
  const somewhere = answers.length
    ? answers[0].square.asked : { lat: 23.25, lon: 77.5 };

  // A real answer, for every day and every threshold: every count row, the
  // dots, all 51 values, and every trust sentence those counts reach.
  answers.forEach((place) => {
    [1, 10, 50].forEach((threshold) => {
      place.days.forEach((entry) => {
        out.push(renderToStaticMarkup(
          <Panel
            place={place}
            day={entry.lead_day}
            threshold={threshold}
            onDay={nothing}
            onThreshold={nothing}
            from={{ how: 'tap' }}
            square={place.square.asked}
          />));
      });
    });
  });

  // The panel's other states: nothing chosen, waiting, a square still
  // loading, an island the grid cannot carry, and each way it can fail.
  out.push(renderToStaticMarkup(
    <Panel day={1} threshold={10} onDay={nothing} onThreshold={nothing} />));
  out.push(renderToStaticMarkup(
    <Panel busy day={1} threshold={10} onDay={nothing}
      onThreshold={nothing} />));
  out.push(renderToStaticMarkup(
    <Panel square={somewhere} day={1} threshold={10} onDay={nothing}
      onThreshold={nothing} />));
  ISLANDS.forEach((island) => {
    const lat = island.lat[0];
    const lon = island.lon[0];
    out.push(renderToStaticMarkup(
      <Panel notice={{ where: islandGroup(lat, lon), note: island.note }}
        day={1} threshold={10} onDay={nothing} onThreshold={nothing} />));
  });
  // SPEC 11.38: OUTSIDE is not here. A tap on the sea is a notice now, and
  // it is rendered as one above.
  [NO_LOCATION, mapProblem('webgl2'), mapProblem('maplibre'),
    mapProblem('chunk'), mapProblem(), locationProblem(1),
    locationProblem(2), locationProblem(3), locationProblem(9)]
    .forEach((said) => {
      out.push(renderToStaticMarkup(
        <Panel error={{ said, detail: said }} day={1} threshold={10}
          onDay={nothing} onThreshold={nothing} />));
    });

  // SPEC 11.38. Everything outside the panel that the forecast page draws:
  // the welcome card, both control groups for every day and every amount,
  // the legend for all three amounts, the header's lines and the footer.
  // Before this the sweep covered the panel and the bar alone, which is
  // not where most of a first-time reader's words are.
  const days = answers.length ? answers[0].days : [];
  const run = answers.length ? answers[0].run : null;
  out.push(renderToStaticMarkup(<Welcome onGo={nothing} />));
  // SPEC 11.39. The header of every page, and the menu behind the button
  // on a phone: the band, the freshness line, the warning bar and all
  // four page names. Before this the sweep never saw any of them.
  out.push(renderToStaticMarkup(
    <Menu path="/" onGo={nothing} />));
  out.push(renderToStaticMarkup(
    <PageHead run={null} nav={<TopNav path="/" onGo={nothing} />}
      onGo={nothing} />));
  // SPEC 11.39. How to read this map, which is a page of its own now. It
  // is swept with the forecast page and not with the two document pages,
  // because it is the one page that may say "it is not a probability" --
  // refusing that reading is the whole point of the sentence.
  out.push(renderToStaticMarkup(<HowToRead />));
  // Every day chosen, and with the reader's own date on each of the five,
  // so "Today" and "Tomorrow" are both rendered and both swept.
  days.forEach((entry) => {
    days.forEach((today) => {
      out.push(renderToStaticMarkup(
        <DayChoice days={days} day={entry.lead_day} onDay={nothing}
          today={String(today.from_ist).slice(0, 10)} />));
    });
  });
  // SPEC 11.40. And the morning when the five days start tomorrow, which
  // none of the twenty-five above can be: the reader's date is the day
  // before the first of the five, which is the state the note is drawn
  // in. Without this the sweep would never see those words.
  if (days.length) {
    const before = new Date(
      Date.parse(`${String(days[0].from_ist).slice(0, 10)}T00:00:00Z`)
      - 86_400_000).toISOString().slice(0, 10);
    out.push(renderToStaticMarkup(
      <DayChoice days={days} day={days[0].lead_day} onDay={nothing}
        today={before} />));
  }
  [1, 10, 50].forEach((threshold) => {
    out.push(renderToStaticMarkup(
      <ThresholdChoice threshold={threshold} onThreshold={nothing}
      onGo={nothing} />));
    // SPEC 11.39. The colour key, shut and open, for all three amounts.
    out.push(renderToStaticMarkup(
      <MapKey threshold={threshold} open={false} onToggle={nothing} />));
    out.push(renderToStaticMarkup(
      <MapKey threshold={threshold} open onToggle={nothing} />));
  });
  out.push(renderToStaticMarkup(
    <Search onTown={nothing} onPoint={nothing} onUnit={nothing} busy={false}
      shown="" onLocation={nothing} snapTo={nothing} from={null} />));
  // SPEC 11.38. The state block, for every one of the 36, and the line a
  // query that matched nothing is answered with.
  UNITS.forEach((unit) => {
    out.push(tooBig(unit.name));
    townsIn(unit.name).forEach((town) => out.push(townLabel(town)));
  });
  out.push(noMatch('Ooty'), noMatch('Bombay Central'));
  out.push(renderToStaticMarkup(
    <MyLocation onLocation={nothing} snapTo={nothing} from={null} />));
  out.push(renderToStaticMarkup(<Footer />));
  if (run) {
    // The run a test publishes is dated, so freshness is forced here:
    // both of the two things this line can say are rendered and swept.
    const fresh = {
      ...run,
      run_time_utc: new Date(Date.now() - 2 * 3_600_000).toISOString(),
      age_hours: 2,
    };
    out.push(renderToStaticMarkup(<Freshness run={fresh} />));
    // And the same run made old, which is the only other thing the
    // freshness line and the banner can say.
    const old = { ...run, age_hours: 41, stale: true,
      run_time_utc: '2026-01-01T00:00:00+00:00' };
    out.push(renderToStaticMarkup(<Freshness run={old} />));
    out.push(renderToStaticMarkup(<StaleBanner run={old} />));
    // And the header as a whole, fresh and old, which is where the
    // freshness line is actually read.
    [fresh, old].forEach((when) => out.push(renderToStaticMarkup(
      <PageHead run={when} nav={<TopNav path="/" onGo={nothing} />}
        onGo={nothing} />)));
  }
  // The calm line for a tap on the sea or on a neighbour's land.
  out.push(renderToStaticMarkup(
    <Panel notice={{ where: null, note: OUTSIDE, why: THE_BOX }}
      day={1} threshold={10} onDay={nothing} onThreshold={nothing} />));

  // SPEC 11.39. The bar of 11.37, its one-line summary and the prompt it
  // showed with nothing chosen are gone: the card is on the page, so
  // there is no second copy of the headline to sweep.

  return out;
}
