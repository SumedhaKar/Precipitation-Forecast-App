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

import { CLASSES, notProbability } from './palette';

export default function Legend({ threshold }) {
  return (
    <div className="legend group" aria-label="What the colours mean">
      <span className="grouplabel">
        <strong>N of 51 model runs</strong> reach {threshold} mm
      </span>
      <ul className="legend-rows">
        {CLASSES.map((band) => (
          <li key={band.label}>
            <span
              className="swatch"
              aria-hidden="true"
              style={{ background: band.colour }}
            />
            {band.label}
          </li>
        ))}
      </ul>
      {/* SPEC 11.30. Some squares inside the outline are white: they are
          inside India and not forecast, because the model's own land
          fraction for them is under the half SPEC 3.5 asks for. Without
          this line they are a hole in the map with no explanation. */}
      <p className="legend-white">
        <span className="swatch" aria-hidden="true" />
        White: inside India but not forecast at this grid size
      </p>
      <p className="legend-foot">{notProbability()}</p>
    </div>
  );
}
