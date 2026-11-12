# SPEC.md

India precipitation forecast website.

Status: sections 1-4 drafted and revised 12 November 2026, with all five open
questions resolved. Sections 5 and 6 decided 12 November 2026. Sections 7-12 to
be drafted before any verification results are produced.

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
| Raw bytes for the whole date | 301 MB | 153 MB |

**[open] — the exact changeover dates.** The two changes are confirmed on
13 May and 25 October, but the first date carrying each is not yet known. When
the full Pile A run finishes, the first date with `bitsPerValue` 12 and the
first date with longitude origin 180 are to be read from the done records and
written in here. They may not be the same date.

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

#### What AIFS ENS does and does not publish

Checked on 12 November 2026 against the real URLs and the real index files:

| Product | Available? |
|---|---|
| `aifs-ens` / `enfo` / `cf` | yes, about 58 MB per step |
| `aifs-ens` / `enfo` / `pf` | yes, about 2.9 GB per step for all parameters |
| `aifs-ens` / `enfo` / `ep` (probabilities) | **no**, HTTP 404 |
| `aifs-ens` / `enfo` / `ef`, `em`, `es` | no, HTTP 404 |
| `aifs-ens` / `waef` / `cf` and `pf` (waves) | yes, not used here |

The `pf` index lists 29 parameters, with `tp` the only precipitation total and
no threshold-probability parameter such as `tpg1` or `tpg10`. **[verified]**

So **there is no official AIFS ENS rain probability to compare our counts
against**, which decides the shape of HC6 (section 4.6). It also means our
counts cannot be cross-checked against an ECMWF-produced probability at all,
and the only independent check available is a member-by-member dump.

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

**Packing**

- `bitsPerValue`, `packingType` and the quantum are recorded for every message
  and are **never** a failure reason on their own
- the one exception is the cap: a coarsest quantum above 0.5 mm fails the date
  (section 3.6)

**Recorded, never a failure reason**

- `longitudeOfFirstGridPointInDegrees` for every message

**Applies to every GRIB we read**

The longitude origin is taken from the file in hand, every time, with no
exceptions: forecast files, the land-sea mask, and the live pipeline. No code
path is allowed to assume an origin of 0 or of 180.

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

Six probe files in `data/raw/` came out of the 12 November 2026 checks, 126 MB
in total. Five were deleted on 12 November 2026 once the HC1 to HC3 output had
been saved to `handchecks/results/`. One is kept permanently.

| File | Size | What it proved | Status |
|---|---|---|---|
| `probe_cf_20260513_s24.grib2` | 0.9 MB | tp units, accumulation, 0.25 grid, member 0 | deleted 12 Nov 2026 |
| `probe_pf_20260513_s48.grib2` | 46.8 MB | 50 perturbed members; single-connection speed | deleted 12 Nov 2026 |
| `probe_pf_20260513_s144.grib2` | 53.4 MB | step 144 exists; members out of file order | deleted 12 Nov 2026 |
| `probe_lsm_ifs.grib2` | 0.19 MB | IFS land-sea mask, kept for comparison | deleted 12 Nov 2026 |
| `3B-DAY-L...20260514...V07C.nc4` | 30.7 MB | HC4, the IMERG structure in section 2.3 | deleted 12 Nov 2026 |
| `probe_lsm_aifs-ens.grib2` | 0.18 MB | land-sea mask on the identical grid | **kept**, the India mask needs it |

The standalone HC4 IMERG file was deleted only after its SHA256 was confirmed
byte-identical to the copy Pile B downloaded into `data/raw/imerg/`, so nothing
unique was lost. Hash
`760e95127ce5d058bd4c298b9ae8ba5792f178dea1b65fe69770643f6c8797d6`.

Every deletion is recorded in `data/logs/done/probe_cleanup.json` with each
file's size and SHA256 as it was at the moment of deletion.

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

#### Coastal squares

A square is **coastal** when it is an India square and at least one of its 8
neighbours has `lsm` below 0.5.

The test is on the neighbour's land-sea mask, not on whether the neighbour is
in India. A square on the border with another country therefore does not read
as coastline.

Squares on the edge of the India box are judged against their real neighbours
from the global field, using a one-square border read outside the box, rather
than being judged against nothing.

#### What the mask comes out as

Built 12 November 2026 **[verified]**:

| | Count |
|---|---|
| Squares in the 129 x 121 box | 15,609 |
| Centre inside or on the outline | 4,636 |
| India, after `lsm >= 0.5` | **4,613** |
| of which coastal | 215 |
| of which inland | 4,398 |

So the `lsm >= 0.5` rule removes 23 squares whose centres are inside India's
outline.

Eight named places were checked. Delhi, Srinagar, Gilgit and Aksai Chin are
India; Colombo, Kathmandu, Dhaka and Lahore are not. Gilgit and Lahore sit at
the same longitude of 74.25, and only the point-of-view edition separates them.

#### Island groups: what the rule costs

Reported, not corrected. The rule stands as written.

| Group | Centres inside the outline | Surviving `lsm >= 0.5` | Highest `lsm` nearby |
|---|---|---|---|
| Andaman & Nicobar | 8 | 3 | 0.7578 |
| Lakshadweep | 0 | 0 | 0.0312 |

Andaman & Nicobar keeps 3 of its 8 squares; 5 are lost to the land-sea cut.

**Lakshadweep disappears entirely, and not because of the `lsm` rule.** No
0.25 degree grid centre falls inside its outline at all, so it is already gone
before the land-sea mask is applied. The islands are far smaller than one grid
square. The highest `lsm` anywhere in that box is 0.03, so no threshold short
of abandoning the land test would recover them.

This is a limitation of forecasting on a 0.25 degree grid, not a mistake in
the mask, and it is stated on the site rather than glossed over.

### 3.6 Negative differences

Daily totals are differences of accumulated fields. GRIB packing is 16-bit
**[verified]**, so tiny negative differences can appear where true accumulation
is flat.

The tolerance is **not a fixed number**. It is derived from the packing of the
date being processed, because ECMWF's storage precision changed around
20 October 2026 (section 2.1) and a fixed figure cannot survive that.

```
coarsest_quantum = the largest packing quantum across all 6 steps of the date
tolerance        = -2 x coarsest_quantum
```

The quantum of one GRIB message is `2**binaryScaleFactor / 10**decimalScaleFactor`.
Differencing two accumulations each rounded to a step of q can produce a
spurious negative of about q, so twice q is a safe floor.

Worked from the real files **[verified]**:

| Date | bits | Coarsest quantum | Tolerance | Worst difference seen | Verdict |
|---|---|---|---|---|---|
| 13 May 2026 | 16 | 0.015625 mm | -0.03125 mm | -0.015625 mm | passes |
| 25 Oct 2026 | 12 | 0.25 mm | -0.5 mm | -0.125 mm | passes |

Note this is **stricter** than the old fixed -0.1 mm on the 16-bit data.

Then:

- A difference from the tolerance to 0 mm is set to 0.
- A difference below the tolerance is an error, handled differently by pile:

| Pile | Behaviour on a difference below -0.1 mm |
|---|---|
| C, live | The live run **stops**. Nothing is published. The previous forecast stays up. |
| A, historical | **That date alone is marked failed** and recorded under `data/logs/failures/`. The remaining dates continue. |

The difference exists because a live run is a single publishable artefact,
while Pile A is a long batch where one bad date must not destroy 177 good ones.
Failed Pile A dates are excluded from the track record and their count is
published alongside it.

#### The 0.5 mm cap

If a date's coarsest quantum is **above 0.5 mm**, the date fails outright and
a live run stops. Rounding that coarse is too rough to judge against the 1 mm
threshold, so the file is not trusted at all.

25 October, at 0.25 mm, is inside the cap and is used.

#### Recorded per date

Every done record carries:

- the packing quantum at each of the 6 steps
- the coarsest quantum and the cap it was tested against
- the tolerance that was used
- how many daily differences were set to 0 by it

So the rule that was applied to any date can always be read back, rather than
inferred from the code as it stands later.

#### Limitation: precision after about 20 October 2026

From the packing change onwards, daily totals are only accurate to about
plus or minus 0.25 mm. Before it they were accurate to about 0.016 mm.

**The 1 mm threshold is the one most affected.** A member whose true daily
total sits within about a quarter of a millimetre of 1 mm may be counted on
either side of it, purely because of how the number was stored. The 10 mm and
50 mm thresholds are far enough above the quantum for this to be negligible.

HC6 was written to compare our counts against ECMWF's own published
probabilities. **There are none to compare against.** Checked on
12 November 2026: the only AIFS ENS products in the 0.25 degree `enfo` stream
on ECMWF open data are `cf` and `pf`. There is no `ep` probability file, and
the `pf` index lists 29 parameters with `tp` the only precipitation total.
**[verified]** by HEAD requests on the real URLs and by reading the index.

HC6 therefore dumps all 51 members instead, and the precision point still
applies to it: a member whose stored total sits within about a quarter of a
millimetre of 1 mm may be counted on either side of that threshold. That is a
storage-precision artefact, not a disagreement about the weather, and must be
reported as such rather than explained away.

This limitation is published on the site alongside the track record.

### 3.7 IMERG processing

`pipeline/nasa_process.py`. One IMERG file is one date. Written and run on
12 November 2026 while Pile A was still downloading, so `pipeline/config.py`
was not touched; see "Where the numbers live" below.

```
python -m pipeline.nasa_process --all        process every Pile B date
python -m pipeline.nasa_process 20260722     process one date
python -m pipeline.nasa_process --summary    report over what is done
```

#### Which IMERG date verifies which lead day

The run of date **R**, lead day **n**, covers forecast steps 24n to 24(n+1),
which is the 00 UTC to 00 UTC day starting n days after R. IMERG files are
named for the day they cover. So:

| Lead day | Steps | IMERG date |
|---|---|---|
| 1 | 24-48 | R + 1 |
| 2 | 48-72 | R + 2 |
| 3 | 72-96 | R + 3 |
| 4 | 96-120 | R + 4 |
| 5 | 120-144 | R + 5 |

