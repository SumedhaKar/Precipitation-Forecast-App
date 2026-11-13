// What the page asks the track record. SPEC 11.33.
//
// Pure functions over the summary handed in, with no imports at all, so
// `node` can load this file and a test can drive every one of them against
// the real web/src/summary.json, which is results/site_summary.json byte for
// byte. web/src/trust.js is the one line of glue that binds them to that file
// for the components.
//
// Nothing here computes a score, a frequency or a label. Every number comes
// out of the file as it was written by pipeline/labels.py, including the
// rounding: "about 5 times in 10" is the bucket's own `times_in_10`, decided
// when the record was frozen and never worked out again here.

// The record was scored on 51 members (SPEC 2.1). A run with any other number
// is not comparable with it, so nothing is said rather than something close.
export const RECORD_MEMBERS = 51;

// The four conditions of SPEC 6.2, in the order they are checked, said as
// what went wrong rather than as the name of a test. `name` is the short name
// the "Why this label?" list uses; `missed` is the plain words the one line
// under the chip uses when that check was not passed.
export const CONDITIONS = [
  { key: 'enough_data',
    name: 'Enough past cases',
    missed: 'too few past cases' },
  { key: 'skill_above_zero',
    name: 'Better than the usual rain for this place and month',
    missed: 'not clearly better than the usual rain for this place and '
      + 'month' },
  { key: 'range_narrow_enough',
    name: 'A narrow enough range',
    missed: 'too uncertain to tell' },
  { key: 'small_honesty_error',
    name: 'Counts that matched what happened',
    missed: 'the counts were too confident: when many runs agreed, the '
      + 'satellite saw it less often' },
];

// SPEC 11.33. Said where a group beat the usual rain and is still amber: the
// honest line has to carry both halves, or it reads as a worse record than it
// is.
export const SKILL_PASSED = 'better than the usual rain for this place and '
  + 'month';

