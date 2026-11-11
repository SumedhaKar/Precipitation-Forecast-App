# SPEC.md

India precipitation forecast website.

Status: sections 1-4 drafted and revised 12 November 2026, with all five open
questions resolved. Sections 5-12 to be drafted before any verification results
are produced.

Every claim marked **[verified]** was checked against a real download or the
ECMWF documentation on 12 November 2026. Claims marked **[open]** are not
settled and must not be implemented until resolved.

---

## 1. Purpose and scope

### 1.1 What the site does

Shows, for India, how many members of the ECMWF AIFS ENS 51-member ensemble
forecast at least 1 mm, at least 10 mm, and at least 50 mm of precipitation,
for each of the next five days, on a 0.25 degree grid. Alongside every
forecast it publishes a track record of how past forecasts compared with NASA
IMERG satellite estimates.

### 1.2 What a "day" means

A day is a 24-hour window from 00 UTC to 00 UTC, which is 5:30 am IST to
5:30 am IST. This is not the Indian calendar day.

Every day shown on the site is labelled in that form, for example
"5:30 am Thu to 5:30 am Fri". The site never prints a bare date such as
"Thursday" for a forecast day, because that would imply the IST calendar day
and would be wrong by 5.5 hours at each end.

### 1.3 Which five days

Forecasts come from the 00 UTC run. That run reaches us around midday IST, by
which time most of the 0-24 hour window has already passed. So the 0-24 hour
window is never shown.

| Site label | Forecast steps | Window |
|---|---|---|
| Day 1 | 24-48 | 00 UTC tomorrow to 00 UTC the next day |
| Day 2 | 48-72 | |
| Day 3 | 72-96 | |
| Day 4 | 96-120 | |
| Day 5 | 120-144 | |

Day 1 is tomorrow, never today.

Because tp is accumulated from the start of the forecast **[verified]**, each
daily total is a difference of two downloaded steps. Steps 24, 48, 72, 96, 120
and 144 are all downloaded; six steps give five daily totals.

### 1.4 Spatial scope

India box: latitude 6 to 38 N, longitude 68 to 98 E. On the 0.25 degree grid
this is 129 latitude rows by 121 longitude columns, 15,609 grid squares.

A square counts as India if both hold:

- its centre lies inside India's outline, and
- the ECMWF land-sea mask for that square is at least 0.5.

### 1.5 Honesty commitments

Binding, and repeated from CLAUDE.md:

- Ensemble counts are **model-run counts**, not calibrated probabilities. The
  site never prints a percentage as a probability of rain without saying it is
  the share of model runs.
- NASA IMERG is a **satellite estimate**, not ground truth. Verification
  language says "agreed with the satellite estimate", never "was correct".
- An incomplete forecast is never published. If any required member, step or
  check fails, the run is abandoned and the previous published forecast stays
  up with its original timestamp.

### 1.6 Out of scope

Station observations, nowcasting, sub-daily forecasts, bias correction and
calibrated probabilities.

---

## 2. Data sources

### 2.1 Forecast: ECMWF AIFS ENS

Accessed with the `ecmwf-opendata` Python client (version 0.3.35 installed).

| Setting | Value | Status |
|---|---|---|
| model | `aifs-ens` | [verified] |
| stream | `enfo` | [verified] |
| type | `cf` (control) and `pf` (perturbed) | [verified] |
| time | `0` (00 UTC run) | [verified] |
| param | `tp` | [verified] |
| step | 24, 48, 72, 96, 120, 144 | [verified] at 24, 48 and 144 |
| Grid | regular lat-lon 0.25 deg, 1440 x 721 | [verified] |
| Units | `kg m**-2`, numerically equal to mm | [verified] |
| Accumulation | `stepType = accum`, from step 0 | [verified] |

Members: one `cf` message with `perturbationNumber = 0`, and 50 `pf` messages
with `perturbationNumber` 1 to 50. `numberOfForecastsInEnsemble = 51`.
**[verified]** — a real `pf` download returned exactly 50 messages with
perturbation numbers 1-50 and no duplicates.

