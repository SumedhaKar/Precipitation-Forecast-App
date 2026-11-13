// HC-FAIL, part 3: the local build served against a copy of the store, so
// the stale banner of SPEC 11.8 can be seen rather than argued about.
//
// One server, two jobs:
//
//   /store/...   the bytes of a published run, from data/publish/<run>/,
//                which is the exact payload `pipeline/publish.py` uploaded.
//                `STORE_BASE_URL` points the real api/*.mjs at it, so
//                nothing here pretends to be the store: the real code reads
//                a real manifest.
//   everything   web/dist as built, with /api/health and /api/place answered
//   else         by importing the real api/*.mjs files.
//
// No network, no token: every byte is local. The run time in that manifest
// is the real one, so the page's age and the banner are worked out by the
// real code from the real timestamp. Nothing here moves a clock.
//
//   node handchecks/hc_fail_site.mjs 20261112T00Z 5102

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = resolve(new URL('..', import.meta.url).pathname.slice(1));
const RUN = process.argv[2] || '20261112T00Z';
const PORT = Number(process.argv[3] || 5102);
const STORE = join(ROOT, 'data', 'publish', RUN);
const DIST = join(ROOT, 'web', 'dist');

process.env.STORE_BASE_URL = `http://127.0.0.1:${PORT}/store`;

const health = await import(pathToFileURL(join(ROOT, 'api', 'health.mjs')));
const place = await import(pathToFileURL(join(ROOT, 'api', 'place.mjs')));

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.u8': 'application/octet-stream',
};

async function send(response, file, fallback) {
  try {
    const bytes = await readFile(file);
    response.writeHead(200, {
      'content-type': TYPES[extname(file)] || 'application/octet-stream',
      'access-control-allow-origin': '*',
    });
    response.end(bytes);
  } catch {
    if (fallback) return send(response, fallback, null);
    response.writeHead(404, { 'content-type': 'text/plain' }).end('no');
  }
  return undefined;
}

createServer(async (request, response) => {
  const url = new URL(request.url, `http://127.0.0.1:${PORT}`);

  if (url.pathname.startsWith('/store/')) {
    const file = normalize(join(STORE, url.pathname.slice('/store/'.length)));
    if (!file.startsWith(normalize(STORE))) {
      response.writeHead(403).end('no');
      return;
    }
    await send(response, file, null);
    return;
  }

  if (url.pathname === '/api/health' || url.pathname === '/api/place') {
    const fn = url.pathname.endsWith('health') ? health : place;
    try {
      const answer = await fn.default.fetch(
        new Request(`https://local.test${request.url}`));
      const body = await answer.text();
      response.writeHead(answer.status, {
        'content-type': answer.headers.get('content-type')
          || 'application/json',
        'cache-control': 'no-store',
      });
      response.end(body);
    } catch (error) {
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: false, error: String(error) }));
    }
    return;
  }

  // vercel.json's rewrite: anything that is not /api and not an asset is
  // index.html.
  const asset = /\.[a-z0-9]+$/i.test(url.pathname);
  const file = normalize(join(DIST, asset ? url.pathname : '/index.html'));
  if (!file.startsWith(normalize(DIST))) {
    response.writeHead(403).end('no');
    return;
  }
  await send(response, file, asset ? null : join(DIST, 'index.html'));
}).listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`${RUN} from ${STORE}\n`);
  process.stdout.write(`serving http://127.0.0.1:${PORT}\n`);
});
