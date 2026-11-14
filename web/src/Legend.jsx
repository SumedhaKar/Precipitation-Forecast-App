// What the colours mean. SPEC 11.17, moved by 11.28, remade by 11.39.
//
// Three homes in three batches, and each move was paid for by something
// measured. It began floating over the map, bottom right, where it covered
// the Bay of Bengal and the three forecast squares of the Andaman Islands,
// and where leaving room for a box 237 pixels tall shrank India by a fifth.
// 11.28 moved it into the bar with the day and amount buttons, where it was
// honest and cost nothing of the map — and where, as seven numbered classes
// plus two colour lines, it was the largest single block of the controls and
// the thing that pushed the map down a phone.
//
// 11.39 makes it a key again, on the map and over the sea, and small: shut
// it is a title and a strip of the seven colours, and opened it is nine
// plain rows. The room it needs on the map is paid for by padding the fit on
// the side it sits on, which costs nothing where the map box is wider than
// India needs; where it cannot be paid for — a phone, where India fills the
// width — the key sits directly under the map instead.
//
// It is a module of its own rather than part of Map.jsx so that it is in the
// first chunk: the key paints with the controls, before MapLibre's 325 KB
// has arrived (SPEC 11.16).

import { CLASSES, MEMBERS, NEIGHBOURS } from './palette';

/**
 * The nine rows of the colour key, in plain words. SPEC 11.39.
 *
 * Seven colours and two more things a reader can see on the map: the white
 * squares inside India that are not forecast, and the land outside it. They
 * were a strip of bare numbers with "0" at one end and "51" at the other,
 * plus two lines that were hidden on a phone for want of room.
 *
 * Every row says "runs", which is the page's one name for the 51 (11.38),
 * and no row carries a band word: beside a colour, "a few" would read as a
 * name for what that colour means on the ground.
 */
export function rowLabel(band, index, last) {
  if (index === 0) return 'None';
  if (index === last) return `All ${MEMBERS} runs`;
  return `${band.label} runs`;
}

export function KeyRows() {
  const last = CLASSES.length - 1;
  return (
    <ul className="keyrows">
      {CLASSES.map((band, index) => (
        <li key={band.label}>
          <span
            className="swatch"
            aria-hidden="true"
            style={{ background: band.colour }}
          />
          {rowLabel(band, index, last)}
        </li>
      ))}
      {/* SPEC 11.30. Some squares inside the outline are white: they are
          inside India and not forecast, because the model's own land
          fraction for them is under the half SPEC 3.5 asks for. */}
      <li className="keywhite">
        <span className="swatch" aria-hidden="true" />
        White: no forecast for this spot
      </li>
      {/* SPEC 11.38. The beige had no entry at all, so a reader who tapped
          Nepal got a red error about a colour the page had never named. */}
      <li>
        <span
          className="swatch"
          aria-hidden="true"
          style={{ background: NEIGHBOURS }}
        />
        Beige: land outside India, not forecast
      </li>
    </ul>
  );
}

/** The title, which is a question, and the strip of the seven colours. */
export const KEY_TITLE = `How many of the ${MEMBERS} runs bring rain?`;

/**
 * The key, on the map. SPEC 11.39.
 *
 * A real <details>, so it opens with no script of ours, the keyboard
 * reaches it, and a screen reader is told whether it is open. `open` is
 * controlled -- expanded on a desktop and shut on a phone, which is where
 * the map has no room to spare -- and `onToggle` hands the reader's own
 * click back, because the fit is padded by this box's width and has to be
 * done again when the box changes size.
 *
 * The title is a question and does not name the amount; the summary's
 * accessible name does, because the amount is what the colours are counts
 * of and a reader using a screen reader cannot see the chosen pill.
 */
export default function MapKey({ threshold, open, onToggle }) {
  const last = CLASSES.length - 1;
  return (
    <details className="mapkey" open={open} onToggle={onToggle}>
      <summary
        aria-label={`${KEY_TITLE} At ${threshold} mm or more. `
          + 'The colours, in words.'}
      >
        <span className="keytitle">{KEY_TITLE}</span>
        <span className="ministrip" aria-hidden="true">
          {CLASSES.map((band) => (
            <span key={band.label} style={{ background: band.colour }} />
          ))}
        </span>
        <span className="keyends" aria-hidden="true">
          <span>None</span>
          <span>All {MEMBERS}</span>
        </span>
      </summary>
      <KeyRows />
    </details>
  );
}