**The `pf` messages are not in file order.** The first message in the step-144
file had `perturbationNumber = 38`. Members must always be indexed by the
`perturbationNumber` key, never by position in the file. **[verified]**

Grid origin is latitude 90 at the first row descending to -90, longitude 0 to
359.75 ascending **[verified]**. Latitude is descending; subsetting code must
not assume ascending order. India's longitudes 68-98 E are positive in this
convention, so no wrap-around handling is needed.

#### How the control member is built

The AIFS ENS control member starts from the operational IFS control analysis
regridded to the N320 grid. It is **not** an unperturbed deterministic run in
the sense of a physics-based ensemble control, because the AIFS ENS model is
itself stochastic. The site therefore treats member 0 as one of 51 equal
members and gives it no special status.

This equal treatment is checked, not assumed. A Tier 2 analysis compares the
control against the 50 perturbed members, and the report card is published
twice, once with all 51 members and once with the 50 perturbed members only.
If the two differ materially, that difference is published rather than hidden.

#### How the 0.25 degree grid is produced

AIFS ENS runs on an N320 octahedral reduced Gaussian grid, roughly 31 km. The
0.25 degree fields we download are interpolated from that grid for
dissemination. The 0.25 degree grid is therefore a presentation grid, not the
model's native resolution. The site must never imply detail finer than about
31 km.

#### Two things ECMWF changed around 20 October 2026

Both were found on 12 November 2026 by processing 13 May and 25 October and
comparing them. Both are **[verified]** from the real files.

| Key | 13 May 2026 | 25 October 2026 |
|---|---|---|
| `bitsPerValue` | 16 | 12 |
| Packing quantum at step 24 | 0.0039 mm | 0.125 mm |
| Coarsest quantum across the 6 steps | 0.0156 mm | 0.250 mm |
| `longitudeOfFirstGridPointInDegrees` | 0.0 | 180.0 |
| `longitudeOfLastGridPointInDegrees` | 359.75 | 179.75 |
| File size, `pf` step 24 | 42 MB | 21.6 MB |

**Storage precision dropped from 16 to 12 bits.** This is recorded for every
date and never causes a failure. It does affect the negative-difference rule;
see section 3.6.

**The longitude origin moved from 0 to 180.** The grid is still 1440 columns
at 0.25 degrees, but column 0 now holds longitude 180 instead of 0. India at
68-98 E is contiguous under both conventions, at column 272 under the old
origin and column 992 under the new one.

The code therefore computes the India window from each file's own
`longitudeOfFirstGridPointInDegrees` and never assumes an origin. It also
rejects any origin that would make India wrap around the end of the array,
rather than silently returning the wrong part of the world.

#### Model version

AIFS ENS v2 went operational on the 12 May 2026 06 UTC run. The first 00 UTC
run on v2 is 13 May 2026, which is why Pile A starts there. Mixing v1 and v2
forecasts in one track record is not allowed.

#### Sources and retention

ECMWF's own server retains "the most recent 12 forecast runs, corresponding to
approximately 2-3 days of forecasts based on the four daily IFS and AIFS cycles
(00, 06, 12 and 18 UTC)". Retention is counted in **runs, not days**; the day
figure is only an approximate equivalent. **[verified]**

The cloud mirrors keep much longer; a 13 May 2026 run downloaded cleanly from
Google on 12 November 2026, 183 days later. **[verified]**

| Use | source | Why |
|---|---|---|
| Pile A, historical | `google` | holds the full archive; worked first time |
| Pile A, fallback | `aws` | AWS throttled us in earlier practice, so backup only |
| Pile C, live | `ecmwf` | fastest for fresh runs, which are inside the 12-run (2-3 day) window |

Valid source values in the client are `ecmwf`, `aws`, `azure`, `google` and
`ecmwf-testdata`. Google resolves to
`https://storage.googleapis.com/ecmwf-open-data`. **[verified]**

