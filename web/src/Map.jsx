// The map. SPEC 11.14, 11.16 and 11.17.
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
import { CLASSES, countKey, fillExpression } from './palette';
import { LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, STEP } from './snap';

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
const LIMITS = [[LON_MIN - 20, LAT_MIN - 12], [LON_MAX + 20, LAT_MAX + 12]];

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

const SEA = '#eaf0f4';
const LAND = '#ffffff';
const STATE_LINE = '#c9d2da';
const COAST = '#aab6c0';
const PICKED = '#0b2b4a';
const CITY_DOT = '#5b6b7b';

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
      properties: { name: city.name, lat: city.lat, lon: city.lon },
      geometry: { type: 'Point', coordinates: [city.lon, city.lat] },
    })),
  };
}

function selectedShape(square) {
  if (!square) return { type: 'FeatureCollection', features: [] };
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

const EMPTY_STYLE = {
  version: 8,
  sources: {},
  layers: [{
    id: 'sea',
    type: 'background',
    paint: { 'background-color': SEA },
  }],
};

export default function ForecastMap({
  counts, grid, threshold, day, square, onPick, padding, handcheck,
}) {
  const holder = useRef(null);
  const map = useRef(null);
  const ready = useRef(false);
  const touched = useRef(false);

  // Create the map once. MapLibre owns the canvas for the life of the page;
  // React never re-creates it.
  useEffect(() => {
    if (map.current || !holder.current) return undefined;
    const created = new maplibregl.Map({
      container: holder.current,
      style: EMPTY_STYLE,
      bounds: [[LON_MIN, LAT_MIN], [LON_MAX, LAT_MAX]],
      fitBoundsOptions: { padding: 20 },
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
        'Outlines: Natural Earth, public domain. Rendering: MapLibre GL JS',
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

    created.on('load', () => {
      created.addSource('india', { type: 'geojson', data: indiaOutline });
      created.addSource('states', { type: 'geojson', data: stateLines });
      created.addSource('squares', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      created.addSource('cities', { type: 'geojson', data: cityPoints() });
      created.addSource('picked', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
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
          'circle-stroke-color': '#ffffff',
        },
      });
      created.addLayer({
        id: 'picked',
        type: 'line',
        source: 'picked',
        paint: { 'line-color': PICKED, 'line-width': 2 },
      });
      // Where place labels would go: over everything, including the squares.
      created.addLayer({
        id: SLOT_LABELS,
        type: 'background',
        paint: { 'background-opacity': 0 },
      });

      ready.current = true;
      created.getContainer().dataset.ready = '1';
    });

    // The container is sized by flexbox and by the bottom sheet, and it is
    // not necessarily final when the map is created: the first build fitted
    // India to a container that then grew, and cut the south of the country
    // off. Watching the element and refitting is cheap and cannot be wrong.
    const moved = () => { touched.current = true; };
    created.on('dragstart', moved);
    created.on('zoomstart', (event) => { if (event.originalEvent) moved(); });

    const watcher = new ResizeObserver(() => {
      created.resize();
      // Refit only while the reader has not moved the map themselves:
      // yanking somebody back to the whole country because a panel opened
      // would be worse than the cut-off country this fixes.
      if (touched.current) return;
      created.fitBounds(
        [[LON_MIN, LAT_MIN], [LON_MAX, LAT_MAX]],
        { padding: 20, duration: 0, animate: false });
    });
    watcher.observe(holder.current);

    map.current = created;
    return () => {
      watcher.disconnect();
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

  // The chosen square's outline.
  useEffect(() => {
    const created = map.current;
    if (!created) return;
    const put = () => {
      const source = created.getSource('picked');
      if (source) source.setData(selectedShape(square));
    };
    if (ready.current) put();
    else created.once('load', put);
  }, [square]);

  // Keep India centred in the part of the canvas the panel is not covering.
  useEffect(() => {
    const created = map.current;
    if (!created || !padding) return;
    created.setPadding(padding, { duration: 0 });
  }, [padding]);

  return (
    <div className="map" ref={holder}>
      <Legend threshold={threshold} />
    </div>
  );
}

export function Legend({ threshold }) {
  return (
    <div className="legend" aria-label="What the colours mean">
      <p className="legend-head">
        <strong>N of 51 model runs</strong> reach {threshold} mm
      </p>
      <ul className="legend-rows">
        {CLASSES.map((band) => (
          <li key={band.label}>
            <span className="swatch" style={{ background: band.colour }} />
            {band.label}
          </li>
        ))}
      </ul>
      <p className="legend-foot">
        N of 51 model runs, which is not a calibrated probability.
      </p>
    </div>
  );
}
