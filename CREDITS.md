# Credits and licences

Everything this site shows comes from one of the sources below. Nothing on
the map comes from anywhere else: there is no basemap, no tile server, no
font server and no geocoder, so a reader's browser talks only to this site
and to the public store the forecast is published to.

**The only national boundary drawn anywhere on this site is India's own
outline**, from the Natural Earth India point-of-view edition, which is the
same geometry the forecast squares were cut with. The land around India is
shaded from a coastline-only layer that carries no boundary at all.

---

## The forecast

**ECMWF AIFS ENS open data**, 51 members, the 00 UTC run.

Copyright © 2026 European Centre for Medium-Range Weather Forecasts (ECMWF).

This data is published under a Creative Commons Attribution 4.0 International
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). ECMWF does not
accept any liability whatsoever for any error or omission in the data, their
availability, or for any loss or damage arising from their use.

- Source: <https://www.ecmwf.int>
- Licence: CC BY 4.0
- **Modified:** each member daily total is the difference between the run's
  accumulated total precipitation at the two 24-hour step boundaries of that
  day, and the counts published here are of how many of the 51 members reach
  1 mm, 10 mm and 50 mm in each 0.25 degree square on each of five days.

The attribution line is on the page itself, outside anything a reader has to
open: *Forecast: ECMWF AIFS ENS, CC BY 4.0.*

## The observations

**NASA GPM IMERG Late Precipitation L3 1 day V07C**, DOI
[10.5067/GPM/IMERGDL/DAY/07](https://doi.org/10.5067/GPM/IMERGDL/DAY/07).

Used for the track record only; it is not shown on the forecast page. IMERG
is a **satellite estimate, not ground truth**, and the site never calls it an
observation of what fell.

- Source: NASA Goddard Earth Sciences Data and Information Services Center
  (GES DISC), <https://disc.gsfc.nasa.gov>
- Access: an Earthdata login, which belongs to the person running the
  downloads and is never in this repository

## The map

**Natural Earth 1:10m**, all public domain. No permission is required and
none is implied by its use here.

| layer | what it draws |
|---|---|
| `ne_10m_admin_0_countries_ind` | India's outline — the **India point-of-view edition**, which is the same geometry the forecast mask was cut with, so the country on screen and the squares that are coloured are the same shape |
| `ne_10m_admin_1_states_provinces` | the state and union territory lines, and their names and label points. Only boundaries **shared by two Indian units** are drawn: Natural Earth publishes no point-of-view edition of admin-1, so an outer edge taken from it would be a different boundary from the one the mask was cut with |
| `ne_10m_populated_places` | the 215 towns the search offers, and the one city labelled in each unit |
| `ne_10m_land` | the land around India, as one quiet fill under India's own. It is **coastline and nothing else** — the layer holds no boundary of any kind, which is why it is the one used — clipped to the box the map can show and simplified to 0.05 degrees. Without it, every country around India was painted the colour of the sea |

- Source: <https://www.naturalearthdata.com>
- Licence: public domain
- Terms: <https://www.naturalearthdata.com/about/terms-of-use/>
- Versions: admin-0, admin-1 and land are 5.1.1 and populated places is
  5.1.2, which is what each layer's own `VERSION.txt` says
- Built into the files the site ships by `scripts/build_outline.py` and
  `scripts/build_towns.py`, which both refuse to write if what they measured
  stops being true.

Town and state spellings are Natural Earth's own, not this project's.

**MapLibre GL JS 6.17.0**, BSD-3-Clause.

- Source: <https://maplibre.org>
- Licence: <https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt>
- Copyright © 2020 MapLibre contributors; copyright © 2020 Mapbox, for the
  parts inherited from mapbox-gl-js v1.

## The colours

**ColorBrewer YlGnBu**, by Cynthia Brewer, Mark Harrower and The Pennsylvania
State University, which ColorBrewer itself marks colour-blind safe.

- Source: <https://colorbrewer2.org>
- Licence: Apache 2.0

## The code

**React**, MIT. **Vite**, MIT. Both are build and runtime dependencies only;
their licences are in `web/node_modules` after an install and their versions
are pinned in `web/package-lock.json`.

The site's own code, specification and hand checks are by Sumedha Kar, at
<https://github.com/SumedhaKar/Precipitation-Forecast-App>.

---

## What is not used

No analytics, no cookies, no third-party scripts, no fonts fetched from
anywhere, no reverse geocoding, no advertising, and no account of any kind.
"Use my location" is answered by the browser, rounded to a 0.25 degree square
**in the page**, and only that square's centre is ever sent anywhere.

## Not an official warning

This site is not a warning service. For warnings and advisories for India,
see the [India Meteorological Department](https://mausam.imd.gov.in/).
