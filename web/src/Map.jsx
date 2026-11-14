// The map. SPEC 11.14, 11.16, 11.17, 11.28 and 11.29.
//
// No basemap. India is drawn from web/src/geo/india.geo.json, which is the
// same Natural Earth India point-of-view geometry the forecast mask was cut
// with, so the country on screen and the squares we colour are the same
// shape. The state lines are only boundaries two Indian units share.
//
// The 4,613 squares are built once, as one GeoJSON source whose features each
// carry all fifteen counts. Changing day or threshold then changes one paint
// property: no setData, no re-tessellation, no fetch, no request.
//
// This module is loaded by a dynamic import(), so MapLibre's 325 KB does not
// hold up the run line, the stale banner or the panel. If it never arrives,
// or the browser cannot draw it, the page says so and every number is still
// reachable without it (SPEC 11.29).

import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// SPEC 11.15. MapLibre 6 is ESM only and loads its worker as a real URL,
// which it works out at runtime as a sibling of its own bundle. A bundler
// cannot see that, so the file is not emitted and the map dies with "Worker
// failed to load" — which is exactly what the first build did. Importing it
// with Vite's `?url` makes it a real asset with a real hashed name, and
// setWorkerUrl, which MapLibre exports for this, points the library at it.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

import indiaOutline from './geo/india.geo.json';
import stateLines from './geo/states.geo.json';
// SPEC 11.30. The land around India: Natural Earth's coastlines, clipped to
// the box maxBounds allows and carrying no boundary of any kind. 34 KB
// gzipped, in this chunk rather than the first one, so it costs the run line
// and the panel nothing.
import landAround from './geo/land.geo.json';
import { CITY_LABELS, FIT_ASPECTS, STATE_LABELS } from './places';
import { fitsInside, roomFor } from './fits';
import { EASE_MS, nudge, visibleBox } from './inview';
import { LAND, NEIGHBOURS, SEA, countKey, fillExpression } from './palette';
import { LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STEP, squareText } from './snap';

maplibregl.setWorkerUrl(workerUrl);

// How far the map may be dragged, outside the India box of SPEC 1.4.
//
// The slack has to be generous, and two degrees was wrong. maxBounds is not
// only a limit on panning: MapLibre also refuses to zoom out past it, so a
// box barely wider than India forces a minimum zoom, and on a wide screen
// that minimum is **more** zoomed in than the zoom that fits the country.
// The first build cut the south of India off for exactly that reason: at the
// zoom that fits 6 to 38 N in a 1,060 by 657 canvas the view is 54.6 degrees
// of longitude wide, and a 34 degree box will not allow that.
//
// So the box is wide enough never to bind on any sensible screen, and narrow
// enough that nobody can wander off to somewhere we draw nothing at all.
//
// Twenty degrees was still not enough, and the way it failed is worth
// recording: the minimum zoom maxBounds implies was *higher* than the zoom
// the padded fit asked for, so fitBounds was silently clamped and the
// padding that keeps India clear of the zoom buttons did nothing. India was
// not cut off this time only because the country is smaller than the 6 to 38
// box it sits in. At these limits the implied minimum zoom is below the
// fitting zoom on every screen from a phone to a desktop, so the fit is the
// fit and nothing overrides it.
const LIMITS = [[LON_MIN - 40, LAT_MIN - 24], [LON_MAX + 40, LAT_MAX + 14]];

const INDIA = [[LON_MIN, LAT_MIN], [LON_MAX, LAT_MAX]];

// SPEC 11.14. No basemap is drawn, and none is planned for G3. These two
// empty layers exist so that adding one later is an insertion and not a
// rewrite: they are stable ids to insert before, and they cost nothing,
// because a background layer painted at zero opacity paints nothing.
//
//   map.addLayer(basemapLayer, SLOT_BASEMAP)  // under the squares,
//                                             // over our own land fill
//   map.addLayer(labelLayer, SLOT_LABELS)     // over everything
//
// The squares are one layer with one constant opacity, below. A basemap that
// has to show through would change that constant and nothing else.
export const SLOT_BASEMAP = 'slot-basemap';
export const SLOT_LABELS = 'slot-labels';

// One number, not an expression. HC8 samples the drawn pixel and compares it
// with the palette hex (SPEC 11.25), which is only an exact match while this
// is 1 and nothing is drawn underneath the squares.
export const SQUARE_OPACITY = 1;

const STATE_LINE = '#c9d2da';
const COAST = '#8fa0ad';

// SPEC 11.28. The chosen square is marked in the page's ink, which is a
// near-black warm grey and deliberately **not** in the palette: the first
// build drew the selection in #0b2b4a, and at the whole-India view a 0.25
// degree square is about four pixels wide, so a two pixel navy outline filled
// it in and the chosen square read as a square where all 51 model runs reach
// the threshold — the darkest colour on the scale. A mark must not be able to
// be mistaken for a measurement.
const MARK = '#1f2933';
const HALO = '#ffffff';

// The grid itself. SPEC 11.29.
//
// A 0.25 degree square is (0.25 / 360) * 512 * 2^zoom pixels across in Web
// Mercator — 0.3556 at zoom 0 — so it is about four pixels at the zoom that
// fits India and 182 at the closest zoom. Twelve pixels is where an edge is
// worth drawing: below that the lines are closer together than the squares
// they separate and the map turns into a grey mesh.
//
// So one zoom decides two things, and they are opposites: below it a square
// is a speck, and the chosen one is marked with a ring of a fixed size that
// does not pretend to be the square; above it the square is a shape, and it
// is marked by its own outline while every square's edges are drawn faintly
// so the grid can be seen for what it is.
const SQUARE_AT_ZOOM_0 = (STEP / 360) * 512;
const GRID_VISIBLE_PX = 12;
export const GRID_FROM_ZOOM = Math.log2(GRID_VISIBLE_PX / SQUARE_AT_ZOOM_0);

