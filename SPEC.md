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

HC6, which compares our counts against ECMWF's own published probabilities,
may therefore show small gaps near thresholds for dates after the change.
Those gaps are a storage-precision artefact, not a disagreement about the
weather, and must be reported as such rather than explained away.

This limitation is published on the site alongside the track record.

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

## 5. Verification method

Draft, 12 November 2026. Items marked **[proposal]** are mine and need your
decision; everything else follows from decisions you have already made.

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
event frequency for that square and that calendar month, taken from our own
sample, unsmoothed.

This is the best constant forecast that group could have had, and it could
only be built after seeing the answers. Our skill against it is therefore a
**conservative lower bound**, and the site says so wherever skill is shown.
A forecast that beats it has beaten a reference it could never have had in
advance.

**[proposal]** The calendar month is the month of the **day being forecast**,
in UTC, not the month of the run date. The climatology describes the weather
of the observed day, so that is the day it should be keyed to. This matters
only for runs within 5 days of a month end.

#### Computing it per square-month before pooling

The reference is worked out **per square and calendar month first**, and only
then pooled:

```
BSS = 1 - (sum of case Brier scores) / (sum of case reference Brier scores)
```

summed over the cases in the group, with each case's reference being its own
square-month frequency.

Pooling squares with different climates before computing the reference
manufactures skill that is not there: a forecast can look skilful merely by
knowing that Cherrapunji is wetter than Jaisalmer, which is geography, not
forecasting. Computing the reference per square-month first removes that
(Hamill and Juras, 2006).

### 5.4 Groups

Results are reported per **region x lead day x threshold**.

**Lead days are never mixed.** A Day 1 forecast and a Day 5 forecast are
different products and pooling them hides the decay that matters most.

#### Regions **[proposal]**

Eight climate-based regions. The rules below are applied **in order to India
squares only, first match wins**, so every India square lands in exactly one
region.

| # | Region | Rule |
|---|---|---|
| 1 | Northeast | `lon >= 89.0` |
| 2 | Himalaya & foothills | `lat >= 29.0` |
| 3 | West coast & Western Ghats | `lat <= 22.0` and `lon <= 76.5` (or `<= 77.25` where `lat < 13.0`) |
| 4 | Dry northwest | `lat >= 22.0` and `lon <= 76.0` |
| 5 | Indo-Gangetic plains | `lat >= 24.0` |
| 6 | East coast | `lat <= 23.0` and `lon >= 79.5` |
| 7 | Peninsula interior | `lat <= 19.0` |
| 8 | Central India | everything else |

The wider longitude cutoff in rule 3 below 13 N is because the peninsula
narrows and the Ghats crest sits further east there.

These boundaries are **straight lines on a grid, not climate science**. They
are a starting point. Before any results are produced:

- the square count per region is printed and reviewed,
- the boundaries are checked by someone who knows Indian climatology,
- and a handful of named places are asserted into the region they belong to,
  as was done for the mask in section 3.5.

A region with too few squares to be meaningful is merged into its neighbour
rather than reported thinly.

### 5.5 Uncertainty

Bootstrap by resampling **whole start dates**, with replacement, 1000 times.
A resample takes all squares and all lead days of a chosen date together.

Reported as the 2.5th and 97.5th percentiles of the resampled statistic, a
95% range.

Whole dates are the unit because squares on the same day are strongly
correlated, and so are lead days from the same run. Resampling individual
cases would treat one weather system as thousands of independent facts and
would make the range far too narrow.

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

**[proposal]** Reliability buckets: `count = 0` on its own, `count = 51` on its
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

---

## 6. Trust labels

Draft, 12 November 2026. Items marked **[proposal]** are mine.

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

### 6.3 Enough data **[proposal]**

All three:

| Requirement | Figure |
|---|---|
| Cases in the group, as defined in 5.1, with a usable observed box-day | at least **1,000** |
| Distinct start dates contributing any case | at least **30** |
| Distinct start dates on which the event was **observed** at least once | at least **20** |

The third is yours and is the one that actually binds. The other two are mine.

The case count is deliberately the weakest of the three. With about 4,613
India squares and 177 dates, even a small region reaches tens of thousands of
cases, so a case minimum is close to free. Cases on the same day are not
independent, so the real guard against a thin sample is the bootstrap
half-width of condition 3, which is computed over dates.

The 20-dates rule is what stops a label resting on one freak week. A region
can have 80,000 cases and still have seen 50 mm of rain on only three days,
and that group must not be called a good track record.

### 6.4 Small honesty error **[proposal]**

Every reliability bucket holding at least **100 cases** has its observed
frequency within **0.10** of its mean forecast.

Buckets below 100 cases are ignored for this test and are **still drawn** on
the diagram with their counts, so a reader can see what was set aside.

0.10 matches the rounding used for display. A "Good track record" label shows
"About 40%", rounded to the nearest 10, so an error up to 0.10 is the largest
error that rounding can still absorb. Allowing more would print a number the
data does not support.

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

**[proposal]** "came true about N times in 10" is the observed frequency of
the reliability bucket this forecast falls into, for this region, lead day and
threshold, rounded to the nearest whole number out of 10. If that bucket holds
fewer than 100 cases the phrase is **omitted** and only the count is shown,
because the same 100-case floor that governs 6.4 governs what we are willing
to say.

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
