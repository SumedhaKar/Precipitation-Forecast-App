// The map. SPEC 11.14, 11.16, 11.17 and 11.28.
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
// This module is loaded by a dynamic import(), so MapLibre's 295 KB does not
// hold up the run line, the stale banner or the panel.

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
import cityList from './cities.json';
import { LAND, SEA, countKey, fillExpression } from './palette';
import { LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STEP, squareText } from './snap';

maplibregl.setWorkerUrl(workerUrl);

const CITIES = cityList.cities;

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
const CITY_DOT = '#5b6b7b';

// SPEC 11.28. The chosen square is marked in the page's ink, which is a
// near-black warm grey and deliberately **not** in the palette: the first
// build drew the selection in #0b2b4a, and at the whole-India view a 0.25
// degree square is about four pixels wide, so a two pixel navy outline filled
// it in and the chosen square read as a square where all 51 model runs reach
// the threshold — the darkest colour on the scale. A mark must not be able to
// be mistaken for a measurement.
const MARK = '#1f2933';
const HALO = '#ffffff';

// The ring around the chosen square, in screen pixels.
//
// A 0.25 degree square is 0.3556 * 2^zoom pixels across in Web Mercator, so
// at the zoom that fits India it is about four pixels and at the closest zoom
// about 182. The ring is the larger of half the square's diagonal and 9, so
// it encloses the square when the square is big and is an 18 pixel ring when
// the square is a speck. It is drawn as two circles at the same radius, a
// white 4 px stroke under a dark 2 px one, which puts the halo on both sides.
//
// Written as a top-level `interpolate` rather than the `max` of a `^` that
// says the same thing, because the style spec allows `["zoom"]` only as the
// direct input of a top-level `step` or `interpolate`. The first build used
// the arithmetic form, MapLibre refused both layers with
// `"zoom" expression may only be used as input to a top-level "step" or
// "interpolate" expression`, and the chosen square had no ring at all.
//
// An exponential interpolation of base 2 over zoom *is* the square's own
// growth, so this is exact and not an approximation: flat at MIN_RING until
// the square's half-diagonal overtakes it, and equal to that half-diagonal
// from there to the closest zoom.
const MIN_RING = 9;                                 // 18 px across
const HALF_DIAGONAL = (STEP / 360) * 512 * Math.SQRT1_2;
const CROSSES_AT = Math.log2(MIN_RING / HALF_DIAGONAL);
const RING = ['interpolate', ['exponential', 2], ['zoom'],
  3, MIN_RING,
  CROSSES_AT, MIN_RING,
  9, HALF_DIAGONAL * 2 ** 9];

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

