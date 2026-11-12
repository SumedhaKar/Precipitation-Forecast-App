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

#### Two things ECMWF changed, on 14 May and 21 October 2026

Both were found on 12 November 2026 by processing 13 May and 25 October and
comparing them, and both changeover dates were then read from the done records
of the whole 177 date archive. Both are **[verified]** from the real files.

| Key | 13 May 2026 | 25 October 2026 |
|---|---|---|
| `bitsPerValue` | 16 | 12 |
| Packing quantum at step 24 | 0.0039 mm | 0.125 mm |
| Coarsest quantum across the 6 steps | 0.0156 mm | 0.250 mm |
| `longitudeOfFirstGridPointInDegrees` | 0.0 | 180.0 |
| `longitudeOfLastGridPointInDegrees` | 359.75 | 179.75 |
| File size, `pf` step 24 | 42 MB | 21.6 MB |
| Raw bytes for the whole date | 301 MB | 153 MB |

**The exact changeover dates [verified].** Read from the `longitude_origin`
and `packing.bitsPerValue` fields of all 177 Pile A done records on 12
November 2026. They are not the same date, and they are five months apart:

| Change | Last date before | **First date with it** | Holds unbroken to |
|---|---|---|---|
| longitude origin 0.0 to **180.0** | 20260513 | **20260514** | 20261105 |
| `bitsPerValue` 16 to **12** | 20261020 | **20261021** | 20261105 |

Two things worth noticing in those numbers. The longitude origin moved on the
**second** date of the archive, so exactly one date in the whole of Pile A,
13 May 2026, carries the old origin — had the archive started a day later
nothing here would ever have seen it, and the code would have been written
against an assumption instead of a measurement. And `packingType` is
`grid_ccsds` on all 177 dates: only the bit depth changed, not the scheme.

The coarsest quantum across the six steps follows the bit depth, and varies
from date to date within each era: 0.0078125, 0.015625 or 0.03125 mm on the
16-bit dates, and 0.125 or 0.25 mm from 20261021 onward. That per-date
variation is why the tolerance of 3.6 is derived from each file's own packing
rather than fixed.

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

**And it comes back.** Three file-level failures drop it to 4; then, once
`RECOVER_AFTER_SECONDS` (900 s, fifteen minutes) have passed with no further
file error, the next file that arrives puts it back to 8 and logs that it
did. The counter resets on each change, so going down again takes three fresh
errors, not one. There is no timer thread: the check happens on the success
path of `download_one`, costs nothing in a run that never dropped, and a run
that never errs is never touched by it.

The drop used to be permanent, and that is what Pile A actually ran under.
Fifteen minutes is chosen against what the real run measured: the errors came
in two bursts of a few minutes each, so a shorter window would flap and a
longer one would have cost most of the run anyway.

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

#### What the real run did, 12 November 2026

The whole of Pile A ran in one day, and is **[verified]** from
`data/logs/pile_a.log`, `data/logs/supervisor.log` and the 177 done records.

| | |
|---|---|
| Dates | **177**, 20260513 to 20261105, every calendar day |
| Failed, finally | **0** |
| Raw downloaded | **50.7 GB**, 2,124 GRIB files |
| Kept | **3.38 GB**, 19.1 MB a date |
| Per date, 16-bit era | 160 dates: min 121 s, **median 304 s**, mean 345 s, max 965 s |
| Per date, 12-bit era | 15 dates: min 226 s, **median 283 s**, mean 288 s, max 343 s |
| First log line to last | 14.09 h |
| Of which frozen | **7.66 h** |
| So actually moving | **6.43 h**, against the 4.6 h estimated above at 3.21 MB/s |

The two eras cost almost the same per date even though a 12-bit date is half
the bytes (156 MB against 300 MB), which says the limit was not bandwidth.

#### The freeze, and why there is a supervisor

At 01:55 the run logged `progress 6/171` and then **nothing at all for 7
hours 40 minutes**. The laptop's Wi-Fi had gone away under it. The sockets
did not error and did not time out: the read timeout of 120 s in
`ecmwf_download.py` only fires when a socket is open and silent, and these
connections were neither open nor refused, so eight threads sat in a kernel
wait and the process stayed alive, idle and completely quiet. At 09:35,
when the network came back, the retries that had been queued all failed at
once: five `ConnectionAbortedError 10053` and three `IncompleteRead`, which
took out seven dates and dropped the limiter to 4 connections at 09:57.

Nothing in the run was wrong. A hung download looks exactly like a slow one
from inside the process, and a process that is waiting cannot notice that it
has stopped making progress. That is a job for something outside it:

| The supervisor, `scripts/supervise.py` | |
|---|---|
| Checks | every 120 s |
| Stall limit | **600 s** with no new done record |
| On a stall | kill the run and relaunch it; dates with a done record are skipped, so it resumes where it stopped |
| Restart limit | 10, so a genuinely broken run cannot spin for ever |
| On an all-network-errors finish | archive the failure records to `data/logs/failures/archived/` and relaunch once more |
| Stops when | every date has a done record, and says so |

It earned its place twice on the day. Pile B finished under it at 11:26
(181/181). Pile A was relaunched by hand at 11:16 after the freeze, ran 146
dates to 15:28:55 with `done=145 failed=1`, and then the supervisor did the
last piece itself:

```
15:29:12  Pile A ended with 1 failure(s), all network errors. Archived 1 record(s) and relaunching once more.
15:29:12  relaunched Pile A as PID 16276
15:33:12  Pile A complete: 177/177 done. Supervisor stopping.
```

That relaunch is the run with `done=1`: it recomputed the full 177 date list,
skipped the 176 that already had a done record, and did the one that was
left, 20260621, in 121 s. 20260621 had failed at 13:43:17 with
`IncompleteRead(965118 bytes read, 100503 more expected)` on `pf` step 120
after 3 retries — a broken connection, nothing about the data. Its raw files
were kept for inspection, as 2.6 requires, then redownloaded cleanly on the
retry. Its failure record is kept at
`data/logs/failures/archived/20260621_20261112T152912.json`, so the one
failure in the archive is still on the record rather than tidied away.

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

The outline decides which grid squares count as India, and the map draws it
(11.14). It is the only national boundary the site draws, it is the India
point-of-view edition, and it is the same geometry the mask was cut with, so
the country on screen and the squares we forecast are the same shape. No
other country's borders are drawn, and no boundary comes from a third-party
basemap.

**Amended 12 November 2026.** This paragraph used to end "The published map
does not draw national borders", which was true of the plain G2 page and
stopped being true when the map was built. The reason the sentence existed —
that this project does not take a boundary from somewhere else and does not
draw borders it has not checked — is the reason 11.14 refuses a basemap.

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
was not touched until Pile A finished later the same day; see "Where the
numbers live" below.

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

The IMERG constants (0.1 degree, 3600 by 1800, the fill value, 48, 0.90)
were in `pipeline/nasa_process.py` while Pile A was running, because Pile A
imports `config.py` and a running download must not have the module under it
edited. **Pile A finished on 12 November 2026, and they moved to
`config.py`** the same day, with an `IMERG_` prefix:

| In `config.py` | Value |
|---|---|
| `IMERG_PIXEL` | 0.1 degrees |
| `IMERG_N_PIX_LON`, `IMERG_N_PIX_LAT` | 3600, 1800 |
| `IMERG_FILL_VALUE`, `IMERG_FILL_TOLERANCE` | -9999.9, 0.01 |
| `IMERG_COMPLETE_CNT` | 48 |
| `IMERG_MIN_COMPLETE_FRACTION`, `IMERG_FRACTION_EPSILON` | 0.90, 1e-12 |
| `IMERG_COORD_TOLERANCE`, `IMERG_AREA_TOLERANCE` | 1e-4, 1e-9 |
| `IMERG_REQUIRED_FILE_VERSION`, `IMERG_REQUIRED_DOI` | `V07C`, `10.5067/GPM/IMERGDL/DAY/07` |
| `IMERG_TITLE_MUST_CONTAIN`, `IMERG_EXPECT_UNITS` | `("Late", "1 day", "0.1 degree")`, `mm/day` |
| `N_LEAD_DAYS` | `N_DAYS`, which is 5 |

`nasa_process.py` keeps the short names as **aliases** of those
(`PIXEL = cfg.IMERG_PIXEL`, and so on). The value exists in one place; the
name stays where the callers already look for it. That is deliberate: the
hand checks in `handchecks/` import `FILL_VALUE`, `COMPLETE_CNT` and
`MIN_COMPLETE_FRACTION` from this module, and those files are evidence of
what was checked and when. Rewriting evidence to prove that a constant had
moved would be the wrong trade.

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
| `manifest.json` | 10,588, 57 files with a sha256 each | **60 s** | the only blob that is ever rewritten: which `run_id` is current, the list of that run's files with a sha256 each, the day labels, the thresholds, the dot category names, and the last retention result |
| `published/<run_id>.json` | 549 | 2,592,000 s | the marker of 8.5, written last. Immutable, and the pathname carries the run id, which is what run selection reads (8.6) |
| `runs/<run_id>/manifest.json` | 10,588 | 2,592,000 s | byte for byte the same as `manifest.json`, on a pathname that is never overwritten, so the current manifest's bytes can be read back and hashed (8.10) |
| `runs/<run_id>/run.json` | about 3 KB | 2,592,000 s | the run's section 4.6 manifest: every check result, the download summary, the India maxima |
| `runs/<run_id>/grid.json` | about 3 KB | 2,592,000 s | the 129 latitudes, the 121 longitudes, the array order, the thresholds, the dot categories, the tile rule |
| `runs/<run_id>/days.json` | 1,571 | 2,592,000 s | per lead day: steps, the window in UTC and IST, the label |
| `runs/<run_id>/india.u8` | 15,609 | 2,592,000 s | 1 for an India square, 0 otherwise |
| `runs/<run_id>/counts/ge1mm_day1.u8` ... `ge50mm_day5.u8` | 15,609 each, 15 files | 2,592,000 s | the count out of 51, one byte a square |
| `runs/<run_id>/tiles/<lat>_<lon>.json` | 3,202,461 over 38 files | 2,592,000 s | per-square counts, dots and all 51 member totals |

**59 blobs and 3,474,829 bytes a run** — the 57 run files, the immutable copy
of the manifest and the marker — plus the one shared `manifest.json`, so the
eight runs of 8.7 are **27.8 MB and 473 blobs**. One publish writes 60 blobs
and 3,485,479 bytes, the manifest twice.

The manifest lists the 57 run files and not the two extras. The copy cannot
list itself, and the marker is written after the manifest exists; the marker
carries the manifest's `sha256` and `ETag` instead, which is what ties the
three together.

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

### 8.5 The order of writing, the manifest, and the marker last

| # | Write | What it means |
|---|---|---|
| 1 | the 57 run files, in any order | nothing refers to anything else, and the store still describes the **previous** run throughout |
| 2 | `runs/<run_id>/manifest.json` | the bytes that are about to become current, on a pathname that will never be overwritten |
| 3 | `manifest.json` | **the site now shows this run.** One small write, the only mutable blob in the store |
| 4 | retention, then the read-back of 8.10 | — |
| 5 | `published/<run_id>.json` | **the publisher now says this run is published.** The last write of all |

Until the manifest is rewritten, the store still describes the previous run
and the site still shows it, however many of the new run's files are already
uploaded. The manifest moving is the one moment the published forecast
changes. This is the same rule as on disk in section 4.6, for the same
reason.

#### Why there is a marker at all

`manifest.json` is rewritten every publish, so it is the one blob a CDN can
be wrong about, and Vercel's own documentation says an overwrite "may take up
to 60 seconds to propagate through our cache". A marker is the opposite kind
of object: **one immutable blob a run, whose pathname carries the run id**.
That has three consequences, and they are the whole reason for it:

- run selection can read what is published from `list` alone, with no fetch
  and therefore no cache (8.6),
- it cannot be stale, because nothing is ever written to that pathname twice,
- its presence means a publish **finished**. It is written after the manifest
  and after the read-back, so a publish that died halfway leaves no marker
  and is retried by the next run rather than remembered as done. Retrying
  writes the same bytes to the same pathnames, which is safe.

Vercel's own advice, in the same documentation, is to "treat blobs as
immutable" and give anything mutable a short cache age. The manifest stays
because the site needs one address that always names the current run; the
marker is how the publisher stops depending on it.

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
| 1 | `list` the store under `published/` and take the **newest marker's run id** | **yes** |
| 2 | `run_live --published <that run id>`, so the section 4.6 rules apply unchanged | no |
| 3 | if a run was built, publish it; if not, exit 0 and leave the store alone | **yes** |

Step 1 reads pathnames and nothing else. `published/20261112T00Z.json` says
which run is published in its own name, run ids sort chronologically as text,
so the newest marker is `max()` of the list — **no body is fetched, and no
JSON is parsed.** `list` is an API call, answered by the store and not by the
CDN, so there is nothing in this path a cache can be wrong about.

The store is reached through the SDK's `list` rather than a hostname written
into the repository. The store id is not a secret, it appears in every public
URL, but hard-coding it would mean editing the repository if the store were
ever recreated. With `list`, the token is the only thing that has to exist,
which is why step 1 needs it as much as step 3 does. Step 2 needs no
credential of any kind (section 4.6).

#### Why not the manifest, which is what this section used to say

This section originally had step 1 fetch `manifest.json` from its public URL
with a cache-busting query, "so the CDN cannot hand back the manifest from
before the last publish". **Measured on the real store on 12 November 2026,
that does not work:**

| Request | Answer |
|---|---|
| `GET manifest.json` | `200`, `Cache-Control: public, max-age=60`, `Age: 582`, `X-Vercel-Cache: HIT` |
| `GET manifest.json?cb=<nonce>` | `200`, `Age: 583`, `X-Vercel-Cache: HIT`, the **same** `ETag` |
| `GET` with `Cache-Control: no-cache` | `Age: 606`, still `HIT` |
| `GET` with `Pragma: no-cache` | `Age: 606`, still `HIT` |

The query string is not part of the cache key, so the nonce changes nothing,
and no request header a client can send forces a fresh copy. Vercel's
documentation does recommend "add a unique query parameter to the blob URL",
but reading it again: that paragraph is about **browsers** continuing to
serve their own cached version, not about their CDN. The claim in this
section was wrong, and the code that implemented it has been removed rather
than left in place looking like a safeguard.

