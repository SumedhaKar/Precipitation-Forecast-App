// What the colours mean. SPEC 11.17, moved by 11.28.
//
// It used to float on the map, bottom right, where it covered the Bay of
// Bengal and the Andaman Islands — which have three forecast squares of their
// own. Anything drawn on top of the map has to be paid for twice: once in the
// country it hides, and again in the fit, because leaving room for a box 237
// pixels tall shrinks India by a fifth.
//
// So it is in the bar with the day and threshold buttons instead, beside the
// control that chooses which threshold it is describing. Nothing is drawn
// over the country now except MapLibre's own zoom buttons.
//
// It is a module of its own rather than part of Map.jsx so that it is in the
// first chunk: the legend paints with the controls, before MapLibre's 325 KB
// has arrived (SPEC 11.16).

import { CLASSES, MEMBERS, NEIGHBOURS } from './palette';

/**
 * The two ends said in words. SPEC 11.38.
 *
 * "0" and "51" are the counts and they are right, and at the end of a
 * colour ramp a bare 0 reads as "nothing here" rather than as "no run
 * reaches this amount". The seven classes and their colours are the
 * palette's own and are not touched; only the two end labels are written
 * out. No band word of 11.38 is ever drawn here: beside a colour, "a few"
 * would read as a name for what that colour means on the ground, which is
 * a forecast this site does not make.
 */
export function endLabel(band, index, last) {
  if (index === 0) return 'None';
  if (index === last) return `All ${MEMBERS}`;
  return band.label;
}

export default function Legend({ threshold }) {
  const last = CLASSES.length - 1;
  return (
    <div className="legend group" aria-label="What the colours mean">
      <span className="grouplabel">
        Runs bringing <strong>{threshold} mm or more</strong>, out of
        {' '}{MEMBERS}
      </span>
      <ul className="legend-rows">
        {CLASSES.map((band, index) => (
          <li key={band.label}>
            <span
              className="swatch"
              aria-hidden="true"
              style={{ background: band.colour }}
            />
            {endLabel(band, index, last)}
          </li>
        ))}
      </ul>
      {/* SPEC 11.30. Some squares inside the outline are white: they are
          inside India and not forecast, because the model's own land
          fraction for them is under the half SPEC 3.5 asks for. Without
          this line they are a hole in the map with no explanation. */}
      <p className="legend-white">
        <span className="swatch" aria-hidden="true" />
        White: no forecast for this spot
      </p>
      {/* SPEC 11.38. The beige had no entry at all, so a reader who tapped
          Nepal got a red error about a colour the page had never named. */}
      <p className="legend-white legend-around">
        <span
          className="swatch"
          aria-hidden="true"
          style={{ background: NEIGHBOURS }}
        />
        Land outside India, which this site does not forecast
      </p>
    </div>
  );
}
