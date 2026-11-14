# SPEC.md

India precipitation forecast website.

Status: sections 1-4 drafted and revised 12 November 2026, with all five open
questions resolved. Sections 5 and 6 decided 12 November 2026, with the decisions the
code needed added 13 November 2026 as 5.11 and 6.9, before any
verification output existed. Sections 7-12 to
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

Checked on 12 November 2026 against the real URLs and the real index files,
and **corrected on 13 November 2026 by HC-ECMWF**, which found that the
12 November reading of the `ep` row was wrong:

| Product | Available? |
|---|---|
| `aifs-ens` / `enfo` / `cf` | yes, about 58 MB per step |
| `aifs-ens` / `enfo` / `pf` | yes, about 2.9 GB per step for all parameters |
| `aifs-ens` / `enfo` / `ep` (probabilities) | **yes**, two files per run |
| `aifs-ens` / `enfo` / `em`, `es` (mean and spread) | yes, inside the `ep` files |
| `aifs-ens` / `enfo` / `ef` | no, HTTP 404 |
| `aifs-ens` / `waef` / `cf` and `pf` (waves) | yes, not used here |

The `pf` index lists 29 parameters, with `tp` the only precipitation total and
no threshold-probability parameter such as `tpg1` or `tpg10`. **[verified]**

What was missed on 12 November is that the probabilities are not in the `pf`
files and are not named per step. The whole set for a run sits in
`...-240h-enfo-ep.grib2` and `...-360h-enfo-ep.grib2`, named for the end of
their range, and a listing that walks the steps never shows them. Inside the
first are `tpg1`, `tpg5`, `tpg10`, `tpg20`, `tpg25`, `tpg50`, `tpg100` and
more, as percentages, for 24-hour windows including 24-48, which is our day
1. **[verified]** by HC-ECMWF on run 20261112T00Z.

So **there is an official AIFS ENS probability of 10 mm, and HC-ECMWF
compares our counts against it**. It is not a count of members -- it holds
values far below one member's worth of 51 -- so the two cannot be made equal
by arithmetic; what HC-ECMWF measures is how closely they agree. HC6's
member-by-member dump stands as the check of the counting itself.

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

**Amended 13 November 2026 (11.30).** The map now shades the land around
India as well, from `ne_10m_land`, so that Nepal and Bangladesh do not read
as ocean. That layer is coastline and nothing else: it holds no border of any
kind, which is why it is the layer used. The sentence above still holds in
full — the India point-of-view outline is the only national boundary this
site draws, the shading carries no line, and it is painted **under** India's
own fill, so the country still ends exactly where the outline says it does.
Which squares are in the mask is untouched by it.

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
probabilities. On 12 November 2026 it was recorded here that there are none
to compare against: the only AIFS ENS products seen in the 0.25 degree
`enfo` stream were `cf` and `pf`, with `tp` the only precipitation total in
the `pf` index.

**That was wrong, and HC-ECMWF found it on 13 November 2026.** ECMWF open
data does publish `tpg10`, "Total precipitation of at least 10 mm", for AIFS
ENS, as a percentage, for 24-hour windows including 24-48 hours, which is
our day 1. The earlier check missed it because the probability fields are
not one file per step like `cf` and `pf`: the whole set sits in two files
per run named for the end of their range, `-240h-enfo-ep.grib2` and
`-360h-enfo-ep.grib2`. The comparison is in HC-ECMWF and its result file,
and the short answer is that their number is **not** a count of members --
it holds values far below one member's worth of 51 -- while agreeing
closely with ours square by square. We publish a count and call it a count,
and no other model is substituted anywhere.

HC6 dumps all 51 members, and the precision point still applies to it: a member whose stored total sits within about a quarter of a
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

### 5.11 Decisions fixed 13 November 2026, before any result

Section 5 left these to the code. They are settled here, **before
`pipeline/verify.py` existed and before any real score was produced**, and
nothing below was chosen after seeing a number.

#### Cases and pairing

| # | Rule |
|---|---|
| 1 | The forecast side is **recomputed** from `data/india/ecmwf/<date>.npz` with the same daily-total and threshold code `pipeline/ecmwf_process.py` uses. Pile A was never published, so there are no stored counts to read |
| 2 | A case exists only when the IMERG file for `R + n` is present. Absent IMERG dates exclude those cases under their own reason and are listed |
| 3 | `verify` re-reads `complete_fraction` and asserts `rain` is NaN exactly where the fraction is below 0.90. Two expressions of one rule, so a silent change upstream is caught |
| 4 | The observed side uses the same "greater than or equal to" of 4.2, on the remapped value, with no epsilon. The event is the same event on both sides |

Measured 13 November 2026: Pile A holds 177 dates, 20260513 to 20261105, with
no gaps; Pile B holds 181 dates, 20260514 to 20261110, with no gaps. The last
run date's day 5 is 20261110, so **every one of the 885 run-lead pairs has its
IMERG date**. Rule 2 exists because that stops being true the moment Pile A
grows.

#### Exclusions

| # | Rule |
|---|---|
| 5 | A run date is usable when its `.npz` and its done record both exist. Anything else is listed by date with its reason |
| 6 | Coastal squares (3.5) are **in** the headline numbers -- they are India squares -- and everything is rerun inland-only as a sensitivity. A label that changes between the two is disclosed next to it |
| 7 | `possible = dates x 5 x 4,613 x 3`, and `used + excluded == possible` is asserted, with `excluded` split by reason. An identity is the only proof that nothing was dropped quietly |

#### The reference

| # | Rule |
|---|---|
| 8 | A reference group whose observed rate is 0 or 1 keeps its cases; they add 0 to the reference Brier sum. A **group** whose reference sum is 0 has no skill number at all: it is reported as undefined and labelled "Not enough past data", because `1 - x/0` is not a number and a reference that was never wrong is nothing to beat |
| 9 | Plain in-sample: a case is inside its own reference group, with no leave-one-out. 5.3 wants the best constant forecast for exactly those cases |
| 10 | No minimum size for a reference group. The distribution of group sizes and the smallest one are published |
| 11 | The month key is the calendar month, 1 to 12, not year and month. The sample is one year, so the two are identical |

Rule 10 has a consequence, and it is stated on **How we checked** in these
words:

> Some reference groups are small -- a square in November has only six to ten
> days behind it -- and a small group's own average fits its own days closely,
> which makes it harder to beat. Where that happens our skill is if anything
> understated.

#### The bootstrap

| # | Rule |
|---|---|
| 12 | The seed is `numpy.random.default_rng(20261112)`, the date sections 5 and 6 were fixed. It is recorded in `verification_meta.json`, and a seed declared before results cannot be shopped for |
| 13 | **One** set of 1000 date draws, from the full Pile A date list, reused for every group and every sensitivity. A drawn date that contributes nothing to a group adds zeros. This makes ranges comparable across groups and across 8, 10 and 12 mm |
| 14 | `numpy.percentile(..., method="linear")`. The half-width of 6.2 is `(p97.5 - p2.5) / 2` |
| 15 | A resample whose reference sum is 0 is discarded and counted. If more than 1% are discarded the group is "Not enough past data", because a percentile over undefined values is not a range |
| 16 | Condition 2 of 6.2 is strict (**above** 0); condition 3 is not (**0.10 or less**) |
| 17 | BSS carries a 95% range and decides labels. BS carries one too and is shown only |

#### Reliability buckets

The ten middle buckets of 5.6 land on exactly five counts each, because
`k/51 < 0.1` is `k <= 5`, `k/51 < 0.2` is `k <= 10`, and so on to the top:

| Bucket | `k` |
|---|---|
| none | 0 |
| the ten middle buckets | 1-5, 6-10, 11-15, 16-20, 21-25, 26-30, 31-35, 36-40, 41-45, 46-50 |
| all | 51 |

Twelve buckets, published as that table of `k` rather than as edges, so no
floating-point tie decides which bucket a case is in.

| # | Rule |
|---|---|
| 18 | A bucket's "mean forecast" is the mean of its own cases' `k/51`, never the midpoint of the bucket |
| 19 | A bucket belongs to one region x lead day x threshold group, the same group as the label. A bucket with no cases is drawn as a gap with a count of 0 |
| 20 | A group with **no counted bucket** under 6.4 **fails** condition 4 and cannot be green. "Every counted bucket is within 0.10" is otherwise true of no evidence at all, which is the easiest way for a wrong label to get through |

#### Sensitivity and Tier 2

| # | Rule |
|---|---|
| 21 | 8 mm and 12 mm rebuild everything, reference and buckets included, on the same date draws. Scoring them against a 10 mm reference would mix two yardsticks |
| 22 | The 50-member card counts out of 50 over members 1 to 50 and rebuilds reference and buckets on `k/50`, where the first middle bucket holds `k` 1-4 and the other nine hold five each. It is a second card, never pooled with the first |
| 23 | The decomposition is Murphy's, `REL - RES + UNC = BS`, over the 52 exact `k/51` bins, with uncertainty from the group's own base rate. The identity is asserted to 1e-12 in float64 and **fails the run** if it does not hold |
| 24 | "Block" means two different things and they are named apart. `base_rate_2deg` and `skill_2deg` are spatial, floored to 2 degrees over the India box; `skill_by_date_block` is temporal, over consecutive runs of 30 start dates, so five of 30 and a last of 27, which is labelled short. A 2-degree block holding fewer than 20 India squares is drawn grey with its count, never hidden |
| 25 | The CRPS baseline is the observed daily totals **at that square over the 30 days ending the day before the run date**, needing at least 20 valid days; cases without them are excluded and counted. It is out-of-sample and is labelled as such, beside the Brier reference of 5.3, which is not |
| 26 | Both the plain empirical CRPS and the fair, ensemble-size-corrected CRPS are reported. The plain one is biased by ensemble size, which would otherwise confound the 51-versus-50 comparison with a real difference |

#### What is written, and where

| # | Rule |
|---|---|
| 27 | `results/` is committed, holds `verification.json`, `labels.json`, `site_summary.json` and `verification_meta.json`, and stays under about 5 MB in total, with its size reported. The per-case table is never written there; it belongs in `data/`. **`site_summary.json` is the only one the website reads**, and it is held under 100,000 bytes by a check that stops the build; the big files stay for anyone who wants to check the working |
| 28 | The SHA256 of 6.8 is taken over the file read as bytes with CRLF normalised to LF, which are the committed bytes. The working copy on this machine is CRLF, and a hash of it would never match anywhere else |
| 29 | `verification_meta.json` adds to the list in 6.8: the seed, the number of resamples, the percentile method, the IMERG date range, the SHA256 of the admin-1 file and of `config/india_mask.json`, the git commit, the UTC time of the run, and the exclusion tally by reason |
| 30 | Region assignment is built once into **`config/regions.json`** and committed, exactly as `config/india_mask.json` is. The Natural Earth admin-1 file lives in `data/raw/`, which is never committed, so nothing may be rebuilt from it at test time |
| 31 | Two passes over the archive: one to build the reference, one to build the per-date rows. All accumulation in float64 and every number rounded to 6 decimal places on write, so two runs give byte-identical files |

#### Added 13 November 2026, after the first results and deciding nothing

The labels were already fixed by the rules above when these were written, and
rerunning with them changed no label, no skill score and no bucket.

**The frequency check.** Per region x lead day x threshold, and for all India
together: the mean of `k/51` over a group's cases, the share of those cases in
which the event was observed, and the first over the second. Above 1 the
wording is

> the model says this much rain more often than the satellite sees it

and below 1 the same sentence with "less". It is in `verification.json` and in
the site file. **It decides nothing.** No label depends on it; it is there
because it is the plainest thing that can be said about a forecast and the
easiest for a reader to check.

**CRPS is now computed** (5.7, Tier 2), in both the plain and the fair form,
against the baseline of rule 25. The fair form is what the skill score uses,
because the plain one is biased by ensemble size and the 51-against-50
comparison would otherwise read that bias as a difference. `crps_compared` is
true, and the disagreement flags of 6.9 rule 3 are published beside the
labels.

**Still not computed**, and said so in both files rather than left to be
assumed: the CORP isotonic diagnostic and the high-`randomError` sensitivity,
both Tier 2. Nothing on the site may mention either until they exist.

#### The period, on everything

This sentence appears on every label, every score, every diagram and in both
JSON files:

> Track record from ECMWF AIFS ENS 00 UTC runs of 13 May to 5 November 2026,
> checked against NASA IMERG Late V07C for 14 May to 10 November 2026. 177
> runs over six months, most of them monsoon, so it says little about winter.

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

**What "the event was observed" counts, exactly.** Within the group's own
usable cases: a start date counts towards the third condition when at least
one case of that group, from that date, had an observed value of 1. The
threshold is the group's own threshold. There is no separate notion of a
"heavy rain day" anywhere in this specification -- the event is always "the
square-average daily total reached this group's threshold" (5.1) -- so
nothing here rests on an undefined word.

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

### 6.9 Decisions fixed 13 November 2026, before any result

| # | Rule |
|---|---|
| 1 | All **60** groups -- 4 regions x 5 lead days x 3 thresholds -- appear in `results/labels.json`, each with its label, the outcome of all four conditions of 6.2 and the numbers behind them. A group with nothing to say reads "Not enough past data"; it is never simply absent |
| 2 | When CRPS has not been computed, `crps_compared` is `false` and the site says nothing about CRPS at all. A check that did not run is never implied |
| 3 | CRPS has no threshold, so "if CRPS disagrees" (6.1) means this: at one region and lead day, one of CRPSS and BSS has its 95% range above 0 and the other does not. It is disclosed beside the label; the label still follows Brier |

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