What is left is a rule: **nothing that decides anything is read from a public
URL.** `list` decides what is published; a public `fetch` is used only to
check bytes on pathnames that are never overwritten (8.10).

#### A store published before markers existed

Run `20261112T00Z` was published on 12 November 2026 by the code this section
describes, before markers existed, so the real store holds a manifest and no
marker. That state is handled explicitly and once:

| What `list` finds | Treated as |
|---|---|
| one or more markers | the newest marker's run id. No fetch |
| no marker, but `manifest.json` exists | the manifest is fetched, **once**, and its `run_id` is taken. The next publish writes the marker that run never had: `published/<run_id>.json` with `adopted_from: manifest.json`, the sha256 of the body that was read, and a note saying so |
| no marker and no manifest | an empty store, before the first publish |

Adoption is an **addition and nothing else**. It writes one new blob, it
overwrites nothing, it deletes nothing, and the run it names is not
republished: the selection rules below still see `20261112T00Z` as published
and still refuse to publish it again. After that one write the store is
consistent and the manifest body is never read again.

A pathname under `published/` that is not a valid `<run_id>.json` is logged
and left alone, by the same rule as 8.7's stray prefixes.

#### An empty store and a broken store are not the same thing

| What happened | Treated as | Exit |
|---|---|---|
| `list` succeeded and found no marker and no `manifest.json` | an empty store, before the first publish. `published` is `None`, the newest complete run is built and published | 0 |
| `list` failed: no token, wrong token, store gone, suspended, rate limited, network error | **a failure** | **1** |
| `list` found a marker | the published run id, from its pathname. Nothing else can fail here | 0 |
| `list` found no marker, and the manifest's URL could not be fetched, or did not return 200 | **a failure** | **1** |
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
| 6 | A dropped run loses its `published/<run_id>.json` marker with the rest of it, in the same delete. Markers for runs that no longer exist would otherwise accumulate for ever, and the newest-marker rule of 8.6 would start naming a run whose files are gone |
| 7 | The marker of the run being published does not exist when the plan is made, so retention cannot name it at all, let alone delete it |

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

**The schedule was held back and is now live.** It was commented out on 12
November 2026 and restored the same day, once the first publish and HC7 had
both passed.

The reason was not the cron itself but what a cron does before anyone has
watched the job work. A schedule becomes live the moment the file is on
`main`, and until the secret of 8.9 existed every attempt would have failed
at step 6 with a missing token: one runner minute, nothing downloaded,
nothing published. That failure is correct, and the alternative of skipping
quietly when the secret is absent would make a store that had stopped
answering look the same as a store nobody had set up yet. What it is not is
**informative**, and a job that goes red every day at the same time is how a
real failure comes to be ignored. So the schedule waited until there was a
successful publish to compare a failure against, which 20261112T00Z now is.

| Setting | Value | Why |
|---|---|---|
| Triggers | `schedule` and `workflow_dispatch` | the cron is the normal path; the dispatch is for the first publish, after a failure, and for a run ECMWF published late |
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
| Where it lives | **one place: a GitHub Actions secret named `BLOB_READ_WRITE_TOKEN`.** Nowhere else |
| Why Vercel does not need it | the site and `api/` read **public URLs only** (section 11.4), and a public URL needs no credential. So the Blob store is deliberately **not connected to the Vercel project**: connecting it would add `BLOB_STORE_ID` and a rotating `VERCEL_OIDC_TOKEN` to every deployment, which is write access the website has no use for. The only writer is Actions |
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
`list` under `published/` and prints the newest marker's `run_id` for the
workflow to pass to `run_live`. It prints an empty line and exits 0 **only**
when `list` itself succeeded and found neither a marker nor a manifest.
Everything else in that path, listed in 8.6, exits 1 and prints why.

#### Reading it back

Two different questions, answered two different ways, because one of them
cannot be answered from a public URL at all.

| What | How | A difference means |
|---|---|---|
| the 57 run files and the immutable copy of the manifest | fetched from their **public URLs with no token**, sha256 compared against the bytes that were sent | **failure.** These pathnames are written once and never overwritten, so no cache can be holding an older version: a wrong byte is wrong |
| `manifest.json` | the `ETag` that `put` returned, compared with the `ETag` that `list` returns afterwards | **failure.** Both come from the API, neither from the CDN, so disagreement means something else overwrote the manifest between the two calls |

The read-back costs 3.47 MB of download a run.

**The mutable manifest is never judged by its bytes.** Its public body is
fetched as well, and if it differs the publish **logs** that the edge is
still serving the previous manifest and carries on, because Vercel documents
up to 60 seconds for an overwrite to propagate and the ETags have already
confirmed the write. Failing there would mean failing a publish that was
entirely correct, every time a run was published within a minute of a read.
The manifest's bytes are still checked to the last byte — through
`runs/<run_id>/manifest.json`, which holds the same bytes on a pathname that
has never been served before (8.5).

A store that returns no `ETag` at all is a failure: there would then be
nothing left to confirm the write with except a cached body.

`@vercel/blob` 2.9.0 declares `etag: string`, required, on both
`PutBlobResult` and `ListBlobResultBlob`, and the compiled SDK copies both
straight out of the API response, so the two are in the same format by
construction. The comparison **normalises anyway**: surrounding quotes and a
`W/` weak prefix are stripped from each side first, because the same value
appears quoted in an HTTP `ETag` header and a daily publish should not go red
over a pair of quotation marks.

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

**In `config.py`, since 12 November 2026.** They were in
`pipeline/publish.py` while Pile A was running, for the reason given in 3.7,
and moved to `config.py` the same day Pile A finished. `publish.py` keeps the
short names as aliases, so the tests and the module itself are unchanged.

| In `config.py` | Alias in `publish.py` | Value |
|---|---|---|
| `KEEP_RUNS` | `KEEP_RUNS` | 8 |
| `MANIFEST_MAX_AGE` | `MANIFEST_MAX_AGE` | 60 s |
| `RUN_FILE_MAX_AGE` | `RUN_FILE_MAX_AGE` | 2,592,000 s |
| `TILE_DEGREES` | `TILE_DEGREES` | 4.0 |
| `NOT_INDIA` | `NOT_INDIA` | 255 |
| `MEMBER_STEP` | `MEMBER_STEP` | 0.0625 mm |
| `MEMBER_MAX_CODE` | `MEMBER_MAX_CODE` | 65,535 |
| `STEPS_PER_MM` | `STEPS_PER_MM` | 16 |
| `MANIFEST_NAME` | `MANIFEST` | `manifest.json` |
| `MARKERS_PREFIX` | `MARKERS` | `published/` |
| `RUNS_PREFIX` | `RUNS` | `runs/` |
| `PUBLISH_DIR` | `PUBLISH` | `data/publish` |

`NODE_SCRIPT` stays in `publish.py`: it is the path of the uploader that
module runs, and nothing else has any business with it.

### 8.13 Tests

`tests/test_publish.py`, all against `FakeStore`, no network and no token.

| Test | Covers |
|---|---|
| every file the manifest names was written before the manifest, and the immutable copy holds the same bytes | 8.5 |
| the **marker is the very last write of all**, after the manifest and after the read-back, and carries the manifest's sha256 and ETag | 8.5 |
| an older local run never replaces a newer published one, and nothing at all is written | 8.6 |
| the same run is never republished, and nothing at all is written | 8.6 |
| a local run with no manifest, or already marked published, is not published | 8.1 |
| the published run comes from the marker **with no fetch at all** | 8.6 |
| the newest marker wins when there are several | 8.6 |
| **a stale public manifest cannot change the published run**: the edge serves yesterday's `run_id`, the marker still decides, and today's run is not republished | 8.6 |
| a `list` that succeeds and finds no marker and no manifest publishes the first run | 8.6 |
| a `list` that fails exits 1, publishes nothing, and is never read as an empty store | 8.6 |
| a manifest whose fetch returns 404 or 500 exits 1, on the legacy path | 8.6 |
| a manifest that is not JSON, has no `run_id`, or has a `run_id` that is not a valid run id, exits 1 | 8.6 |
| a stray file under `published/` is left alone and does not break selection | 8.6 |
| a store with a manifest and no marker is **adopted**: one new blob, nothing overwritten, nothing deleted, the run not republished, and the manifest body never read again afterwards | 8.6 |
| adoption does not stop a newer run being published, and the adopted run's files survive | 8.6 |
| **a stale edge does not fail a correct publish**: the public manifest is still the previous one, the ETags agree, the publish succeeds and the marker is written | 8.10 |
| a manifest whose stored ETag no longer matches the one `put` returned is a failure | 8.10 |
| a store that returns no ETag for the manifest is a failure | 8.10 |
| the read-back refuses to byte-verify `manifest.json` at all | 8.10 |
| the read-back notices a single changed byte on an immutable pathname | 8.10 |
| retention deletes a dropped run's marker with the rest of it | 8.7 |
| retention never deletes the current run's marker | 8.7 |
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
`handchecks/hc7_published.py` fetches the published tiles and the published
counts bytes for two squares from their public URLs, and compares them against
those squares' numbers in `data/live/<run_id>/squares.npz`, with the index
arithmetic written out longhand. Saved to
`handchecks/results/hc7_published.csv`.

Two squares and not one, because a check that only ever reads a 51 would not
notice a 0 being served as a 255: the wettest India square of lead day 1, and
one square that is dry in all 51 members. For each of them all 15 counts
bytes, both tile records in full, the India mask byte, and the 51 member
integers of each of the 5 days, against `floor(mm * 16)` worked out here and
not in `pipeline/publish.py`. The bytes the CDN served are also hashed
against the manifest's own `sha256` record of them.

**Run 20261112T00Z, 12 November 2026: 170 comparisons, 0 different.** The
store was built by Actions from its own download and the local file by this
laptop a few hours earlier, so this is two independent builds of one run
agreeing to the byte, not a file compared with itself. The check was shown to
bite: a copy with one member integer raised by 1 fails 10 of the 170.

### 8.14 Settled, and what is still open

Four of the five questions in the first draft of this section were decided on
review, 12 November 2026:

| Question | Decision |
|---|---|
| each member's millimetre value in the place panel | **published now**, as integers in the tiles (8.4), displayed as whole millimetres |
| whether `api/place` is built at all | **built**, in section 11, with `tests/test_api_consistency.py` holding it to the published tiles (8.11) |
| a Python-only publisher | **not taken.** `@vercel/blob` 2.9.0 in Node stays, with the decision rules and the tests in Python (8.10) |
| `robots.txt` in the store | **no action.** Nothing on the site links to a store URL as a page, and a crawler reading a count file costs a few kilobytes |

The fifth was settled by the first publish itself, 12 November 2026:

| Question | Decision |
|---|---|
| the store name and its id | the store id is `zshhfucqsimhyy61`, so the manifest is at `https://zshhfucqsimhyy61.public.blob.vercel-storage.com/manifest.json`. Nothing in `pipeline/` depends on it: the publisher still finds the manifest with `list` (8.6). It is a read-only public address and not a credential, so the publish step logs it, and HC7 and the site in section 11 are given it |

Nothing in section 8 is open.

#### G2 as it went live, 12 November 2026

| Checked against the published store | Result |
|---|---|
| `/api/health` | `20261112T00Z`, 4,613 India squares, 51 members, the five labels, `stale: false` at 10.6 hours |
| `/api/place` for Delhi, Mumbai and the HC6 wettest square | every count, every dot and all 51 member values of all five days identical to the squares' own records in `tiles/28N_76E.json`, `tiles/16N_72E.json` and `tiles/32N_72E.json`. **0 mismatches** |
| Mumbai | moved from 19.00 N 73.00 E to 19.25 N 73.00 E, one square, and said so |
| 10 N 70 E, the Arabian Sea | 404, "outside the forecast area" |
| the page | the live JavaScript bundle is **byte for byte** the local build, 228,423 bytes, and holds no store URL |
| the function region | `X-Vercel-Id: bom1::...`, which is Mumbai |

## 11. Display rules, the website pages and the `api/` functions

This section is drafted in two parts. **This draft is part one, G2 only:** a
plain page, live on Vercel, showing one square's counts honestly. The map is
G3 and extends this section rather than replacing it; nothing here is written
in a way the map would have to undo.

G2 is finished when the page is reachable on its Vercel URL, shows the run id
and the five day labels from the published manifest, lets someone pick a
place and see the three counts out of 51 and the 51 member values for each of
the five days, and carries the three sentences of 11.9 and the credits. The
target is **7 pm IST on 12 November 2026**.

| In G2 | Out of G2, and where it goes |
|---|---|
| the published run id, its model run time in IST, and when it was published | — |
| the five lead-day labels | — |
| a short city list plus a latitude and longitude box | the map, G3 |
| the three counts out of 51 a day for one square | — |
| the 51 member values as whole millimetres, rounded down | — |
| a stale banner when the run is older than 36 hours | — |
| "model-run counts, not probabilities", "0 mm means under 1 mm", "not an official warning" | — |
| credits and licences | `CREDITS.md`, written in the same step (2.1) |
| `api/health` and `api/place` | — |
| a map of India coloured by count | G3, reading the counts files of 8.4 |
| the track record, report card and reliability diagrams | sections 5, 6 and 12 |
| any percentage | section 6: only with a "Good track record" label |

### 11.1 What was measured before deciding anything

Every row was run from this laptop against the real store on 12 November
2026, after the first publish, with no token. The commands were plain `curl`
against the public URLs of run `20261112T00Z`.

| Measured | Result | What it decides |
|---|---|---|
| `Access-Control-Allow-Origin` on `manifest.json`, a tile and a counts file | `*` on all three, with `Access-Control-Allow-Headers: content-type` | a browser **may** read the store directly. No rewrite and no proxy is needed for that |
| `OPTIONS` preflight on a tile | **405 Method Not Allowed**, though it does carry `Access-Control-Allow-Origin: *` | any request that **triggers** a preflight fails. So no custom request headers, no `Range`, no credentials from the page |
| `Cache-Control` as served | `public, max-age=60` on the manifest, `public, max-age=2592000` on run files | the publisher's two cache ages of 8.4 arrive intact |
| brotli | the 102,791 byte tile is 31,974 bytes on the wire with `Content-Encoding: br` | a tile is affordable to a server, still heavy for a phone on a slow link |
| `Range: bytes=1837-1837` on `ge10mm_day1.u8` | **206**, `Content-Range: bytes 1837-1837/15609`, byte value **40** | ranges work server side, and 40 is the same number HC7 and `squares.npz` give for 34.25 N 73.5 E. Combined with the 405 above: the map may **not** read single bytes from a browser, it fetches whole counts files |
| `Age` on the manifest | `Age: 583` with `max-age=60`, `X-Vercel-Cache: HIT` | the CDN serves the manifest well past its freshness lifetime |
| `manifest.json?cb=<nonce>` | same `Age`, same `X-Vercel-Cache: HIT`, same `ETag` | **the query string is not part of the cache key.** Cache busting by query string does not work on this store |
| `Cache-Control: no-cache` and `Pragma: no-cache` as request headers | same `Age`, still `HIT` | nothing a client can send forces a fresh copy |
| `If-None-Match` with the current ETag | **304 Not Modified** | the page can poll the manifest cheaply |

