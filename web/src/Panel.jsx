// The place panel. SPEC 11.20 and 11.28.
//
// Everything the map shows for the chosen square is written here in words and
// numbers, because a canvas is not readable: no information on this site is
// available only by clicking the map (SPEC 11.22).
//
// Every number here was published. The counts and the dots are the tiles' own
// (SPEC 8.4), the member values are whole millimetres rounded down, which
// api/place computed from the published integers, and the one sentence a day
// is built by api/place from that day's three counts and nothing else.

import { Fragment, useState } from 'react';

import { colourOf, inkOf, labelOf, notProbability } from './palette';
import { squareText } from './snap';
import { placeName } from './places';
import { sameSquare } from './answers';
import { trustFor } from './trust';
import { PICK_A_PLACE, headline } from './record';
import { plainClick } from './TopNav';
import { AMOUNTS } from './Controls';
import { dayButton, dayName, istToday } from './days';

// SPEC 4.3, in the order the store publishes them. The same colour family as
// the map's legend, so the page has one visual language.
const DOT_COLOURS = ['#eceff1', '#a1dab4', '#41b6c4', '#225ea8'];

const THRESHOLDS = [1, 10, 50];

/** "under 1 mm" -> "Under 1 mm". The names are the store's, not ours. */
function sentenceCase(text) {
  const name = String(text || '');
  return name ? name[0].toUpperCase() + name.slice(1) : name;
}

function summarise(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    lowest: sorted[0],
    middle: sorted[Math.floor(sorted.length / 2)],
    highest: sorted[sorted.length - 1],
    same: sorted[0] === sorted[sorted.length - 1],
  };
}

/* SPEC 11.37. The one line the closed bar carries on a phone, in the words
   the panel itself uses: the place, the count, the amount. Pure, and
   exported, so a test can drive it against a real answer.

   `square` is what the reader last asked for. While a newer square is still
   loading the bar says the prompt rather than the old square's number,
   because a number under the wrong place name is the worst thing this page
   could do (SPEC 11.30). */
export function summaryLine(place, square, day, threshold) {
  if (square && place && place.square
    && !sameSquare(place.square.asked, square)) return PICK_A_PLACE;
  return headlineFor(place, day, threshold) || PICK_A_PLACE;
}

/**
 * The headline for the chosen day and amount, or null. SPEC 11.38.
 *
 * One function for the bar and for the top of the panel, so the two cannot
 * say different things about the same square. Pure, and exported, so a test
 * can drive it against a real answer.
 */
export function headlineFor(place, day, threshold, today) {
  if (!place || !place.square || !place.days) return null;
  const chosen = place.days.find((entry) => entry.lead_day === day)
    || place.days[0];
  const k = THRESHOLDS.indexOf(threshold);
  const entry = chosen && chosen.counts_by_threshold
    && chosen.counts_by_threshold[k];
  if (!entry) return null;
  const where = place.square;
  // SPEC 11.38, one name per thing: the day is called what the button
  // above the map calls it. "Today" on the button and "Sat 14 Nov" in the
  // sentence under it are two names for one day.
  const when = dayName(chosen.from_ist, today || istToday(),
    chosen.short_ist);
  return headline(placeName(where.lat, where.lon), when, entry.count,
    place.members, threshold);
}

/**
 * A link to the report card. SPEC 11.38.
 *
 * A plain <a href>, so a middle click opens a tab and the keyboard reaches
 * it with no handler of ours; a plain left click becomes the pushState the
 * menu uses, where the page has one to offer. With no `onGo` -- which is
 * what the server renderer and the tests have -- it is simply a link, and
 * the path it points at is a real page either way (SPEC 11.34).
 */
export function ReportCardLink({ onGo, children }) {
  return (
    <a
      href="/report-card"
      onClick={(event) => {
        if (!onGo || !plainClick(event)) return;
        event.preventDefault();
        onGo('/report-card');
      }}
    >
      {children}
    </a>
  );
}

/** The headline, at the top of the panel, under the place name. */
export function Headline({ place, day, threshold, today }) {
  const said = headlineFor(place, day, threshold, today);
  if (!said) return null;
  return <p className="headline">{said}</p>;
}

/**
 * The place name, and the coordinates under it. SPEC 11.38.
 *
 * The name is first and bold; the square's own centre is the small line
 * beneath. The first build had it the other way round -- "23.25 N 77.50 E"
 * in the heading with the city after it -- which is the order a grid
 * reference is written in and not the order a person reads one.
 *
 * "Your location" stays what a location is called (SPEC 11.28): the reader
 * knows where they are, and the square is on the line below.
 */