**Amended 13 November 2026: a second schedule, `23 12-22 * * *`.** Eleven
more attempts, 12:23 to 22:23 UTC, hourly, on top of the twelve above.

The reason is what happened on 12 November 2026: **not one of the twelve
scheduled attempts ran at all.** The only run of the day started at 17:44
UTC, nearly six hours after the window closed, and the publish of
`20261112T00Z` that the site is serving came from it. The window was not too
early or too late; it was simply skipped.

GitHub documents that scheduled workflows may be delayed during periods of
high load and that a run may be dropped entirely. A window five and a half
hours wide can therefore be missed whole, and a forecast site that publishes
nothing that day has no honest way to describe itself. Covering the day to
22:23 UTC makes a single skipped hour harmless: the next attempt is an hour
away, and once the run is published each remaining attempt costs one listing
check and exits 0 (8.10). Nothing else changes -- the same job, the same
concurrency group, the same token on the same two steps.

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

**Amended 13 November 2026 (11.30).** There is still no basemap and none is
planned. What has been added is one more file from the same Natural Earth
family, drawn the same way as the outline: `ne_10m_land`, the land around
India, as a single quiet fill under India's own. It was added because
everything outside the outline was painted the sea's colour, so Nepal,
Bangladesh, Myanmar and Pakistan read as ocean on a map of rain. It is not a
basemap and does not become one: no tile server, no glyphs, no sprite, no
request at runtime, no label, no road, no place and **no boundary of any
kind** — `ne_10m_land` is coastline, which is the whole reason it is the
layer used. Every one of the five reasons below still holds, including the
first: the only national boundary this map draws is still the India
point-of-view outline, and the land under it carries no line at all.

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
only while `SQUARE_OPACITY` is 1, so that nothing underneath can show
through. The land fill of 11.30 is under the squares, which is where a
basemap would go, and it changes nothing about this: at opacity 1 a square's
pixel is the square's colour whatever is beneath it. What HC8 checks is
unchanged — that `slot-basemap` holds no layer and that `SQUARE_OPACITY` is
1 — and 11.30 adds that it samples nothing from `NOT_DATA_LAYERS`. If a
basemap is ever added and that constant drops below 1, HC8's colour
comparison has to be rewritten to account for the blend, and the hand check
should fail loudly rather than quietly compare a blended pixel against an
unblended table. It therefore checks both: that the slot is empty, and that
the constant is 1.

#### What else gives the reader their bearings

| | |
|---|---|
| The squares | outside the mask there is **no feature at all**, so the coloured area is exactly the area we forecast. The 0 class is a visible pale fill (11.17), so an India square with no model runs still shows that it is a square we stand behind |
| Cities | the 20 dots of `web/src/cities.json`, drawn as small circles, no labels. Tapping or focusing one selects that square and names it in the panel. 20 labels on a phone is clutter; 20 dots is orientation. **Replaced by 11.29 and 11.30**: one named city per state and union territory, with its dot, and the names of the units themselves; `web/src/cities.json` was deleted on 13 November 2026 |
| The land around India | **added 13 November 2026 (11.30)**, `web/src/geo/land.geo.json` from `ne_10m_land`: one fill, `#dcd7cb`, no line, under India's own white. 299 parts, 34,072 bytes gzipped. Without it everything that is not India was the colour of the sea |
| The white squares inside the outline | squares inside India whose land fraction is under the 0.5 of 3.5, so there is no feature and India's own white shows through. The legend says so in one line (11.30) |
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

### 11.29 The polish round: names on the map, a visible grid, and what is said when something fails

The second reading of the built page. Thirteen things, in three groups: the
layout and the names on the map, four faults, and the documents. As in 11.28,
every one of them is recorded with what was measured, nothing about the data
or the method changes, and where this amends something an earlier part of
section 11 settled the amendment is written out.

Everything measured here was measured on the local production build serving
`web/dist` and reading the real public store, in Chrome, at two sizes: a
1,440 by 709 desktop window with a 1,060 by 536 map, and a 390 by 844 phone
viewport.

#### The title

One sentence, in the browser tab and in the page's own `<h1>`, word for word:

> India rain forecast: how many of 51 model runs say rain

On a screen 560 pixels wide or less the clause after the colon is dropped and
the title is **India rain forecast**. Nothing is lost by dropping it: the
legend in the bar says "N of 51 model runs reach 1 mm" at every width, the
panel says it again in words, and the tab keeps the whole sentence. A test
holds the two copies together and `<noscript>`'s heading as well.

#### The phone, measured before and after

A 390 by 844 viewport, the default view, nothing chosen:

| | before | after |
|---|---|---|
| header | 0 to 147 | 0 to 89 |
| controls | 147 to 368 | 89 to 254 |
| of which the legend | 53 px | 44 px |
| **the map starts at** | **367 px** | **254 px** |
| the map is | 439 px tall | 464 px tall |
| the day row | 418 px of buttons in 371 px, scrolling sideways | 371 px in 371 px |

The middle of the screen is 422 pixels down. The map used to start 55 pixels
above it, after two cards of controls; it now starts 168 pixels above it.

Nothing was removed to get there except the title's second clause. The
warning sits beside the title instead of under it, the word "Day" over the
five dates is hidden (the radio group still names itself with it through
`aria-labelledby`, which works on a hidden element), the run line is 0.7rem,
and the legend's swatches are 0.6rem tall instead of 0.8. The map's share of
the screen went from 52vh to 55vh.

**The day buttons.** Five buttons reading "Fri 13 Nov" came to 418 pixels on
a 390 pixel phone, so the row had a horizontal scrollbar and days 4 and 5
were off the edge of the screen with nothing to say they were there. The
buttons read "Fri 13" now — `dayTab()` in `Controls.jsx`, which drops the
month from the manifest's own `short_ist` and nothing else — and each takes a
fifth of whatever width there is, so the row cannot overflow however wide the
words turn out to be. The whole window, with the month, the times and IST, is
the line underneath it, unchanged, and `api/place` repeats the full label for
the chosen day in the panel. `overflow-x: auto` is gone from the stylesheet
and a test keeps it gone.

#### The names on the map

`web/src/units.json`, built by `scripts/build_towns.py` alongside the town
list, from `ne_10m_admin_1_states_provinces` and the same populated places.
36 units — `admin == "India"`, which is 28 states and 8 union territories —
8,385 bytes, 2,197 gzipped (the sizes at 11.30, after the city rule changed three of them and both Natural Earth versions were written down). Each carries:

| field | what it is |
|---|---|
| `name`, `code` | Natural Earth's own `name` and `postal`; Gujarat has no `postal` and falls back to its `iso_3166_2` |
| `lat`, `lon` | where the name is written, **inside the unit** |
| `span` | how wide the unit is, in degrees of longitude, along the line through that point |
| `city` | the one town the map labels in that unit, as the 0.25 degree square the page shows |

**Where a unit's name goes.** Natural Earth publishes a label point per unit
in its `latitude` and `longitude` fields, placed by eye, and it is used where
it is actually inside the polygon. For two units it is not — Andhra Pradesh
and Jammu and Kashmir — and those fall back to shapely's representative point
of the largest part, which is inside by construction. The script fails rather
than writes if that set of two ever changes.

**Which city.** The unit's capital where Natural Earth marks one inside the
unit's polygon, and otherwise the largest town inside it by `POP_MAX`. 34 of
the 36 are capitals. The two that are not are Punjab and Haryana, whose
capital is Chandigarh, which is a union territory in its own right and gets
its own entry; they are labelled Ludhiana and Faridabad, their largest towns.
Three capitals are much smaller than the city a reader may expect — Gujarat is
labelled Gandhinagar and not Ahmedabad, Assam Dispur and not Guwahati, Andhra
Pradesh Amaravati — because the rule is the capital first. Dispur and Guwahati
are the same 0.25 degree square in any case. The spellings are Natural
Earth's: Simla, Dehra Dun.

Both island capitals have no square to forecast (11.28): Kavaratti and Port
Blair are labelled anyway, in the quiet ink and with a hollow dot, because the
islands are there and the panel says why there are no numbers for them.

**How many fit.** Largest unit first, then one city per unit largest
population first, each tried in every placement before it is given up on: a
unit's name centred on its point and then nudged 8 or 16 pixels in each
direction, a city's name at 8 or 18 pixels on each of the four sides. A name
is drawn only if its whole box is inside the canvas, and a city's dot claims
its own 8 by 8 pixels before any name is placed, so no word is ever written
through a dot. The dot belongs to the name: where the name is hidden, so is
the dot.

| default view | unit names in full | as a two letter code | not drawn | city names |
|---|---|---|---|---|
| desktop, 1,060 by 536 map | 21 | 14 | 1 (Assam) | 8 |
| phone, 390 by 844 | 15 | 17 | 4 | 9 |

**The two letter code, and why.** A name is written across its unit, so what
decides whether it can be written at all is how much unit there is to write it
on. `span` is measured from the polygon itself — 7.58 degrees for Madhya
Pradesh, 0.10 for Dadra and Nagar Haveli and Daman and Diu — and a name may be
up to four times that wide, which lets a small state's name cross its borders
the way it does on every printed map. Beyond that it is not a name for the
unit any more but a word written across its neighbours: the first build drew
DADRA AND NAGAR HAVELI AND DAMAN AND DIU across 230 pixels of the Arabian Sea
for a union territory 7 pixels wide. Those units are marked with Natural
Earth's own two letter code until the reader zooms in far enough for the name
to fit inside them, which is the same rule and not a different one.

**This replaces the twenty city dots of 11.8 and 11.28.** `web/src/cities.json`
is no longer read by anything. It has not been deleted: it is data, and
deleting data needs approval.

#### The grid, and the mark on the chosen square

A 0.25 degree square is `(0.25 / 360) * 512 * 2^zoom` pixels across in Web
Mercator — 0.3556 at zoom 0, about four pixels at the zoom that fits India,
182 at the closest zoom. Twelve pixels is where an edge is worth drawing, so

    GRID_FROM_ZOOM = log2(12 / 0.3556) = 5.0768

decides two opposite things:

| | below 5.0768 | above |
|---|---|---|
| the chosen square | an 18 px ring, dark with a white halo, no fill | its own square outline, white casing under a dark line |
| every other square | nothing | its own edges, `#8a97a3` at 0.4 opacity, 0.5 px |

The ring is now one number rather than the exponential interpolation of
11.28: it exists only where the square is too small to see, and above that
the square itself is the mark. This amends 11.28's ring, which grew with the
square; the square's own outline does that job better.

**HC8 samples none of it.** `NOT_DATA_LAYERS` names the five layers that are
marks rather than measurements — `squares-grid`, `picked-casing`,
`picked-line`, `picked-ring-halo`, `picked-ring` — and is exported so the hand
check can assert it rather than be trusted. HC8 samples at the default view,
where the zoom is below `GRID_FROM_ZOOM` and not one of them draws a pixel,
with nothing chosen. The assertions of 11.25 and 11.28 are unchanged:
`SLOT_BASEMAP` holds no layer, `SQUARE_OPACITY` is 1, and none of the three
mark colours (`#1f2933`, `#ffffff`, `#8a97a3`) is in the palette, which a test
checks by asking the palette for its own colours.

#### The four faults

**"Your location" was written twice, and stayed.** The control under the
search box said "Your location: square 28.50 N 77.25 E. Your exact position
was not sent anywhere." and so did the panel, and the control's copy was
still there after the reader had gone on to search for Kavaratti. The panel
says it, once; the search box shows the square, as it shows whatever is being
shown (11.28); and the control now only ever reports what went wrong, and
clears that when some other place is chosen. Measured on the page: the words
"Your location" appear exactly once after a location is picked, and zero times
after searching for a town.

**A misspelling got nothing.** The search matches the start of a name and
then anything containing it, and Natural Earth's spellings are its own, so
"Shimla", "Dehradun" and "Chenai" all matched nothing at all. They are now
answered with up to three near names as buttons — "Did you mean Simla?" —
using plain Levenshtein distance with a limit that grows with the length of
what was typed: one edit for a short word, three for a long one. Nothing is
ever chosen automatically. Showing one place's numbers under another place's
name is the single worst thing this page could do, and a page that corrects
spelling silently does exactly that.

**A refused location said nothing useful.** The three failures of the
geolocation standard each get a line of their own in `web/src/messages.js`:
permission denied, position unavailable, timed out. The browser's own
`message` is never shown — it is written for a developer and differs between
browsers. A browser with no geolocation at all, or a page that is not on
https, gets the same line as "I do not know where you are".

**The map could fail silently.** Three ways: no WebGL 2, MapLibre refusing to
start, and the 325 KB chunk not arriving. The first is now asked before
MapLibre is constructed (`canDraw()`), the second is caught, and the third is
caught by the page's one error boundary, because React's `lazy` throws during
a render and would otherwise take the whole page down with it. All three end
in one line in the map's own area saying the map is not drawn and that
everything it would have shown is in words and numbers below — which is true:
the search, the panel, the five days and all 51 values come from `api/place`
and never touch the map (11.22).

`?nomap=webgl2`, `=maplibre` or `=chunk` draws the page as it is drawn for a
reader whose browser cannot show the map, which is how that case was checked
and photographed without having to find such a browser. Checked on the page:
no canvas, the message in the map's area, and searching "Chenai" still gives
"Did you mean Chennai?", which still gives 18 of 51 model runs reach 1 mm for
13.00 N 80.25 E.

**Confirmed, not changed:** where all 51 runs give the same whole number the
panel writes one line — "All 51 runs: 0 mm, which means under 1 mm" — with
"Show all 51 values" under it and the grid of 51 behind that button. Checked
at 26.25 N 81.00 E on the real run.

#### Tests

Twelve more, in `tests/test_api_consistency.py`, and ten sabotages run against
them: every one failed the test it was aimed at and no other.

| what it holds |
|---|
| `units.json` is the Natural Earth list it says it is: 36 units, a code and a span and a city each |
| every unit's city is a town in `towns.json`, on the same square, or one of the two with no square |
| no position in `units.json` is finer than a 0.25 degree square |
| the map is handed the units largest first and the cities largest first, with the span |
| a misspelling is offered up to three near names, and only ever offered them |
| the edit distance is the plain one and stops at its limit |
| each of the three location failures says a different clear line |
| each of the three map failures says the numbers are still there |
| the page asks for WebGL 2, catches MapLibre, and has an error boundary |
| the grid and the mark are named as not-data and are not palette colours |
| the tab title is the page title, word for word |
| the day button is short and the window line is not |

#### What this does not change

The run, the counts, the mask, the tiles, the publishing, the workflow, the
verification, `pipeline/`, `scripts/publish/`, `.github/workflows/` and
`config/store.json`. `web/src/geo/` is untouched; the outline and state-line
decisions of 11.14 stand as approved. The only script that changed is
`scripts/build_towns.py`, which now writes a second file.

---

### 11.30 The final polish: a map that reads like a map, and one answer at a time

Seven things, of which one was a real fault on the published page and the
rest are the map reading as a map. As in 11.28 and 11.29, nothing about the
data or the method changes, every number here was measured, and amendments to
earlier sections are written out where they belong rather than edited over.

