# Precipitation Forecast App

India precipitation forecast from the ECMWF AIFS ENS 51-member ensemble,
verified against NASA IMERG satellite estimates, with a published track record.

See `SPEC.md` for what the project does and `CLAUDE.md` for the working rules.

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

---

## Credits and licences

ECMWF open data is CC-BY-4.0 and requires attribution. NASA IMERG is a
satellite estimate, not ground truth. See `CREDITS.md`.
