"""Build the India mask on the 0.25 degree ECMWF grid.

SPEC 3.5. A square counts as India when its centre lies inside or on India's
outline AND the ECMWF land-sea mask for that square is at least 0.5.

The outline is Natural Earth admin-0 countries, India point-of-view edition,
which shows India's official boundaries. It decides only which squares count;
the published map does not draw national borders.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path

import eccodes as ec
import numpy as np
import shapefile  # pyshp
from shapely.geometry import Point, shape
from shapely.prepared import prep

from . import config as cfg

NE_URL = (
    "https://naturalearth.s3.amazonaws.com/10m_cultural/"
    "ne_10m_admin_0_countries_ind.zip"
)
NE_LAYER = "ne_10m_admin_0_countries_ind"
NE_VERSION = "5.1.1"
NE_DIR = cfg.RAW / "ne"

LSM_FILE = cfg.RAW / "probe_lsm_aifs-ens.grib2"
LSM_THRESHOLD = 0.5

MASK_FILE = cfg.ROOT / "config" / "india_mask.json"

# Reporting boxes only; they do not affect the rule (SPEC 3.5).
ISLAND_GROUPS = {
    "Andaman & Nicobar": {"lat": (6.0, 14.0), "lon": (92.0, 94.5)},
    "Lakshadweep": {"lat": (8.0, 12.5), "lon": (71.5, 74.0)},
}


class MaskError(Exception):
    """The mask could not be built from trustworthy inputs."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_outline() -> tuple[Path, str]:
    """Fetch the Natural Earth India POV outline. Returns (zip path, sha256)."""
    import requests

    NE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = NE_DIR / f"{NE_LAYER}.zip"

    if not zip_path.exists():
        response = requests.get(NE_URL, timeout=(30, 120))
        response.raise_for_status()
        part = zip_path.with_suffix(".zip.part")
        part.write_bytes(response.content)
        part.replace(zip_path)

    digest = sha256(zip_path)

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(NE_DIR)

    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        if not (NE_DIR / f"{NE_LAYER}{suffix}").exists():
            raise MaskError(f"{NE_LAYER}{suffix} missing from the archive")

    return zip_path, digest


def load_india_geometry():
    """The India polygon. Fails unless there is exactly one India feature."""
    reader = shapefile.Reader(str(NE_DIR / NE_LAYER))
    fields = [f[0] for f in reader.fields[1:]]
    if "NAME" not in fields:
        raise MaskError(f"shapefile has no NAME field, found {fields}")
    name_index = fields.index("NAME")

    matches = [
        sr for sr in reader.iterShapeRecords()
        if sr.record[name_index] == "India"
    ]
    if len(matches) != 1:
        raise MaskError(
            f"expected exactly one feature named India, found {len(matches)}"
        )

    geometry = shape(matches[0].shape.__geo_interface__)
    if geometry.is_empty:
        raise MaskError("the India geometry is empty")
    return geometry


def read_lsm_with_halo() -> np.ndarray:
    """India land-sea mask with a one-square border on every side.

    The halo exists so that squares on the edge of the India box have real
    neighbours when the coastal test runs, rather than being judged against
    nothing. Shape is (N_LAT + 2, N_LON + 2).

    The longitude origin comes from the file itself, never assumed
    (SPEC 2.5): ECMWF changed it from 0 to 180 around 20 October 2026.
    """
    if not LSM_FILE.exists():
        raise MaskError(f"{LSM_FILE} is missing; the mask needs it")

    with open(LSM_FILE, "rb") as f:
        h = ec.codes_grib_new_from_file(f)
        if h is None:
            raise MaskError(f"{LSM_FILE.name} contains no GRIB message")
        try:
            if ec.codes_get(h, "shortName") != "lsm":
                raise MaskError(f"{LSM_FILE.name} is not a land-sea mask")
            rows, cols = cfg.india_slice(
                ec.codes_get(h, "latitudeOfFirstGridPointInDegrees"),
                ec.codes_get(h, "longitudeOfFirstGridPointInDegrees"),
            )
            values = ec.codes_get_values(h)
        finally:
            ec.codes_release(h)

    field = values.reshape(cfg.GLOBAL_NJ, cfg.GLOBAL_NI)
    padded = field[
        rows.start - 1: rows.stop + 1,
        cols.start - 1: cols.stop + 1,
    ]
    if padded.shape != (cfg.N_LAT + 2, cfg.N_LON + 2):
        raise MaskError(f"padded lsm has shape {padded.shape}")
    return padded.astype(np.float32)


def centres_inside(geometry) -> np.ndarray:
    """True where a square's centre is inside or on India's outline."""
    prepared = prep(geometry)
    inside = np.zeros((cfg.N_LAT, cfg.N_LON), dtype=bool)
    for i, lat in enumerate(cfg.INDIA_LATS):
        for j, lon in enumerate(cfg.INDIA_LONS):
            # covers() is true on the boundary as well as strictly inside.
            inside[i, j] = prepared.covers(Point(lon, lat))
    return inside


def coastal_from(india: np.ndarray, lsm_padded: np.ndarray) -> np.ndarray:
    """India squares with at least one of their 8 neighbours below the lsm cut.

    SPEC 3.5: this is the coastal definition. It uses the land-sea mask of the
    neighbours, not whether the neighbour is in India, so the border with
    another country does not read as coastline.
    """
    sea = lsm_padded < LSM_THRESHOLD
    has_sea_neighbour = np.zeros((cfg.N_LAT, cfg.N_LON), dtype=bool)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            shifted = sea[
                1 + di: 1 + di + cfg.N_LAT,
                1 + dj: 1 + dj + cfg.N_LON,
            ]
            has_sea_neighbour |= shifted
    return india & has_sea_neighbour