Measured on the local production build serving `web/dist` and reading the
real public store, in Chrome: a 1,440 by 765 desktop window with a 1,060 by
570 map, and a 390 by 844 phone viewport, where the map starts 273 pixels
down (254 before the legend's new line, 367 before 11.29).

#### The fault: the panel showed another square's numbers

Reported from the page: after "use my location", the box and the ring were on
22.75 N 88.25 E, a square where no model run reaches 1 mm, and the panel went
on showing **34.50 N 74.25 E with 51 of 51 model runs** — Srinagar's square,
chosen a moment earlier.

**Reproduced before it was fixed**, on the built page, by making `/api/place`
slow for one square and then taking the path a reader takes:

| | box | panel |
|---|---|---|
| search 34.50 N 74.25 E, answer delayed 3 s | `34.50 N 74.25 E` | — |
| press "use my location" (22.75 N 88.25 E), which answers at once | `22.75 N 88.25 E` | 22.75 N 88.25 E, 0 of 51 |
| the delayed answer arrives | `22.75 N 88.25 E` | **34.50 N 74.25 E, 51 of 51** |

The first attempt at reproducing it did not: typing a second search while the
first was loading does nothing, because the Show button is disabled while
`busy`. "Use my location" is not, which is how two requests get into the air
at once and why the report came from that path.

**The fix is two rules, in `web/src/answers.js`, and both are needed.**

| | |
|---|---|
| a ticket | every request is numbered when it is sent; an answer is used only if its number is still the latest |
| the square | an answer is used only if `square.asked` — what was sent to `api/place` — is the square chosen now |

The ticket catches two requests crossing. The square catches everything else:
a retry, an answer to a request made before the reader moved on, a square
chosen while nothing was in flight. `square.asked` rather than `square`,
because the answer for a sea square is the land square one step away (11.7)
and that is not a mismatch.

Two more changes come with it:

- **The old numbers go the moment a new square is picked**, before the
  request is sent, and the panel says `Loading 22.75 N 88.25 E…` with the
  square named. Nothing stale is on the screen while an answer is on its way.
- **`Panel` refuses to draw numbers whose square is not the chosen one**,
  whatever reaches it. The same rule in a second place, because it is the one
  rule this page cannot be allowed to break.

Checked after the fix, the same three steps: the delayed answer arrives and
the panel still reads 22.75 N 88.25 E, 0 of 51.

#### The names on the map, in the other order

11.29 placed the 36 unit names first and fitted cities around them, which
gave 21 unit names, 14 codes and **eight city names** on a map whose point is
the places people look for. The order is now the chosen square, then the
cities largest first, then the units in what is left.

| default view | city names | unit names in full | as a code, in a gap | as a code, over something | not drawn |
|---|---|---|---|---|---|
| desktop, 1,060 by 570 map | **26** | 12 | 18 | 6 | **0** |
| phone, 390 by 844 | **24** | 2 | 25 | 9 | **0** |

**No unit is ever left unlabelled.** 11.29 left Assam with nothing at all. A
unit whose name does not fit is offered its two letter code in 25 placements
— eight directions at three distances, and the point itself — and if none of
those is clear the code is written anyway, in whichever of those 25 covers
the least of what is already there, clamped inside the canvas. Six units
needed that at the desktop default view: KA, TN, NL, DL, PY and CH. Two
letters over a colour is a worse map than two letters in a gap, and no label
at all is worse than either.

#### Which city a unit is labelled with

**The capital, unless the largest town inside the unit has more than three
times its population**, by Natural Earth's own `POP_MAX`. Three units change:

| unit | was | is | populations |
|---|---|---|---|
| Gujarat | Gandhinagar | **Ahmedabad** | 195,891 against 5,375,000 |
| Assam | Dispur | **Guwahati** | 16,140 against 983,000 |
| Delhi | New Delhi | **Delhi** | 317,797 against 15,926,000 |

Three times is wide enough that a capital merely smaller than a neighbour
keeps its label: Bhopal over Indore, Lucknow over Kanpur, Thiruvananthapuram
over Kochi, Raipur over Bhilai, Ranchi over Jamshedpur. 31 of the 36 cities
are now their unit's capital; the other two of the five are Punjab and
Haryana, whose capital Chandigarh is a union territory in its own right.

**Andhra Pradesh does not change, and was expected to.** Natural Earth's
`POP_MAX` is the figure for the built-up area, and it calls Amaravati
5,800,000 — the capital region around Vijayawada and Guntur — against
Vishakhapatnam's 1,529,000. So Amaravati is not merely the capital there, it
is also the largest by the field the rule is written on. The field this
project uses for size everywhere else is the one the rule is applied to;
switching to `POP_MIN` to move that one label would put Amaravati at 103,000
and Vishakhapatnam at 1,063,178, and it would also put Guwahati at 17,516,
which is worse. If Vishakhapatnam is wanted there it has to be a named
exception, and that is a judgement, not a rule.

#### The land around India

Everything outside the India outline was painted `#aec6da`, the sea, because
the page drew no land it has no squares for. Nepal, Bangladesh, Myanmar, Sri
Lanka and Pakistan were ocean.

`web/src/geo/land.geo.json`, from `ne_10m_land` version 5.1.1, public domain,
downloaded by `scripts/build_outline.py` against its sha256
`e547d749445eaa0964aba76738090ec88f5e63c4585122170f98c67a7ea922dc`:

| | |
|---|---|
| what it is | coastline and nothing else. `ne_10m_land` holds no boundary of any kind, which is why it is the layer used |
| clipped to | 28 E to 138 E, 18 S to 52 N — the box `maxBounds` lets a reader pan to, which a test holds against `LIMITS` in Map.jsx |
| simplified to | 0.05 degrees, about 5.5 km, written to 2 decimal places |
| islands dropped | 2,029 parts under 0.01 square degrees, about 120 km2, totalling 2.958 square degrees. India's own islands are not affected: they come from the outline, which is not filtered |
| what is left | 299 parts, 6,788 points, 127,616 bytes, **34,072 gzipped**, in the map's chunk and not the first one |
| drawn as | one fill, under India's own white fill, with **no line on it at all** |

**The three colours, and why they are only so far apart.**

| | hex | relative luminance |
|---|---|---|
| the sea | `#aec6da` | 0.5445 |
| the land around India | `#dcd7cb` | 0.6813 |
| a square no model run reached | `#eceff1` | 0.8592 |
| a square inside India that is not forecast | `#ffffff` | 1.0 |

| pair | contrast |
|---|---|
| land against sea | **1.230** |
| land against the 0 class | **1.243** |
| land against a white square | 1.436 |
| sea against the 0 class (11.28, unchanged) | 1.519 |

A colour between the sea and the 0 class can be at most the square root of
their product from both, which is **1.237**; this one is 1.230 and 1.243, as
near that limit as makes any difference. Lightness alone could not carry it,
so the land is warm against a cool sea and a cool grey class and the hue does
the rest. The coast of India keeps its own line (`#8fa0ad`), so the 0 class
and the land never meet without one between them.

This amends 3.5 and 11.14, both written out in those sections. There is still
no basemap.

#### The white squares, explained

A square inside the outline whose land fraction is under the 0.5 of 3.5 is
not forecast, so no feature is drawn and India's own white shows through.
Those squares were a hole in the map with nothing to say what they were. The
legend now carries one more line, at every width:

> **White:** inside India but not forecast at this grid size

#### `web/src/cities.json` is deleted

The twenty city dots of 11.8 were replaced in 11.29 by one named city per
state and union territory, and nothing had read the file since. Checked
before deleting it, on 13 November 2026:

| checked | result |
|---|---|
| every `.js` and `.jsx` in `web/src` | no import, no mention |
| `api/*.mjs` | no mention |
| `tests/*.py` | no mention |
| the built bundle | `Cherrapunji`, a name in that file and in no other, is not in `web/dist` |
| `README.md`, `CLAUDE.md`, `CREDITS.md` | no mention |
| `SPEC.md` | **five mentions**, in 11.8, 11.18, 11.20, 11.23 and 11.28, all of them history: what the file was and what was decided about it. They stay, and 11.14's table now says where it went |

A test keeps it that way: the file does not exist and no source file names it.

#### Tests

Nine more, and eleven sabotages run against them — every one failed the test
it was aimed at and no other.

| what it holds |
|---|
| a stale answer is refused, by ticket and by square, and nothing half-formed is guessed at |
| two squares are the same square only when they are |
| the page clears the old numbers before asking, and the panel checks the square it is drawing |
| the three times rule, the three units it moves and the five it deliberately leaves |
| the land file is polygons with no properties, covers the whole pannable box, and fits its budget |
| the land, the sea and the 0 class are three colours, as far apart as the arithmetic allows |
| the white squares have their line in the legend |
| cities before states, and no unit left unlabelled |
| `cities.json` is gone and nothing looks for it |

#### What this does not change

The run, the counts, the mask, the tiles, the publishing, the workflow, the
verification, `pipeline/`, `scripts/publish/`, `.github/workflows/` and
`config/store.json`. `web/src/geo/india.geo.json` and `states.geo.json` are
byte for byte what they were.

---

### 11.31 A name belongs to one state, and a swatch is not a tick box

Two things, both seen on the built page. The first is the only kind of
mistake this map cannot make and still be a map: a word in the wrong place.

Measured on the local production build serving `web/dist` and reading the
real public store, in Chrome, in an iframe of a fixed size so that the same
view can be measured before and after: a 1,440 by 765 viewport with a 1,060
by 572 map, and a 390 by 844 phone viewport with a 390 by 464 map.

#### The fault: state names written across other states

Seen on the page. On the phone, HIMACHAL PRADESH was written across
Uttarakhand and ARUNACHAL PRADESH across Bhutan and Sikkim; on the desktop,
JAMMU AND KASHMIR began outside the outline altogether and UTTARAKHAND hung
over Nepal. 11.29 let a name hang over the unit by its own width again on
each side, and nudged it up to sixteen pixels to dodge a clash -- which at
the whole-India view is half a degree, the width of a small state.

How wrong the four of them were, measured against the Natural Earth polygons
by the word's own box at the desktop default view:

| the word | outside the unit it names | and it reached into |
|---|---|---|
| UTTARAKHAND | 49.4% | Uttar Pradesh, Himachal Pradesh, Haryana, Punjab |
| JAMMU AND KASHMIR | 70.8% | Himachal Pradesh, Ladakh, and 29.0% of the box over Pakistan |
| HIMACHAL PRADESH | 64.5% | Punjab, Uttarakhand |
| ARUNACHAL PRADESH | 56.5% | no other Indian unit: 51.0% of the box over China, 4.1% over Myanmar, 1.4% over Bhutan |

An Indian state's name written across Pakistan and China is not a label that
needs tidying. It is the one thing a project that draws only the India
point-of-view outline (11.14) must not do, and it was on the page.

#### The rule

**A unit's full name is drawn at the unit's own label point, centred, with no
offset of any kind, and only when the whole label box is inside the unit's
own polygon at the current zoom. Everywhere else the unit is marked with its
two letter code**, which may still look for a gap in the 25 placements of
11.30 and is still written anyway if there is none, so no unit is ever
unlabelled.

The box is the word's own box as the browser laid it out, line box and all,
unprojected back to degrees. Nothing smaller is tested: the test is about
where the label is, not where the ink is.

#### How the page knows, without the polygons

The polygons are 3 MB of shapefile and the page has no other use for them.
So the question is answered where the polygons are -- in
`scripts/build_towns.py` -- and `web/src/units.json` carries the answer.

A label box is centred on the label point, so boxes of one shape nest: if a
box of some height fits inside the unit, every shorter box of the same shape
fits too, and there is a tallest one that does. One number settles each shape.

| | |
|---|---|
| shapes measured | width over height in degrees: 2, 4, 6, 9, 13, 18 and 25 |
| what is stored | `fit`, half the height in degrees of the tallest box of each shape, centred on the label point, that is `within` the polygon |
| how | binary search over shapely's `within` to a tenth of a second of arc, at the **rounded** label point the page itself uses, then floored to four decimal places -- never rounded up, because a number rounded up is a box the polygon does not contain |
| how the page reads it | `web/src/fits.js`: the shape asked about is rounded **up** to the first shape measured, so the box tested is at least as wide as the box drawn; wider than 25 to 1 and there is no answer, so the answer is no |
| the cost | units.json goes from 8,385 bytes to 12,123, and from 2,197 gzipped to 3,299, in the first chunk. The budget in the build script goes from 2,500 to 4,000 |

`span` -- the unit's width in degrees at the label point, which 11.29 added
and which the overhang rule read -- is gone from units.json, from
`unitlist.js` and from the map. A width was never the question. A box inside
a polygon was.

#### What it costs, and what it buys

| default view | before: full names | codes | forced codes | after: full names | codes | forced codes | city names |
|---|---|---|---|---|---|---|---|
| desktop, 1,060 by 572 map, zoom 3.28 | 12 | 18 | 6 | **0** | 31 | 5 | 26 |
| phone, 390 by 464 map, zoom 3.00 | 2 | 25 | 9 | **0** | 29 | 7 | 24 |

**No state name is drawn at either default view, and that is the true
answer.** At the whole-India view a word 14 pixels tall is 0.78 degrees tall
and MADHYA PRADESH is 6.9 degrees wide; the tallest box of that shape which
stays inside Madhya Pradesh is 0.72 degrees. The word is bigger than the
state. Two units do have room at the desktop default view -- Rajasthan and
Odisha -- and both lose their one placement to a city label, because cities
are placed first (11.30) and the capital is usually near the middle of the
unit, which is also where the unit's name goes.

Names come back as the reader zooms in, which is the point of "at the current
zoom". Three zoom steps in from the desktop default view, at zoom 5.28:
**ODISHA, CHHATTISGARH, WEST BENGAL, HARYANA and MEGHALAYA**, and eleven more
that now fit inside their unit but lose the place to a city.

Every unit still carries at least its code at both default views: 31 + 5 and
29 + 7 are both 36.

#### The second thing: swatches that looked like tick boxes

The legend's white swatch and the swatch in each panel row were 0.95rem
squares with a hairline border and a 2px radius, which is what an empty
checkbox looks like in every browser there is -- and the panel one sits
inside a row that really is a radio button, so it read as a tick box that
would not tick.

| | |
|---|---|
| shape | 1.5rem by 0.6rem, square cornered: a colour chip, not a control |
| pointer | `pointer-events: none`, so a click goes to whatever is behind it |
| reading order | `aria-hidden="true"` on all four, because the words beside them carry the meaning |
| focus | they are `span`s with no handler and no `tabIndex`, as they always were |

The one round swatch stays round and says why in the stylesheet: it is the
key to the round dots of the 51 runs.

#### One more fix, found while measuring

The label count changed from one load of the same page at the same size to
the next: 26 city names on one load and 31 on the next. A word's width is
measured once and kept, because reading it back forces the browser to lay the
page out again and doing that on every frame of a drag is the one thing here
that could be slow -- but the first draw happens while the map is still being
fitted and flexbox is still sizing, and a width measured then was kept for
the rest of the page's life. The words are measured once more when the map
goes idle, and again when `document.fonts` is ready. Three consecutive loads
now give the same counts and the same zoom to four places.

#### Tests

Seven more, and eight sabotages run against them.

| what it holds |
|---|
| every unit has a fit table, of the right length, that never rises as the box widens |
| every number in every fit table is a box inside the unit's own polygon, and a box a tenth taller plus one rounding step is not |
| every unit name the built page actually drew, at three recorded views, is inside the unit it names |
| the shape of a box is rounded up and never down, and anything wider than the widest shape measured is refused |
| the map offers a name one placement and only one, after the box test, and the overhang rule is gone |
| a swatch is a chip, not a control: shape, pointer-events, aria-hidden, no handler |

`tests/sample/names_on_screen.json` is the boxes themselves, recorded from
the page, because only a browser knows how wide a word came out. What they
are checked against is the polygon. Three of the eight sabotages were edits
to `units.json`, and each of those failed the test it was aimed at **and**
the check that the committed file is what the build script writes, which is
the right answer for a built file edited by hand.

#### What this does not change

The run, the counts, the mask, the tiles, the publishing, the workflow, the
verification, `pipeline/`, `scripts/publish/`, `.github/workflows/` and
`config/store.json`. No colour, no wording and no number in the panel. The
three geometry files in `web/src/geo/` are byte for byte what they were.

---

### 11.32 The square you chose is the square you see

Choosing a place and not being shown it is the oldest fault a map can have,
and the page had it three ways. A town searched for while the map was
somewhere else stayed off the edge of it. A square at the very edge had its
ring half drawn. And on a phone, choosing anything opens the bottom sheet,
which takes the map from 464 pixels tall to 236 -- so a square in the lower
half of the map was, a moment later, below the bottom of it.

**After a square is chosen the map pans, by as little as will do, until the
square is comfortably inside the part of the map a reader can actually see.
The zoom never changes.**

| | |
|---|---|
| comfortable | at least `EDGE` = 40 pixels inside every edge of the visible box |
| where it lands | `REST` = 80 pixels inside the edge it was outside, or the middle of that axis if there is not room for both margins |
| why REST is twice EDGE | a square one pixel outside the box would otherwise slide the map by one pixel, which is an animation with no point. Every move is worth making, and a square already comfortable still never moves |
| how it moves | `panBy`, 600 ms. Not `flyTo` or `fitBounds`: the zoom is the reader's, or the fit's, and a map that changes scale every time a town is searched for is a worse map than one that pans |
| reduced motion | `prefers-reduced-motion: reduce` makes it 0 ms. The map is where it has to be; it simply arrives without the journey |
| when | whenever the chosen square changes -- search, did you mean, a click on the map, use my location -- and again whenever the map changes size |

**The visible box is not the canvas.** The canvas is not always all on the
screen: the page can be scrolled, and on a phone the sheet takes the lower
part of the window. `visibleBox` clips the canvas rectangle to the window and
puts it back in canvas coordinates, and everything is measured against that.
So a square under the sheet is out of view however firmly the canvas says it
is there.

**It has to survive the refit.** Choosing a square opens the sheet, which
resizes the map, and the resize watcher refits India (11.16). On a phone that
refit cannot help: India does not fit in 390 by 236 pixels at the minimum
zoom of 3, so the south of the country is simply off the map. So the watcher
brings the chosen square back after it refits -- and it does that even when
the reader has moved the map themselves, which the refit deliberately does
not, because this only ever pans and does nothing at all while the square is
already comfortable.

Measured on the local production build:

| | before | after |
|---|---|---|
| phone, 8.50 N 77.00 E searched | y = 439.3 of a 464 pixel map | the sheet opens, the map is 236 tall, y = **156.1**, which is 236 - 80 |
| desktop, 28.75 N 77.25 E searched at the whole-India view | in view | **the map does not move at all**, zoom 3.2763 either way |
| desktop, 8.50 N 77.00 E searched from a northern view at zoom 4.6553 | south edge 17.77 N, the square off the bottom | south edge 6.29 N, the square in view, **zoom 4.6553 unchanged** |

A town the grid cannot carry -- Kavaratti, Port Blair (11.28) -- marks no
square, so there is nothing to bring into view and the map does not move. The
panel says why there are no numbers, which is the answer to that question.

#### Tests

Four, over `web/src/inview.js`, which has no imports so `node` can drive it:
a square in the middle of the desktop map and squares exactly 40 pixels in
are left alone; squares off the left, off the bottom right, and inside the
margin are moved, and the answer puts them inside the margin rather than on
it; a square under the sheet is out of view in the clipped box and in view in
the whole one; a map too short for two margins centres the square instead of
giving up; and the map pans with `panBy` at 600 ms, jumps under reduced
motion, and changes the zoom nowhere.

---

### 11.33 The trust label in the place panel

The track record is frozen (6.8, tag `results-v1`). This is the first thing
the site does with it: beside every count, what happened the last time the
model said something like this.

**The one file the page reads.** `results/site_summary.json`, and nothing
else. It is copied byte for byte to `web/src/summary.json`, so the bundle
carries one copy and the build reads nothing outside `web/`; a test fails if
the two files differ by a byte. `verification.json` and `labels.json` are
never read by the site.

**The region comes from the API.** A label belongs to a region, a lead day and
a threshold, so the page must know which of the four IMD regions (5.4) a
square is in. `api/place` answers it, as `square.region` and
`square.region_code`, reading `config/regions.json` -- the one place that
assignment lives. The page keeps no second copy of it. Every square the site
can answer for has a region: the 4,613 squares of the India mask (3.5) and the
4,613 squares `config/regions.json` assigns are the same squares.

`includeFiles` in `vercel.json` widens to `config/{store,regions}.json` for
it. 11.23 dropped `nearest_city` rather than widen it for a city name; a
region is not decoration. It is the key a label is filed under, and if the
page worked it out for itself the site could show one region's record under
another region's square.

#### What the panel shows

| where | what |
|---|---|
| under the counts | the chip for the chosen day and threshold -- green, amber or grey, the label in words -- and one plain line saying why it is that colour |
| on each of the three threshold rows | that row's own small chip, because the three thresholds are three different track records and often three different labels |
| under the chosen count, at the same size as the count | the past-frequency sentence below |
| behind "Why this label?" | the four conditions of 6.2 in plain words with their numbers, the 6.5 luck sentence where it applies, the CRPS note where the two scores disagree, and the period sentence |

#### The one line under the chip

It names what went wrong, in these words and no others:

| check not passed | words |
|---|---|
| enough past cases | too few past cases |
| better than the usual rain | not clearly better than the usual rain for this place and month |
| a narrow enough range | too uncertain to tell |
| counts that matched what happened | the counts were too confident: when many runs agreed, the satellite saw it less often |

Joined in 6.2's order, the last two with "and", and ended with a full stop.
**Where the group did beat the usual rain and is amber all the same, the line
says both halves**, because leaving the good half out describes a worse record
than the one we measured:

> Better than the usual rain for this place and month, but the counts were too
> confident: when many runs agreed, the satellite saw it less often.

Where that check was not passed either, only the failed checks are named. All
four passed reads "All four checks passed."

"too uncertain to tell" is the one place the word "certain" appears on this
site, inside its opposite. The forbidden list of 11.20 bans the claim
"certain"; a confession that the range is too wide to tell is the opposite of
that claim, so the test matches the whole word.

#### The past-frequency sentence

The count's reliability bucket (5.11) for that region, lead day and threshold,
said as one sentence:

> In May to November 2026, when 36 to 40 of 51 runs said 10 mm or more in
> Northwest India on day 1, the satellite saw it about 5 times in 10.

| the two ends | 0 reads as never and 10 reads as always, which a rounded band did not earn. 0 is said as **"fewer than 1 time in 10"** and 10 as **"nearly every time"** |

| | |
|---|---|
| the bucket | the counted bucket holding this count. `k = 0` and `k = 51` have their own, and read "when none of the 51 runs said" and "when all 51 runs said" |
| the number | the bucket's `times_in_10`, which the verification rounded. The page never rounds a frequency itself |
| one time | "about 1 time in 10", not "1 times" |
| not a counted bucket | "Too few past cases with this many runs agreeing to say how often the satellite saw it." The floor of 6.4 -- 100 cases from 10 start dates -- governs what we say out loud as well as what we test |
| the satellite, always | "the satellite saw it", never "it rained" and never "came true". 5.9: the satellite is an estimate, and the strongest thing that can be said is that the forecast agreed with it. 6.7's shorthand "came true about N times in 10" names the same quantity; the page says it in full |
| a run with any other number of members | nothing is said. The bands are counts out of 51 (2.1), and a count out of some other number is not the same question |

#### Percentages

A percentage is shown only beside a **Good track record**, as "about N in 10"
with N = ten times the count divided by 51, rounded to a whole number: never
a decimal and never a percent sign. **No group is green today**, so no such line
appears anywhere on the site. The rule is written and tested against a made-up
green group, so that it is already right the day a real one appears, and the
test that no percentage appears anywhere runs against the real record.

#### Why this label?

A `<details>` under the chip, shut until it is opened. In it: each of the four
conditions of 6.2, in plain words, with the number it got and the number the
rule asks for, marked passed or not; the 6.5 sentence where the group's skill
is above 0 but could be luck; the period sentence of 5.11; and, where the
group is flagged (6.9 rule 3), that Brier and CRPS point different ways here,
said as two different yardsticks rather than as a contradiction -- one asks
whether the right number of runs crossed a line, the other asks how close the
whole spread of runs was to the millimetres that fell.

Nothing in the panel recomputes a label, a skill score or a frequency. Every
number in it was read from `summary.json`, and a test drives the page's own
functions over all 60 groups and every count from 0 to 51 and compares them
with that file.

#### Tests

Twelve. Most of them drive `web/src/record.js`, which has no imports so `node`
can run it against the real file, over all 60 groups at all 52 counts -- 3,120
answers, each one compared with `results/site_summary.json`:

| | |
|---|---|
| the label, the colour, the sentence and the four conditions | are the record's, for every group and every count |
| the sentence | is withheld exactly where the band is not counted, and nowhere else |
| a share of ten | appears for no group of the real record, and a made-up green one gets "about 4 in 10" |
| the forbidden words of 11.20 | hold over every string the label can put on the page, and every sentence says "the satellite saw it" |
| a run with other than 51 members | gets no sentence at all |
| the two ends | 0 is "fewer than 1 time in 10" and 10 is "nearly every time"; the real record reaches 0 in 79 bands and 10 in none, so the top end is driven with a band moved there by hand |
| the one line under the chip | says both halves for the 20 groups that beat the usual rain and are amber all the same, and only the failed checks for the other 40 |
| `api/place` | gives all 15,609 squares of the box the region `config/regions.json` gives them, which for 4,613 is one of the four and for the rest is none, and those 4,613 are the India mask of 3.5 square for square |
| the twelve place tests of 5.4 | answer through the function the site asks |
| a whole request | carries `region` and `region_code` for the square it answers for, agreeing with that function |
| `web/src/summary.json` | is `results/site_summary.json` byte for byte, and the only `.json` the page imports besides the towns, the units and the outlines |
| the panel | puts the sentence under the chosen count only, carries a chip on every row, and decides no label, frequency or colour of its own |

Eight sabotages, eight caught: "it rained" for "the satellite saw it", a count
with no counted band borrowing the nearest one, a share of ten without a green
label, the page rounding a frequency itself, the line naming the checks it
passed rather than the ones it did not, the region read one row further north,
the sentence shown on every threshold row, and one digit changed in the
bundled copy of the record.

---

### 11.34 The report card and How we checked

Two pages, for two readers. The report card answers "should I believe this?"
in a minute. How we checked answers "how do you know?" and expects to be
argued with.

#### Three real paths

| | |
|---|---|
| the paths | `/`, `/report-card`, `/how-we-checked`. Real paths, not hashes and not a query: they can be linked to, bookmarked and sent to a reviewer |
| the rewrite | `vercel.json` sends everything that is not `/api/...` or `/assets/...` to `/index.html`, after the filesystem. One HTML file, three pages |
| the menu | plain `<a href>` links at the top of every page, so a middle click opens a tab and the keyboard reaches them with no handler of ours. A left click with no modifier is intercepted and becomes `history.pushState`, which is what makes it a single page application rather than three downloads; `popstate` takes the reader back |
| the current page | `aria-current="page"`, and marked in the text as well as the colour |
| on a phone | the three sit in one row above the title and stay there; nothing is hidden behind a hamburger, because three links do not need a menu |

#### What each page reads

| page | file | how |
|---|---|---|
| forecast | `web/src/summary.json` | already in the bundle (11.33) |
| report card | the same file | nothing new is downloaded |
| How we checked | `web/src/details.json` | inside that page's own chunk, so a reader who never opens it never downloads it |

`results/site_details.json` is written by `pipeline/labels.py` from the frozen
`results/verification.json`, holds no number that file does not, and stays
under **150,000 bytes** by a check that stops the build. A test derives it
again from `verification.json` and compares it field by field, so the page
cannot show a score the verification did not produce. It is copied byte for
byte to `web/src/details.json`, as the summary is.

#### The report card

In this order, because a reader who stops after two things should still have
the two that matter:

1. **The period sentence**, first and whole.
2. **One plain headline.** Today: all 60 groups read "Treat as a rough
   guide", and why -- the counts were too confident in every one of them, and
   20 of the 60 did beat the usual rain for their place and month.
3. **The grid**: 4 regions x 5 days x 3 thresholds, one chip each. The chips
   use the labels' short forms -- **Good**, **Rough guide**, **Too few** --
   with the full label as each cell's accessible name and a key above the
   grid giving all three in full, because sixty chips reading "Treat as a
   rough guide" is a wall, not a grid.
4. **Skill against lead day**, per region and threshold: a small SVG of five
   points with their 95% ranges and the zero line drawn across. Headed in
   words, "better than the usual rain for this place and month", never "BSS".
5. **A pickable table**: region, day and threshold chosen by the reader, then
   every counted band -- "when 36 to 40 of 51 runs said 10 mm or more, the
   satellite saw it about 5 times in 10", the same sentence the panel says,
   from the same function. Bands that are not counted are not in the table.
6. **The frequency check**, one sentence, for the chosen day and threshold
   over all India.
7. **CRPS**, one sentence, with the different yardstick said plainly.

#### How we checked

The method as written, with the numbers beside it: what a case is and how it
is paired (5.1); IMERG Late as a satellite estimate and never ground truth
(5.9); the area-weighted remap (3.3) and the 90% completeness rule (3.4); the
hindsight reference, with the note that a November square has only six to ten
days behind it so the skill is if anything understated (5.11); the Brier skill
score pooled per reference group; the bootstrap over whole dates with its
seed; the reliability bands; and that every rule was fixed before any result,
with the commit and the SHA256 of `SPEC.md` printed on the page.

Then, each from `site_details.json`: the exact decomposition for a group the
reader picks, with `REL - RES + UNC = BS` shown adding up; 51 members against
50; the 8 mm and 12 mm and inland-only sensitivities, with the fact that no
label moved; the 2-degree base-rate and skill maps as light SVG grids, one
rectangle per cell; skill by 30-day block; CRPS with its baseline and the 25
disagreements explained as two yardsticks; the exclusion tally; the limits,
including SPEC 5.10's sub-cell offset and the two Tier 2 checks that were not
computed; and links to the repository, `SPEC.md`, all four result files and
every hand check that has been done, each linking to the file it
wrote (11.36).

#### Rules both pages keep

| | |
|---|---|
| every number | comes from `summary.json` or `details.json` and is printed as it was written there. Nothing is recomputed on the page, and the test drives both pages' own functions against the files |
| the period sentence | is on both pages, whole, as 5.11 requires of everything that shows the record |
| no percentage | anywhere, until a label is green (6.7, 11.33) |
| the forbidden words of 11.20 | hold over every sentence either page can produce |
| with JavaScript off | both paths serve the same `index.html`, whose `<noscript>` links to the result files themselves and to the specification, so a reader with no script is sent to the numbers rather than to an empty page |
| no chart library | the SVGs are written out as rectangles, lines and text. A library for twelve line charts and two grids would be 40 KB to draw 200 rectangles |

#### Tests

Thirteen. Two kinds, because two things can go wrong: a page can read the
file wrongly, and a page can be written wrongly.

`web/src/pages.js` is driven by `node` against the two real files, as
`record.js` is. And **both pages are rendered to HTML by React's own server
renderer** -- `vite build --ssr` over `web/src/ssr.jsx`, which is a test entry
nothing on the site imports -- for **every choice a reader can make**: 159
renders covering all 60 region-day-threshold choices of both pickable
sections, all 20 of the sensitivity table and all 15 of the maps. So the
forbidden words and the no-percentage rule are checked on the words that
reach a screen, not on a description of them.

| | |
|---|---|
| `site_details.json` | derived again from `results/verification.json` in the test and compared field by field; under 150,000 bytes; `web/src/details.json` equal to it byte for byte |
| every chip in the grid | is the label `site_summary.json` gives that region, day and threshold, all 60 |
| every point and whisker | in the twelve skill plots is the `bss`, `bss_lo` and `bss_hi` of its group |
| every row of the pickable table | is a counted band of that group, in order, with the panel's own sentence |
| the frequency and CRPS sentences | carry the file's own figures and no others |
| the decomposition shown | adds up to the Brier score it was taken from |
| the two maps | draw one rectangle per 2-degree cell and nothing for a cell with too few squares |
| the period sentence | appears on both pages |
| no percentage | appears on either page, for any choice a reader can make |
| the forbidden words | hold over every string either page can produce |

**And over the forecast page's own panel and bar, which they did not.** Until
13 November 2026 the sweep covered only the two strings the panel *computes*
-- the day sentence of 11.20 and the track-record answers of `record.js` --
and never its written text, which is most of what a reader reads, nor the bar
of 11.37. `ssr.jsx` now renders the panel from real `/api/place` answers in
every state it has (an answer for all five days and all three thresholds,
nothing chosen, waiting, a square still loading, both island notes and each
of the ten failure lines) and the bar's three labels with it, and the same
list and the same no-percentage rule are swept over the lot.

The forecast page has **one** word the two document pages do not: it may say
`probability`, in the two sentences that refuse the reading -- the heading
"It is not a probability." and the sentence of 11.21 under it. The allowance
is written as those sentences and not as the word, so it cannot spread: the
count of the word over the whole sweep must equal the count of those two
sentences. Inserting "certain" into How to read this map is caught.
| the menu | is three real links to the three paths, with `aria-current` on the one being read |
| `vercel.json` | rewrites everything but `/api/` and `/assets/` to `/index.html`, and nothing the built page loads depends on the rewrite |
| `<noscript>` | links to all five result files and to `SPEC.md` |

Eleven sabotages, eleven caught: a score in the details file that is not the
verification's, a short label the page invented, the whiskers upside down,
"came true" for "the satellite saw it", the frequency ratio turned over, a
menu that forgets which page is open, a rewrite that swallows `/api` too, a
`<noscript>` with the files taken out, a percentage printed beside a band, a
decomposition that adds the resolution instead of subtracting it, and a map
that quietly leaves out the cells with too few squares.

#### Found on the preview, and fixed: a missing asset answered 200

The first catch-all excluded only `/api/`, so **`/assets/does-not-exist.js`
came back as `index.html` with a 200** -- measured on the preview of `e18781b`
on 13 November 2026. A `<script src>` for a renamed or half-deployed chunk
would then be handed HTML and the browser would report a syntax error, which
says nothing about what is actually wrong. `/assets/` is excluded as well now,
so Vercel answers it from the filesystem and a missing file is a 404. A test
drives the rule over both lists, and over every same-origin link in the built
page.

#### Two things found while building, and kept

**The decomposition does not quite add up on the page, and says so.** The
identity holds exactly in float64 and the run stops if it does not (5.11 rule
23), but what is published is rounded to six decimals, and in **102 of the
300** scored groups the three rounded parts differ from the rounded Brier
score by one in the last digit. The page shows the sum and says why it can
differ, rather than hiding the rounding.

**One 2-degree cell has no skill at all.** 36 N 76 E, in the Karakoram, never
reached 10 mm on any day of the six months, so its base rate is 0 and there is
no skill to compute. It is drawn white and reads "no number" rather than being
left out of the map.

---

### 11.35 The phone viewport: the handle under the bars

**The bug.** On a Samsung A32 and an Oppo, in the browsers those phones
ship, the forecast page's "Show the details" handle sat under the browser's
bottom toolbar and the system's back and home bar. The panel could not be
opened at all, so on those phones a square's numbers were unreachable. It
did not show in a desktop browser's device emulation, which has no bars.

**The cause, measured, not guessed.** `.mapwrap` was `flex: 0 0 55vh` with a
matching `min-height`. That is a share of the **viewport**, inside a `.shell`
that is `100dvh` and has already spent the header and the controls out of
that same viewport. At 390 pixels wide the header and the controls come to
339 pixels, which is 44% of a 764-pixel screen; 55% more for the map leaves
5 pixels for the panel, and the handle is 46 pixels tall. Measured on the
built site at 390 by 664: the map ran from 339 to 704, the panel was 20
pixels tall, and the handle sat from 705 to 750 -- **41 pixels past the
bottom of a 664-pixel screen, with the shell's `max-height` stopping the
page from scrolling to it.** The bars on a real phone then make it worse in
both directions at once: `100vh` includes the area behind them, so the map
grows, while `100dvh` excludes it, so the shell shrinks. `min-height: 55vh`
is what stopped flexbox from solving it.

**The rule.** A share of the screen may be spent only on what is left of the
screen. On a phone the map's height comes out of the stage -- the box that
is left after the header and the controls -- and never out of the viewport:

| | |
|---|---|
| `.shell` | `height: 100dvh` and `max-height: 100dvh`, with the `100vh` fallback in an `@supports not (height: 100dvh)` block and **not** as a line before them |
| `.mapwrap` | `flex: 1 1 auto` with a floor of 6rem (5rem under 560 pixels). It may shrink; it may not vanish |
| `.panel` | `flex: 0 1 auto`, `min-height: 3.4rem`, `max-height: 45%` of the stage. The minimum is a little more than the handle, which is the guarantee the handle is on the screen |
| `.shell.open .panel` | `max-height: 78%` of the stage, not `none`. With `none` the panel grew past the bottom of the screen and the 51 member values could not be scrolled to |
| no viewport unit | may be used for the height of anything inside the shell |

**The fallback had to move, and the reason is a rule of its own.** It was
first written the ordinary way, a `100vh` line immediately before its
`100dvh` line. The source was right and the site was not: the minifier drops
a declaration the next line overrides, so the stylesheet actually served
carried `dvh` alone, and a browser that had never heard of `dvh` would have
had no height at all. It was found on 13 November 2026 by reading the
deployed `assets/*.css` after the merge, not by reading the source. An
`@supports` block cannot be dropped that way.

The lesson is kept as a test rather than as a note: one test now builds the
site and reads the stylesheet the build wrote, because a rule that is true in
`src/styles.css` and false in what is served is worse than no rule.

`viewport-fit=cover` is **not** set. Without it the page is laid out inside
the safe area and the bars cannot cover it; with it every edge that touches
the bottom would need `env(safe-area-inset-bottom)` padding, and the handle
is the one thing that must never be covered. If it is ever wanted for a
full-bleed map, the padding comes first.

The map resizes with the viewport because `.mapwrap` is sized by the stage
and `Map.jsx` already watches its container with a `ResizeObserver`, so
showing or hiding the address bar changes `100dvh`, which changes the
stage, which resizes the map.

**Measured after the fix, at 390 by 664.** Closed: map 339 to 518, panel 518
to 664, handle 518 to 564, fully on the screen. Open: map 339 to 419, panel
419 to 664 with 654 pixels of content in a 244-pixel box, so `overflow-y`
scrolls to the last of the 51 values. The report card and How we checked are
documents, not the shell; they use no viewport unit and were measured not to
be clipped at the same size.

### 11.36 The report card at 390 pixels, and the list of checks

**The mark.** 20 of the 60 groups beat the usual rain for their place and
month. The grid marks them with a plain `+` after the label, never by colour
alone, and never with a tick: nothing here has passed, and a tick would say
it had. The key line reads "+ better than the usual rain for this place and
month, but still a rough guide", with the number on it. The flag is read
from `site_summary.json`'s own `conditions.skill_above_zero.pass` and is
never worked out again in the page, so the mark and the label beside it
cannot disagree.

**The width.** Under 560 pixels the grid is `table-layout: fixed` at full
width, the chip words wrap rather than being cut, and the row heading keeps
"1 mm" on one line. A table that scrolls sideways hides days 4 and 5 with
nothing to say they are there. Measured at 390: the page's own scroll width
is 373 and every grid's scroll width equals its client width. Above 560
pixels nothing changes.

**The wording.** "and all 60 were too confident" when it is every one of
them, and "shown, but too few squares to give a number" for a 2-degree cell
with too few squares, which is what a dashed edge means.

**The list of checks.** How we checked carries every hand check that has
been done, one line each, each linking to the file it wrote in
`handchecks/results/`. HC4 and HC10 have no file: HC4's file was deleted
after it was read (2.6) and HC10 is the checklist for the end of the build,
listed as not done. Both link to "The hand checks" in the specification. No
file is named that is not in the repository, and no file is created in order
to be linked to.

**The ECMWF line.** How we checked carries what HC-ECMWF found, in the units
this site publishes: on the 12 November 2026 run, for day 1 at 10 mm, our
count of 51 against ECMWF's own figure at all 4,613 squares, with the gap
given as a number of runs -- the mean of the sizes of the differences, not a
signed mean, which would hide them -- and the count of squares more than 5
runs apart. Then, in those words: "This shows the counting is right. It does
not show the model is right; that is what the report card checks." ECMWF's
own word for its figure cannot be used here, because it is one of the
forbidden words of 11.20; "its own figure for 10 mm or more (the tpg10
field)" is the wording, which names the field without using the word,
with the point that it is not a count of runs said plainly beside it. This
is on How we checked only, never on the forecast page and never on the
report card.