This is `imerg_date_for(run_date, lead_day)`, one function, used by anything
that pairs a forecast with an observation, including the cases of section 5.1.
It is tested across a month end, a year end and the ends of its own range.

#### Checks before any value is used

Read from the file itself, not from its name alone, and any failure stops that
date:

| What | Check |
|---|---|
| Version | `DOI` attribute is exactly `10.5067/GPM/IMERGDL/DAY/07` |
| Version | `title` attribute contains `Late`, `1 day` and `0.1 degree` |
| Version | the file name contains `V07C` |
| Units | `precipitation.units` is `mm/day` |
| Shape | `precipitation` is `(1, 3600, 1800)` and `precipitation_cnt` matches |
| Date | the `time` coordinate, converted using its own `units` attribute, is 00:00 UTC on the file-name date |
| Date | the `BeginDate` attribute is that same date |
| Counts | `precipitation_cnt` in the India window lies between 0 and 48 |

**Limitation, recorded rather than hidden.** The revision letter `C` of
`V07C` appears only in the file name; the `DOI` attribute carries version
`07` without it. So the major version is checked from inside the file and the
revision letter from the name. If NASA issues a `V07D`, the name check is what
catches it.

The `time` coordinate is converted by parsing its `units` string, currently
`days since 1980-01-06 00:00:00Z`. The epoch is never hardcoded.

#### Values

| Value | Treatment |
|---|---|
| `-9999.9`, the `_FillValue`, within 0.01 | **missing**, excluded like an incomplete pixel |
| any other negative value | **fails the date** |
| NaN that is not the fill value | **fails the date** |

Checked over the India window, which is the only data this step uses. A
negative rainfall that is not the documented fill value means the file is not
what it claims to be, and guessing what it meant is not allowed.

#### The grid is rebuilt from the coordinate values

Pixel edges come from the `lat` and `lon` vectors in the file, never from an
assumed index order:

- spacing is checked to be 0.1 degrees everywhere, within 1e-4,
- the vectors are checked to be ascending,
- edges are centre plus or minus 0.05, and the **outermost edges are asserted
  to be -90 and +90 in latitude and -180 and +180 in longitude**,
- only once the file has proved it is that grid are the edges snapped to exact
  multiples of 0.1, so that the overlap arithmetic does not carry the float32
  noise the file stores longitude in.

The India window is then chosen by which pixel edges actually overlap the
India box, not by arithmetic on index numbers. It comes out 324 pixels of
latitude by 304 of longitude.

The first operation on the data itself is the transpose and latitude flip of
section 3.2, `(lon, lat)` ascending to `(lat, lon)` descending, and it has its
own test that a transpose without the flip would fail.

#### The weight matrix

The overlap weights of section 3.3 are computed **once** and reused for every
date, as a sparse matrix in coordinate form: a row index into the 15,609 cells,
a column index into the window pixels, and the spherical area of the overlap
rectangle. It holds 191,648 entries, about 12.3 pixels per cell.

One identity is asserted every time it is built: because the 0.1 degree pixels
tile the globe, **the weights of each cell must sum to that cell's analytic
area**, `0.25 * (sin(top) - sin(bottom))`. This is required to hold to 1e-9
relative. If the overlap arithmetic were wrong anywhere, this is what would
catch it before any rainfall was computed.

#### Completeness

Exactly as section 3.4. Only pixels with `precipitation_cnt == 48` and a
non-missing value contribute; the weights are renormalised over them; a cell
is usable when they cover at least 0.90 of the cell's area. **Exactly 0.90
passes**, with a 1e-12 tolerance so that float dust cannot push a cell that is
arithmetically on the line to the wrong side. An unusable cell is NaN, and the
count of unusable cells is in every done record.

`complete_fraction` is published alongside the rainfall for every cell, so a
reader can see how much of each cell was observed rather than inferring it.

#### Output

| Path | Contents |
|---|---|
| `data/india/nasa/<date>.npz` | `rain` (129, 121) float32 mm, NaN where unusable; `complete_fraction` (129, 121) float32; `lat` 38.0 down to 6.0; `lon` 68.0 up to 98.0 |
| `data/logs/done/nasa_<date>.json` | done record: file identity, window summary, grid, usable and unusable counts, lowest complete fraction, wettest cell |
| `data/logs/failures/nasa_<date>.json` | error type, message and traceback |

Written to `<date>.npz.part`, reopened, compared array by array against what
was in memory including NaN positions, and only then renamed. A date is
skipped on a later run when both its done record and its output file exist,
so the step resumes exactly like Pile A.

**The raw IMERG files are kept.** Nothing in this step deletes them. The
standing permission to delete raw files after checks pass covers Pile A's
GRIB only.

#### Where the numbers live

The IMERG constants (0.1 degree, 3600 by 1800, the fill value, 48, 0.90) are
in `pipeline/nasa_process.py` rather than in `pipeline/config.py`, because
Pile A was running and imports `config.py`. They belong in `config.py` and
move there the next time Pile A is stopped.

#### What the first full run found

181 dates processed on 12 November 2026, **0 failures**, 23.1 MB of output.

| Measure | Result |
|---|---|
| India square-days | 834,953 (4,613 squares x 181 dates) |
| Unusable square-days | **0** |
| Dates with more than 10% of India squares unusable | 0 |
| Lowest `complete_fraction` of any cell, any date | 1.0 |
| Lowest `precipitation_cnt` in any India window | 48 |
| Fill values in any India window | 0 |
| Wettest India square-day | 22 July 2026, 20.25 N 72.75 E, 406.1 mm |

Every IMERG pixel over India, on all 181 days, was complete. So the
completeness rule of section 3.4 has **never yet excluded anything in
practice**, and the only evidence that it works is the unit tests that build
incomplete pixels on purpose. That is worth knowing before anyone reads the
0% unusable figure as a property of the code.

#### Tests

`tests/test_nasa_process.py`:

| Test | What it would catch |
|---|---|
| transpose and flip | a wrong orientation, including a transpose without the flip |
| weights sum to the cell area | any error in the overlap arithmetic |
| constant field unchanged | a broken normalisation |
| field linear in longitude returns the cell centre | asymmetric longitude weights |
| `lon * 1000 + lat` against longhand expected means at 7 cells | a flip, a transpose or a swapped axis |
| single-pixel spike against a hand-computed weight | a wrong weight or a leak into the neighbouring cell |
| conserved total over latitude 10-20 N, longitude 70-80 E | a systematic area error |
| incomplete pixels excluded, not zeroed | treating a gap as no rain |
| the 0.90 boundary, exactly and just below | an off-by-epsilon on the usability rule |
| `imerg_date_for` across a month end and a year end | a date-mapping error |
| grid rejection: descending, wrong spacing, shifted, uneven | accepting a file that is not the IMERG grid |
| **a second implementation on real data** | anything the first six tests share an assumption about |

The last one re-implements the remapping a different way: it supersamples each
cell 50 by 50, takes each sub-point's pixel by nearest neighbour, and weights
by `cos(latitude)` instead of sine differences. It shares no code with the
sparse-matrix path. On 14 July 2026 the two agree to within **1e-3 mm**, the
required tolerance, and the completeness fractions agree to 1e-6. It skips
when the raw IMERG files are absent, because `data/` is never committed, so it
does not run in CI.

#### HC5

`handchecks/hc5_cell.py` writes `handchecks/results/hc5_cell.csv`: every
IMERG pixel overlapping one cell, with its own edges, the overlap rectangle's
edges, its value, its count, the fraction of the pixel inside the cell, and
its weight. The header carries the sum of weights, the analytic cell area, the
complete fraction, and the cell value the program produced, so the weighted
mean can be recomputed by hand in a spreadsheet.

The cell is chosen by rule, not picked: the wettest India square-day in July
2026 with its centre between 8 and 22 N and at or west of 76 E. That is
22 July 2026 at 20.25 N, 72.75 E, on the Gujarat-Maharashtra coast. Nine
pixels overlap it, all complete, and the recomputed mean matches the program's
406.09262545270906 mm exactly.

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

### 4.6 The live run

`pipeline/run_live.py`. It fetches one 00 UTC run and builds the product.
**It publishes nothing**; publishing is section 8.

```
python -m pipeline.run_live              build the latest complete run
python -m pipeline.run_live --dry-run    decide which run, download nothing
```

#### Same code as the archive

The live run calls the **same** downloader and the **same** checks that built
Pile A: `download_one` from `ecmwf_download`, and `build_india_array`,
`quantum_summary`, `check_quantum_cap`, `check_daily_differences` and
`daily_totals` from `ecmwf_process`. No copies, no live-only variants.

An honest track record depends on this. If the live forecast were produced by
different code from the archive it is judged against, the record would be
measuring the wrong thing. The only difference is the `source` argument:
`ecmwf` live, `google` for the archive (section 2.6).

Because the downloader writes to `data/raw/<date>/`, the live run downloads
there, runs the checks there, and **moves** the 12 raw files into
`data/live/<run_id>/raw/` once the product is written, leaving nothing of its
own in Pile A's directory. A run that fails a check leaves its raw files in
`data/raw/<date>/` for inspection, as a failed Pile A date does.

#### Run selection

| # | Rule |
|---|---|
| 1 | Only `00` UTC runs are eligible. A run at any other hour is ignored, whatever its id looks like |
| 2 | An **incomplete run is never used**. The newest complete 00 UTC run is used and the incomplete newer one is named in the log |
| 3 | A run is never built when one at least as new has already been built. This covers both "an older run never replaces a newer one" and "the same run is never republished" |

`select_run(listing, published)` is a pure function: a listing in, a decision
and a **reason in words** out. No network, no disk, no clock. That is what
makes the rules testable without the network, and it is why the reason is
returned rather than logged from inside.