def build() -> dict:
    """Build the mask and return everything needed to save and report it."""
    zip_path, outline_sha = download_outline()
    geometry = load_india_geometry()

    lsm_padded = read_lsm_with_halo()
    lsm = lsm_padded[1:-1, 1:-1]

    inside = centres_inside(geometry)
    land = lsm >= LSM_THRESHOLD
    india = inside & land
    coastal = coastal_from(india, lsm_padded)

    islands = {}
    for name, box in ISLAND_GROUPS.items():
        lat_ok = np.array([box["lat"][0] <= v <= box["lat"][1]
                           for v in cfg.INDIA_LATS])
        lon_ok = np.array([box["lon"][0] <= v <= box["lon"][1]
                           for v in cfg.INDIA_LONS])
        box_mask = lat_ok[:, None] & lon_ok[None, :]
        islands[name] = {
            "squares_in_box": int(box_mask.sum()),
            "centre_inside_outline": int((inside & box_mask).sum()),
            "also_lsm_at_least_0_5": int((india & box_mask).sum()),
            "max_lsm_in_box": round(float(lsm[box_mask].max()), 4),
        }

    return {
        "india": india,
        "coastal": coastal,
        "inside": inside,
        "lsm": lsm,
        "islands": islands,
        "outline_zip": zip_path,
        "outline_sha256": outline_sha,
    }


def save(result: dict, path: Path = MASK_FILE) -> dict:
    """Write config/india_mask.json. Rows are strings of 0 and 1."""
    india = result["india"]
    coastal = result["coastal"]

    record = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "spec_section": "3.5",
        "grid": {
            "n_lat": cfg.N_LAT,
            "n_lon": cfg.N_LON,
            "lat_first": cfg.LAT_MAX,
            "lat_last": cfg.LAT_MIN,
            "lon_first": cfg.LON_MIN,
            "lon_last": cfg.LON_MAX,
            "step": cfg.GRID_STEP,
            "lat_order": "descending, row 0 is latitude 38.0",
        },
        "outline": {
            "source": "Natural Earth admin-0 countries, India point-of-view",
            "layer": NE_LAYER,
            "version": NE_VERSION,
            "url": NE_URL,
            "sha256": result["outline_sha256"],
            "licence": "public domain",
        },
        "land_sea_mask": {
            "file": LSM_FILE.name,
            "sha256": sha256(LSM_FILE),
            "threshold": LSM_THRESHOLD,
        },
        "rules": {
            "india": "centre inside or on the outline AND lsm >= 0.5",
            "coastal": ("an India square with at least one of its 8 "
                        "neighbours having lsm < 0.5"),
        },
        "counts": {
            "squares_in_box": int(india.size),
            "centre_inside_outline": int(result["inside"].sum()),
            "india": int(india.sum()),
            "coastal": int(coastal.sum()),
            "inland": int(india.sum() - coastal.sum()),
        },
        "island_groups": result["islands"],
        "lat": [round(v, 2) for v in cfg.INDIA_LATS],
        "lon": [round(v, 2) for v in cfg.INDIA_LONS],
        "india_rows": ["".join("1" if v else "0" for v in row) for row in india],
        "coastal_rows": ["".join("1" if v else "0" for v in row)
                         for row in coastal],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(record, indent=1), encoding="utf-8")

    # Reopen and check before replacing the real file.
    reloaded = json.loads(part.read_text(encoding="utf-8"))
    back = np.array([[c == "1" for c in row]
                     for row in reloaded["india_rows"]], dtype=bool)
    if not np.array_equal(back, india):
        raise MaskError("the reopened mask does not match what was written")
    part.replace(path)
    return record


def load(path: Path = MASK_FILE) -> dict:
    """Read the saved mask back as boolean arrays."""
    record = json.loads(Path(path).read_text(encoding="utf-8"))
    record["india"] = np.array(
        [[c == "1" for c in row] for row in record["india_rows"]], dtype=bool)
    record["coastal"] = np.array(
        [[c == "1" for c in row] for row in record["coastal_rows"]], dtype=bool)
    return record


def index_of(lat: float, lon: float) -> tuple[int, int]:
    """Grid indices of the square whose centre is at this lat/lon."""
    i = int(round((cfg.LAT_MAX - lat) / cfg.GRID_STEP))
    j = int(round((lon - cfg.LON_MIN) / cfg.GRID_STEP))
    if not (0 <= i < cfg.N_LAT and 0 <= j < cfg.N_LON):
        raise MaskError(f"lat {lat} lon {lon} is outside the India box")
    return i, j


if __name__ == "__main__":
    result = build()
    record = save(result)
    counts = record["counts"]
    print(f"squares in the box       : {counts['squares_in_box']}")
    print(f"centre inside the outline: {counts['centre_inside_outline']}")
    print(f"India (also lsm >= 0.5)  : {counts['india']}")
    print(f"  of which coastal       : {counts['coastal']}")
    print(f"  of which inland        : {counts['inland']}")
    print(f"outline sha256           : {record['outline']['sha256'][:32]}...")
    print()
    for name, info in record["island_groups"].items():
        print(f"{name}:")
        print(f"  squares in box          : {info['squares_in_box']}")
        print(f"  centre inside outline   : {info['centre_inside_outline']}")
        print(f"  surviving lsm >= 0.5    : {info['also_lsm_at_least_0_5']}")
        print(f"  highest lsm in that box : {info['max_lsm_in_box']}")