### 11.37 The phone: a bar at the bottom, and type that can be read

Read on a Samsung A32, which is the point: 11.35 made the handle reachable
and the panel behind it was still two thirds of the screen, because shut it
carried the search box, Use my location and the whole of How to read this
map. The map, which is the page, had about a third. And the type in the open
panel, measured, was 13.4 pixels for the line that carries the answer.

#### Shut: one line and one button

| | |
|---|---|
| the bar | the whole of the panel: a grab strip, a line, and a button reading **Search**. Nothing else is in it, and nothing is under it |
| the line | before a place is chosen, "Tap the map to pick a place"; after one, that place's own result for the chosen day and amount, in the panel's words: **"Bhopal: 0 of 51 runs reach 10 mm"** |
| the button | always there, always whole, never under 44 pixels tall, at 320 pixels wide and with the longest name the town list has. The **line** is what gives way: it wraps to two lines and is cut with an ellipsis after that |
| the map | everything between the controls and the bar |
| everything else | the search box, Use my location, the counts, the dots, How to read this map: open only |

The line's words come from `barLine` in `record.js`, which is pure and has
no imports, so a test drives it directly; `summaryLine` in `Panel.jsx` finds
the place and the count and hands them over. While a newer square is still
loading the bar says the prompt rather than the last square's number: a
number under the wrong name is the worst thing this page could do (11.30).