A run id is `YYYYMMDDTHHZ`, for example `20261112T00Z`. Twelve characters,
and it sorts chronologically as plain text, so "newest" needs no date
parsing. `data/live/last_run.json` holds the last run built, which is what
rule 3 compares against.

**File-level completeness** is decided by `Client.latest`, which walks back
from today and returns the newest run for which every file of the request
returns HTTP 200. **Member-level completeness** is decided afterwards by the
section 2.5 checks, which require 51 members at all six steps. Both must
pass; the first stops a run being chosen, the second stops it being built.

#### One per-square record

The stored record for a square is its **51 member daily totals for the five
lead days**. Counts (4.2) and dot categories (4.3) are both derived from that
same array, in one function, every run.

This is deliberate. If counts and dots were computed or stored separately the
map could show "40 of 51" while the panel drew 39 dots at or above the line,
and there would be no way for a reader to tell which was wrong. Four
identities are asserted on every square of every day **at run time**, not
only in the tests:

```
dots[under 1] + dots[1-10] + dots[10-50] + dots[50+]  ==  51
count(>= 1 mm)   ==  dots[1-10] + dots[10-50] + dots[50+]
count(>= 10 mm)  ==  dots[10-50] + dots[50+]
count(>= 50 mm)  ==  dots[50+]
```

A run that breaks one of them fails rather than publishing numbers that
disagree with each other.

#### Day labels

Lead day n covers 00 UTC to 00 UTC starting n days after the run date, which
in IST is 5:30 am to 5:30 am. The label is built from those two instants, not
written out:

> `5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov`

IST is a fixed +05:30 with no daylight saving, so no timezone database is
needed and the offset is the same in every month. Both the run time and the
publish time are recorded in IST in the manifest, and the run time in UTC as
well.

#### What a run writes

`data/live/<run_id>/`:

| File | Contents |
|---|---|
| `squares.npz` | `member_totals` (5, 51, 129, 121) float32 mm; `counts` (3, 5, 129, 121) uint8; `dots` (4, 5, 129, 121) uint8; `india` mask; `lat`; `lon` |
| `days.json` | per lead day: steps, the window in UTC and IST, and the label |
| `raw/` | the 12 GRIB files the run was built from |
| `manifest.json` | run id, run and publish times, thresholds, dot categories, download summary, every check result, product shapes, the highest count per threshold and lead day over India, and `"published": false` |

**The manifest is written last, on purpose.** Its presence is the only signal
that everything else in the directory is complete and checked. `squares.npz`
is written through a `.part`, reopened and compared, then renamed, as
everywhere else in this project.

#### Running in GitHub Actions

The live run must work on Linux with **no login**. ECMWF open data needs no
credential: there is no netrc, no token, no key and no interactive step
anywhere in this path, which is why the live source is ECMWF's own server and
not something authenticated. Paths are built with `pathlib`, there is no
shell call and no Windows-only code.

**It exits non-zero on any failed check.** Anything raised by the downloader,
the section 2.5 checks, the quantum cap, the negative-difference rule, the
member count or the product identities is logged with its type and message
and returns exit code 1. Deciding not to build (nothing new, or the newest
run incomplete) is **not** a failure and exits 0, because the previous
forecast correctly stays up.

#### First real run

12 November 2026, run `20261112T00Z`, from `source="ecmwf"`:

| Measure | Result |
|---|---|
| Downloaded | 149.3 MB, 12 files, 130 s on 4 connections |
| Total wall clock | 2 min 26 s |
| Packing | `bitsPerValue` 12, coarsest quantum 0.25 mm, tolerance -0.5 mm |
| Longitude origin | 180.0 |
| Members | 51, numbered 0 to 50, at all six steps |
| Most negative daily difference | -0.125 mm, inside the -0.5 mm tolerance |
| Product | 2.7 MB compressed |
| Highest count at 10 mm over India, lead day 1 | 43 of 51 |

149.3 MB is about half what a May date cost, because of the 12-bit packing
change in section 2.1.

#### Tests

| File | Covers |
|---|---|
| `tests/test_lead_days.py` | lead day n is steps 24n to 24(n+1); the 0-24 window is never a lead day; windows meet exactly; IST labels across a month end and a year end; IST has no daylight saving |
| `tests/test_counts_dots.py` | the four identities on every square of a full grid; exactly 10.0 counts at 10 mm; each threshold boundary and the float just below it; a longhand per-member recount on a small grid |
| `tests/test_run_selection.py` | every rule above, with made-up listings; no network, no disk |

#### HC6

`handchecks/hc6_members.py` and `handchecks/results/hc6_members.csv`. All 51
members' accumulated `tp` at steps 24 and 48 for one rainy and one dry India
square, chosen from the run itself, with the day 1 difference, the three
threshold flags, the dot category, and our own counts in the header to
compare against.

Values are read with `codes_grib_find_nearest` from the ecCodes library, so
no pipeline code takes part in locating them. The ecCodes **command line**
tools would be the cleaner independent route, but they are not shipped in the
Windows pip wheel; there are no executables in the package and none on PATH.
This is the same limitation and the same substitute as HC1.

On run `20261112T00Z` the CSV reproduces our counts exactly: the rainy square
at 34.25 N, 73.5 E gives 51 at 1 mm, 40 at 10 mm and 0 at 50 mm, with dots
0/11/40/0; the dry square at 29.5 N, 75.5 E gives 0, 0, 0 with all 51 dots in
the under-1-mm category.

---

## 5. Verification method

Decided 12 November 2026. Every rule below is fixed; nothing here is still
an open proposal.

### 5.1 What a case is

One case is one combination of:

- a Pile A 00 UTC run date
- an India square (section 3.5)
- a lead day, 1 to 5
- a threshold, 1 mm, 10 mm or 50 mm

Each case has two sides:

| Side | Value |
|---|---|
| Forecast | `count / 51`, the share of model runs reaching the threshold |
| Observed | 1 if the event happened, 0 if it did not |

The event is the same on both sides: the **square-average daily total reaches
the threshold**, using the same "greater than or equal to" rule as section 4.2.
On the forecast side that is each member's own daily total for the square. On
the observed side it is the IMERG value remapped to that square by the
area-weighted overlap of section 3.3.

`count / 51` is a share of model runs. It is used here as a probability for
scoring only. That does not make it a calibrated probability, and the site
never presents it as one (section 1.5).

### 5.2 What is excluded

- Any box-day that is not usable under section 3.4, meaning complete IMERG
  pixels cover less than 90% of the square.
- Every lead day of a Pile A date that failed (section 3.6).

Exclusions are **counted and published**, never silently dropped. The report
card states how many cases were possible, how many were used, and why the rest
were not.

### 5.3 Score

The Brier score, the mean squared difference between the forecast share and
the observed 0 or 1:

```
BS = mean over cases of (forecast - observed)^2
```

Lower is better. 0 is perfect.

#### The reference forecast

Skill is measured against a reference that **uses hindsight**: the observed
event frequency within one **reference group**, taken from our own sample,
unsmoothed. A reference group is one combination of:

- an India square
- the calendar month of the **day being forecast**
- the lead day, 1 to 5
- the threshold, 1 mm, 10 mm or 50 mm

The reference for a case is the share of that group's own cases in which the
event was observed. Because the group is keyed on exactly the four things
that define a case apart from the run date, that share is **exactly the best
constant forecast for those cases**: no other single number has a lower
Brier score over them.

This is the best constant forecast that group could have had, and it could
only be built after seeing the answers. Our skill against it is therefore a
**conservative lower bound**, and the site says so wherever skill is shown.
A forecast that beats it has beaten a reference it could never have had in
advance.

The calendar month is the month of the **day being forecast**, in UTC, not
the month of the run date. The climatology describes the weather of the
observed day, so that is the day it should be keyed to. This matters only for
runs within 5 days of a month end.

Keying the reference on lead day and threshold as well as square and month
costs nothing in fairness and removes two more ways of manufacturing skill.
The observed frequency of a square-month does not depend on lead day, so in
a complete sample the lead-day keys would hold near-identical values; they
differ only through the exclusions of section 5.2, which fall differently on
different lead days. Keying on them means the reference is computed from the
same cases the forecast is scored on, never a different set.

#### Computing it per reference group before pooling

The reference is worked out **per reference group first**, and only
then pooled:

```
BSS = 1 - (sum of case Brier scores) / (sum of case reference Brier scores)
```

summed over the cases in the group, with each case's reference being its own
reference-group frequency.

Pooling squares with different climates before computing the reference
manufactures skill that is not there: a forecast can look skilful merely by
knowing that Cherrapunji is wetter than Jaisalmer, which is geography, not
forecasting. Computing the reference per reference group first removes that
(Hamill and Juras, 2006).

### 5.4 Groups

Results are reported per **region x lead day x threshold**.

**Lead days are never mixed.** A Day 1 forecast and a Day 5 forecast are
different products and pooling them hides the decay that matters most.

#### Regions

The four **homogeneous rainfall regions** the India Meteorological Department
uses for its own rainfall reporting: **Northwest India**, **Central India**,
**South Peninsula** and **East & Northeast India**.

They are not our invention and not straight lines on a grid. They are IMD's
groupings of its 36 meteorological subdivisions, taken from the
subdivision-wise rainfall table that IMD prints under those four headings:

> India Meteorological Department, **Annual Report 2025**, Table 1,
> "Subdivision-wise rainfall (mm) distribution", page 96.
> <https://metnet.imd.gov.in/docs/imdnews/ANNUAL_REPORT2025English.pdf>

| Region | IMD meteorological subdivisions, as printed in that table |
|---|---|
| East & Northeast India | Arunachal Pradesh; Assam & Meghalaya; NMMT; SHWB & Sikkim; Gangetic West Bengal; Jharkhand; Bihar |
| Northwest India | East U.P.; West U.P.; Uttarakhand; Har., Chd & Delhi; Punjab; Himachal Pradesh; J&K and Ladakh; West Rajasthan; East Rajasthan |
| Central India | Odisha; West Madhya Pradesh; East Madhya Pradesh; Gujarat region; Saurashtra & Kutch; Konkan & Goa; Madhya Maharashtra; Marathwada; Vidarbha; Chhattisgarh |
| South Peninsula | A & N Island; Coastal A.P. & Yanam; Telangana; Rayalaseema; Tamil., Pudu. & Karaikal; Coastal Karnataka; N.I. Karnataka; S.I. Karnataka; Kerala & Mahe; Lakshadweep |

