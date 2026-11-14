// How to read this map. SPEC 11.39.
//
// It used to be a block inside the forecast panel, and on a phone that is
// where every help sentence on the site had collected: three bullets in the
// panel, a line under the day buttons, a line under the amount buttons, a
// line under the five-day strip, a line under the legend and two more under
// the dots. A reader who wanted the forecast had to read past all of it, and
// a reader who wanted the explanation had to open a drawer to find it.
//
// So it is a page. The forecast page keeps one explanatory line -- the one
// under the place name, which says which day and how much rain -- and
// everything else that explains the map is here, where it can be linked to:
// from the menu, and from "What does mm mean?" under the amount buttons,
// which lands on the amounts below.
//
// It is a document page like the report card and How we checked: a column of
// text that scrolls, lazily loaded, so none of this is in the forecast's
// download.

import { CLASSES, MEMBERS, NEIGHBOURS, notProbability } from './palette';
import { AMOUNTS, STARTS_TOMORROW } from './Controls';
import { KeyRows } from './Legend';

/**
 * This site's own words for the three amounts. SPEC 11.39.
 *
 * Everyday English, written down here and in the specification and nowhere
 * else. They are nobody's official categories -- in particular not IMD's,
 * whose "heavy rain" names a band this site does not measure -- and the
 * millimetres are beside every one of them, always.
 *
 * The first of them was "enough to wet the ground" in the brief and could
 * not be: "wet" is on the forbidden list of 11.20, which is there because
 * "a wet day" is a forecast of what the day will be like and this site does
 * not make one. "Damp" says the same thing about the ground and claims
 * nothing about the day.
 */
export const AMOUNT_WORDS = {
  1: 'Enough to leave the ground damp.',
  10: 'A proper shower: you would want an umbrella.',
  50: 'A very rainy day: water can collect on roads.',
};

export default function HowToRead() {
  return (
    <article className="page howtoread">
      <h1>How to read this map</h1>
      <p className="lead">
        A few ideas, and then what every colour on the map means.
      </p>

      <h2>One square</h2>
      <p>
        One square is 0.25 degrees, about 28 km across. The forecast has no
        detail finer than that, so a square is the smallest place this site
        can answer about. A square is named after the city in it where there
        is one, and called &ldquo;near&rdquo; that city when the city is
        within 50 km.
      </p>

      <h2>One day</h2>
      <p>
        Each day runs from 5:30 am to 5:30 am the next morning, IST. That is
        the window the model publishes, so it is the window this site adds
        up; it is not the calendar day, and the five days are these five
        windows.
      </p>

      <h2>The mornings when the five days start tomorrow</h2>
      <p>
        The run is the 00 UTC one, and it has to be downloaded, added up and
        published before this site can show it, which happens around midday
        IST. Until it arrives, the newest run here is the one whose first day
        begins tomorrow morning at 5:30 — so the first day button reads
        &ldquo;Tomorrow&rdquo;, and the day you are in is not one of the
        five. The page says so beside the question when it happens:{' '}
        <em>{STARTS_TOMORROW}</em>
      </p>

      <h2 id="amounts">How much rain</h2>
      <ul className="amountwords">
        {AMOUNTS.map((amount) => (
          <li key={amount.mm}>
            <strong>{amount.nickname}</strong>
            <span className="mmtag">{amount.mm} mm or more</span>
            <span className="meaning">{AMOUNT_WORDS[amount.mm]}</span>
          </li>
        ))}
      </ul>
      <p>
        Those are our own everyday words and not an official category. The
        millimetres are the rule; the words are only there to make a number
        mean something.
      </p>
      <p>
        This is the total over the whole day, averaged over the square, so it
        can be one short burst or hours of drizzle.
      </p>

      <h2>The colours</h2>
      <p>
        The model is run {MEMBERS} times from slightly different starting
        points. A square&apos;s colour is how many of those {MEMBERS} runs
        bring at least the chosen amount of rain in the chosen day. Darker is
        more runs.
      </p>
      <KeyRows />
      <p>
        The two ends are their own colours: a square no run reaches, and a
        square every run reaches. The {CLASSES.length - 2} between them are
        ten runs wide each, so two classes darker means about twenty more
        runs and nothing else.
      </p>

      <h2>What it is not</h2>
      <p>
        It is not a probability. {notProbability()} Nothing on this site is
        calibrated against what actually happened until the track record
        exists, and the record is{' '}
        <a href="/report-card">published in full</a>.
      </p>
      <p className="small">
        The land outside India is drawn in one quiet colour
        (<span className="inlineswatch" aria-hidden="true"
          style={{ background: NEIGHBOURS }} />) because this site has no
        squares for it. It is not a forecast of no rain there; it is the
        edge of what is forecast at all.
      </p>
    </article>
  );
}