export function PlaceLine({ place, from }) {
  const where = place.square;
  const name = from === 'location' ? 'Your location'
    : placeName(where.lat, where.lon);
  return (
    <div className="placeline" aria-live="polite">
      <h2>{name}</h2>
      <p className="atsquare">{squareText(where.lat, where.lon)}</p>
      {/* SPEC 11.28: a location is reported as its square and nothing
          finer, and the name appears only because that square is exactly
          that town's square. */}
      {from === 'location' ? (
        <p className="small">
          Your exact position was not sent anywhere.
        </p>
      ) : null}
      {where.moved ? (
        <p className="moved">
          {squareText(where.moved.from.lat, where.moved.from.lon)} is sea on
          this 0.25 degree grid. Showing{' '}
          {squareText(where.moved.to.lat, where.moved.to.lon)}, the nearest
          land square, one square away.
        </p>
      ) : null}
    </div>
  );
}

export function DayStrip({ place, day, threshold, onDay, today }) {
  const k = THRESHOLDS.indexOf(threshold);
  const now = today || istToday();
  return (
    <div className="strip">
      <h3>The next five days</h3>
      <ol>
        {place.days.map((entry) => {
          const count = entry.counts_by_threshold[k].count;
          const chosen = entry.lead_day === day;
          return (
            <li key={entry.lead_day}>
              <button
                type="button"
                className={chosen ? 'cell chosen' : 'cell'}
                style={{ background: colourOf(count), color: inkOf(count) }}
                aria-pressed={chosen}
                aria-label={`${entry.short_ist} IST: ${count} of `
                  + `${place.members} runs bring ${threshold} mm or more`}
                onClick={() => onDay(entry.lead_day)}
              >
                <span className="cellday">
                  {dayButton(entry.from_ist, now, entry.short_ist)}
                </span>
                <span className="cellcount">{count}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="small">
        Each cell is that day&apos;s count of runs at {threshold} mm, in the
        same colours as the map. Dates are IST. Choose one to change the day.
      </p>
    </div>
  );
}

/* SPEC 11.38. The day sentence of 11.20 used to be here, under the place
   name. It says "model runs", it is pinned word for word by its own test,
   and the page now has one name for the 51 -- so it is taken off the page
   rather than reworded. `api/place` still computes it and still publishes
   it, so 11.20 is unchanged for anyone reading the API; what a reader is
   given is the headline above, which says the same thing in the page's own
   language and carries the band word with it. */

/**
 * The trust label for one region, lead day and threshold. SPEC 11.33.
 *
 * The word and the colour are both read from the frozen record. There is no
 * rule here that turns a number into a colour: `pipeline/labels.py` decided
 * that before any of these numbers were looked at (SPEC 6.8).
 */
export function Chip({ trust, small }) {
  return (
    <span className={`chip ${trust.colour}${small ? ' tiny' : ''}`}>
      {trust.label}
    </span>
  );
}

/**
 * What the record says about the chosen day and threshold. SPEC 11.33.
 *
 * One chip, one line saying which of the four checks it did not pass, and
 * everything behind it a reader could want in order to disagree with us.
 * `trust` is null only where there is no region, which is to say nowhere the
 * site can answer for at all.
 */
export function TrustBlock({ place, day, threshold, onGo }) {
  const k = THRESHOLDS.indexOf(threshold);
  const count = day.counts_by_threshold[k].count;
  const trust = trustFor(place.square.region, day.lead_day, threshold, count,
    place.members);
  if (!trust) return null;
  return (
    <div className="trust">
      <p className="trustline">
        <Chip trust={trust} /> {trust.reason}
      </p>
      {/* SPEC 11.38: the one unambiguously good thing the record can say,
          said only where the check it rests on passed. */}
      {trust.better ? (
        <p className="betterline">
          {trust.better}{' '}
          <ReportCardLink onGo={onGo}>See the record</ReportCardLink>
        </p>
      ) : null}
      <details className="whylabel">
        <summary>Why this label?</summary>
        {/* SPEC 11.38. Which of the four checks went wrong used to be the
            line under the chip. It is a sentence about our method rather
            than about this square, so it is the first thing inside the
            disclosure instead of the first thing a reader meets. */}
        <p className="whyline">{trust.why}</p>
        <ul className="conds">
          {trust.conditions.map((condition) => (
            <li key={condition.name} className={condition.pass ? 'met' : 'no'}>
              <span className="condname">
                {condition.name}:{' '}
                <strong>{condition.pass ? 'passed' : 'not passed'}</strong>
              </span>
              <span className="condgot">{condition.got}</span>
              <span className="condrule">
                The rule asks for {condition.rule}.
              </span>
            </li>
          ))}
        </ul>
        <dl className="trustnotes">
          {trust.notes.map((note) => (
            <Fragment key={note.what}>
              <dt>{note.what}</dt>
              <dd>{note.says}</dd>
            </Fragment>
          ))}
        </dl>
      </details>
    </div>
  );
}

/**
 * The three counts for the chosen day, each row a way of choosing it.
 *
 * SPEC 11.28. These were a table, and the chosen row was shaded, so the rows
 * looked like the control they were not. They are a radio group now: the same
 * three choices as the buttons over the map, kept in step with them because
 * both read and set the one `threshold` the page holds.
 */
export function Counts({ place, day, threshold, onThreshold }) {
  return (
    <div className="counts">
      <h3 id="countshead">
        {day.short_ist}: {day.label} IST
      </h3>
      <ul className="countrows" role="radiogroup" aria-labelledby="countshead">
        {THRESHOLDS.map((amount, k) => {
          const count = day.counts_by_threshold[k].count;
          const chosen = amount === threshold;
          return (
            <li key={amount}>
              <button
                type="button"
                role="radio"
                aria-checked={chosen}
                className={chosen ? 'countrow on' : 'countrow'}
                onClick={() => onThreshold(amount)}
              >
                <span className="rowwhat">{amount} mm or more</span>
                <span className="rowcount">
                  <strong>{count}</strong> of {place.members} runs
                </span>
                <span className="rowband">
                  <span
                    className="swatch"
                    aria-hidden="true"
                    style={{ background: colourOf(count) }}
                  />
                  {labelOf(count)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function Dots({ place, day }) {
  const categories = place.dot_categories || [];
  const dots = [];
  day.dots.forEach((howMany, category) => {
    for (let n = 0; n < howMany; n += 1) dots.push(category);
  });
  return (
    <div className="dots">
      <h3>The 51 runs, one dot each</h3>
      <ol className="dotgrid">
        {dots.map((category, index) => (
          // eslint-disable-next-line react/no-array-index-key
          <li key={index} style={{ background: DOT_COLOURS[category] }} />
        ))}
      </ol>
      <ul className="dotkey">
        {categories.map((name, category) => (
          <li key={name}>
            <span
              className="swatch"
              aria-hidden="true"
              style={{ background: DOT_COLOURS[category] }}
            />
            {sentenceCase(name)}: {day.dots[category]}
          </li>
        ))}
      </ul>
      {/* SPEC 11.38. One line saying what a dot is. The grid of 51 squares
          was drawn with no sentence to read it by, so a reader who did not
          already know what an ensemble was met 51 coloured boxes. */}
      <p className="small">
        Each dot is one run; its colour shows how much rain it brings that
        day.
      </p>
    </div>
  );
}

/**
 * What each of the 51 runs gives, in whole millimetres.
 *
 * SPEC 11.28. A grid of 51 numbers that are all the same number says nothing
 * a sentence cannot, and in a dry week every square showed one, so the grid
 * is behind a button and the line in front of it is the shape of the spread.
 * The numbers are never summarised away: the button is always there.
 */
export function MemberValues({ day }) {
  const [open, setOpen] = useState(false);
  const spread = summarise(day.members_mm);
  const count = day.members_mm.length;
  return (
    <div className="members">
      <h3>What each run gives, in whole millimetres</h3>
      {spread.same ? (
        <p className="spread">
          All {count} runs: {spread.lowest} mm
          {spread.lowest === 0 ? ', which means under 1 mm' : null}
        </p>
      ) : (
        <p className="spread">
          lowest {spread.lowest} mm, middle {spread.middle} mm, highest{' '}
          {spread.highest} mm
        </p>
      )}
      <button
        type="button"
        className="reveal"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {open ? `Hide the ${count} values` : `Show all ${count} values`}
      </button>
      {open ? (
        <>
          <ol className="values">
            {day.members_mm.map((value, index) => (
              // eslint-disable-next-line react/no-array-index-key
              <li key={index} className={index === 0 ? 'control' : undefined}>
                <span className="who">{index === 0 ? 'control' : index}</span>
                <span className="mm">{value}</span>
              </li>
            ))}
          </ol>
          <p className="small">
            The control run first, then the 50 perturbed runs, in the order the
            model publishes them. Rounded down, so 9.9 mm shows as 9 and{' '}
            <strong>0 mm means under 1 mm</strong>.
          </p>
        </>
      ) : (
        <p className="small">
          Rounded down, so 9.9 mm shows as 9 and{' '}
          <strong>0 mm means under 1 mm</strong>.
        </p>
      )}
    </div>
  );
}

export function SquareUsed({ place }) {
  const where = place.square;
  return (
    <p className="arith">
      Square i = {where.i}, j = {where.j}, tile {where.tile}. Asked for{' '}
      {squareText(where.asked.lat, where.asked.lon)}.
    </p>
  );
}

/**
 * Which run this is, to the second and by its own name. SPEC 11.38.
 *
 * The header's run line is three facts in two sizes of grey, and on a phone
 * it was two of the lines that pushed the map under the fold. A reader who
 * wants the run ID and the UTC stamp wants them exactly; a reader who does
 * not wants one line saying how old this is, which is what the header now
 * carries. So these are in here.
 */
export function RunDetail({ run }) {
  if (!run) return null;
  return (
    <p className="arith">
      Run {run.run_id}, the 00 UTC run of {run.run_time_utc}.
      {run.publish_time_ist
        ? ` Published ${run.publish_time_ist} IST.` : null}
    </p>
  );
}

/**
 * Everything a reader can choose to open. SPEC 11.38.
 *
 * Three reviews called this page too textual, and the count of sentences
 * was most of why. Nothing is deleted: the 51 values, the square's own
 * arithmetic, the run's name and time, and the long form of the track
 * record are all here, in one place, shut until they are asked for.
 */
export function ForTheCurious({ place, day, threshold }) {
  const k = THRESHOLDS.indexOf(threshold);
  const count = day.counts_by_threshold[k].count;
  const trust = trustFor(place.square.region, day.lead_day, threshold, count,
    place.members);
  return (
    <details className="curious">
      <summary>For the curious: the numbers behind this</summary>
      <MemberValues day={day} />
      {/* The long track-record sentence: the period, the band of agreement,
          the region and the day number, all of which change the answer. */}
      {trust && trust.past ? <p className="pastline">{trust.past}</p> : null}
      <SquareUsed place={place} />
      <RunDetail run={place.run} />
    </details>
  );
}

/**
 * What the panel says before anything has been chosen. SPEC 11.28.
 *
 * The page opens on day 1 at 1 mm with no square chosen, so this is the first
 * thing a reader sees, and it has to explain the only three ideas the map
 * uses. It says what a square is, what a colour is, and what the number is
 * not.
 */
export function HowToRead() {
  return (
    <div className="howto" id="howtoread" tabIndex={-1}>
      <h2>How to read this map</h2>
      <ul>
        <li>
          <strong>One square is 0.25 degrees</strong>, about 28 km across. The
          forecast has no detail finer than that, so a square is the smallest
          place this site can answer about.
        </li>
        <li>
          <strong>The colour is a count.</strong> The model is run 51 times
          from slightly different starting points, and a square&apos;s colour
          is how many of those 51 runs bring at least the chosen amount of
          rain in the chosen day. Darker is more runs.
        </li>
        <li>
          <strong>It is not a probability.</strong> {notProbability()} Nothing
          on this site is calibrated against what actually happened until the
          track record exists.
        </li>
      </ul>
      {/* SPEC 11.37. On a phone the legend has no room for this line, so it
          is here instead, where the rest of the reading of the map is. The
          legend still carries it at desktop width. */}
      {/* SPEC 11.37. On a phone the legend has no room for these, so they
          are here, where the rest of the reading of the map is. */}
      <p className="whitehere">
        <span className="swatch" aria-hidden="true" />
        White: no forecast for this spot
      </p>
      <p className="whitehere around">
        <span className="swatch" aria-hidden="true" />
        Land outside India, which this site does not forecast
      </p>
      {/* SPEC 11.38. The three amounts and this site's own nicknames for
          them, written down here and in the specification and nowhere
          else. They are not anybody's official categories. */}
      <ul className="nicknames">
        {AMOUNTS.map((amount) => (
          <li key={amount.mm}>
            <strong>{amount.nickname}</strong>: {amount.mm} mm or more in the
            day. Our own words, not an official category.
          </li>
        ))}
      </ul>
      <p className="prompt">Tap a square or search a city.</p>
    </div>
  );
}

/**
 * What the page says before anything has been chosen at all. SPEC 11.38.
 *
 * Two real first-time readers failed here: one could not tell what the site
 * was for, and one did not know how to start. The page opened on a map of
 * counts with no sentence saying what a count was and no visible way in —
 * the only control on a phone's first screen was a line of grey text.
 *
 * So the empty state carries exactly two things: what this is, in words that
 * assume nothing, and what to do next. It is drawn over the map on a phone
 * and in the empty panel on a desktop; the stylesheet hides whichever copy
 * is not this reader's, so only one is ever in the page a reader is given.
 *
 * It never covers the "Not an official warning" chip, which is in the header
 * above the map and on the screen whatever else is.
 */
export function Welcome({ onFind, onHowTo, where }) {
  return (
    <div className={`welcome welcome-${where || 'panel'}`}>
      <h2>Will it rain where you are in the next 5 days?</h2>
      <p>
        One weather model from Europe&apos;s weather centre (ECMWF), run 51
        times, each from a slightly different start. We show how many of the
        51 bring rain where you are.
      </p>
      <button type="button" className="findcity" onClick={onFind}>
        Find my city
      </button>
      <p className="ortap">
        or tap the map
        {/* A button and not a link: on a phone this has to open the panel,
            which is a thing the page does and not a place to go. */}
        <button type="button" className="howtolink" onClick={onHowTo}>
          How to read this map
        </button>
      </p>
    </div>
  );
}

export default function Panel({
  place, error, notice, busy, day, threshold, onDay, onThreshold, from, square,
  onFind, onHowTo, onGo,
}) {
  // SPEC 11.30. The last line of defence, and the rule in one place: numbers
  // are shown for the chosen square or not at all. `place.square.asked` is
  // what was sent to api/place, which is the chosen square even when the
  // answer is for the land square one step away (SPEC 11.7).
  const answered = place && place.square
    && sameSquare(place.square.asked, square);
  if (notice) {
    // SPEC 11.28: a place the grid cannot carry is not an error. It gets the
    // island group's own sentence, in a plain box rather than a red one.
    return (
      <div className="panel-body">
        <div className="notice" role="status">
          {notice.where ? <h2>{notice.where}</h2> : null}
          <p>{notice.note}</p>
          {notice.why ? <p className="small">{notice.why}</p> : null}
        </div>
        <HowToRead />
      </div>
    );
  }
  if (error) {
    return (
      <div className="panel-body">
        <div className="error">
          <p>{error.said}</p>
          {error.detail ? <p className="why">{error.detail}</p> : null}
        </div>
        <HowToRead />
      </div>
    );
  }
  if (!place || !answered) {
    return (
      <div className="panel-body">
        {square ? (
          <p className="loadingsquare" role="status">
            Reading the 51 runs for this square…{' '}
            <span className="small">{squareText(square.lat, square.lon)}</span>
          </p>
        ) : null}
        {!square && busy ? (
          <p className="small">Reading the 51 runs…</p>
        ) : null}
        {!square && !busy ? (
          <>
            <Welcome where="panel" onFind={onFind} onHowTo={onHowTo} />
            <HowToRead />
          </>
        ) : null}
      </div>
    );
  }
  const chosen = place.days.find((entry) => entry.lead_day === day)
    || place.days[0];
  // SPEC 11.38. The order is the answer first and the working after it:
  // where, what, the five days, the 51 runs, the three amounts, how much
  // this label has been worth, and then one caveat said once. Everything a
  // reader can choose to open is in the one closed section at the end.
  return (
    <div className="panel-body">
      <PlaceLine place={place} from={from} />
      <Headline place={place} day={day} threshold={threshold} />
      <DayStrip
        place={place}
        day={day}
        threshold={threshold}
        onDay={onDay}
      />
      <Dots place={place} day={chosen} />
      <Counts
        place={place}
        day={chosen}
        threshold={threshold}
        onThreshold={onThreshold}
      />
      <TrustBlock place={place} day={chosen} threshold={threshold}
        onGo={onGo} />
      {/* SPEC 11.38. The one caveat, said once. It was under the legend,
          under the counts and inside How to read this map, three times on
          one screen, which is how a sentence stops being read. */}
      <p className="notpromise">
        A count of runs, not a promise of rain.{' '}
        <ReportCardLink onGo={onGo}>
          See how the counts have held up
        </ReportCardLink>
        .
      </p>
      <ForTheCurious place={place} day={chosen} threshold={threshold} />
    </div>
  );
}