#### One control, one job

| tapping | does |
|---|---|
| the line | opens the panel, and asks for no keyboard |
| **Search** | opens the panel and gives the search box the keyboard, ready to type |
| the map, a search result, Use my location | opens the panel on that place's result, so an answer is never hidden behind a shut bar |
| the handle, now reading "Hide the details" | shuts it again, and the map has the screen back |

The keyboard is asked for by counting up, not by a flag: `askFocus` is a
number the search box watches, so asking twice in a row works.

#### Open

The panel keeps the share of the stage 11.35 gave it -- 78%, which is right
on the A32 -- and scrolls inside itself to the last of the 51 values. The
map keeps its floor and is resized by the same `ResizeObserver` after every
open and every close.

#### Type, measured and not guessed

In the open panel, on a phone:

| | |
|---|---|
| the chosen row's count | 18.4 px, larger than everything around it |
| the three threshold rows | 15.2 px |
| the trust chip and its line | 15.2 px |
| the past-frequency sentence | 15.2 px |
| "These are counts out of 51 model runs..." | 15.2 px |
| the place line | 16.8 px |
| nothing anywhere in the panel | under 13 px |
| every button, link control and summary | at least 44 px tall |

Desktop sizes are untouched: every rule is inside a phone media block, and a
test reads the stylesheet to say so.

#### What moved, and what did not

"White: inside India but not forecast at this grid size" moves out of the
legend and into How to read this map on phones only, where there is room for
it; in the bar it cost the map a whole line. It is never in both places.

Nothing else is removed or shrunk: the run time, the published time, the
"Not an official warning" note, the day and amount controls and the colour
key are all where they were, and the parts of the footer that live in the
panel are bigger than they were, not smaller.

#### Measured, at 390 pixels wide, against the published store

| | shut | open |
|---|---|---|
| 390 x 664 | map 283, bar 61 | map 80, panel 264 |
| 390 x 844 | map 463, bar 61 | map 115, panel 409 |

#### Tests

In the browser, at 390 x 664, 390 x 844 and 320 x 568, against a small run
written and published by the test itself and served over HTTP, with the
real `api/health` and `api/place` reading it: the bar whole and the map's
floor at each size; the prompt on one line; the longest line the town list
allows put in the bar and the button measured beside it; the line, the
button and the handle each doing their one thing; a real tap on the map,
aimed with the map's own bounds, opening the panel on a square with counts,
a chip and a sentence; every font size and every tap target in the panel
that follows; and the map's own canvas back to its full height after the
panel closes. Plus, without a browser: the line's words, and the stylesheet
read to show the desktop keeps its panel.

### 11.38 Plain words on the forecast page

Three reviews and two real first-time readers said the same three things
about this page, and none of them was about the data: one could not tell
what the site was for, one did not know how to start, and all of them found
the page too textual and full of words nobody outside a weather centre
uses. The forecast is right; it was being handed over in a language the
reader does not speak.

So this section is about placement and words on the forecast page only. No
number changes, no rule changes, no new claim: the report card and How we
checked keep every sentence they had. What changes is which words this page
uses for the things it already shows, and where on the screen the answer is.

#### One name per thing

The page had four names for the 51: "model runs" in the day sentence and
the legend, "members" in the API's own field names, "model run" in the
header's run line, and "runs" in the track-record sentences. A reader who
does not already know they are the same thing has no way to learn it from
the page.

| the thing | its one name | never |
|---|---|---|
| one of the 51 forecasts | **run** | member, model run, ensemble member |
| one 0.25 degree cell | **square** | cell, grid point, pixel |
| a place in the search box | **city** | town, place, settlement |

"Run" is defined once, in the tagline and again in the welcome card — "one
weather model, run 51 times, each from a slightly different start" — and
after that it is used bare: in the legend, in the amount rows, over the
dots, and in the headline. The API's JSON keeps `members`, because that is
what the field has always been called and a reader never sees it; what is
forbidden is the word on the screen.

The day sentence of 11.20 says "model runs" and is pinned, word for word,
by its own test. It is not reworded: it is **taken off the page**, and the
headline below says the same thing in the page's own language. `api/place`
still computes it and still publishes it, so 11.20 is unchanged for anyone
reading the API.

A control asks a question and an answer states something. "Which day?" and
"How much rain?" over the two button rows; everything in the panel is a
statement. Every caveat is said once, in one place, and the repeats are
gone.

#### The amount nicknames

The three thresholds are the same three numbers they have always been. The
words beside them are **this site's own nicknames**, not an official
category of anybody's, and they are written down here so that they are
fixed and so that nobody can take them for IMD's classes:

| threshold | the nickname | why not the obvious word |
|---|---|---|
| 1 mm or more | **Some rain** | |
| 10 mm or more | **A rainy day** | "a wet day" is the natural phrase and "wet" is a forbidden word of 11.20 |
| 50 mm or more | **A lot of rain** | "very heavy" is the natural phrase and "heavy" is a forbidden word of 11.20 |

The forbidden list is not a style preference. "Heavy rain" is IMD's own
class name for a band this site does not measure, and a page that borrowed
it would be claiming a warning it has not issued. One line under the
buttons gives the only scale a reader needs: *10 mm of rain is water 1 cm
deep if none of it ran away.*

The same three nicknames appear in How to read this map and nowhere else;
they are never used without their millimetres beside them.

#### The headline

One sentence, the same shape every time, in the phone's closed bar and at
the top of the panel:

> **Srinagar, Today: a few of the 51 runs bring 10 mm or more (7 of 51).**

The band word is a reading aid and the count is the number. Both are
there, always, in that order, because the word alone would be a claim the
count has not made and the count alone is what three reviews called too
textual.

| runs | the word |
|---|---|
| 0 | none |
| 1 to 10 | a few |
| 11 to 20 | some |
| 21 to 30 | about half |
| 31 to 45 | most |
| 46 to 50 | almost all |
| 51 | all |

The bands describe **the runs** and never the weather. "A few of the 51
runs bring 10 mm" is a statement about a model; "rain is unlikely" is a
forecast, and this site does not make one. No band word is ever drawn on
the colour legend, where it would read as a label for the colour and so as
a claim about the square.

The boundaries are tested one by one, at 0, 1, 10, 11, 20, 21, 30, 31, 45,
46, 50 and 51, because an off-by-one here is the page saying "most" where
the record says "about half".

#### What a place is called

| how it was chosen | what the page calls it |
|---|---|
| searched by name | that city's name |
| tapped, and the square is a city's own square | that city's name |
| tapped, with a city within 50 km | **near** that city |
| tapped, with nothing within 50 km | **this area** |

The name is bold and first; the coordinates are small underneath. The
first build led with "23.25 N 77.50 E" and put the name after it, which is
the order a grid reference is written in and not the order a person reads.
Fifty kilometres is under two squares, so "near Nagpur" is never said about
somewhere a reader would call a different place.

#### Answer first

The panel's order, on a phone and on a desktop alike:

1. the place name
2. the headline
3. **The next five days** — the strip, moved up from sixth
4. **The 51 runs, one dot each** — the four category counts always visible
5. the three amount rows
6. the trust label, once per place, with the track record as its reason
7. one line: *A count of runs, not a promise of rain.* — linked to the report card

and then a closed section, **For the curious: the numbers behind this**,
holding the 51 values with the control run, the square's i and j and its
tile, the run ID, the UTC line and the long track-record sentence with its
region, day number and date range. Nothing is deleted; what is moved is
moved into one place a reader can choose to open.

The trust chip was drawn four times on one screen — once per amount row
and once more under them — which is a wall of "Rough guide" and not a
label. It is drawn once. Its reason is the track record itself:

> When the runs said this before in East and North East India, the
> satellite saw rain of 10 mm or more about 4 times in 10.

and, only where the group's better-than-the-usual-rain check passed, one
more sentence saying so, linked to the report card. The two ends keep the
wording of 11.33: a band rounded to 0 reads "fewer than 1 time in 10" and
one rounded to 10 reads "nearly every time", because "about 0 times in 10"
reads as never and the record did not say never.

On a phone, once a place is answered, the search box and "Use my location"
move **below** the answer. The bar's Search button still opens the panel
with the keyboard, so the way in is unchanged; what changes is that the
answer is no longer 193 pixels down behind a box the reader has already
used.

#### The welcome card

Until a place is chosen there is no answer to put first, so the space
carries the only two things a first-time reader needs: what this is, and
what to do.

> **Will it rain where you are in the next 5 days?**
>
> One weather model from Europe's weather centre (ECMWF), run 51 times,
> each from a slightly different start. We show how many of the 51 bring
> rain where you are.
>
> [ Find my city ]  or tap the map
>
> How to read this map

It is over the map on a phone and in the empty panel on a desktop. It
leaves the moment a place is chosen and comes back if the choice is
cleared. It never covers the "Not an official warning" chip, which is in
the header above it and is on the screen whatever else is.

