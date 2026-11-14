// How to read this map. SPEC 11.39, rewritten by 11.41.
//
// It used to be a block inside the forecast panel, and on a phone that is
// where every help sentence on the site had collected: three bullets in the
// panel, a line under the day buttons, a line under the amount buttons, a
// line under the five-day strip, a line under the legend and two more under
// the dots. A reader who wanted the forecast had to read past all of it, and
// a reader who wanted the explanation had to open a drawer to find it.
//
// So it is a page. But as a page it was still written in the order the
// specification is written in -- one square, one day, the mornings when the
// days start tomorrow, the amounts, the colours, what it is not -- which is
// the order somebody who already understands the site would choose. The
// people who tested the site were not that reader. What they said, every
// one of them, was that they could not see where to start.
//
// So it is written for them now, in the order they asked their questions:
// what the colours mean, what the 51 are, what a millimetre is worth, what
// to tap, and that the colours are safe to read. Six short answers, then a
// line telling anybody who is satisfied that they can stop, and then one
// shut section with everything a reader has to want before it helps them:
// the size of a square, where a day begins and ends, why the first day is
// usually tomorrow, what a daily total does not say, the nine colour
// classes in full, and that a count of runs is not a promise of rain.
//
// Nothing technical is written outside that section -- not UTC, not a lead
// day, not a grid, not calibration -- and a test splits the rendered page
// at the section and reads the half above it to prove so.
//
// It is a document page like the report card and How we checked: a column of
// text that scrolls, lazily loaded, so none of this is in the forecast's
// download.

import {
  CLASSES, GUESSES, MEMBERS, NEIGHBOURS, notProbability,
} from './palette';
import {
  AmountGuide, AmountWords, STARTS_TOMORROW, WHOLE_DAY,
} from './Controls';
import { KeyRows } from './Legend';

/* SPEC 11.41. The three steps a reader follows, which README.md gives as
   the same three in the same words: the repository's own "how to use it"
   and this page may not describe two different sites. */
export const MANUAL = [
  'Search your city, or just tap the map.',
  'Pick the day and the amount of rain you care about.',
  "That's it, your forecast shows up.",
];

/* SPEC 11.41. The line between the six answers and the fine print. A
   reader who is happy is told so in as many words, because a page that
   goes on for another screen and a half reads like a page a reader has
   not finished. */
export const STOP_HERE = "Don't like technical stuff? Stop reading here. "
  + 'Nerdy birdies, read on!';

export default function HowToRead() {
  return (
    <article className="page howtoread">
      <h1>Hello, first-time visitor!</h1>
      <p className="lead">
        This site works a little differently from other weather apps, so
        here are a few quick points to get you going.
      </p>

      <h2>The colours, in one line</h2>
      <p>
        Darker means more of our {MEMBERS} weather runs bring rain there.
      </p>

      <h2>What are the {MEMBERS} runs?</h2>
      <p>
        The same weather model, run {MEMBERS} times from slightly different
        starts: {MEMBERS} slightly different guesses.
      </p>

      <h2>The mm guide</h2>
      {/* SPEC 11.41. The same three amounts the forecast page asks about,
          in the plainest words the site has: the millimetres are written
          out as "1 mm or more" here rather than "1 mm+", because this is
          the page for somebody who has not met the pills yet. The four
          lines "What does mm mean?" opens under the pills are the same
          three facts in the pills' own shorthand, and both come off the
          one table of amounts in Controls.jsx. */}
      <AmountGuide />

      <h2>Your mini user manual</h2>
      <ol className="manual">
        {MANUAL.map((step) => <li key={step}>{step}</li>)}
      </ol>

      <h2>No worries if you are colour-blind</h2>
      <p>
        The map uses a colour-blind-friendly scale. If you&apos;re ever
        unsure about a shade, tap the square and you&apos;ll get the
        number.
      </p>

      <p className="stophere">{STOP_HERE}</p>

      {/* SPEC 11.41. One shut section, and everything technical on this
          page is inside it. It is shut rather than absent because none of
          it is optional to the site's honesty -- what a square cannot
          tell you, what a daily total does not say, and that a count of
          runs is not a promise -- and a reader who wants any of it can
          find all of it in one place. */}
      <details className="fineprint">
        <summary>The fine print</summary>

        <h3>One square</h3>
        <p>
          One square is 0.25 degrees, about 28 km across. The forecast has
          no detail finer than that, so a square is the smallest place this
          site can answer about and nothing here is street level. A square
          is named after the city in it where there is one, and called{' '}
          &ldquo;near&rdquo; that city when the city is within 50 km.
        </p>

        <h3>One day</h3>
        <p>
          Each day runs from 5:30 am to 5:30 am the next morning, IST. That
          is the window the model publishes, so it is the window this site
          adds up; it is not the calendar day, and the five days are these
          five windows.
        </p>

        <h3>Why the days start tomorrow</h3>
        <p>
          The run is the 00 UTC one, and it has to be downloaded, added up
          and published before this site can show it, which happens around
          midday IST. Until it arrives, the newest run here is the one
          whose first day begins tomorrow morning at 5:30 — so the first
          day button reads &ldquo;Tomorrow&rdquo;, and the day you are in
          is not one of the five. The page says so beside the question when
          it happens: <em>{STARTS_TOMORROW}</em>
        </p>

        <h3>How much rain</h3>
        <p>
          {WHOLE_DAY} A whole day&apos;s total can be one short burst or
          hours of drizzle: the number does not say which.
        </p>
        <p>
          Those three names are our own everyday words and
          not an official category. The millimetres are the rule; the
          words are only there to make a number mean something. Under the
          amount buttons on the forecast page, the same three read:
        </p>
        <AmountWords />

        <h3>The colours in full</h3>
        {/* SPEC 11.40: the same sentence the empty card and the dots use. */}
        <p>
          {GUESSES} A square&apos;s colour is how many of those {MEMBERS}{' '}
          runs bring at least the chosen amount of rain in the chosen day.
          Darker is more runs.
        </p>
        <KeyRows />
        <p>
          The two ends are their own colours: a square no run reaches, and
          a square every run reaches. The {CLASSES.length - 2} between them
          are ten runs wide each, so two classes darker means about twenty
          more runs and nothing else.
        </p>
        <p className="small">
          The land outside India is drawn in one quiet colour
          (<span className="inlineswatch" aria-hidden="true"
            style={{ background: NEIGHBOURS }} />) because this site has no
          squares for it. It is not a forecast of no rain there; it is the
          edge of what is forecast at all.
        </p>

        <h3>A count of runs, not a promise of rain</h3>
        <p>
          It is not a probability. {notProbability()} Nothing on this site
          is calibrated against what actually happened until the track
          record exists, and the record is{' '}
          <a href="/report-card">published in full</a>.
        </p>
        <p>
          The method behind that record — what was checked, against what,
          and by which rules — is on{' '}
          <a href="/how-we-checked">How we checked</a>, which is written
          for experts.
        </p>
      </details>
    </article>
  );
}