That is 7 + 9 + 10 + 10 = 36 subdivisions, IMD's full set.

Two of these placements are IMD's and would not be guessed from the names:
**Odisha is in Central India**, not in the east, and the **Andaman & Nicobar
Islands are in South Peninsula**, not in the east. We follow IMD.

#### From subdivisions to states

Subdivisions are not polygons we have, so each one is translated to the
states and union territories it covers. **No subdivision boundary cuts
across a state boundary in a way that would split a state between two
regions**, so no choice had to be made:

| Region | States and union territories |
|---|---|
| Northwest India | Uttar Pradesh, Uttarakhand, Haryana, Chandigarh, Delhi, Punjab, Himachal Pradesh, Jammu and Kashmir, Ladakh, Rajasthan |
| Central India | Odisha, Madhya Pradesh, Gujarat, Dadra and Nagar Haveli and Daman and Diu, Goa, Maharashtra, Chhattisgarh |
| South Peninsula | Andaman and Nicobar, Andhra Pradesh, Telangana, Tamil Nadu, Puducherry, Karnataka, Kerala, Lakshadweep |
| East & Northeast India | Arunachal Pradesh, Assam, Meghalaya, Nagaland, Manipur, Mizoram, Tripura, Sikkim, West Bengal, Jharkhand, Bihar |

All 36 Natural Earth admin-1 units with `admin = India` appear exactly once.

Puducherry is the one union territory IMD splits across subdivisions:
Puducherry and Karaikal go with Tamil Nadu, Yanam with Coastal Andhra
Pradesh, Mahe with Kerala. All three subdivisions are in South Peninsula, so
the whole territory lands in one region regardless. The same holds for Daman,
Diu and Dadra & Nagar Haveli, which IMD divides between Gujarat region and
Saurashtra & Kutch, both Central India.

#### Assigning a square

| # | Rule |
|---|---|
| 1 | An India square (section 3.5) belongs to the region of the **state its centre falls in** |
| 2 | Inside-or-on-boundary counts, by the same `covers` test as section 3.5 |
| 3 | A square whose centre is inside the India outline but **in no Indian state polygon** goes to **Northwest India** |

Rule 3 exists because the outline is the India point-of-view edition of
Natural Earth while admin-1 is not: Gilgit-Baltistan, Pakistan-administered
Kashmir and Aksai Chin are inside the India outline but have no Indian state
polygon over them. All of them are in the northwest, so Northwest India is
where they belong.

Rule 3 is **only** safe while every such square is in that northern area. If
the fallback ever catches a square elsewhere, for example on a coast where
the admin-0 and admin-1 coastlines disagree, that is a fault to be fixed and
not to be absorbed silently. The build therefore prints the latitude and
longitude range of every square the fallback catches, and whether any of them
is a coastal square.

**Boundaries source.** Natural Earth 1:10m Admin 1 – States, Provinces,
`ne_10m_admin_1_states_provinces`, version **5.1.1**, **public domain**,
SHA256 `efc59726337323058f9446210adc96673179cd344e053666ee3d28cb58ba2b05`
for the zip as downloaded. This is a different file from the admin-0 outline
of section 3.5 and is recorded separately. Natural Earth publishes no
point-of-view edition of admin-1, which is why rule 3 is needed.

#### Square counts

Measured on 12 November 2026 from `config/india_mask.json` and the admin-1
file above:

| Region | Squares |
|---|---|
| Northwest India | 1,501 |
| Central India | 1,510 |
| South Peninsula | 857 |
| East & Northeast India | 745 |
| **Total** | **4,613** |

Of the 1,501 Northwest India squares, **183** are there by rule 3. All 183
have centres between 33.0 N and 37.0 N and between 72.75 E and 80.25 E, and
**none** is a coastal square, which is what rule 3 requires.

No region is anywhere near too small to report, so the merging rule the
earlier draft needed is gone.

#### Region tests

Asserted the same way as the mask tests of section 3.5, on the **nearest
India square** to each place:

| Place | Expected region |
|---|---|
| Delhi, Jaipur, Srinagar | Northwest India |
| Mumbai, Bhopal, Ahmedabad | Central India |
| Chennai, Bengaluru, Thiruvananthapuram | South Peninsula |
| Kolkata, Patna, Guwahati | East & Northeast India |

All twelve pass. Two of them are worth knowing about:

- **Mumbai.** The 0.25-degree square that contains the city has its centre at
  19.00 N, 73.00 E, in the Panvel–Thane creek, so it is not an India square
  at all under the centre rule of section 3.5. The nearest India square is
  19.25 N, 73.00 E, in Maharashtra, Central India. The test is written against
  the nearest India square for exactly this reason.
- **Delhi.** The square nearest the city centre has its own centre at
  28.50 N, 77.25 E, which falls in Haryana rather than in Delhi. Both are
  Northwest India, so the region is right. The state is only a routing device
  and is never displayed.

### 5.5 Uncertainty

Bootstrap by resampling **whole start dates**, with replacement, 1000 times.
A resample takes all squares and all lead days of a chosen date together.

Reported as the 2.5th and 97.5th percentiles of the resampled statistic, a
95% range.

Whole dates are the unit because squares on the same day are strongly
correlated, and so are lead days from the same run. Resampling individual
cases would treat one weather system as thousands of independent facts and
would make the range far too narrow.

#### The reference is not resampled

The reference of section 5.3 is computed **once, from the full sample**, and
then held fixed through all 1000 resamples. It is not recomputed inside each
resample.

The reference is the yardstick. Recomputing it per resample would let the
yardstick move with the measurement and would mix two different kinds of
uncertainty into one range. The range we publish is the uncertainty in **our
skill against a fixed reference**, and that is what it is labelled as.

#### Adding up per start date first

Before resampling, each group's cases are collapsed to **one row per start
date** holding three numbers:

| Field | Meaning |
|---|---|
| `n` | cases used from that date |
| `sum_bs` | sum of the case Brier scores |
| `sum_ref` | sum of the case reference Brier scores |

A resample is then a draw of dates with replacement and a sum of their rows:

```
BSS = 1 - (sum of sum_bs over drawn dates) / (sum of sum_ref over drawn dates)
```

This is **exactly** the same number as resampling the cases of those dates
and recomputing, because the statistic is a ratio of sums over cases and the
unit of resampling is the whole date. 1000 resamples then cost 1000 sums over
at most 177 rows instead of 1000 passes over tens of thousands of cases.

### 5.6 Tier 1

| Output | What it shows |
|---|---|
| Reliability diagram | per bucket: mean forecast, observed frequency, and the number of cases |
| 8 mm / 12 mm sensitivity | everything recomputed at 8 mm and 12 mm, to see whether the 10 mm labels survive a small change in where the line sits |
| 2-degree base-rate map | how often the event actually happened, aggregated to 2-degree boxes |

The case count per bucket is shown **next to** every point on the reliability
diagram, not in a footnote. A bucket holding 30 cases and one holding 30,000
look identical otherwise.

If a label changes between 8 mm and 12 mm, that is published next to the
label. A result that only holds at exactly 10 mm is not a result.

Reliability buckets: `count = 0` on its own, `count = 51` on its
own, and the remaining values in 10 equal-width buckets of 0.1. The two
extremes are separated because they are by far the most common forecasts and
burying them in a 0-0.1 bucket would hide most of the behaviour.

### 5.7 Tier 2

| Output | Note |
|---|---|
| CRPS | on the ensemble of daily totals, not on the thresholded events |
| Brier decomposition | on the exact `k/51` values, so reliability, resolution and uncertainty **add up exactly** |
| CORP isotonic diagnostic | labelled clearly as a **different decomposition**, not a second opinion on the first |
| High-randomError sensitivity | results recomputed with squares of high IMERG `randomError` removed |
| Per-block skill | skill by contiguous blocks of dates, to show whether it is steady or driven by one period |
| Control vs 50 | report card published with all 51 members and with the 50 perturbed members only (section 2.1) |

The Brier decomposition uses the exact `k/51` values as its bins, 52 of them,
because that is what makes the three terms sum to the Brier score exactly.
Binning first would leave a within-bin remainder, and a decomposition that
does not add up is not a decomposition.

CORP and the classical decomposition answer different questions and can
disagree without either being wrong. Both are shown, each labelled with what
it is.

### 5.8 Tier 3

A long-term "usual chance" from IMERG **Final**, earlier years.

If that data is not present, the site shows **no** "usual chance" at all. It
does not fall back to the hindsight reference of section 5.3, because a
figure built from our own 177 days is not a long-term normal and presenting it
as one would be dishonest.

### 5.9 Wording

Verification language is always "**agreed with the satellite estimate**".
Never "correct", never "right", never "accurate".

IMERG is an estimate from space with its own errors (section 2.3). When the
forecast and IMERG disagree, we do not know which one was wrong, and the
wording must not imply that we do.

### 5.10 Finding: a sub-cell offset between forecast and IMERG rainfall

Measured 12 November 2026, HC-ALIGN parts 2 and 4,
`handchecks/results/hc_align.txt`. Recorded here because it was found before
any verification output existed, and because the answer was not the expected
one.

#### What was measured

The spatial correlation between the lead day 1 ensemble mean and IMERG,
across India squares within a date and then averaged over dates, with the
**target cell edges** moved by `dlat` north and `dlon` east before the
remapping of section 3.3 is rebuilt. Moving our cell north makes it read
IMERG from further north, so a negative `dlat` here is the same direction as
"the IMERG map moved north".