"Find my city" opens the search with the box focused — the review found
that a reader who wants to start cannot see a search box at all until the
panel is open, and the panel's only visible control was a line of text.

#### The site's name

**India Rain Outlook**, with the tagline *51 runs of one weather model. See
how many bring rain where you are.* under it. The browser tabs are
"India Rain Outlook · next 5 days", "Report card · India Rain Outlook" and
"How we checked · India Rain Outlook", so a reader with three tabs open can
tell them apart, which the one shared title did not allow.

#### Freshness, on a phone

The header's run line is three facts — run time, publish time, run ID — in
two sizes of grey. On a phone it is one line:

> Updated 13 Nov, 12:33 pm IST · 16 h old

and when the run is older than the 36 hours of 11.8 that line becomes the
warning itself: *This forecast is 41 hours old; a newer one has not arrived
yet.* It never says a newer one is on its way, because nothing here knows
that. The run ID and the UTC time are in "For the curious". The desktop
header keeps the run line it had.

#### The map, and the things that are not squares

| | |
|---|---|
| the fit | the whole of India — 6 to 38 N and both coasts — is in view on first load at 390 x 664 and at 1440 x 900, fitted **after** the map box has its real size and not before |
| white | "White: no forecast for this spot" |
| beige | a swatch of its own: "Land outside India, which this site does not forecast" — it had no legend entry at all, so a reader who tapped Nepal got a red error about a colour the page had never named |
| a tap outside India | the calm line *That's outside India. Tap the map over India or find a city.*, in a plain box and not a red one, and the old city name is cleared out of the search box |
| waiting | "Reading the 51 runs for this square…" |

#### The phone floors

11.37 set a floor for the panel and the bar and left the controls bar and
the menu where they were: 12.2 pixel day buttons 29.8 pixels tall, and nav
links of 13.6 pixels. The floors are the page's now, not the panel's:

| | |
|---|---|
| day buttons, amount buttons, nav links | at least 44 pixels tall, text at least 15 pixels |
| any text on the forecast page | at least 12 pixels |
| at 390 pixels | nothing scrolls sideways |
| at 390 x 664, after choosing | the place name, the headline and the five-day strip are all in the open panel without scrolling |

Where they do not fit, the headline wraps to two lines and the strip's
cells shrink first. No text goes under the floors to make room.

**What the floors cost, measured at 390 x 664.** The three rows go from
30 pixels tall to 44, and that height comes out of the map: the shut map
was 250 pixels and is 227. It is the trade this section chose, and the
test that used to ask for 250 asks for 225 and says why. The open panel
takes the last of the map's own floor as well -- 56 pixels rather than
80 -- which is what puts the five cells of the strip on the screen; the
map is thinner and never gone, and it has all of it back the moment the
panel is shut.

The 12 pixel floor is the page's and not the panel's, so it reaches the
names drawn **on** the map too: the state codes were 9.6 pixels and the
city names 11.5. The fit of 11.31 measures the drawn word, so a larger
word means a code where a name used to fit and nothing where a code used
to, which is that algorithm doing its job rather than a layout to repair.
MapLibre's own zoom buttons are 29 pixels and are not ours to lay out;
its attribution is set to 12 where the stylesheet can reach it.

#### The search box

It had one way in and one way out: type the first letters of one of 215
Natural Earth city names, or go away. A reader who types the name of their
state, or the name their city had when they learned it, was told "No town
in the list starts with ...", which is a page blaming a reader for not
knowing what is in a file.

**States and union territories.** All 36 are recognised, in any case, with
`&` and "and" the same word and punctuation ignored, so "Jammu & Kashmir"
and "jammu and kashmir" are one query. The **short forms** — WB, UP, MP,
TN and the rest — count **only as the whole query**, because two letters
inside a longer word are not an abbreviation: "up" on its own is Uttar
Pradesh and "udaipur" is a city. Older names of units are keys too:
Orissa, Uttaranchal, Pondicherry.

A state is never answered with a count. Rain over Rajasthan on one day is
not one number, and an average nobody asked for is not an answer. What a
state gives is its outline on the map and the cities inside it:

> **Kerala is too big for one forecast: rain can differ a lot across it.
> Tap the map, or pick a city:**

Which cities are inside it is decided at build time, by the city's own
point against that unit's own polygon from the admin-1 layer —
`scripts/build_towns.py` writes `unit` onto every city and `box`, the
unit's bounding box rounded **outwards** to a hundredth of a degree, onto
every unit. Natural Earth's own `ADM1NAME` on the populated-places layer
is not used: it calls Bhavnagar "Dadra and Nagar Haveli". 214 of the 215
cities land in a unit; the one that does not is Gilgit, which is inside
the India point-of-view outline and inside no admin-1 polygon, and it is
reported by the build rather than guessed at.

Where a name is both a city and a territory — Delhi, Chandigarh,
Puducherry — **the city wins**, and it wins through the older names too, so
"Pondicherry" is the city.

**Older names of cities.** The list's spelling is Natural Earth's, and it
is not always the one a reader learned: it says Mumbai, Bengaluru, Mysuru,
Hubballi and Vijayapura, and it also says Simla, Dehra Dun, Jullundur,
Nasik, Sholapur and Gurgaon. A reader should not have to know which of the
two this file happens to hold, so both are search keys: Bombay, Calcutta,
Madras, Bangalore, Gurugram, Poona, Trivandrum, Cochin, Baroda, Benares
and forty more. The name **shown** is always the list's own, because the
name over a count has to be the name the count belongs to.

**Anywhere in the name**, with the ones that start with what was typed
first — so "agar" finds Agartala, Ahmednagar, Bhavnagar and Gandhinagar,
and a reader who knows the middle of a name is not stuck. "Did you mean"
stays for a misspelling.

**"City", not "town"**, in the label, the hint and every message. And
nothing matched is said as four ways on rather than as a refusal:

> We don't have Ooty yet. Try a nearby city or your state, tap the map, or
> type a latitude and longitude such as 22.5, 88.4.

#### Tests

| | |
|---|---|
| the states | all 36 names, in any case, and every short form as the whole query, each finding its own unit |
| the short forms | "up" is Uttar Pradesh and "udaipur" is Udaipur |
| the city wins | Delhi, Chandigarh and Puducherry are cities, and so is Pondicherry |
| no count for a state | a state's answer holds no number out of 51 and no square |
| the cities inside | every city the state block lists has that unit in `towns.json`, and every unit has at least one |
| the older names | each one finds its city, and the city is shown under its own name |
| the middle of a name | "agar" finds four, with the ones that start with it first |
| nothing matched | the four ways on, and the query in it |
| the box | every unit's `box` holds every city in that unit |

#### Tests for the rest of this section

| | |
|---|---|
| the bands | every boundary, 0 to 51, against the table above |
| the names | the rendered forecast page holds no "model runs" and no "members" |
| the day labels | the visitor's date equal to, one before, and two before the first day, so "Tomorrow" is never printed for today |
| the welcome card | it shows with nothing chosen, leaves when a place is chosen, comes back when the choice is cleared, its button focuses the search box, and its How to read this map link opens on a phone |
| the place name | a city's own square by name, a square within 50 km as "near", and one beyond as "this area" |
| answer first | at 390 x 664, after a tap, the name, the headline and the strip are inside the open panel with no scrolling, and nothing is under the floors |
| once only | "A count of runs, not a promise of rain." appears exactly once in the answered panel |
| the dots | the four counts are readable without opening the closed section |
| the trust reason | the track-record line is the chip's reason, and the better-than-usual sentence appears only for groups whose check passed |
| the fit | the whole India box is in view at 390 x 664 and at 1440 x 900 |
| the sizes | the floors above, measured in a real browser |
| outside India | a tap there gives the calm line and clears the box |
| staleness | the stale line never promises a newer run |
| the tabs | each page's own title |
| the words | the forbidden-word and no-percentage sweep covers every new sentence and every new state, and is shown to catch a "certain" inserted into it |

### 11.39 The calm page: one column, pills, and a card

11.38 fixed the words on the forecast page and left its shape alone. The
shape was the next thing readers tripped on: on a phone the page was a
fixed-height shell with a map in the middle and a bottom sheet over it, so
the answer lived in a drawer that had to be dragged open, the map had a
floor measured in tens of pixels, and everything competed for one screen
that never scrolled.

This section replaces that with the ordinary thing: a page that scrolls,
top to bottom, with the controls above and below the map and one card for
the answer. Nothing about the forecast changes. Counts are still out of 51,
there are still no percentages, the forbidden-word list of 11.20 still
holds, the trust labels of 11.33 are untouched, freshness and the warning
are still on the first screen of every page, tap targets are still 44
pixels and sentences still 15, the theme is still light only and the map
colours are exactly the colours of 11.17.

Where two of those rules fight, spacing gives way first and the map's
height second. Type size and tap targets never give way.

#### The card: one order, and one closed section

The card is called the Location forecast, and its order is the answer
first and the working after it:

| | what it holds |
|---|---|
| 1 | the place name, large: a city, "near <city>", or "this area" (11.38) |
| 2 | one small line: `<Day>, <date> · 5:30 am to 5:30 am IST · <amount name> (<N> mm+)` |
| 3 | the square's own centre, small |
| 4 | the headline of 11.38, with its band word |
| 5 | the five-day strip |
| 6 | the 51 dots, their four counts, and the one line that says what a dot is |
| 7 | "A count of runs, not a promise of rain.", linked to the report card |
| 8 | the trust label on one line: the chip, its reason, and a link to the record |
| 9 | a closed **More detail** |

