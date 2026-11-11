"""Downloading and checking NASA IMERG Late daily files.

SPEC 2.3. One file is one date. Authentication uses the Earthdata login
already stored in netrc on this machine; no password is read, printed, stored
or asked for anywhere in this project.
"""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

import h5py

from . import config as cfg

SHORT_NAME = "GPM_3IMERGDL"
VERSION = "07"
REQUIRED_FILE_VERSION = "V07C"   # never mix versions
EXPECT_NLON = 3600
EXPECT_NLAT = 1800
EXPECT_UNITS = "mm/day"
REQUIRED_VARIABLES = ("precipitation", "precipitation_cnt")

CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120
MAX_ATTEMPTS = 3


class ImergCheckFailed(Exception):
    """A downloaded IMERG file is not what was asked for."""


def force_requests_timeout() -> None:
    """Give every requests call a timeout, so a stalled read cannot hang.

    Same failure mode that hung the ECMWF downloads on 12 November 2026: with
    no timeout a dead socket blocks forever instead of raising. earthaccess
    does not expose a timeout setting, so it is injected here.
    """
    import requests

    if getattr(requests.Session, "_pf_timeout_patched", False):
        return

    original = requests.Session.request

    def request(self, *args, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (CONNECT_TIMEOUT, READ_TIMEOUT)
        return original(self, *args, **kwargs)

    requests.Session.request = request
    requests.Session._pf_timeout_patched = True


def imerg_dir() -> Path:
    return cfg.RAW / "imerg"


def imerg_done_path(date: str) -> Path:
    return cfg.DONE / f"imerg_{date}.json"


def imerg_failure_path(date: str) -> Path:
    return cfg.FAILURES / f"imerg_{date}.json"


def existing_file(date: str) -> Path | None:
    """The already-downloaded file for this date, if there is one."""
    matches = sorted(imerg_dir().glob(f"3B-DAY-L.MS.MRG.3IMERG.{date}-*.nc4"))
    return matches[0] if matches else None


def check_file(path: Path, date: str) -> dict:
    """Apply every SPEC 2.3 check. Returns a summary. Raises on failure."""
    name = path.name

    # Version first: a wrong version must be logged and refused, never mixed.
    if REQUIRED_FILE_VERSION not in name:
        raise ImergCheckFailed(
            f"{name}: expected {REQUIRED_FILE_VERSION}, refusing to mix versions"
        )

    # The date in the file name must be the date we asked for.
    marker = f"3IMERG.{date}-"
    if marker not in name:
        raise ImergCheckFailed(f"{name}: file name is not for date {date}")

    with h5py.File(path, "r") as f:
        def attr(key):
            v = f.attrs.get(key)
            return v.decode() if isinstance(v, bytes) else v

        for var in REQUIRED_VARIABLES:
            if var not in f:
                raise ImergCheckFailed(f"{name}: variable {var} is missing")

        units = f["precipitation"].attrs.get("units")
        units = units[0] if hasattr(units, "__len__") and not isinstance(units, (str, bytes)) else units
        units = units.decode() if isinstance(units, bytes) else str(units)
        if units != EXPECT_UNITS:
            raise ImergCheckFailed(
                f"{name}: precipitation units are {units!r}, expected "
                f"{EXPECT_UNITS!r}"
            )

        shape = f["precipitation"].shape
        if shape[-2:] != (EXPECT_NLON, EXPECT_NLAT):
            raise ImergCheckFailed(
                f"{name}: grid is {shape}, expected (.., {EXPECT_NLON}, "
                f"{EXPECT_NLAT})"
            )

        begin_date = attr("BeginDate")
        begin_time = attr("BeginTime")
        end_time = attr("EndTime")

        wanted = dt.datetime.strptime(date, "%Y%m%d").date().isoformat()
        if begin_date != wanted:
            raise ImergCheckFailed(
                f"{name}: BeginDate is {begin_date}, asked for {wanted}"
            )
        if not str(begin_time).startswith("00:00:00"):
            raise ImergCheckFailed(
                f"{name}: BeginTime is {begin_time}, expected 00:00:00"
            )

    return {
        "file": name,
        "bytes": path.stat().st_size,
        "file_version": REQUIRED_FILE_VERSION,
        "begin_date": begin_date,
        "begin_time": begin_time,
        "end_time": end_time,
        "grid": list(shape),
        "units": units,
        "variables_present": list(REQUIRED_VARIABLES),
    }


def download_date(date: str) -> dict:
    """Download, check and store one IMERG day. Returns a done record."""
    import earthaccess

    out = imerg_dir()
    out.mkdir(parents=True, exist_ok=True)

    iso = dt.datetime.strptime(date, "%Y%m%d").date().isoformat()
    results = earthaccess.search_data(
        short_name=SHORT_NAME, version=VERSION, temporal=(iso, iso)
    )
    if not results:
        raise ImergCheckFailed(f"{date}: no granule found")
    if len(results) > 1:
        raise ImergCheckFailed(
            f"{date}: {len(results)} granules found, expected exactly 1"
        )

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tmp = Path(tempfile.mkdtemp(prefix=f"imerg_{date}_", dir=str(out)))
        try:
            got = earthaccess.download(results[:1], str(tmp), threads=1)
            if not got:
                raise ImergCheckFailed("download returned no file")

            downloaded = Path(got[0])
            final = out / downloaded.name
            part = final.with_suffix(final.suffix + ".part")

            if part.exists():
                part.unlink()
            shutil.move(str(downloaded), str(part))

            # Check the .part before it is allowed to become the real file.
            summary = check_file(part, date)
            part.replace(final)

            # Report the final name, not the .part it was checked under.
            summary["file"] = final.name
            summary["attempts"] = attempt
            return summary
        except Exception as exc:
            last_error = exc
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    raise ImergCheckFailed(
        f"{date}: failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )
