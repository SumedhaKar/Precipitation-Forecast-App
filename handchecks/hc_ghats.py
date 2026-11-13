"""HC-GHATS: one monsoon day of remapped IMERG, drawn, with the Ghats measured.

The remap of SPEC 3.3 is arithmetic, and HC5 and HC9 check the arithmetic of
one cell by hand. This check asks the different question: **does the finished
field look like India?** A remap can be exactly right cell by cell and still
be flipped, rolled or transposed as a whole, and no per-cell check would
notice. Geography notices.

In July the monsoon westerlies are lifted by the Western Ghats, and the
heaviest daily rain in peninsular India falls on the narrow windward strip
between the coast and the crest, with a rain shadow immediately east of it.
That is the oldest and least arguable fact about Indian rainfall, so it is
the one used here.

What is checked

  1. The wettest India squares of the day are inside the Ghats strip.
  2. The windward strip is much wetter than the leeward strip at the same
     latitudes on the same day.
  3. The picture itself, `hc_ghats.png`, for a reader to look at.

**The day is chosen by rule, not picked**: the July 2026 day with the highest
area-weighted mean rain over India, cos(latitude) weighted, over the squares
that have a value. The rule is on the rain alone and knows nothing about
where the rain is, so it cannot be chosen to flatter the strip test.

What is taken rather than redone, and is therefore not what this checks: the
remap itself, read from `data/india/nasa/<date>.npz` as the pipeline wrote
it; and the India mask, read from `config/`. Those have HC5, HC9 and the mask
tests. The grid geometry is read from `pipeline/config.py`, and HC-ALIGN
checks that against the files.

Needs Pillow, which is installed in the virtual environment and is not a
pipeline dependency: nothing in `pipeline/` draws anything.

    python handchecks/hc_ghats.py
    python handchecks/hc_ghats.py --month 202607 --sabotage
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import config as cfg                          # noqa: E402
from pipeline.india_mask import load as load_mask           # noqa: E402

OUT = ROOT / "handchecks" / "results"

# The two strips, in degrees. Windward: the coast and the crest, which the
# 0.25 degree grid cannot separate. Leeward: the rain shadow, far enough east
# to be clear of the crest and still west of the Eastern Ghats.
LAT_LO, LAT_HI = 8.0, 21.0
WINDWARD = (72.5, 76.0)
LEEWARD = (76.25, 79.75)
TOP_SQUARES = 25

# Discrete bins, because a continuous ramp invites reading a colour as a
# number. Edges in mm; the colour of a square is the bin it falls in.
BINS = (0.0, 1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 150.0)
COLOURS = ((245, 245, 242), (222, 235, 247), (185, 215, 236), (133, 186, 220),
           (82, 152, 203), (42, 112, 175), (24, 72, 140), (12, 36, 96))
NOT_INDIA = (232, 232, 230)
NO_VALUE = (150, 150, 150)
CELL = 7
PAD_L, PAD_T, PAD_R, PAD_B = 54, 52, 20, 108


def font(size: int):
    """A readable font if the machine has one, Pillow's own if it does not."""
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def day_mean(rain: np.ndarray, india: np.ndarray,
             weight: np.ndarray) -> float:
    """Area-weighted mean rain over the India squares that have a value."""
    usable = india & np.isfinite(rain)
    if not usable.any():
        return float("nan")
    return float((rain[usable] * weight[usable]).sum() / weight[usable].sum())


def choose_day(month: str, india: np.ndarray,
               weight: np.ndarray) -> tuple[str, list]:
    """The wettest day of the month over India, and the whole ranking."""
    ranked = []
    for path in sorted(cfg.INDIA_NASA.glob(f"{month}*.npz")):
        with np.load(path) as f:
            ranked.append((day_mean(f["rain"], india, weight), path.stem))
    if not ranked:
        raise SystemExit(f"no remapped IMERG days for {month} in "
                         f"{cfg.INDIA_NASA}")
    ranked.sort(reverse=True)
    return ranked[0][1], ranked


def strip(lat: np.ndarray, lon: np.ndarray, west: float, east: float,
          india: np.ndarray, rain: np.ndarray) -> np.ndarray:
    """The India squares with a value inside one longitude strip."""
    rows = (lat >= LAT_LO) & (lat <= LAT_HI)
    cols = (lon >= west) & (lon <= east)
    return rows[:, None] & cols[None, :] & india & np.isfinite(rain)


def bin_of(value: float) -> int:
    at = 0
    for edge in BINS[1:]:
        if value >= edge:
            at += 1
    return at


