# Precipitation Forecast App

**India rain outlook: how many of 51 runs bring rain.**

A map of India in 0.25 degree squares, about 28 km across, 4,613 of them.
Each square is coloured by how many of 51 runs of one weather model bring at
least the chosen amount of rain — 1 mm, 10 mm or 50 mm — on the chosen one of
the next five days. The numbers are counts out of 51, never percentages and
never probabilities, and the point of the project is the track record: 177
past runs have been checked against NASA's satellite estimates and the result
is published in full on the site, including where the forecasts are too
confident.

**Live: <https://precipitation-forecast-app.vercel.app>**

| | |
|---|---|
| the page | <https://precipitation-forecast-app.vercel.app> |
| what is published now | <https://precipitation-forecast-app.vercel.app/api/health> |
| one square | `/api/place?lat=28.5&lon=77.25` |
| the track record | <https://precipitation-forecast-app.vercel.app/report-card> |
| how it was checked | <https://precipitation-forecast-app.vercel.app/how-we-checked> |

## How to use it

1. Search your city, or just tap the map.
2. Pick the day and the amount of rain you care about.
3. That's it, your forecast shows up.

The search knows 215 Indian cities and all 36 states and union territories,
and takes a typed latitude and longitude; "use my location" rounds the fix to
its square inside the page, so no position is ever put in a request. Every
number the colours carry is also written out in words, so nothing is only
available by looking at a picture, and if the map cannot be drawn at all — an
old browser, no WebGL 2 — the page says so and the rest still works.

## What the numbers mean

- **A count of runs, not a probability.** "18 of 51" means 18 of the 51 runs
  reached 1 mm in that square on that day. It is not a 35-in-100 chance of
  rain: turning counts into chances needs a record of how often they came
  true, and the record published here says these counts are too confident.
- **A day is 5:30 am to 5:30 am IST.** That is the window the model
  publishes, so it is the window this site adds up. It is not the calendar
  day, and every time on the site is IST.
- **A square is 0.25 degrees, about 28 km.** It is the smallest place this
  site can answer about: two towns in one square get the same numbers, and
  nothing here is street level.
- **The amount is the whole day's total, averaged over the square.** It does
  not say whether that was one burst or hours of drizzle.
- **NASA IMERG is a satellite estimate, never ground truth.** It is what the
  forecasts were checked against; it is not a measurement of what fell.
