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

const WORDS = ['no', 'one', 'two', 'three', 'four'];

// The four conditions of SPEC 6.2, in the order they are checked, in words a
// reader has a chance with.
export const CONDITIONS = [
  { key: 'enough_data', name: 'enough past cases' },
  { key: 'skill_above_zero',
    name: 'beating the usual rain for this place and month' },
  { key: 'range_narrow_enough', name: 'a narrow enough range' },
  { key: 'small_honesty_error', name: 'counts that matched what happened' },
];

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

export const TOO_FEW = 'Too few past cases with this many runs agreeing to '
  + 'say how often it came true.';

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
  const times = bucket.times_in_10;
  const unit = times === 1 ? 'time' : 'times';
  return `In May to November 2026, when ${howMany(bucket, members)} said `
    + `${amount(group.threshold_mm)} or more in ${group.region} on day `
    + `${group.lead_day}, the satellite saw it about ${times} ${unit} in 10.`;
}

/** The names of the conditions this group did not pass, in 6.2's order. */
export function failed(group) {
  if (!group || !group.conditions) return [];
  return CONDITIONS.filter(
    (condition) => !(group.conditions[condition.key] || {}).pass);
}

/**
 * One plain line saying why the chip is the colour it is.
 *
 * It names the checks that were not passed rather than a grade, because
 * "rough guide" on its own tells a reader nothing they can act on.
 */
export function whyLine(group) {
  if (!group || !group.conditions) return null;
  const data = group.conditions.enough_data || {};
  const dates = data.dates || 0;
  if (group.label === 'Not enough past data') {
    return `Too few past cases here to check it: ${grouped(data.cases || 0)} `
      + `cases on ${dates} start dates.`;
  }
  const missed = failed(group);
  if (!missed.length) {
    return `All four checks passed, on ${dates} start dates.`;
  }
  const names = missed.map((condition) => condition.name);
  const list = names.length === 1 ? names[0]
    : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
  return `Checked on ${dates} start dates. It did not pass `
    + `${WORDS[missed.length]} of the four checks: ${list}.`;
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
      name: 'Enough past cases',
      pass: !!data.pass,
      got: `${grouped(data.cases || 0)} cases on ${data.dates || 0} start `
        + `dates, ${data.event_dates || 0} of them with the satellite seeing `
        + `${amount(group.threshold_mm)} or more on a square somewhere in `
        + 'the region',
      rule: `at least ${grouped(rules.min_cases)} cases, ${rules.min_dates} `
        + `start dates and ${rules.min_event_dates} of them with it seen`,
    },
    {
      name: 'Better than the usual rain for this place and month',
      pass: !!skill.pass,
      got: `skill ${fixed(group.bss)}, and the range runs from `
        + `${fixed(group.bss_lo)} to ${fixed(group.bss_hi)}`,
      rule: 'the whole range above 0',
    },
    {
      name: 'A narrow enough range',
      pass: !!range.pass,
      got: `half the range is ${fixed(range.value)}`,
      rule: `at most ${fixed(rules.max_halfwidth)}`,
    },
    {
      name: 'Counts that matched what happened',
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
