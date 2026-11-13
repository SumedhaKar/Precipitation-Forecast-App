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
//
// `ink` is what may be written **on** that colour, and two of these were
// wrong until SPEC 11.28 made something read them. White on #1d91c0 is a
// contrast ratio of 3.58, under the 4.5 that WCAG AA asks of text this size,
// and the page's own #1f2933 on it is only 4.12. The dark ink here is
// #111a22, which is 4.91 on #1d91c0 and 7.29 or better on the four lighter
// classes; white stays on the two darkest, where it is 6.49 and 12.29. A
// test checks all seven, so an ink that cannot be read cannot be shipped.
export const CLASSES = [
  { from: 0, to: 0, colour: '#eceff1', label: '0', ink: '#111a22' },
  { from: 1, to: 10, colour: '#c7e9b4', label: '1-10', ink: '#111a22' },
  { from: 11, to: 20, colour: '#7fcdbb', label: '11-20', ink: '#111a22' },
  { from: 21, to: 30, colour: '#41b6c4', label: '21-30', ink: '#111a22' },
  { from: 31, to: 40, colour: '#1d91c0', label: '31-40', ink: '#111a22' },
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

/**
 * The ink to write on a count's own colour.
 *
 * SPEC 11.28. The five-day strip paints each cell its count's colour and
 * wrote the number on it in the page's dark ink, so a day where all 51 runs
 * reach the threshold was a dark navy cell with a near-black "51" on it. The
 * table has carried the right ink per class since 11.17 and nothing was
 * reading it.
 */
export function inkOf(count) {
  const band = classOf(count);
  return band ? band.ink : null;
}

/** "11-20", for the panel to print in words what the map shows in colour. */
export function labelOf(count) {
  const band = classOf(count);
  return band ? band.label : null;
}

// The sea. Not a palette colour, but it has to be told apart from one.
//
// SPEC 11.28. This used to be #eaf0f4, which against the 0 class's #eceff1 is
// a contrast ratio of 1.005: the same colour to any eye. A reader could not
// tell a square where no model run reaches 1 mm from the ocean, which is the
// difference between "the forecast says nothing happens here" and "there is
// no forecast here". #aec6da is 1.53 against the 0 class and 1.77 against the
// white land fill underneath, and it is a desaturated blue-grey, so it does
// not read as one of the saturated blues further up the scale either.
export const SEA = '#aec6da';
export const LAND = '#ffffff';

// The land this site does not forecast. SPEC 11.30.
//
// Everything outside the India outline used to be painted the sea colour,
// because the page drew no land it has no squares for, so Nepal, Bangladesh,
// Myanmar and Pakistan read as ocean. This is the fill for all of it, under
// India's own white, from Natural Earth's coastlines and with no boundary of
// any kind in it.
//
// It has to be told apart from two colours at once, and they are only so far
// apart: the sea's relative luminance is 0.5445 and the 0 class's is 0.8592,
// so a colour between them can be at most 1.237 from both, which is the
// square root of their product. This one is 1.230 against the sea and 1.243
// against the 0 class, as near that limit as makes no difference, and 1.436
// against India's white fill. Lightness alone could not carry it, so it is
// warm against a cool sea and a cool grey class: the hue does the rest.
export const NEIGHBOURS = '#dcd7cb';

// SPEC 11.21, amended twice (11.28). The sentence under the legend and under
// the counts. It first read "These are model-run counts, not probabilities.";
// then "N of 51 model runs, which is not a calibrated probability.", which
// with a real count in it ("1 of 51 model runs, which is not a calibrated
// probability.") is a fragment with no verb. One sentence, no count in it, so
// it cannot be read as a claim about the number beside it.
// SPEC 11.38 amends it once more: "model runs" was one of four names this
// page had for the 51, and the page has one now.
export const NOT_PROBABILITY = `These are counts out of ${MEMBERS} runs, `
  + 'not a calibrated probability.';

export function notProbability() {
  return NOT_PROBABILITY;
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
