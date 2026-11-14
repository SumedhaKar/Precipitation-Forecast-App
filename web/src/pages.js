// What the report card and How we checked ask the record. SPEC 11.34.
//
// Pure functions over the two files handed in, so `node` can load this file
// and a test can drive every one of them against the real
// web/src/summary.json and web/src/details.json. The components do the
// drawing and nothing else.
//
// The one import is web/src/record.js, with its extension written out so
// that node resolves it as a browser would: the band sentence on this page
// has to be the same function as the band sentence in the place panel, or
// the two could say different things about the same band.
//
// Nothing here computes a score. Every number is read from the files, which
// were written by pipeline/verify.py before any of it was looked at
// (SPEC 6.8), and printed as it was written.

import { groupFor, howOften, pastSentence } from './record.js';

export { groupFor, howOften, pastSentence };

// SPEC 11.34. Sixty cells reading "Treat as a rough guide" is a wall rather
// than a grid, so the grid uses these, with the label in full as the cell's
// accessible name and a key above it giving all three.
export const SHORT = {
  'Good track record': 'Good',
  'Treat as a rough guide': 'Rough guide',
  'Not enough past data': 'Too few',
};

export function shortLabel(label) {
  return SHORT[label] || label;
}

/** n -> "1,635". The same grouping as the panel's. */
export function grouped(value) {
  const digits = String(Math.round(Math.abs(value)));
  let out = '';
  for (let at = digits.length; at > 0; at -= 3) {
    out = digits.slice(Math.max(0, at - 3), at) + (out ? `,${out}` : '');
  }
  return (value < 0 ? '-' : '') + out;
}

export function fixed(value, places = 2) {
  if (value === null || value === undefined) return null;
  const text = Number(value).toFixed(places);
  return /^-0\.0*$/.test(text) ? text.slice(1) : text;
}

function amount(threshold) {
  return `${Number.isInteger(threshold) ? threshold : threshold} mm`;
}

/**
 * The one plain line about the whole record. SPEC 11.34.
 *
 * Counted from the file every time rather than written down, so the day a
 * group turns green or grey the sentence turns with it.
 */
/**
 * The four sentences at the top of the report card. SPEC 11.41.
 *
 * The page already had one plain line about the whole record -- the
 * `headline` below -- but it sat under the period and above sixty labels,
 * a skill plot and twelve reliability bands, and the readers who were
 * asked to use this site did not get as far as reading it. What they
 * wanted was the answer to "can I believe this?" in four sentences,
 * before anything that has to be explained.
 *
 * So these are those four, and every number in them is counted from
 * web/src/summary.json here rather than written into the page: how many
 * runs were saved, how many of the labels say what, how many beat the
 * usual rain, and whether the honesty check failed. The day any of that
 * changes the sentences change with it, and the day the labels stop
 * being all one label the second sentence stops claiming they are.
 *
 * The period is the file's own period, quoted out of it, so the dates
 * here and the dates under the heading cannot differ.
 */
