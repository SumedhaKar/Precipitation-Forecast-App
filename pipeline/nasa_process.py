"""Remap IMERG daily rainfall onto the ECMWF India grid.

SPEC 3.1 to 3.4 and 3.7. One IMERG file is one date. Observations are
aggregated up to the forecast grid, never the other way round.

The three traps this module exists to get right, all from SPEC 2.3:

1. IMERG arrays are shaped ``(time, lon, lat)``. Longitude comes first.
2. IMERG latitude ascends; ECMWF latitude descends.
3. 0.25 is not a whole multiple of 0.1, so pixels straddle cell edges and
   partial overlaps are the normal case, not an edge case.

Nothing here is taken on trust from the file layout: the grid is rebuilt from
the coordinate values in the file and the pixel edges are asserted against
-90/90 and -180/180 before any weight is computed.

Usage
  python -m pipeline.nasa_process --all          process every Pile B date
  python -m pipeline.nasa_process 20260714       process one date
  python -m pipeline.nasa_process --summary      report over what is done
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from . import config as cfg
from .nasa_download import existing_file, imerg_dir

# ----------------------------------------------------------------- numbers
# These live here rather than in pipeline/config.py only because Pile A was
# running when this module was written and config.py must not be touched
# while a run imports it (SPEC 3.7). They belong in config.py and move there
# the next time Pile A is stopped.

PIXEL = 0.1                     # IMERG grid spacing, degrees
N_PIX_LON = 3600
N_PIX_LAT = 1800
FILL_VALUE = -9999.9            # IMERG precipitation _FillValue
FILL_TOLERANCE = 0.01           # the value is stored as float32
COMPLETE_CNT = 48               # all 48 half-hourly fields contributed
MIN_COMPLETE_FRACTION = 0.90    # SPEC 3.4; exactly 0.90 passes
FRACTION_EPSILON = 1e-12        # guards the >= 0.90 test against float dust

COORD_TOLERANCE = 1e-4          # lon is stored as float32
AREA_TOLERANCE = 1e-9           # relative, for the weights-sum-to-area check

REQUIRED_FILE_VERSION = "V07C"
REQUIRED_DOI = "10.5067/GPM/IMERGDL/DAY/07"
TITLE_MUST_CONTAIN = ("Late", "1 day", "0.1 degree")
EXPECT_UNITS = "mm/day"

N_LEAD_DAYS = len(cfg.STEPS) - 1    # 6 steps give 5 daily totals

NASA_DIR = cfg.INDIA_NASA


class NasaProcessError(Exception):
    """An IMERG file is not what SPEC 2.3 says it is, or its values are bad."""


# ------------------------------------------------------------ date mapping

def imerg_date_for(run_date: str, lead_day: int) -> str:
    """The IMERG date that verifies one lead day of one run (SPEC 3.7).

    Lead day n covers forecast steps 24n to 24(n+1), which is the 00 UTC to
    00 UTC day beginning n days after the run date. IMERG files are named for
    the day they cover, so that is IMERG date R + n.

    >>> imerg_date_for("20260801", 1)
    '20260802'
    """
    if not isinstance(lead_day, int) or isinstance(lead_day, bool):
        raise NasaProcessError(f"lead day must be an int, got {lead_day!r}")
    if not 1 <= lead_day <= N_LEAD_DAYS:
        raise NasaProcessError(
            f"lead day {lead_day} is outside 1 to {N_LEAD_DAYS}")
    day = dt.datetime.strptime(run_date, "%Y%m%d").date()
    return (day + dt.timedelta(days=lead_day)).strftime("%Y%m%d")


def lead_day_steps(lead_day: int) -> tuple[int, int]:
    """The two forecast steps whose difference is this lead day's total."""
    if not 1 <= lead_day <= N_LEAD_DAYS:
        raise NasaProcessError(
            f"lead day {lead_day} is outside 1 to {N_LEAD_DAYS}")
    return 24 * lead_day, 24 * (lead_day + 1)


# -------------------------------------------------------------- file paths

def nasa_path(date: str) -> Path:
    return NASA_DIR / f"{date}.npz"


def nasa_part_path(date: str) -> Path:
    return NASA_DIR / f"{date}.npz.part"


def nasa_done_path(date: str) -> Path:
    return cfg.DONE / f"nasa_{date}.json"