// The ring, in screen pixels, for the zooms where the square is too small to
// have an edge: 18 pixels across, dark with a white halo and no fill. One
// number and no expression over zoom, because it only exists below
// GRID_FROM_ZOOM and above that the square's own outline takes over.
const RING = 9;

const GRID_LINE = '#8a97a3';
const GRID_OPACITY = 0.4;

// SPEC 11.25 and 11.29. Nothing in this list is data: it is the mark on the
// chosen square and the edges of the grid. HC8 samples a square's fill and
// compares it with the palette, so it samples with nothing chosen, at the
// default view, where the zoom is below GRID_FROM_ZOOM and not one of these
// layers draws a pixel. Exported so the hand check can assert that rather
// than trust it.
export const NOT_DATA_LAYERS = [
  'squares-grid', 'picked-casing', 'picked-line',
  'picked-ring-halo', 'picked-ring',
];

/**
 * Pan the map, at the zoom it is at, until the chosen square is in view.
 *
 * SPEC 11.32. Called when a square is chosen and again whenever the map
 * changes size, because on a phone choosing a square opens the bottom sheet
 * and the map that was 464 pixels tall becomes 236: a square that was near
 * the bottom of it is then below the bottom of it.
 */
function bringIntoView(created, square) {
  if (!created || !square) return;
  const at = created.project([square.lon, square.lat]);
  const canvas = created.getCanvas().getBoundingClientRect();
  const offset = nudge({ x: at.x, y: at.y }, visibleBox(
    { left: canvas.left, top: canvas.top,
      width: canvas.width, height: canvas.height },
    { width: window.innerWidth, height: window.innerHeight },
  ));
  if (!offset) return;
  // A reader who has asked for less movement gets none: the map is where it
  // has to be, it simply arrives there without the journey.
  const still = typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  created.panBy(offset, { duration: still ? 0 : EASE_MS });
}

/** Can this browser draw the map at all? SPEC 11.29. */
export function canDraw() {
  if (typeof document === 'undefined') return false;
  try {
    // MapLibre 6 needs WebGL 2. Asking for the context is the only honest
    // test: a machine can support the API and still fail to give one.
    return Boolean(document.createElement('canvas').getContext('webgl2'));
  } catch {
    return false;
  }
}

/** One square's corners, from its centre. */
function squarePolygon(lat, lon) {
  const h = STEP / 2;
  return [[
    [lon - h, lat - h], [lon + h, lat - h],
    [lon + h, lat + h], [lon - h, lat + h],
    [lon - h, lat - h],
  ]];
}

/**
 * Every India square as one FeatureCollection, with all fifteen counts.
 *
 * 255 means "outside India" (SPEC 8.4), and such a square gets no feature at
 * all, so "outside India is transparent" is a property of the data rather
 * than a colour that could be got wrong. Any one counts file carries the mask
 * as well as its values, which is why india.u8 is never fetched; a test
 * checks all fifteen agree about it.
 */
export function buildSquares(counts, grid) {
  const nLat = grid.n_lat;
  const nLon = grid.n_lon;
  const notIndia = grid.not_india;
  const step = grid.grid_step_degrees;
  const keys = Object.keys(counts);
  const first = counts[keys[0]];
  const features = [];

  for (let i = 0; i < nLat; i += 1) {
    const lat = LAT_MAX - step * i;
    for (let j = 0; j < nLon; j += 1) {
      const at = i * nLon + j;
      if (first[at] === notIndia) continue;
      const lon = LON_MIN + step * j;
      const properties = { i, j };
      for (const key of keys) properties[key] = counts[key][at];
      features.push({
        type: 'Feature',
        id: at,
        properties,
        geometry: { type: 'Polygon', coordinates: squarePolygon(lat, lon) },
      });
    }
  }
  return { type: 'FeatureCollection', features };
}

const NOTHING = { type: 'FeatureCollection', features: [] };

function selectedShape(square) {
  if (!square) return NOTHING;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: squarePolygon(square.lat, square.lon),
      },
    }],
  };
}

function selectedCentre(square) {
  if (!square) return NOTHING;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {},
      geometry: { type: 'Point', coordinates: [square.lon, square.lat] },
    }],
  };
}

const EMPTY_STYLE = {
  version: 8,
  sources: {},
  layers: [{
    id: 'sea',
    type: 'background',
    paint: { 'background-color': SEA },
  }],
};

// Where a name may go, relative to the point it belongs to. SPEC 11.29.
//
// Each pair is a side and how far from the point, in pixels, and they are
// tried in this order until one does not clash with a name already placed.
// The first build had one placement, "to the right of the dot", and hid
// anything that clashed: Delhi hid Faridabad for no better reason than being
// first in the file, when there was room for both an inch away. Eight tries
// per city name took the number of them on screen at the whole-India view
// from four to the number in SPEC 11.29.
//
// A unit's full name has one placement and only one: centred on the unit's
// own label point, with no nudge of any kind. SPEC 11.31. A nudge is eight
// or sixteen pixels, which at the whole-India view is half a degree, and
// half a degree is the width of a small state -- so a nudge that tidied the
// map wrote HIMACHAL PRADESH across Uttarakhand. There is nowhere else a
// unit's name belongs, so there is nowhere else to try.
const CITY_TRIES = [
  ['right', 8], ['left', 8], ['above', 7], ['below', 7],
  ['right', 18], ['left', 18], ['above', 15], ['below', 15],
];
const NAME_TRIES = [['centre', 0]];

// A two letter code is small enough to look for a gap in earnest: eight
// directions at three distances, as well as the point itself. SPEC 11.30.
// It is tried only when the name did not fit, and what it saves is a forced
// label — a code written over whatever is already there because the unit has
// to be labelled somehow.
const CODE_TRIES = [['centre', 0]];
for (const away of [8, 16, 24]) {
  for (const side of ['above', 'below', 'left', 'right',
    'ne', 'nw', 'se', 'sw']) {
    CODE_TRIES.push([side, away]);
  }
}
const CHOSEN_TRIES = [['right', 14], ['left', 14], ['above', 12],
  ['below', 12]];