Licence: CC-BY-4.0. Attribution to ECMWF is required and goes in CREDITS.md and
in the site footer.

### 2.2 Land-sea mask

Parameter `lsm`, step 0, from the same `aifs-ens` open data, on the identical
0.25 degree 1440 x 721 grid. Values run 0 to 1; about 12.4% of global squares
are fractional coastline values. **[verified]**

Downloaded once and cached. Never re-downloaded per run.

### 2.3 Observations: NASA IMERG

GPM IMERG Late Precipitation L3 1 day 0.1 degree V07C, short name
`GPM_3IMERGDL`, version `07`. DOI 10.5067/GPM/IMERGDL/DAY/07.

All of the following was confirmed by downloading the real 14 May 2026 file
(hand check HC4, 12 November 2026).

| Property | Value | Status |
|---|---|---|
| File name form | `3B-DAY-L.MS.MRG.3IMERG.YYYYMMDD-S000000-E235959.V07C.nc4` | [verified] |
| Size | about 30 MB per day | [verified] |
| Window | `BeginTime 00:00:00.000Z` to `EndTime 23:59:59.999Z`, same date | [verified] |
| Grid | 0.1 degree, `lon` 3600 points, `lat` 1800 points | [verified] |
| Latitude | -89.95 to 89.95, **ascending** | [verified] |
| Longitude | -179.95 to 179.95 | [verified] |
| `precipitation` | float32, units `mm/day`, `_FillValue` -9999.9 | [verified] |
| `precipitation_cnt` | int8, units `count`, no `_FillValue`, max 48 | [verified] |

The daily window matches our 00 UTC to 00 UTC day definition exactly, so no
time shifting is needed.

**Two ordering traps, both verified:**

1. Arrays are shaped `(time, lon, lat)`. **Longitude comes first**, which is the
   opposite of the usual convention. Code must not assume `(lat, lon)`.
2. IMERG latitude **ascends** (-89.95 first). ECMWF latitude **descends**
   (90 first). The two grids run in opposite directions and one must be
   flipped before any comparison.

On the 14 May 2026 file, 99.91% of global pixels had `precipitation_cnt = 48`
and the observed range was 37 to 48, with no fill values present in
`precipitation`. **[verified]**

Access uses the NASA Earthdata login already stored in netrc on this machine,
via `earthaccess.login(strategy="netrc")`. No `.env` entry, no credential in
code, and the password is never requested in chat or written anywhere by this
project.

IMERG is a satellite estimate. It is used for verification only. It is never
called truth, and it never feeds back into the forecast.

### 2.4 The three piles

| Pile | What | Range | Used for |
|---|---|---|---|
| A | AIFS ENS 00 UTC forecasts | 13 May 2026 to about 6 Nov 2026, about 178 dates | track record only |
| B | IMERG Late daily | 14 May 2026 to latest available | observations for the track record |
| C | Live forecasts | ongoing, via GitHub Actions | the published forecast |

Pile B starts one day after Pile A because the earliest day a 13 May run
forecasts is the 14-15 May window.

Pile A ends at the latest start date whose Day 5 window still has IMERG data
available by the Friday cut-off, which is about 6 November 2026. The exact last
date is computed from what IMERG actually has, not assumed.

### 2.5 Unit checking

Every downloaded forecast file is checked before use.

**Units and grid**

- `shortName` is `tp`
- `units` is `kg m**-2`
- `stepType` is `accum`
- `Ni` is 1440 and `Nj` is 721
- both direction increments are 0.25
- `gridType` is `regular_ll`

**Identity: the file is what we asked for**

- `dataDate` equals the requested date
- `dataTime` is the 00 UTC run
- `endStep` equals the requested step
- `startStep` is 0, because tp accumulates from the forecast start

**Orientation**

- `jScansPositively` is 0, so latitude descends
- `iScansNegatively` is 0, so longitude ascends
- the first latitude is 90
- the first longitude is on the 0.25 grid, and the India window computed from
  it does not wrap past the end of the array