def nasa_failure_path(date: str) -> Path:
    return cfg.FAILURES / f"nasa_{date}.json"


# ------------------------------------------------------- file-level checks

def _attr(obj, key: str) -> str:
    """One HDF5 attribute as a plain string, however it is wrapped."""
    value = obj.attrs.get(key)
    if value is None:
        return ""
    if isinstance(value, np.ndarray):
        value = value[0] if value.size else ""
    if isinstance(value, bytes):
        value = value.decode()
    return str(value)


def check_file_identity(f: h5py.File, path: Path, date: str) -> dict:
    """Version, units and time coordinate, read from the file itself."""
    name = path.name

    if REQUIRED_FILE_VERSION not in name:
        raise NasaProcessError(
            f"{name}: expected {REQUIRED_FILE_VERSION}, refusing to mix "
            "IMERG versions")

    doi = _attr(f, "DOI")
    if doi != REQUIRED_DOI:
        raise NasaProcessError(f"{name}: DOI is {doi!r}, expected "
                               f"{REQUIRED_DOI!r}")

    title = _attr(f, "title")
    for fragment in TITLE_MUST_CONTAIN:
        if fragment not in title:
            raise NasaProcessError(
                f"{name}: title {title!r} does not contain {fragment!r}")

    for var in ("precipitation", "precipitation_cnt", "lat", "lon", "time"):
        if var not in f:
            raise NasaProcessError(f"{name}: variable {var} is missing")

    units = _attr(f["precipitation"], "units")
    if units != EXPECT_UNITS:
        raise NasaProcessError(
            f"{name}: precipitation units are {units!r}, expected "
            f"{EXPECT_UNITS!r}")

    shape = f["precipitation"].shape
    if tuple(shape) != (1, N_PIX_LON, N_PIX_LAT):
        raise NasaProcessError(
            f"{name}: precipitation shape is {tuple(shape)}, expected "
            f"(1, {N_PIX_LON}, {N_PIX_LAT})")
    if tuple(f["precipitation_cnt"].shape) != tuple(shape):
        raise NasaProcessError(
            f"{name}: precipitation_cnt shape {tuple(f['precipitation_cnt'].shape)}"
            f" does not match precipitation {tuple(shape)}")

    # The time coordinate, not the file name, has to agree with the date.
    time_units = _attr(f["time"], "units")
    epoch = _epoch_from_units(time_units, name)
    values = np.asarray(f["time"][:], dtype=np.float64)
    if values.size != 1:
        raise NasaProcessError(
            f"{name}: time has {values.size} values, expected 1")
    stamp = epoch + dt.timedelta(days=float(values[0]))
    wanted = dt.datetime.strptime(date, "%Y%m%d").date()
    if stamp.date() != wanted:
        raise NasaProcessError(
            f"{name}: time coordinate is {stamp.isoformat()} "
            f"({time_units!r}), which is not {wanted.isoformat()}")
    if stamp.time() != dt.time(0, 0, 0):
        raise NasaProcessError(
            f"{name}: time coordinate {stamp.isoformat()} is not 00:00 UTC")

    begin_date = _attr(f, "BeginDate")
    if begin_date != wanted.isoformat():
        raise NasaProcessError(
            f"{name}: BeginDate is {begin_date!r}, expected "
            f"{wanted.isoformat()!r}")

    return {
        "file": name,
        "bytes": path.stat().st_size,
        "file_version": REQUIRED_FILE_VERSION,
        "doi": doi,
        "title": title,
        "units": units,
        "time_units": time_units,
        "time_value": float(values[0]),
        "time_coordinate": stamp.isoformat(),
        "begin_date": begin_date,
        "grid": list(shape),
    }


def _epoch_from_units(units: str, name: str) -> dt.datetime:
    """Parse "days since YYYY-MM-DD HH:MM:SSZ" rather than assume the epoch."""
    text = units.strip()
    if not text.lower().startswith("days since "):
        raise NasaProcessError(
            f"{name}: time units {units!r} are not 'days since ...'")
    rest = text[len("days since "):].strip().rstrip("Z").strip()
    for form in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(rest, form)
        except ValueError:
            continue
    raise NasaProcessError(f"{name}: cannot read epoch from {units!r}")


# ------------------------------------------------------- grid from the file