Line 2 is the one line that replaced three: a heading over the amount
rows, the help sentence under the day buttons ("Each day runs from 5:30 am
to 5:30 am the next morning") and the help sentence under the amount
buttons ("10 mm of rain is water 1 cm deep if none of it ran away"). A
count means nothing without which day it is for, what a day is on this
site, and how much rain, so those three are said once, under the name, and
not once per control.

The day on that line is named by the rule of 11.38 and written as two
pieces, the word and the date, because the pills above the card are two
lines and the two have to agree: "Today" over "15 Nov". The date is the
run's own published `short_ist` with the weekday taken off the front of
it. Nothing on this page formats a date a second time.

More detail holds everything a reader can choose to open, and nothing is
deleted to get there:

- the three amount rows, which are a second copy of the buttons above the
  map and were the fifth block of the card;
- what each of the 51 runs gives, in whole millimetres, with the control
  run first;
- which of the four conditions the label came from ("Why this label?") and
  the long track-record sentence, both of which are about our method
  rather than about this square;
- the square's i, j and tile, and what was asked for;
- the run's own ID and its 00 UTC time.

The strip's own help sentence goes with the others. The cells still carry
a full sentence each to a screen reader, and what that sentence said, the
colours, the amount, and that the dates are IST, is line 2 and How to read
this map.

#### How to read this map: a page, not a block in the panel

Every help sentence on this site had collected on the forecast page: three
bullets and two colour lines in the panel, one under the day buttons, one
under the amount buttons, one under the five-day strip, one under the
legend and two under the dots. A reader who wanted the forecast read past
all of it; a reader who wanted the explanation opened a drawer to find it,
and could not send anybody a link to it.

So it is the site's fourth page, at `/how-to-read`, lazily loaded like the
report card and How we checked, and it holds:

- "Each day runs from 5:30 am to 5:30 am the next morning, IST." The
  published window, which is not the calendar day.
- What one square is: 0.25 degrees, about 28 km, and the smallest place
  this site can answer about.
- The three amounts, in this site's own everyday words, at `#amounts`,
  which is where "What does mm mean?" lands.
- "This is the total over the whole day, averaged over the square, so it
  can be one short burst or hours of drizzle."
- The full colour ranges, as the nine rows below.
- "It is not a probability", with the sentence of 11.21.

| amount | our words |
|---|---|
| 1 mm or more | Enough to leave the ground damp. |
| 10 mm or more | A proper shower: you would want an umbrella. |
| 50 mm or more | A very rainy day: water can collect on roads. |

The first of those was "enough to wet the ground" as it was asked for, and
could not be: "wet" is on the forbidden list of 11.20, and that list is
there because "a wet day" is a forecast of what a day will be like, which
this site does not make. "Damp" says the same thing about the ground and
claims nothing about the day. The millimetres are the rule; these words are
only there to make a number mean something, and the page says so.

The nine rows of the colour key are one list, read by this page and by the
key on the map, so the two cannot disagree:

| row | |
|---|---|
| 1 | None |
| 2 | 1-10 runs |
| 3 | 11-20 runs |
| 4 | 21-30 runs |
| 5 | 31-40 runs |
| 6 | 41-50 runs |
| 7 | All 51 runs |
| 8 | White: no forecast for this spot |
| 9 | Beige: land outside India, not forecast |

Every row says "runs", which is the page's one name for the 51 (11.38), and
no row carries a band word: beside a colour, "a few" would read as a name
for what that colour means on the ground, which is a forecast this site
does not make.

The header band writes out three page links and this is not one of them:
the band has room for three, and this page is reached from the page it
explains, from the menu, and from "What does mm mean?" under the amount
buttons.

What the forecast page keeps is one explanatory line, the one under the
place name. Nothing else on it explains anything.

#### The calm look

The page was not loud because of its colours; the map colours are 11.17's
and are untouched. It was loud because everything on it was drawn as a box
with an edge. The controls bar was fourteen white rectangles with hairline
borders, which is what an empty form looks like, and three of those
rectangles were already answered without a reader being able to see which.

So:

| | |
|---|---|
| an unchosen pill | a pale grey fill, `#e9edf1`, and no border at all |
| the chosen pill | filled `#0b2b4a`, white ink, the same navy the map marks the chosen square with |
| cards and notes | the fill is what says it is a card; no outline round it |
| a quoted note | may keep a 3 pixel bar down its left edge, which is not an outline |
| the search box | keeps its 1 pixel border: it is the one control a reader puts something into, and a field with no edge reads as a line of text |
| every control | keeps the focus ring, declared once as `:focus-visible { outline: 2px solid #0b2b4a; outline-offset: 2px }`. Nothing on this site may set `outline: none` |
| labels | no all-caps, anywhere. Mixed case is read about a fifth faster, and capitals were being used to make three ordinary questions look like system labels |

Two rules about how much of each thing there may be: at most two text
sizes in the header, and at most three in the card. And the space between
one group and the next is about one and a half times what it was on a
phone and about twice on a desktop; both numbers are one custom property
each, so the whole page reads them and a change is one line.

The map's own state names lose their capitals with everything else. A
state is told from a city by weight, colour and letter spacing, which is
what told them apart before as well, and the width of every one of those
words is measured at runtime before it is placed (11.31), so the placement
follows the words rather than an assumption about them.

#### Three buttons that are gone

"Find my city", "Find a city" and the bar's "Search" are all removed. Each
of them did the same thing: open the panel and move the keyboard into the
search box. A button whose whole job is to focus a box that is already on
the screen is a second way in competing with the first, and it was the
first way in that readers could not find. What replaces all three is the
search row itself, with the box in it, and the card saying what to do:
"Tap the map or search a city to see its next five days."

#### One grid, two orders

There is one set of blocks and one grid. The order is the only thing that
differs between a phone and a desktop, so there is one copy of every
control in the page and no second layout to keep in step.

| | a phone (under 1024) | a desktop (1024 and over) |
|---|---|---|
| 1 | the search row | the search row |
| 2 | the map card | the two pill rows |
| 3 | the day pills | the map card, left; the forecast card, right |
| 4 | the amount pills | |
| 5 | the Location forecast card | |
| 6 | the footer | the footer |

The header is one band at both widths: the mark, the site's name, how old
this run is, and the pages. Under it, across the whole width, the warning.
Three things left it: the tagline, because what the site is for is the
question at the top of the card where a reader who has chosen nothing is
already looking; the run ID; and the "(00 UTC)". The last two are in More
detail.

The freshness line names the **run** time and counts the age from the time
it has just printed. It used to print the publish time beside an age
counted from the run time, so the two numbers on one line disagreed with
each other by however long the pipeline had taken.

The card's empty state is the page's answer to "what is this": the
question, one sentence saying what the 51 are, what to do next, and a link
to How to read this map. Under the card there are two links, and the How
to read one is not drawn while the empty card is carrying it — a link to
something already on the screen under it is noise.

#### Where the colour key goes, and what it costs

The key is paid for by padding the fit on the side it sits on: the left
edge is padded by the key's own measured width, so India begins to the
right of it and nothing of the country can be behind it. While the fit is
limited by the map box's height, that padding costs the country nothing at
all.

Where it would cost something the key is drawn directly under the map
instead, inside the same card. The boundary is 1280 pixels, and it was
measured rather than chosen:

| width | the map box | what a floating key would cost |
|---|---|---|
| 1440 x 900 | 990 x 558 | nothing: the fit is height-limited and India keeps all 482 pixels of its width |
| 1024 x 768 | 574 x 476 | the fit becomes width-limited, India shrinks from 409 to 305 pixels, and Gujarat is behind the key anyway |
| 390 x 844 | 358 x 464 | India fills the width; 226 pixels of padding would leave the country a third of the card |

So at 1280 and over the key floats in the lower left corner, over the
Arabian Sea, open. Below that it is under the map, shut, and what a reader
sees without opening it is the title, the strip of the seven colours and
the two ends in words.

A check projects every one of the 4,613 forecast squares and every point
of the drawn outline — Lakshadweep included, which has no forecast square
at all — into the canvas's own pixels, from the bounds the map itself
reports, and fails if one of them is behind the key.

#### The header, on every page

Five icons, drawn inline in `src/Icons.jsx`: the mark, a clock, a warning
triangle, a location pin and the menu bars. No icon library, which would
be a download for five shapes, and no emoji, because a rain cloud is a
different picture on every platform and a site's own mark may not be. Each
one is 24 by 24, takes its colour from `currentColor`, and is
`aria-hidden`: every one of them sits beside a word that says the same
thing, which is SPEC 11.22 and why the clock is next to the time rather
than instead of it.

The mark is the favicon too, written into `index.html` as an SVG data URI
with the same path, and a test compares the two.

| | |
|---|---|
| the band | the mark and the name (the page's one `h1`, and the way back to the forecast), the freshness line, and the pages |
| the pages | three links as text at 1024 and over; a **Menu** button under it, holding all four |
| under the band | the warning, across the whole width |

The Menu is a real button with `aria-expanded` and real links behind it. It
shuts on Escape, on a pointer down anywhere outside it, and on following a
link: a menu a reader cannot get out of is worse than no menu.

All of it is drawn once, in `Site.jsx`, above whichever page is being
read. Freshness and "not an official warning" are rules about every page
and not about the forecast, and the report card and How we checked used to
carry the warning in the footer only, which on either page is several
screens down. The back link those two pages had is the mark and the name,
which is the same way back from everywhere.

## The hand checks

A hand check redoes one thing the pipeline did, outside the pipeline, and
says where the two disagree. They are kept whole in `handchecks/`, with
their output in `handchecks/results/`, and they are not run in CI: a check
that is run by the thing it checks is not a check.

The numbered ones were done first and keep their numbers. The named ones
were added on 13 November 2026.

HC1, HC2 and HC3 were each run on more than one date on purpose: 13 May, 1
August and 25 October 2026 for HC1 and HC3, and 13 May and 25 October for
HC2, which puts a run either side of both things ECMWF changed in 2026 (2.1).
Each run wrote its own file and every one of them is linked from the site.

| | what it redoes | script | result |
|---|---|---|---|
| HC1 | the saved subset against the original GRIB, on three run dates | `hc1_compare_grib.py` | `hc1_20260513.txt`, `hc1_20260801.txt`, `hc1_20261025.txt` |
| HC2 | the daily difference, worked out again, on two run dates | `hc2_difference.py` | `hc2_20260513.txt`, `hc2_20261025.txt` |
| HC3 | the steps and the 51 members, on three run dates | `hc3_steps_members.py` | `hc3_20260513.txt`, `hc3_20260801.txt`, `hc3_20261025.txt` |
| HC4 | one raw IMERG file, field by field | none: the file was deleted after it was read (2.6), and what it found is in 2.3 | |
| HC-ALIGN | the two grids against each other | `hc_align.py` | `hc_align.txt` |
| HC5 | one cell of the area-weighted remap | `hc5_cell.py` | `hc5_cell.csv` |
| HC6 | the 51 member values in one square | `hc6_members.py` | `hc6_members.csv` |
| HC7 | the published bytes against the built run | `hc7_published.py` | `hc7_published.csv` |
| HC8 | five squares on the live map (11.25) | `hc8_map_square.py` | `hc8_map_square.csv`, `.jpg` |
| HC9 | one reliability band, from the archive | `hc9_bucket.py` | `hc9_bucket.csv` |
| HC-FAIL | the publisher and the chooser, made to fail | `hc_fail.py`, `hc_fail_site.mjs` | `hc_fail.csv`, `hc_fail_stale.txt`, `.jpg`, `hc_fail_13nov.txt` |
| HC-ECMWF | ECMWF's own probability of 10 mm against our count | `hc_ecmwf.py` | `hc_ecmwf.csv` |
| HC-REPORT | the report card's Brier scores, redone | `hc_report.py` | `hc_report.csv` |
| HC-GHATS | one monsoon day of remapped IMERG, drawn | `hc_ghats.py` | `hc_ghats.csv`, `hc_ghats.png` |
| HC10 | the final checklist, at the end of the build | not written yet | none: it has not been done, and nothing published depends on it |

`hc6_members.csv` was written on 12 November 2026 and carries a line saying
ECMWF publishes no probability product. That line is wrong and HC-ECMWF is
the correction; the file is left as it was written, because a result file is
a record of a run and not a draft. The script's wording is corrected, so a
re-run does not repeat it.

#### HC-FAIL

Failure handling, on purpose (1.5, 8.6, 11.8). A real built run is copied to
a temporary folder, broken one way at a time, and the real publisher is run
against an in-memory store that already publishes the real run. Nothing
touches `data/`, nothing touches the network and no token exists.

Seven ways of going wrong, and in **every one of them nothing was uploaded
and the store went on publishing the run it already had**.

**The two exit codes are a rule, not an accident.** A missing ECMWF run, or
one that is not complete yet, exits **0**: the workflow tries all day
(1.5, 8.6) and simply comes back later, and a run that is not there yet is
not a failure. A broken or inconsistent file exits **1**: that is a failure
and has to be seen. In both cases nothing is published and the run already
published stays exactly where it is, which is the part a reader depends on. A broken file --
a torn manifest, a missing `days.json`, a cut-off `squares.npz`, counts that
no longer match their members, a different India mask -- exits 1. Nothing to
publish -- no forecast at all, or a run with no manifest, which means it
never finished its checks -- exits 0. That difference is deliberate: the
workflow runs all day whether or not ECMWF has a run ready, and a red
failure on an ordinary quiet day would teach us to ignore red. A control
publishes the same copy unbroken, so the seven failures are the sabotage and
not the fixture.

`select_run` is asked the same question five ways: nothing offered, an
incomplete newer run, the run already built, an older run, and a complete
newer one. Only the last is built.

The banner of 11.8 is shown rather than argued about: `hc_fail_site.mjs`
serves `web/dist` and the real `api/*.mjs` against a copy of a published
run, and the real 12 November run really did pass 36 hours old at 12:00 UTC
on 13 November. No clock is moved anywhere in this check.

And the day it happened for real: on 13 November 2026 **not one of the 23
scheduled attempts fired**, and the site kept the 12 November run until a
manual dispatch at 07:02 UTC. 31.5 hours, so no visitor ever saw the banner.
The run list and the logs are in `hc_fail_13nov.txt`.

#### HC-ECMWF

ECMWF's own probability against ours, and the correction to 3.6 above.
`tpg10` is real, it is a percentage, and at 24-48 hours it is our day 1. For
run 20261112T00Z, over all 4,613 India squares: mean size of the difference
**0.21 points**, correlation **0.993**, 6 squares apart by more than 10
points. 90 squares where we say none of 51 and they say more than nothing,
80 of them beside a square where members do reach 10 mm; never the other way
round.

**Their number is not a count of members.** A count of 51 can only be 0,
1.96, 3.92 ... per cent; their field holds values as small as 0.03 per cent
and no search over ensemble sizes from 20 to 400 makes them whole numbers of
members. So the two cannot be reconciled by arithmetic, and we do not try:
we publish a count, we say it is a count, and no other model is put in its
place.

One finding about the data rather than the forecast: the `.index` beside an
`ep` file is three indexes concatenated and the byte offsets restart at 0 in
each. Read as published -- which is what `ecmwf-opendata`, the official
client, does -- the download is 354,571 bytes that do not begin with `GRIB`.
HC-ECMWF carries the running position across the blocks instead.

#### HC-REPORT

The report card's own Brier scores, redone from the stored arrays with
nothing imported from `pipeline/`. The region is chosen by rule: the one
whose published groups hold the most cases and the most events, which is
Central India. All 15 of its groups -- 5 lead days by 3 thresholds -- were
worked out again: **cases, events and base rate identical, and the largest
difference in any Brier score 4.97e-07**, which is the six decimals the
published file is rounded to and nothing else.

Ten of the 267,270 cases are written out in full, chosen on the forecast
side alone: ten counts spread from 0 of 51 to 51 of 51, and for each the
first case in date and then square order that says it. Each row carries the
run date, the IMERG day it was a forecast for, the square, k, k/51, the
satellite's millimetres, the outcome and the squared error.

Two unit tests carry what no recomputation of a real group can: a perfect
forecast scores 0 with a skill of 1, and **forecasting the usual rain for
that place and month, every day, scores a skill of exactly 0**. The second
is new, and it needed a second toy archive: 1/3 is a rate 51 members can say
exactly and 1/2 is not. Breaking `verify.py` two ways is shown to fail them.

#### HC-GHATS

A remap can be right cell by cell and still be flipped, rolled or transposed
as a whole, and no per-cell check would notice. Geography notices.

The day is chosen by rule -- the July 2026 day with the highest
cos(latitude) weighted mean rain over India, which is 3 July -- and then
drawn, one rectangle per 0.25 degree square, in `hc_ghats.png`. On that day
**23 of the 25 wettest India squares are inside the windward strip** (8 to
21 N, 72.5 to 76 E), and the two that are not are at 73.25 E a quarter and a
half degree north of its edge, on the same line of hills. The windward strip
averaged **33.0 mm** against the leeward strip's **6.7 mm**, a factor of
five on one day. Drawing the field upside down, rolled four squares east, or
transposed is caught.

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
approved the same day; 11.28 and 11.29 record what reading the built page
changed, with the measurement behind each change. The track record pages and the display rules that go
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