- **Not an official warning.** For warnings and advisories, see the
  [India Meteorological Department](https://mausam.imd.gov.in/).

## The track record

We saved 177 past forecasts from 13 May to 5 November 2026 and checked each
one against the satellite estimate of the rain that fell. We sorted them into
60 groups, by region, days ahead and rain amount. In 20 groups the counts did
better than the usual rain for that place and month; in the other 40 we could
not show they were better. And in all 60, when most of the 51 runs agreed on
rain, rain was seen less often than that. So treat the counts as a helpful
hint, not a promise.

That is the same summary the site's own
[report card](https://precipitation-forecast-app.vercel.app/report-card)
opens with, and it is computed from `results/site_summary.json` rather than
written out by hand, so the two cannot drift apart. A label is one region,
one lead day and one threshold: four regions by five days by three thresholds
is 60 of them. The record is mostly monsoon and says little about winter.

## How it works

**The live pipeline.** Once a day, `pipeline/` downloads the 00 UTC run of
ECMWF's AIFS ENS open data — 51 runs, total precipitation, six 24-hour step
boundaries — keeps only the India box, differences the accumulations into
five IST days per run, counts how many of the 51 reach 1 mm, 10 mm and 50 mm
in each square, masks everything outside the India land mask, and runs its
own checks (every count in 0 to 51, counts monotone across the thresholds,
every published square inside the mask) before anything is published.

**Publishing.** The run is uploaded to a Vercel Blob store, every file first
and `manifest.json` last, so a reader can never meet half a run: until the
manifest moves, the site goes on serving the previous one. A marker file per
published run records what is live. The site shows the age of what it is
showing, and says the forecast is old once it passes 36 hours. An incomplete
run is never published.

**Verification.** 177 saved runs were scored against NASA IMERG Late V07C,
remapped onto the forecast grid by area-weighted overlap on a sphere, with
the same 5:30-to-5:30 day at both ends. The score is the Brier score and the
skill is against the rain that usually falls in that square in that calendar
month; the range is a bootstrap of run dates. Every rule — what a case is,
what is excluded, how groups are formed, what each label needs — was written
into `SPEC.md` and committed before any result was looked at.

**The site.** React, Vite and MapLibre GL JS, with the map in a chunk of its
own and the three document pages lazily loaded. `api/health` and `api/place`
are two Node functions on Vercel, with no database and no token: they read
the public store. There is no basemap, no tile server, no font server and no
geocoder, so a reader's browser talks only to this site and to the store.

## Checks

`python -m pytest` runs 563 tests from 450 test functions in 11 files. They
need no network, no token and no data: the API tests build a small run,
publish it through a fake store into a temporary directory, serve it on
127.0.0.1 and call the real functions against it, and the page's own pure
modules are driven by `node`. The browser checks drive a headless Chrome
over the DevTools protocol against a real `vite build` and measure the page
at eight screen sizes.

Beside the suite, each hand check redoes one step outside the pipeline, by
hand or in its own script, and writes its own file:

| | what it redoes | what it wrote |
|---|---|---|
| HC1 | the saved subset against the original GRIB, three run dates | [13 May](handchecks/results/hc1_20260513.txt), [1 Aug](handchecks/results/hc1_20260801.txt), [25 Oct](handchecks/results/hc1_20261025.txt) |
| HC2 | the daily difference, worked out again, two run dates | [13 May](handchecks/results/hc2_20260513.txt), [25 Oct](handchecks/results/hc2_20261025.txt) |
| HC3 | the six steps and the 51 runs, three run dates | [13 May](handchecks/results/hc3_20260513.txt), [1 Aug](handchecks/results/hc3_20260801.txt), [25 Oct](handchecks/results/hc3_20261025.txt) |
| HC4 | one raw IMERG file, field by field | the file was deleted after it was read; what it found is in `SPEC.md` 2.3 |
| HC-ALIGN | the forecast grid and the satellite grid against each other | [hc_align.txt](handchecks/results/hc_align.txt) |
| HC5 | one cell of the area-weighted remap, nine pixels by hand | [hc5_cell.csv](handchecks/results/hc5_cell.csv) |
| HC6 | all 51 run values in one square, read by ecCodes | [hc6_members.csv](handchecks/results/hc6_members.csv) |
| HC7 | the published bytes against the run this laptop built | [hc7_published.csv](handchecks/results/hc7_published.csv) |
| HC8 | five squares on the live map: colour, bytes and panel | [hc8_map_square.csv](handchecks/results/hc8_map_square.csv) |
| HC9 | one reliability band, worked out again from the archive | [hc9_bucket.csv](handchecks/results/hc9_bucket.csv) |
| HC-FAIL | the publisher broken seven ways, the run chooser given five awkward servers | [hc_fail.csv](handchecks/results/hc_fail.csv) |
| HC-ECMWF | our counts against ECMWF's own figure for 10 mm or more | [hc_ecmwf.csv](handchecks/results/hc_ecmwf.csv) |
| HC-REPORT | fifteen of the report card's own scores, redone outside the pipeline | [hc_report.csv](handchecks/results/hc_report.csv) |
| HC-GHATS | one monsoon day of the remapped satellite field, drawn | [hc_ghats.csv](handchecks/results/hc_ghats.csv) |
| HC10 | the final checklist, done at the end | — |

Colours: ColorBrewer YlGnBu; checked under protanopia, deuteranopia,
tritanopia and achromatopsia in Chrome's vision-deficiency emulation.

## Updates and freshness

The forecast workflow, `.github/workflows/forecast.yml`, asks GitHub's
scheduler for 23 attempts a day between 06:17 and 22:23 UTC. In this build
the schedule fired late and unreliably: of the 11 workflow runs in the
Actions history, 5 were scheduled and 6 were started by hand, and **all three
runs published so far were published by a manual start — the scheduled runs
published nothing.** The five that did fire arrived at 00:55, 13:27, 14:29,
17:44 and 19:53 UTC, which is 06:25 am to 01:24 am IST: never the midday
window when the new forecast is ready.

When no new run publishes, the site keeps the last good forecast and says how
old it is, and calls it old past 36 hours. It never shows half a run and
never shows broken data. A second, backup daily trigger from Vercel's cron
was designed and deliberately left unbuilt (see Future work).

## Limits

- **Not street level.** 0.25 degree squares, and nothing finer exists in this
  forecast: hills, cities and coastlines inside one square are not told
  apart.
- **Daily totals only.** No timing inside the day: 10 mm can be one burst at
  dawn or drizzle all afternoon, and this site cannot tell you which.
- **Rain only.** No temperature, no wind, no humidity.
- **The record is mostly monsoon.** 13 May to 5 November 2026, so it says
  little about winter rain, and nothing about a winter western disturbance.
- **A satellite estimate, not ground truth.** NASA IMERG is what the record
  checks against. It is not a rain gauge.
- **1 mm precision since 20 October 2026.** ECMWF changed the storage of its
  open data that day and the member totals arrive more coarsely rounded, so
  counts near a threshold are slightly coarser from then on.
- **The first day is usually tomorrow.** The 00 UTC run is published here
  around midday IST, and its first day is tomorrow, because today is already
  under way by then. In the morning, before that, the site is still showing
  the day before's run, whose first day is today.
- **One place at a time.** One square, one day, one amount: there is no
  "where will it rain most this week" view.
- **Lakshadweep is not forecast.** Of the 209 squares covering the group, not
  one has its centre on land. Searching Kavaratti says so.
- **Port Blair is not forecast.** Its square's land fraction is 0.0469,
  under the 0.5 the mask needs, as are all eight squares around it. Three
  other squares in the Andaman and Nicobar Islands are forecast.
- **Some squares inside India are white.** Inside the outline and not
  forecast, because their land fraction is under a half — mostly a coast or a
  narrow island. The colour key says so.
- **Zoomed out, a state shows its two letter code.** A full name is drawn
  only where the whole word fits inside that state at that zoom; a name
  written across the neighbours would be a false statement about where a
  place is.

## Future work

- **Temperature.** It would need its own checks and its own track record
  before it could be shown; a forecast without one is the thing this project
  exists not to publish.
- **Time Machine.** A view of what the runs said on seven chosen past days
  beside what the satellite then saw. Parked on the `time-machine` branch
  with its day-selection rule and the seven days chosen; dropped to spend the
  last day of the build on the interface.
- **The safest window.** Which of the five days has the fewest runs bringing
  rain, for somebody planning around it.
- **The backup daily trigger.** A Vercel cron hitting a small endpoint that
  starts the forecast workflow when GitHub's scheduler has not, which is the
  fix for the freshness problem above.
- **A larger city list, with state names in "near X" results**, so that
  "Near Budaun" can say which state Budaun is in.
- **Calibration, tested on held-out dates**, and a winter record, which is
  what it would take to turn these counts into chances honestly.
- **A larger headline count in the card**, which SPEC 11 allows only for a
  forecast carrying a "Good track record" label.

## Running it locally

The tests need Python 3.13.4 and node, and nothing else:

```powershell
python -m pip install -r requirements.txt
cd web; npm ci; cd ..
python -m pytest -q
```

The page, against the live published store:

```powershell
cd web; npm run dev
```

One live run, end to end, on this laptop. The first command builds the run
into `data/live/`; the second publishes it, and needs the Blob write token,
which lives in exactly one place — a GitHub Actions secret — so this step is
normally left to the workflow:

```powershell
python -m pipeline.run_live
python -m pipeline.publish
```

What the store says is published, with no token at all:

```powershell
python -m pipeline.publish remote-run-id
```

## How it is put together

| | |
|---|---|
| `pipeline/` | download, process, mask, check, publish — one run a day |
| `api/` | `health` and `place`, two Vercel functions, no token, no database |
| `web/` | React, Vite and MapLibre GL JS; the map is a chunk of its own |
| `tests/` | the test suite, run with `pytest` |
| `handchecks/` | checks run by hand against the original files |
| `results/` | the frozen verification output the site reads |
| `data/` | never committed |

`SPEC.md` is what the project does, section by section, and is the source of
truth; `DECISIONS.md` records the choices the code does not explain by
itself; `CLAUDE.md` holds the working rules. `CREDITS.md` has the licences in
full.

## Credits and licences

ECMWF open data is CC BY 4.0 and requires attribution. NASA IMERG is a
satellite estimate, not ground truth. The outline, the state lines and the
city names are Natural Earth, public domain. See [`CREDITS.md`](CREDITS.md).

---

## Running the historical downloads

Two background downloads built the historical archive behind the track
record. They are independent and can run at the same time.

| Pile | What | Dates | Script |
|---|---|---|---|
| A | ECMWF AIFS ENS 00 UTC forecasts | 13 May 2026 to 5 Nov 2026 | `scripts/run_pile_a.py` |
| B | NASA IMERG Late daily | 14 May 2026 to the latest available day | `scripts/run_pile_b.py` |

Pile A downloads about 300 MB per date, keeps a 19 MB India subset and deletes
the raw files. Pile B keeps its files, about 30 MB per day.

Both resume automatically: a date that already has a done record is skipped, so
re-running a launch command continues from where it stopped rather than
starting over. Neither ever needs a password typed in; Pile B uses the
Earthdata login already stored in netrc on this machine.

### Set the project folder first

Every command below starts with this line. Run it once per PowerShell window.

```powershell
$r = "C:\Users\Sumedha\Downloads\Projects\Precipitation-forecast"
```

### Start Pile A

```powershell
$p = Start-Process -FilePath "$r\.venv\Scripts\python.exe" -ArgumentList "scripts\run_pile_a.py" -WorkingDirectory $r -WindowStyle Hidden -RedirectStandardOutput "$r\data\logs\pile_a.out" -RedirectStandardError "$r\data\logs\pile_a.err" -PassThru
$p.Id | Set-Content -Encoding ascii "$r\data\logs\pile_a.pid"
```

### Start Pile B

```powershell
$p = Start-Process -FilePath "$r\.venv\Scripts\python.exe" -ArgumentList "scripts\run_pile_b.py" -WorkingDirectory $r -WindowStyle Hidden -RedirectStandardOutput "$r\data\logs\pile_b.out" -RedirectStandardError "$r\data\logs\pile_b.err" -PassThru
$p.Id | Set-Content -Encoding ascii "$r\data\logs\pile_b.pid"
```

`-WindowStyle Hidden` means no window appears. The process keeps running after
the terminal, or Claude Code, is closed.

### Progress, Pile A

```powershell
"{0}/{1} done, {2} failed, {3:N1} GB free | {4}" -f (Get-ChildItem "$r\data\logs\done" -Filter '2*.json').Count,(Get-Content "$r\data\logs\pile_a_manifest.json"|ConvertFrom-Json).total,(Get-ChildItem "$r\data\logs\failures" -Filter '2*.json' -EA SilentlyContinue).Count,((Get-PSDrive C).Free/1GB),(Get-Content "$r\data\logs\pile_a.log" -Tail 1)
```

### Progress, Pile B

```powershell
"{0}/{1} done, {2} failed, {3:N1} GB free | {4}" -f (Get-ChildItem "$r\data\logs\done" -Filter 'imerg_*.json').Count,(Get-Content "$r\data\logs\pile_b_manifest.json"|ConvertFrom-Json).total,(Get-ChildItem "$r\data\logs\failures" -Filter 'imerg_*.json' -EA SilentlyContinue).Count,((Get-PSDrive C).Free/1GB),(Get-Content "$r\data\logs\pile_b.log" -Tail 1)
```

### Stop

```powershell
Stop-Process -Id (Get-Content "$r\data\logs\pile_a.pid") -Force    # Pile A
Stop-Process -Id (Get-Content "$r\data\logs\pile_b.pid") -Force    # Pile B
```

Stopping is safe at any moment. A date that was partway through leaves no done
record, its part-downloaded files are thrown away on the next start, and that
date is redone from the beginning. Finished dates are never redone.

### The supervisor

On the night of 11-12 November 2026 a Wi-Fi drop at 02:05 froze Pile A for
7 hours 24 minutes. The socket read timeout did not catch it: the part-files
stopped growing and nothing moved or errored until the sockets finally
aborted, hours later.

`scripts/supervise.py` watches for exactly that. It runs as its own detached
process so the download code is never edited while a run is using it, and it
only ever kills and relaunches. It never touches data.

Every 2 minutes it looks at the newest of the pile's log file and any growing
part-file. If nothing has moved for 10 minutes it kills the pile by its PID
file, logs `watchdog restart` with the reason, and relaunches the same command,
which resumes from the done records. It gives up after 10 restarts.

If the pile ends with failures that are **all** network errors, the supervisor
archives those records and relaunches once more. Any other kind of error is
left alone for you to look at. It stops when every date is done.

**Start** (one per pile; `a` or `b`):

```powershell
$p = Start-Process -FilePath "$r\.venv\Scripts\python.exe" -ArgumentList "scripts\supervise.py","a" -WorkingDirectory $r -WindowStyle Hidden -RedirectStandardOutput "$r\data\logs\supervisor_a.out" -RedirectStandardError "$r\data\logs\supervisor_a.err" -PassThru
$p.Id | Set-Content -Encoding ascii "$r\data\logs\supervisor_a.pid"
```

**Progress:**

```powershell
"{0} restarts | {1}" -f (Select-String -Path "$r\data\logs\supervisor.log" -Pattern 'watchdog restart' -SimpleMatch).Count,(Get-Content "$r\data\logs\supervisor.log" -Tail 1)
```

**Stop:**

```powershell
Stop-Process -Id (Get-Content "$r\data\logs\supervisor_a.pid") -Force
```

Stop the supervisor **before** stopping a pile by hand, otherwise it will
restart the pile you just stopped.

### If something goes wrong

- Full history: `Get-Content "$r\data\logs\pile_a.log"`. It is appended to, not
  overwritten, so it survives restarts.
- Failed dates: `Get-ChildItem "$r\data\logs\failures"`. Each file holds the
  error and the traceback. A failed Pile A date keeps its raw files for
  inspection.
- To retry a failed date, delete its failure record and start the pile again.
- Both piles stop cleanly if free disk space falls below 15 GB.

### Running the hand checks

Run against any completed date to confirm the saved file matches the original
GRIB. Saved output is in `handchecks/results/`.

```powershell
& "$r\.venv\Scripts\python.exe" "$r\handchecks\hc1_compare_grib.py" 20260513
& "$r\.venv\Scripts\python.exe" "$r\handchecks\hc2_difference.py" 20260513
& "$r\.venv\Scripts\python.exe" "$r\handchecks\hc3_steps_members.py" 20260513
```

HC1 needs the raw GRIB for that date, which exists only for dates run with
`--keep-raw`. HC2 and HC3 work from the saved file alone.

The rest, in `handchecks/`, each write their own file into
`handchecks/results/`. SPEC's "The hand checks" section says what each one
redoes.

| | what it redoes | run it with |
|---|---|---|
| HC-ALIGN | the two grids against each other | `hc_align.py` |
| HC5 | one cell of the area-weighted remap | `hc5_cell.py` |
| HC6 | the 51 run values in one square | `hc6_members.py` |
| HC7 | the published bytes against the built run | `hc7_published.py` |
| HC8 | one square on the live map | `hc8_map_square.py` |
| HC9 | one reliability band, from the archive | `hc9_bucket.py` |
| HC-FAIL | the publisher, made to fail on purpose | `hc_fail.py` |
| HC-ECMWF | ECMWF's own figure for 10 mm against our count | `hc_ecmwf.py` |
| HC-REPORT | the report card's Brier scores, redone | `hc_report.py` |
| HC-GHATS | one monsoon day of remapped IMERG, drawn | `hc_ghats.py` |

Three of them take a `--sabotage` flag, which breaks the thing on purpose to
show the check notices.

HC-ECMWF downloads about 350 KB from ECMWF and needs the run it compares to
be one the server still offers, which is the last four days. HC-FAIL's third
part serves the site against a copy of a published run so the 36-hour banner
can be seen:

```powershell
node "$r\handchecks\hc_fail_site.mjs" 20261112T00Z 5102
```

---

## How this was built, and the help I used

All of the code, data processing, tests and deployment in this repository were produced by Claude Code in a single session, from 11 November 2026 at 11:56 pm IST to its final commit on 14 November 2026. The full session log is submitted with this application. Before the session I practised the downloads, map and checks on my own; none of that practice code or data was reused, and I said so in the session's first prompt.

Alongside the session, I used a separate Claude chat in the Claude desktop app as an advisor. I used it to review Claude Code's reports, point out risks and gaps, explain things I didn't understand, keep track of my schedule, and polish the prompts I sent to Claude Code. Every prompt went through me: I read it, questioned it, often asked for changes, and decided whether and when to send it. I asked it repeatedly to challenge me rather than agree with me. Some independent checks came from that chat, such as recomputing one remapped square by hand (HC5) and checking news reports of the 406 mm day.

For the user interface I also used ChatGPT and a second Claude chat to critique the site, compare it with other weather websites, and produce mock-up images that I used as design references. None of their code went into this repository.

The decisions were mine throughout. I read every report and prompt, asked questions until I understood them, stuck to my plan where I believed it was right, and changed it when the evidence said so. There were many more such decisions; these are some of the major ones:

- **Found a phone bug on my own Samsung A32** (and my mother's Oppo): the "Show the details" handle was hidden under the phone's bottom bar, so the forecast panel couldn't be opened. Desktop testing had not shown it. The cause turned out to be a layout rule, and it was fixed and tested on both phones.
- **Noticed the map didn't move to a searched place:** when I used "Use my location" or searched for Delhi, the map circled the place but didn't slide to it, so I asked for it to move there automatically.
- **Caught that the hand checks had drifted from my original plan:** several checks I had planned (failure handling, a comparison with ECMWF's own published figure, real report-card rows, a monsoon map) had been renumbered or not done. I had them added, and one of them found a mistake in the specification.
- **Asked for every line on the "How we checked" page to be verified against its file,** which corrected two entries (one check had run on three dates, not one; another covered five squares, not one).
- **Found gaps in the search:** it said "town" but only knew cities, and typing a state such as West Bengal found nothing. That led to the city wording, state search and old city names.
- **Pushed back on wording a beginner wouldn't understand:** for example "1 cm deep" for 10 mm, and "tap a square" when the squares aren't visible until you zoom in.
- **Made sure dry places read correctly and the track record states its period:** 0 of 51 runs in Delhi in November is the right answer, not missing data, and the report card says its record comes mostly from the monsoon.
- **Checked the GitHub scheduler myself,** found it firing late (in the evening or at night, never when the new forecast arrives around midday), ran the forecast by hand when needed, and designed a backup daily trigger, which I chose to leave as future work so the last hours went to the interface.
- **Dropped the Time Machine feature** I had planned, to spend the last day on the interface after real users struggled with it.
- **Kept the security rules myself:** I never put a password or token in a prompt; I created the secrets in the GitHub and Vercel dashboards by hand.

To test the interface, I asked my mother and several friends to use the site without help and tell me what they struggled with. They all said much the same: it was hard to see where to start, there was too much text, and the numbers were hard to understand. I also asked for the site to be compared with other weather apps. That feedback is the reason for the final, simpler design.

This section was drafted with the help of the same Claude chat and edited by me.
