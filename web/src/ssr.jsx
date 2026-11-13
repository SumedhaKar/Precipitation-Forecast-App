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
import TopNav from './TopNav';
import Panel, { summaryLine } from './Panel';
import { ISLANDS, islandGroup } from './islands';
import { NO_LOCATION, OUTSIDE, locationProblem, mapProblem }
  from './messages';
import { PICK_A_PLACE } from './record';

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
  [OUTSIDE, NO_LOCATION, mapProblem('webgl2'), mapProblem('maplibre'),
    mapProblem('chunk'), mapProblem(), locationProblem(1),
    locationProblem(2), locationProblem(3), locationProblem(9)]
    .forEach((said) => {
      out.push(renderToStaticMarkup(
        <Panel error={{ said, detail: said }} day={1} threshold={10}
          onDay={nothing} onThreshold={nothing} />));
    });

  // The bar of 11.37: both labels the handle can carry, the button, and
  // every line a chosen square can put in it.
  out.push(PICK_A_PLACE, 'Hide the details', 'Search');
  answers.forEach((place) => {
    [1, 10, 50].forEach((threshold) => {
      place.days.forEach((entry) => {
        out.push(summaryLine(place, place.square.asked, entry.lead_day,
          threshold) || '');
      });
    });
  });

  return out;
}