def pixel_edges(centres: np.ndarray, spacing: float, first_edge: float,
                last_edge: float, what: str) -> np.ndarray:
    """Edges from coordinate values, asserted, never assumed.

    Returns one more value than there are centres: edge i is the low side of
    pixel i.
    """
    centres = np.asarray(centres, dtype=np.float64)
    if centres.ndim != 1 or centres.size < 2:
        raise NasaProcessError(f"{what}: not a coordinate vector")

    steps = np.diff(centres)
    if np.any(steps <= 0):
        raise NasaProcessError(f"{what}: coordinate values are not ascending")
    if np.max(np.abs(steps - spacing)) > COORD_TOLERANCE:
        worst = float(np.max(np.abs(steps - spacing)))
        raise NasaProcessError(
            f"{what}: spacing is not {spacing} degrees, worst error {worst}")

    edges = np.empty(centres.size + 1, dtype=np.float64)
    edges[:-1] = centres - spacing / 2.0
    edges[-1] = centres[-1] + spacing / 2.0

    if abs(edges[0] - first_edge) > COORD_TOLERANCE:
        raise NasaProcessError(
            f"{what}: first pixel edge is {edges[0]}, expected {first_edge}")
    if abs(edges[-1] - last_edge) > COORD_TOLERANCE:
        raise NasaProcessError(
            f"{what}: last pixel edge is {edges[-1]}, expected {last_edge}")

    # Snap to the exact grid once the file has proved it is that grid, so
    # that overlap arithmetic is not carrying float32 noise from the file.
    return np.round(edges / spacing) * spacing


def read_grid(f: h5py.File, name: str = "") -> tuple[np.ndarray, np.ndarray]:
    """IMERG latitude and longitude edges, ascending, from the file."""
    lat = np.asarray(f["lat"][:], dtype=np.float64)
    lon = np.asarray(f["lon"][:], dtype=np.float64)
    if lat.size != N_PIX_LAT or lon.size != N_PIX_LON:
        raise NasaProcessError(
            f"{name}: grid is {lon.size} x {lat.size}, expected "
            f"{N_PIX_LON} x {N_PIX_LAT}")
    lat_edges = pixel_edges(lat, PIXEL, -90.0, 90.0, f"{name} latitude")
    lon_edges = pixel_edges(lon, PIXEL, -180.0, 180.0, f"{name} longitude")
    return lat_edges, lon_edges


def to_lat_lon_descending(block: np.ndarray) -> np.ndarray:
    """(lon, lat) ascending-latitude -> (lat, lon) descending latitude.

    SPEC 3.2 makes this the first operation of the remapping, so that both
    grids run the same way before any overlap is computed.
    """
    if block.ndim != 2:
        raise NasaProcessError(f"expected a 2-D (lon, lat) block, got "
                               f"{block.shape}")
    return block.T[::-1, :]


# ---------------------------------------------------------- weight matrix

@dataclass
class Remap:
    """The sparse remapping operator, computed once and reused every date.

    It is a sparse matrix in coordinate form: ``rows`` indexes the 129 x 121
    ECMWF cells flattened, ``pix`` indexes the IMERG window flattened in
    (descending latitude, longitude) order, and ``weight`` is the spherical
    area of the overlap rectangle.
    """
    lat_slice: slice            # into the file's ascending-latitude axis
    lon_slice: slice
    n_lat_window: int
    n_lon_window: int
    rows: np.ndarray
    pix: np.ndarray
    weight: np.ndarray
    cell_area: np.ndarray       # (N_LAT * N_LON,) analytic cell area
    lat_edges_window_desc: np.ndarray   # n_lat_window + 1, descending
    lon_edges_window: np.ndarray        # n_lon_window + 1, ascending

    @property
    def n_cells(self) -> int:
        return cfg.N_LAT * cfg.N_LON


def _sin_deg(x: np.ndarray | float) -> np.ndarray | float:
    return np.sin(np.deg2rad(x))


