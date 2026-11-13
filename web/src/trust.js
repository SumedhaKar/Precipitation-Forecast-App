// The frozen track record, bound to the file it lives in. SPEC 11.33.
//
// web/src/summary.json is results/site_summary.json byte for byte, written by
// pipeline/labels.py and frozen at the tag results-v1. A test fails if the
// two files differ. It is the only one of the three result files the site
// reads: verification.json and labels.json stay in the repository for anyone
// who wants to check the working, and are never shipped to a browser.
//
// The thinking is all in web/src/record.js, which has no imports so that
// `node` can test it against this very file. This is the glue.

import summary from './summary.json';
import * as record from './record';

export const SUMMARY = summary;
export const PERIOD = summary.period;

/** Everything the panel says about one square, day and threshold, or null. */
export function trustFor(region, leadDay, threshold, count, members) {
  return record.trustFor(summary, region, leadDay, threshold, count, members);
}

/** Just the chip, for the two threshold rows that are not the chosen one. */
export function labelFor(region, leadDay, threshold) {
  const group = record.groupFor(summary, region, leadDay, threshold);
  return group ? { label: group.label, colour: group.colour } : null;
}