The first longitude is deliberately **not** required to be 0, because ECMWF
changed it to 180 around 20 October 2026 (section 2.1). The orientation keys
are checked rather than assumed: a silent change here would have read India
from the wrong half of the world, which is exactly what happened on the first
attempt at 25 October and what this check caught.

**Members**

- `cf` files contain exactly one message, `perturbationNumber` 0
- `pf` files contain exactly 50 messages, `perturbationNumber` 1 to 50, each
  once
- combined, every step has members 0 to 50, each exactly once
- members are indexed by `perturbationNumber`, never by file order

**Values**

- no bitmap is present, so no values are missing
- every value is finite: no NaN, no infinity

**Recorded, never a failure reason**

- `bitsPerValue` and `packingType` for every message
- `longitudeOfFirstGridPointInDegrees` for every message

Every downloaded IMERG file is checked for its declared units and grid shape.

If any check fails the pipeline **stops** and writes a failure record. It does
not convert, guess or continue. This follows from rule 2: no invented data.

### 2.6 Download plan and raw-file retention

#### Parallelism

Measured from Google on 12 November 2026 **[verified]**:

| Connections | Bytes | Wall clock | Aggregate | Errors |
|---|---|---|---|---|
| 1 | 46.8 MB | 109 s | 0.43 MB/s | 0 |
| 4 | 192.8 MB | 116.0 s | 1.66 MB/s | 0 |
| 8 | 371.5 MB | 115.8 s | 3.21 MB/s | 0 |

Per-connection speed stayed at 0.40 to 0.43 MB/s at all three settings, so
throughput scaled linearly and no throttling appeared at 8.

**Pile A uses 8 parallel connections.** Estimated total is about 178 dates at
roughly 300 MB per date, about 53 GB, about 4.6 hours at 3.21 MB/s. The
per-date size is extrapolated from measured steps 48 and 144, so treat it as
plus or minus 15%.

If errors appear at 8 during the real run, the downloader drops to 4 and
records that it did so. It never silently retries forever.

#### Date order: spread, not sequential

Dates are downloaded in a spread order so that stopping early still leaves
every month covered:

1. every 4th date from the start,
2. then every 2nd date not already taken,
3. then the remainder.

A sequential order would leave a half-finished Pile A covering only May to
August, which would make the track record seasonally biased. The spread order
means any prefix of the work is a roughly even sample of the whole period.

#### One date is one unit of work

A date is only "done" when all of these have happened, in this order:

1. all 12 files downloaded, 2 types by 6 steps
2. every check in section 2.5 passed
3. the India subset written to a `.part` file
4. the `.part` file reopened from disk and checked against what was written
5. the `.part` file renamed to its final name
6. the daily-difference check of section 3.6 passed
7. the raw GRIB deleted and the deletion logged

Anything less leaves no done record, so a rerun simply redoes the date. There
is no half-done state.

The saved file holds **accumulated** tp for 51 members at 6 steps, shaped
`(6, 51, 129, 121)` as float32, about 19 MB per date. Daily differences are
computed from it rather than stored, so the original ECMWF quantity is what is
archived and nothing is baked in.

Alongside `tp` the file stores `steps`, `members`, `lat` and `lon`, so it is
readable without reference to this document.

#### Download timeouts

`ecmwf-opendata` calls `multiurl.download()` without a `timeout`, so a stalled
connection blocks forever rather than failing. This was not theoretical: on
12 November 2026 a download stopped at 27 MB and sat there indefinitely.

The pipeline therefore wraps the client's HTTP session so a `None` timeout
becomes a real one: 30 s to connect, 120 s per read. `multiurl` already treats
a read timeout as retryable, so the `maximum_retries` policy then applies and
the run moves on. Without this, the unattended background run could freeze
silently and produce nothing overnight.

#### Failure handling

- A file that fails after 3 retries fails its date. The run continues with
  other dates.
