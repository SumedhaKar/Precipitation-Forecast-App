"""Shared configuration for the precipitation forecast pipeline.

Every number here comes from SPEC.md. Nothing is duplicated elsewhere in the
code, so if SPEC.md changes there is exactly one place to change.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- paths
DATA = ROOT / "data"
RAW = DATA / "raw"
INDIA_ECMWF = DATA / "india" / "ecmwf"
INDIA_NASA = DATA / "india" / "nasa"
LOGS = DATA / "logs"
DONE = LOGS / "done"
FAILURES = LOGS / "failures"

# ------------------------------------------------- forecast steps, SPEC 1.3
# Six steps give five daily totals: 24-48, 48-72, 72-96, 96-120, 120-144.
STEPS = (24, 48, 72, 96, 120, 144)
N_STEPS = len(STEPS)
N_DAYS = N_STEPS - 1

# ------------------------------------------------------ ECMWF open data, 2.1
MODEL = "aifs-ens"
STREAM = "enfo"
PARAM = "tp"
RUN_TIME = 0
TYPES = ("cf", "pf")

N_MEMBERS = 51
MEMBERS = tuple(range(N_MEMBERS))  # 0 is the control, 1-50 are perturbed

ARCHIVE_SOURCE = "google"
FALLBACK_SOURCE = "aws"
LIVE_SOURCE = "ecmwf"

MAX_RETRIES = 3
RETRY_AFTER = 30

# Expected GRIB keys, SPEC 2.5
EXPECT_SHORT_NAME = "tp"
EXPECT_UNITS = "kg m**-2"
EXPECT_STEP_TYPE = "accum"
EXPECT_GRID_TYPE = "regular_ll"

GLOBAL_NI = 1440
GLOBAL_NJ = 721
GRID_STEP = 0.25

# ------------------------------------------------------- India box, SPEC 1.4
LAT_MAX = 38.0
LAT_MIN = 6.0
LON_MIN = 68.0
LON_MAX = 98.0
N_LAT = 129
N_LON = 121

# Slices into the global field.
# ECMWF latitude DESCENDS from 90, longitude ASCENDS from 0 (SPEC 2.1),
# so the India rows run from latitude 38 down to latitude 6.
ROW_START = int(round((90.0 - LAT_MAX) / GRID_STEP))  # 208
ROW_STOP = ROW_START + N_LAT                          # 337, exclusive
COL_START = int(round(LON_MIN / GRID_STEP))           # 272
COL_STOP = COL_START + N_LON                          # 393, exclusive

# Coordinate axes of the saved India subset, in saved order.
INDIA_LATS = tuple(LAT_MAX - GRID_STEP * i for i in range(N_LAT))   # 38.0 -> 6.0
INDIA_LONS = tuple(LON_MIN + GRID_STEP * i for i in range(N_LON))   # 68.0 -> 98.0

# ---------------------------------------------------------- piles, SPEC 2.4
PILE_A_START = "20260513"  # first 00 UTC run on AIFS ENS v2

# ------------------------------------------- download plan, SPEC 2.6
MAX_CONNECTIONS = 8
REDUCED_CONNECTIONS = 4
DROP_AFTER_FILE_ERRORS = 3   # drop 8 -> 4 after this many file-level failures
DATES_IN_FLIGHT = 3          # keeps the 8-connection pool busy across dates
MIN_FREE_GB = 15             # SPEC 2.6, stop cleanly below this

# ----------------------------------------- negative differences, SPEC 3.6
# The tolerance is not a fixed number. It is derived from the packing quantum
# of the date being processed, because ECMWF dropped storage precision from
# 16 to 12 bits around 20 October 2026 and a fixed -0.1 mm is finer than the
# new quantum. Differencing two values each quantised with step q can produce
# a spurious negative of up to about q, so twice q is a safe floor.
QUANTUM_TOLERANCE_FACTOR = 2.0

# Above this quantum a file is not trusted at all: rounding that coarse is too
# rough for the 1 mm threshold. Such a date fails; a live run stops.
MAX_TRUSTED_QUANTUM = 0.5


def tolerance_for(coarsest_quantum: float) -> float:
    """The most negative daily difference tolerated for this date, in mm."""
    return -QUANTUM_TOLERANCE_FACTOR * coarsest_quantum


class GridLayoutError(ValueError):
    """The file's grid is not one we can cut India out of."""


def india_rows_for(first_lat: float) -> slice:
    """Rows covering India, given the file's own first latitude.

    ECMWF latitude descends, so row k holds latitude first_lat - 0.25 * k.
    """
    start = (first_lat - LAT_MAX) / GRID_STEP
    if abs(start - round(start)) > 1e-6:
        raise GridLayoutError(
            f"latitude {LAT_MAX} is not on the grid starting at {first_lat}"
        )
    start = int(round(start))
    stop = start + N_LAT
    if start < 0 or stop > GLOBAL_NJ:
        raise GridLayoutError(
            f"India rows {start}:{stop} fall outside the {GLOBAL_NJ}-row grid"
        )
    return slice(start, stop)


def india_cols_for(first_lon: float) -> slice:
    """Columns covering India, given the file's own first longitude.

    Column k holds longitude (first_lon + 0.25 * k) modulo 360. ECMWF used a
    first longitude of 0 until about 20 October 2026 and 180 afterwards, so
    this offset is computed per file and never assumed. India at 68-98 E is
    contiguous under both conventions, which is checked rather than trusted.
    """
    start = ((LON_MIN - first_lon) % 360.0) / GRID_STEP
    if abs(start - round(start)) > 1e-6:
        raise GridLayoutError(
            f"longitude {LON_MIN} is not on the grid starting at {first_lon}"
        )
    start = int(round(start))
    stop = start + N_LON
    if stop > GLOBAL_NI:
        raise GridLayoutError(
            f"India columns {start}:{stop} wrap past the end of the "
            f"{GLOBAL_NI}-column grid, which this code does not handle"
        )
    return slice(start, stop)


def india_slice(first_lat: float = 90.0, first_lon: float = 0.0):
    """Return the (rows, cols) slice pair that cuts a global field to India."""
    return india_rows_for(first_lat), india_cols_for(first_lon)


def raw_dir(date: str) -> Path:
    """Folder holding one date's raw GRIB files."""
    return RAW / date


def raw_path(date: str, typ: str, step: int) -> Path:
    return raw_dir(date) / f"{typ}_{step:03d}.grib2"


def india_path(date: str) -> Path:
    return INDIA_ECMWF / f"{date}.npz"


def part_path(date: str) -> Path:
    return INDIA_ECMWF / f"{date}.npz.part"


def done_path(date: str) -> Path:
    return DONE / f"{date}.json"


def failure_path(date: str) -> Path:
    return FAILURES / f"{date}.json"


def ensure_dirs() -> None:
    for d in (RAW, INDIA_ECMWF, INDIA_NASA, DONE, FAILURES):
        d.mkdir(parents=True, exist_ok=True)
