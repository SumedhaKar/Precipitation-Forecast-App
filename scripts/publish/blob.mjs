// The only code in this project that talks to Vercel. SPEC 8.10.
//
// One JSON request on standard input, one JSON reply on standard output,
// three verbs:
//
//   {"op":"put","items":[{pathname,file,contentType,maxAge}]}
//   {"op":"list","prefix":"runs/"}
//   {"op":"delete","pathnames":["runs/.../days.json", ...]}
//
// It holds no logic about runs, tiles or retention: those are decisions, and
// decisions live in pipeline/publish.py where they can be tested without a
// network.
//
// The token. BLOB_READ_WRITE_TOKEN is read from the environment by the SDK
// itself. There is no token argument and no token flag, because a flag would
// show up in process listings and in Actions logs. This script never prints
// its environment, and an error reply carries the error's name and message
// and nothing else.

import { readFile } from 'node:fs/promises';
import { del, list, put } from '@vercel/blob';

const TOKEN_NAME = 'BLOB_READ_WRITE_TOKEN';

function reply(value) {
  process.stdout.write(JSON.stringify(value));
}

function fail(name, message) {
  reply({ ok: false, error: { name, message } });
  process.exit(1);
}

async function readRequest() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const text = Buffer.concat(chunks).toString('utf8').trim();
  if (!text) throw new Error('no request on standard input');
  return JSON.parse(text);
}

async function doPut(items) {
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error('put needs a non-empty items array');
  }
  const results = [];
  for (const item of items) {
    const body = await readFile(item.file);
    const blob = await put(item.pathname, new Blob([body]), {
      access: 'public',
      addRandomSuffix: false,     // SPEC 8.5: pathnames must be predictable
      allowOverwrite: true,       // SPEC 8.5: a half-finished publish retries
      contentType: item.contentType,
      cacheControlMaxAge: item.maxAge,
    });
    results.push({
      pathname: blob.pathname,
      url: blob.url,
      size: body.length,
      etag: blob.etag,
    });
  }
  return { ok: true, results };
}

async function doList(prefix) {
  const blobs = [];
  let cursor;
  do {
    // eslint-disable-next-line no-await-in-loop
    const page = await list({ prefix: prefix || undefined, cursor, limit: 1000 });
    for (const blob of page.blobs) {
      blobs.push({
        pathname: blob.pathname,
        url: blob.url,
        size: blob.size,
        uploadedAt: blob.uploadedAt,
        etag: blob.etag,
      });
    }
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);
  return { ok: true, blobs };
}

async function doDelete(pathnames) {
  if (!Array.isArray(pathnames) || pathnames.length === 0) {
    throw new Error('delete needs a non-empty pathnames array');
  }
  if (pathnames.length > 1000) {
    throw new Error(`delete was given ${pathnames.length} pathnames, over the 1000 limit`);
  }
  await del(pathnames);
  return { ok: true, deleted: pathnames.length };
}

async function main() {
  // Presence only. The value is never read into a variable, logged or echoed.
  if (!process.env[TOKEN_NAME]) {
    fail('MissingToken', `${TOKEN_NAME} is not set in this environment`);
  }

  let request;
  try {
    request = await readRequest();
  } catch (error) {
    fail('BadRequest', error.message);
    return;
  }

  try {
    switch (request.op) {
      case 'put':
        reply(await doPut(request.items));
        break;
      case 'list':
        reply(await doList(request.prefix));
        break;
      case 'delete':
        reply(await doDelete(request.pathnames));
        break;
      default:
        fail('BadRequest', `unknown op ${JSON.stringify(request.op)}`);
    }
  } catch (error) {
    fail(error?.name || 'Error', error?.message || String(error));
  }
}

await main();