def build_remap(lat_edges: np.ndarray, lon_edges: np.ndarray) -> Remap:
    """Build the weights from IMERG pixel edges and the ECMWF cell edges."""
    half = cfg.GRID_STEP / 2.0
    cell_lat_top = np.asarray(cfg.INDIA_LATS, dtype=np.float64) + half
    cell_lat_bot = np.asarray(cfg.INDIA_LATS, dtype=np.float64) - half
    cell_lon_left = np.asarray(cfg.INDIA_LONS, dtype=np.float64) - half
    cell_lon_right = np.asarray(cfg.INDIA_LONS, dtype=np.float64) + half

    box_lat_lo, box_lat_hi = cell_lat_bot.min(), cell_lat_top.max()
    box_lon_lo, box_lon_hi = cell_lon_left.min(), cell_lon_right.max()

    # Pixels that touch the India box, found from the edges themselves.
    lat_hit = np.nonzero((lat_edges[1:] > box_lat_lo)
                         & (lat_edges[:-1] < box_lat_hi))[0]
    lon_hit = np.nonzero((lon_edges[1:] > box_lon_lo)
                         & (lon_edges[:-1] < box_lon_hi))[0]
    if lat_hit.size == 0 or lon_hit.size == 0:
        raise NasaProcessError("the IMERG grid does not cover the India box")

    lat_slice = slice(int(lat_hit[0]), int(lat_hit[-1]) + 1)
    lon_slice = slice(int(lon_hit[0]), int(lon_hit[-1]) + 1)
    n_lat_w = lat_slice.stop - lat_slice.start
    n_lon_w = lon_slice.stop - lon_slice.start

    # Window edges, latitude flipped to descending to match the data after
    # to_lat_lon_descending.
    lat_edges_w = lat_edges[lat_slice.start:lat_slice.stop + 1]
    lat_top_desc = lat_edges_w[1:][::-1]      # high side of each pixel
    lat_bot_desc = lat_edges_w[:-1][::-1]     # low side
    lon_edges_w = lon_edges[lon_slice.start:lon_slice.stop + 1]
    lon_left_w = lon_edges_w[:-1]
    lon_right_w = lon_edges_w[1:]

    # Per ECMWF row: which window rows overlap, and by how much in sine.
    lat_parts: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(cfg.N_LAT):
        top = np.minimum(lat_top_desc, cell_lat_top[i])
        bot = np.maximum(lat_bot_desc, cell_lat_bot[i])
        overlap = _sin_deg(top) - _sin_deg(bot)
        keep = np.nonzero(overlap > 0)[0]
        lat_parts.append((keep, overlap[keep]))

    # Per ECMWF column: which window columns overlap, and by how many degrees.
    lon_parts: list[tuple[np.ndarray, np.ndarray]] = []
    for j in range(cfg.N_LON):
        right = np.minimum(lon_right_w, cell_lon_right[j])
        left = np.maximum(lon_left_w, cell_lon_left[j])
        overlap = right - left
        keep = np.nonzero(overlap > 0)[0]
        lon_parts.append((keep, overlap[keep]))

    rows_all, pix_all, w_all = [], [], []
    for i in range(cfg.N_LAT):
        lat_idx, lat_w = lat_parts[i]
        for j in range(cfg.N_LON):
            lon_idx, lon_w = lon_parts[j]
            block = lat_w[:, None] * lon_w[None, :]
            flat_pix = (lat_idx[:, None] * n_lon_w + lon_idx[None, :])
            rows_all.append(np.full(block.size, i * cfg.N_LON + j,
                                    dtype=np.int32))
            pix_all.append(flat_pix.ravel().astype(np.int32))
            w_all.append(block.ravel())

    rows = np.concatenate(rows_all)
    pix = np.concatenate(pix_all)
    weight = np.concatenate(w_all)

    cell_area = (cfg.GRID_STEP
                 * (_sin_deg(cell_lat_top)[:, None]
                    - _sin_deg(cell_lat_bot)[:, None])
                 * np.ones((1, cfg.N_LON))).ravel()

    # The pixel grid tiles the globe, so every cell must be fully covered.
    # If this identity fails, the overlap arithmetic is wrong and nothing
    # downstream can be trusted.
    summed = np.bincount(rows, weights=weight, minlength=cfg.N_LAT * cfg.N_LON)
    worst = float(np.max(np.abs(summed - cell_area) / cell_area))
    if worst > AREA_TOLERANCE:
        raise NasaProcessError(
            f"weights do not sum to the cell area, worst relative error "
            f"{worst:.3e}")

    return Remap(
        lat_slice=lat_slice, lon_slice=lon_slice,
        n_lat_window=n_lat_w, n_lon_window=n_lon_w,
        rows=rows, pix=pix, weight=weight, cell_area=cell_area,
        lat_edges_window_desc=lat_edges_w[::-1],
        lon_edges_window=lon_edges_w,
    )