Two of these are uncomfortable and are written down rather than smoothed
over.

**The cache-busting that used to be in 8.6 and 8.10 did not do what it
said**, and this is how it was found. Those paragraphs claimed that
`?cb=<nonce>` stopped the CDN serving a stale run id. Measured, the query
string is ignored for caching and no request header changes that, so a
manifest read could be minutes old; and the read-back had a sharper version
of the same problem, because the **second** publish overwrites
`manifest.json` and would then have compared a stale body against the bytes
just sent, failing the job after a correct publish.

**Fixed on 12 November 2026, before any of this section was built.** What is
published is now decided from `list` and an immutable `published/<run_id>`
marker, and the manifest is confirmed by its `ETag`: 8.5, 8.6 and 8.10. The
consequence for this section is that **the page cannot force a fresh read
either**, so `api/health` may report a run id up to about a minute behind a
publish that is happening while someone is reading. Nobody can perceive that
in a daily forecast, and the 36 hour staleness rule of 11.8 is unaffected.

**A browser cannot ask for one byte.** The `Range` header is not on the CORS
safe list, so a ranged `fetch` preflights, and the preflight answers 405.
G3's map therefore fetches whole 15,609 byte counts files, which is what the
one-month immutable cache of 8.4 was for.

### 11.2 One Vercel project, `api/` at the root, `web/` in a subfolder

The trap in the question is real. Setting the project's **Root Directory** to
`web` makes Vercel treat `web/` as the whole project: it would find
`web/package.json`, build the site, and never see `api/`, because `api/` is
above the root. Vercel's rule is "create an `api` directory at the **root of
your project directory**", where root means the Root Directory setting, not
the repository.