/**
 * Place names, as elements over the canvas rather than a symbol layer.
 *
 * SPEC 11.28 and 11.29. MapLibre draws text from SDF glyph files it fetches
 * from a `glyphs` URL, and there is no such URL here on purpose: nothing on
 * this map comes from a third party, and a font server would be one.
 * Rasterising the glyphs ourselves would be a new build dependency for a few
 * dozen words. So the labels are elements in a layer of their own above the
 * canvas, moved by the map's own projection on every frame, with the white
 * halo done by four text shadows. Being above the canvas puts them above
 * every layer, including SLOT_LABELS, which stays for a basemap's own labels.
 *
 * Three ranks, in this order: the chosen square's own label, then the 36
 * states and union territories largest first, then one city per unit with the
 * largest population first. Each is tried in every placement before it is
 * hidden, and a state that will not fit under its name is offered its two
 * letter code before it is given up on. So the whole country shows every
 * state's name and as many cities as there is room for, and a phone shows
 * fewer cities rather than a worse map.
 *
 * The dot is part of the label, not a separate circle layer, so a city's dot
 * cannot be drawn where its name was hidden.
 */
function makeLabels(container, mapFor) {
  const holder = document.createElement('div');
  holder.className = 'maplabels';
  holder.setAttribute('aria-hidden', 'true'); // the panel carries the words
  container.appendChild(holder);

  function add(className, text, lngLat, extra) {
    const element = document.createElement('span');
    element.className = `maplabel ${className}`;
    element.textContent = text;
    holder.appendChild(element);
    return { element, text, lngLat, ...extra };
  }

  // The dot is a thing of its own, drawn at the point, rather than something
  // attached to a side of the word: a name may end up in any of eight places
  // around its dot, and a dot that had to be glued to the word would have
  // needed a rule in the stylesheet for each of them. It is still the label's
  // own dot — the same item owns both, so a hidden name hides its dot.
  function addDot(forecast) {
    const dot = document.createElement('i');
    dot.className = forecast ? 'mapdot' : 'mapdot absent';
    holder.appendChild(dot);
    return dot;
  }

  const states = STATE_LABELS.map((unit) => add(
    'state', unit.name, [unit.lon, unit.lat],
    { code: unit.code, fit: unit.fit, pad: 2, tries: NAME_TRIES }));

  const cities = CITY_LABELS.map((city) => add(
    city.forecast ? 'city' : 'city absent', city.name,
    [city.lon, city.lat],
    { pad: 6, tries: CITY_TRIES, dot: addDot(city.forecast) }));

  const chosen = add('chosen', '', null, { pad: 9, tries: CHOSEN_TRIES });

  // The order the names are placed in, and the whole of the "which name
  // matters" question. SPEC 11.30: the chosen square first, then the cities
  // largest first, then the units largest first in what is left.
  //
  // It was the other way round, and states-first cost too much: 36 unit
  // names took the room and eight city names fitted around them, on a map
  // whose point is the places people look for. A unit's name is the quieter
  // of the two in any case, and no unit loses its label by being last —
  // whatever is left of it is always at least its two letter code.
  const items = [chosen, ...cities, ...states];

  // Measured, not guessed: the halo and the font are set in CSS and the
  // browser is the only thing that knows how wide a word came out. Measured
  // once, too — a word's width does not change when the map moves, and
  // reading offsetWidth after writing a style forces the browser to lay the
  // page out again, which on every frame of a drag is the one thing here
  // that could be slow.
  function measure(item) {
    const { element } = item;
    element.style.display = '';
    element.textContent = item.text;
    item.w = element.offsetWidth;
    item.h = element.offsetHeight;
    if (item.code) {
      element.textContent = item.code;
      item.codeW = element.offsetWidth;
      element.textContent = item.text;
    }
  }

  function forget() { for (const item of items) item.w = 0; }

  // Where a word of this size would sit, for one placement.
  function boxFor(at, w, h, gap, side) {
    if (side === 'right') return [at.x + gap, at.y - h / 2];
    if (side === 'left') return [at.x - gap - w, at.y - h / 2];
    if (side === 'above') return [at.x - w / 2, at.y - gap - h];
    if (side === 'below') return [at.x - w / 2, at.y + gap];
    // The corners, at the same distance from the point along both axes.
    const step = gap * Math.SQRT1_2;
    if (side === 'ne') return [at.x + step, at.y - step - h];
    if (side === 'nw') return [at.x - step - w, at.y - step - h];
    if (side === 'se') return [at.x + step, at.y + step];
    if (side === 'sw') return [at.x - step - w, at.y + step];
    return [at.x - w / 2, at.y - h / 2]; // centre
  }

  /**
   * Is this unit's full name inside this unit, at this zoom? SPEC 11.31.
   *
   * The word's own box, centred on the label point, is unprojected back to
   * degrees and handed to the table measured against the polygon itself. The
   * half sizes are the larger side of each axis, so the box tested contains
   * the box drawn: Mercator puts the label point a hair off the middle of
   * the box in latitude, and the error is to the safe side of the border.
   */
  function nameInside(map, at, item) {
    if (!item.fit || !item.lngLat) return false;
    const [left, top] = boxFor(at, item.w, item.h, 0, 'centre');
    const nw = map.unproject([left, top]);
    const se = map.unproject([left + item.w, top + item.h]);
    const halfLon = Math.max(Math.abs(se.lng - item.lngLat[0]),
      Math.abs(item.lngLat[0] - nw.lng));
    const halfLat = Math.max(Math.abs(nw.lat - item.lngLat[1]),
      Math.abs(item.lngLat[1] - se.lat));
    item.box = [nw.lng, se.lat, se.lng, nw.lat];
    const ok = fitsInside(FIT_ASPECTS, item.fit, halfLon, halfLat);
    // What the rule was given and what it said, for the browser check.
    item.tried = { name: item.text, halfLon, halfLat,
      aspect: halfLon / halfLat, room: roomFor(FIT_ASPECTS, item.fit,
        halfLon / halfLat), ok };
    return ok;
  }

  function draw() {
    const map = mapFor();
    if (!map) return;
    const canvas = map.getContainer();
    const wide = canvas.clientWidth;
    const high = canvas.clientHeight;
    const placed = [];

    const hide = (item) => {
      item.element.style.display = 'none';
      item.drawn = null;
      if (item.dot) item.dot.style.display = 'none';
    };

    // Where everything is, before anything is placed. Off the canvas is not
    // drawn, and not allowed to block anything that is.
    const where = new Map();
    for (const item of items) {
      if (!item.lngLat) continue;
      const point = map.project(item.lngLat);
      if (point.x < -40 || point.y < -40
        || point.x > wide + 40 || point.y > high + 40) continue;
      where.set(item, point);
    }

    // A dot is at the town, and the town is where it is: a name can move and
    // a dot cannot, so every dot's box is taken before any name is placed.
    // Without this a state's name was written straight through the dots of
    // towns whose own names had been pushed somewhere else — "UTTAR P•ADESH"
    // was Lucknow's dot sitting in the middle of the word. The box is a
    // claim, not a drawing: the dot itself still appears only if its own
    // name found a place.
    for (const item of cities) {
      const point = where.get(item);
      if (!point) continue;
      placed.push({
        owner: item,
        box: [point.x - 4, point.y - 4, point.x + 4, point.y + 4],
      });
    }

    for (const item of items) {
      const at = where.get(item);
      if (!at) {
        hide(item);
        continue;
      }
      if (!item.w) measure(item);

      let put = null;
      // The full name at its own point, then the code anywhere near it.
      //
      // SPEC 11.31. A unit's name is offered one placement, the middle of
      // the unit, and is offered it only when the whole word is inside the
      // unit's own polygon at this zoom. It is not a name for the
      // neighbours, so it is not written on them: the two letter code marks
      // the unit until the reader zooms in far enough for the name to fit.
      // The clash rule still applies to the name at that one placement, so
      // a name that would be written over a city is a code too.
      const words = [];
      if (item.code) {
        if (nameInside(map, at, item)) {
          words.push([item.text, item.w, '', item.tries, item.pad]);
        }
        words.push([item.code, item.codeW, 'coded', CODE_TRIES, 1]);
      } else {
        words.push([item.text, item.w, '', item.tries, item.pad]);
      }
      for (const [text, width, how, tries, pad] of words) {
        for (const [side, gap] of tries) {
          const [left, top] = boxFor(at, width, item.h, gap, side);
          // Inside the canvas, or it is drawn cut in half: Kavaratti sat at
          // the western edge with its name running off the side of the map.
          if (left < 0 || top < 0
            || left + width > wide || top + item.h > high) continue;
          const box = [left - pad, top - pad,
            left + width + pad, top + item.h + pad];
          // A name is allowed to sit on its own dot, and on nothing else.
          const clash = placed.some(({ owner, box: other }) => owner !== item
            && !(box[2] < other[0] || box[0] > other[2]
              || box[3] < other[1] || box[1] > other[3]));
          if (!clash) {
            put = { text, left, top, side, how, box };
            break;
          }
        }
        if (put) break;
      }

      // SPEC 11.30. A unit is never left unlabelled: if neither its name nor
      // its code found a clear place, the code is written at the unit's own
      // point anyway, clamped inside the canvas. Two letters over a colour
      // is a worse map than two letters in a gap, and no label at all is a
      // worse map than either — Assam had no label on it before this.
      if (!put && item.code) {
        // Of the placements that are all taken, the one that covers the
        // least of what is already there. Written over something is the
        // last resort; written over as little as possible is the least bad
        // way to do it.
        let best = null;
        for (const [side, gap] of CODE_TRIES) {
          const [left, top] = boxFor(at, item.codeW, item.h, gap, side);
          const x = Math.min(Math.max(left, 0),
            Math.max(wide - item.codeW, 0));
          const y = Math.min(Math.max(top, 0), Math.max(high - item.h, 0));
          const box = [x, y, x + item.codeW, y + item.h];
          let over = 0;
          for (const { owner, box: other } of placed) {
            if (owner === item) continue;
            const across = Math.min(box[2], other[2]) - Math.max(box[0],
              other[0]);
            const down = Math.min(box[3], other[3]) - Math.max(box[1],
              other[1]);
            if (across > 0 && down > 0) over += across * down;
          }
          if (!best || over < best.over) {
            best = { over, text: item.code, left: x, top: y, side,
              how: 'forced', box };
          }
          if (over === 0) break;
        }
        put = best;
      }

      if (!put) {
        hide(item);
        continue;
      }
      placed.push({ owner: item, box: put.box });
      // SPEC 11.31. Where a full name was drawn, in degrees, for the check
      // that every name on screen is inside the unit it names. `item.box` is
      // the box nameInside just unprojected, and a name has one placement,
      // so it is the box of the word that went on the map.
      item.drawn = item.code && put.how === '' ? item.box : null;
      const { element } = item;
      element.style.display = '';
      element.textContent = put.text;
      element.dataset.side = put.side;
      element.dataset.how = put.how;
      element.style.transform = `translate(${Math.round(put.left)}px, `
        + `${Math.round(put.top)}px)`;
      if (item.dot) {
        item.dot.style.display = '';
        item.dot.style.transform = `translate(${Math.round(at.x - 3)}px, `
          + `${Math.round(at.y - 3)}px)`;
      }
    }
  }

  return {
    draw,
    resized() { forget(); draw(); },
    setChosen(square, name) {
      chosen.lngLat = square ? [square.lon, square.lat] : null;
      chosen.text = square
        ? (name || squareText(square.lat, square.lon)) : '';
      chosen.w = 0;
      draw();
    },
    remove() { holder.remove(); },
    // For the browser checks: what is actually on screen, by rank.
    shown() {
      const seen = { states: [], cities: [], coded: [], forced: [],
        boxes: [], tried: [] };
      for (const item of states) {
        if (item.drawn) seen.boxes.push({ name: item.text, box: item.drawn });
        if (item.tried) seen.tried.push(item.tried);
      }
      for (const item of states) {
        if (item.element.style.display === 'none') continue;
        const how = item.element.dataset.how;
        if (how === 'forced') seen.forced.push(item.code);
        else if (how === 'coded') seen.coded.push(item.code);
        else seen.states.push(item.text);
      }
      for (const item of cities) {
        if (item.element.style.display !== 'none') seen.cities.push(item.text);
      }
      return seen;
    },
  };
}