# --------------------------------------------------------------- remapping

def remap(remapper: Remap, rain: np.ndarray, cnt: np.ndarray,
          ) -> tuple[np.ndarray, np.ndarray]:
    """Area-weighted mean over complete pixels. Returns (rain, fraction).

    ``rain`` and ``cnt`` are the India window in (descending latitude,
    longitude) order. Missing pixels are NaN. A cell whose complete pixels
    cover less than MIN_COMPLETE_FRACTION of its area comes back NaN.
    """
    shape = (remapper.n_lat_window, remapper.n_lon_window)
    if rain.shape != shape or cnt.shape != shape:
        raise NasaProcessError(
            f"window is {rain.shape} / {cnt.shape}, expected {shape}")

    values = rain.ravel().astype(np.float64)
    complete = ((cnt.ravel() == COMPLETE_CNT) & np.isfinite(values))

    w = remapper.weight
    pix = remapper.pix
    rows = remapper.rows
    n = remapper.n_cells

    ok = complete[pix]
    w_ok = w * ok
    contribution = np.where(ok, values[pix], 0.0) * w

    numerator = np.bincount(rows, weights=contribution, minlength=n)
    denominator = np.bincount(rows, weights=w_ok, minlength=n)

    fraction = denominator / remapper.cell_area
    usable = fraction >= MIN_COMPLETE_FRACTION - FRACTION_EPSILON

    out = np.full(n, np.nan, dtype=np.float64)
    np.divide(numerator, denominator, out=out, where=usable & (denominator > 0))
    out[~usable] = np.nan

    return (out.reshape(cfg.N_LAT, cfg.N_LON),
            fraction.reshape(cfg.N_LAT, cfg.N_LON))


def read_window(f: h5py.File, remapper: Remap, date: str, name: str,
                ) -> tuple[np.ndarray, np.ndarray, dict]:
    """The India window of one IMERG file, oriented like ECMWF and checked."""
    raw = np.asarray(
        f["precipitation"][0, remapper.lon_slice, remapper.lat_slice],
        dtype=np.float64)
    cnt = np.asarray(
        f["precipitation_cnt"][0, remapper.lon_slice, remapper.lat_slice],
        dtype=np.int16)

    rain = to_lat_lon_descending(raw)
    counts = to_lat_lon_descending(cnt)

    is_fill = np.isclose(rain, FILL_VALUE, rtol=0.0, atol=FILL_TOLERANCE)
    bad = ~is_fill & (np.isnan(rain) | (rain < 0.0))
    if bad.any():
        where = np.argwhere(bad)[0]
        raise NasaProcessError(
            f"{name}: {int(bad.sum())} precipitation value(s) in the India "
            f"window are negative or NaN but are not the fill value "
            f"{FILL_VALUE}; first at window row {where[0]} column {where[1]} "
            f"= {rain[tuple(where)]!r}")

    rain = np.where(is_fill, np.nan, rain)

    if counts.min() < 0 or counts.max() > COMPLETE_CNT:
        raise NasaProcessError(
            f"{name}: precipitation_cnt range is {int(counts.min())} to "
            f"{int(counts.max())}, expected 0 to {COMPLETE_CNT}")

    summary = {
        "window_shape": list(rain.shape),
        "fill_pixels": int(is_fill.sum()),
        "complete_pixels": int((counts == COMPLETE_CNT).sum()),
        "pixels": int(counts.size),
        "cnt_min": int(counts.min()),
        "cnt_max": int(counts.max()),
        "window_max_mm": float(np.nanmax(rain)) if np.isfinite(rain).any()
        else float("nan"),
    }
    return rain, counts, summary


# ----------------------------------------------------------------- one date

