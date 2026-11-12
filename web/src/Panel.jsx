// The place panel. SPEC 11.20.
//
// Everything the map shows for the chosen square is written here in words and
// numbers, because a canvas is not readable: no information on this site is
// available only by clicking the map (SPEC 11.22).
//
// Every number here was published. The counts and the dots are the tiles' own
// (SPEC 8.4), the member values are whole millimetres rounded down, which
// api/place computed from the published integers, and the one sentence a day
// is built by api/place from that day's three counts and nothing else.

import { colourOf, labelOf, notProbability } from './palette';
import { squareText } from './snap';
import cityList from './cities.json';

const CITIES = cityList.cities;

// SPEC 4.3, in the order the store publishes them. The same colour family as
// the map's legend, so the page has one visual language.
const DOT_COLOURS = ['#eceff1', '#a1dab4', '#41b6c4', '#225ea8'];

const THRESHOLDS = [1, 10, 50];

function cityAt(lat, lon) {
  const found = CITIES.find(
    (city) => Math.abs(city.lat - lat) < 1e-9
      && Math.abs(city.lon - lon) < 1e-9);
  return found ? found.name : null;
}

function summarise(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return {
    lowest: sorted[0],
    middle: sorted[Math.floor(sorted.length / 2)],
    highest: sorted[sorted.length - 1],
  };
}

export function PlaceLine({ place }) {
  const where = place.square;
  const name = cityAt(where.lat, where.lon);
  return (
    <div className="placeline" aria-live="polite">
      <h2>
        {squareText(where.lat, where.lon)}
        {name ? <span className="cityname">{name}</span> : null}
      </h2>
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
                style={{ background: colourOf(count) }}
                aria-pressed={chosen}
                aria-label={`${entry.short_ist}. ${entry.sentence}`}
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
        same colours as the map. Choose one to change the day.
      </p>
    </div>
  );
}

export function DaySentence({ day }) {
  if (!day || !day.sentence) return null;
  return <p className="sentence">{day.sentence}</p>;
}

export function Counts({ place, day, threshold }) {
  return (
    <>
      <table className="counts">
        <caption>
          {day.short_ist}: {day.label}
        </caption>
        <tbody>
          {THRESHOLDS.map((amount, k) => {
            const count = day.counts_by_threshold[k].count;
            return (
              <tr key={amount} className={amount === threshold ? 'now' : ''}>
                <th scope="row">{amount} mm or more</th>
                <td>
                  <strong>{count}</strong> of {place.members} model runs
                </td>
                <td className="band">
                  <span
                    className="swatch"
                    style={{ background: colourOf(count) }}
                  />
                  {labelOf(count)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="small">
        {notProbability(day.counts_by_threshold[THRESHOLDS.indexOf(threshold)]
          .count)}
      </p>
    </>
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
            {day.dots[category]} {name}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MemberValues({ day }) {
  const spread = summarise(day.members_mm);
  return (
    <div className="members">
      <h3>What each model run gives, in whole millimetres</h3>
      <p className="spread">
        lowest {spread.lowest} mm, middle {spread.middle} mm, highest{' '}
        {spread.highest} mm
      </p>
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

export default function Panel({ place, error, busy, day, threshold, onDay }) {
  if (error) {
    return (
      <div className="panel-body">
        <p className="error">{error}</p>
      </div>
    );
  }
  if (!place) {
    return (
      <div className="panel-body">
        <p className="small">
          {busy ? 'Reading the forecast…' : 'Choose a square on the map.'}
        </p>
      </div>
    );
  }
  const chosen = place.days.find((entry) => entry.lead_day === day)
    || place.days[0];
  return (
    <div className="panel-body">
      <PlaceLine place={place} />
      <DaySentence day={chosen} />
      <Counts place={place} day={chosen} threshold={threshold} />
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
