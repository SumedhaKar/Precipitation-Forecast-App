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
