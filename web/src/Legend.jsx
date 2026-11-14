// What the colours mean. SPEC 11.17, moved by 11.28, 11.39 and 11.40.
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
// 11.39 made it a key again, small: shut it is a title and a strip of the
// seven colours, and opened it is nine plain rows. It floated in the map's
// lower left corner over the Arabian Sea at 1280 pixels and over, paid for
// by padding the fit on that side, and sat under the map at every width
// where that padding would have cost the country anything.
//
// 11.40 takes it off the map everywhere. Nothing is drawn over the canvas
// now but MapLibre's own zoom buttons: on a desktop the key is the top of
// the right-hand panel, above the card and always on the screen, and on a
// phone it is directly under the map as it was. So nothing of the fit is
// spent on it, which is the width the whole country was competing for.
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
 * The three places on the strip that are worth a word. SPEC 11.40.
 *
 * The shut strip named its two ends. The middle of a scale of counts is
 * the one other place a reader looks, and "About half" is a position on
 * the strip rather than a word for what a colour means on the ground --
 * which is why no row of the open key carries a band word (11.39).
 */
export const KEY_ENDS = ['None', 'About half', `All ${MEMBERS}`];

/**
 * The key. SPEC 11.39, moved off the map by 11.40.
 *
 * A real <details>, shut, with nothing controlling it: it opens with no
 * script of ours, the keyboard reaches it, a screen reader is told
 * whether it is open, and one tap either way is the whole of it. It was
 * controlled while it floated over the canvas -- open on a desktop, shut
 * on a phone, with the map refitting around it -- and off the map there
 * is nothing for the page to know about it.
 *
 * The title names the amount, because the colours are counts of
 * something and the chosen pill is a row of controls away; the strip's
 * three words are its two ends and its middle.
 */
export default function MapKey({ threshold }) {
  return (
    <details className="mapkey">
      <summary
        aria-label={`${KEY_TITLE} At ${threshold} mm or more. `
          + 'The colours, in words.'}
      >
        <span className="keytitle">
          {KEY_TITLE} ({threshold} mm+)
        </span>
        <span className="ministrip" aria-hidden="true">
          {CLASSES.map((band) => (
            <span key={band.label} style={{ background: band.colour }} />
          ))}
        </span>
        <span className="keyends" aria-hidden="true">
          {KEY_ENDS.map((word) => <span key={word}>{word}</span>)}
        </span>
      </summary>
      <KeyRows />
    </details>
  );
}