A whole-cell scan first (65 dates) found the correct pairing beaten by a
one-cell northward shift by 0.0002, and east ahead of west by 0.016. That
shape peaks near half a cell, which is what a **centre-versus-corner mistake
in our own grid handling** would produce, so it was followed up rather than
written off as a tie.

The follow-up scanned `dlat` and `dlon` over 13 values each from -0.25 to
+0.25 degrees, 169 remappings, on 82 dates. The local weight builder used
for the scan was proved to reproduce `pipeline/nasa_process.py` **exactly**
at zero shift, worst difference 0.000e+00 mm over 15,609 cells, before any
of its results were read.

#### The result

| | |
|---|---|
| Correlation unshifted | **0.5933** |
| Peak of the surface | **0.5958** at `dlat` -0.100, `dlon` -0.050 |
| Gain from shifting | **+0.0025** |
| Same peak as a map movement | 0.100 degrees north, 0.050 degrees east |

The top of the surface is a **plateau**, not a point: everything between
`dlat` -0.200 and -0.050 and `dlon` -0.200 and 0.000 sits within 0.002 of the
peak, and the row at `dlat` -0.125 is slightly **lower** than its neighbours
either side. Nothing singles out a half cell.

The surface is clearly asymmetric, though: at `dlat` +0.25 it falls to 0.5760
while at -0.25 it is still 0.5923. There is a real, small displacement, of
roughly 0.05 to 0.15 degrees, which is 5 to 17 km.

#### Per region, per lead day, and for the control alone

82 dates. Each slice's own peak, found over the same 169 shifts:

| Slice | Squares | r unshifted | Own peak (dlat, dlon) | r there |
|---|---|---|---|---|
| All India, day 1, ensemble mean | 4,613 | 0.5933 | -0.100, -0.050 | 0.5958 |
| Northwest India | 1,501 | 0.4842 | +0.000, -0.200 | 0.4877 |
| Central India | 1,510 | 0.5487 | +0.000, -0.050 | 0.5495 |
| South Peninsula | 857 | 0.6118 | **+0.050**, +0.000 | 0.6120 |
| East & Northeast India | 745 | 0.4365 | -0.100, **+0.050** | 0.4434 |
| All India, day 3, ensemble mean | 4,613 | 0.5385 | -0.100, -0.050 | 0.5397 |
| All India, day 1, control member | 4,613 | 0.5013 | -0.150, -0.050 | 0.5044 |

**The four regions disagree, including in sign.** South Peninsula peaks to the
*south* in latitude, East & Northeast India to the *east* in longitude, and
Northwest India four times further west than Central India. A mistake in our
grid arithmetic would be identical everywhere, because the same code and the
same two grids are used for every square.

#### The decision rule and the verdict

Fixed in advance, before these numbers were seen: *a peak within 0.03 degrees
of 0.125 in both latitude and longitude, in the direction parts 1 to 3 point
to, and the same in all four regions and at lead day 3, is a bug in our grid
handling; anything else is a property of the model or of IMERG.*

No slice meets it. The closest latitude is 0.025 away from a half cell and
the closest longitude 0.075 away, the regions disagree in sign, and the
plateau has no feature at 0.125.

**Verdict: not a grid bug.** It is recorded here as a property of the
forecast or of the satellite estimate, most likely both: a model places
orographic and convective rain slightly differently from where a satellite
retrieval puts it, and 5 to 17 km is well inside the 31 km the model actually
resolves (section 2.1).

#### Independent evidence that our grids are right

Read without any pipeline code, from the real files (HC-ALIGN parts 5 and 6):

| Source | Finding |
|---|---|
| GRIB header | first latitude 90.0, last -90.0; first longitude 180.0, last 179.75; both increments 0.25; `Ni` 1440, `Nj` 721; `scanningMode` 0, `iScansNegatively` 0, `jScansPositively` 0, `jPointsAreConsecutive` 0; `gridType` `regular_ll` |
| ecCodes `find_nearest` at 20.25 N, 72.75 E | returns grid point 20.25 N, 72.75 E at distance **0.000000 km**, so our cell centres are ECMWF grid points exactly |
| ecCodes step 48 minus step 24, control, 35.5 N 76.75 E | 34.000000 - 11.750000 = **22.250000 mm**, against our stored 22.250000 mm, difference 0.000e+00 |
| IMERG coordinates | latitude 1800 values -89.95 to 89.95 ascending, longitude 3600 values -179.95 to 179.95; **no `lat_bnds` or `lon_bnds` published**, only `time_bnds`, so pixel edges must be derived as centre plus or minus 0.05 and asserted against -90/90 and -180/180 as section 3.7 does |

#### What follows from this

- Verification is computed on the **unshifted** pairing. Always.
- **No data is ever shifted to improve a score.** Not the forecast, not the
  observation, not for a region, not for a lead day. A score that needed the
  grids moved to look better would not be a score of anything.
- The offset is published with the track record, because it is part of why
  forecast and satellite disagree at this scale, and a reader comparing a
  0.25 degree square against where rain actually fell deserves to know that
  the two sources place rainfall about 10 km apart on average.
- It is re-measured whenever the archive grows materially, and this section
  is updated with the new figures rather than kept as a one-off.

---

## 6. Trust labels

Decided 12 November 2026. Every rule below is fixed.

### 6.1 Scope

A label is assigned per **region x lead day x threshold**, from 00 UTC runs
only.

The **Brier score decides** the label. If CRPS disagrees, pointing the other
way, the label still follows Brier but the disagreement is **disclosed next to
the label**. Picking whichever score flatters the result would make the label
meaningless.

### 6.2 Good track record

Requires **all four** conditions. Any one failing drops the group to a lower
label.

| # | Condition |
|---|---|
| 1 | Enough data (6.3) |
| 2 | The 95% range for skill has its **lower end above 0** |
| 3 | That range has a **half-width of 0.10 or less** |
| 4 | Small honesty error (6.4) |

Condition 2 says the forecast beat the hindsight reference. Condition 3 says
we know that well enough to say it out loud; a range of plus or minus 0.4 that
happens to sit above 0 is not knowledge.

### 6.3 Enough data

All three:

| Requirement | Figure |
|---|---|
| Cases in the group, as defined in 5.1, with a usable observed box-day | at least **1,000** |
| Distinct start dates contributing any case | at least **30** |
| Distinct start dates on which the event was **observed** at least once | at least **20** |

The third condition is the one that actually binds.

The case count is deliberately the weakest of the three. With about 4,613
India squares and 177 dates, even a small region reaches tens of thousands of
cases, so a case minimum is close to free. Cases on the same day are not
independent, so the real guard against a thin sample is the bootstrap
half-width of condition 3, which is computed over dates.

The 20-dates rule is what stops a label resting on one freak week. A region
can have 80,000 cases and still have seen 50 mm of rain on only three days,
and that group must not be called a good track record.

### 6.4 Small honesty error

Every **counted** reliability bucket has its observed frequency within
**0.10** of its mean forecast.

A bucket is counted only if **both** hold:

| # | Requirement |
|---|---|
| 1 | at least **100 cases** |
| 2 | those cases come from at least **10 different start dates** |

Buckets that fail either test are ignored for this test and are **still
drawn** on the diagram with their counts, so a reader can see what was set
aside.

The 10-dates requirement is there for the same reason as the 20-dates rule in
6.3. Cases on one day are not independent, so 100 cases from two weather
systems say far less than 100 cases from fifty, and a bucket that passed on
the strength of one wet week would be the easiest way for a wrong label to get
through.

**0.10 is not a rounding argument.** Displaying "About 40%" rounded to the
nearest 10 only hides an error of up to 0.05, so rounding would justify 0.05,
not 0.10. 0.10 is a judgement about what the word "about" can carry: a
forecast displayed as "About 40%" whose events happened 30% or 50% of the time
is still recognisably that forecast, while 20% or 60% is not. The figure is
fixed here, before any results exist, and section 6.8 is what stops it moving
afterwards.

### 6.5 Rough guide

Enough data under 6.3, but **any** of conditions 2, 3 or 4 fails.

When the 95% range **includes 0**, the wording is exactly:

> slightly better than the usual rain for this place and month, but the
> difference could be luck

That sentence is fixed. It says what was measured and admits what is not
known, and it is not to be reworded into something more confident.

### 6.6 Not enough past data

Everything else. The group has not earned a statement about its skill, so no
statement is made.

### 6.7 Display

| Label | Shows | Colour |
|---|---|---|
| Good track record | "About 40%", rounded to the nearest 10 | green |
| Rough guide | "20 of 51 runs" **and** "came true about 2 times in 10" | amber |
| Not enough past data | the count only, "20 of 51 runs" | grey |

**Never two competing percentages.** The two numbers on a rough guide are
different quantities, not two estimates of the same thing, and they are
labelled so:

- "20 of 51 runs" is what the model said.
- "came true about 2 times in 10" is what happened in the past when it said
  something like that.

"came true about N times in 10" is the observed frequency of the reliability
bucket this forecast falls into, for this region, lead day and threshold,
rounded to the nearest whole number out of 10. The phrase is shown only if
that bucket is a **counted** bucket under 6.4, meaning at least 100 cases from
at least 10 different start dates. Otherwise the phrase is **omitted** and
only the count out of 51 is shown, because the floor that governs what we
test in 6.4 also governs what we are willing to say out loud.

A "Good track record" percentage is only ever shown with a green label.
Without that label the site shows the count out of 51 instead. A large
percentage implies reliability, so it has to be earned by the record rather
than printed by default.

### 6.8 Rules fixed before results

Every rule in sections 5 and 6 is fixed **before** any verification output is
produced. Nothing is tuned after seeing the scores.

`results/verification_meta.json` records, for the run that produced the
figures:

- the SHA256 of `SPEC.md` as committed
- the git commit hash
- the date range of Pile A used, and the number of dates that failed
- the IMERG version
- counts of cases possible, used and excluded, with reasons

