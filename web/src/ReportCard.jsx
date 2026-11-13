// The report card. SPEC 11.34.
//
// For a reader who wants to know whether to believe the forecast, in that
// order: the period first, then one plain line about the whole record, then
// the sixty labels, then the skill, then what actually happened the last time
// the model said what it is saying now.
//
// Every number is read from web/src/summary.json, which the forecast page
// already carries, so this page downloads nothing of its own. The thinking is
// in web/src/pages.js, which node can drive against that same file.

import { useState } from 'react';

import summary from './summary.json';
import {
  bandRows, crpsSentence, frequencySentence, gridFor, headline, grouped,
  skillSeries,
} from './pages';
import { SkillPlot } from './plots';

const LABELS = ['Good track record', 'Treat as a rough guide',
  'Not enough past data'];
const COLOURS = { green: 'green', amber: 'amber', grey: 'grey' };

function Chip({ label, colour, short }) {
  return (
    <span className={`chip ${COLOURS[colour] || 'grey'}`}>
      {short || label}
    </span>
  );
}

export function Headline() {
  const said = headline(summary);
  return (
    <>
      <p className="period">{summary.period}</p>
      <p className="lead">{said.sentence}</p>
      <p className="small">
        A label is one region, one lead day and one threshold: four regions by
        five days by three thresholds is {said.total} of them. Nothing on this
        page was decided after the scores were seen; the rules are SPEC 6, and
        they were written and committed first.
      </p>
    </>
  );
}

export function Grid() {
  return (
    <section className="cardsec">
      <h2>All {summary.groups.length} labels</h2>
      <ul className="chipkey">
        {LABELS.map((label) => (
          <li key={label}>
            {/* The colour is SPEC 6.7's own, carried in the file, so a key
                cannot invent one for a label no group has today. */}
            <Chip label={label} colour={summary.label_colours[label]} />
          </li>
        ))}
      </ul>
      <p className="small">
        The grid is short for these: <strong>Good</strong> is a good track
        record, <strong>Rough guide</strong> is treat as a rough guide, and{' '}
        <strong>Too few</strong> is not enough past data.
      </p>
      {summary.regions.map((region) => (
        <div className="gridwrap" key={region}>
          <h3>{region}</h3>
          <table className="labelgrid">
            <thead>
              <tr>
                <th scope="col">At least</th>
                {summary.leads.map((lead) => (
                  <th scope="col" key={lead}>Day {lead}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {gridFor(summary, region).map((row) => (
                <tr key={row.threshold}>
                  <th scope="row">{row.threshold} mm</th>
                  {row.cells.map((cell) => (
                    <td key={cell.lead}>
                      <span
                        className={`chip ${COLOURS[cell.colour] || 'grey'}`}
                        aria-label={`${region}, day ${cell.lead}, `
                          + `${row.threshold} mm: ${cell.label}`}
                      >
                        {cell.short}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

export function Skill() {
  return (
    <section className="cardsec">
      <h2>Better than the usual rain for this place and month?</h2>
      <p>
        The rain that usually falls at that square in that calendar month is
        the thing to beat. Above 0 is better than it; the line through each
        plot is 0, and the bar through each dot is the range the resampling
        gives, which holds 95 of every 100 resamples.
      </p>
      {summary.regions.map((region) => (
        <div className="plotrow" key={region}>
          <h3>{region}</h3>
          <div className="plots">
            {summary.thresholds_mm.map((threshold, at) => (
              <SkillPlot
                key={threshold}
                title={`${threshold} mm or more`}
                series={skillSeries(summary, region, threshold)}
                foot={at === 0}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

export function Bands({ start }) {
  // `start` is the choice the pickers open on. The page never sets it; the
  // test does, so that every choice a reader can make is rendered and
  // checked rather than only the one the page opens with.
  const first = start || {};
  const [region, setRegion] = useState(first.region || summary.regions[1]);
  const [lead, setLead] = useState(first.lead || 1);
  const [threshold, setThreshold] = useState(first.threshold || 10);
  const rows = bandRows(summary, region, lead, threshold);
  const frequency = frequencySentence(summary, lead, threshold);
  const crps = crpsSentence(summary, region, lead);
  return (
    <section className="cardsec">
      <h2>What happened last time the model said this</h2>
      <div className="pickers">
        <label>
          Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            {summary.regions.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          Day
          <select
            value={lead}
            onChange={(e) => setLead(Number(e.target.value))}
          >
            {summary.leads.map((one) => (
              <option key={one} value={one}>Day {one}</option>
            ))}
          </select>
        </label>
        <label>
          At least
          <select
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
          >
            {summary.thresholds_mm.map((one) => (
              <option key={one} value={one}>{one} mm</option>
            ))}
          </select>
        </label>
      </div>
      <table className="bands">
        <thead>
          <tr>
            <th scope="col">Runs agreeing</th>
            <th scope="col">Past cases</th>
            <th scope="col">The satellite saw it</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.k_from}_${row.k_to}`}>
              <th scope="row">
                {row.k_from === row.k_to ? `${row.k_from} of 51`
                  : `${row.k_from} to ${row.k_to} of 51`}
              </th>
              <td>{grouped(row.cases)}</td>
              <td>{row.often}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        Only bands with at least {summary.rules.bucket_floor.cases} past cases
        from at least {summary.rules.bucket_floor.dates} different start dates
        are here.{' '}
        {rows.length === 12
          ? 'All twelve bands of this group have that many.'
          : `${rows.length} of the twelve bands of this group have that `
            + 'many; the rest are not here, because too little happened in '
            + 'them to say anything.'}
      </p>
      {frequency ? (
        <>
          <h3>How often the model says it, against how often it happened</h3>
          <p>{frequency.sentence}</p>
        </>
      ) : null}
      {crps ? (
        <>
          <h3>The other yardstick</h3>
          <p>{crps.sentence}</p>
        </>
      ) : null}
    </section>
  );
}

export default function ReportCard() {
  return (
    <article className="page">
      <h1>The report card</h1>
      <Headline />
      <Grid />
      <Skill />
      <Bands />
      <p className="small">
        The working is on <a href="/how-we-checked">How we checked</a>, with
        the method, the decomposition, the sensitivities and what was left
        out.
      </p>
    </article>
  );
}