def write_and_verify(date: str, rain: np.ndarray, fraction: np.ndarray) -> dict:
    """Write the .npz through a .part, reopen it, compare, then rename."""
    NASA_DIR.mkdir(parents=True, exist_ok=True)
    final = nasa_path(date)
    part = nasa_part_path(date)

    rain32 = rain.astype(np.float32)
    frac32 = fraction.astype(np.float32)
    lat = np.asarray(cfg.INDIA_LATS, dtype=np.float64)
    lon = np.asarray(cfg.INDIA_LONS, dtype=np.float64)

    if part.exists():
        part.unlink()
    with open(part, "wb") as fh:
        np.savez(fh, rain=rain32, complete_fraction=frac32, lat=lat, lon=lon)

    with np.load(part) as f:
        back_rain = f["rain"]
        back_frac = f["complete_fraction"]
        back_lat = f["lat"]
        back_lon = f["lon"]
        if back_rain.shape != (cfg.N_LAT, cfg.N_LON):
            raise NasaProcessError(
                f"{date}: written rain shape {back_rain.shape}")
        if not np.array_equal(back_rain, rain32, equal_nan=True):
            raise NasaProcessError(f"{date}: rain changed on the way to disk")
        if not np.array_equal(back_frac, frac32, equal_nan=True):
            raise NasaProcessError(
                f"{date}: complete_fraction changed on the way to disk")
        if not (np.array_equal(back_lat, lat) and np.array_equal(back_lon, lon)):
            raise NasaProcessError(f"{date}: coordinates changed on disk")

    part.replace(final)
    return {"file": final.name, "bytes": final.stat().st_size}


def process_date(date: str) -> dict:
    """Read, check, remap and store one IMERG date. Returns a done record."""
    path = existing_file(date)
    if path is None:
        raise NasaProcessError(
            f"{date}: no IMERG file in {imerg_dir()}; Pile B has not got it")

    started = dt.datetime.now()
    with h5py.File(path, "r") as f:
        identity = check_file_identity(f, path, date)
        lat_edges, lon_edges = read_grid(f, path.name)
        remapper = build_remap(lat_edges, lon_edges)
        rain_window, counts, window = read_window(f, remapper, date, path.name)

    rain, fraction = remap(remapper, rain_window, counts)

    usable = np.isfinite(rain)
    written = write_and_verify(date, rain, fraction)

    record = {
        "date": date,
        "imerg": identity,
        "window": window,
        "grid": {
            "cells": int(rain.size),
            "lat_from": cfg.INDIA_LATS[0],
            "lat_to": cfg.INDIA_LATS[-1],
            "lon_from": cfg.INDIA_LONS[0],
            "lon_to": cfg.INDIA_LONS[-1],
            "window_pixels": [remapper.n_lat_window, remapper.n_lon_window],
            "weight_entries": int(remapper.weight.size),
        },
        "output": written,
        "usable_cells": int(usable.sum()),
        "unusable_cells": int((~usable).sum()),
        "min_complete_fraction": float(np.min(fraction)),
        "max_rain_mm": float(np.nanmax(rain)) if usable.any() else None,
        "raw_kept": True,
        "finished_at": dt.datetime.now().isoformat(timespec="seconds"),
        "seconds_total": round((dt.datetime.now() - started).total_seconds(), 2),
    }

    cfg.DONE.mkdir(parents=True, exist_ok=True)
    nasa_done_path(date).write_text(json.dumps(record, indent=2),
                                    encoding="utf-8")
    return record


# ------------------------------------------------------------------ runner

def pile_b_dates() -> list[str]:
    """Every date Pile B has a raw file for, in order."""
    dates = []
    for p in sorted(imerg_dir().glob("3B-DAY-L.MS.MRG.3IMERG.*.nc4")):
        stem = p.name.split("3IMERG.")[1]
        dates.append(stem.split("-")[0])
    return sorted(set(dates))