If `SPEC.md` changes after results are published, the hash no longer matches
and that is visible. The point is that nobody, including me, can quietly move
a threshold after seeing which side of it the answer fell.

---

## 8. Publishing

Section 4.6 builds a run and publishes nothing. This section is how a built
run reaches the website, and nothing else. Two constraints shape all of it:

1. **The write token never touches this laptop.** Every write to the store
   happens inside GitHub Actions. This laptop can only read public URLs.
2. **Nothing is published unless the run passed every check.** The local
   `manifest.json` of section 4.6 is the only thing that says it did.

### 8.1 A note on the section number

The first draft list called section 8 "Website and API". Publishing turned out
to be the whole of it, so section 8 is publishing and the data contract the
site reads from the store. The React and MapLibre pages and the `api/`
functions move to section 11, display rules. Nothing else is renumbered.

Two things are added to the fixed structure in CLAUDE.md:

| Added | Why |
|---|---|
| `scripts/publish/` with `package.json`, `package-lock.json`, `blob.mjs` | the only Node in the project, kept in one folder so it cannot be mistaken for the website's own `web/` dependencies |
| `data/publish/<run_id>/` | the exact bytes that were uploaded, kept locally for comparison. Never committed, like the rest of `data/` |

The workflow is `.github/workflows/forecast.yml`, the file the fixed structure
already names. **There is no backfill in Actions.** Pile A and Pile B run on
this laptop, against the Google archive and Earthdata, so the only scheduled
job there is ever the live one and it does not need a file of its own.

### 8.2 The store, the library and the pinned versions

One **public** Blob store. Public because the forecast is meant to be public,
and a public blob is readable by URL with no credential: the website needs no
server in front of it, and this laptop can check what was published without a
token. Access is chosen when the store is created and each upload must state
the same access.

Everything below was read from Vercel's own documentation on 12 November 2026
and is marked `[verified]` where the behaviour the code depends on is stated
there explicitly.

| Fact | Value |
|---|---|
| Library | `@vercel/blob` **2.9.0**, `engines.node >= 20.0.0` `[verified]` |
| Public URL form | `https://<store-id>.public.blob.vercel-storage.com/<pathname>` `[verified]` |
| Reading a public blob | no token, no credential `[verified]` |
| `put` option `addRandomSuffix` | default `false` `[verified]` |
| `put` option `allowOverwrite` | default `false`; an existing pathname otherwise throws `[verified]` |
| `put` option `cacheControlMaxAge` | default one month, 2,592,000 s; **minimum 60 s** `[verified]` |
| `put` option `contentType` | guessed from the pathname extension when not given `[verified]` |
| Token | read by the SDK from `process.env.BLOB_READ_WRITE_TOKEN` `[verified]` |
| `list({prefix, cursor, limit, mode})` | returns `pathname`, `url`, `size`, `uploadedAt`, `etag`, plus `cursor` and `hasMore` `[verified]` |
| `del(pathname or array)` | permanent; deleting a blob that does not exist still succeeds `[verified]` |
| CDN after a delete | a deleted blob can still be served from cache for up to a minute `[verified]` |
| Conditional reads | the CDN sends an `ETag`; a browser `If-None-Match` gets `304` with no code on our side `[verified]` |
| HTML | cannot be hosted: Blob sets `content-disposition` itself `[verified]` |

Pinned for the workflow, all checked on 12 November 2026:

| Thing | Version | Why this one |
|---|---|---|
| Python | 3.13.4 | the same as `.python-version` and this laptop |
| Node | 24.22.3 | Active LTS, supported to 30 April 2028; 2.9.0 needs 20 or newer |
| `@vercel/blob` | 2.9.0 | exact, in `package.json` and locked in `package-lock.json`, installed with `npm ci` |
| Runner image | `ubuntu-24.04` | pinned, not `ubuntu-latest`: a runner image change should not change a forecast quietly |
| `actions/checkout` | v7.0.1 | |
| `actions/setup-python` | v7.1.0 | |
| `actions/setup-node` | v7.1.0 | |
| `actions/upload-artifact` | v7.0.2 | the logs of every attempt, kept 14 days |

The four action tags were confirmed to exist twice on 12 November 2026:
`api.github.com/repos/<owner>/<repo>/releases/latest` named them as the latest
release (checkout v7.0.1 of 20 July 2026, setup-python v7.1.0 of 22 October
2026, setup-node v7.1.0 of 8 October 2026, upload-artifact v7.0.2 of 7
October 2026), and `git ls-remote --tags` against each repository returned
the tag with its commit:

| Action | Tag | Commit the tag pointed at |
|---|---|---|
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v7.1.0 | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| `actions/setup-node` | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| `actions/upload-artifact` | v7.0.2 | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

The workflow uses the tags, not the commits, because a tag is readable. The
commits are recorded here so that a tag moved under us can be noticed.

### 8.3 What is published and what is not

| Published | Not published |
|---|---|
| the count out of 51 for each of 3 thresholds and 5 days, per square | the raw GRIB, 149 MB a run |
| per square, the counts and the four dot category totals | the accumulated `tp` at each step, which the daily totals are made from |
| per square, **all 51 members' five daily totals**, as integers (8.4) | anything else in `data/` |
| the day labels and windows | the IMERG observations and the verification archive |
| the run's own checks and download summary | |

The member totals are published so that the place panel can show what each of
the 51 model runs actually said, which is what section 4.3 asks of it, and not
only which category each one fell in. They are **displayed as whole
millimetres**; the stored value keeps more than that, so the display rule
belongs to section 11 and can change without republishing anything.

### 8.4 The layout in the store

Sizes are the real ones from run `20261112T00Z`.

| Pathname | Bytes | Cache max age | Contents |
|---|---|---|---|
| `manifest.json` | about 10 KB, 57 files with a sha256 each | **60 s** | the only blob that is ever rewritten: which `run_id` is current, the list of that run's files with a sha256 each, the day labels, the thresholds, the dot category names, and the last retention result |
| `runs/<run_id>/run.json` | about 3 KB | 2,592,000 s | the run's section 4.6 manifest: every check result, the download summary, the India maxima |
| `runs/<run_id>/grid.json` | about 3 KB | 2,592,000 s | the 129 latitudes, the 121 longitudes, the array order, the thresholds, the dot categories, the tile rule |
| `runs/<run_id>/days.json` | 1,571 | 2,592,000 s | per lead day: steps, the window in UTC and IST, the label |
| `runs/<run_id>/india.u8` | 15,609 | 2,592,000 s | 1 for an India square, 0 otherwise |
| `runs/<run_id>/counts/ge1mm_day1.u8` ... `ge50mm_day5.u8` | 15,609 each, 15 files | 2,592,000 s | the count out of 51, one byte a square |
| `runs/<run_id>/tiles/<lat>_<lon>.json` | 3,202,461 over 38 files | 2,592,000 s | per-square counts, dots and all 51 member totals |

**57 blobs and about 3.46 MB a run**, plus the one manifest, so the eight runs
of 8.7 are about 28 MB and 457 blobs.

The member totals are what made it that size: they are 1,176,315 numbers a
run, against 23,065 for the counts and the dots together. The largest tile is
172.5 KB and the median is 81.0 KB, fetched once when a square in it is
clicked and then cached for a month.

#### Why raw bytes for the grids

A count is an integer from 0 to 51, so one byte holds it exactly. 15,609
bytes read with one `fetch` and an `ArrayBuffer` beats about 60 KB of JSON
text that then has to be parsed, there is no number formatting to get wrong,
and the map fetches only the threshold and day it is showing rather than all
fifteen. The content type is set explicitly to `application/octet-stream`,
because `.u8` is not an extension Blob knows.

The order is stated in `grid.json` and here: **row major, index =
i × 121 + j**, with i going north to south from 38.00 N and j west to east
from 68.00 E, which is the same order as everything else in this project.

**255 means "outside India".** Counts are 0 to 51, so 255 cannot be mistaken
for one. Squares outside the India mask carry 255 rather than their computed
count, because a count for a square we never verify is a number we do not
stand behind. `india.u8` carries the same information and is published as
well, so a reader can mask without special-casing a magic number.

#### The tiles

A tile is a **4 degree by 4 degree block, named after its south-west corner
in whole degrees**: `tiles/20N_72E.json` holds the squares from 20.00 N to
23.75 N and 72.00 E to 75.75 E. For a square at (lat, lon) the tile is
`floor(lat / 4) × 4`, `floor(lon / 4) × 4`.

Measured on the real mask: the 4,613 India squares fall into **38 tiles**,
median 15.2 KB, largest 34.0 KB with 256 squares in it. Only tiles that hold
at least one India square exist, and `manifest.json` lists which, so the site
never asks for one that is not there.

One square's record, the real numbers for the HC6 rainy square on run
`20261112T00Z`, with `m` shortened to its first eight members of day 1 and
day 5 for printing:

```json
{"lat": 34.25, "lon": 73.5,
 "c": [[51,40,0],[41,3,0],[9,1,0],[0,0,0],[0,0,0]],
 "d": [[0,11,40,0],[10,38,3,0],[42,8,1,0],[51,0,0,0],[51,0,0,0]],
 "m": [[44,203,211,171,179,263,605,374, ...],
       ...,
       [0,0,0,0,2,0,0,0, ...]]}
```

`c` is five days of three counts, at 1, 10 and 50 mm. `d` is five days of the
four dot categories, in the order of section 4.3. `m` is five days of 51
member totals, in member order 0 to 50, as integers.

The four identities of section 4.6 are asserted again on the published
numbers, not assumed: a tile whose `c` and `d` disagree stops the publish. So
does a tile whose `m` does not reproduce its own `c` and `d`.

#### The member totals are integers, in steps of 0.0625 mm

A member total is stored as **the number of 0.0625 mm steps in it, rounded
down**: 12.6875 mm is 203. That is an unsigned 16-bit value, 0 to 65,535, so
the largest total it can carry is 4,095.9 mm against the 101.75 mm highest
member total over India on this run. The step is written in `grid.json`, so a
reader multiplies rather than guesses.

