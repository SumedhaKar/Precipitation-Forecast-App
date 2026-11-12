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

import { useState } from 'react';

import { colourOf, inkOf, labelOf, notProbability } from './palette';
import { squareText } from './snap';
import { nameOfSquare } from './places';

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

export function PlaceLine({ place, from }) {
  const where = place.square;
  const name = nameOfSquare(where.lat, where.lon);
  return (
    <div className="placeline" aria-live="polite">
      <h2>
        {squareText(where.lat, where.lon)}
        {name ? <span className="cityname">{name}</span> : null}
      </h2>
      {/* SPEC 11.28: a location is reported as its square and nothing
          finer, and the name appears only because that square is exactly
          that town's square. */}
      {from === 'location' ? (
        <p className="small">
          Your location: square {squareText(where.lat, where.lon)}. Your exact
          position was not sent anywhere.
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

export function DayStrip({ place, day, threshold, onDay }) {
  const k = THRESHOLDS.indexOf(threshold);
  return (
    <div className="strip">
      <h3>All five days at {threshold} mm</h3>
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
                aria-label={`${entry.short_ist} IST. ${entry.sentence}`}
                onClick={() => onDay(entry.lead_day)}
              >
                <span className="cellday">{entry.short_ist}</span>
                <span className="cellcount">{count}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <p className="small">
        Each cell is that day&apos;s count out of 51 at {threshold} mm, in the
        same colours as the map. Dates are IST. Choose one to change the day.
      </p>
    </div>
  );
}

export function DaySentence({ day }) {
  if (!day || !day.sentence) return null;
  return <p className="sentence">{day.sentence}</p>;
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
                  <strong>{count}</strong> of {place.members} model runs
                </span>
                <span className="rowband">
                  <span
                    className="swatch"
                    style={{ background: colourOf(count) }}
                  />
                  {labelOf(count)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      <p className="small">{notProbability()}</p>
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
      <h3>Each of the 51 model runs</h3>
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
              style={{ background: DOT_COLOURS[category] }}
            />
            {sentenceCase(name)}: {day.dots[category]}
          </li>
        ))}
      </ul>
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
      <h3>What each model run gives, in whole millimetres</h3>
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
 * What the panel says before anything has been chosen. SPEC 11.28.
 *
 * The page opens on day 1 at 1 mm with no square chosen, so this is the first
 * thing a reader sees, and it has to explain the only three ideas the map
 * uses. It says what a square is, what a colour is, and what the number is
 * not.
 */
export function HowToRead() {
  return (
    <div className="howto">
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
          is how many of those 51 runs give at least the chosen amount of rain
          in the chosen day. Darker is more runs.
        </li>
        <li>
          <strong>It is not a probability.</strong> {notProbability()} Nothing
          on this site is calibrated against what actually happened until the
          track record exists.
        </li>
      </ul>
      <p className="prompt">Click a square or search a town.</p>
    </div>
  );
}

export default function Panel({
  place, error, notice, busy, day, threshold, onDay, onThreshold, from,
}) {
  if (notice) {
    // SPEC 11.28: a place the grid cannot carry is not an error. It gets the
    // island group's own sentence, in a plain box rather than a red one.
    return (
      <div className="panel-body">
        <div className="notice" role="status">
          {notice.where ? <h2>{notice.where}</h2> : null}
          <p>{notice.note}</p>
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
  if (!place) {
    return (
      <div className="panel-body">
        {busy ? <p className="small">Reading the forecast…</p> : <HowToRead />}
      </div>
    );
  }
  const chosen = place.days.find((entry) => entry.lead_day === day)
    || place.days[0];
  return (
    <div className="panel-body">
      <PlaceLine place={place} from={from} />
      <DaySentence day={chosen} />
      <Counts
        place={place}
        day={chosen}
        threshold={threshold}
        onThreshold={onThreshold}
      />
      <DayStrip
        place={place}
        day={day}
        threshold={threshold}
        onDay={onDay}
      />
      <Dots place={place} day={chosen} />
      <MemberValues day={chosen} />
      <SquareUsed place={place} />
    </div>
  );
}