def draw(rain: np.ndarray, india: np.ndarray, lat: np.ndarray,
         lon: np.ndarray, date: str, note: str, to: Path) -> None:
    """The day as a picture: one rectangle per square, bins for colours."""
    rows, cols = rain.shape
    width = PAD_L + cols * CELL + PAD_R
    height = PAD_T + rows * CELL + PAD_B
    image = Image.new("RGB", (width, height), "white")
    pen = ImageDraw.Draw(image)
    small, big = font(12), font(14)

    for i in range(rows):
        for j in range(cols):
            box = (PAD_L + j * CELL, PAD_T + i * CELL,
                   PAD_L + (j + 1) * CELL - 1, PAD_T + (i + 1) * CELL - 1)
            if not india[i, j]:
                pen.rectangle(box, fill=NOT_INDIA)
            elif not np.isfinite(rain[i, j]):
                pen.rectangle(box, fill=NO_VALUE)
            else:
                pen.rectangle(box, fill=COLOURS[bin_of(float(rain[i, j]))])

    def x_of(degrees: float) -> int:
        return PAD_L + int(round((degrees - (lon[0] - 0.125)) / 0.25)) * CELL

    def y_of(degrees: float) -> int:
        return PAD_T + int(round(((lat[0] + 0.125) - degrees) / 0.25)) * CELL

    for west, east, colour, name in ((WINDWARD[0], WINDWARD[1], (200, 40, 40),
                                      "windward"),
                                     (LEEWARD[0], LEEWARD[1], (40, 120, 40),
                                      "leeward")):
        pen.rectangle((x_of(west - 0.125), y_of(LAT_HI + 0.125),
                       x_of(east + 0.125) - 1, y_of(LAT_LO - 0.125) - 1),
                      outline=colour, width=2)
        pen.text((x_of(west - 0.125) + 3, y_of(LAT_HI + 0.125) - 15), name,
                 fill=colour, font=small)

    # Degree ticks every 5, so a reader can place the strips themselves.
    for degrees in range(70, 100, 5):
        if lon[0] <= degrees <= lon[-1]:
            pen.text((x_of(degrees) - 8, PAD_T + rows * CELL + 4),
                     f"{degrees}E", fill=(60, 60, 60), font=small)
    for degrees in range(10, 40, 5):
        if lat[-1] <= degrees <= lat[0]:
            pen.text((6, y_of(degrees) - 6), f"{degrees}N",
                     fill=(60, 60, 60), font=small)

    pen.text((PAD_L, 10), "IMERG Late V07C, remapped to the 0.25 degree "
             f"India grid: {date[:4]}-{date[4:6]}-{date[6:]}",
             fill=(20, 20, 20), font=big)
    pen.text((PAD_L, 26), note, fill=(90, 90, 90), font=small)

    base = PAD_T + rows * CELL + 26
    pen.text((PAD_L, base), "mm in the day", fill=(20, 20, 20), font=big)
    for at, colour in enumerate(COLOURS):
        left = PAD_L + at * 74
        pen.rectangle((left, base + 18, left + 68, base + 36), fill=colour,
                      outline=(120, 120, 120))
        label = (f"{BINS[at]:g} and over" if at == len(COLOURS) - 1
                 else f"{BINS[at]:g} to {BINS[at + 1]:g}")
        pen.text((left, base + 40), label, fill=(60, 60, 60), font=small)
    pen.text((PAD_L, base + 56), "grey: outside India, or no value "
             "(SPEC 3.4's 90% rule)", fill=(90, 90, 90), font=small)
    image.save(to)


def check(rain: np.ndarray, india: np.ndarray, lat: np.ndarray,
          lon: np.ndarray) -> dict:
    """The two measurements, and the squares they rest on."""
    inside = india & np.isfinite(rain)
    order = sorted(((float(rain[i, j]), float(lat[i]), float(lon[j]))
                    for i, j in zip(*np.nonzero(inside))), reverse=True)
    top = order[:TOP_SQUARES]
    in_strip = sum(1 for mm, la, lo in top
                   if LAT_LO <= la <= LAT_HI
                   and WINDWARD[0] <= lo <= WINDWARD[1])
    wind = strip(lat, lon, WINDWARD[0], WINDWARD[1], india, rain)
    lee = strip(lat, lon, LEEWARD[0], LEEWARD[1], india, rain)
    return {
        "top": top,
        "in_strip": in_strip,
        "windward_mm": float(rain[wind].mean()), "windward_n": int(wind.sum()),
        "leeward_mm": float(rain[lee].mean()), "leeward_n": int(lee.sum()),
        "india_squares": int(inside.sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="202607")
    ap.add_argument("--sabotage", action="store_true",
                    help="also run the check on a flipped and a rolled field")
    args = ap.parse_args()

    mask = load_mask()["india"]
    lat = np.array(cfg.INDIA_LATS, dtype=float)
    lon = np.array(cfg.INDIA_LONS, dtype=float)
    weight = np.cos(np.radians(lat))[:, None] * np.ones((1, len(lon)))

    date, ranked = choose_day(args.month, mask, weight)
    with np.load(cfg.INDIA_NASA / f"{date}.npz") as f:
        rain = np.array(f["rain"], dtype=float)
    got = check(rain, mask, lat, lon)

    OUT.mkdir(parents=True, exist_ok=True)
    picture = OUT / "hc_ghats.png"
    draw(rain, mask, lat, lon, date,
         f"the windward strip averaged {got['windward_mm']:.1f} mm, "
         f"the leeward strip {got['leeward_mm']:.1f} mm", picture)

    sabotages = []
    if args.sabotage:
        square = min(rain.shape)
        transposed = np.vstack([rain[:square, :square].T, rain[square:, :]])
        for what, field in (
            ("the field drawn upside down", rain[::-1, :]),
            ("the field rolled four squares east", np.roll(rain, 4, axis=1)),
            ("the square part of the field transposed", transposed),
        ):
            broken = check(field, mask, lat, lon)
            bites = (broken["in_strip"] < TOP_SQUARES
                     or broken["windward_mm"] < 2 * broken["leeward_mm"])
            sabotages.append((what, "CAUGHT" if bites else "missed",
                              f"{broken['in_strip']} of {TOP_SQUARES} top "
                              f"squares in the strip, windward "
                              f"{broken['windward_mm']:.1f} mm against "
                              f"leeward {broken['leeward_mm']:.1f} mm"))

    out = OUT / "hc_ghats.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["hc-ghats", "one monsoon day of remapped IMERG, SPEC 3.3"])
        w.writerow(["date", date])
        w.writerow(["date_rule", f"the {args.month} day with the highest "
                    "cos(latitude) weighted mean rain over India"])
        w.writerow(["days_ranked", len(ranked)])
        w.writerow(["india_mean_mm", f"{ranked[0][0]:.4f}"])
        w.writerow(["second_place",
                    f"{ranked[1][1]} at {ranked[1][0]:.4f} mm"])
        w.writerow(["india_squares_with_a_value", got["india_squares"]])
        w.writerow(["windward_strip", f"{LAT_LO} to {LAT_HI} N, "
                    f"{WINDWARD[0]} to {WINDWARD[1]} E"])
        w.writerow(["leeward_strip", f"{LAT_LO} to {LAT_HI} N, "
                    f"{LEEWARD[0]} to {LEEWARD[1]} E"])
        w.writerow(["picture", picture.name])
        w.writerow([])
        w.writerow(["what", "value", "squares"])
        w.writerow(["windward mean mm", f"{got['windward_mm']:.4f}",
                    got["windward_n"]])
        w.writerow(["leeward mean mm", f"{got['leeward_mm']:.4f}",
                    got["leeward_n"]])
        w.writerow(["windward over leeward",
                    f"{got['windward_mm'] / got['leeward_mm']:.2f}", ""])
        w.writerow([f"the {TOP_SQUARES} wettest squares inside the windward "
                    "strip", f"{got['in_strip']} of {TOP_SQUARES}", ""])
        outside = [f"{la:.2f} N {lo:.2f} E" for mm, la, lo in got["top"]
                   if not (LAT_LO <= la <= LAT_HI
                           and WINDWARD[0] <= lo <= WINDWARD[1])]
        if outside:
            w.writerow(["the ones outside the strip", "; ".join(outside),
                        "the strip is cut at a round number of degrees and "
                        "the hills do not stop there"])
        w.writerow([])
        w.writerow(["rank", "mm", "lat", "lon", "in_windward_strip"])
        for at, (mm, la, lo) in enumerate(got["top"], start=1):
            w.writerow([at, f"{mm:.2f}", f"{la:.2f}", f"{lo:.2f}",
                        "yes" if (LAT_LO <= la <= LAT_HI
                                  and WINDWARD[0] <= lo <= WINDWARD[1])
                        else "no"])
        if sabotages:
            w.writerow([])
            w.writerow(["sabotage", "outcome", "note"])
            for row in sabotages:
                w.writerow(row)

    print(f"{date}: windward {got['windward_mm']:.1f} mm over "
          f"{got['windward_n']} squares, leeward {got['leeward_mm']:.1f} mm "
          f"over {got['leeward_n']}, "
          f"{got['in_strip']}/{TOP_SQUARES} wettest squares in the strip")
    for row in sabotages:
        print(f"  {row[1]}: {row[0]} -- {row[2]}")
    print(f"wrote {out} and {picture}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