An unsigned type is safe because a member total is never negative by the time
anything sees it. The small negative differences section 3.6 tolerates are
set to 0 inside `daily_totals`, before the counts, the dots or this section
touch them, and anything below the tolerance raises instead. On run
`20261112T00Z` the lowest member total is **0.0 mm** over India and over the
whole window, with no negative value anywhere, after 61,338 differences had
been clamped. The publish checks it again and fails on a negative rather than
storing it as a large unsigned number.

Three reasons for that step and for rounding down rather than to the nearest:

1. **0.0625 mm is the finest quantum the data has.** GRIB packs each message
   with its own scale factors (section 2.1), so the step a member's total can
   land on varies by member and by forecast step. Measured on all 1,176,315
   India member-day totals of run `20261112T00Z`: every one is an exact
   multiple of 0.0625, while 32,942 of them are **not** multiples of 0.125 and
   144,954 are not multiples of 0.25. At 0.0625 the published integer times
   the step gives the stored total back exactly, with nothing lost.
2. **Rounding down cannot move a member across a threshold.** 1, 10 and 50 mm
   are all whole multiples of 0.0625, so `x >= T` and
   `floor(x / step) * step >= T` are the same statement. The counts and the
   dot categories computed from the published integers are therefore
   identical to ours, for every member, every day and every square. Checked
   on run `20261112T00Z` by rebuilding `counts` and `dots` from the integers
   with the same two functions the run itself used: both came back identical,
   array for array.
3. **Rounding to the nearest could not promise that.** A total of 9.9375 mm
   would become 10.0 at a 0.125 step, and the panel would show a member at
   the 10 mm line that our count does not count. Rounding down can only ever
   understate a member, never promote one.

A future run with an even finer quantum than 0.0625 mm would be rounded down
by less than one step, which still cannot change a count or a dot category.
The publish asserts that the integers reproduce the counts and the dots
exactly, so a run where that stops being true fails instead of publishing
numbers that disagree.

#### The displayed whole millimetre is rounded down too

The panel shows a member total as a whole number of millimetres, **rounded
down**: 9.9375 mm shows as 9, and 10.0 mm shows as 10. In integers it is one
division, `code // 16`, because 16 steps of 0.0625 mm make a millimetre.

Rounding the display down is what keeps the three things a reader sees about
one member in agreement. A member at 9.9375 mm is below the 10 mm line, so it
is not in our count of 51 and its dot is in the "1 to under 10 mm" category.
Displayed to the nearest it would read "10 mm", next to a dot in the under-10
category and a count that does not include it, and a reader comparing them
would be right to think one of the three was wrong. Rounded down it reads
"9 mm", and all three agree.

This holds for every value, not just the ones measured. 0.0625 mm divides
1 mm exactly, so flooring to the step and then flooring to the millimetre
gives the same whole number as flooring the true total straight away, and the
three thresholds are whole millimetres themselves. Display, dot category and
count cannot disagree about which side of a line a member is on.

A consequence worth stating plainly: a member total under 1 mm displays as
**0 mm** while its dot is still in the "under 1 mm" category and the 1 mm
count correctly excludes it. Zero displayed does not mean no rain, it means
less than a millimetre, and section 11 has to word it that way.

The integers live in the tile JSON rather than in a separate binary file next
to it. Measured both ways on the real run: JSON is 3,202,461 bytes against
2,352,630 for raw 16-bit binary, 36% more, in exchange for the place panel
needing **one** fetch for a tile instead of two and the contract in 8.11
staying three requests long.

### 8.5 The order of writing, and why the manifest is last

Run files first, in any order, because none of them refers to another. Then
`manifest.json`.

Until the manifest is rewritten, the store still describes the **previous**
run and the site still shows it, however many of the new run's files are
already uploaded. The manifest moving is the one moment the published
forecast changes, and it is a single small write. This is the same rule as
on disk in section 4.6, for the same reason.

Run files are written with `allowOverwrite: true` even though a run id is
immutable. A publish that dies halfway has to be retryable, and the default
would make the retry throw on the files that already arrived. What stops a
run being published twice is the manifest comparison in 8.6, not the store
refusing a write. The bytes cannot differ between attempts: both the run id
and the bytes come from the same checked run directory.

`addRandomSuffix` stays `false`, because every pathname has to be predictable
from the run id.

### 8.6 Run selection in Actions reads the store, not the disk

The Actions disk is empty at the start of every run, so
`data/live/last_run.json` is never there and rule 3 of section 4.6 would
never bite: every run would look unbuilt, and the same forecast could be
published twice a day. In Actions the "already built" value comes from the
store instead.

| # | Step | Token |
|---|---|---|
| 1 | `list` the store for `manifest.json`, fetch it, and take its `run_id` | **yes** |
| 2 | `run_live --published <that run id>`, so the section 4.6 rules apply unchanged | no |
| 3 | if a run was built, publish it; if not, exit 0 and leave the store alone | **yes** |

The manifest is read through the SDK's `list` and the URL it returns, not
through a hostname written into the repository. The store id is not a secret,
it appears in every public URL, but hard-coding it would mean editing the
repository if the store were ever recreated. With `list`, the token is the
only thing that has to exist, which is why step 1 needs it as much as step 3
does. Step 2 needs no credential of any kind (section 4.6).

The fetch of the manifest in step 1 uses the same cache-busting query as the
read-back in 8.10. Without it the CDN could hand back the manifest from
before the last publish, for up to the 60 s of 8.4, and run selection would
then be deciding against a run id that is already out of date.

#### An empty store and a broken store are not the same thing

| What happened | Treated as | Exit |
|---|---|---|
| `list` succeeded and found no `manifest.json` | an empty store, before the first publish. `published` is `None`, the newest complete run is built and published | 0 |
| `list` failed: no token, wrong token, store gone, suspended, rate limited, network error | **a failure** | **1** |
| `list` succeeded, the manifest's URL could not be fetched, or did not return 200 | **a failure** | **1** |
| the manifest was fetched but is not JSON, or has no `run_id`, or its `run_id` is not a valid 12-character run id | **a failure** | **1** |

This distinction is the whole of it. If any of the lower three rows were
quietly treated as "no manifest, so the store is empty", a token that had
expired would make the run selection of section 4.6 believe nothing had ever
been published, and the same forecast would be published again, every day,
with the retention of 8.7 counting runs that were already there. Failing
loudly leaves the previous forecast up and sends a red workflow, which is the
correct outcome: a publishing problem is not a forecast.

#### Exit codes

| Situation | `run_live` | `publish` | Workflow | What the site shows |
|---|---|---|---|---|
| the store could not be listed, or its manifest could not be fetched or parsed | not run | **1** | **failure** | the previous run |
| nothing new | 0 | 0, "nothing to publish" | success | the previous run, correctly |
| the newest run is incomplete | 0 | 0 | success | the previous run |
| a check failed | **1** | not run | **failure** | the previous run |
| upload failed before the manifest | 0 | **1** | **failure** | the previous run, because the manifest never moved |
| upload failed after the manifest | 0 | **1** | **failure** | the new run, with retention not yet done |

Deciding not to publish is never a failure. Failing a check always is.

### 8.7 Retention: the newest eight runs

| # | Rule |
|---|---|
| 1 | Retention runs **after** the new manifest is in place, never before |
| 2 | The run the manifest points at is **never** deleted, whatever its position in the list |
| 3 | Run prefixes sort as plain text, which is chronological for a run id, so the newest eight are kept and anything older is deleted |
| 4 | Every deletion is logged with its pathname, its bytes and the run it belonged to, and the totals go into the next manifest's `retention` block |
| 5 | A prefix under `runs/` that is not a valid 12-character run id is logged and **left alone**, so a stray hand-uploaded file cannot be destroyed by a cron |

Eight is about a week of daily runs: enough to show the site's recent history
and to re-check a published forecast against the bytes that were published,
while the store stays near 7 MB.

Deleting an old run blob loses nothing the track record needs. The forecast
archive that verification uses is `data/india/ecmwf/` on this laptop, and the
frozen results are `results/` in the repository. The store is a delivery
copy, not a record.

### 8.8 The workflow

`.github/workflows/forecast.yml`, one job, nine steps:

| # | Step | Token on it |
|---|---|---|
| 1-5 | checkout, Python 3.13.4, Node 24.22.3, `pip install -r requirements.txt`, `npm ci` in `scripts/publish` | no |
| 6 | `python -m pipeline.publish remote-run-id`, the store's current run id (8.6) | **yes** |
| 7 | `python -m pipeline.run_live --published <that run id>` | **no** |
| 8 | `python -m pipeline.publish`: upload, manifest last, retention, read back | **yes** |
| 9 | the logs as an artefact, `if: always()`, kept 14 days | no |

Step 6 prints the run id on standard output and **nothing else**, with its
own log going to standard error, so step 7 can be handed the value without
parsing anything. An empty value means an empty store, and `run_live` takes
`--published ""` to mean exactly that rather than falling back to
`data/live/last_run.json`, which on a fresh Actions disk is always missing
anyway.

Step 8 runs whether or not step 7 built anything: with nothing new on the
disk it prints "nothing to publish" and exits 0.

**The schedule is live from the moment this file is on `main`.** Until the
secret of 8.9 exists, every scheduled attempt fails at step 6 with a missing
token, which costs one runner minute, downloads nothing and publishes
nothing. That is the right failure: the alternative, skipping quietly when
the secret is absent, would make a store that had stopped answering look the
same as a store nobody had set up yet.

| Setting | Value | Why |
|---|---|---|
| Triggers | `schedule` and `workflow_dispatch` | the dispatch is for the first publish and after a failure |
| Concurrency | group `live`, `cancel-in-progress: false` | two overlapping publishes could interleave uploads; a queued second attempt simply finds nothing new |
| Permissions | `contents: read` | the workflow writes nothing back to the repository |
| Timeout | 30 minutes | the first real run took 2 min 26 s |
| Runner | `ubuntu-24.04` | pinned |