- A failed date gets `data/logs/failures/<date>.json` with the error, the
  traceback and the time taken, and **its raw files are kept** for inspection.
- A successful date gets `data/logs/done/<date>.json` with sizes, every check
  result, the packing, the longitude origin and the time taken.
- Dates with a done record are skipped on a rerun, so rerunning simply
  continues.
- Leftover `.part` files from an interrupted run are deleted and that date is
  redone from the start.
- The run stops cleanly if free disk space falls below 15 GB.

#### Raw-file retention

Standing approval is in place for one deletion only: after a date's India
subset has been written **and** its checks have passed, that date's raw GRIB
files are deleted. Every deletion is logged per date under `data/logs/done/`.

No other deletion happens without asking. In particular, India subsets,
results, logs and the probe files are never deleted automatically.

After subsetting, a date occupies about 16 MB instead of about 300 MB, so the
full Pile A India archive is about 2.9 GB.

The six probe files in `data/raw/` from the 12 November 2026 checks, 126 MB in
total, are kept until hand check HC1 is complete, then deleted:

| File | Size | What it proved |
|---|---|---|
| `probe_cf_20260513_s24.grib2` | 0.9 MB | tp units, accumulation, 0.25 grid, member 0 |
| `probe_pf_20260513_s48.grib2` | 46.8 MB | 50 perturbed members; single-connection speed |
| `probe_pf_20260513_s144.grib2` | 53.4 MB | step 144 exists; members out of file order |
| `probe_lsm_aifs-ens.grib2` | 0.18 MB | land-sea mask on the identical grid |
| `probe_lsm_ifs.grib2` | 0.19 MB | IFS land-sea mask, kept for comparison |
| `3B-DAY-L...20260514...V07C.nc4` | 30.7 MB | HC4, the IMERG structure in section 2.3 |

The files downloaded by the 4-connection and 8-connection throughput tests were
written to a temporary folder and removed by the test itself. They were never
inside `data/`.

---

## 3. Grid, India mask and remapping

### 3.1 Direction of remapping

Observations are remapped to the forecast grid. IMERG 0.1 degree is aggregated
up to the ECMWF 0.25 degree grid.

The forecast is **never** remapped to 0.1 degree. Doing so would paint detail
the model does not have, and the model's real resolution is coarser than
0.25 degree anyway (section 2.1).

### 3.2 Cell geometry

An ECMWF 0.25 degree value is a point value interpolated to the grid-point
location. For remapping it is treated as representing the 0.25 by 0.25 degree
box centred on that point. This is an approximation and is recorded as such.

An IMERG 0.1 degree pixel is treated as the 0.1 by 0.1 degree box centred on
its grid point.

Before any overlap is computed, the IMERG array is transposed from
`(lon, lat)` to `(lat, lon)` and its latitude axis is flipped to descending, so
that both grids are in the same orientation as ECMWF (section 2.3). This
transposition and flip is the first operation in the remapping step, and it is
covered by an explicit test.

### 3.3 Area-weighted overlap

Each ECMWF box's observed value is the area-weighted mean of the IMERG pixels
that overlap it.

0.25 is not a whole multiple of 0.1, so IMERG pixels straddle ECMWF box edges
and partial overlaps are normal. Weights are true spherical areas:

```
weight = overlap_in_longitude_degrees * (sin(lat_top) - sin(lat_bottom))
```

evaluated on the overlap rectangle. The sine terms make high-latitude boxes
correctly smaller. Plain arithmetic means and nearest-neighbour sampling are
both forbidden.

### 3.4 Completeness rule

An IMERG pixel is complete when `precipitation_cnt` equals 48, meaning all 48
half-hourly fields contributed. **[verified]** — 48 is the observed maximum.

An ECMWF box-day is usable only when complete pixels cover at least 90% of the
box's area. The observed value is then the area-weighted mean over the complete
pixels only, with weights renormalised to sum to 1. Incomplete pixels are
excluded from the mean, not treated as zero.

