// How we checked. SPEC 11.34.
//
// For a reader who wants to argue with the method. Everything here is meant
// to be checkable: the rules, the commit they were fixed in, the hash of the
// specification they are written in, and then the numbers, with the file they
// came from named beside them.
//
// web/src/details.json is imported here and nowhere else, so it travels in
// this page's own chunk: a reader who only wants the forecast never
// downloads 126 KB of working.

import { useState } from 'react';

import summary from './summary.json';
import details from './details.json';
import {
  blockSeries, decomposition, disagreements, exclusions, fixed, grouped,
  mapCells, prettyDate, rowsOf, thresholdRows, variantRows, WHY_LEFT_OUT,
} from './pages';
import { CellMap } from './plots';

const REPO = 'https://github.com/SumedhaKar/Precipitation-Forecast-App';
// The nine hand checks of the specification. HC4 read a raw IMERG file that
// was deleted after it was checked (SPEC 2.6), so its findings are in SPEC
// 2.3 rather than in a script here; the other eight have both a script and a
// record, and hc_align is a tenth that came before them.
const HANDCHECKS = [
  ['HC1', 'the GRIB file against the subset', true],
  ['HC2', 'the daily difference, worked out again', true],
  ['HC3', 'the steps and the members', true],
  ['HC4', 'one raw IMERG file, read field by field, on a file since deleted',
    false],
  ['HC5', 'one cell of the area-weighted remap', true],
  ['HC6', 'the 51 member values in one square', true],
  ['HC7', 'the published bytes', true],
  ['HC8', 'one square on the live map', true],
  ['HC9', 'one reliability band, worked out again from the archive', true],
];