**Schedule: `17,47 6-11 * * *`.** Twelve attempts, 06:17 to 11:47 UTC, which
is 11:47 to 17:17 India time.

Why it starts at 06:17 UTC. ECMWF publishes AIFS as soon as it is produced
and documents the 00 UTC deterministic AIFS at 05:45 UTC; our own first live
run found `20261112T00Z` complete at about 07:06 UTC. 06:17 is after the
earliest time ECMWF describes and before the time we have actually observed.

Why every thirty minutes until 11:47 UTC. If the run is late, or a scheduled
job starts late, the next attempt is half an hour away instead of a day. Once
the run is published, each remaining attempt costs one listing check and
exits 0.

Why minute 17 and 47. GitHub documents that scheduled workflows can be
delayed when load is high, and load clusters at the start of an hour, so
`:00` and `:30` are the two worst minutes available.

### 8.9 The token

| Question | Answer |
|---|---|
| Where it lives | a GitHub Actions secret named `BLOB_READ_WRITE_TOKEN`, and Vercel's own project environment |
| How the code gets it | `env: BLOB_READ_WRITE_TOKEN: ${{ secrets.BLOB_READ_WRITE_TOKEN }}` on **the two steps that talk to the store and no others**: step 2, which reads the manifest with `list`, and step 4, which publishes. The SDK reads it from `process.env` |
| Which step does **not** get it | step 3, `run_live`. It downloads from ECMWF open data, which needs no credential, and it must stay that way: a step that cannot see the token cannot leak it |
| What the repository holds | the name, and nothing else. `.env.example` gains the name with an empty value |
| What this laptop can do | read public URLs. It cannot list, upload or delete, and it has no token |
| Never | printed, echoed, written to a file, passed on a command line, or put in a `.env` here |

There is no `--token` flag on the uploader, on purpose: a command-line flag
appears in process listings and in Actions logs. The uploader never prints
its environment; a failure prints the error class and message only. If a
token is ever exposed it is rotated in the Vercel dashboard, not reused.

### 8.10 The two programs

**`pipeline/publish.py`** makes every decision and touches no network:

- which local run to publish: the newest `data/live/<run_id>/` that has a
  `manifest.json` and `"published": false`,
- whether it is newer than the store's current run id, and refusing if not,
- building the payload into `data/publish/<run_id>/`, exactly the bytes to
  be uploaded,
- the sha256 of every file, which goes into the manifest,
- the write order, the cache ages and the retention plan.

It reaches the store only through a `Store` interface with three methods:
`put(pathname, data, content_type, max_age)`, `list(prefix)` and
`delete(pathnames)`. `BlobStore` runs the Node script; `FakeStore` keeps
everything in a dictionary and records the order of every call, and is what
the tests use. No network code in the module that holds the rules.

**`scripts/publish/blob.mjs`** is the only code that talks to Vercel. One
JSON request on standard input, one JSON reply on standard output, three
verbs: `put`, `list`, `delete`. It holds no logic about runs, tiles or
retention.

`python -m pipeline.publish remote-run-id` is the step 2 of 8.8: it runs
`list`, fetches the manifest with the cache-busting query, and prints the
`run_id` for the workflow to pass to `run_live`. It prints an empty line and
exits 0 **only** when `list` itself succeeded and returned no manifest.
Everything else in that path, listed in 8.6, exits 1 and prints why.

#### Reading it back

After the manifest is written, `publish.py` fetches every published file from
its **public URL with no token** and compares the sha256 against the
manifest. A file that cannot be read back is a failure even though the bytes
are in the store, because the site reads those same URLs. It costs 3.46 MB of
download a run.

The manifest itself is fetched with a cache-busting query, because the CDN
may serve the previous manifest for up to the 60 s of 8.4. The run files are
new pathnames that were never cached, so they need no such trick.

### 8.11 What the website reads

The whole contract, in three requests:

| # | Request | For |
|---|---|---|
| 1 | `manifest.json` | the current run id, the day labels, the tile list, the thresholds |
| 2 | `runs/<run_id>/counts/ge<T>mm_day<d>.u8` | the map, 15,609 bytes, 255 outside India |
| 3 | `runs/<run_id>/tiles/<lat>_<lon>.json` | the place panel, on a square click: the counts, the four dot categories and all 51 member totals for that square |

A member total arrives as an integer in steps of 0.0625 mm, the step being
stated in `grid.json`. The panel shows **whole millimetres, rounded down**,
which is `code // 16`: 9.9375 mm shows as 9 and 10.0 mm shows as 10, so the
number shown, the dot category and the count always agree about which side of
a threshold that member is on (8.4). It never shows more precision than a
millimetre: a sixteenth of a millimetre is an artefact of how GRIB packs
numbers, not a distinction a five-day forecast can support.

No server, no database, no key: the pages can read the store directly.
`api/health` and `api/place` are built as well, in section 11, because the
fixed structure names them and `tests/test_api_consistency.py` exists to
prove that what `api/place` answers for a square is the same as what the tile
says for that square. The API is a second route to the same published bytes,
not a second source of numbers.

A reader who loads the page within 60 s of a publish may be served the
previous manifest. The page always shows the run id and the run time in IST,
so which forecast is on screen is never ambiguous.

### 8.12 Where the numbers live

In `pipeline/publish.py`, not `config.py`, for the same reason as section
3.7: `config.py` is imported by Pile A, which is still running, and it is not
being touched until it stops.

| Name | Value |
|---|---|
| `KEEP_RUNS` | 8 |
| `MANIFEST_MAX_AGE` | 60 s |
| `RUN_FILE_MAX_AGE` | 2,592,000 s |
| `TILE_DEGREES` | 4.0 |
| `NOT_INDIA` | 255 |
| `MEMBER_STEP` | 0.0625 mm |

### 8.13 Tests

`tests/test_publish.py`, all against `FakeStore`, no network and no token.

| Test | Covers |
|---|---|
| the manifest is the last write, and every file it names was written before it | 8.5 |
| an older local run never replaces a newer published one, and nothing at all is written | 8.6 |
| the same run is never republished, and nothing at all is written | 8.6 |
| a local run with no manifest, or already marked published, is not published | 8.1 |
| a `list` that succeeds and finds no manifest publishes the first run | 8.6 |
| a `list` that fails exits 1, publishes nothing, and is never read as an empty store | 8.6 |
| a manifest whose fetch returns 404 or 500 exits 1 | 8.6 |
| a manifest that is not JSON, has no `run_id`, or has a `run_id` that is not a valid run id, exits 1 | 8.6 |
| the manifest fetch during run selection carries the cache-busting query | 8.6 |
| retention keeps the newest eight prefixes and deletes the rest, blob by blob | 8.7 |
| retention never deletes the run the manifest points at, even when that run is the ninth newest | 8.7 |
| retention leaves a prefix that is not a valid run id, and logs it | 8.7 |
| no deletion happens before the manifest write | 8.7 |
| every sha256 in the manifest matches the bytes handed to the store | 8.10 |
| counts files are 15,609 bytes, 0 to 51 on India squares, 255 everywhere else | 8.4 |
| every India square is in exactly one tile, and in the tile the formula names | 8.4 |
| the four identities of 4.6 hold in the published tiles | 8.4 |
| every square's 51 member integers rebuild that square's own `c` and `d` exactly | 8.4 |
| member integers round **down**: a total of 9.9375 mm never becomes 10 mm, at any step | 8.4 |
| a member total that is an exact multiple of 0.0625 mm survives the round trip exactly | 8.4 |
| a member integer above 65,535, or a negative one, fails the publish | 8.4 |
| the whole-millimetre display rounds down: 9.9375 mm shows 9, 10.0 mm shows 10, 0.9375 mm shows 0 | 8.4 |
| for every member of every India square of a real run, the displayed whole millimetre is on the same side of 1, 10 and 50 mm as the count and the dot category | 8.4 |
| the cache ages are 60 s on the manifest and 2,592,000 s on every run file | 8.4 |

#### HC7

After the first real publish, and from this laptop with no token:
`handchecks/hc7_published.py` fetches the published tile and the published
counts byte for one square from their public URLs, and compares them against
that square's numbers in `data/live/<run_id>/squares.npz`, with the index
arithmetic written out longhand. Saved to
`handchecks/results/hc7_published.csv`.

### 8.14 Settled, and what is still open

Four of the five questions in the first draft of this section were decided on
review, 12 November 2026:

| Question | Decision |
|---|---|
| each member's millimetre value in the place panel | **published now**, as integers in the tiles (8.4), displayed as whole millimetres |
| whether `api/place` is built at all | **built**, in section 11, with `tests/test_api_consistency.py` holding it to the published tiles (8.11) |
| a Python-only publisher | **not taken.** `@vercel/blob` 2.9.0 in Node stays, with the decision rules and the tests in Python (8.10) |
| `robots.txt` in the store | **no action.** Nothing on the site links to a store URL as a page, and a crawler reading a count file costs a few kilobytes |

One thing is still open:

| # | Open | Note |
|---|---|---|
| 1 | the store name and its id | created by hand in the dashboard. Nothing in the repository depends on either: the id is never written down, because the manifest is found with `list` (8.6) |

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

7. Pipeline stages and file layout
9. Automation and failure handling
10. Testing strategy
11. Display rules, the website pages and the `api/` functions (8.1)
12. Tiers and acceptance tests

### Requirements already fixed for later sections

Recorded here so they are not lost between drafting groups.

**Section 8 is drafted** and is publishing, not "Website and API": see 8.1.

**Section 11, display rules.** A large percentage may be displayed **only**
when that forecast carries a "Good track record" label. Without that label the
site shows the count out of 51 instead. A big percentage implies reliability,
so it has to be earned by the record rather than printed by default.

**Section 12, tiers and acceptance tests.** A Tier 2 analysis compares the
control member against the 50 perturbed members, and the report card is
published both with 51 members and with 50 (section 2.1).
