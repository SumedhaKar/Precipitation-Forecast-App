// GET /api/health - what the store is publishing, and how old it is.
// SPEC 11.6.
//
// No dependencies: `fetch`, `URL` and `Response` are built into Node, and
// the pipeline's requirements.txt is never installed for this (SPEC 11.3).
// No token either: every read here is a public URL (SPEC 8.9).
//
// The twenty lines above `fetch` are repeated in api/place.mjs on purpose.
// Vercel turns every file in /api into its own function and documents that
// shared modules belong outside /api, and there is no third place for them
// in the fixed structure. Twenty duplicated lines is the cheaper mistake.

import { readFileSync } from 'node:fs';

const STALE_HOURS = 36; // SPEC 11.8
const MAX_AGE = 60; // SPEC 11.6, the manifest's own cache age

function storeBase() {
  const fromEnv = process.env.STORE_BASE_URL;
  if (fromEnv) return fromEnv.replace(/\/+$/, '');
  const candidates = [
    new URL('../config/store.json', import.meta.url),
    new URL('config/store.json', `file://${process.cwd()}/`),
  ];
  for (const candidate of candidates) {
    try {
      const base = JSON.parse(readFileSync(candidate, 'utf8')).base_url;
      if (base) return base.replace(/\/+$/, '');
    } catch {
      // Try the next one. A missing or unreadable file is reported below.
    }
  }
  return null;
}

function json(body, status, maxAge) {
  return new Response(JSON.stringify(body, null, 1), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': `public, max-age=${maxAge}`,
    },
  });
}

async function readManifest(base) {
  const response = await fetch(`${base}/manifest.json`);
  if (!response.ok) {
    throw new Error(`the store answered ${response.status} for manifest.json`);
  }
  const manifest = await response.json();
  if (!manifest || typeof manifest.run_id !== 'string') {
    throw new Error('the store\'s manifest.json has no run_id');
  }
  return manifest;
}

function ageOf(manifest, now) {
  const runTime = Date.parse(manifest.run_time_utc);
  if (Number.isNaN(runTime)) return { age_hours: null, stale: null };
  const hours = (now - runTime) / 3_600_000;
  return {
    age_hours: Math.round(hours * 10) / 10,
    stale: hours > STALE_HOURS,
  };
}

function istNow(now) {
  // IST is a fixed +05:30, so this needs no time zone database.
  return new Date(now + 5.5 * 3_600_000).toISOString()
    .replace('T', ' ').slice(0, 19) + ' IST';
}

export default {
  async fetch() {
    const base = storeBase();
    if (!base) {
      return json({
        ok: false,
        store: 'no base URL: STORE_BASE_URL is not set and '
          + 'config/store.json could not be read',
      }, 500, 0);
    }

    const now = Date.now();
    let manifest;
    try {
      manifest = await readManifest(base);
    } catch (error) {
      return json({
        ok: false,
        store: `unreachable: ${error.message}`,
        checked_at_ist: istNow(now),
      }, 503, 0);
    }

    const age = ageOf(manifest, now);
    return json({
      ok: true,
      store: 'reachable',
      run_id: manifest.run_id,
      run_time_utc: manifest.run_time_utc,
      run_time_ist: manifest.run_time_ist,
      publish_time_ist: manifest.publish_time_ist,
      age_hours: age.age_hours,
      stale: age.stale,
      stale_after_hours: STALE_HOURS,
      days: (manifest.days || []).map((day) => ({
        lead_day: day.lead_day,
        label: day.label,
        from_ist: day.from_ist,
        to_ist: day.to_ist,
      })),
      thresholds_mm: manifest.thresholds_mm,
      members: manifest.members,
      india_squares: manifest.india_squares,
      member_display: manifest.member_display,
      counts_not_probabilities: true,
      checked_at_ist: istNow(now),
    }, 200, MAX_AGE);
  },
};
