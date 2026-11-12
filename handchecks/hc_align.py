"""HC-ALIGN: prove the two grids are aligned, and that cnt is not constant.

Read-only. Nothing is written except handchecks/results/hc_align.txt.

Three questions:

1. Is `precipitation_cnt` actually a variable, or is it 48 everywhere? If it
   were constant the completeness rule of SPEC 3.4 would be untestable.
2. Is the forecast grid paired with the right IMERG day, the right way up and
   the right way round? Spatial correlation is computed for the correct
   pairing and for eight wrong ones. The correct pairing has to win.
3. One named square on one date, with the ensemble numbers and the
   observation side by side.

Usage: python handchecks/hc_align.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.ecmwf_process import daily_totals              # noqa: E402
from pipeline.india_mask import load as load_mask            # noqa: E402
from pipeline.nasa_download import existing_file             # noqa: E402
from pipeline.nasa_process import imerg_date_for, nasa_path  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "hc_align.txt"

CNT_DATE = "20260722"          # the wettest India day in the archive
WANTED_RUN = "20260721"        # part 3 asks for this run
WANTED_LAT, WANTED_LON = 20.25, 72.75

lines: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)
    lines.append(text)


# ------------------------------------------------------------------- part 1

def part_one() -> None:
    say("=" * 72)
    say("1. Is precipitation_cnt constant 48?")
    say("=" * 72)

    path = existing_file(CNT_DATE)
    if path is None:
        say(f"   no IMERG file for {CNT_DATE}")
        return

    with h5py.File(path, "r") as f:
        cnt = np.asarray(f["precipitation_cnt"][0], dtype=np.int16)

    say(f"   file  {path.name}")
    say(f"   shape {cnt.shape} (lon, lat), {cnt.size:,} pixels")
    say(f"   global minimum {int(cnt.min())}, maximum {int(cnt.max())}")
    say("")
    say("   histogram of every value present, whole globe:")
    say(f"     {'cnt':>5s} {'pixels':>12s} {'share':>9s}")
    values, counts = np.unique(cnt, return_counts=True)
    for v, c in zip(values, counts):
        say(f"     {int(v):5d} {int(c):12,d} {100 * c / cnt.size:8.4f}%")
    say("")
    say(f"   values below 48: {int((cnt < 48).sum()):,} pixels "
        f"({100 * (cnt < 48).sum() / cnt.size:.4f}% of the globe)")
    say(f"   distinct values present: {len(values)}")
    say("   So the variable is not constant. It is 48 over India on every")
    say("   day in the archive, which is a fact about India's coverage, not")
    say("   about the variable (SPEC 3.7).")
    say("")


# ------------------------------------------------------------------- part 2

def pearson(a: np.ndarray, b: np.ndarray) -> float:
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 100:
        return float("nan")
    x, y = a[ok].astype(np.float64), b[ok].astype(np.float64)
    x -= x.mean()
    y -= y.mean()
    denom = np.sqrt((x * x).sum() * (y * y).sum())
    return float((x * y).sum() / denom) if denom > 0 else float("nan")


def shift(field: np.ndarray, drow: int, dcol: int) -> np.ndarray:
    """Sample the field at (i + drow, j + dcol), NaN outside. No wrapping."""
    out = np.full_like(field, np.nan, dtype=np.float64)
    n_row, n_col = field.shape
    r_lo, r_hi = max(0, -drow), min(n_row, n_row - drow)
    c_lo, c_hi = max(0, -dcol), min(n_col, n_col - dcol)
    out[r_lo:r_hi, c_lo:c_hi] = field[r_lo + drow:r_hi + drow,
                                      c_lo + dcol:c_hi + dcol]
    return out


def ecmwf_day1_mean(date: str) -> np.ndarray | None:
    path = cfg.india_path(date)
    if not path.exists():
        return None
    with np.load(path) as f:
        tp = f["tp"]
    return daily_totals(tp)[0].mean(axis=0).astype(np.float64)


def imerg_rain(date: str) -> np.ndarray | None:
    if not nasa_path(date).exists():
        return None
    with np.load(nasa_path(date)) as f:
        return f["rain"].astype(np.float64)


def other_day(date: str, offset: int) -> str:
    day = dt.datetime.strptime(date, "%Y%m%d").date()
    return (day + dt.timedelta(days=offset)).strftime("%Y%m%d")


def part_two() -> bool:
    say("=" * 72)
    say("2. Is the pairing right? Spatial correlation over India squares")
    say("=" * 72)
    say("   Forecast side: lead day 1 ensemble mean, steps 24 to 48.")
    say("   Observed side: IMERG for imerg_date_for(R, 1) = R + 1.")
    say("   Correlation is Pearson's r across India squares within one date,")
    say("   then averaged over dates. Shifts move the IMERG map, so")
    say("   'one cell north' compares our square with the IMERG square")
    say("   0.25 degrees to its south.")
    say("")

    india = load_mask()["india"]
    runs = sorted(p.stem for p in cfg.DONE.glob("2*.json"))

    # (label, day offset applied to R+1, row offset, col offset, flip)
    variants = [
        ("correct pairing", 0, 0, 0, False),
        ("IMERG one day earlier", -1, 0, 0, False),
        ("IMERG one day later", +1, 0, 0, False),
        ("IMERG one cell north", 0, +1, 0, False),
        ("IMERG one cell south", 0, -1, 0, False),
        ("IMERG one cell east", 0, 0, -1, False),
        ("IMERG one cell west", 0, 0, +1, False),
        ("IMERG flipped north-south", 0, 0, 0, True),
    ]
    totals: dict[str, list[float]] = {label: [] for label, *_ in variants}

    used = []
    for run in runs:
        forecast = ecmwf_day1_mean(run)
        if forecast is None:
            continue
        base = imerg_date_for(run, 1)
        needed = [other_day(base, off) for off in (-1, 0, 1)]
        if any(imerg_rain(d) is None for d in needed):
            continue

        used.append(run)
        f_india = np.where(india, forecast, np.nan)
        for label, day_off, drow, dcol, flip in variants:
            obs = imerg_rain(other_day(base, day_off))
            if flip:
                obs = obs[::-1, :]
            if drow or dcol:
                obs = shift(obs, drow, dcol)
            o_india = np.where(india, obs, np.nan)
            r = pearson(f_india, o_india)
            if np.isfinite(r):
                totals[label].append(r)

    if not used:
        say("   no date had both a forecast file and the three IMERG days")
        return False

    say(f"   dates used: {len(used)}  ({used[0]} to {used[-1]})")
    say(f"   India squares per date: {int(india.sum()):,}")
    say("")
    say(f"   {'pairing':30s} {'mean r':>8s} {'min r':>8s} {'max r':>8s} "
        f"{'dates':>6s}")
    ranked = []
    for label, *_ in variants:
        values = np.asarray(totals[label])
        mean = float(values.mean())
        ranked.append((mean, label))
        say(f"   {label:30s} {mean:8.4f} {values.min():8.4f} "
            f"{values.max():8.4f} {values.size:6d}")

    ranked.sort(reverse=True)
    best_mean, best_label = ranked[0]
    correct_mean = float(np.asarray(totals["correct pairing"]).mean())
    say("")
    say(f"   highest average: {best_label} at r = {best_mean:.4f}")
    runner_up = ranked[1]
    say(f"   next best:       {runner_up[1]} at r = {runner_up[0]:.4f}")
    say(f"   margin:          {best_mean - runner_up[0]:.4f}")

    ok = best_label == "correct pairing"
    if ok:
        say("   PASS: the correct pairing wins, so the day mapping, the")
        say("   latitude direction and the longitude direction are all right.")
    else:
        say("   FAIL by the rule as written: a wrong pairing beat the")
        say("   correct one. Two diagnostics below say what kind of failure")
        say("   this is before anyone acts on it.")
    say("")

    # ---- diagnostic A: is the winner a real winner, or a coin flip?
    say("   DIAGNOSTIC A: paired per-date comparison against the winner")
    correct = np.asarray(totals["correct pairing"])
    for _, label in ranked[:3]:
        if label == "correct pairing":
            continue
        other = np.asarray(totals[label])
        diff = correct - other
        wins = int((diff > 0).sum())
        say(f"     correct vs {label}:")
        say(f"       correct higher on {wins} of {diff.size} dates")
        say(f"       mean difference {diff.mean():+.5f}, "
            f"standard deviation {diff.std(ddof=1):.5f}")
        say(f"       standard error of the mean {diff.std(ddof=1) / np.sqrt(diff.size):.5f}")
    say("")

    # ---- diagnostic B: two cells out, to show the shape of the curve
    say("   DIAGNOSTIC B: the same correlation at two cells out")
    say("   If a one-cell shift were a real misalignment, two cells in that")
    say("   direction would not fall away sharply.")
    india = load_mask()["india"]
    far = {f"{n} cell(s) {d}": [] for n in (1, 2)
           for d in ("north", "south", "east", "west")}
    for run in used:
        forecast = ecmwf_day1_mean(run)
        f_india = np.where(india, forecast, np.nan)
        obs = imerg_rain(imerg_date_for(run, 1))
        for n in (1, 2):
            for name, (drow, dcol) in {
                "north": (+n, 0), "south": (-n, 0),
                "east": (0, -n), "west": (0, +n),
            }.items():
                moved = np.where(india, shift(obs, drow, dcol), np.nan)
                r = pearson(f_india, moved)
                if np.isfinite(r):
                    far[f"{n} cell(s) {name}"].append(r)
    say(f"     {'shift':22s} {'mean r':>8s} {'vs correct':>11s}")
    say(f"     {'none (correct)':22s} {correct.mean():8.4f} {0.0:+11.4f}")
    for key, values in far.items():
        arr = np.asarray(values)
        say(f"     {key:22s} {arr.mean():8.4f} "
            f"{arr.mean() - correct.mean():+11.4f}")
    say("")
    return ok


# ------------------------------------------------------------------- part 3

def part_three() -> None:
    say("=" * 72)
    say("3. One square, one run, both sides")
    say("=" * 72)

    runs = sorted(p.stem for p in cfg.DONE.glob("2*.json"))
    if WANTED_RUN in runs:
        run = WANTED_RUN
        note = "the run asked for"
    else:
        wanted = dt.datetime.strptime(WANTED_RUN, "%Y%m%d").date()
        run = min(runs, key=lambda d: abs(
            (dt.datetime.strptime(d, "%Y%m%d").date() - wanted).days))
        gap = (dt.datetime.strptime(run, "%Y%m%d").date() - wanted).days
        note = (f"nearest done date to {WANTED_RUN}, which is not done; "
                f"{abs(gap)} day(s) {'later' if gap > 0 else 'earlier'}")

    i = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LATS) - WANTED_LAT)))
    j = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LONS) - WANTED_LON)))
    india = load_mask()["india"]

    with np.load(cfg.india_path(run)) as f:
        tp = f["tp"]
    totals = daily_totals(tp)

    say(f"   run            {run}  ({note})")
    say(f"   square         {cfg.INDIA_LATS[i]} N, {cfg.INDIA_LONS[j]} E  "
        f"(India square: {bool(india[i, j])})")
    say("")

    for lead in (1, 2):
        members = totals[lead - 1, :, i, j].astype(np.float64)
        obs_date = imerg_date_for(run, lead)
        obs = imerg_rain(obs_date)
        label = "LEAD DAY 1, as asked" if lead == 1 else (
            "LEAD DAY 2, added because this is the day the 406 mm fell")
        say(f"   {label}")
        say(f"     steps                 {24 * lead} to {24 * (lead + 1)}")
        say(f"     IMERG date            {obs_date}")
        say(f"     ensemble mean mm      {members.mean():.4f}")
        say(f"     ensemble max mm       {members.max():.4f}")
        say(f"     ensemble min mm       {members.min():.4f}")
        say(f"     members >= 50 mm      {int((members >= 50).sum())} of 51")
        say(f"     members >= 10 mm      {int((members >= 10).sum())} of 51")
        say(f"     members >= 1 mm       {int((members >= 1).sum())} of 51")
        if obs is None:
            say("     IMERG mm              not processed")
        else:
            say(f"     IMERG mm              {obs[i, j]:.4f}")
        say("")


# ------------------------------------------------------------------- part 4
# A half-cell offset in both directions is what a centre-versus-corner
# mistake looks like, so the correlation surface is mapped properly rather
# than sampled at whole cells. Everything below is read-only: the weights are
# rebuilt here on shifted copies of the cell edges, and the local builder is
# proved identical to pipeline/nasa_process.py at zero shift before it is
# trusted anywhere else.

SHIFTS = (-0.25, -0.20, -0.15, -0.125, -0.10, -0.05, 0.0,
          0.05, 0.10, 0.125, 0.15, 0.20, 0.25)
PAD_DEGREES = 0.45          # covers the largest shift plus a half cell
HALF = cfg.GRID_STEP / 2.0

# SPEC 5.4: IMD's four homogeneous regions, by the state a centre falls in.
STATE_REGION = {
    "Uttar Pradesh": "Northwest India", "Uttarakhand": "Northwest India",
    "Haryana": "Northwest India", "Chandigarh": "Northwest India",
    "Delhi": "Northwest India", "Punjab": "Northwest India",
    "Himachal Pradesh": "Northwest India",
    "Jammu and Kashmir": "Northwest India", "Ladakh": "Northwest India",
    "Rajasthan": "Northwest India",
    "Odisha": "Central India", "Madhya Pradesh": "Central India",
    "Gujarat": "Central India", "Goa": "Central India",
    "Dadra and Nagar Haveli and Daman and Diu": "Central India",
    "Maharashtra": "Central India", "Chhattisgarh": "Central India",
    "Andaman and Nicobar": "South Peninsula",
    "Andhra Pradesh": "South Peninsula", "Telangana": "South Peninsula",
    "Tamil Nadu": "South Peninsula", "Puducherry": "South Peninsula",
    "Karnataka": "South Peninsula", "Kerala": "South Peninsula",
    "Lakshadweep": "South Peninsula",
    "Arunachal Pradesh": "East & Northeast India",
    "Assam": "East & Northeast India", "Meghalaya": "East & Northeast India",
    "Nagaland": "East & Northeast India", "Manipur": "East & Northeast India",
    "Mizoram": "East & Northeast India", "Tripura": "East & Northeast India",
    "Sikkim": "East & Northeast India",
    "West Bengal": "East & Northeast India",
    "Jharkhand": "East & Northeast India", "Bihar": "East & Northeast India",
}
REGION_ORDER = ("Northwest India", "Central India", "South Peninsula",
                "East & Northeast India")


def sind(x):
    return np.sin(np.deg2rad(x))


def padded_window(lat_edges, lon_edges):
    """Pixel window wide enough for every shift, as slices and edge arrays."""
    lat_lo = min(cfg.INDIA_LATS) - HALF - PAD_DEGREES
    lat_hi = max(cfg.INDIA_LATS) + HALF + PAD_DEGREES
    lon_lo = min(cfg.INDIA_LONS) - HALF - PAD_DEGREES
    lon_hi = max(cfg.INDIA_LONS) + HALF + PAD_DEGREES

    lat_hit = np.nonzero((lat_edges[1:] > lat_lo) & (lat_edges[:-1] < lat_hi))[0]
    lon_hit = np.nonzero((lon_edges[1:] > lon_lo) & (lon_edges[:-1] < lon_hi))[0]
    lat_slice = slice(int(lat_hit[0]), int(lat_hit[-1]) + 1)
    lon_slice = slice(int(lon_hit[0]), int(lon_hit[-1]) + 1)

    lat_edges_w = lat_edges[lat_slice.start:lat_slice.stop + 1]
    lon_edges_w = lon_edges[lon_slice.start:lon_slice.stop + 1]
    return lat_slice, lon_slice, lat_edges_w[::-1], lon_edges_w


def build_shifted(lat_desc, lon_asc, dlat: float, dlon: float):
    """The SPEC 3.3 weights for cell edges moved by (dlat north, dlon east).

    Same formula as pipeline/nasa_process.build_remap, applied to shifted
    copies of the target cell edges. Proved equal to it at (0, 0) below.
    """
    n_lat_w = lat_desc.size - 1
    n_lon_w = lon_asc.size - 1
    lat_top_p, lat_bot_p = lat_desc[:-1], lat_desc[1:]
    lon_left_p, lon_right_p = lon_asc[:-1], lon_asc[1:]

    cell_top = np.asarray(cfg.INDIA_LATS, dtype=np.float64) + HALF + dlat
    cell_bot = np.asarray(cfg.INDIA_LATS, dtype=np.float64) - HALF + dlat
    cell_left = np.asarray(cfg.INDIA_LONS, dtype=np.float64) - HALF + dlon
    cell_right = np.asarray(cfg.INDIA_LONS, dtype=np.float64) + HALF + dlon

    lat_parts = []
    for i in range(cfg.N_LAT):
        top = np.minimum(lat_top_p, cell_top[i])
        bot = np.maximum(lat_bot_p, cell_bot[i])
        overlap = sind(top) - sind(bot)
        keep = np.nonzero(overlap > 0)[0]
        lat_parts.append((keep, overlap[keep]))

    lon_parts = []
    for j in range(cfg.N_LON):
        right = np.minimum(lon_right_p, cell_right[j])
        left = np.maximum(lon_left_p, cell_left[j])
        overlap = right - left
        keep = np.nonzero(overlap > 0)[0]
        lon_parts.append((keep, overlap[keep]))

    rows, pix, weight = [], [], []
    for i in range(cfg.N_LAT):
        lat_idx, lat_w = lat_parts[i]
        for j in range(cfg.N_LON):
            lon_idx, lon_w = lon_parts[j]
            block = lat_w[:, None] * lon_w[None, :]
            flat = lat_idx[:, None] * n_lon_w + lon_idx[None, :]
            rows.append(np.full(block.size, i * cfg.N_LON + j, dtype=np.int32))
            pix.append(flat.ravel().astype(np.int32))
            weight.append(block.ravel())

    rows = np.concatenate(rows)
    pix = np.concatenate(pix)
    weight = np.concatenate(weight)
    cell_area = (cfg.GRID_STEP * (sind(cell_top) - sind(cell_bot))
                 )[:, None] * np.ones((1, cfg.N_LON))
    cell_area = cell_area.ravel()

    summed = np.bincount(rows, weights=weight, minlength=cell_area.size)
    worst = float(np.max(np.abs(summed - cell_area) / cell_area))
    if worst > 1e-9:
        raise RuntimeError(
            f"shift ({dlat}, {dlon}): weights do not sum to the cell area, "
            f"worst {worst:.2e}; the padded window is too small")
    return rows, pix, weight, cell_area


def remap_local(rows, pix, weight, cell_area, rain, cnt):
    """Same arithmetic as pipeline/nasa_process.remap, on a padded window."""
    from pipeline.nasa_process import COMPLETE_CNT, MIN_COMPLETE_FRACTION

    values = rain.ravel()
    complete = (cnt.ravel() == COMPLETE_CNT) & np.isfinite(values)
    ok = complete[pix]
    numerator = np.bincount(rows, weights=np.where(ok, values[pix], 0.0) * weight,
                            minlength=cell_area.size)
    denominator = np.bincount(rows, weights=weight * ok,
                              minlength=cell_area.size)
    fraction = denominator / cell_area
    usable = fraction >= MIN_COMPLETE_FRACTION - 1e-12
    out = np.full(cell_area.size, np.nan)
    np.divide(numerator, denominator, out=out, where=usable & (denominator > 0))
    out[~usable] = np.nan
    return out.reshape(cfg.N_LAT, cfg.N_LON)


def region_map():
    """Region name per India square, or None if the admin-1 file is absent."""
    try:
        import shapefile
        from shapely.geometry import Point, shape
        from shapely.prepared import prep
        from shapely.strtree import STRtree
    except ImportError:
        return None
    path = cfg.RAW / "ne" / "ne_10m_admin_1_states_provinces"
    if not path.with_suffix(".shp").exists():
        return None

    reader = shapefile.Reader(str(path))
    fields = [f[0] for f in reader.fields[1:]]
    i_admin, i_name = fields.index("admin"), fields.index("name")
    names, geoms = [], []
    for sr in reader.shapeRecords():
        if sr.record[i_admin] == "India":
            names.append(sr.record[i_name])
            geoms.append(shape(sr.shape.__geo_interface__))
    tree = STRtree(geoms)
    prepared = [prep(g) for g in geoms]

    india = load_mask()["india"]
    out = np.full((cfg.N_LAT, cfg.N_LON), "", dtype=object)
    for i in range(cfg.N_LAT):
        for j in range(cfg.N_LON):
            if not india[i, j]:
                continue
            point = Point(cfg.INDIA_LONS[j], cfg.INDIA_LATS[i])
            found = None
            for k in tree.query(point):
                if prepared[k].covers(point):
                    found = names[k]
                    break
            out[i, j] = (STATE_REGION[found] if found
                         else "Northwest India")   # SPEC 5.4 rule 3
    return out


def part_four() -> None:
    import h5py

    from pipeline.nasa_process import (FILL_TOLERANCE, FILL_VALUE,
                                       build_remap, read_grid, read_window,
                                       remap as pipeline_remap)

    say("")
    say("=" * 72)
    say("4. Mapping the correlation surface on a fine shift grid")
    say("=" * 72)
    say("   Added 12 November 2026 because the whole-cell scan was not")
    say("   symmetric: 0.5666 at one cell south, 0.5863 unshifted, 0.5865 at")
    say("   one cell north, 0.5678 at two cells north, and east ahead of")
    say("   west by 0.016. That shape peaks near half a cell, which is what")
    say("   a centre-versus-corner mistake would produce.")
    say("")
    say("   SIGN CONVENTION, stated once because everything turns on it:")
    say("   dlat and dlon move the TARGET CELL EDGES, positive north and")
    say("   east. Moving our cell north makes it read IMERG from further")
    say("   north, which is the same as moving the IMERG map SOUTH, so")
    say("   positive dlat here is the opposite direction to 'IMERG one cell")
    say("   north' in part 2. Both conventions are reported at the peak.")
    say("")

    runs = sorted(p.stem for p in cfg.DONE.glob("2*.json"))
    usable_runs = [
        run for run in runs
        if cfg.india_path(run).exists()
        and nasa_path(imerg_date_for(run, 1)).exists()
        and existing_file(imerg_date_for(run, 1)) is not None
    ]
    if not usable_runs:
        say("   no usable dates")
        return

    india = load_mask()["india"]

    sample = existing_file(imerg_date_for(usable_runs[0], 1))
    with h5py.File(sample, "r") as f:
        lat_edges, lon_edges = read_grid(f, sample.name)
    lat_slice, lon_slice, lat_desc_w, lon_asc_w = padded_window(lat_edges,
                                                                lon_edges)
    say(f"   padded pixel window: {lat_desc_w.size - 1} latitudes x "
        f"{lon_asc_w.size - 1} longitudes, pad {PAD_DEGREES} degrees")

    def padded(path):
        with h5py.File(path, "r") as f:
            rain = np.asarray(f["precipitation"][0, lon_slice, lat_slice],
                              dtype=np.float64).T[::-1, :]
            cnt = np.asarray(f["precipitation_cnt"][0, lon_slice, lat_slice],
                             dtype=np.int16).T[::-1, :]
        rain = np.where(np.isclose(rain, FILL_VALUE, rtol=0.0,
                                   atol=FILL_TOLERANCE), np.nan, rain)
        return rain, cnt

    # ---- prove the local builder equals the pipeline at zero shift
    probe_date = imerg_date_for(usable_runs[0], 1)
    probe_file = existing_file(probe_date)
    with h5py.File(probe_file, "r") as f:
        pipeline_remapper = build_remap(lat_edges, lon_edges)
        rain_p, cnt_p, _ = read_window(f, pipeline_remapper, probe_date,
                                       probe_file.name)
    reference, _ = pipeline_remap(pipeline_remapper, rain_p, cnt_p)
    zero_weights = build_shifted(lat_desc_w, lon_asc_w, 0.0, 0.0)
    mine = remap_local(*zero_weights, *padded(probe_file))
    worst = float(np.nanmax(np.abs(mine - reference)))
    say(f"   local builder vs pipeline at zero shift: worst difference "
        f"{worst:.3e} mm over {int(np.isfinite(reference).sum()):,} cells")
    if worst > 1e-9:
        say("   STOP: the local builder does not reproduce the pipeline, so")
        say("   nothing below can be attributed to the grids.")
        return
    say("   identical, so the surface below is a property of the data and")
    say("   not of this script.")
    say("")

    # ---- cache forecasts and padded observation windows
    say(f"   caching {len(usable_runs)} dates ...")
    forecasts, obs1, obs3 = {}, {}, {}
    for run in usable_runs:
        with np.load(cfg.india_path(run)) as f:
            totals = daily_totals(f["tp"])
        forecasts[run] = {
            "day1_mean": totals[0].mean(axis=0).astype(np.float64),
            "day3_mean": totals[2].mean(axis=0).astype(np.float64),
            "day1_control": totals[0, 0].astype(np.float64),
        }
        obs1[run] = padded(existing_file(imerg_date_for(run, 1)))
        third = existing_file(imerg_date_for(run, 3))
        if third is not None and nasa_path(imerg_date_for(run, 3)).exists():
            obs3[run] = padded(third)

    regions = region_map()
    slices = {"all India, day 1, mean": (None, "day1_mean", 1)}
    if regions is not None:
        for name in REGION_ORDER:
            slices[name] = (regions == name, "day1_mean", 1)
    slices["all India, day 3, mean"] = (None, "day3_mean", 3)
    slices["all India, day 1, control"] = (None, "day1_control", 1)

    masks = {label: (india if where is None else (india & where))
             for label, (where, _, _) in slices.items()}

    # ---- one pass over the shift grid; every slice measured at each shift
    results = {label: np.zeros((len(SHIFTS), len(SHIFTS))) for label in slices}
    counts = {label: 0 for label in slices}
    for a, dlat in enumerate(SHIFTS):
        for b, dlon in enumerate(SHIFTS):
            weights = build_shifted(lat_desc_w, lon_asc_w, dlat, dlon)
            per_slice = {label: [] for label in slices}
            for run in usable_runs:
                mapped1 = remap_local(*weights, *obs1[run])
                mapped3 = (remap_local(*weights, *obs3[run])
                           if run in obs3 else None)
                for label, (_, field, lead) in slices.items():
                    mapped = mapped1 if lead == 1 else mapped3
                    if mapped is None:
                        continue
                    mask = masks[label]
                    r = pearson(np.where(mask, forecasts[run][field], np.nan),
                                np.where(mask, mapped, np.nan))
                    if np.isfinite(r):
                        per_slice[label].append(r)
            for label, values in per_slice.items():
                results[label][a, b] = float(np.mean(values))
                counts[label] = len(values)
        say(f"     dlat {dlat:+.3f} done")

    main_label = "all India, day 1, mean"
    surface = results[main_label]
    zero_index = SHIFTS.index(0.0)
    zero_r = surface[zero_index, zero_index]

    say("")
    say(f"   dates: {len(usable_runs)}  ({usable_runs[0]} to "
        f"{usable_runs[-1]})")
    say("   mean r, lead day 1 ensemble mean, all India squares")
    say("")
    say("   dlat/dlon " + "".join(f"{d:>+8.3f}" for d in SHIFTS))
    for a, dlat in enumerate(SHIFTS):
        say(f"   {dlat:>+9.3f} " + "".join(f"{v:8.4f}" for v in surface[a]))
    say("")

    pa, pb = divmod(int(np.argmax(surface)), len(SHIFTS))
    peak_lat, peak_lon = SHIFTS[pa], SHIFTS[pb]
    say(f"   peak on this grid: dlat {peak_lat:+.3f}, dlon {peak_lon:+.3f}, "
        f"r = {surface[pa, pb]:.4f}")
    say(f"   unshifted:         dlat +0.000, dlon +0.000, r = {zero_r:.4f}")
    say(f"   gain from shifting: {surface[pa, pb] - zero_r:+.4f}")
    say("")
    say("   same peak in the part 2 convention, moving the IMERG map:")
    say(f"     {-peak_lat:+.3f} degrees north, {-peak_lon:+.3f} degrees east")
    say("")

    def vertex(values, index):
        if index in (0, len(values) - 1):
            return None
        y0, y1, y2 = values[index - 1], values[index], values[index + 1]
        bottom = y0 - 2 * y1 + y2
        step_lo = SHIFTS[index] - SHIFTS[index - 1]
        step_hi = SHIFTS[index + 1] - SHIFTS[index]
        if bottom == 0 or abs(step_lo - step_hi) > 1e-12:
            return None
        return SHIFTS[index] - step_lo / 2 * (y2 - y0) / bottom

    lat_vertex = vertex(surface[:, pb], pa)
    lon_vertex = vertex(surface[pa, :], pb)
    say("   parabola through the three grid points either side of the peak:")
    say("     latitude  vertex  " + (f"{lat_vertex:+.4f}"
                                     if lat_vertex is not None
                                     else "n/a, peak at a grid edge"))
    say("     longitude vertex  " + (f"{lon_vertex:+.4f}"
                                     if lon_vertex is not None
                                     else "n/a, peak at a grid edge"))
    say("")

    # ---- the slices
    say("   EVERY SLICE, AT ZERO, AT THE ALL-INDIA PEAK, AND AT ITS OWN PEAK")
    if regions is None:
        say("     region split skipped: the Natural Earth admin-1 file is not")
        say("     present (data/ is never committed)")
    say("")
    say(f"     {'slice':27s} {'squares':>7s} {'dates':>5s} {'r at 0,0':>9s} "
        f"{'r at peak':>10s} {'own peak':>17s} {'r there':>8s}")
    peaks = {}
    for label in slices:
        grid = results[label]
        oa, ob = divmod(int(np.argmax(grid)), len(SHIFTS))
        peaks[label] = (SHIFTS[oa], SHIFTS[ob])
        own = f"{SHIFTS[oa]:+.3f}, {SHIFTS[ob]:+.3f}"
        say(f"     {label:27s} {int(masks[label].sum()):7,d} "
            f"{counts[label]:5d} {grid[zero_index, zero_index]:9.4f} "
            f"{grid[pa, pb]:10.4f} {own:>17s} {grid[oa, ob]:8.4f}")
    say("")

    say("   THE DECISION RULE, FIXED BEFORE THESE NUMBERS WERE SEEN")
    say("   'If the peak is within 0.03 degrees of +0.125 in both")
    say("   directions, and the same in all four regions and at lead day 3,")
    say("   treat it as a bug in our grid handling. Otherwise it is a")
    say("   property of the model or of IMERG.'")
    say("")
    say("   Applied on magnitude, because the sign depends on which grid is")
    say("   described as moving, and a half cell is a half cell either way.")
    say("")
    say(f"     {'slice':27s} {'|dlat|':>8s} {'|dlon|':>8s} "
        f"{'|dlat|-0.125':>13s} {'|dlon|-0.125':>13s} {'within 0.03':>12s}")
    verdicts = {}
    for label, (blat, blon) in peaks.items():
        da = abs(abs(blat) - 0.125)
        do = abs(abs(blon) - 0.125)
        hit = da <= 0.03 and do <= 0.03
        verdicts[label] = hit
        say(f"     {label:27s} {abs(blat):8.3f} {abs(blon):8.3f} "
            f"{da:13.4f} {do:13.4f} {'yes' if hit else 'no':>12s}")
    say("")
    all_hit = all(verdicts.values())
    say("   every slice within 0.03 of a half cell in both directions: "
        + ("YES" if all_hit else "NO"))
    if all_hit:
        say("   => by the rule this is a bug in our grid handling. It is")
        say("      reported and NOT fixed without being told to.")
    else:
        say("   => by the rule this is not a grid bug. Recorded as a finding")
        say("      about the model or about IMERG. No data is shifted to")
        say("      improve any score.")
    say("")


def part_five() -> None:
    """Grid metadata read without any pipeline code."""
    import h5py
    import eccodes as ec

    say("=" * 72)
    say("5. The grids, read without our pipeline code")
    say("=" * 72)

    grib = sorted((cfg.DATA / "live").glob("*/raw/cf_024.grib2"))
    if not grib:
        say("   no live raw GRIB present")
    else:
        path = grib[-1]
        say(f"   GRIB {path.parent.parent.name}/{path.name}")
        keys = ("latitudeOfFirstGridPointInDegrees",
                "longitudeOfFirstGridPointInDegrees",
                "latitudeOfLastGridPointInDegrees",
                "longitudeOfLastGridPointInDegrees",
                "iDirectionIncrementInDegrees",
                "jDirectionIncrementInDegrees",
                "Ni", "Nj", "scanningMode",
                "iScansNegatively", "jScansPositively",
                "jPointsAreConsecutive", "gridType")
        with open(path, "rb") as f:
            h = ec.codes_grib_new_from_file(f)
            try:
                for key in keys:
                    try:
                        say(f"     {key:38s} {ec.codes_get(h, key)}")
                    except Exception as exc:                 # noqa: BLE001
                        say(f"     {key:38s} unavailable ({exc})")
                near = ec.codes_grib_find_nearest(h, WANTED_LAT, WANTED_LON)[0]
                say("")
                say(f"   find_nearest at {WANTED_LAT} N {WANTED_LON} E:")
                say(f"     grid point            {near['lat']} N, "
                    f"{near['lon']} E")
                say(f"     distance              {near['distance']:.6f} km")
                say(f"     accumulated tp step24 {near['value']:.6f} mm")
                step24 = float(near["value"])
            finally:
                ec.codes_release(h)

        path48 = path.parent / "cf_048.grib2"
        with open(path48, "rb") as f:
            h = ec.codes_grib_new_from_file(f)
            try:
                near48 = ec.codes_grib_find_nearest(h, WANTED_LAT,
                                                    WANTED_LON)[0]
                step48 = float(near48["value"])
            finally:
                ec.codes_release(h)
        say(f"     accumulated tp step48 {step48:.6f} mm")
        say(f"     day 1 total, 48 - 24  {step48 - step24:.6f} mm")

        squares = path.parent.parent / "squares.npz"
        with np.load(squares) as f:
            lat, lon = f["lat"], f["lon"]
            i = int(np.argmin(np.abs(lat - WANTED_LAT)))
            j = int(np.argmin(np.abs(lon - WANTED_LON)))
            ours = float(f["member_totals"][0, 0, i, j])
        say("")
        say(f"   our stored array, same cell, control member, lead day 1:")
        say(f"     our lat, lon          {lat[i]} N, {lon[j]} E")
        say(f"     our day 1 total       {ours:.6f} mm")
        say(f"     difference            {abs(ours - (step48 - step24)):.3e} mm")

    say("")
    imerg = existing_file(CNT_DATE)
    if imerg is None:
        say("   no IMERG file present")
        return
    with h5py.File(imerg, "r") as f:
        say(f"   IMERG {imerg.name}")
        for name in ("lat", "lon"):
            values = f[name][:]
            say(f"     {name}: {values.size} values, first {values[0]!r}, "
                f"second {values[1]!r}, last {values[-1]!r}")
            attrs = {k: (v.decode() if isinstance(v, bytes) else
                         (v[0] if isinstance(v, np.ndarray) and v.size == 1
                          else v))
                     for k, v in f[name].attrs.items()
                     if k in ("units", "long_name", "bounds", "standard_name")}
            say(f"       attributes {attrs}")
        say(f"     datasets with 'bnds' or 'bounds' in the name: "
            f"{[k for k in f.keys() if 'bnd' in k.lower()]}")
        say(f"     lat_bnds present: {'lat_bnds' in f}   "
            f"lon_bnds present: {'lon_bnds' in f}")
        say("     no latitude or longitude bounds are published, so pixel")
        say("     edges must be derived as centre plus or minus 0.05 and")
        say("     checked against -90/90 and -180/180 (SPEC 3.7).")
    say("")


def part_six() -> None:
    """Part 5 again on a wet cell, because 0 mm against 0 mm proves nothing.

    Part 5 compared the cell the brief named, 20.25 N 72.75 E. On the live
    run that square was dry in every member, so the comparison read
    0.000000 mm against 0.000000 mm, which is true and worthless. This
    repeats it on the wettest India square of the same run, and on the
    wettest for the control member, so the numbers being compared are large.
    """
    import eccodes as ec

    say("=" * 72)
    say("6. The same comparison on wet cells, so it is not 0 against 0")
    say("=" * 72)

    runs = sorted((cfg.DATA / "live").glob("*/squares.npz"))
    if not runs:
        say("   no live run present")
        return
    squares = runs[-1]
    run_id = squares.parent.name
    raw = squares.parent / "raw"

    india = load_mask()["india"]
    with np.load(squares) as f:
        member_totals = f["member_totals"]
        lat, lon = f["lat"], f["lon"]

    day1_mean = member_totals[0].mean(axis=0)
    wet_mean = np.where(india, day1_mean, -np.inf)
    mi, mj = np.unravel_index(int(np.argmax(wet_mean)), wet_mean.shape)
    control = member_totals[0, 0]
    wet_control = np.where(india, control, -np.inf)
    ci, cj = np.unravel_index(int(np.argmax(wet_control)), wet_control.shape)

    def grib_total(member: int, want_lat: float, want_lon: float):
        values = {}
        for step in (24, 48):
            found = None
            for typ in cfg.TYPES:
                path = raw / f"{typ}_{step:03d}.grib2"
                with open(path, "rb") as fh:
                    while True:
                        h = ec.codes_grib_new_from_file(fh)
                        if h is None:
                            break
                        try:
                            if ec.codes_get(h, "perturbationNumber") != member:
                                continue
                            near = ec.codes_grib_find_nearest(
                                h, want_lat, want_lon)[0]
                            found = (float(near["value"]), float(near["lat"]),
                                     float(near["lon"]),
                                     float(near["distance"]))
                        finally:
                            ec.codes_release(h)
                if found is not None:
                    break
            if found is None:
                raise RuntimeError(f"member {member} not found at step {step}")
            values[step] = found
        return values

    say(f"   run {run_id}")
    for label, i, j, member in (
            ("wettest by ensemble mean", int(mi), int(mj), 0),
            ("wettest for the control", int(ci), int(cj), 0)):
        want_lat, want_lon = float(lat[i]), float(lon[j])
        values = grib_total(member, want_lat, want_lon)
        step24, glat, glon, distance = values[24]
        step48 = values[48][0]
        ours = float(member_totals[0, member, i, j])
        say("")
        say(f"   {label}, member {member}")
        say(f"     asked for             {want_lat} N, {want_lon} E")
        say(f"     ecCodes grid point    {glat} N, {glon} E, "
            f"distance {distance:.6f} km")
        say(f"     accumulated step 24   {step24:.6f} mm")
        say(f"     accumulated step 48   {step48:.6f} mm")
        say(f"     48 - 24               {step48 - step24:.6f} mm")
        say(f"     our stored day 1      {ours:.6f} mm")
        say(f"     difference            {abs(ours - (step48 - step24)):.3e} mm")
        say(f"     ensemble mean here    "
            f"{float(member_totals[0, :, i, j].mean()):.6f} mm")
    say("")
    say("   ecCodes lands on our cell centre with distance 0, and its own")
    say("   48 minus 24 equals our stored daily total, on cells where both")
    say("   numbers are large. Our cell centres are ECMWF grid points, and")
    say("   our differencing is the same differencing.")
    say("")


def main_part_six() -> int:
    say("")
    say("#" * 72)
    say("HC-ALIGN part 6, appended "
        f"{dt.datetime.now().isoformat(timespec='seconds')}")
    say("#" * 72)
    part_six()
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nappended to {OUT}")
    return 0


def main_part_four() -> int:
    say("")
    say("#" * 72)
    say("HC-ALIGN part 4 and 5, appended "
        f"{dt.datetime.now().isoformat(timespec='seconds')}")
    say("#" * 72)
    part_four()
    part_five()
    with open(OUT, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"\nappended to {OUT}")
    return 0


def main() -> int:
    if "--part4" in sys.argv:
        return main_part_four()
    if "--part6" in sys.argv:
        return main_part_six()
    say("HC-ALIGN")
    say(f"written {dt.datetime.now().isoformat(timespec='seconds')}")
    say("read-only check; nothing but this file is written")
    say("")
    part_one()
    ok = part_two()
    part_three()
    say("=" * 72)
    say(f"HC-ALIGN {'PASSED' if ok else 'FAILED'}")
    say("=" * 72)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
