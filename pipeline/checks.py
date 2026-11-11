"""Checks applied to every downloaded GRIB file before it is used.

SPEC 2.5 lists the unit checks. SPEC 2.6 adds the identity, member and
missing-value checks. A failed check raises CheckFailed; it never converts,
guesses or continues (CLAUDE.md rule 2).

Packing details are recorded but never cause a failure: ECMWF changed storage
precision around 20 October 2026 and we want that visible in the logs.
"""
from __future__ import annotations

from pathlib import Path

import eccodes as ec
import numpy as np

from . import config as cfg


class CheckFailed(Exception):
    """A downloaded file did not match what was asked for."""


def _get(handle, key, default=None):
    try:
        return ec.codes_get(handle, key)
    except Exception:
        return default


def message_quantum(handle) -> float:
    """Smallest value step this message can represent, in mm.

    GRIB stores values as integers scaled by two factors, so the quantum is
    2**binaryScaleFactor / 10**decimalScaleFactor. Verified against the real
    files on 12 November 2026: 0.003906 mm for a 16-bit May field and
    0.125 mm for a 12-bit October field, both matching the smallest gap
    between distinct decoded values exactly.
    """
    binary = _get(handle, "binaryScaleFactor")
    decimal = _get(handle, "decimalScaleFactor")
    if binary is None or decimal is None:
        raise CheckFailed("message has no scale factors, cannot find quantum")
    return (2.0 ** binary) / (10.0 ** decimal)


def read_india_subset(path: Path, date: str, step: int, typ: str):
    """Read one GRIB file, check it, and return its India subset.

    Returns (members, packing) where

      members  dict of perturbationNumber -> float32 array shaped (129, 121)
      packing  list of one dict per message with bitsPerValue and packingType

    Raises CheckFailed on any problem.
    """
    members: dict[int, np.ndarray] = {}
    packing: list[dict] = []
    rows = cols = None

    with open(path, "rb") as f:
        while True:
            h = ec.codes_grib_new_from_file(f)
            if h is None:
                break
            try:
                _check_message(h, date, step, typ)

                values = ec.codes_get_values(h)
                if values.size != cfg.GLOBAL_NI * cfg.GLOBAL_NJ:
                    raise CheckFailed(
                        f"{path.name}: expected "
                        f"{cfg.GLOBAL_NI * cfg.GLOBAL_NJ} values, "
                        f"got {values.size}"
                    )

                # SPEC 2.6: no missing values and no NaNs.
                if _get(h, "bitmapPresent", 0):
                    raise CheckFailed(f"{path.name}: a bitmap is present, "
                                      "so some values are missing")
                if not np.isfinite(values).all():
                    n_bad = int((~np.isfinite(values)).sum())
                    raise CheckFailed(f"{path.name}: {n_bad} non-finite values")

                # The India window is located from the file's own grid origin,
                # which ECMWF changed from longitude 0 to 180 around
                # 20 October 2026.
                if rows is None:
                    rows, cols = cfg.india_slice(
                        _get(h, "latitudeOfFirstGridPointInDegrees"),
                        _get(h, "longitudeOfFirstGridPointInDegrees"),
                    )

                field = values.reshape(cfg.GLOBAL_NJ, cfg.GLOBAL_NI)
                number = _get(h, "perturbationNumber")
                if number in members:
                    raise CheckFailed(
                        f"{path.name}: perturbationNumber {number} appears "
                        "more than once"
                    )
                # SPEC 2.1: index by perturbationNumber, never by file order.
                members[number] = np.ascontiguousarray(
                    field[rows, cols], dtype=np.float32
                )
                packing.append({
                    "perturbationNumber": number,
                    "bitsPerValue": _get(h, "bitsPerValue"),
                    "packingType": _get(h, "packingType"),
                    "longitudeOfFirstGridPoint":
                        _get(h, "longitudeOfFirstGridPointInDegrees"),
                    "quantum": message_quantum(h),
                })
            finally:
                ec.codes_release(h)

    expected = {0} if typ == "cf" else set(range(1, cfg.N_MEMBERS))
    if set(members) != expected:
        missing = sorted(expected - set(members))
        extra = sorted(set(members) - expected)
        raise CheckFailed(
            f"{path.name}: wrong members. missing={missing} extra={extra}"
        )

    return members, packing