function Numbers({ rows }) {
  return (
    <table className="plain">
      <tbody>
        {rows.map(([what, value]) => (
          <tr key={what}>
            <th scope="row">{what}</th>
            <td>{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Method() {
  const reference = details.reference;
  const bootstrap = details.bootstrap;
  return (
    <section className="cardsec">
      <h2>The method</h2>
      <p className="period">{details.period}</p>
      <p>
        <strong>A case</strong> is one square, one start date and one lead
        day. The forecast is how many of the 51 runs give at least the
        threshold over that day; the observation is whether the satellite
        estimate for that square and that day reached the same threshold. The
        day is 5:30 am to 5:30 am IST at both ends, so the two are the same
        day (SPEC 1.2 and 5.1).
      </p>
      <p>
        <strong>The observation is a satellite estimate.</strong> NASA IMERG
        Late {details.meta.imerg.version}, DOI {details.meta.imerg.doi}, and
        never ground truth. Everything on this site says the forecast{' '}
        {details.wording.replace(' (SPEC 5.9)', '')}.
      </p>
      <p>
        <strong>The grids are made to meet</strong> by area-weighted overlap,
        IMERG&apos;s 0.1 degree boxes onto the forecast&apos;s 0.25 degree
        squares, with the weights computed on a sphere (SPEC 3.3). A square is
        used only if at least 90 of every 100 parts of its area have a usable
        observation (SPEC 3.4). On this record that rule never bound: every
        India square of all {details.meta.imerg.dates} observation dates was
        complete.
      </p>
      <p>
        <strong>The thing to beat</strong> is the rain that usually falls at
        that square in that calendar month, taken over{' '}
        {grouped(reference.groups)} reference groups keyed by{' '}
        {reference.key}. It is computed from the same six months it is
        compared with, which makes it harder to beat, not easier.{' '}
        {details.note_small_reference_groups}
      </p>
      <p>
        <strong>The score</strong> is the Brier score, and the skill is one
        minus the sum of the case scores over the sum of the reference&apos;s,
        pooled inside each reference group before the groups are added up
        (Hamill and Juras 2006). <strong>The range</strong> is{' '}
        {grouped(bootstrap.resamples)} resamples of {bootstrap.unit}, seed{' '}
        {bootstrap.seed}, taken at the 2.5 and 97.5 points by the{' '}
        {bootstrap.percentile_method} method, which is the range that holds 95
        of every 100 resamples.
      </p>
      <p>
        <strong>The honesty check</strong> bands the forecasts by how many
        runs agreed -- 0 alone, 51 alone, and ten bands of five in between --
        and asks whether what happened in each band is within{' '}
        {fixed(summary.rules.max_bucket_error)} of what the runs said. A band
        counts only with at least {summary.rules.bucket_floor.cases} cases
        from {summary.rules.bucket_floor.dates} different start dates.
      </p>
      <p className="fixedrules">
        <strong>Every rule was fixed before any result existed.</strong> The
        labels come from the four conditions of SPEC 6.2 with the figures{' '}
        {grouped(summary.rules.min_cases)} cases, {summary.rules.min_dates}{' '}
        start dates, {summary.rules.min_event_dates} of them with the event
        seen, a half-range of at most {fixed(summary.rules.max_halfwidth)} and
        a band error of at most {fixed(summary.rules.max_bucket_error)}. They
        were committed in{' '}
        <a href={`${REPO}/commit/${details.meta.git_commit}`}>
          {details.meta.git_commit.slice(0, 7)}
        </a>
        , and the SHA256 of SPEC.md as committed is{' '}
        <code>{details.meta.spec_sha256}</code> ({details.meta.spec_sha256_note}).
      </p>
    </section>
  );
}

export function Decomposition({ start }) {
  // See the note in ReportCard.jsx: the pickers' first choice is a seam for
  // the test, and the page never passes it.
  const first = start || {};
  const [region, setRegion] = useState(first.region || details.regions[1]);
  const [lead, setLead] = useState(first.lead || 1);
  const [threshold, setThreshold] = useState(first.threshold || 10);
  const parts = decomposition(details, 'all51', region, lead, threshold);
  if (!parts) return null;
  return (
    <section className="cardsec">
      <h2>The decomposition, for one group</h2>
      <div className="pickers">
        <label>
          Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            {details.regions.map((name) => (
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
            {details.leads.map((one) => (
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
            {details.thresholds_mm.map((one) => (
              <option key={one} value={one}>{one} mm</option>
            ))}
          </select>
        </label>
      </div>
      <Numbers
        rows={[
          ['Reliability (lower is better)', fixed(parts.reliability, 6)],
          ['Resolution (higher is better)', fixed(parts.resolution, 6)],
          ['Uncertainty (the base rate’s own score)',
            fixed(parts.uncertainty, 6)],
          ['Reliability − resolution + uncertainty',
            fixed(parts.sum, 6)],
          ['Brier score', fixed(parts.brier, 6)],
          ['Skill against the usual rain', fixed(parts.bss, 6)],
          ['Cases', grouped(parts.cases)],
          ['How often it happened', fixed(parts.base_rate, 6)],
        ]}
      />
      <p className="small">
        The first three add up to the fourth, which is the Brier score, over
        all 52 possible counts rather than over the twelve bands. The identity
        is checked to one part in a million million while the scores are being
        computed, and the run stops if it fails; the numbers here are the
        published ones, rounded to six decimals, so the sum can differ from
        the Brier score in the last digit and does for{' '}
        {parts.gap > 0 ? 'this group' : 'some groups'}.
      </p>
    </section>
  );
}

export function Sensitivities({ start }) {
  const first = start || {};
  const [region, setRegion] = useState(first.region || details.regions[1]);
  const [lead, setLead] = useState(first.lead || 1);
  const variants = variantRows(details, region, lead, 10);
  const thresholds = thresholdRows(details, region, lead);
  return (
    <section className="cardsec">
      <h2>What happens if the choices change</h2>
      <div className="pickers">
        <label>
          Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            {details.regions.map((name) => (
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
            {details.leads.map((one) => (
              <option key={one} value={one}>Day {one}</option>
            ))}
          </select>
        </label>
      </div>
      <h3>51 members against the 50 perturbed ones, and inland only</h3>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Ensemble</th>
            <th scope="col">Skill at 10 mm</th>
            <th scope="col">Range</th>
            <th scope="col">Cases</th>
          </tr>
        </thead>
        <tbody>
          {variants.map((row) => (
            <tr key={row.variant}>
              <th scope="row">{row.note}</th>
              <td>{fixed(row.bss, 4)}</td>
              <td>{fixed(row.lo, 4)} to {fixed(row.hi, 4)}</td>
              <td>{grouped(row.cases)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3>Thresholds either side of 10 mm</h3>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">At least</th>
            <th scope="col">Skill</th>
            <th scope="col">Range</th>
            <th scope="col">How often it happened</th>
          </tr>
        </thead>
        <tbody>
          {thresholds.map((row) => (
            <tr key={row.threshold_mm}>
              <th scope="row">
                {row.threshold_mm} mm{row.published ? '' : ' (checked only)'}
              </th>
              <td>{fixed(row.bss, 4)}</td>
              <td>{fixed(row.lo, 4)} to {fixed(row.hi, 4)}</td>
              <td>{fixed(row.base_rate, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        8 mm and 12 mm are scored to see whether 10 mm is a lucky line, and
        the inland-only run leaves out the {details.squares.coastal} coastal
        squares. <strong>
          {details.sensitivity_changes.length === 0
            ? 'No label changes under any of them.'
            : `${details.sensitivity_changes.length} labels change under one `
              + 'of them, and each is disclosed beside that label.'}
        </strong>
      </p>
    </section>
  );
}

export function Maps({ start }) {
  const first = start || {};
  const [lead, setLead] = useState(first.lead || 1);
  const [threshold, setThreshold] = useState(first.threshold || 10);
  const cells = mapCells(details, lead, threshold);
  const scores = cells.map((cell) => cell.bss).filter(
    (value) => value !== null);
  return (
    <section className="cardsec">
      <h2>Where the rain is, and where the skill is</h2>
      <div className="pickers">
        <label>
          Day
          <select
            value={lead}
            onChange={(e) => setLead(Number(e.target.value))}
          >
            {details.leads.map((one) => (
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
            {details.published_thresholds_mm.map((one) => (
              <option key={one} value={one}>{one} mm</option>
            ))}
          </select>
        </label>
      </div>
      <div className="plots">
        <CellMap
          title={`How often ${threshold} mm or more happened`}
          cells={cells}
          pick={(cell) => cell.base_rate}
          high={1}
          least={details.two_degree.minimum_squares}
        />
        <CellMap
          title="Skill against the usual rain"
          cells={cells}
          pick={(cell) => cell.bss}
          high={Math.max(0, ...scores)}
          least={details.two_degree.minimum_squares}
        />
      </div>
      <p className="small">
        {cells.length} cells of 2 degrees, each holding up to 64 forecast
        squares. Hover or focus a rectangle for its own numbers.
      </p>
    </section>
  );
}

export function Blocks({ start }) {
  const first = start || {};
  const [region, setRegion] = useState(first.region || details.regions[1]);
  const rows = blockSeries(details, region, 1, 10);
  return (
    <section className="cardsec">
      <h2>Skill in each 30 day block</h2>
      <div className="pickers">
        <label>
          Region
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            {details.regions.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Start dates</th>
            <th scope="col">Days</th>
            <th scope="col">Cases</th>
            <th scope="col">Skill, day 1 at 10 mm</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.block}>
              <th scope="row">
                {prettyDate(row.from)} to {prettyDate(row.to)}
              </th>
              <td>{row.dates}{row.short ? ' (short)' : ''}</td>
              <td>{grouped(row.cases)}</td>
              <td>{fixed(row.bss, 4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        Six blocks of 30 start dates, the last one short. One season is one
        season: these say how much the number moves from month to month, not
        how it would behave in a winter nobody has checked.
      </p>
    </section>
  );
}

export function Crps() {
  const rows = rowsOf(details.crps).filter((row) => row.variant === 'all51');
  const split = disagreements(details);
  return (
    <section className="cardsec">
      <h2>The other yardstick: CRPS</h2>
      <p>{details.crps_note}</p>
      <p>
        The baseline is {details.crps.baseline}, needing at least{' '}
        {details.crps.minimum_days} usable days, so it is out of sample while
        the Brier reference is not. The skill below uses the fair form, which
        corrects for ensemble size.
      </p>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Region</th>
            <th scope="col">Day</th>
            <th scope="col">CRPS</th>
            <th scope="col">Baseline</th>
            <th scope="col">Skill</th>
            <th scope="col">Range</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.region}_${row.lead_day}`}>
              <th scope="row">{row.region}</th>
              <td>{row.lead_day}</td>
              <td>{fixed(row.crps_fair, 3)}</td>
              <td>{fixed(row.baseline_crps_fair, 3)}</td>
              <td>{fixed(row.crpss_fair, 3)}</td>
              <td>{fixed(row.crpss_lo, 3)} to {fixed(row.crpss_hi, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <strong>
          {split.disagree} of the {split.total} groups have the two scores
          pointing different ways.
        </strong>{' '}
        In all {split.one_way} of them it is the same way round: the Brier
        skill does not clear 0 and the CRPS skill does. They are different
        questions against different baselines -- one asks whether the right
        number of runs crossed a line against the usual rain for that place
        and month, the other asks how close the whole spread was to the
        millimetres, against what the last 30 days at that square would have
        said. The label follows the Brier score, and this is said rather than
        hidden.
      </p>
    </section>
  );
}

export function Tally() {
  return (
    <section className="cardsec">
      <h2>What was left out</h2>
      <table className="plain">
        <thead>
          <tr>
            <th scope="col">Score</th>
            <th scope="col">Possible</th>
            <th scope="col">Used</th>
            <th scope="col">Left out</th>
            <th scope="col">Why</th>
          </tr>
        </thead>
        <tbody>
          {exclusions(details).map((line) => (
            <tr key={line.what}>
              <th scope="row">{line.what}</th>
              <td>{grouped(line.possible)}</td>
              <td>{grouped(line.used)}</td>
              <td>{grouped(line.excluded)}</td>
              <td>
                {Object.entries(line.why)
                  .filter(([, count]) => count > 0)
                  .map(([why, count]) => `${grouped(count)}: `
                    + `${WHY_LEFT_OUT[why] || why}`)
                  .join('; ') || 'nothing was left out'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">
        The CRPS exclusions are the first 21 start dates, which have no 30 day
        window behind them inside the archive.
      </p>
    </section>
  );
}

export function Limits() {
  return (
    <section className="cardsec">
      <h2>What this does not tell you</h2>
      <ul className="limits">
        <li>
          <strong>The satellite is not ground truth.</strong> IMERG Late is an
          estimate from space, and where it is wrong this record is wrong with
          it. A forecast can only be shown to agree with it.
        </li>
        <li>
          <strong>It is weaker over hills and coasts.</strong> Satellite
          rainfall is hardest exactly where the rain is steepest, so a
          mountain square&apos;s record is worth less than a plain&apos;s. The
          inland-only run is one check on that, not a fix for it.
        </li>
        <li>
          <strong>A square is 28 km.</strong> Nothing here says anything about
          one street, one hill or one field.
        </li>
        <li>
          <strong>One season.</strong> {details.dates.runs} runs from{' '}
          {prettyDate(details.dates.first)} to{' '}
          {prettyDate(details.dates.last)}, most of them monsoon.
          It says little about winter and nothing about a year.
        </li>
        <li>
          <strong>A sub-cell offset.</strong> SPEC 5.10 found that the
          forecast and the satellite put the same rain in slightly different
          places within a square. It is reported, not corrected for.
        </li>
        <li>
          <strong>
            {Object.keys(details.not_computed).length} checks were not
            computed.
          </strong>
          <ul>
            {Object.entries(details.not_computed).map(([name, said]) => (
              <li key={name}>{said}</li>
            ))}
          </ul>
          Nothing on this site rests on either, and nothing claims they were
          done.
        </li>
      </ul>
    </section>
  );
}

export function Files() {
  return (
    <section className="cardsec">
      <h2>The files themselves</h2>
      <ul className="files">
        <li><a href={`${REPO}/blob/main/SPEC.md`}>SPEC.md</a>, the
          specification every rule here is written in
        </li>
        <li>
          <a href={`${REPO}/blob/main/results/verification.json`}>
            results/verification.json
          </a>, every score, 1.6 MB
        </li>
        <li>
          <a href={`${REPO}/blob/main/results/labels.json`}>
            results/labels.json
          </a>, every label with its four conditions
        </li>
        <li>
          <a href={`${REPO}/blob/main/results/site_summary.json`}>
            results/site_summary.json
          </a>, what this website reads
        </li>
        <li>
          <a href={`${REPO}/blob/main/results/site_details.json`}>
            results/site_details.json
          </a>, what this page reads
        </li>
        <li>
          <a href={`${REPO}/blob/main/results/verification_meta.json`}>
            results/verification_meta.json
          </a>, the commit, the hash and the tally
        </li>
        <li>
          <a href={`${REPO}/tree/main/handchecks`}>handchecks/</a> and{' '}
          <a href={`${REPO}/tree/main/handchecks/results`}>
            handchecks/results/
          </a>, nine checks done again outside the pipeline:
          <ul>
            {HANDCHECKS.map(([name, what, script]) => (
              <li key={name}>
                <strong>{name}</strong>, {what}
                {script ? '' : ' (no script here: the file it read was '
                  + 'deleted after it was checked, and what it found is in '
                  + 'SPEC 2.3)'}
              </li>
            ))}
          </ul>
        </li>
      </ul>
    </section>
  );
}

export default function HowWeChecked() {
  return (
    <article className="page">
      <h1>How we checked</h1>
      <Method />
      <Decomposition />
      <Sensitivities />
      <Maps />
      <Blocks />
      <Crps />
      <Tally />
      <Limits />
      <Files />
    </article>
  );
}