function cityPoints() {
  return {
    type: 'FeatureCollection',
    features: CITIES.map((city) => ({
      type: 'Feature',
      properties: { name: city.name },
      geometry: { type: 'Point', coordinates: [city.lon, city.lat] },
    })),
  };
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

/**
 * Place names, as elements over the canvas rather than a symbol layer.
 *
 * SPEC 11.28. MapLibre draws text from SDF glyph files it fetches from a
 * `glyphs` URL, and there is no such URL here on purpose: nothing on this map
 * comes from a third party, and a font server would be one. Rasterising the
 * glyphs ourselves would be a new build dependency for twenty words. So the
 * labels are twenty spans in a layer of their own above the canvas, moved by
 * the map's own projection on every frame, with the white halo done by four
 * text shadows. Being above the canvas puts them above every layer, including
 * SLOT_LABELS, which stays for a basemap's own labels.
 *
 * The declutter is a greedy pass in rank order: the chosen square's label
 * first, then the cities in the order cities.json lists them, and any label
 * whose box would touch one already placed is hidden. So the whole-India view
 * shows the few that fit and a close view shows all twenty, without a list of
 * "important" cities to argue about.
 */
function makeLabels(container, mapFor) {
  const holder = document.createElement('div');
  holder.className = 'maplabels';
  holder.setAttribute('aria-hidden', 'true'); // the panel carries the words
  container.appendChild(holder);

  const items = CITIES.map((city) => {
    const element = document.createElement('span');
    element.className = 'maplabel';
    element.textContent = city.name;
    holder.appendChild(element);
    return { element, lngLat: [city.lon, city.lat], chosen: false };
  });

  const chosen = document.createElement('span');
  chosen.className = 'maplabel chosen';
  holder.appendChild(chosen);
  const chosenItem = { element: chosen, lngLat: null, chosen: true };

  // Enough space around each name that the whole-India view shows the
  // handful that fit comfortably and a close view shows all twenty. The
  // number is the whole of the "which cities are important" question: there
  // is no list of important cities, only room or no room.
  const PAD = 9;

  function draw() {
    const map = mapFor();
    if (!map) return;
    const placed = [];
    const order = chosenItem.lngLat ? [chosenItem, ...items] : items;
    for (const item of order) {
      const { element } = item;
      if (!item.lngLat) {
        element.style.display = 'none';
        continue;
      }
      const at = map.project(item.lngLat);
      // Measured, not guessed: the halo and the font are set in CSS and the
      // browser is the only thing that knows how wide a word came out.
      element.style.display = '';
      const width = element.offsetWidth;
      const height = element.offsetHeight;
      const left = at.x + (item.chosen ? 13 : 6);
      const top = at.y - height / 2;
      const box = [left - PAD, top - PAD, left + width + PAD,
        top + height + PAD];
      const clash = placed.some((other) => !(box[2] < other[0]
        || box[0] > other[2] || box[3] < other[1] || box[1] > other[3]));
      if (clash) {
        element.style.display = 'none';
        continue;
      }
      placed.push(box);
      element.style.transform = `translate(${Math.round(left)}px, `
        + `${Math.round(top)}px)`;
    }
  }

  return {
    draw,
    setChosen(square, name) {
      chosenItem.lngLat = square ? [square.lon, square.lat] : null;
      chosen.textContent = square
        ? (name || squareText(square.lat, square.lon)) : '';
      draw();
    },
    remove() { holder.remove(); },
  };
}

export default function ForecastMap({
  counts, grid, threshold, day, square, squareName, onPick, handcheck,
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
    const created = new maplibregl.Map({
      container: holder.current,
      style: EMPTY_STYLE,
      bounds: INDIA,
      maxBounds: LIMITS,
      minZoom: 3,
      maxZoom: 9,
      dragRotate: false,
      pitchWithRotate: false,
      attributionControl: false,
      // SPEC 11.25: reading a pixel back from a WebGL canvas needs this, and
      // it costs every reader a copy on every frame, so HC8 asks for it with
      // ?handcheck=1 and the map everyone else loads does without it.
      preserveDrawingBuffer: Boolean(handcheck),
    });
    created.addControl(
      new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    created.addControl(new maplibregl.AttributionControl({
      compact: true,
      customAttribution:
        'Outlines and towns: Natural Earth, public domain. '
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
      created.addSource('india', { type: 'geojson', data: indiaOutline });
      created.addSource('states', { type: 'geojson', data: stateLines });
      created.addSource('squares', { type: 'geojson', data: NOTHING });
      created.addSource('cities', { type: 'geojson', data: cityPoints() });
      created.addSource('picked', { type: 'geojson', data: NOTHING });
      created.addSource('picked-centre', { type: 'geojson', data: NOTHING });

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
      created.addLayer({
        id: 'cities',
        type: 'circle',
        source: 'cities',
        paint: {
          'circle-radius': 2.6,
          'circle-color': CITY_DOT,
          'circle-stroke-width': 1,
          'circle-stroke-color': HALO,
        },
      });

      // The chosen square. No fill of any kind, and no palette colour: a
      // white casing, a dark edge that appears only once the square is big
      // enough on screen to have an edge worth drawing, and a ring that is
      // never smaller than 18 pixels across.
      created.addLayer({
        id: 'picked-casing',
        type: 'line',
        source: 'picked',
        paint: {
          'line-color': HALO,
          'line-width': 4,
          'line-opacity': ['step', ['zoom'], 0, 6, 1],
        },
      });
      created.addLayer({
        id: 'picked-line',
        type: 'line',
        source: 'picked',
        paint: {
          'line-color': MARK,
          'line-width': 1.6,
          'line-opacity': ['step', ['zoom'], 0, 6, 1],
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
          'circle-stroke-opacity': 0.95,
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
      redraw();
      // Refit only while the reader has not moved the map themselves:
      // yanking somebody back to the whole country because a panel opened
      // would be worse than the cut-off country this fixes.
      if (touched.current || !ready.current) return;
      refit();
    });
    watcher.observe(holder.current);

    map.current = created;
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

  // The chosen square: the ring, the edge, and the name beside it.
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
