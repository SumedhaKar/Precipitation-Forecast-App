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
import { CITY_LABELS, STATE_LABELS } from './places';
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
// A unit's own name is only ever near the middle of the unit, because the
// point it belongs to is the unit and not a dot: eight or sixteen pixels is
// a nudge off a neighbour, half a degree at the whole-India view, and a
// bigger offset would start writing the name on the wrong state.
const CITY_TRIES = [
  ['right', 8], ['left', 8], ['above', 7], ['below', 7],
  ['right', 18], ['left', 18], ['above', 15], ['below', 15],
];
const STATE_TRIES = [['centre', 0]];
for (const away of [8, 16]) {
  for (const side of ['above', 'below', 'left', 'right',
    'ne', 'nw', 'se', 'sw']) {
    STATE_TRIES.push([side, away]);
  }
}

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

// How wide a unit's name may be, as a multiple of the unit's own width
// where the name goes. Small states have their names written across their
// borders on every printed map there is, so this is generous; what it rules
// out is a name many times longer than the thing it names, which is a name
// for the neighbours and not for the unit.
const NAME_OVERHANG = 4;

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
    { code: unit.code, span: unit.span, pad: 2, tries: STATE_TRIES }));

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

  function draw() {
    const map = mapFor();
    if (!map) return;
    const canvas = map.getContainer();
    const wide = canvas.clientWidth;
    const high = canvas.clientHeight;
    const placed = [];

    const hide = (item) => {
      item.element.style.display = 'none';
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
      // The full name in every placement first, then the code in every
      // placement. A state is better named in an awkward spot than reduced
      // to two letters in a tidy one — but only if the name belongs to the
      // unit it is written on. `span` is how wide the unit is where the name
      // goes (SPEC 11.29), and a name may hang over that by its own length
      // again on each side; wider than that and it is not a name for this
      // unit any more but a word written across its neighbours, so the
      // two letter code marks the unit until the reader zooms in far enough
      // for the name to fit. Without this the map wrote DADRA AND NAGAR
      // HAVELI AND DAMAN AND DIU across 230 pixels of the Arabian Sea for a
      // union territory seven pixels wide.
      const words = [];
      if (item.code) {
        const edge = map.project([item.lngLat[0] + item.span, item.lngLat[1]]);
        if (item.w <= (edge.x - at.x) * NAME_OVERHANG) {
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
      const seen = { states: [], cities: [], coded: [], forced: [] };
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
  handcheck,
}) {
  const holder = useRef(null);
  const map = useRef(null);
  const labels = useRef(null);
  const ready = useRef(false);
  const touched = useRef(false);

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
        minZoom: 3,
        maxZoom: 9,
        dragRotate: false,
        pitchWithRotate: false,
        attributionControl: false,
        // SPEC 11.25: reading a pixel back from a WebGL canvas needs this,
        // and it costs every reader a copy on every frame, so HC8 asks for it
        // with ?handcheck=1 and the map everyone else loads does without it.
        preserveDrawingBuffer: Boolean(handcheck),
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
      return {
        top: cap(most(top), canvas.height),
        right: cap(most(right), canvas.width),
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
    });

    labels.current = makeLabels(created.getContainer(), () => map.current);
    const redraw = () => { if (labels.current) labels.current.draw(); };
    created.on('move', redraw);
    created.on('zoom', redraw);

    // The container is sized by flexbox and by the bottom sheet, and it is
    // not necessarily final when the map is created: the first build fitted
    // India to a container that then grew, and cut the south of the country
    // off. Watching the element and refitting is cheap and cannot be wrong.
    const moved = () => { touched.current = true; };
    created.on('dragstart', moved);
    created.on('zoomstart', (event) => { if (event.originalEvent) moved(); });

    const watcher = new ResizeObserver(() => {
      created.resize();
      if (labels.current) labels.current.resized();
      // Refit only while the reader has not moved the map themselves:
      // yanking somebody back to the whole country because a panel opened
      // would be worse than the cut-off country this fixes.
      if (touched.current || !ready.current) return;
      refit();
    });
    watcher.observe(holder.current);

    map.current = created;
    // For the browser checks, and for nothing else: which names are on
    // screen, and the zoom the grid appears at.
    created.getContainer().labelsShown = () => (
      labels.current ? labels.current.shown() : null);
    created.getContainer().gridFromZoom = GRID_FROM_ZOOM;

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

  return <div className="map" ref={holder} />;
}