/** First letter up, the rest left alone. */
function upper(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

/** 265677 -> "265,677". Not toLocaleString: the grouping must not move. */
export function grouped(value) {
  const digits = String(Math.round(Math.abs(value)));
  let out = '';
  for (let at = digits.length; at > 0; at -= 3) {
    out = digits.slice(Math.max(0, at - 3), at) + (out ? `,${out}` : '');
  }
  return (value < 0 ? '-' : '') + out;
}

/** Two decimals, and never the "-0.00" that a rounded -0.001 would give. */
export function fixed(value) {
  const text = Number(value).toFixed(2);
  return text === '-0.00' ? '0.00' : text;
}

/** The group for one region, lead day and threshold, or null. */
export function groupFor(summary, region, leadDay, threshold) {
  if (!summary || !Array.isArray(summary.groups)) return null;
  if (!region) return null;
  return summary.groups.find(
    (group) => group.region === region
      && group.lead_day === Number(leadDay)
      && Math.abs(group.threshold_mm - Number(threshold)) < 1e-9,
  ) || null;
}

/**
 * The counted bucket a count falls in, or null.
 *
 * Only counted buckets are in the file at all (SPEC 6.4: at least 100 cases
 * from at least 10 start dates), so "not found" and "too few past cases" are
 * the same answer, and the page cannot say how often something came true out
 * of a handful of cases.
 */
export function bucketFor(group, count) {
  if (!group || !Array.isArray(group.buckets)) return null;
  if (!Number.isInteger(count)) return null;
  return group.buckets.find(
    (bucket) => count >= bucket.k_from && count <= bucket.k_to) || null;
}

/** "none of the 51 runs", "all 51 runs", "36 to 40 of 51 runs". */
function howMany(bucket, members) {
  if (bucket.k_from === 0 && bucket.k_to === 0) {
    return `none of the ${members} runs`;
  }
  if (bucket.k_from === members && bucket.k_to === members) {
    return `all ${members} runs`;
  }
  if (bucket.k_from === bucket.k_to) {
    return `${bucket.k_from} of ${members} runs`;
  }
  return `${bucket.k_from} to ${bucket.k_to} of ${members} runs`;
}

/** "1 mm", "10 mm", "50 mm". */
function amount(threshold) {
  return `${Number.isInteger(threshold) ? threshold : threshold} mm`;
}

// SPEC 5.9 again: even the line that says nothing says the satellite.
export const TOO_FEW = 'Too few past cases with this many runs agreeing to '
  + 'say how often the satellite saw it.';

/**
 * "about 5 times in 10", and the two ends said in words.
 *
 * SPEC 11.33. "about 0 times in 10" reads as never, which is not what a band
 * with a few hundred cases in it earned the right to say, and "about 10 times
 * in 10" reads as always. Both ends are rounded, so both are said as the
 * roundings they are.
 */
export function howOften(bucket) {
  const times = bucket.times_in_10;
  if (times <= 0) return 'fewer than 1 time in 10';
  if (times >= 10) return 'nearly every time';
  return `about ${times} ${times === 1 ? 'time' : 'times'} in 10`;
}

/**
 * What happened last time the model said something like this.
 *
 * "the satellite saw it", never "it rained" (SPEC 5.9): IMERG is an estimate,
 * and the strongest thing that can be said is that the forecast agreed with
 * it. The sentence names the period, the band of agreement, the region and
 * the day, because every one of those changes the answer.
 */
export function pastSentence(group, count, members) {
  if (!group || members !== RECORD_MEMBERS) return null;
  const bucket = bucketFor(group, count);
  if (!bucket) return TOO_FEW;
  return `In May to November 2026, when ${howMany(bucket, members)} said `
    + `${amount(group.threshold_mm)} or more in ${group.region} on day `
    + `${group.lead_day}, the satellite saw it ${howOften(bucket)}.`;
}

/** The names of the conditions this group did not pass, in 6.2's order. */
export function failed(group) {
  if (!group || !group.conditions) return [];
  return CONDITIONS.filter(
    (condition) => !(group.conditions[condition.key] || {}).pass);
}

/**
 * One plain line saying why the chip is the colour it is. SPEC 11.33.
 *
 * It names what went wrong rather than a grade, because "rough guide" on its
 * own tells a reader nothing they can act on. Where the group did beat the
 * usual rain for this place and month and is amber all the same, the line
 * says both halves: leaving the good half out would describe a worse record
 * than the one we measured.
 */
export function whyLine(group) {
  if (!group || !group.conditions) return null;
  const missed = failed(group).map((condition) => condition.missed);
  if (!missed.length) return 'All four checks passed.';
  const joined = missed.length === 1 ? missed[0]
    : `${missed.slice(0, -1).join(', ')}, and ${missed[missed.length - 1]}`;
  const skill = group.conditions.skill_above_zero || {};
  if (skill.pass) {
    return `${upper(SKILL_PASSED)}, but ${joined}.`;
  }
  return `${upper(joined)}.`;
}

/**
 * "about 4 in 10", and only beside a green label. SPEC 6.7.
 *
 * A count read as a share of 10 is a claim that the count means something
 * about how often it happens, and that claim is exactly what the track record
 * has not earned yet. No group is green today, so this returns null
 * everywhere on the site as it stands.
 */
export function aboutInTen(group, count, members) {
  if (!group || group.label !== 'Good track record') return null;
  if (!Number.isInteger(count) || !members) return null;
  return `about ${Math.round((10 * count) / members)} in 10`;
}

/**
 * The four conditions of 6.2 in plain words, with their own numbers.
 *
 * The figures a rule asks for are read from the file too, so the page cannot
 * print a rule the record was not judged by.
 */
export function conditionLines(summary, group) {
  if (!group || !group.conditions) return [];
  const rules = (summary && summary.rules) || {};
  const got = group.conditions;
  const data = got.enough_data || {};
  const skill = got.skill_above_zero || {};
  const range = got.range_narrow_enough || {};
  const honest = got.small_honesty_error || {};
  return [
    {
      name: CONDITIONS[0].name,
      pass: !!data.pass,
      got: `${grouped(data.cases || 0)} cases on ${data.dates || 0} start `
        + `dates, ${data.event_dates || 0} of them with the satellite seeing `
        + `${amount(group.threshold_mm)} or more on a square somewhere in `
        + 'the region',
      rule: `at least ${grouped(rules.min_cases)} cases, ${rules.min_dates} `
        + `start dates and ${rules.min_event_dates} of them with it seen`,
    },
    {
      name: CONDITIONS[1].name,
      pass: !!skill.pass,
      got: `skill ${fixed(group.bss)}, and the range runs from `
        + `${fixed(group.bss_lo)} to ${fixed(group.bss_hi)}`,
      rule: 'the whole range above 0',
    },
    {
      name: CONDITIONS[2].name,
      pass: !!range.pass,
      got: `half the range is ${fixed(range.value)}`,
      rule: `at most ${fixed(rules.max_halfwidth)}`,
    },
    {
      name: CONDITIONS[3].name,
      pass: !!honest.pass,
      got: `over ${honest.counted_buckets || 0} counted bands of agreement, `
        + `the widest gap between what the runs said and what the satellite `
        + `saw was ${fixed(honest.worst_error)}`,
      rule: `at most ${fixed(rules.max_bucket_error)}`,
    },
  ];
}

/**
 * The notes under the conditions: luck, the two yardsticks, the period.
 *
 * The CRPS note is shown only where the record flagged this region and lead
 * day (SPEC 6.9 rule 3), and it says what the disagreement is rather than
 * leaving a reader to find it in a file.
 */
export function notes(summary, group) {
  const out = [];
  if (!summary || !group) return out;
  if (group.luck) {
    out.push({ what: 'About the skill', says: summary.luck_wording });
  }
  if (summary.crps_compared && group.crps_disagrees) {
    out.push({
      what: 'Two yardsticks',
      says: 'A second score, CRPS, asks a different question: not whether the '
        + 'right number of runs crossed a line, but how close the whole '
        + 'spread of runs was to the millimetres that fell. Here '
        + `${summary.crps_disagrees_wording}.`,
    });
  }
  if (group.disclose) out.push({ what: 'Also', says: group.disclose });
  out.push({ what: 'The period', says: summary.period });
  return out;
}

/** Everything the panel shows for one square, day and threshold. */
export function trustFor(summary, region, leadDay, threshold, count,
  members) {
  const group = groupFor(summary, region, leadDay, threshold);
  if (!group) return null;
  return {
    label: group.label,
    colour: group.colour,
    why: whyLine(group),
    past: pastSentence(group, count, members),
    percent: aboutInTen(group, count, members),
    conditions: conditionLines(summary, group),
    notes: notes(summary, group),
  };
}
