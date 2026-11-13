# Precipitation Forecast App

**India rain forecast: how many of 51 model runs say rain.**

India precipitation forecast from the ECMWF AIFS ENS 51-member ensemble, to
be checked against NASA IMERG satellite estimates. The point of the project is
an honest, published track record: it does not exist yet, and the site says so
rather than implying one.

**Live: <https://precipitation-forecast-app.vercel.app>**

| | |
|---|---|
| the page | <https://precipitation-forecast-app.vercel.app> |
| what is published now | <https://precipitation-forecast-app.vercel.app/api/health> |
| one square | `/api/place?lat=28.5&lon=77.25` |

## What the site shows

A map of India in 0.25 degree squares, about 28 km across, 4,613 of them.
Every square is coloured by **how many of the 51 model runs** give at least
the chosen amount of rain in the chosen day: 1 mm, 10 mm or 50 mm, over the
next five days. Darker is more runs.

The model is ECMWF's AIFS ENS, run 51 times a day from slightly different
starting points. The 00 UTC run is downloaded, totalled into five IST days,
counted against the three thresholds and published once a day by
`.github/workflows/forecast.yml`.

Choose a square by clicking it, by searching one of 215 Indian towns, by
typing a latitude and longitude, or with "use my location". The panel then
says, in words and numbers:

- the three counts for that day, out of 51, and the five days together
- one sentence saying what the counts mean
- a dot for each of the 51 runs
- what each of the 51 runs gives, in whole millimetres

Everything the map shows is also written in the panel, so nothing is only
available by clicking a picture. If the map cannot be drawn at all — an old
browser, no WebGL 2 — the page says so and all of that still works.

## How to read it

**A square is the smallest place this site can answer about.** The forecast
has no detail finer than 0.25 degrees, so a town is shown as the square it
falls in, and two towns in one square get the same numbers.

**The colour is a count, not a probability.** "18 of 51" means 18 of the 51
runs reached 1 mm in that square on that day. It is not the same thing as a
35 in 100 chance of rain: turning counts into chances takes a record of what
actually happened, and there is not one yet.

**Every time on the page is IST.** The model's day runs 5:30 am to 5:30 am.

## The limits, in full

- **0.25 degree squares.** Nothing finer exists in this forecast. Hills,
  cities and coastlines inside one square are not distinguished.
- **Lakshadweep is not forecast.** Of the 209 squares covering the group, not
  one has its centre on land: every island there is far smaller than one
  square. Searching Kavaratti says so.
- **Port Blair is not forecast.** Its square is inside the drawn outline, but
  the model's own land fraction for it is 0.0469, under the 0.5 the mask
  needs, as are all eight squares around it. Three other squares in the
  Andaman and Nicobar Islands are land on this grid and are forecast.
- **Counts are not probabilities,** and no percentage is shown anywhere.
- **No track record is published yet.** The verification against NASA IMERG
  (section 5 of `SPEC.md`) has not been run, so there is no report card and
  no trust label. When there is, it will say which period it covers.
- **NASA IMERG is a satellite estimate, not ground truth.** It is what the
  forecast will be checked against; it is not a measurement of what fell.
- **There is no basemap.** Nothing on the map comes from a third party: the
  outline, the state lines, the state names, the town names and the land
  around India are all Natural Earth, public domain, and the squares are
  ours. The land around India is shaded so it does not read as ocean, from a
  layer that is coastline only: the one national boundary this site draws is
  India's own outline.
- **Zoomed out, a state shows its two letter code.** A state's full name is
  written only where the whole word fits inside that state at the zoom you
  are looking at, which at the whole-country view is almost nowhere: a word
  14 pixels tall is most of a degree, and most states are narrower than their
  own names. Zoom in and the names appear. A name written across the
  neighbours would be a false statement about where a place is.
- **Some squares inside India are white.** They are inside the outline and
  not forecast, because the model's own land fraction for them is under a
  half — mostly a coast or a narrow island. The legend says so.
- **Not an official warning.** For warnings and advisories, see the
  [India Meteorological Department](https://mausam.imd.gov.in/).

## How it is put together

| | |
|---|---|
| `pipeline/` | download, process, mask, check, publish — one run a day |
| `api/` | `health` and `place`, two Vercel functions, no token, no database |
| `web/` | React, Vite and MapLibre GL JS; the map is a chunk of its own |
| `tests/` | the test suite, run with `pytest` |
| `handchecks/` | checks run by hand against the original files |
| `data/` | never committed |

See `SPEC.md` for what the project does and `CLAUDE.md` for the working rules.
Section 11 of `SPEC.md` covers the page and the two functions; section 8
covers publishing. `CREDITS.md` has the licences in full.

---

## Running the historical downloads

Two background downloads build the historical archive used for the track
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

### Hand checks

Run against any completed date to confirm the saved file matches the original
GRIB. Saved output for 13 May and 25 October 2026 is in `handchecks/results/`.

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
| HC6 | the 51 member values in one square | `hc6_members.py` |
| HC7 | the published bytes against the built run | `hc7_published.py` |
| HC8 | one square on the live map | `hc8_map_square.py` |
| HC9 | one reliability band, from the archive | `hc9_bucket.py` |
| HC-FAIL | the publisher, made to fail on purpose | `hc_fail.py` |
| HC-ECMWF | ECMWF's own probability of 10 mm against our count | `hc_ecmwf.py` |
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

## Credits and licences

ECMWF open data is CC-BY-4.0 and requires attribution. NASA IMERG is a
satellite estimate, not ground truth. See `CREDITS.md`.