A box-day below 90% is marked missing. Missing box-days are excluded from
verification entirely and are counted and reported, never silently dropped.

Confirmed 12 November 2026: incomplete pixels are excluded from the mean and
the remaining weights are renormalised. They are not treated as zero rainfall.

### 3.5 India mask

A 0.25 degree box is in India when both hold:

1. the box centre lies inside India's outline, and
2. `lsm` for that box is at least 0.5.

The mask is computed once and stored. It is identical for every run.

#### The outline

Natural Earth admin-0 countries, **India point-of-view edition**, layer
`ne_10m_admin_0_countries_ind`, version 5.1.1, 1:10 million scale.

Verified 12 November 2026 **[verified]**:

- Downloads from
  `https://naturalearth.s3.amazonaws.com/10m_cultural/ne_10m_admin_0_countries_ind.zip`,
  HTTP 200, 4,922,443 bytes, complete `.shp` `.shx` `.dbf` `.prj` set.
- The `India` feature has 8,474 points and a bounding box of longitude
  68.1434 to 97.3623, latitude 6.7456 to 37.0545. The 37.05 northern limit
  confirms this is the official-boundaries edition; the default de facto
  edition stops near 35.5.
- That bounding box sits entirely inside the India box of section 1.4, so the
  box does not clip any territory.

Licence: public domain. Natural Earth states "All versions of Natural Earth
raster + vector map data found on this website are in the public domain" and
"No permission is needed to use Natural Earth. Crediting the authors is
unnecessary." It is credited in CREDITS.md anyway.

The outline decides only which grid squares count as India. The published map
does not draw national borders.

### 3.6 Negative differences

Daily totals are differences of accumulated fields. GRIB packing is 16-bit
**[verified]**, so tiny negative differences can appear where true accumulation
is flat.

**[open] — the -0.1 mm figure no longer works for data after about
20 October 2026 and needs your decision. Evidence and options are at the end of
this section. Everything below describes the rule as currently written.**

- A difference from -0.1 to 0 mm is set to 0.
- A difference below -0.1 mm is an error, handled differently by pile:

| Pile | Behaviour on a difference below -0.1 mm |
|---|---|
| C, live | The live run **stops**. Nothing is published. The previous forecast stays up. |
| A, historical | **That date alone is marked failed** and recorded under `data/logs/failures/`. The remaining dates continue. |

The difference exists because a live run is a single publishable artefact,
while Pile A is a long batch where one bad date must not destroy 177 good ones.
Failed Pile A dates are excluded from the track record and their count is
published alongside it.

#### Why -0.1 mm no longer works: the evidence

Measured from the real files on 12 November 2026 **[verified]**:

| | 13 May 2026 | 25 October 2026 |
|---|---|---|
| `bitsPerValue` | 16 | 12 |
| Coarsest packing quantum across the 6 steps | 0.015625 mm | 0.250 mm |
| Most negative daily difference found | -0.015625 mm | -0.125 mm |
| Most negative, as a multiple of the coarsest quantum | 1.0 | 0.5 |
| Verdict under the -0.1 mm rule | passes | **fails, 10,126 values** |

The -0.125 mm on 25 October is exactly one packing step of that file. It is
not bad data; it is the storage precision ECMWF now uses. The rule rejects it
only because -0.1 mm is finer than the new quantum.

Left unchanged, this rule fails **every** date after the packing change, which
is roughly 18 of the 178 Pile A dates and all future live runs.

On both dates the most negative difference was at most one coarsest quantum,
which is what differencing two quantised accumulations should produce.

#### Options

1. **Tolerance derived from the file's own packing.** Allow differences down
   to minus twice the coarsest quantum of the date, computed per date from
   `binaryScaleFactor` and `decimalScaleFactor`. That is -0.031 mm for 13 May
   and -0.5 mm for 25 October. It tracks whatever ECMWF does next without
   further edits, and it is *stricter* than -0.1 mm on the older 16-bit data.