export function tldr(summary) {
  const groups = summary.groups || [];
  const total = groups.length;
  const runs = Math.max(0, ...groups.map(
    (group) => group.conditions.enough_data.dates || 0));
  // "runs of 13 May to 5 November 2026", out of the file's own period.
  const span = /runs of ([^,]+), checked/.exec(summary.period || '');
  const when = span ? span[1] : null;
  const counts = {};
  groups.forEach((group) => {
    counts[group.label] = (counts[group.label] || 0) + 1;
  });
  const names = Object.keys(counts);
  const rough = counts['Treat as a rough guide'] || 0;
  const beat = groups.filter(
    (group) => group.conditions.skill_above_zero.pass).length;
  const confident = groups.filter(
    (group) => !group.conditions.small_honesty_error.pass).length;
  // The highest count any reliability band reaches, which is how many
  // runs there are. Nothing here is told the number.
  const members = Math.max(51, ...groups.flatMap(
    (group) => (group.buckets || []).map((bucket) => bucket.k_to || 0)));

  const saved = `We saved ${runs} old forecasts`
    + `${when ? ` from ${when}` : ''}, and checked each one against what `
    + 'satellites saw afterwards.';

  const everywhere = names.length === 1
    && names[0] === 'Treat as a rough guide'
    ? `The forecasts worked as a rough guide everywhere: all ${total} `
      + 'labels say so'
    : `${rough} of the ${total} labels say treat the forecasts as a rough `
      + 'guide';
  const worked = `${everywhere}, and ${beat} of the ${total} did better `
    + 'than just guessing the usual rain for that place and month.';

  const over = confident === total
    ? `But when most of the ${members} runs agreed on rain, the satellite `
      + 'saw rain less often than they suggested.'
    : `But in ${confident} of the ${total}, when most of the ${members} `
      + 'runs agreed on rain, the satellite saw rain less often than they '
      + 'suggested.';
  const honest = confident === 0
    ? `Where many of the ${members} runs agreed on rain, the satellite saw `
      + 'rain about as often as they suggested.'
    : over;

  return {
    runs,
    total,
    beat,
    confident,
    period: when,
    sentences: [saved, worked, honest,
      'So treat them as a helpful hint, not a promise.'],
  };
}

export function headline(summary) {
  const groups = summary.groups || [];
  const counts = {};
  groups.forEach((group) => {
    counts[group.label] = (counts[group.label] || 0) + 1;
  });
  const names = Object.keys(counts);
  const honest = groups.filter(
    (group) => !group.conditions.small_honesty_error.pass).length;
  const beat = groups.filter(
    (group) => group.conditions.skill_above_zero.pass).length;
  const one = names.length === 1
    ? `All ${groups.length} of them read "${names[0]}".`
    : names.map((name) => `${counts[name]} read "${name}"`).join(', ') + '.';
  // "and all 60 were too confident" when it is every one of them, which is
  // plainer than "and 60 of them", and it stops being true the day it is
  // not all of them.
  const confident = honest === groups.length
    ? `all ${honest} were too confident`
    : `${honest} of them were too confident`;
  return {
    total: groups.length,
    counts,
    beat,
    sentence: `${one} ${beat} of the ${groups.length} beat the usual rain `
      + `for their place and month over the whole range, and ${confident}: `
      + 'when many runs agreed, the satellite saw it less often than they '
      + 'said.',
  };
}

/** One row per threshold, one cell per lead day, for one region. */
export function gridFor(summary, region) {
  return (summary.thresholds_mm || []).map((threshold) => ({
    threshold,
    cells: (summary.leads || []).map((lead) => {
      const group = groupFor(summary, region, lead, threshold);
      return {
        lead,
        label: group ? group.label : null,
        short: group ? shortLabel(group.label) : null,
        colour: group ? group.colour : null,
        bss: group ? group.bss : null,
        // SPEC 11.36. Read, never worked out again here: the page shows
        // what `site_summary.json` already decided, and a page that
        // recomputed a condition could disagree with the label beside it.
        beat: group
          ? Boolean(group.conditions.skill_above_zero.pass) : false,
      };
    }),
  }));
}

/** The five points and their ranges, for one region and threshold. */
export function skillSeries(summary, region, threshold) {
  return (summary.leads || []).map((lead) => {
    const group = groupFor(summary, region, lead, threshold);
    return group ? {
      lead,
      bss: group.bss,
      lo: group.bss_lo,
      hi: group.bss_hi,
      above: group.conditions.skill_above_zero.pass,
    } : { lead, bss: null, lo: null, hi: null, above: false };
  });
}

/**
 * Every counted band of one group, with the panel's own sentence.
 *
 * The sentence is `pastSentence` from web/src/record.js, not a second copy
 * of the wording: the report card and the place panel cannot say different
 * things about the same band.
 */
