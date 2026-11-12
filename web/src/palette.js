// The colour scale and the legend. SPEC 11.17.
//
// This file is the only copy of the table. The map's fill expression, the
// legend swatches and the five-day strip all read it, so a colour on the map
// and a class named in the panel cannot disagree.
//
// It is plain JavaScript with no imports, so `node` can load it and check
// every count from 0 to 51 against the published table (SPEC 11.24), which is
// also what lets HC8 know which hex a square must be painted (SPEC 11.25).
//
// ColorBrewer YlGnBu, which ColorBrewer itself marks colour-blind safe, with
// 0 given its own near-neutral class and 51 its own darkest one. Equal width
// of ten in between, so "two classes darker" means "about twenty more model
// runs" and nothing else. A scale tuned to look interesting would imply that
// the distance between classes says something about likelihood. It does not.

export const MEMBERS = 51;

// Outside India. SPEC 8.4: counts are 0 to 51, so 255 cannot be one.
export const NOT_INDIA = 255;

// In order. `from` and `to` are inclusive.
export const CLASSES = [
  { from: 0, to: 0, colour: '#eceff1', label: '0', ink: '#1f2933' },
  { from: 1, to: 10, colour: '#c7e9b4', label: '1-10', ink: '#1f2933' },
  { from: 11, to: 20, colour: '#7fcdbb', label: '11-20', ink: '#1f2933' },
  { from: 21, to: 30, colour: '#41b6c4', label: '21-30', ink: '#1f2933' },
  { from: 31, to: 40, colour: '#1d91c0', label: '31-40', ink: '#ffffff' },
  { from: 41, to: 50, colour: '#225ea8', label: '41-50', ink: '#ffffff' },
  { from: 51, to: 51, colour: '#0c2c84', label: '51', ink: '#ffffff' },
];

/** The class a count falls in, or null for anything that is not a count. */
export function classOf(count) {
  if (!Number.isInteger(count)) return null;
  if (count < 0 || count > MEMBERS) return null;
  return CLASSES.find((band) => count >= band.from && count <= band.to)
    || null;
}

/** The fill for a count, or null where nothing should be drawn. */
export function colourOf(count) {
  const band = classOf(count);
  return band ? band.colour : null;
}

/** "11-20", for the panel to print in words what the map shows in colour. */
export function labelOf(count) {
  const band = classOf(count);
  return band ? band.label : null;
}

// SPEC 11.21. The sentence that goes under the legend and under the counts.
// `N` is the word when no count is in hand, and the number when one is.
export function notProbability(count) {
  const n = Number.isInteger(count) ? count : 'N';
  return `${n} of ${MEMBERS} model runs, which is not a calibrated `
    + 'probability.';
}

/**
 * A MapLibre `step` expression for one day and threshold.
 *
 * Switching day or threshold calls setPaintProperty with this, over a
 * different property key, which repaints without touching the source
 * (SPEC 11.16). Squares outside India have no feature at all, so there is no
 * 255 case here: the expression never sees one.
 */
export function fillExpression(key) {
  const steps = ['step', ['get', key], CLASSES[0].colour];
  for (const band of CLASSES.slice(1)) {
    steps.push(band.from, band.colour);
  }
  return steps;
}

/** The feature property holding one day and threshold: "ge10_d3". */
export function countKey(threshold, day) {
  return `ge${threshold}_d${day}`;
}