def _check_message(h, date: str, step: int, typ: str) -> None:
    """Apply SPEC 2.5 unit checks and SPEC 2.6 identity checks to one message."""
    checks = [
        ("shortName", cfg.EXPECT_SHORT_NAME),
        ("units", cfg.EXPECT_UNITS),
        ("stepType", cfg.EXPECT_STEP_TYPE),
        ("gridType", cfg.EXPECT_GRID_TYPE),
        ("Ni", cfg.GLOBAL_NI),
        ("Nj", cfg.GLOBAL_NJ),
        ("dataType", typ),
    ]
    for key, want in checks:
        got = _get(h, key)
        if got != want:
            raise CheckFailed(f"{key}: expected {want!r}, got {got!r}")

    for key in ("iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees"):
        got = _get(h, key)
        if got is None or abs(got - cfg.GRID_STEP) > 1e-9:
            raise CheckFailed(f"{key}: expected {cfg.GRID_STEP}, got {got!r}")

    # The file must be the date, run and step we asked for (SPEC 2.6 point 1).
    got_date = str(_get(h, "dataDate"))
    if got_date != date:
        raise CheckFailed(f"dataDate: asked for {date}, file says {got_date}")

    got_time = _get(h, "dataTime")
    if got_time != cfg.RUN_TIME * 100 and got_time != cfg.RUN_TIME:
        raise CheckFailed(
            f"dataTime: asked for the {cfg.RUN_TIME:02d} UTC run, "
            f"file says {got_time}"
        )

    got_step = _get(h, "endStep")
    if got_step != step:
        raise CheckFailed(f"endStep: asked for {step}, file says {got_step}")

    if _get(h, "startStep") != 0:
        raise CheckFailed(
            f"startStep: expected 0 because tp accumulates from the forecast "
            f"start, got {_get(h, 'startStep')}"
        )

    # Grid orientation. If this ever changes, the reshape below would silently
    # flip India upside down, so it is checked rather than assumed.
    if _get(h, "jScansPositively", 0) != 0:
        raise CheckFailed("jScansPositively is not 0: latitude is not descending")
    if _get(h, "iScansNegatively", 0) != 0:
        raise CheckFailed("iScansNegatively is not 0: longitude is not ascending")

    first_lat = _get(h, "latitudeOfFirstGridPointInDegrees")
    first_lon = _get(h, "longitudeOfFirstGridPointInDegrees")
    if first_lat is None or abs(first_lat - 90.0) > 1e-6:
        raise CheckFailed(f"first latitude is {first_lat}, expected 90")
    if first_lon is None:
        raise CheckFailed("the file has no first longitude")

    # The origin is not fixed: ECMWF used 0 until about 20 October 2026 and
    # 180 afterwards. Any origin on the 0.25 grid is acceptable, as long as
    # India comes out contiguous. india_cols_for raises if it does not.
    try:
        cfg.india_slice(first_lat, first_lon)
    except cfg.GridLayoutError as exc:
        raise CheckFailed(str(exc)) from exc


def check_quantum_cap(coarsest_quantum: float) -> None:
    """Reject a date whose storage precision is too coarse to trust.

    SPEC 3.6: above 0.5 mm the rounding is too rough relative to the 1 mm
    threshold, so the file is not used at all.
    """
    if coarsest_quantum > cfg.MAX_TRUSTED_QUANTUM:
        raise CheckFailed(
            f"coarsest packing quantum is {coarsest_quantum:.6f} mm, above the "
            f"{cfg.MAX_TRUSTED_QUANTUM} mm cap: too coarse to trust against "
            "the 1 mm threshold"
        )


def check_daily_differences(tp: np.ndarray, tolerance: float) -> dict:
    """Difference the accumulated field and apply the SPEC 3.6 negative rule.

    tp is shaped (n_steps, n_members, n_lat, n_lon) and holds ACCUMULATED
    precipitation. ``tolerance`` is the most negative difference allowed, a
    negative number derived from the date's packing quantum.

    Differences between ``tolerance`` and 0 are packing noise and are reported
    as values that will be set to 0. Anything below ``tolerance`` raises.
    """
    diffs = np.diff(tp, axis=0)  # (n_days, n_members, n_lat, n_lon)
    worst = float(diffs.min())

    if worst < tolerance:
        bad = int((diffs < tolerance).sum())
        raise CheckFailed(
            f"daily difference of {worst:.6f} mm is below the tolerance of "
            f"{tolerance:.6f} mm ({bad} values affected)"
        )

    n_clamped = int(((diffs < 0) & (diffs >= tolerance)).sum())
    return {
        "tolerance_mm": round(tolerance, 6),
        "most_negative_difference_mm": round(worst, 6),
        "values_set_to_zero": n_clamped,
        "max_daily_total_mm": round(float(diffs.max()), 4),
        "shape": list(diffs.shape),
    }
