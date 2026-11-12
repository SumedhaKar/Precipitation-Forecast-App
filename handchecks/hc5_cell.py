"""HC5: dump every IMERG pixel that goes into one ECMWF cell.

The point is that the area-weighted mean can be recomputed by hand, in a
spreadsheet, from the CSV this writes. Nothing has to be taken on trust:
every pixel's edges, value, count, overlap fraction and weight are printed,
and so is the value the program produced.

The cell is chosen, not hand-picked: the wettest India square-day in July
2026 whose centre is on or near the west coast (latitude 8 to 22 N, longitude
at most 76 E).

Usage
  python handchecks/hc5_cell.py                     choose the cell
  python handchecks/hc5_cell.py 20260722 20.25 72.75   or name it
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config as cfg                           # noqa: E402
from pipeline.nasa_download import existing_file             # noqa: E402
from pipeline.nasa_process import (                          # noqa: E402
    COMPLETE_CNT,
    MIN_COMPLETE_FRACTION,
    build_remap,
    nasa_path,
    pile_b_dates,
    read_grid,
    read_window,
    remap,
)
from pipeline.india_mask import load as load_mask            # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "hc5_cell.csv"

LAT_LOW, LAT_HIGH = 8.0, 22.0
LON_HIGH = 76.0


def choose_cell() -> tuple[str, int, int]:
    """Wettest July India square-day in the west-coast window."""
    india = load_mask()["india"]
    lat = np.asarray(cfg.INDIA_LATS)
    lon = np.asarray(cfg.INDIA_LONS)
    west = (india
            & ((lat >= LAT_LOW) & (lat <= LAT_HIGH))[:, None]
            & (lon <= LON_HIGH)[None, :])

    best = (-1.0, None, None, None)
    for date in pile_b_dates():
        if date[4:6] != "07" or not nasa_path(date).exists():
            continue
        with np.load(nasa_path(date)) as f:
            rain = f["rain"]
        masked = np.where(west & np.isfinite(rain), rain, -np.inf)
        i, j = np.unravel_index(int(np.argmax(masked)), masked.shape)
        if float(masked[i, j]) > best[0]:
            best = (float(masked[i, j]), date, int(i), int(j))
    if best[1] is None:
        raise SystemExit("no processed July date found")
    print(f"chosen: {best[1]} cell {cfg.INDIA_LATS[best[2]]} N "
          f"{cfg.INDIA_LONS[best[3]]} E, {best[0]:.2f} mm")
    return best[1], best[2], best[3]


def main() -> int:
    if len(sys.argv) == 4:
        date = sys.argv[1]
        i = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LATS) - float(sys.argv[2]))))
        j = int(np.argmin(np.abs(np.asarray(cfg.INDIA_LONS) - float(sys.argv[3]))))
    else:
        date, i, j = choose_cell()

    path = existing_file(date)
    if path is None:
        raise SystemExit(f"{date}: no raw IMERG file")

    with h5py.File(path, "r") as f:
        lat_edges, lon_edges = read_grid(f, path.name)
        remapper = build_remap(lat_edges, lon_edges)
        rain_w, cnt_w, _ = read_window(f, remapper, date, path.name)

    rain, fraction = remap(remapper, rain_w, cnt_w)

    half = cfg.GRID_STEP / 2.0
    cell_top = cfg.INDIA_LATS[i] + half
    cell_bot = cfg.INDIA_LATS[i] - half
    cell_left = cfg.INDIA_LONS[j] - half
    cell_right = cfg.INDIA_LONS[j] + half

    lat_desc = remapper.lat_edges_window_desc
    lon_asc = remapper.lon_edges_window

    rows = []
    for a in range(remapper.n_lat_window):
        p_top, p_bot = lat_desc[a], lat_desc[a + 1]
        top = min(p_top, cell_top)
        bot = max(p_bot, cell_bot)
        if top <= bot:
            continue
        for b in range(remapper.n_lon_window):
            p_left, p_right = lon_asc[b], lon_asc[b + 1]
            right = min(p_right, cell_right)
            left = max(p_left, cell_left)
            if right <= left:
                continue

            pixel_area = ((p_right - p_left)
                          * (math.sin(math.radians(p_top))
                             - math.sin(math.radians(p_bot))))
            weight = ((right - left)
                      * (math.sin(math.radians(top))
                         - math.sin(math.radians(bot))))
            value = float(rain_w[a, b])
            count = int(cnt_w[a, b])
            rows.append({
                "pixel_lat_bottom": round(p_bot, 6),
                "pixel_lat_top": round(p_top, 6),
                "pixel_lon_left": round(p_left, 6),
                "pixel_lon_right": round(p_right, 6),
                "overlap_lat_bottom": round(bot, 6),
                "overlap_lat_top": round(top, 6),
                "overlap_lon_left": round(left, 6),
                "overlap_lon_right": round(right, 6),
                "value_mm": "" if not np.isfinite(value) else repr(float(value)),
                "cnt": count,
                "complete": int(count == COMPLETE_CNT and np.isfinite(value)),
                "overlap_fraction_of_pixel": repr(float(weight / pixel_area)),
                "weight": repr(float(weight)),
            })

    total_weight = sum(float(r["weight"]) for r in rows)
    complete_weight = sum(float(r["weight"]) for r in rows if r["complete"])
    by_hand = (sum(float(r["weight"]) * float(r["value_mm"])
                   for r in rows if r["complete"]) / complete_weight)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# HC5: every IMERG pixel overlapping one ECMWF cell\n")
        fh.write(f"# IMERG file,{path.name}\n")
        fh.write(f"# date,{date}\n")
        fh.write(f"# cell centre lat N,{cfg.INDIA_LATS[i]}\n")
        fh.write(f"# cell centre lon E,{cfg.INDIA_LONS[j]}\n")
        fh.write(f"# cell latitude range,{cell_bot} to {cell_top}\n")
        fh.write(f"# cell longitude range,{cell_left} to {cell_right}\n")
        fh.write("# weight,overlap_lon_degrees * (sin(overlap_lat_top) - "
                 "sin(overlap_lat_bottom))\n")
        fh.write("# cell value = sum(weight * value over complete pixels) / "
                 "sum(weight over complete pixels)\n")
        fh.write(f"# sum of weights,{float(total_weight)!r}\n")
        fh.write(f"# analytic cell area,"
                 f"{float(remapper.cell_area[i * cfg.N_LON + j])!r}\n")
        fh.write(f"# sum of weights over complete pixels,{float(complete_weight)!r}\n")
        fh.write(f"# complete_fraction reported by the program,"
                 f"{float(fraction[i, j])!r}\n")
        fh.write(f"# usable threshold,{MIN_COMPLETE_FRACTION}\n")
        fh.write(f"# cell value reported by the program mm,{float(rain[i, j])!r}\n")
        fh.write(f"# cell value recomputed here from these rows mm,{float(by_hand)!r}\n")
        fh.write(f"# pixels overlapping this cell,{len(rows)}\n")
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {OUT}")
    print(f"  pixels overlapping the cell  {len(rows)}")
    print(f"  sum of weights               {float(total_weight)!r}")
    print(f"  analytic cell area           "
          f"{float(remapper.cell_area[i * cfg.N_LON + j])!r}")
    print(f"  complete fraction            {float(fraction[i, j])!r}")
    print(f"  program cell value mm        {float(rain[i, j])!r}")
    print(f"  recomputed from the rows mm  {float(by_hand)!r}")
    print(f"  difference mm                {float(abs(by_hand - rain[i, j]))!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