2. **A fixed larger number**, such as -0.3 mm or -0.5 mm. Simple and easy to
   state, but arbitrary, and it would have to be revisited if ECMWF changes
   precision again.
3. **Leave -0.1 mm** and accept that post-20-October dates fail. Not
   recommended: it discards the most recent and most relevant 18 dates.

Option 1 is recommended. It is the only one that stays correct if the packing
changes again, and it makes the check tighter rather than looser on the data
we already have.

---

## 4. The forecast product

### 4.1 Daily member totals

For each member m in 0..50 and each day d in 1..5:

```
total(m, d) = tp(m, step_end(d)) - tp(m, step_start(d))
```

in mm, with the negative handling of section 3.6.

### 4.2 Threshold counts

Thresholds are 1 mm, 10 mm and 50 mm.

A member counts towards a threshold when its daily total is **greater than or
equal to** the threshold. A total of exactly 10.0 mm counts towards the 10 mm
threshold.

```
count(box, d, T) = number of members m where total(m, d) >= T
```

count is an integer from 0 to 51. It is stored and published as an integer out
of 51, never as a bare percentage.

When a percentage is shown it is always accompanied by the fraction, for
example "34 of 51 model runs (67%)", and it is never called a probability.

### 4.3 The 51 dots in the place panel

**Dots are not on the map.** They are in the place panel, which opens for one
selected grid square and one selected day.

The panel shows 51 dots. Each dot is **one member's daily total** for that
square and that day. All 51 members are shown, always; the panel never shows a
subset or a summary in place of the dots.

Each dot is coloured by which of four categories that member's total falls in:

| Category | Range |
|---|---|
| under 1 | 0 to below 1 mm |
| 1-10 | 1 mm up to below 10 mm |
| 10-50 | 10 mm up to below 50 mm |
| 50+ | 50 mm and above |

Boundaries follow the same "greater than or equal to" rule as section 4.2, so a
member total of exactly 10.0 mm is in the "10-50" category.

The dots are the honest picture of the spread: 51 individual model runs, shown
individually, rather than one number standing in for all of them.

### 4.4 Map square colouring

The map is separate from the dots. Map squares are coloured by the **count**
(section 4.2) for the **currently selected threshold**, which the user chooses
from 1 mm, 10 mm or 50 mm.

So the map answers "how many of the 51 model runs reach this threshold here",
and the place panel answers "what did each of the 51 model runs actually say
for this square".

### 4.5 Completeness rule for publishing

A run is publishable only when, for every one of the six steps, all 51 members
are present with the right perturbation numbers and all checks in section 2.5
pass. 50 of 51 members is not publishable. There is no partial publish.

---

## Open questions

All five open questions from the first draft were resolved on 12 November 2026:

| # | Question | Resolution |
|---|---|---|
| 1 | India outline | Natural Earth India POV edition, verified, public domain (3.5) |
| 2 | IMERG count variable | `precipitation_cnt`, int8, max 48, no fill value (2.3) |
| 3 | IMERG daily window | 00:00:00.000Z to 23:59:59.999Z, matches our day (2.3) |
| 4 | Incomplete pixels | Excluded and weights renormalised (3.4) |
| 5 | Dots | 51 member totals in the place panel, not on the map (4.3) |

Nothing in sections 1-4 is now blocked.

---

## Sections still to draft

5. Verification method
6. Labels and track record
7. Pipeline stages and file layout
8. Website and API
9. Automation and failure handling
10. Testing strategy
11. Display rules
12. Tiers and acceptance tests

### Requirements already fixed for later sections

Recorded here so they are not lost between drafting groups.

**Section 11, display rules.** A large percentage may be displayed **only**
when that forecast carries a "Good track record" label. Without that label the
site shows the count out of 51 instead. A big percentage implies reliability,
so it has to be earned by the record rather than printed by default.

**Section 12, tiers and acceptance tests.** A Tier 2 analysis compares the
control member against the 50 perturbed members, and the report card is
published both with 51 members and with 50 (section 2.1).