So **Root Directory stays at the repository root** and `vercel.json` does the
rest:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "cd web && npm ci",
  "buildCommand": "cd web && npm run build",
  "outputDirectory": "web/dist",
  "regions": ["bom1"],
  "functions": {
    "api/*.mjs": {
      "maxDuration": 10,
      "includeFiles": "config/store.json",
      "excludeFiles": "{data/**,handchecks/**,results/**,tests/**,pipeline/**,scripts/**,web/**,.github/**,.venv/**,*.md}"
    }
  }
}
```

`includeFiles` names `config/store.json` explicitly: it is the one file
outside `api/` that a function reads, and it is read rather than imported, so
nothing would trace it into the bundle on its own. The functions also look
for it relative to the working directory as a second try, so a bundle that
flattens the layout still finds it (11.5).

The site is built with **Vite 8.3.8, React 19.3.1 and @vitejs/plugin-react
6.3.0**, pinned exactly in `web/package.json` with a `package-lock.json`
beside it. `npm ci` and `npm run build` were both run on this laptop before
the first deploy: 17 modules, `dist/index.html` 0.72 KB, one 2.85 KB
stylesheet and one 228 KB script, 72 KB of it over the wire gzipped.

| Key | Value | Why |
|---|---|---|
| `framework` | `null` | `null` is documented as the way to select the "Other" preset. There is no framework at the repository root, and the site inside `web/` is built by our own command |
| `installCommand` | `cd web && npm ci` | there is no `package.json` at the repository root, so the default install has nothing to do. `npm ci` and not `npm install`, so the deploy uses `web/package-lock.json` exactly, the same rule as `scripts/publish` in 8.10 |
| `buildCommand` | `cd web && npm run build` | Vite writes `web/dist` |
| `outputDirectory` | `web/dist` | overrides the default of the root directory, which would otherwise publish `SPEC.md` and the pipeline as a static site |
| `regions` | `["bom1"]` | the store answers from `bom1` (`X-Vercel-Id: bom1::…` in every response measured in 11.1) and the readers are in India. The documented default is `iad1`, which would put Washington between the page and a Mumbai store on every request. Hobby plans may select any single region |
| `functions` key glob | `api/*.mjs` | one level, which is all of `api/` |
| `maxDuration` | `10` | a function that fetches a manifest and a tile and gives up. The default is longer; a request that cannot finish in ten seconds is a request to fail |
| `memory` | **absent on purpose** | Fluid compute has been on by default for new projects since 23 April 2025, and with Fluid on, `memory` in `vercel.json` is documented as not settable. It belongs in the dashboard |
| `excludeFiles` | the pipeline, tests, data and the site | Vercel bundles "all files reachable at build time" for a function unless told otherwise. `api/` needs nothing but itself and `config/store.json` |

Checked on 12 November 2026 against `vercel.com/docs/project-configuration/vercel-json`,
`/docs/functions/runtimes/node-js`, `/docs/functions/runtimes/node-js/node-js-versions`
and `/docs/functions/configuring-functions/region`.

The site is a Vite and React app from the start, not a hand-written HTML
file. The fixed structure already says `web/` is React, Vite and MapLibre,
and G3 needs exactly that; a static page now would be thrown away in a day.
G2 simply has no map in it.

### 11.3 The runtime for `api/`: Node, with no dependencies

The question was how to keep the functions from installing the pipeline's
requirements. The answer is to use a runtime that never looks at them.

Vercel's Python runtime takes its dependencies from `pyproject.toml`,
`requirements.txt` or a `Pipfile` **at the project root**. The
`/api`-directory page for Python says nothing about a per-directory
requirements file and points back to that same reference. Our root
`requirements.txt` is the pipeline's:

| Package | What it drags in |
|---|---|
| `eccodes==2.50.1` | the ecCodes C library |
| `netCDF4`, `h5py` | HDF5 |
| `earthaccess` | NASA authentication, and a login this laptop does by netrc |
| `shapely`, `pyshp`, `numpy` | geometry and arrays for the mask |
| `ecmwf-opendata` | the downloader |

None of it is needed to read two JSON files over HTTPS, all of it would be
installed on every deploy, and a function that carries an ecCodes build to
answer `/api/health` is a function that will one day fail to build for a
reason that has nothing to do with the website.

So the functions are **Node, `.mjs`, with no dependencies at all**:

| Decision | Value | Why |
|---|---|---|
| Files | `api/health.mjs`, `api/place.mjs` | the fixed structure names `health` and `place`. `.mjs` because Vercel compiles ES module syntax in `.js` to CommonJS unless the nearest `package.json` says `"type": "module"`, and there is no `package.json` at the root |
| Signature | `export default { fetch(request) { … } }` | the Web standard export. It takes a `Request` and returns a `Response`, which means **plain `node` can import the file and call it**, with no Vercel runtime and no emulator. That is what makes `tests/test_api_consistency.py` possible offline (11.8) |
| Dependencies | none | `fetch`, `URL` and `Response` are global in Node 18 and later. No `package.json`, no lockfile, no install step, nothing to keep pinned |
| Node version | **26.x**, the default Vercel chose | 26.x is the current default, with 24.x and 22.x available. The functions use only built-ins — `fetch`, `URL`, `Response` and `node:fs` — so any of the three works, and the default is one fewer setting to remember. It is deliberately **not** matched to the publisher's Node 24.22.3 (8.2): nothing is shared between them but JSON over HTTPS |
| Two functions, not one | kept | Vercel's own advice is to put related routes in one function so Fluid can reuse instances. The fixed structure names two, and `health` answering while `place` is broken is the whole point of a health endpoint. Two functions of about fifty lines each is not the case that advice is about |

### 11.4 How the page gets its numbers

The store's CORS is open, so the page *could* fetch the manifest and the
tiles itself. For G2 it does not.

| | Decision |
|---|---|
| The page talks to | `api/health` and `api/place` on its own origin, and nothing else |
| The functions talk to | the store's public URLs, with no token |
| G3's map will talk to | the store directly, fetching whole counts files, which is what 11.1 measured the CORS and the one-month cache for |

Four reasons, in order of weight:

1. **The page is tested.** `tests/test_api_consistency.py` can drive
   `api/place.mjs` in plain Node against a local copy of a published run and
   check it square by square against the tile. If the page read the store
   itself, the arithmetic that turns a latitude into a byte would live in
   the browser where that test cannot reach it.
2. **Size.** A square's answer is about 2 KB. The tile holding it is 102 KB,
   31 KB compressed, and the manifest is 10.6 KB because it lists the
   `sha256` of all 58 files. The page should not download a hundred
   kilobytes to show one place.
3. **One place does the arithmetic.** The snapping and the tile naming of
   11.7 exist once, server side, not once per client.
4. **No CORS dependence.** Same-origin requests cannot be broken by a change
   to someone else's response headers.

### 11.5 Where the store's public base URL comes from

It is not a secret: it is a read-only public address, now recorded in 8.14.
It is also not a constant of the code, because a store can be recreated.

| Reader | Source | Fallback |
|---|---|---|
| `api/health.mjs`, `api/place.mjs` | `process.env.STORE_BASE_URL` if set, else `base_url` from `config/store.json` | none; a function with neither answers 500 and says which |
| `tests/test_api_consistency.py` | sets `STORE_BASE_URL` to its own local HTTP server | — |
| the page | `store.base_url` in the `api/health` response, at runtime. **Amended 12 November 2026** for the map (11.23): it was "nothing, it never learns the URL", which was true while the page read only `api/`. The point of the rule was that the store URL is not baked into the built site, and that still holds — the page is given it by its own origin, from this same file | — |
| `pipeline/publish.py` | still nothing: it finds the manifest with `list` (8.6), as before | — |

`config/store.json` is committed, holds `{"base_url": …, "manifest":
"manifest.json"}` and no credential, and is the single source of truth. A
change of store is then a commit, which is the right weight for a change of
data source. The environment variable exists so a preview deployment can be
pointed at a different store without a commit, and so the test can point at
`127.0.0.1`.

`.env.example` gains `STORE_BASE_URL=` alongside the empty
`BLOB_READ_WRITE_TOKEN=` line of 8.9. Neither carries a value.

**Vercel is given no store credential at all.** A public URL needs none, so
the Blob store is deliberately **not connected** to the Vercel project: a
connection would put `BLOB_STORE_ID` and a rotating `VERCEL_OIDC_TOKEN` into
every deployment and give the website write access to the store it only ever
reads. The only writer is GitHub Actions (8.9).

**This adds `config/store.json` to the fixed structure**, which needs your
approval under rule 5. Nothing else in the structure changes: `vercel.json`,
`api/health`, `api/place`, `web/` and `tests/test_api_consistency` are all
already there.

### 11.6 `api/health`

`GET /api/health`, no parameters.

| Field | From |
|---|---|
| `ok` | true when the manifest was fetched and parsed |
| `run_id`, `run_time_utc`, `run_time_ist`, `publish_time_ist` | the manifest |
| `age_hours` | now minus `run_time_utc`, one decimal |
| `stale` | `age_hours > 36` (11.8) |
| `days` | the five `lead_day` and `label` pairs only |
| `india_squares`, `thresholds_mm`, `members` | the manifest |
| `store` | `"reachable"`, or the failure in words |
| `checked_at_ist` | the function's own clock |

| Case | Status |
|---|---|
| manifest fetched and parsed | **200**, `ok: true` |
| manifest old | **200**, `ok: true`, `stale: true`. Old data is not a broken service, and a monitor that goes red for staleness cannot be trusted to mean anything else |
| store unreachable, or the body is not a manifest | **503**, `ok: false`, with the reason |
| no base URL configured | **500**, saying which of the two sources were empty |

Response header `Cache-Control: public, max-age=60`, matching the manifest's
own age. The function never sends `no-store`: a health endpoint that cannot
be cached is a health endpoint that can be used to hammer the store.

### 11.7 `api/place`

`GET /api/place?lat=<degrees north>&lon=<degrees east>`

| Step | Rule |
|---|---|
| 1. Validate | both present, finite, `6 <= lat <= 38` and `68 <= lon <= 98`, the India box of 1.4. Anything else is **400** with the box in the message |
| 2. Snap | `i = round((38 - lat) / 0.25)`, `j = round((lon - 68) / 0.25)`, then the square's own centre is reported back as `square.lat` and `square.lon`. The request's own numbers are echoed as `asked` |
| 3. Tile | `floor(lat / 4) * 4`, `floor(lon / 4) * 4`, named after the south-west corner, as 8.4 |
| 4. Fetch | the manifest, then `paths.tiles/<tile>.json` of that run |
| 5. Find | the record whose `lat` and `lon` match the snapped square |
| 6. Answer | counts, dots and member integers as published, plus the whole millimetres |

The response, per day: `lead_day`, `label`, `from_ist`, `to_ist`, `counts`
as `{ge1, ge10, ge50}` out of 51, `dots` as the four category counts, and
`members_mm`, the 51 member values as whole millimetres **rounded down**,
which is `code // 16` of 8.4 and nothing else. The run block is the same
fields `api/health` returns, so the page can render everything from one
request. `square` carries `lat`, `lon`, `i`, `j` and `tile`, so a reader can
check the arithmetic by hand the way HC7 does.

| Case | Status |
|---|---|
| a square inside the India mask | **200** |
| outside the box, or unparseable | **400** |
| inside the box, but not in the India mask, and an India square lies **within one square** of it | **200**, for that neighbour, with `moved` naming both squares. The same rule as the city list: the nearest India square, one square at most |
| inside the box, not in the India mask, and no India square within one square | **404**, "outside the forecast area", with `nearest_in_tile` if the tile holds anything at all |
| store unreachable | **503** |

#### A typed latitude and longitude snaps by the same rule as a city

A city in the list of 11.8 whose own square is sea is shown at the nearest
India square, and three of the twenty are. A typed latitude and longitude
gets exactly the same treatment, because there is no honest reason for
Mumbai to work from the list and fail from the box:

| Step | Rule |
|---|---|
| 1 | snap to the nearest 0.25 degree square |
| 2 | if that square is in the India mask, use it |
| 3 | otherwise look one square out, the eight neighbours, and take the nearest India square among them, ties broken north first then west |
| 4 | if none of the nine is in India, answer **"outside the forecast area"** and stop. No second ring, no searching across a tile boundary |

Whenever the square used is not the square asked for, **the page says so**:
"19.08 N 72.88 E is sea on this 0.25 degree grid. Showing 19.25 N 73.00 E,
one square north." The square actually used is always on the page anyway
(11.8), so the move is visible rather than silent.

One square is 0.25 degrees, about 28 km north to south. Moving a forecast
further than that without saying so would be a different place; stopping at
one square and naming it is the honest version of being helpful.

`Cache-Control: public, max-age=60`. One square's answer is small and
identical for every reader, so the edge may keep it for a minute; a new run
appears a minute later than it might have, which nobody can perceive in a
daily forecast.

Nothing in the answer is computed from a member value except the whole
millimetre. The counts and the dots are the published ones (8.4), so the
page cannot disagree with the store even if someone later changes how
members are rounded.

### 11.8 The G2 page

In order down the page:

| Part | Content |
|---|---|
| Title | the project name, and one line saying what it is: 51 model runs, India, five days |
| Stale banner | only when `stale`: "This forecast is from <age> hours ago. A newer model run has not been published." in a colour, above everything |
| Run line | "Model run **12 Nov 2026, 5:30 am IST** (00 UTC). Published 2:39 pm IST." and the run id in small type |
| Day labels | the five labels from `days`, exactly as the manifest gives them: "5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov" |
| Place picker | a city list (below) and a latitude and longitude box. The square actually used is always shown: "34.25 N 73.5 E, tile 32N_72E" |
| Counts table | five rows, one a day; three columns, 1 mm, 10 mm, 50 mm; each cell "**40** of 51" |
| Members | per day, the 51 whole-millimetre values in member order, with member 0 labelled as the control (2.1), and the lowest, middle and highest called out so 51 numbers are readable |
| The three sentences | 11.9, verbatim |
| Credits | 11.9, verbatim, with links |

The city list is committed as `web/src/cities.json`. Every entry was checked
against the India mask on 12 November 2026, and three of them do not snap to
a land square, so the list stores **the square the page shows**, not the city
centre, and the page says so when they differ:

| City | Square shown | Note |
|---|---|---|
| Delhi | 28.50 N 77.25 E | |
| Mumbai | **19.25 N 73.00 E** | the nearest 0.25 square to 19.08 N 72.88 E is 19.00 N 73.00 E, which the mask calls sea |
| Kolkata | 22.50 N 88.25 E | |
| Chennai | 13.00 N 80.25 E | |
| Bengaluru | 13.00 N 77.50 E | |
| Hyderabad | 17.50 N 78.50 E | |
| Ahmedabad | 23.00 N 72.50 E | |
| Pune | 18.50 N 73.75 E | |
| Jaipur | 27.00 N 75.75 E | |
| Lucknow | 26.75 N 81.00 E | |
| Patna | 25.50 N 85.25 E | |
| Bhopal | 23.25 N 77.50 E | |
| Nagpur | 21.25 N 79.00 E | |
| Visakhapatnam | 17.75 N 83.25 E | |
| Kochi | **10.25 N 76.25 E** | 10.00 N 76.25 E is sea in the mask |
| Thiruvananthapuram | 8.50 N 77.00 E | |
| Guwahati | 26.25 N 91.75 E | |
| Cherrapunji | 25.25 N 91.75 E | the wettest place in the list, and a useful check that large counts display |
| Srinagar | 34.00 N 74.75 E | |
| Mangaluru | **12.75 N 75.00 E** | 12.75 N 74.75 E is sea in the mask |

A coastal city sitting in a sea square is a property of a 0.25 degree mask,
not a mistake, and the page says which square it is showing rather than
pretending the city centre was asked for.

**Stale means older than 36 hours**, measured from the model run time, not
from the publish time. A 00 UTC run published around 11:00 UTC is at most
about 18.5 hours old at midnight IST, so a normal day never trips it; two
missed publishes do. The threshold is compared server side in `api/health`
and `api/place`, and the page also recomputes it from `run_time_utc` so that
a page served from a browser cache cannot show a fresh-looking banner.

**No percentages anywhere.** Not in the table, not in the member list, not in
a tooltip. A forecast carries a percentage only when it carries a "Good track
record" label (section 6), and no label exists until the verification of
section 5 has run. The page says "40 of 51 model runs" and stops.

### 11.9 Wording that is fixed

These strings are part of the specification, not of the styling, and are
written out so they cannot drift:

| Where | Exactly |
|---|---|
| under the counts table | `0 mm means under 1 mm.` |
| under the counts table, and under the legend | `These are counts out of 51 model runs, not a calibrated probability.` **Amended twice on 12 November 2026** (11.21, then 11.28). It first read `These are model-run counts, not probabilities.`, and the page also carried "a count of 40 out of 51 is not a chance of rain", which can be read as "there is no chance of rain"; one sentence then carried the point for both, as `N of 51 model runs, which is not a calibrated probability.`, which with the count filled in is a fragment with no verb. This one is a sentence and does not change with the count |
| footer, prominent | `Not an official warning. For warnings and advisories, see the India Meteorological Department.` linking to `https://mausam.imd.gov.in/` |
| footer, forecast credit | `Copyright © 2026 European Centre for Medium-Range Weather Forecasts (ECMWF)` |
| footer, forecast credit | `This data is published under a Creative Commons Attribution 4.0 International (CC BY 4.0)` |
| footer, forecast credit | `ECMWF does not accept any liability whatsoever for any error or omission in the data, their availability, or for any loss or damage arising from their use` |
| footer, forecast credit | `Source: www.ecmwf.int. Modified: daily totals and member counts computed from AIFS ENS open data.` |
| footer, observation credit | `Observations: NASA GPM IMERG Late Precipitation L3 1 day V07C, DOI 10.5067/GPM/IMERGDL/DAY/07, a satellite estimate and not ground truth.` |
| footer | a link to `CREDITS.md` and to the repository |

The three ECMWF lines are the copyright statement, licence statement and
disclaimer that ECMWF's terms of use require of anyone redistributing their
data, quoted from `apps.ecmwf.int/datasets/licences/general/` on 12 November
2026, with the year taken from the run. 2.1 says attribution goes in
`CREDITS.md` **and** in the site footer, so `CREDITS.md` is written in this
step too; the footer is the short form and links to the long one.

### 11.10 Tests

| Test | What it holds |
|---|---|
| `tests/test_api_consistency.py` | `api/place` against the published tile, square by square |
| | a synthetic run is built with the helpers of `test_publish.py`, published to a temporary directory through `FakeStore`, and served by a `http.server` on `127.0.0.1`. `STORE_BASE_URL` points at it, so there is no network and no token |
| | the harness is written to the test's own temporary directory, not committed: six lines that import `api/place.mjs` and call `export default.fetch(new Request(url))` in plain `node` |
| | for every square checked: the three counts, the four dots and the 51 member values the API returns are identical to the tile's `c`, `d` and `m` |
| | the whole millimetres the API returns equal `m // 16`, and their count above each threshold equals the published count, which is 8.4's rule arriving at the page |
| | snapping: a request half a square away comes back with the square's own centre, and `i`, `j` and `tile` consistent with it |
| | a sea square inside the box answers 404 with a `nearest_in_tile` the tile really holds |
| | outside the box answers 400; an unreachable store answers 503; no base URL answers 500 |
| `tests/test_api_consistency.py`, `api/health` | the fields come from the manifest unchanged, `age_hours` and `stale` are computed from `run_time_utc` against a frozen clock, and `stale` flips at 36 hours and not before |
| the committed `config/store.json` | an `https` Blob URL with no trailing slash and no credential in it, and `STORE_BASE_URL` read **before** the file in both functions |
| `api/place` against the counts bytes | the byte at `i × n_lon + j` of each of the 15 counts files equals the count the API returns, so the map of G3 and the page of G2 cannot drift apart |
| the existing 156 tests | unchanged. Nothing in `pipeline/` moves for G2 |

Skipped rather than failed when `node` is not on `PATH`, with the reason
printed, the same way the `@real` tests of 8.13 skip without a built run.

**Built and run, 12 November 2026: 19 tests here, 175 in the suite.** Every
one of the 30 India squares of the synthetic run is fetched through
`api/place` under `node` and compared against its published tile, day by day
and member by member. The check was shown to bite: changing the whole
millimetre from `floor` to `round` in `api/place.mjs` fails two of the 19.

### 11.11 Settled, and what is open

Settled in this draft:

| Question | Decision |
|---|---|
| project layout | Root Directory stays the repository root; `vercel.json` sets `installCommand`, `buildCommand`, `outputDirectory` and `framework: null`, so `web/` builds and `api/` still deploys (11.2) |
| the `api/` runtime | Node `.mjs`, Web standard `fetch` export, zero dependencies, so the pipeline's `requirements.txt` is never installed (11.3) |
| CORS | the store sends `Access-Control-Allow-Origin: *`, measured. No rewrite is needed. The G2 page still goes through `api/` for the four reasons of 11.4, and G3's map reads the store directly |
| the store URL | `config/store.json`, committed, with a `STORE_BASE_URL` override; the page never learns it (11.5) |
| the G2 page | 11.8, with the city list measured against the mask and three coastal cities moved to their nearest land square |
| percentages | none, until a "Good track record" label exists |

Open:

| # | Open | Note |
|---|---|---|
| 1 | ~~the stale-cache problem of 11.1~~ | **fixed on 12 November 2026, before any section 11 code.** What is published is now decided from `list` and an immutable marker, and the mutable manifest is confirmed by ETag rather than by bytes. See 8.5, 8.6 and 8.10 |
| 2 | ~~adding `config/store.json` to the fixed structure~~ | approved |
| 3 | ~~whether the repository is connected to a Vercel project~~ | **imported and live, 12 November 2026**, at `https://precipitation-forecast-app.vercel.app`, functions in `bom1`, with the Blob store deliberately not connected to it (8.9) |
| 4 | ~~the Node version in Project Settings~~ | **26.x**, Vercel's default, kept (11.3) |

### 11.12 Part two: the real site

**This is part two of section 11, G3.** Part one (11.1 to 11.11) is live and
unchanged: `api/health`, `api/place`, the plain page, the wording and the
tests all stay. Part two adds the map, makes the map the page, and moves the
place panel beside it. Nothing in `pipeline/`, nothing in publishing and
nothing in the workflow changes; the store already holds every byte the map
needs (8.4), published and verified, and this part only reads it.

| In G3 | Out of G3, and where it goes |
|---|---|
| a MapLibre map of India, the 4,613 squares coloured by count | — |
| day 1 to 5 and threshold 1 / 10 / 50 mm controls | — |
| city search, a typed latitude and longitude, and "use my location" | — |
| click or pick a square: counts, the 51 dots, the member millimetres, a five-day strip | — |
| the legend, reading `N of 51 model runs` | — |
| everything from G2: the run line, the stale banner, the three sentences, the credits | — |
| a basemap with roads and labels | not planned; 11.14 says why |
| percentages, probabilities, reliability diagrams, the report card | sections 5, 6 and 12 |
| the track record pages | section 6, after the verification of section 5 runs |
| IMERG observations drawn on the map | not planned for G3 |

G3 is finished when the map is live on the same Vercel URL, every one of the
4,613 squares is coloured by the published count for the chosen day and
threshold, a square can be reached by clicking the map **and** by keyboard
without the map, HC8 passes on the deployed site, and the screenshots at
desktop and phone width have been looked at. The tag is **`g3-map-live`**.

### 11.13 What was measured before deciding anything, part two

Run from this laptop on 12 November 2026 against the real store and the real
published run `20261112T00Z`, with no token, plus the npm registry and the
Natural Earth shapefile already in `data/raw/ne/`.

| Measured | Result | What it decides |
|---|---|---|
| one counts file over the wire, with `Accept-Encoding: br` | **1,295 bytes** for `ge1mm_day1.u8`, of 15,609 raw, `Content-Encoding: br`, `Cache-Control: public, max-age=2592000`, `Access-Control-Allow-Origin: *` | the map can read the store directly and cheaply |
| **all fifteen** counts files over the wire | **14,441 bytes** in total, of 234,135 raw. The largest is `ge1mm_day3.u8` at 1,967 and the smallest `ge50mm_day1.u8` at 508 | the map fetches **all fifteen at load**, so changing day or threshold needs no network at all (11.16) |
| the 255 bytes of a counts file against `india.u8` | the 4,613 non-255 bytes are **exactly** the 1 bytes of `india.u8`, byte for byte | one counts file carries the mask as well as the values, so `india.u8` need not be fetched and the geometry can be built from the first file that arrives |
| the India mask's extent | 4,613 squares, from **37.0 N down to 8.25 N** and 68.5 E to 97.25 E, with **226 squares at 34.25 N and above** | those squares sit north of the boundary an OpenStreetMap basemap would draw. 11.14 |
| the OpenFreeMap Liberty style | HTTP 200, 43,311 bytes, no key, 111 layers, two sources, and three boundary layers: `boundary_2`, `boundary_3` and **`boundary_disputed`** | a basemap brings a national boundary that is not the one our mask came from, and the style itself provides for boundaries its source data calls disputed |
| the India outline, Natural Earth India POV, simplified at 0.01 degrees and written with 3 decimal places | **2,752 points in 35 parts, 44,010 bytes, 14,827 gzipped**, bounding box identical to the source, **99.9947%** of the area kept | an outline is affordable if we want one. 11.14 recommends not drawing one, and deciding from the screenshots |
| `maplibre-gl` on the npm registry | latest **6.18.0**, published 11 Nov 2026 21:28 UTC; **6.17.0** published 7 Nov 2026; BSD-3-Clause; about a release a week through October and November | pin 6.17.0, not the build published the evening before (11.15) |
| `maplibre-gl@6.17.0` `dist/maplibre-gl.mjs` and `.css` | **1,110,272 bytes raw, 295,327 gzipped** for the script; 71,596 and 10,191 for the stylesheet | the map is the heaviest thing on the site by far, against 72 KB gzipped for all of G2. 11.16 code-splits it so the text does not wait for it |
| 4,613 square polygons with all fifteen counts as properties, built in Python the way the browser will build them | **1,531,279 bytes** as compact JSON | what the browser holds in memory, built from 14,441 bytes over the wire and never transferred |
| the day-1, 1 mm counts over the seven legend classes of 11.17 | 0 → **3,660** squares, 1-10 → 457, 11-20 → 79, 21-30 → 50, 31-40 → 57, 41-50 → 115, 51 → **195** | every class is used, and in November most of India is 0. The map will look pale, and that is the forecast |

Nothing about frame rate or build size is claimed here. Those are measured
when the thing exists, and reported with the screenshots (11.26).

### 11.14 No basemap. India's own outline, and its state lines

The question was a free keyless basemap with its attribution, or no basemap
and just the Natural Earth outline. **The answer is the outline**: no
basemap, India drawn from the same source the forecast mask comes from, with
thin light internal state boundaries for orientation, and nothing else but
city dots.

#### Why no basemap

OpenFreeMap works, needs no key and would be easy. It is not used, for five
reasons, the first of which is decisive:

1. **It draws a boundary we did not choose, under squares we did.** Our mask
   comes from the Natural Earth **India point-of-view** edition, verified in
   3.5, which reaches 37.05 N; the mask has **226 squares at 34.25 N and
   above**. OpenStreetMap's boundary through that area is a different line,
   and the Liberty style carries a `boundary_disputed` layer because its
   source data marks some boundaries as disputed. Our coloured squares would
   overhang the drawn border, which reads as a bug, and the page would be
   publishing a boundary claim as a side effect of picking a tile server.
   Drawing India ourselves, from the file the mask already uses, means the
   drawn country and the forecast squares cannot disagree.
2. **Weight.** A basemap is a sprite sheet, a glyph set and a vector tile for
   every viewport on every pan and zoom. Our entire data layer is 14,441
   bytes and the two outline files are 30,967 gzipped, all fetched once.
3. **A dependency we do not need.** OpenFreeMap is free and generous and runs
   on donated infrastructure. If it is down, our map is blank for a reason
   that has nothing to do with our forecast. The store is ours and is already
   on the critical path.
4. **Clutter.** The brief asks for calm. 111 layers of roads, landuse and
   place labels under a semi-transparent choropleth is the opposite, and a
   choropleth that has to be semi-transparent to let a basemap through is a
   choropleth whose colours no longer match its legend.
5. **No attribution burden and no third-party terms.** With no basemap there
   is no OpenStreetMap or OpenFreeMap credit to carry, and the page fetches
   nothing outside our own origin and our own store.

#### What is drawn, and what it cost

Built by **`scripts/build_outline.py`** from the shapefiles already in
`data/raw/ne/`, and committed as two files under `web/src/geo/`. `data/` is
never committed, so the generated outlines are, and the script is rerun only
when Natural Earth changes. Measured by the script itself on 12 November
2026:

| File | From | Geometry | Bytes | Gzipped |
|---|---|---|---|---|
| `web/src/geo/india.geo.json` | `ne_10m_admin_0_countries_ind`, the `India` feature, **the same file and edition the mask of 3.5 is built from** | MultiPolygon, 2,745 points in 35 parts | 43,557 | **14,730** |
| `web/src/geo/states.geo.json` | `ne_10m_admin_1_states_provinces`, `admin = India`, the same file the IMD regions of 5.4 use | MultiLineString, 3,063 points in 141 parts, 220.2 degrees of line | 49,026 | **16,237** |
| | | | | **30,967 total**, against the 60,000 you allowed |

The outline keeps **99.9952%** of the source area. Both files are simplified
at **0.01 degrees**, about 1.1 km, and their coordinates are then snapped to
a **0.001 degree grid**, about 110 m, which is the precision they are written
to. A grid square is 0.25 degrees, so the drawn lines are finer than the data
they sit under by a factor of twenty-five and cannot be nudged into the wrong
square by any of this.

The snapping is done to the geometry and not to the text, so **what is
written is exactly what was checked**. Rounding coordinates in the JSON
afterwards would have meant the file could contain shapes the checks never
saw, and it did: the first build left a zero-length closed ring at 93.018 E
24.399 N, a shared border a few centimetres long whose two ends rounded to
the same coordinate. One part was below the grid and is dropped.

The outline's bounding box is 68.143 to 97.362 E and 6.746 to 37.054 N,
within one grid step of the shapefile's own 68.1434 to 97.3623 and 6.7456 to
37.0545. The script fails rather than writes if it ever moves further than
that; simplifying at 0.5 degrees instead of 0.01 moves it by 0.266 and was
refused.

| Layer | Paint |
|---|---|
| India, fill | `#ffffff` over the page's `#f4f6f8`, so the country is a sheet of paper and the sea is not |
| the counts squares | 11.17, over that fill |
| state lines | `#c9d2da`, 0.6 px, under the national line and over the squares: thin and light enough to orient without competing with the palette |
| India, line | `#aab6c0`, 1 px, drawn last so the coast stays crisp where squares meet the sea |

#### The state lines are shared boundaries only, and make no claim

**`states.geo.json` contains a line only where two Indian units meet.** For
every pair of the 36 India admin-1 polygons whose bounding boxes overlap, the
script takes the part of their boundaries that coincides, and that is all it
keeps. **68 pairs share a boundary**, 225.3 degrees of it, of which 220.2
degrees survive being clipped to the national outline.

That is a stronger rule than "internal lines", which is what this section
first proposed: an internal line is any line not near the national edge, and
a unit's edge facing an area admin-1 does not cover is exactly that. The
measured difference is **9.4 degrees of line**, about 1,000 km, that the
first rule would have drawn and this one does not.

The reason it matters is in the data. As 5.4 already records, **Natural Earth
publishes no point-of-view edition of admin-1**, and its northern units stop
short:

| | Northern limit |
|---|---|
| `ne_10m_admin_0_countries_ind`, the India POV outline, which the mask and the map both come from | **37.0545 N** |
| admin-1 `Ladakh` | 35.4954 N |
| admin-1 `Jammu and Kashmir` | 34.77 N |
| the state lines actually drawn | **34.558 N** |

An outer edge taken from admin-1 would therefore have been a different
boundary from the one the mask was cut with, drawn underneath squares we
colour. A **shared** boundary never is one: it is a line between two Indian
units by construction, which no national edge can be.

The Jammu and Kashmir to Ladakh boundary is a boundary between two Indian
union territories, so it is drawn, and it is **2.168 degrees** long. The
northern edges of both are shared with nothing and are not drawn. North of
34.558 N the map shows India's outline with no internal subdivision inside
it, which is the honest consequence of the admin-1 file stopping there, and
not a line invented to fill the space.

Four things the script checks before it writes, each of which fails the build
rather than warning:

| Check | Measured |
|---|---|
| `Jammu and Kashmir` and `Ladakh` are both in admin-1 and share a boundary | both present, 2.168 degrees |
| no drawn state line falls outside the national outline | **0.000000 degrees** outside. Keeping every unit boundary instead of only shared ones puts 0.016646 degrees outside, so this check is what the rule is for |
| no state line runs north of the admin-1 data | 34.558 N against 35.4954 N |
| both files together fit the budget | 30,967 gzipped against 60,000 |

One closed ring survives all of that and should: **Puducherry's Yanam** is an
enclave inside Andhra Pradesh, so the boundary it shares with Andhra Pradesh
is its entire perimeter, 0.327 degrees at 82.178 to 82.301 E. It is a real
boundary between two Indian units and it is drawn.

#### Amending 3.5


3.5 said "The outline decides only which grid squares count as India. The
published map does not draw national borders." **The second sentence is now
wrong and is replaced**, approved 12 November 2026:

> The outline decides which grid squares count as India, and the map draws
> it (11.14). It is the only national boundary the site draws, it is the
> India point-of-view edition, and it is the same geometry the mask was cut
> with, so the country on screen and the squares we forecast are the same
> shape. No other country's borders are drawn, and no boundary comes from a
> third-party basemap.

#### Built so a basemap could be added later without rework

Added 12 November 2026, at your request. **No basemap is drawn now and none
is planned for G3.** What this fixes is the cost of changing that mind later:
without it, adding a basemap would mean reordering layers, changing how the
squares are painted, and rewriting HC8.

| Kept open | How |
|---|---|
| a slot **below** the squares for a basemap | an empty layer with the stable id `slot-basemap`, sitting above our own white land fill and below the squares. `map.addLayer(basemapLayer, SLOT_BASEMAP)` puts a basemap exactly where one belongs: over the plain land fill it would replace, under every number we publish |
| a slot **above** the squares for labels | an empty layer with the stable id `slot-labels`, at the very top. `map.addLayer(labelLayer, SLOT_LABELS)` puts place names over everything, which is the only place labels can go |
| the squares as **one** layer with **one** constant opacity | `fill-opacity` is the exported constant `SQUARE_OPACITY`, which is **1.0**. A basemap that has to show through is then one number, not a new expression and not a second layer |

Both slots are `background` layers painted at zero opacity, so they draw
nothing at all and cost nothing: they exist only as ids to insert before.

**HC8 samples with no basemap present**, and says so in its result. That is
not a convenience: a sampled pixel equals the palette hex of 11.17 exactly
only while `SQUARE_OPACITY` is 1 and nothing is drawn underneath. If a
basemap is ever added and that constant drops below 1, HC8's colour
comparison has to be rewritten to account for the blend, and the hand check
should fail loudly rather than quietly compare a blended pixel against an
unblended table. It therefore checks both: that the slot is empty, and that
the constant is 1.

#### What else gives the reader their bearings

| | |
|---|---|
| The squares | outside the mask there is **no feature at all**, so the coloured area is exactly the area we forecast. The 0 class is a visible pale fill (11.17), so an India square with no model runs still shows that it is a square we stand behind |
| Cities | the 20 dots of `web/src/cities.json`, drawn as small circles, no labels. Tapping or focusing one selects that square and names it in the panel. 20 labels on a phone is clutter; 20 dots is orientation |
| The selected square | its own outline layer, one feature, drawn on top of everything |
| Panning off the edge | `maxBounds` set to the India box of 1.4, so the map cannot be dragged into an empty grey plain |

### 11.15 Versions, pinned

| Package | Version | Why exactly this |
|---|---|---|
| `maplibre-gl` | **6.17.0** | published 7 November 2026 and the latest for five days. 6.18.0 landed at 21:28 UTC on 11 November, the evening before this was drafted, and nothing here needs it. BSD-3-Clause |
| `react`, `react-dom` | 19.3.1 | unchanged from G2 |
| `vite` | 8.3.8 | unchanged |
| `@vitejs/plugin-react` | 6.3.0 | unchanged |

No React wrapper for MapLibre. `maplibre-gl` is used directly from one
`useEffect` that creates the map once and never recreates it: React owns the
panel and the controls, MapLibre owns the canvas. A wrapper would be a fifth
pinned dependency to keep in step with both of them, for an API that is three
calls wide.

**MapLibre 6 is ESM only**, which changes how it is imported. From the 6.0.0
changelog and the v5-to-v6 migration guide, checked 12 November 2026:

| Changed in 6 | What we write |
|---|---|
| no default export | `import * as maplibregl from 'maplibre-gl'`, never `import maplibregl from 'maplibre-gl'` |
| UMD and CSP bundles no longer published | irrelevant to us; Vite bundles the `.mjs` |
| the worker is a real URL, so `worker-src blob:` is no longer needed | one fewer thing to configure, and nothing in `vercel.json` changes |
| style-spec v25; `setPaintProperty` and `setLayoutProperty` are typed | the property names and value shapes in 11.16 are the typed ones, not strings |
| stylesheet | `import 'maplibre-gl/dist/maplibre-gl.css'` |

### 11.16 How the map gets the counts, and how it stays smooth

**Directly from the store, all fifteen files, once.** Not through `api/`.
11.4's table already promised this, and 11.1 measured the CORS that allows
it. Through `api/` it would be fifteen function invocations that do nothing
but copy bytes, each with a possible cold start between the reader and data
that is already on a CDN in `bom1` and already immutable for a month.

The page learns where the store is from **`api/health`**, on its own origin,
at runtime: that response gains a `store` block with the base URL and the
run's `paths` (11.23). So `config/store.json` is still the single source of
truth (11.5), the page still has no build-time knowledge of the store, and a
change of store is still one commit.

The whole map contract, on first load:

| # | Request | Bytes on the wire | When |
|---|---|---|---|
| 1 | `/api/health`, our own origin | about 1 KB | at load. The run id, the day labels, the staleness, the store base URL and the paths |
| 2 | 15 x `runs/<run_id>/counts/ge<T>mm_day<d>.u8` | **14,441 total**, measured | at load, in parallel. Immutable for a month |
| 3 | `/api/place?lat=&lon=` | about 2 KB | when a square is chosen |
| 4 | nothing else | | the panel's numbers all come from 3, the map's from 2 |

The India outline and the state lines of 11.14 are **not** in that table:
they are imported by the map module, so they travel inside the map's own
JavaScript chunk and add **30,967 gzipped bytes** to it rather than two more
requests. They are build-time constants of the site, not data of a run, and
they change only when `scripts/build_outline.py` is rerun.

Smoothness, with 4,613 squares on a phone:

1. **The geometry is built once and never rebuilt.** One GeoJSON
   `FeatureCollection` of 4,613 square polygons, each feature carrying **all
   fifteen counts as properties** (`ge1_d1` through `ge50_d5`) and its own
   `i` and `j`. Measured at 1,531,279 bytes of compact JSON, built in the
   browser from the 14 KB of step 2 and never transferred.
2. **Changing day or threshold changes one paint property.** The fill is a
   `step` expression over `['get', 'ge10_d3']`, and switching calls
   `map.setPaintProperty('squares', 'fill-color', …)` with the same
   expression over a different key. **No `setData`, no re-tessellation, no
   fetch, no request.** This is the whole reason all fifteen files are
   fetched up front: the controls are the thing a reader will press most, and
   they should cost nothing.
3. **Outside India has no feature.** The 255 squares are never built, so
   "outside India is transparent" is a property of the data rather than a
   colour that could be got wrong. Measured in 11.13: a counts file's
   non-255 bytes are exactly `india.u8`, so the first file to arrive gives
   both the mask and the first colouring.
4. **The map is code-split.** The map component is a dynamic `import()`, so
   the title, the run line, the stale banner and the panel render from
   `/api/health` while the 295 KB of MapLibre is still arriving. On a slow
   link the honest content appears first and the map fills in.
5. **`fill-antialias: false`** on the squares layer: a 0.25 degree square has
   a hard edge in the data, and an antialiased one costs a blend per edge
   pixel to blur a boundary that is real.
6. **No tiles, no sprite, no glyphs, no fonts.** Because of 11.14 the only
   network traffic after load is one `/api/place` per square chosen. The
   outline and the state lines are two static sources tessellated once at
   startup and never touched again: they carry no per-day property, so no
   control can make them redraw.
7. `maxBounds` on the India box and `minZoom` at the whole-country fit, so
   there is no zoom level at which the browser is asked to draw something we
   do not have.

**Rejected: drawing the counts as a raster.** A 121 x 129 canvas with one
pixel a square, as an `ImageSource` with `raster-resampling: nearest`, would
be far cheaper than 4,613 polygons and was the first idea. It is wrong, not
slow: an image source is placed by its four corner coordinates and
interpolated in Mercator space, while our rows are equally spaced in
**latitude**. Over 8.25 N to 37.0 N those are not the same spacing, so rows
in the middle of the country would be drawn a fraction of a square away from
where they belong. A silent, plausible-looking misplacement of data is
exactly what this project refuses, and no performance gain buys it.

#### What the build actually measured

Built on this laptop on 12 November 2026, `vite build`, and served as a
production build reading the real published store:

| | Raw | Gzipped |
|---|---|---|
| `index.html` | 1,540 | **780** |
| the page's stylesheet | 7,972 | **2,290** |
| the page's script, which paints the title, the run line, the stale banner, the controls and the panel | 237,883 | **75,390** |
| **first paint, all three** | | **78,460** |
| the map chunk: MapLibre, the map code, the India outline and the state lines | 1,162,750 | **323,780** |
| MapLibre's stylesheet, in the same chunk | 71,339 | **10,250** |
| **the map, loaded after the text** | | **334,030** |
| the worker MapLibre starts, loaded by the worker thread only | 520,110 | |

So the code-splitting of point 4 does what it was for: the honest content is
78 KB and arrives first, and the map's third of a megabyte follows. The
forecast data itself, on top of that, is the 14,441 bytes of 11.13.

**Four things were wrong and were found by looking at the built page**, not
by reasoning about it. They are written down because each one would have
looked like a design choice to anyone reading the result:

| What happened | Why | Fixed by |
|---|---|---|
| the map never drew: "Worker failed to load" | MapLibre 6 is ESM only and works its worker's URL out at runtime as a sibling of its own bundle, which no bundler can see, so the file was never emitted | importing it with Vite's `?url` and calling `setWorkerUrl`, which MapLibre exports for exactly this |
| the map container collapsed to zero height | `maplibre-gl.css` sets `position: relative` on the same element and loads **after** our stylesheet, so `position: absolute; inset: 0` was overridden | a definite `width: 100%; height: 100%`, which no rule about position can undo |
| the south of India was cut off | `maxBounds` two degrees outside the India box: MapLibre will not zoom out past `maxBounds`, so on a wide screen the minimum zoom it forces is **more** zoomed in than the zoom that fits the country | a box 20 degrees wider and 12 taller, which never binds and still stops anyone wandering off |
| the map was below the fold | `.shell` used `min-height`, so the panel's content set the height of the row and the map went with it | a definite `100dvh`, with the panel and the footer scrolling inside it |

On a phone the day and threshold controls are a strip **between** the map and
the sheet, not a card floating over the map: floating, they covered both the
south of the country and the legend. The legend becomes a single compact
ramp, and it is hidden while the sheet is open, because with the map reduced
to a strip it covered what was left of it. Every count row in the panel
carries its own swatch and class name, so the key is never out of reach.

The frame cost of a day or threshold switch is not claimed here either. What
can be said is what the code does: one `setPaintProperty`, no request and no
source update, which was checked by watching the network while switching.

### 11.17 The colour scale and the legend

**ColorBrewer YlGnBu**, which ColorBrewer itself marks colour-blind safe,
with 0 given its own near-neutral class and 51 its own darkest one.

| Count | Fill | Legend row |
|---|---|---|
| 0 | `#eceff1` | `0` |
| 1 to 10 | `#c7e9b4` | `1-10` |
| 11 to 20 | `#7fcdbb` | `11-20` |
| 21 to 30 | `#41b6c4` | `21-30` |
| 31 to 40 | `#1d91c0` | `31-40` |
| 41 to 50 | `#225ea8` | `41-50` |
| 51 | `#0c2c84` | `51` |
| 255 | no feature | not in the legend |

The legend heading is **`N of 51 model runs`** and its caption is the fixed
sentence of 11.21. The seven swatches each carry a hairline border so the
palest two are visible against the page.

Why these classes:

- **Equal width of ten, between two endpoints of their own.** The legend's
  arithmetic is then obvious: a square two classes darker is roughly twenty
  more model runs. A quantile scale, or anything tuned to make the map look
  interesting, would imply that the distance between classes means something
  about likelihood. It does not, and section 6 is where that question is
  earned.
- **0 is its own class** because "no model run gives this" is a different
  statement from "a few do", and in November it is most of the map: 3,660 of
  4,613 squares on day 1 at 1 mm (11.13). It is drawn rather than left blank
  so that an India square with no rain is visibly a square we forecast.
- **51 is its own class** because "every model run" is also a different
  statement, and it is 195 squares on that same day.
- A sequential ramp, not a diverging one: a count has a low end and a high
  end and no meaningful middle.

`web/src/palette.js` holds this table as the only copy, exports
`classOf(count)` and `colourOf(count)`, and is plain enough for `node` to
import, which is what makes the legend testable (11.24) and HC8 possible
(11.25).

Contrast is checked rather than assumed: every text colour against its
background, and the legend labels against their swatches, measured as a
contrast ratio at build time and reported. The two darkest classes take white
labels; the rest take the page's ink colour.

### 11.18 The layout

Light theme only, declared with `color-scheme: light`, because the palette is
chosen against a white page and an automatic dark inversion would change what
the colours mean.

One font: the **system UI stack**
(`ui-sans-serif, system-ui, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`).
No webfont download, no flash of unstyled text, and it renders Indian
language text correctly if the city list ever carries it. Counts are set with
`font-variant-numeric: tabular-nums` so columns of numbers line up.

**Desktop, 1024 px and wider.** The map is the hero and fills the viewport.

```
+--------------------------------------------------------------+
| India precipitation forecast        run line, stale banner    |  header
+---------------------------------------------+----------------+
|                                             |  place         |
|                                             |  counts        |
|            map, fills the rest              |  dots          |
|                                             |  members       |
|  [day 1..5]  [1 / 10 / 50 mm]   legend      |  5-day strip   |
+---------------------------------------------+----------------+
|  the three sentences, IMD link, credits                       |  footer
+--------------------------------------------------------------+
```

The panel is a fixed 380 px column on the right. The day and threshold
controls and the legend float over the map's bottom-left on a translucent
white card: over the map because they change the map, and bottom-left because
that corner of the India box is the Arabian Sea.

**Phone and tablet, under 1024 px.** The map takes the top 55% of the
viewport and the panel becomes a bottom sheet with two heights: a peek that
shows the place line and the three counts, and an expanded state at 85% that
shows everything. The sheet is moved by dragging its handle **and** by a real
`<button>` with `aria-expanded`, so it is not gesture-only. The day and
threshold controls sit in the sheet's header, so they are reachable at either
height, and the legend collapses to one row of swatches with the end labels
only.

Nothing in either layout overlaps anything: the controls card and the sheet
have their own space, and MapLibre is told about the panel with `padding`, so
`fitBounds` centres India in the part of the canvas that is actually visible.

### 11.19 The controls

| Control | Behaviour | Keyboard |
|---|---|---|
| Day 1 to 5 | five buttons showing the short IST label, `Fri 13 Nov`, from `short_ist` (11.23). The full window, `5:30 am Fri 13 Nov to 5:30 am Sat 14 Nov`, is printed under the group for the chosen day | `role="radiogroup"`, arrow keys move, one tab stop |
| Threshold | three buttons, `1 mm`, `10 mm`, `50 mm`, described once as "at least this much rain in the day" | the same |
| Search | one text box. Typing filters the 20 cities; typing two numbers, `28.5, 77.25`, is taken as a latitude and longitude | `role="combobox"`, arrow keys through the list, Enter picks, Escape closes |
| Use my location | a button, so it is always a deliberate act. `navigator.geolocation.getCurrentPosition` once, no watching | a button |
| The map | click a square to select it | MapLibre's own keys pan and zoom. **A square is never selectable only by clicking**: search and the typed coordinates reach every square without the map (11.22) |

**The location never leaves the device at full precision.** The browser's fix
is snapped to the 0.25 degree square **in the page** before anything is sent,
and only the square's centre goes to `/api/place`. `api/place` would snap it
to that same square anyway, so the answer is identical, and the finest thing
that ever appears in a request URL or a server log is a 28 km square rather
than somebody's position. The same snap is applied to a map click.

That duplicates arithmetic which 11.4 said should live in one place, so it is
**tested rather than trusted**: `web/src/snap.js` exports the snap, plain
`node` can import it, and a test drives it and `api/place.mjs` over a grid of
points and fails if they ever disagree about which square a point is in
(11.24). One copy with a test that the two agree is honest; two copies that
merely look alike is not.

A denied permission, a browser with no geolocation, and a fix outside the
India box each get one plain sentence and no retry loop. A fix inside the box
on a sea square goes through the one-square rule of 11.7 and the page says
which square it moved to, exactly as a typed coordinate does.

### 11.20 The place panel

In order down the panel, for the chosen square and the chosen day:

| Part | Content |
|---|---|
| Place | `28.50 N 77.25 E`, with the city name only when the square **is** that city's square in `cities.json`. No city name is invented for a square that merely sits near one |
| Moved | when the square used is not the square asked for: `19.08 N 72.88 E is sea on this 0.25 degree grid. Showing 19.25 N 73.00 E, one square north.` (11.7) |
| **The day in one sentence** | one plain sentence for the chosen day, built only from that day's three counts: `18 of 51 model runs reach 1 mm, none reach 10 mm.` The rule is below |
| Counts | three rows for 1, 10 and 50 mm, each `40 of 51 model runs`, the chosen threshold emphasised. The published numbers, from `api/place` |
| The sentence | `40 of 51 model runs, which is not a calibrated probability.` once, under the counts, for the chosen threshold |
| Dots | 51 dots, one a member, in the four categories of 4.3, with the category counts beside them and member 0 marked as the control (2.1). Laid out so 51 dots are countable rather than decorative |
| Members | the 51 values as whole millimetres rounded down, in member order, with the lowest, middle and highest called out, and `0 mm means under 1 mm.` under them |
| Five-day strip | five cells, one a day, each filled with the palette colour for that day's count at the chosen threshold and printing the count. Clicking a cell changes the day. Each cell's accessible name is **that day's sentence**, so a screen reader gets five readable days rather than five numbers. One square's whole five days without touching the day control |
| The square used | `i = 15, j = 22, tile 32N_72E`, in small type, so a reader can repeat the arithmetic by hand the way HC7 and HC8 do |

The dots, the counts, the sentences and the five-day strip all come from the
single `/api/place` response, which already carries all five days (11.7), so
changing the day changes no request.

#### The one-sentence rule

Added 12 November 2026. The counts table is correct and it is also four
numbers in a grid; a reader who wants to know what a day looks like should
not have to assemble it. So each day gets one sentence, **derived from
nothing but that day's three published counts**, by a rule with no choices
in it.

Built in `api/place` as `days[].sentence`, so there is one copy of the rule
and a test can hold it (11.24). Never built in the browser.

Let `c1`, `c10` and `c50` be that day's counts at 1, 10 and 50 mm.

| Case | Sentence |
|---|---|
| `c1 = 0` | `0 of 51 model runs reach 1 mm.` and nothing more: nothing can reach 10 mm without reaching 1 mm |
| `c1 > 0`, `c10 = 0` | `18 of 51 model runs reach 1 mm, none reach 10 mm.` |
| `c1 > 0`, `c10 > 0`, `c50 = 0` | `40 of 51 model runs reach 1 mm, 12 reach 10 mm, none reach 50 mm.` |
| `c1 > 0`, `c10 > 0`, `c50 > 0` | `51 of 51 model runs reach 1 mm, 48 reach 10 mm, 3 reach 50 mm.` |
| a count of exactly 1 | the verb agrees: `1 of 51 model runs reaches 1 mm`, and `1 reaches 10 mm` |

What the rule deliberately does not contain:

- **No adjectives and no weather words.** Not "dry", not "wet", not "heavy",
  not "likely", not "chance", not "expected", not "risk". The sentence names
  a count, a threshold and a number of model runs, and stops. A rule that
  said "dry" below some count would be a forecast of its own, made up by the
  website rather than by the ensemble, and `0 of 51` reaching 1 mm is not the
  same claim as "it will be dry".
- **No thresholds it cannot support.** A higher threshold is mentioned only
  once a lower one is reached, because `c1 >= c10 >= c50` always holds
  (4.2) and saying "none reach 50 mm" after "0 reach 1 mm" is noise.
- **No percentages, ever**, as everywhere else on the page.
- **No rounding, no banding, no "about".** The counts go in as integers.

The published counts are monotone by construction, so the test asserts
`c1 >= c10 >= c50` on every square of the synthetic run as well as checking
the sentence, and a day that broke that would fail rather than produce a
sentence that reads backwards.

### 11.21 Wording, and what G2 keeps

Everything in 11.9 stays, with **one replacement**. The G2 page carried
`a count of 40 out of 51 is not a chance of rain`, which can be read as
"there is no chance of rain". It is replaced, everywhere it appears, by the
sentence this part is built around:

| Where | Exactly |
|---|---|
| legend heading | `N of 51 model runs` |
| legend caption, and under the panel's counts | `These are counts out of 51 model runs, not a calibrated probability.` **Amended by 11.28.** This row read `N of 51 model runs, which is not a calibrated probability.`, with the real number in place of `N`, which is a fragment with no verb and reads as a claim about that one number |
| under the member values | `0 mm means under 1 mm.` |
| **removed** | `These are model-run counts, not probabilities.` and `a count of 40 out of 51 is not a chance of rain` |
| footer | `Not an official warning. For warnings and advisories, see the India Meteorological Department.` linking to `https://mausam.imd.gov.in/` |
| footer | the three ECMWF lines of 11.9, verbatim |
| footer | the NASA IMERG line of 11.9, verbatim |
| footer, new | `Map rendering: MapLibre GL JS 6.17.0, BSD-3-Clause.` |
| footer | the link to `CREDITS.md` and to the repository |

One sentence carrying the point is better than two, and the replacement says
what the old pair said while also naming the thing these numbers are not: a
calibrated probability. **This amends 11.9**, which needs your nod.

There is no OpenStreetMap or basemap credit because there is no basemap
(11.14), and the Natural Earth credit in `CREDITS.md` is unchanged: the
outline still decides the mask, it is simply not drawn.

Kept from G2 without change: the run id and the run time in IST, the publish
time, the stale banner at 36 hours recomputed in the page from
`run_time_utc`, the day labels taken from the manifest rather than formatted
in the browser, and no percentage anywhere.

### 11.22 Keyboard, screen readers and the promise about the map

A `<canvas>` is not readable. So the rule for this page is written down as a
promise rather than left to chance:

**No information on this site is available only by clicking the map.**

| | |
|---|---|
| Reaching a square | the search box takes a city or a typed latitude and longitude, both without the map |
| Reading a square | everything the map shows for the selected square is text in the panel, including its count and its legend class by name |
| The map element | `aria-label` naming what it is, MapLibre's own keyboard pan and zoom, one tab stop, and `aria-hidden` on its decorative sub-elements |
| Announcing a change | the place line is an `aria-live="polite"` region, so picking a square or changing the day says so once rather than silently repainting |
| Focus | a visible focus ring on every control, never removed |
| Motion | `prefers-reduced-motion` is respected; MapLibre's `respectPrefersReducedMotion` default is left on, and the page's own fly-to becomes a jump |
| Contrast | every text and swatch pair measured at build time, 4.5:1 or better |
| No JavaScript | a `<noscript>` block saying the page needs JavaScript and giving the raw `/api/place?lat=&lon=` route, which answers JSON with no script at all |

### 11.23 The two small additions to `api/health` and `api/place`

Both are additive. No field changes meaning, no status code changes, and the
60 second `Cache-Control` of 11.6 and 11.7 stays.

**`api/health` gains a `source` block**, so the page can fetch bytes from
the store after exactly one request to its own origin:

| Field | From |
|---|---|
| `source.base_url` | the same resolution as today: `STORE_BASE_URL`, then `config/store.json` (11.5) |
| `source.paths` | the manifest's own `paths`: `counts`, `tiles`, `india` |
| `source.counts_files` | the manifest's 15 names, `ge1mm_day1.u8` and the rest |
| `source.grid` | the manifest's `grid`: `n_lat`, `n_lon`, `grid_step_degrees`, `not_india`, `order` |

It is called `source` and not `store`, as this draft first said, because
`store` is **already** a field of that response: 11.6 gives it the one-word
status, `reachable` or the failure in words. Taking a live field's name for
something else would have broken the G2 page to save a word.

The `grid` block matters more than it looks: the page then never hardcodes
121, 129 or 255, so it reads the byte at `i * n_lon + j` using the numbers
the run itself published. A grid that ever changed would move the colours
correctly or fail loudly, rather than quietly painting the wrong squares.

**Both functions gain `days[].short_ist`**, `Fri 13 Nov`, derived server side
from `from_ist`, which the manifest already carries. The browser does no date
formatting at all, which keeps every date on the page in IST by construction
rather than by the reader's time zone.

**`api/place` gains two more fields per square**:

| Field | What |
|---|---|
| `days[].sentence` | the one-sentence rule of 11.20, built from that day's three counts and nothing else. Server side so there is one copy of the rule and a test can hold it |
| ~~`nearest_city`~~ | **dropped while building, 12 November 2026.** It would have made the function read `web/src/cities.json`, which means coupling `api/` to the site's source tree and widening `includeFiles` in `vercel.json` (11.2) for a city name. The page already holds that list and does the lookup itself: the square's name is a label, not a forecast number, so nothing honest is lost by the browser matching a latitude and longitude against twenty rows. The rule is unchanged either way — a city name appears only when the square **is** that city's square |

**This amends 11.5's table**: the page's row changes from "**nothing.** It
never learns the URL" to "learns it from `api/health` at runtime, never from
a build-time value". The point of that row was that the store URL is not
baked into the site, and that still holds.

### 11.24 Tests

All of it extends `tests/test_api_consistency.py`, which already publishes a
synthetic run through `FakeStore`, serves it on `127.0.0.1` and drives the
functions under plain `node` (11.10). No network, no token, no browser.

| Test | What it holds |
|---|---|
| the `store` block | `base_url` is the server the test set, and `paths`, `counts_files` and `grid` are the manifest's own values, unchanged |
| `short_ist` | all five days match a fixed expected string for the frozen synthetic run, with no timezone library involved |
| **the map byte against the panel count** | for **every** India square and **all fifteen** day-threshold combinations: the byte at `i * n_lon + j` of `counts/ge<T>mm_day<d>.u8` equals the count `api/place` returns for that day and that threshold. Part one checked one combination; the map reads all fifteen, so all fifteen are checked |
| the mask across the counts files | the set of non-255 positions is identical in all fifteen files and equal to `india.u8`, which is what lets the geometry be built from whichever file arrives first |
| the palette, in `node` | `palette.js` for every count 0 to 51: each falls in exactly one class, the classes are contiguous and cover 0 to 51 with no gap and no overlap, the boundaries are the published table of 11.17, and 255 produces no fill |
| the snap agreement, in `node` | `web/src/snap.js` and `api/place.mjs` are given the same grid of points and must name the same square every time. This is what makes it safe for the page to round a location before sending it (11.19) |
| the legend class of a count | `classOf` agrees with the class the panel names in text, so the colour on the map and the words in the panel cannot drift |
| **the day sentence**, in `node` | the rule of 11.20 against every square of the synthetic run: the sentence names the day's real counts, it stops at `1 mm` when `c1` is 0, it says `none reach` rather than `0 reach` for a higher threshold, the verb agrees when a count is 1, and it contains **none** of the words `dry`, `wet`, `heavy`, `likely`, `chance`, `expected`, `risk`, `probability` or `%`. The forbidden words are a list in the test, so adding a cheerful adjective later fails it |
| the counts are monotone | `c1 >= c10 >= c50` on every square and every day of the synthetic run, which is what lets the sentence mention a higher threshold only after a lower one |
| `web/src/geo/india.geo.json` and `states.geo.json` | in `tests/test_india_mask.py`: every one of the 4,613 India square centres lies inside the committed outline; the outline's bounding box equals the shapefile's; the state lines are all inside the outline; and `scripts/build_outline.py --check` reproduces both files byte for byte, so a committed outline can never drift from the source it claims to come from |
| everything from part one | unchanged. Today's 193 tests must still pass, and nothing in `pipeline/` moves for G3 |

Skipped with a printed reason when `node` is not on `PATH`, as before. The
number of new tests is not predicted here; it is reported when they are
written and run.

### 11.25 HC8

**For one square, five independent things must give the same answer.** HC7
compared two copies of the same run; HC8 compares the published bytes, the
API, the rendered page and the drawn pixel.

`handchecks/hc8_map_square.py`, anonymous HTTPS only, no project imports, the
arithmetic written out longhand the way HC7 does it:

| # | The thing | How it is got |
|---|---|---|
| 1 | **the store byte** | `i = (38.0 - lat) / 0.25`, `j = (lon - 68.0) / 0.25`, `byte = i * 121 + j`, read from `runs/<run_id>/counts/ge<T>mm_day<d>.u8` |
| 2 | **the tile** | `c[day - 1][k]` from `runs/<run_id>/tiles/<tile>.json`, with `tile = floor(lat / 4) * 4, floor(lon / 4) * 4` |
| 3 | **`/api/place`** | `counts_by_threshold[k].count` from the live site |
| 4 | **the panel** | the number in the panel's count row, read out of the page's DOM in Chrome |
| 5 | **the map colour and the legend class** | the pixel sampled from the map canvas at that square's centre, and the legend row the page marks active |

It passes when 1, 2, 3 and 4 are the same integer, **and** the sampled pixel
is exactly the palette hex of 11.17 for the class that contains that integer,
**and** the active legend row is that class. Anything else is a failure with
all five values printed.

Two more conditions, because the pixel comparison depends on them: the
basemap slot of 11.14 must be **empty**, and the squares' `fill-opacity`
must be **1**. A sampled pixel only equals an unblended table while both hold,
so HC8 asserts them rather than assuming them, and records in its result that
it sampled with no basemap present.

Reading a pixel back from a WebGL canvas needs `preserveDrawingBuffer`, which
costs performance on every frame for every reader. So the map sets it **only
when the page is loaded with `?handcheck=1`**, and the production map never
carries it. The hand check therefore runs against the same deployed code with
one flag, not against a special build.

Run on five squares, though one is the requirement: the HC6 and HC7 square at
**34.25 N 73.5 E**, a square whose count is 0, one whose count is 51, and one
in each of two middle classes, so every part of the palette table is
exercised. Results to `handchecks/results/hc8_map_square.csv` with the run
id, and the screenshot kept beside it.

It is shown to bite before it is believed: moving one palette boundary by one
count, or changing one hex digit, must fail it.

### 11.26 The order of work, and the tag

1. `api/health` and `api/place`: the `store` block, `short_ist`,
   `nearest_city`. Tests first, then the change.
2. `web/src/palette.js` and `web/src/snap.js` with their `node` tests, before
   anything draws.
3. The map: source, layers, controls, legend.
4. The panel and the layout, desktop then bottom sheet.
5. `npm run build`, then the measurements this draft refused to guess: bundle
   size, first paint, the cost of a day and threshold switch, and the
   contrast ratios.
6. Deploy, then **screenshots at 1440 x 900 and 390 x 844, shown to you**.
7. HC8 on the deployed site, shown to bite.
8. Only then the tag **`g3-map-live`**.

Each step is its own commit, staged by name.

### 11.27 Settled, and what is open

Settled in this draft:

| Question | Decision |
|---|---|
| basemap | **none**, and no outline either: the 4,613 squares are the map, with city dots for orientation. 11.14, five reasons, the first being that a basemap draws a boundary that is not the one our mask came from |
| MapLibre version | 6.17.0 exact, ESM-only import, style-spec v25 (11.15) |
| where the counts come from | the store directly, all fifteen files, 14,441 bytes measured, with the base URL learned from `api/health` (11.16) |
| smoothness | geometry built once, day and threshold switch by one paint property with no fetch and no re-tessellation, the map code-split so text paints first (11.16) |
| the palette | ColorBrewer YlGnBu, colour-blind safe, seven classes with 0 and 51 their own (11.17) |
| the raster shortcut | rejected for correctness, not for speed (11.16) |
| percentages | still none, anywhere, until section 6 earns one |
| the tag | `g3-map-live` |

**Answered by you on 12 November 2026**, and built that way:

| # | Was open | Your answer |
|---|---|---|
| 1 | **Draw the India outline?** | **Yes**, from the same Natural Earth India point-of-view file the mask is cut from, **plus thin light state lines** from the admin-1 file the IMD regions already use, drawn only where two Indian units share a boundary, if they stayed under about 60 KB gzipped. Measured: **14,730 + 16,237 = 30,967 gzipped**, about half the budget, so both are drawn (11.14). Jammu and Kashmir and Ladakh were checked by name, as you asked: they share 2.168 degrees of boundary, which is drawn, and nothing from admin-1 falls outside the point-of-view outline. `scripts/build_outline.py` is **approved into the fixed structure**, and 3.5's "the published map does not draw national borders" is amended there and in 11.14. Still no basemap |
| 2 | replacing both old sentences with `N of 51 model runs, which is not a calibrated probability.` | **yes.** 11.9's row is amended and 11.21 holds the replacement |
| 3 | the page learning the store base URL from `api/health` at runtime | **yes.** 11.5's table row is amended |
| 4 | **one plain sentence a day in the panel, above the counts** | **added**, built from that day's three counts and nothing else, with no weather words at all: the rule is 11.20 and the test that holds it, including a list of forbidden words, is 11.24 |
| 5 | New files under `web/src/` | no approval needed: the fixed structure says `web/` is React, Vite and MapLibre and names no files inside it. `scripts/build_outline.py` is the one structure change, and it is approved |
| 6 | City dots with no labels | yes for G3. Labels need either a glyph server or 20 DOM markers, and both are clutter on a phone |
| 7 | Dark mode | no. The palette is calibrated against white, and 11.18 declares `color-scheme: light` so a browser cannot invert it |

Nothing in part two is open. What is left is building it, in the order of
11.26, and the one decision that can only be made from a picture: whether
the state lines at `#c9d2da` are too strong or too faint, which is a colour
to adjust after the screenshots rather than a question to settle in prose.

### 11.28 The design fixes, after looking at the built page

Part two was built, screenshotted and read. Eighteen things were wrong or
missing, and they are recorded here with what was measured rather than
rewritten over the top of 11.14 to 11.27, so the page's history stays legible
and so the measurements behind each fix can be checked. Where a fix changes
something an earlier part of section 11 settled, the amendment is written out
and the earlier wording is kept beside it.

Nothing about the data or the method changes here. The counts, the mask, the
publishing and the workflow are untouched; every fix is in `web/`, in the two
`api/` functions' wording, or in the new town list.

#### The two faults that were invisible in a screenshot

Both were found by reading the browser's console and the page's own geometry,
not by looking at the picture, and both had already shipped to the branch.

**The selection ring never existed.** `circle-radius` was written as
`["max", 9, ["*", 0.708, ["*", ["^", 2, ["zoom"]], 0.3556]]]`, which says the
right thing and is not allowed: the style specification permits `["zoom"]`
only as the direct input of a **top-level** `step` or `interpolate`. MapLibre
refused both ring layers with

    layers.picked-ring.paint.circle-radius: "zoom" expression may only be
    used as input to a top-level "step" or "interpolate" expression

and, because an invalid layer is reported through the map's error event rather
than thrown, the page carried on and simply had no ring. It is now a top-level
`["interpolate", ["exponential", 2], ["zoom"], …]`, which is not an
approximation of the arithmetic it replaces: a 0.25 degree square grows by a
factor of two per zoom level, so an exponential of base 2 **is** its
half-diagonal, flat at 9 pixels until the square overtakes it at zoom 5.16.

**`maxBounds` was quietly overriding the fit.** `fitBounds` was being given
padding worked out from the overlays, and MapLibre was ignoring it, because
the minimum zoom implied by `maxBounds` was *higher* than the zoom the padded
fit asked for. On the 1,060 by 566 canvas the padded fit wanted a world 4,898
pixels across and `maxBounds` would not allow smaller than 5,451. India was
not cut off only because the country is smaller than the 6 to 38 box it sits
in — the same trap as the first build's cut-off south, one level further in.
The limits are now `LON_MIN - 40` to `LON_MAX + 40` and `LAT_MIN - 24` to
`LAT_MAX + 14`, where the implied minimum is 3,469 pixels and never binds, on
a phone or on a desktop.

#### What is drawn on the map, and what is no longer

| Was | Is | Why |
|---|---|---|
| the chosen square filled `#0b2b4a` by a 2 px outline on a 4 px square | an 18 px ring, dark `#1f2933` with a white halo, no fill, plus the place name | at the whole-India view a 0.25 degree square is about four pixels, so a two pixel navy outline filled it in and the chosen square read as the darkest class on the scale: 51 of 51. A mark must not be able to be mistaken for a measurement |
| the day and threshold card floating bottom left | a bar above the map | the card covered Tamil Nadu, Kerala and the southern tip |
| the legend floating bottom right | in the same bar, a horizontal ramp | it covered the Bay of Bengal and the Andaman Islands, which have three forecast squares of their own, and leaving room for a box 237 pixels tall shrank India by a fifth |
| sea `#eaf0f4` | sea `#aec6da` | see below |
| no place names | the twenty cities, with a white halo | an unlabelled map of coloured squares cannot be read |

**The sea.** `#eaf0f4` against the 0 class's `#eceff1` is a WCAG contrast
ratio of **1.005**: the same colour to any eye. The difference it hid is the
difference between *no model run here reaches 1 mm* and *there is no forecast
here*, which is the whole point of the mask. The two hex values are now
**`#aec6da` for the sea and `#eceff1` for the 0 class**, a ratio of **1.53**,
and 1.77 against the white land fill under the squares. The sea is a
desaturated blue-grey, so it is also not mistakable for the saturated blues
further up the scale. `SEA` and `LAND` live in `palette.js` with the classes
and a test fails if the old value comes back.

**The place names are elements, not a symbol layer.** MapLibre draws text from
SDF glyph files fetched from a `glyphs` URL, and there is no such URL here on
purpose: nothing on this map comes from a third party, and a font server would
be one. Rasterising glyphs in the build would be a new dependency for twenty
words. So the labels are twenty spans above the canvas, positioned by the
map's own `project()` on every frame, with the halo done by four text shadows.
Being above the canvas puts them above every layer including `SLOT_LABELS`,
which stays empty for a basemap's own labels.

Which names show is not a list of important cities. Every label is measured
and placed greedily — the chosen square first, then the cities in the order
`cities.json` lists them — and any whose box would come within 9 pixels of one
already placed is hidden. At the whole-India view about ten fit; zoomed in,
all twenty. The alternative was a hand-written list of "major" cities, which
is an argument rather than a rule.

**The basemap slots are unchanged.** `SLOT_BASEMAP` is still immediately below
the squares and `SLOT_LABELS` above them, `SQUARE_OPACITY` is still the single
constant `1`, and HC8 still samples with no basemap present. The ring and the
labels are drawn above the squares and are not a basemap concern.

#### The panel

| Was | Is |
|---|---|
| `18 under 1 mm` | `Under 1 mm: 18` |
| a 51-cell grid of values, always | one line — `All 51 runs: 0 mm, which means under 1 mm`, or `lowest 0 mm, middle 0 mm, highest 2 mm` — with `Show all 51 values` behind it |
| three count rows that looked clickable and were not | three radio buttons, the same three choices as the threshold buttons, bound to the same state |
| `1 of 51 model runs, which is not a calibrated probability.` | `These are counts out of 51 model runs, not a calibrated probability.` |
| a day window with no timezone | `… to 5:30 am Sat 14 Nov IST`, and `Dates are IST` under the five-day strip |
| the day strip's dark cells written in the page's dark ink | each cell written in its own class's `ink` (see below) |
| a chosen square on first load | nothing chosen, and `How to read this map` |
| an error reduced to its first clause | the error and the detail that says why |

**11.9 and 11.21 are amended.** The row `N of 51 model runs, which is not a
calibrated probability.` is replaced, everywhere it appears, by

> These are counts out of 51 model runs, not a calibrated probability.

With the count filled in, the old sentence was a fragment with no verb, and it
read as a claim about the one number beside it. This one is a sentence, it is
the same whatever the count is, and it says what the whole column is. The
legend caption uses it too, so the page has one sentence for this and not two.
The legend heading `N of 51 model runs` is unchanged.

**11.17's ink column is amended, and two of its seven values were wrong.**
The five-day strip paints each cell its count's colour and wrote the number on
it in the page's own ink, so a day where all 51 runs reach the threshold was
near-black on navy. 11.17 has carried an `ink` per class since it was written
and nothing was reading it — and when something finally did, the column turned
out not to hold. White on `#1d91c0` is a contrast ratio of **3.58**, under the
4.5 WCAG AA asks of text this size, and the page's `#1f2933` on it is only
**4.12**. The dark ink is now `#111a22`, used for the five lighter classes,
where the worst case is **4.91** on `#1d91c0` and the rest are 7.29 or better;
white stays on `#225ea8` and `#0c2c84`, where it is 6.49 and 12.29. A test
computes all seven and fails under 4.5, so an ink that cannot be read cannot
be shipped again.

| class | colour | ink was | ink is | ratio |
|---|---|---|---|---|
| 0 | `#eceff1` | `#1f2933` | `#111a22` | 15.22 |
| 1-10 | `#c7e9b4` | `#1f2933` | `#111a22` | 13.18 |
| 11-20 | `#7fcdbb` | `#1f2933` | `#111a22` | 9.50 |
| 21-30 | `#41b6c4` | `#1f2933` | `#111a22` | 7.29 |
| 31-40 | `#1d91c0` | `#ffffff` (3.58) | `#111a22` | 4.91 |
| 41-50 | `#225ea8` | `#ffffff` | `#ffffff` | 6.49 |
| 51 | `#0c2c84` | `#ffffff` | `#ffffff` | 12.29 |

The square colours themselves are untouched, so nothing HC8 samples changes.

**The default view is day 1, 1 mm, nothing chosen.** `FIRST_DAY` and
`FIRST_THRESHOLD` are the two constants in `App.jsx` and there is no third
place to look. The panel then carries `How to read this map` — what a square
is, what the colour counts, and that it is not a probability — and
`Click a square or search a town.`

**The header carries two lines that were below the fold.** `Not an official
warning.` with the IMD link, and one line of ECMWF credit outside the
collapsed details: `Forecast: ECMWF AIFS ENS, CC BY 4.0`, linking to the full
credits. ECMWF's licence asks for attribution wherever the data is shown, and
"inside a `<details>` the reader never opens" is not wherever.

#### Lakshadweep, and the south of the Andamans

The question asked was whether any Lakshadweep square is in the India mask.
**None is**, and the measurement is already in `config/india_mask.json`: the
group's box holds 209 squares, **0** have their centre inside the outline, and
the model's own land fraction never exceeds **0.0312** anywhere in it.
Kavaratti's square, 10.50 N 72.75 E, has a land fraction of 0.0000 and its
centre is 13.4 km from the nearest land in the outline.

Checking that turned up a second case nobody had asked about. **Port Blair is
not forecast either.** Its square, 11.75 N 92.75 E, *is* inside the outline,
but the model's land fraction there is **0.0469**, under the 0.5 of SPEC 3.5,
and so are all eight squares around it. Three Andaman squares do pass —
12.75 N 92.75 E at 0.7422, 12.50 N 92.75 E at 0.7578, and 10.75 N 92.50 E —
and they are forecast and drawn. South Andaman is simply narrower than a
28 km square.

Both now get one plain sentence instead of `outside the forecast area`, which
is true and reads as though the reader had clicked the open ocean. The table
is in `web/src/islands.js` for the page and repeated word for word in
`api/place.mjs` for a reader with no JavaScript; a test drives both files over
the whole India box and fails if a single word differs, which is the same
arrangement 11.24 already uses for the snapping arithmetic. `api/place` also
returns `island_group` beside the sentence, and the page shows it in a plain
box rather than a red one, because a limit of the grid is not an error.

Each sentence ends `This is a limit of the grid, not a forecast of no rain.`,
and a test holds them to the day sentence's own standard: no percentage, and
none of `dry`, `likely`, `chance`, `probability`, `unlikely`, `expect` or
`safe`.

#### The town list

The twenty hand-written cities are no longer what the search box reads. The
list is now **215 towns**, built by `scripts/build_towns.py` from Natural
Earth 1:10m populated places, version 5.1.2, public domain — the same source
family as the two outlines, downloaded with its sha256 recorded in the script.
`web/src/towns.json` is **15,556 bytes, 2,979 gzipped**, against a budget of
12,000, and it is in the page's first chunk because the search box is there
from the first paint. The twenty cities stay, unchanged, as the labelled dots
on the map.

**Which towns.** A town is in the list when its point falls inside the drawn
India point-of-view outline — the geometry the mask was cut with. That is the
rule the rest of the project already runs on and it is geometric rather than a
judgement: the outline decides what is India, so it decides which towns are in
India. It gives 215. By Natural Earth's own `ADM0NAME` those are
`{India: 214, Pakistan: 1}`; the one is Gilgit, which Natural Earth's
`FCLASS_IN` column — its India point-of-view field — also marks. Nothing from
Nepal, Bangladesh, Bhutan or Myanmar creeps in across a border.

**Which square.** Each town is resolved by the rule of 11.7, the same one
`api/place` uses for any point. Measured: **200** towns land on their own
square, **13** on the nearest land square one step out (Mumbai, Kochi, Panaji,
Diu, Daman, Bhavnagar, Puri, Kollam, Alappuzha, Kozhikode, Machilipatnam,
Mangaluru, Tuticorin), and **2** on nothing within one step — Kavaratti and
Port Blair, which carry their island group instead. The file stores the square
and never the town's own position, so nothing finer than 28 km is in the
bundle at all, which is 11.19 in the data as well as in the code.

Four squares hold two towns each — Bhiwandi with Kalyan, Dispur with Guwahati,
Faridabad with New Delhi, Haora with Kolkata — and the page names both.
Claiming one would be saying something the grid does not know: at 0.25 degrees
they are the same square and get the same numbers. Two towns share a name,
both called Aurangabad, and those two carry the state from `ADM1NAME`. No
other town does, because that field is not always right — it files Bhavnagar
under "Dadra and Nagar Haveli" — and an unnecessary wrong label is worse than
none.

`scripts/build_towns.py` is added to the fixed structure in `CLAUDE.md`. It
prints what it measured and **fails rather than writes** if the count is not
215, if the by-country tally changes, if a different set of towns turns out to
have no square, if the gzip budget is exceeded, or if a town falls outside the
India box. `--check` reproduces the committed file byte for byte.

#### The search box and the location button

- The box shows **what is being shown** after any pick: `Chennai`,
  `28.50 N 77.25 E`, or `Your location: square 28.50 N 77.25 E`. It falls back
  to that text whenever the reader is not in the middle of typing.
- The placeholder is `Search a town, or type lat, lon`, and names no real
  town: `Delhi, or 28.5, 77.25` reads like a value rather than an example.
- `No town in the list starts with "…"` appears **only after something has
  been typed**. It used to appear with an empty string in it.
- **Use my location** is unchanged in what it sends — the fix is rounded to
  its square in the page and only the square's centre is ever requested — and
  changed in what it says. The reader is told the square, never the fix, in
  the box and in the panel. A town is named only when the square is exactly
  that town's own square, from the page's own list. There is no reverse
  geocoding and no third-party service of any kind.

#### Tests

`tests/test_api_consistency.py` gains 13 tests, **256 in the suite**. The
export harness now passes its arguments through a file: Windows caps a command
line at about 32,000 characters and the town list alone is 15,000, so passing
it as an argument failed outright.

`build_towns.py --check` compares with line endings normalised. This
repository stores LF and `core.autocrlf` is on, so a fresh clone on Windows
holds the same file with CRLF in it and a byte-for-byte comparison would fail
for a reason that has nothing to do with the data. Every byte that says
anything is still compared. (`build_outline.py --check` has the same latent
problem and is left alone here: it is not part of this change.)

| What | How it was shown to bite |
|---|---|
| the page and `api/place` tell the same island story | one number changed in `api/place`'s copy |
| the island sentences judge nothing | `so a dry day is likely.` put in one |
| a point in Lakshadweep is not called the open ocean | through the real function, against the test store |
| every town resolves to a square or says why | a mainland town marked `not_forecast` |
| the list holds nothing finer than a square | a town moved to 27.33 N |
| an empty search box matches nothing | `findTowns` made to return everything again |
| a square with two towns names both | made to name only the first |
| the sea is not the colour of the 0 class | `SEA` put back to `#eaf0f4` |
| the sentence under the counts is the new one | the count made to change it |
| every class's ink can be read on it | it already failed: `#ffffff` on `#1d91c0` is 3.58 |

#### What HC8 must now do

11.25 stands, with two additions, because two of the things it samples have
moved:

1. **HC8 must not sample the selection.** The ring and its white halo are a
   mark, not a measurement, and they are drawn over the square they mark. HC8
   samples squares with nothing chosen, which is also the page's default
   state, and the check fails if `picked-centre` holds a feature when a pixel
   is read.
2. The legend bucket HC8 compares against is now read from the bar rather than
   from an overlay on the map. The five things that must agree are unchanged:
   the map colour, the legend bucket, the panel count, `/api/place` and the
   store byte.

The basemap assertions of 11.25 are unchanged: `SLOT_BASEMAP` must hold no
layer and `SQUARE_OPACITY` must be 1 at the moment a pixel is sampled.

#### What this does not change

The run, the counts, the mask, the tiles, the publishing, the workflow, the
verification, `pipeline/` and `scripts/` other than the new `build_towns.py`.
The outline and state-line decisions of 11.14 stand exactly as approved, and
`web/src/geo/` is untouched.

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
12. Tiers and acceptance tests

**Section 11 is drafted and approved in two parts.** Part one, 11.1 to
11.11, is the plain page with `api/health` and `api/place`, live since 12
November 2026. Part two, 11.12 to 11.27, is the map and the real site,
approved the same day. The track record pages and the display rules that go
with a "Good track record" label are section 6, after the verification of
section 5 has run.

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