export function bandRows(summary, region, lead, threshold) {
  const group = groupFor(summary, region, lead, threshold);
  if (!group) return [];
  return group.buckets.map((bucket) => ({
    k_from: bucket.k_from,
    k_to: bucket.k_to,
    cases: bucket.cases,
    times_in_10: bucket.times_in_10,
    often: howOften(bucket),
    sentence: pastSentence(group, bucket.k_from, 51),
  }));
}

/** The frequency check for all India, one sentence. */
export function frequencySentence(summary, lead, threshold) {
  const rows = (summary.frequency_check || {}).all_india || [];
  const row = rows.find(
    (one) => one.lead_day === lead
      && Math.abs(one.threshold_mm - threshold) < 1e-9);
  if (!row) return null;
  const more = row.ratio >= 1;
  return {
    row,
    sentence: `Over all India on day ${lead}, the model said `
      + `${amount(threshold)} or more ${fixed(row.ratio)} times as often as `
      + `the satellite saw it: ${fixed(row.mean_forecast, 3)} against `
      + `${fixed(row.observed, 3)}, over ${grouped(row.cases)} cases. `
      + `That is ${more ? 'more' : 'less'} often than it happened.`,
  };
}

/** CRPS for one region and lead day, one sentence with its yardstick. */
export function crpsSentence(summary, region, lead) {
  if (!summary.crps_compared) return null;
  const row = (summary.crps || []).find(
    (one) => one.region === region && one.lead_day === lead);
  if (!row) return null;
  const beat = row.crpss_lo > 0;
  const missed = row.crpss_hi < 0;
  const how = beat ? 'beat that baseline' : (missed ? 'did not beat that '
    + 'baseline' : 'is too close to that baseline to tell');
  return {
    row,
    sentence: 'A second score, CRPS, asks a different question: not whether '
      + 'the right number of runs crossed a line, but how close the whole '
      + 'spread of 51 runs was to the millimetres the satellite saw. '
      + `Against ${summary.crps_baseline}, ${region} on day ${lead} `
      + `${how}, by ${fixed(row.crpss_fair, 3)}, with a range from `
      + `${fixed(row.crpss_lo, 3)} to ${fixed(row.crpss_hi, 3)}.`,
  };
}

// ---------------------------------------------- what How we checked reads

/** A column-and-row table from site_details.json, as objects. */
export function rowsOf(table) {
  if (!table || !table.rows) return [];
  return table.rows.map((row) => {
    const out = {};
    table.columns.forEach((name, at) => { out[name] = row[at]; });
    return out;
  });
}

export function scoredRow(details, variant, region, lead, threshold) {
  return rowsOf(details.scored).find(
    (row) => row.variant === variant && row.region === region
      && row.lead_day === lead
      && Math.abs(row.threshold_mm - threshold) < 1e-9) || null;
}

/**
 * The Murphy decomposition of one group, shown adding up. SPEC 5.3.
 *
 * REL - RES + UNC = BS exactly, in float64, and the page shows the sum
 * rather than asserting it: a reader can add the three numbers themselves.
 */
export function decomposition(details, variant, region, lead, threshold) {
  const row = scoredRow(details, variant, region, lead, threshold);
  if (!row) return null;
  const sum = row.reliability - row.resolution + row.uncertainty;
  return {
    reliability: row.reliability,
    resolution: row.resolution,
    uncertainty: row.uncertainty,
    residual: row.residual,
    brier: row.brier,
    bs: row.bs,
    sum,
    gap: Math.abs(sum - row.brier),
    bss: row.bss,
    base_rate: row.base_rate,
    cases: row.cases,
  };
}

/** One line per variant, for the 51-against-50 and inland-only comparisons. */
export function variantRows(details, region, lead, threshold) {
  return (details.variants || []).map((variant) => {
    const row = scoredRow(details, variant.name, region, lead, threshold);
    return {
      variant: variant.name,
      note: variant.note,
      members: variant.members,
      squares: variant.squares,
      bss: row ? row.bss : null,
      lo: row ? row.bss_lo : null,
      hi: row ? row.bss_hi : null,
      cases: row ? row.cases : null,
    };
  });
}