export default function ForecastMap({
  counts, grid, threshold, day, square, squareName, onPick, onProblem,
  unitBox,
  handcheck,
}) {
  const holder = useRef(null);
  const map = useRef(null);
  const labels = useRef(null);
  const ready = useRef(false);
  const touched = useRef(false);
  // The chosen square, for the resize watcher, which is made once and so
  // cannot see a prop (SPEC 11.32).
  const chosen = useRef(null);
  // SPEC 11.38. The state or union territory the map is being held on, so
  // that a resize -- the panel opening or closing, which on a phone changes
  // the map's height by a factor of four -- fits it again rather than
  // leaving a view that was fitted to a 64 pixel strip.
  const unitHeld = useRef(null);
  chosen.current = square;

  // Create the map once. MapLibre owns the canvas for the life of the page;
  // React never re-creates it.
  useEffect(() => {
    if (map.current || !holder.current) return undefined;

    // SPEC 11.29. Neither of these used to be checked, and both of them end
    // the same way for a reader: an empty rectangle the size of the map.
    if (!canDraw()) {
      onProblem('webgl2');
      return undefined;
    }
    let created;
    try {
      created = new maplibregl.Map({
        container: holder.current,
        style: EMPTY_STYLE,
        bounds: INDIA,
        maxBounds: LIMITS,
        // SPEC 11.38. It was 3, and 3 is above the zoom that fits India on
        // a phone, so the fit was silently clamped and the south of the
        // country was off the bottom of the screen: 18.7 to 38.6 N in a
        // 390 by 664 browser, which is Kerala, Tamil Nadu, Karnataka and
        // half of Andhra Pradesh not drawn at all on first load.
        //
        // MapLibre's world is 512 pixels at zoom 0, so 6 to 38 N is 0.0488
        // of it at every zoom, which is 200 pixels at zoom 3 and 400 at
        // zoom 4. A phone's map box is 261 pixels tall with 108 of them
        // spent on the padding that keeps India clear of the zoom buttons
        // and the attribution, so the fit needs zoom 2.62 and could not
        // have it. Two is below that with room to spare, and maxBounds
        // still stops anybody wandering off the country.
        minZoom: 2,
        maxZoom: 9,
        dragRotate: false,
        // SPEC 11.39. One finger scrolls the page and two move the map,
        // which is MapLibre's own cooperativeGestures and its own hint.
        //
        // The page scrolls now, and a map that takes a one-finger drag
        // inside a scrolling page is a trap: the map is 365 pixels of a
        // 664 pixel screen, so a reader who puts a thumb down to scroll
        // past it lands on the map more often than not and the page does
        // not move. The same option asks for ctrl with the wheel, which
        // is the same bargain for a mouse.
        //
        // Tapping a square is untouched: a tap is not a gesture.
        cooperativeGestures: true,
        pitchWithRotate: false,
        attributionControl: false,
        // SPEC 11.25: reading a pixel back from a WebGL canvas needs this,
        // and it costs every reader a copy on every frame, so HC8 asks for it
        // with ?handcheck=1 and the map everyone else loads does without it.
        //
        // It must go inside `canvasContextAttributes`. MapLibre 6 takes the
        // WebGL attributes as one object and **ignores a top level
        // `preserveDrawingBuffer` in silence**, which is how this was
        // written first: `?handcheck=1` changed nothing at all, every pixel
        // read back was transparent black, and HC8 could not have run. The
        // page now says what it got (`mapFacts`) so the hand check can
        // refuse to go on if the flag did not take.
        canvasContextAttributes: {
          preserveDrawingBuffer: Boolean(handcheck),
        },
      });
    } catch (error) {
      onProblem('maplibre');
      return undefined;
    }
    created.addControl(
      new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    created.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution:
        'Outlines, states and towns: Natural Earth, public domain. '
        + 'Rendering: MapLibre GL JS',
    }), 'bottom-right');
    // The compact control still renders open, and on a phone it is two lines
    // wide enough to sit on top of the legend's class labels. Nothing we use
    // requires on-map attribution — Natural Earth asks for none and MapLibre
    // is BSD-3 — and the footer carries both in full, so it starts closed and
    // opens when somebody asks for it.
    const attribution = created.getContainer()
      .querySelector('.maplibregl-ctrl-attrib');
    if (attribution) {
      attribution.classList.remove('maplibregl-compact-show');
      if (attribution.tagName === 'DETAILS') attribution.open = false;
      const details = attribution.querySelector('details');
      if (details) details.open = false;
    }
    created.getCanvas().setAttribute(
      'aria-label',
      'Map of India. Every 0.25 degree square is coloured by how many of 51 '
      + 'model runs reach the chosen amount of rain. Everything the map '
      + 'shows is also written in the panel, and a square can be chosen by '
      + 'name or by typing a latitude and longitude.');

    /**
     * The fit, with room left for everything drawn on top of the map.
     *
     * SPEC 11.28. The first build fitted India into the whole canvas and then
     * drew the legend and the zoom buttons over the result, so the legend sat
     * on the Bay of Bengal and the controls card covered Tamil Nadu and
     * Kerala. Neither the controls nor the legend is over the map any more;
     * MapLibre's own zoom buttons and attribution still are, so their boxes
     * are measured and the fit is given that much padding. Measured rather
     * than assumed: a control's size depends on the font the reader has, and
     * a number typed in here would be a guess about their browser.
     */
    const overlap = () => {
      const canvas = created.getContainer().getBoundingClientRect();
      const gap = 10;
      const box = (element) => {
        if (!element) return null;
        const seen = element.getBoundingClientRect();
        return seen.width && seen.height ? seen : null;
      };
      const right = [];
      const bottom = [];
      const top = [];
      for (const control of created.getContainer()
        .querySelectorAll('.maplibregl-ctrl-top-right .maplibregl-ctrl')) {
        const seen = box(control);
        if (seen) {
          right.push(canvas.right - seen.left);
          top.push(seen.bottom - canvas.top);
        }
      }
      const most = (list) => (list.length ? Math.max(...list) : 0);
      // Never more than a third of the canvas: a padding bigger than that
      // would zoom India down to nothing on a small screen, which is worse
      // than a legend over the sea.
      const cap = (value, whole) => Math.min(value + gap, whole / 3);
      // SPEC 11.38. The top is the gap and nothing else.
      //
      // The zoom buttons are 58 pixels tall in the top **right** corner,
      // and padding the whole top edge by 68 of a phone's 261 pixel map
      // took a quarter of the height away from the fit. The fit then
      // wanted a zoom below the minimum, was clamped, and drew 18.7 to
      // 38.6 N: Kerala, Tamil Nadu, Karnataka and half of Andhra Pradesh
      // were off the bottom of the screen on first load.
      //
      // Padding the right is what keeps the country clear of the buttons,
      // because that is the edge they are on. What the buttons cover once
      // the fit is right is the top right of the **box** of SPEC 1.4,
      // which is 38 N 98 E and thereabouts -- China, drawn beige, with no
      // forecast square anywhere near it. Nothing of India is under them.
      const seenRight = most(right);
      // SPEC 11.40. The left edge is padded by nothing.
      //
      // 11.39 floated the colour key in the map's lower left corner at
      // 1280 pixels and over, and paid for it here: the left edge was
      // padded by the key's own measured width, so that India began to
      // the right of it and nothing of the country was ever behind it.
      //
      // The key is off the canvas at every width now, so there is nothing
      // to pay for and the whole box of 1.4 gets the whole canvas. What
      // is over the map is MapLibre's own zoom buttons and its
      // attribution, which are the three things measured above.
      return {
        top: gap,
        right: cap(seenRight, canvas.width),
        bottom: cap(most(bottom), canvas.height),
        left: gap,
      };
    };

    const refit = () => {
      created.fitBounds(INDIA, {
        padding: overlap(), duration: 0, animate: false,
      });
    };

    created.on('load', () => {
      created.addSource('land', { type: 'geojson', data: landAround });
      created.addSource('india', { type: 'geojson', data: indiaOutline });
      created.addSource('states', { type: 'geojson', data: stateLines });
      created.addSource('squares', { type: 'geojson', data: NOTHING });
      created.addSource('picked', { type: 'geojson', data: NOTHING });
      created.addSource('picked-centre', { type: 'geojson', data: NOTHING });

      // Everything that is land, including India, in one quiet colour. It
      // is under India's own fill, so the country still ends exactly where
      // the point-of-view outline says it does, and it is a fill with no
      // line on it at all: the only boundary this map draws between India
      // and anywhere else is that outline (SPEC 11.14 and 11.30).
      created.addLayer({
        id: 'land-fill',
        type: 'fill',
        source: 'land',
        paint: { 'fill-color': NEIGHBOURS, 'fill-antialias': true },
      });
      created.addLayer({
        id: 'india-fill',
        type: 'fill',
        source: 'india',
        paint: { 'fill-color': LAND },
      });
      // Where a basemap would go: over our own white land fill, under the
      // squares. Empty, and drawing nothing, until there is one.
      created.addLayer({
        id: SLOT_BASEMAP,
        type: 'background',
        paint: { 'background-opacity': 0 },
      });
      created.addLayer({
        id: 'squares',
        type: 'fill',
        source: 'squares',
        paint: {
          'fill-color': fillExpression(countKey(threshold, day)),
          'fill-opacity': SQUARE_OPACITY,
          // A 0.25 degree square has a hard edge in the data, so there is
          // nothing to soften and a blend per edge pixel to save.
          'fill-antialias': false,
        },
      });
      // The grid, SPEC 11.29: every square's own edges, faintly, and only
      // where a square is at least twelve pixels across. Drawn from the same
      // source as the fill, so a line cannot appear where there is no square.
      created.addLayer({
        id: 'squares-grid',
        type: 'line',
        source: 'squares',
        paint: {
          'line-color': GRID_LINE,
          'line-width': 0.5,
          'line-opacity': ['step', ['zoom'], 0, GRID_FROM_ZOOM, GRID_OPACITY],
        },
      });
      created.addLayer({
        id: 'states',
        type: 'line',
        source: 'states',
        paint: { 'line-color': STATE_LINE, 'line-width': 0.6 },
      });
      created.addLayer({
        id: 'india-line',
        type: 'line',
        source: 'india',
        paint: { 'line-color': COAST, 'line-width': 1 },
      });

      // The chosen square. No fill of any kind, and no palette colour: its
      // own outline, white under dark, from the zoom where the square is big
      // enough to have an outline, and below that a ring of a fixed 18
      // pixels in the same two colours.
      created.addLayer({
        id: 'picked-casing',
        type: 'line',
        source: 'picked',
        paint: {
          'line-color': HALO,
          'line-width': 4,
          'line-opacity': ['step', ['zoom'], 0, GRID_FROM_ZOOM, 1],
        },
      });
      created.addLayer({
        id: 'picked-line',
        type: 'line',
        source: 'picked',
        paint: {
          'line-color': MARK,
          'line-width': 1.6,
          'line-opacity': ['step', ['zoom'], 0, GRID_FROM_ZOOM, 1],
        },
      });
      created.addLayer({
        id: 'picked-ring-halo',
        type: 'circle',
        source: 'picked-centre',
        paint: {
          'circle-radius': RING,
          'circle-opacity': 0,
          'circle-stroke-width': 4,
          'circle-stroke-color': HALO,
          'circle-stroke-opacity': ['step', ['zoom'], 0.95,
            GRID_FROM_ZOOM, 0],
        },
      });
      created.addLayer({
        id: 'picked-ring',
        type: 'circle',
        source: 'picked-centre',
        paint: {
          'circle-radius': RING,
          'circle-opacity': 0,
          'circle-stroke-width': 2,
          'circle-stroke-color': MARK,
          'circle-stroke-opacity': ['step', ['zoom'], 1, GRID_FROM_ZOOM, 0],
        },
      });
      // Where place labels would go: over everything, including the squares.
      created.addLayer({
        id: SLOT_LABELS,
        type: 'background',
        paint: { 'background-opacity': 0 },
      });

      ready.current = true;
      refit();
      if (labels.current) labels.current.draw();
      created.getContainer().dataset.ready = '1';

      // Measure the words again once the page has stopped moving. SPEC
      // 11.31. A word's width is measured once and kept, because reading it
      // back forces the browser to lay the page out again and doing that on
      // every frame of a drag is the one thing here that could be slow — but
      // the first draw happens while the map is still being fitted to a
      // container flexbox is still sizing, and a width measured then is kept
      // for the rest of the page's life. It showed up as a label count that
      // changed from one load to the next: 26 city names on one load of the
      // same page at the same size and 31 on the next. One more pass, when
      // nothing is moving any more, and the map is the same map every time.
      created.once('idle', () => {
        if (labels.current) labels.current.resized();
        // SPEC 11.38. And fit again now that nothing is moving. The first
        // fit happens on `load`, which can be before the flexbox has given
        // the map its real height; the ResizeObserver catches most of
        // that, and this catches the rest. It does nothing at all if the
        // reader has already moved the map themselves.
        if (!touched.current) refit();
      });
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => {
          if (labels.current) labels.current.resized();
        });
      }
    });

    labels.current = makeLabels(created.getContainer(), () => map.current);
    const redraw = () => { if (labels.current) labels.current.draw(); };
    created.on('move', redraw);
    created.on('zoom', redraw);

    // The container is sized by flexbox and by the bottom sheet, and it is
    // not necessarily final when the map is created: the first build fitted
    // India to a container that then grew, and cut the south of the country
    // off. Watching the element and refitting is cheap and cannot be wrong.
    const moved = () => { touched.current = true; unitHeld.current = null; };
    created.on('dragstart', moved);
    created.on('zoomstart', (event) => { if (event.originalEvent) moved(); });

    const watcher = new ResizeObserver(() => {
      created.resize();
      if (labels.current) labels.current.resized();
      if (!ready.current) return;
      // SPEC 11.38. A state is being held, so it is fitted again at the
      // map's new size. On a phone the panel opening takes the map from
      // 227 pixels to 64 and closing it gives them back, and a view fitted
      // to the 64 is not a view of that state.
      if (unitHeld.current) {
        const held = unitHeld.current;
        created.fitBounds([[held[0], held[1]], [held[2], held[3]]],
          { padding: 12, duration: 0, animate: false });
      } else if (!touched.current) {
        // Refit only while the reader has not moved the map themselves:
        // yanking somebody back to the whole country because a panel opened
        // would be worse than the cut-off country this fixes.
        refit();
      }
      // SPEC 11.32. Whether or not it was refitted, the square the reader
      // chose has to still be on the map afterwards. This is the phone: the
      // sheet opens, the map is half as tall, and the refit cannot help
      // because India does not fit in 236 pixels at the minimum zoom. It
      // runs even when the reader has moved the map themselves, because it
      // only ever pans, and it does nothing at all while the square is
      // comfortably in view.
      bringIntoView(created, chosen.current);
    });
    watcher.observe(holder.current);

    map.current = created;
    // For the browser checks, and for nothing else: which names are on
    // screen, and the zoom the grid appears at.
    created.getContainer().labelsShown = () => (
      labels.current ? labels.current.shown() : null);
    created.getContainer().gridFromZoom = GRID_FROM_ZOOM;
    // The view itself, for the checks that have to know what is on screen:
    // which zoom, and which corner of the world is in which corner of the
    // canvas (SPEC 11.25, 11.31).
    // What the map is made of, for HC8 (SPEC 11.25). The hand check samples
    // a drawn pixel and compares it with a palette hex, and that comparison
    // is only meaningful while the basemap slot is empty, the squares are
    // drawn at full opacity, and nothing in NOT_DATA_LAYERS is painting over
    // the square it samples. It has to be able to assert all three on the
    // live page rather than trust the source it cannot see, so the page says
    // them out loud. Reading only, and nothing here changes what is drawn.
    created.getContainer().mapFacts = () => {
      const order = created.getStyle().layers.map((layer) => layer.id);
      const land = order.indexOf('india-fill');
      const squares = order.indexOf('squares');
      return {
        zoom: created.getZoom(),
        gridFromZoom: GRID_FROM_ZOOM,
        // Whether the pixel can be read back at all. HC8 asserts this
        // before it believes a single colour it sampled.
        preserveDrawingBuffer: Boolean(created.getCanvas()
          .getContext('webgl2').getContextAttributes()
          .preserveDrawingBuffer),
        // Everything between our own land fill and the squares, with the
        // slot marker itself taken out. Empty means no basemap is drawn
        // under the squares, which is the promise of SPEC 11.14.
        basemapSlot: order.slice(land + 1, squares)
          .filter((id) => id !== SLOT_BASEMAP),
        slotOpacity: created.getPaintProperty(SLOT_BASEMAP,
          'background-opacity'),
        squareOpacity: created.getPaintProperty('squares', 'fill-opacity'),
        // The mark on the chosen square: how many features of it are in
        // view at all. None, and none of the ring or outline layers can put
        // a pixel anywhere near what is being sampled.
        picked: created.querySourceFeatures('picked').length
          + created.querySourceFeatures('picked-centre').length,
        notData: NOT_DATA_LAYERS.map((id) => {
          const layer = created.getLayer(id);
          const key = layer.type === 'circle'
            ? 'circle-stroke-opacity' : 'line-opacity';
          return [id, created.getPaintProperty(id, key)];
        }),
        layers: order,
      };
    };
    // SPEC 11.39. Fit again, for the colour key: opening or shutting it
    // changes the width the fit is padded by, and nothing else on the page
    // can tell the map that. It does nothing while the reader has moved
    // the map themselves, like every other refit here.
    created.getContainer().refit = () => { if (!touched.current) refit(); };
    created.getContainer().mapView = () => {
      const box = created.getBounds();
      return { zoom: created.getZoom(),
        bounds: [box.getWest(), box.getSouth(),
          box.getEast(), box.getNorth()] };
    };

    return () => {
      watcher.disconnect();
      if (labels.current) labels.current.remove();
      labels.current = null;
      created.remove();
      map.current = null;
      ready.current = false;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Clicking anywhere picks the square under the pointer. The caller snaps
  // it; this hands over raw degrees and nothing else.
  useEffect(() => {
    const created = map.current;
    if (!created) return undefined;
    const click = (event) => onPick(event.lngLat.lat, event.lngLat.lng);
    const hand = () => { created.getCanvas().style.cursor = 'pointer'; };
    const plain = () => { created.getCanvas().style.cursor = ''; };
    created.on('click', click);
    created.on('mouseenter', 'squares', hand);
    created.on('mouseleave', 'squares', plain);
    return () => {
      created.off('click', click);
      created.off('mouseenter', 'squares', hand);
      created.off('mouseleave', 'squares', plain);
    };
  }, [onPick]);

  // The squares, built once, when all fifteen counts files have arrived.
  useEffect(() => {
    const created = map.current;
    if (!created || !counts || !grid) return;
    const put = () => {
      const source = created.getSource('squares');
      if (!source) return;
      source.setData(buildSquares(counts, grid));
    };
    if (ready.current) put();
    else created.once('load', put);
  }, [counts, grid]);

  /**
   * Fit the map to a state or union territory. SPEC 11.38.
   *
   * A reader who types "Kerala" is told that a state is too big for one
   * forecast and is given the cities inside it; this is the other half of
   * that answer -- the map goes to Kerala, so the reader can see the shape
   * they are being asked to pick a point in and can tap it.
   *
   * It paints nothing. No square is chosen, no count is shown for a state,
   * and the colours under the outline are the same colours they were.
   *
   * `unitBox` is the unit's own bounding box from units.json, rounded
   * outwards, so the whole of the unit is in view. The reader has now moved
   * the map themselves as far as the resize watcher is concerned, which is
   * why `touched` is set: a panel opening must not yank them back to the
   * whole country afterwards.
   */
  useEffect(() => {
    const created = map.current;
    if (!created || !unitBox || unitBox.length !== 4) return;
    const go = () => {
      touched.current = true;
      unitHeld.current = unitBox;
      created.fitBounds(
        [[unitBox[0], unitBox[1]], [unitBox[2], unitBox[3]]],
        { padding: 12, duration: 500 });
    };
    if (ready.current) go();
    else created.once('load', go);
  }, [unitBox ? unitBox.join(',') : null]); // eslint-disable-line react-hooks/exhaustive-deps

  /* SPEC 11.40. The refit when the colour key opened or shut is gone
     with the key's place over the canvas: opening it changes the size of
     a box in the panel beside the map, which the fit knows nothing
     about. The refit on a resize of the container is still there, and it
     is what answers a window being made wider or a phone turned. */

  // Changing day or threshold: one paint property, nothing else.
  useEffect(() => {
    const created = map.current;
    if (!created) return;
    const paint = () => {
      if (!created.getLayer('squares')) return;
      created.setPaintProperty(
        'squares', 'fill-color', fillExpression(countKey(threshold, day)));
    };
    if (ready.current) paint();
    else created.once('load', paint);
  }, [threshold, day]);

  // SPEC 11.38. Choosing a square ends the hold on a state: from here the
  // view is governed by the square the reader picked, as it always was.
  useEffect(() => {
    if (square) unitHeld.current = null;
  }, [square && `${square.lat},${square.lon}`]); // eslint-disable-line react-hooks/exhaustive-deps

  // The chosen square: the outline, the ring, and the name beside it.
  useEffect(() => {
    const created = map.current;
    if (!created) return;
    const put = () => {
      const outline = created.getSource('picked');
      const centre = created.getSource('picked-centre');
      if (outline) outline.setData(selectedShape(square));
      if (centre) centre.setData(selectedCentre(square));
      if (labels.current) labels.current.setChosen(square, squareName);
    };
    if (ready.current) put();
    else created.once('load', put);
  }, [square, squareName]);

  // Bring the chosen square into view. SPEC 11.32.
  //
  // Choosing a place and not being shown it is the oldest fault a map can
  // have, and it happened here three ways: a town searched for while the map
  // was somewhere else, a square at the very edge with its ring half drawn,
  // and -- on a phone -- a square that was in the middle of the map until
  // the bottom sheet opened and made the map half as tall. The map pans by
  // as little as will do, at the zoom it is already at.
  useEffect(() => {
    const created = map.current;
    if (!created || !square || !ready.current) return undefined;
    let alive = true;
    // Two frames first. Choosing a square opens the sheet, which resizes
    // the map, and measuring before that is laid out measures a map that is
    // about to change out from under the answer.
    const frame = requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!alive || map.current !== created) return;
      bringIntoView(created, square);
    }));
    return () => { alive = false; cancelAnimationFrame(frame); };
  }, [square]);

  return <div className="map" ref={holder} />;
}