def already_done(date: str) -> bool:
    return nasa_done_path(date).exists() and nasa_path(date).exists()


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    print(line, flush=True)
    cfg.LOGS.mkdir(parents=True, exist_ok=True)
    with open(cfg.LOGS / "nasa_process.log", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def process_all(dates: list[str] | None = None) -> dict:
    """Process every date, skipping ones already done. Never stops on one."""
    dates = dates or pile_b_dates()
    done = failed = skipped = 0
    log(f"starting: {len(dates)} date(s)")

    for date in dates:
        if already_done(date):
            skipped += 1
            continue
        try:
            record = process_date(date)
            done += 1
            failure = nasa_failure_path(date)
            if failure.exists():
                failure.unlink()
            log(f"{date}  {record['unusable_cells']} unusable cells, "
                f"max {record['max_rain_mm']:.1f} mm, "
                f"{record['seconds_total']}s")
        except Exception as exc:                        # noqa: BLE001
            failed += 1
            cfg.FAILURES.mkdir(parents=True, exist_ok=True)
            nasa_failure_path(date).write_text(json.dumps({
                "date": date,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "failed_at": dt.datetime.now().isoformat(timespec="seconds"),
            }, indent=2), encoding="utf-8")
            log(f"{date}  FAILED {type(exc).__name__}: {exc}")

    log(f"finished: done={done} failed={failed} skipped={skipped}")
    return {"done": done, "failed": failed, "skipped": skipped,
            "dates": len(dates)}


# ----------------------------------------------------------------- summary

def summary(dates: list[str] | None = None) -> dict:
    """What SPEC 3.7 requires reporting: unusable square-days and the wettest.

    Counted over India squares only (section 3.5), because a cell outside
    India is never verified and its usability is not interesting.
    """
    from .india_mask import load as load_mask

    india = load_mask()["india"]
    dates = dates or sorted(d for d in pile_b_dates() if nasa_path(d).exists())

    per_month: dict[str, dict[str, int]] = {}
    total_unusable = total_squaredays = 0
    heavy_dates = []
    wettest = {"mm": -1.0}

    for date in dates:
        with np.load(nasa_path(date)) as f:
            rain = f["rain"]
        usable = np.isfinite(rain) & india
        unusable = int(india.sum() - usable.sum())
        total_unusable += unusable
        total_squaredays += int(india.sum())

        month = date[:6]
        bucket = per_month.setdefault(month, {"dates": 0, "unusable": 0,
                                              "square_days": 0})
        bucket["dates"] += 1
        bucket["unusable"] += unusable
        bucket["square_days"] += int(india.sum())

        share = unusable / int(india.sum())
        if share > 0.10:
            heavy_dates.append({"date": date, "unusable": unusable,
                                "share": round(share, 4)})

        masked = np.where(usable, rain, -np.inf)
        i, j = np.unravel_index(int(np.argmax(masked)), masked.shape)
        if float(masked[i, j]) > wettest["mm"]:
            wettest = {"date": date, "lat": cfg.INDIA_LATS[i],
                       "lon": cfg.INDIA_LONS[j], "mm": float(masked[i, j])}

    return {
        "dates": len(dates),
        "india_squares": int(india.sum()),
        "square_days": total_squaredays,
        "unusable_square_days": total_unusable,
        "unusable_share": (total_unusable / total_squaredays
                           if total_squaredays else 0.0),
        "per_month": per_month,
        "dates_over_10_percent_unusable": heavy_dates,
        "wettest_square_day": wettest,
    }


def print_summary(result: dict) -> None:
    print(f"dates processed            {result['dates']}")
    print(f"India squares per date     {result['india_squares']:,}")
    print(f"India square-days          {result['square_days']:,}")
    print(f"unusable square-days       {result['unusable_square_days']:,} "
          f"({100 * result['unusable_share']:.4f}%)")
    print("\nper month:")
    print(f"  {'month':8s} {'dates':>6s} {'square-days':>12s} "
          f"{'unusable':>10s} {'share':>9s}")
    for month, b in sorted(result["per_month"].items()):
        share = b["unusable"] / b["square_days"] if b["square_days"] else 0.0
        print(f"  {month:8s} {b['dates']:6d} {b['square_days']:12,d} "
              f"{b['unusable']:10,d} {100 * share:8.4f}%")
    heavy = result["dates_over_10_percent_unusable"]
    print(f"\ndates with more than 10% of India squares unusable: {len(heavy)}")
    for row in heavy:
        print(f"  {row['date']}  {row['unusable']:,} squares "
              f"({100 * row['share']:.1f}%)")
    w = result["wettest_square_day"]
    print(f"\nwettest India square-day   {w.get('date')} at "
          f"{w.get('lat')} N, {w.get('lon')} E, {w.get('mm'):.1f} mm")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "--summary":
        print_summary(summary())
        return 0
    if argv[0] == "--all":
        result = process_all()
        return 0 if result["failed"] == 0 else 1
    result = process_all(argv)
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