/** The five thresholds at one region and lead: 1, 8, 10, 12 and 50 mm. */
export function thresholdRows(details, region, lead) {
  return (details.thresholds_mm || []).map((threshold) => {
    const row = scoredRow(details, 'all51', region, lead, threshold);
    return {
      threshold_mm: threshold,
      published: (details.published_thresholds_mm || []).some(
        (one) => Math.abs(one - threshold) < 1e-9),
      bss: row ? row.bss : null,
      lo: row ? row.bss_lo : null,
      hi: row ? row.bss_hi : null,
      base_rate: row ? row.base_rate : null,
      cases: row ? row.cases : null,
    };
  });
}

/** Skill in each 30-day block, for one region, lead and threshold. */
export function blockSeries(details, region, lead, threshold) {
  const rows = rowsOf(details.by_date_block).filter(
    (row) => row.region === region && row.lead_day === lead
      && Math.abs(row.threshold_mm - threshold) < 1e-9);
  return rows.sort((a, b) => a.block - b.block).map((row) => ({
    block: row.block,
    from: details.date_blocks[row.block].from,
    to: details.date_blocks[row.block].to,
    dates: details.date_blocks[row.block].dates,
    short: details.date_blocks[row.block].short,
    cases: row.cases,
    bss: row.bss,
  }));
}

/** One 2-degree map: a cell per rectangle, null where there is no number. */
export function mapCells(details, lead, threshold) {
  const map = details.two_degree || {};
  const picture = (map.pictures || {})[`${lead}_${threshold}`] || [];
  return (map.cells || []).map((cell, at) => {
    const values = picture[at];
    return {
      lat: cell[0],
      lon: cell[1],
      squares: cell[2],
      enough: cell[3],
      cases: values ? values[0] : null,
      base_rate: values ? values[1] : null,
      bss: values ? values[2] : null,
    };
  });
}

// The reasons a case can be left out, in words rather than in the keys the
// pipeline files them under. SPEC 5.2 and 5.11 rule 25.
export const WHY_LEFT_OUT = {
  no_imerg_date: 'no satellite file for that day',
  observation_incomplete:
    'under 90 in 100 of the square had a usable observation',
  baseline_too_short:
    'fewer than 20 usable days in the 30 before the run',
};

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

/** "20260513" -> "13 May 2026". The files carry run ids, readers do not. */
export function prettyDate(stamp) {
  const text = String(stamp || '');
  if (!/^\d{8}$/.test(text)) return text;
  return `${Number(text.slice(6, 8))} ${MONTHS[Number(text.slice(4, 6)) - 1]} `
    + text.slice(0, 4);
}

/** The exclusion tally, as lines a reader can read. */
export function exclusions(details) {
  const cases = details.cases || {};
  const lines = [{
    what: 'Brier score',
    possible: cases.possible,
    used: cases.used,
    excluded: cases.excluded_total,
    why: cases.excluded,
  }];
  if (cases.crps) {
    lines.push({
      what: 'CRPS',
      possible: cases.crps.possible,
      used: cases.crps.used,
      excluded: cases.crps.excluded_total,
      why: cases.crps.excluded,
    });
  }
  return lines;
}

/** How many of the 60 groups Brier and CRPS point different ways in. */
export function disagreements(details) {
  const rows = (details.crps || {}).disagreement || [];
  const list = rows.filter((row) => row.disagrees);
  return {
    total: rows.length,
    disagree: list.length,
    one_way: list.filter(
      (row) => !row.brier_above_zero && row.crps_above_zero).length,
    other_way: list.filter(
      (row) => row.brier_above_zero && !row.crps_above_zero).length,
    rows: list,
  };
}
