"""Score every past forecast against the satellite estimate.

SPEC 5, with the decisions of 5.11. Reads the Pile A forecasts and the Pile B
observations already on disk, scores each case, and writes
`results/verification.json` and `results/verification_meta.json`. It assigns
no labels; that is `pipeline/labels.py`.

    python -m pipeline.verify                            everything
    python -m pipeline.verify --dates 20260601,20260602  a few dates
    python -m pipeline.verify --no-write                 compute, write nothing

A case is one run date, one India square, one lead day and one threshold
(5.1). The forecast side is `k/51`, the share of model runs reaching the
threshold; the observed side is 1 or 0. Both sides use the same "greater than
or equal to" rule, and the forecast side is recomputed here from the stored
accumulations with `ecmwf_process.daily_totals`, the same code the published
product uses, because Pile A was never published and has no stored counts.

Two passes over the archive, because the reference of 5.3 uses hindsight and
has to be known before any case can be scored:

  pass 1   observations only. How often the event actually happened in each
           square x calendar month of the forecast day x lead day x threshold.
  pass 2   forecasts. Every case scored against its own reference group, and
           collapsed to one row per start date per group (5.5).

Nothing here is tuned to a result. Every number that decides anything -- the
seed, the resample count, the bucket edges, the percentile method -- is a
constant below, written into SPEC 5.11 before this file existed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from . import config as cfg
from .ecmwf_process import daily_totals
from .nasa_process import imerg_date_for

MASK_FILE = cfg.ROOT / "config" / "india_mask.json"
REGIONS_FILE = cfg.ROOT / "config" / "regions.json"
RESULTS = cfg.ROOT / "results"
OUT = RESULTS / "verification.json"
META = RESULTS / "verification_meta.json"

# SPEC 4.2 publishes three. 8 and 12 are the sensitivity of 5.6: a result
# that only holds at exactly 10 mm is not a result.
PUBLISHED_MM = (1.0, 10.0, 50.0)
THRESHOLDS_MM = (1.0, 8.0, 10.0, 12.0, 50.0)

LEADS = (1, 2, 3, 4, 5)

# SPEC 5.11 rule 12. The date sections 5 and 6 were fixed, written down
# before any score existed so it cannot be shopped for.
SEED = 20261112
RESAMPLES = 1000
PERCENTILE_METHOD = "linear"
LOW_PERCENTILE, HIGH_PERCENTILE = 2.5, 97.5

# SPEC 5.11 rule 15. Above this share of resamples with no reference to
# divide by, the group has no range worth printing.
DISCARD_LIMIT = 0.01

# SPEC 6.4. A bucket is counted only if it has this many cases from this many
# different start dates. Used here to mark the buckets; labels.py decides.
BUCKET_MIN_CASES = 100
BUCKET_MIN_DATES = 10

# SPEC 5.11 rule 24. Two different meanings of "block", kept apart.
DATE_BLOCK = 30
BLOCK_DEG = 2.0
BLOCK_MIN_SQUARES = 20

# SPEC 5.11 rule 23. The identity has to hold, not nearly hold.
DECOMPOSITION_TOLERANCE = 1e-12

# SPEC 5.11 rule 31.
PLACES = 6

N_BUCKETS = 12

PERIOD = (
    "Track record from ECMWF AIFS ENS 00 UTC runs of 13 May to 5 November "
    "2026, checked against NASA IMERG Late V07C for 14 May to 10 November "
    "2026. 177 runs over six months, most of them monsoon, so it says little "
    "about winter."
)

# SPEC 5.11 rule 10, the sentence How we checked has to carry.
SMALL_GROUPS_NOTE = (
    "Some reference groups are small -- a square in November has only five "
    "to ten days behind it -- and a small group's own average fits its own "
    "days closely, which makes it harder to beat. Where that happens our "
    "skill is if anything understated."
)


# ----------------------------------------------------------------- buckets

def bucket_table(members: int) -> list[dict]:
    """The reliability buckets of SPEC 5.6, as ranges of `k`.

    `k = 0` alone, `k = members` alone, and the rest in ten equal-width
    buckets of 0.1 by share. Written out as ranges of `k` so that no
    floating-point tie decides which bucket a case is in.
    """
    middles: list[list[int]] = [[] for _ in range(10)]
    for k in range(1, members):
        middles[min(9, (k * 10) // members)].append(k)
    rows = [{"name": "none", "k_from": 0, "k_to": 0}]
    for band in middles:
        rows.append({"name": f"{band[0]}-{band[-1]}",
                     "k_from": band[0], "k_to": band[-1]})
    rows.append({"name": "all", "k_from": members, "k_to": members})
    return rows


def bucket_index(members: int) -> np.ndarray:
    """Bucket number 0 to 11 for every possible `k`."""
    out = np.empty(members + 1, dtype=np.int64)
    out[0] = 0
    out[members] = 11
    for k in range(1, members):
        out[k] = 1 + min(9, (k * 10) // members)
    return out


# ------------------------------------------------------------- the archive

def run_dates() -> list[str]:
    """Pile A dates that are usable: the array and the done record both exist.

    SPEC 5.11 rule 5. A date that failed (3.6) has no array and no done
    record, so it is simply not here, and `gaps` reports it.
    """
    return [path.stem for path in sorted(cfg.INDIA_ECMWF.glob("*.npz"))
            if (cfg.DONE / f"{path.stem}.json").exists()]


def obs_dates() -> set[str]:
    return {path.stem for path in cfg.INDIA_NASA.glob("*.npz")
            if (cfg.DONE / f"nasa_{path.stem}.json").exists()}


def gaps(dates: list[str]) -> list[str]:
    """Dates between the first and the last that are not usable."""
    first = dt.date.fromisoformat(dates[0])
    last = dt.date.fromisoformat(dates[-1])
    have = set(dates)
    out = []
    day = first
    while day <= last:
        stamp = day.strftime("%Y%m%d")
        if stamp not in have:
            out.append(stamp)
        day += dt.timedelta(days=1)
    return out


def load_obs(date: str) -> tuple[np.ndarray, np.ndarray]:
    with np.load(cfg.INDIA_NASA / f"{date}.npz") as handle:
        return (handle["rain"].astype(np.float64),
                handle["complete_fraction"].astype(np.float64))


def load_forecast(date: str) -> np.ndarray:
    with np.load(cfg.INDIA_ECMWF / f"{date}.npz") as handle:
        return handle["tp"]


def load_mask() -> dict:
    record = json.loads(MASK_FILE.read_text(encoding="utf-8"))
    return {
        "india": np.array([[c == "1" for c in row]
                           for row in record["india_rows"]], dtype=bool),
        "coastal": np.array([[c == "1" for c in row]
                             for row in record["coastal_rows"]], dtype=bool),
        "lat": np.array(record["lat"], dtype=float),
        "lon": np.array(record["lon"], dtype=float),
    }


def load_regions() -> dict:
    record = json.loads(REGIONS_FILE.read_text(encoding="utf-8"))
    record["codes"] = np.array(
        [[int(c) for c in row] for row in record["region_rows"]],
        dtype=np.int8)
    return record


# ------------------------------------------------------------------ setup

class Setup:
    """Everything the scoring needs that does not change between dates."""

    def __init__(self, mask: dict, regions: dict, dates, available,
                 thresholds=THRESHOLDS_MM, leads=LEADS):
        india = mask["india"]
        self.india = india
        self.lat = np.asarray(mask["lat"], dtype=float)
        self.lon = np.asarray(mask["lon"], dtype=float)
        self.dates = list(dates)
        self.available = set(available)
        self.thresholds = tuple(float(t) for t in thresholds)
        self.leads = tuple(int(n) for n in leads)
        self.regions = list(regions["regions"])

        rows, cols = np.nonzero(india)
        self.n_sq = int(rows.size)
        self.sq_lat = self.lat[rows]
        self.sq_lon = self.lon[cols]
        self.sq_region = regions["codes"][rows, cols].astype(np.int64) - 1
        if self.n_sq and self.sq_region.min() < 0:
            raise SystemExit("an India square has no region")
        self.sq_coastal = np.asarray(mask["coastal"])[rows, cols]

        # SPEC 5.11 rule 24, the spatial sense of "block".
        corner_lat = np.floor(self.sq_lat / BLOCK_DEG) * BLOCK_DEG
        corner_lon = np.floor(self.sq_lon / BLOCK_DEG) * BLOCK_DEG
        corners = sorted({(float(a), float(b))
                          for a, b in zip(corner_lat, corner_lon)})
        self.blocks = corners
        where = {corner: i for i, corner in enumerate(corners)}
        self.sq_block = np.array(
            [where[(float(a), float(b))]
             for a, b in zip(corner_lat, corner_lon)], dtype=np.int64)
        self.n_block = len(corners)

        # The calendar month of the day being forecast (5.3), not of the run.
        self.months = sorted({int(imerg_date_for(date, lead)[4:6])
                              for date in self.dates for lead in self.leads})
        self.month_index = {m: i for i, m in enumerate(self.months)}

        self.n_thr = len(self.thresholds)
        self.n_lead = len(self.leads)
        self.n_region = len(self.regions)
        self.n_date = len(self.dates)
        self.n_group = self.n_region * self.n_lead * self.n_thr
        self.n_cell = self.n_lead * self.n_thr

        # The group each square's case belongs to, per lead and threshold,
        # and the 2-degree block index in the same shape.
        self.group_of = np.empty((self.n_lead, self.n_thr, self.n_sq),
                                 dtype=np.int64)
        self.block_of = np.empty((self.n_lead, self.n_thr, self.n_sq),
                                 dtype=np.int64)
        for li in range(self.n_lead):
            for ti in range(self.n_thr):
                self.group_of[li, ti] = ((self.sq_region * self.n_lead + li)
                                         * self.n_thr + ti)
                self.block_of[li, ti] = (self.sq_block * self.n_cell
                                         + li * self.n_thr + ti)

    def group_name(self, g: int) -> dict:
        ti = g % self.n_thr
        li = (g // self.n_thr) % self.n_lead
        ri = g // (self.n_thr * self.n_lead)
        return {"region": self.regions[ri], "lead_day": self.leads[li],
                "threshold_mm": self.thresholds[ti]}


# ----------------------------------------------------- pass 1, the reference

def reference(setup: Setup, obs_cache: dict) -> dict:
    """How often the event happened, per square x month x lead x threshold.

    SPEC 5.3. In-sample and unsmoothed: the case being scored is inside its
    own group (5.11 rule 9), and there is no minimum group size (rule 10).
    """
    shape = (setup.n_sq, len(setup.months), setup.n_lead, setup.n_thr)
    cases = np.zeros(shape, dtype=np.int64)
    events = np.zeros(shape, dtype=np.int64)
    missing_imerg = 0
    incomplete = 0

    for date in setup.dates:
        for li, lead in enumerate(setup.leads):
            wanted = imerg_date_for(date, lead)
            if wanted not in setup.available:
                missing_imerg += setup.n_sq * setup.n_thr
                continue
            obs = obs_cache[wanted]
            usable = np.isfinite(obs)
            incomplete += int((~usable).sum()) * setup.n_thr
            mi = setup.month_index[int(wanted[4:6])]
            for ti, threshold in enumerate(setup.thresholds):
                cases[:, mi, li, ti] += usable
                events[:, mi, li, ti] += usable & (obs >= threshold)

    rate = np.where(cases > 0, events / np.maximum(cases, 1), np.nan)
    sizes = cases[cases > 0]
    return {
        "cases": cases,
        "events": events,
        "rate": rate,
        "groups": int((cases > 0).sum()),
        "smallest": int(sizes.min()) if sizes.size else 0,
        "largest": int(sizes.max()) if sizes.size else 0,
        "median": float(np.median(sizes)) if sizes.size else 0.0,
        "never_or_always": int(((cases > 0) & ((events == 0)
                                               | (events == cases))).sum()),
        "excluded": {"no_imerg_date": missing_imerg,
                     "observation_incomplete": incomplete},
    }


# ------------------------------------------------------- pass 2, the scoring

class Accumulator:
    """One variant's running totals.

    A variant is a member set and a subset of squares: all 51 members
    everywhere, the 50 perturbed members everywhere (SPEC 2.1), and all 51
    with the coastal squares left out (5.11 rule 6).
    """

    def __init__(self, setup: Setup, name: str, members: int,
                 squares: np.ndarray, note: str):
        self.name = name
        self.note = note
        self.members = members
        self.squares = squares
        self.buckets = bucket_table(members)
        self.bucket_of = bucket_index(members)
        n_group, n_date = setup.n_group, setup.n_date
        self.row_n = np.zeros((n_group, n_date), dtype=np.int64)
        self.row_bs = np.zeros((n_group, n_date), dtype=np.float64)
        self.row_ref = np.zeros((n_group, n_date), dtype=np.float64)
        self.row_ev = np.zeros((n_group, n_date), dtype=np.int64)
        self.buck_n = np.zeros((n_group, N_BUCKETS), dtype=np.int64)
        self.buck_f = np.zeros((n_group, N_BUCKETS), dtype=np.float64)
        self.buck_o = np.zeros((n_group, N_BUCKETS), dtype=np.float64)
        self.buck_dates = np.zeros((n_group, N_BUCKETS, n_date), dtype=bool)
        self.bin_n = np.zeros((n_group, members + 1), dtype=np.int64)
        self.bin_o = np.zeros((n_group, members + 1), dtype=np.int64)
        self.flat_ref = np.zeros(n_group, dtype=np.int64)
        self.blk_n = np.zeros(setup.n_block * setup.n_cell, dtype=np.int64)
        self.blk_bs = np.zeros(setup.n_block * setup.n_cell, dtype=np.float64)
        self.blk_ref = np.zeros(setup.n_block * setup.n_cell,
                                dtype=np.float64)

    def take(self, setup: Setup, di: int, li: int, ti: int, k: np.ndarray,
             observed: np.ndarray, ref: np.ndarray,
             usable: np.ndarray) -> None:
        keep = usable & self.squares
        if not keep.any():
            return
        groups = setup.group_of[li, ti][keep]
        forecast = k[keep] / self.members
        truth = observed[keep].astype(np.float64)
        here = ref[keep]
        size = setup.n_group

        bs = (forecast - truth) ** 2
        rbs = (here - truth) ** 2
        self.row_n[:, di] += np.bincount(groups, minlength=size)
        self.row_bs[:, di] += np.bincount(groups, weights=bs, minlength=size)
        self.row_ref[:, di] += np.bincount(groups, weights=rbs,
                                           minlength=size)
        self.row_ev[:, di] += np.bincount(groups, weights=truth,
                                          minlength=size).astype(np.int64)
        self.flat_ref += np.bincount(
            groups, minlength=size,
            weights=((here <= 0.0) | (here >= 1.0)).astype(np.float64),
        ).astype(np.int64)

        spot = groups * N_BUCKETS + self.bucket_of[k[keep]]
        wide = size * N_BUCKETS
        counts = np.bincount(spot, minlength=wide).reshape(size, N_BUCKETS)
        self.buck_n += counts
        self.buck_f += np.bincount(spot, weights=forecast,
                                   minlength=wide).reshape(size, N_BUCKETS)
        self.buck_o += np.bincount(spot, weights=truth,
                                   minlength=wide).reshape(size, N_BUCKETS)
        self.buck_dates[:, :, di] |= counts > 0

        # SPEC 5.11 rule 23: the decomposition's bins are the exact k values.
        bins = groups * (self.members + 1) + k[keep]
        wide = size * (self.members + 1)
        self.bin_n += np.bincount(bins, minlength=wide).reshape(
            size, self.members + 1)
        self.bin_o += np.bincount(bins, weights=truth, minlength=wide
                                  ).reshape(size, self.members + 1
                                            ).astype(np.int64)

        blocks = setup.block_of[li, ti][keep]
        wide = setup.n_block * setup.n_cell
        self.blk_n += np.bincount(blocks, minlength=wide)
        self.blk_bs += np.bincount(blocks, weights=bs, minlength=wide)
        self.blk_ref += np.bincount(blocks, weights=rbs, minlength=wide)


def count_at(totals: np.ndarray, thresholds, axis: int = 1) -> np.ndarray:
    """Members reaching each threshold, the counting rule of SPEC 4.2.

    `totals` is (day, member, square). The answer is
    (threshold, day, square). Greater than or equal to, with no epsilon.
    """
    return np.stack([np.count_nonzero(totals >= t, axis=axis)
                     for t in thresholds])


def score(setup: Setup, ref: dict, obs_cache: dict,
          variants: list[Accumulator], report=print,
          load=load_forecast) -> dict:
    """Pass 2. Every case scored against its own reference group.

    `load` is how a date's stored accumulations are read. It is a parameter
    only so that a test can drive the whole pass with a few squares and a
    hand-computed answer instead of the real archive.
    """
    excluded = {"no_imerg_date": 0, "observation_incomplete": 0}
    used = 0
    started = time.time()

    for di, date in enumerate(setup.dates):
        totals = daily_totals(load(date))
        if not np.isfinite(totals).all():
            raise SystemExit(f"{date}: the stored forecast is not all finite")
        square_totals = totals[:, :, setup.india]        # (day, member, sq)
        counts = {}
        for variant in variants:
            if variant.members in counts:
                continue
            # 51 keeps every member; 50 drops index 0, the control (SPEC 2.1).
            part = square_totals[:, square_totals.shape[1] - variant.members:]
            counts[variant.members] = count_at(
                part, setup.thresholds).astype(np.int64)

        for li, lead in enumerate(setup.leads):
            wanted = imerg_date_for(date, lead)
            if wanted not in setup.available:
                excluded["no_imerg_date"] += setup.n_sq * setup.n_thr
                continue
            obs = obs_cache[wanted]
            usable = np.isfinite(obs)
            excluded["observation_incomplete"] += (int((~usable).sum())
                                                   * setup.n_thr)
            used += int(usable.sum()) * setup.n_thr
            mi = setup.month_index[int(wanted[4:6])]
            for ti, threshold in enumerate(setup.thresholds):
                here = ref["rate"][:, mi, li, ti]
                if not np.isfinite(here[usable]).all():
                    raise SystemExit(
                        f"{date} lead {lead}: a case has no reference group")
                observed = usable & (obs >= threshold)
                for variant in variants:
                    variant.take(setup, di, li, ti,
                                 counts[variant.members][ti, lead - 1],
                                 observed, here, usable)
        if (di + 1) % 25 == 0 or di + 1 == setup.n_date:
            report(f"    {di + 1}/{setup.n_date} dates, "
                   f"{time.time() - started:.0f}s")

    possible = setup.n_date * setup.n_lead * setup.n_sq * setup.n_thr
    tally = {"possible": possible, "used": used, "excluded": excluded,
             "excluded_total": sum(excluded.values())}
    if used + tally["excluded_total"] != possible:
        raise SystemExit(
            f"{used} used and {tally['excluded_total']} excluded do not make "
            f"{possible} possible")
    return tally


# -------------------------------------------------------------- the maths

def decomposition(bin_n: np.ndarray, bin_o: np.ndarray,
                  members: int) -> dict | None:
    """Murphy's decomposition on the exact `k/members` bins (SPEC 5.7).

    REL - RES + UNC = BS, and it has to hold to the last bit a float can
    carry, or the run stops.
    """
    total = int(bin_n.sum())
    if total == 0:
        return None
    forecast = np.arange(members + 1, dtype=np.float64) / members
    seen = np.where(bin_n > 0, bin_o / np.maximum(bin_n, 1), 0.0)
    base = bin_o.sum() / total
    rel = float((bin_n * (forecast - seen) ** 2).sum() / total)
    res = float((bin_n * (seen - base) ** 2).sum() / total)
    unc = float(base * (1.0 - base))
    brier = float((bin_n * forecast ** 2 - 2 * bin_o * forecast
                   + bin_o).sum() / total)
    residual = rel - res + unc - brier
    if abs(residual) > DECOMPOSITION_TOLERANCE:
        raise SystemExit(f"the decomposition does not add up: {residual:.3e}")
    return {"reliability": rel, "resolution": res, "uncertainty": unc,
            "brier": brier, "base_rate": float(base),
            "residual": float(residual)}


def draws(n_date: int, resamples: int = RESAMPLES,
          seed: int = SEED) -> np.ndarray:
    """The one set of date draws of SPEC 5.11 rule 13.

    Every group and every sensitivity is resampled with these same draws, so
    their ranges can be compared. Returned as counts per date, which turns a
    resample into one matrix multiply.
    """
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, n_date, size=(resamples, n_date))
    out = np.zeros((resamples, n_date), dtype=np.int64)
    for r in range(resamples):
        out[r] = np.bincount(picks[r], minlength=n_date)
    return out


def bootstrap(row_bs: np.ndarray, row_ref: np.ndarray,
              counts: np.ndarray) -> list[dict]:
    """The 95% range for the skill of each group."""
    bs_draws = row_bs @ counts.T                      # (group, resample)
    ref_draws = row_ref @ counts.T
    resamples = counts.shape[0]
    out = []
    for g in range(row_bs.shape[0]):
        good = ref_draws[g] > 0
        kept = int(good.sum())
        if kept == 0:
            out.append({"bss_lo": None, "bss_hi": None,
                        "discarded": resamples})
            continue
        values = 1.0 - bs_draws[g][good] / ref_draws[g][good]
        lo, hi = np.percentile(values, [LOW_PERCENTILE, HIGH_PERCENTILE],
                               method=PERCENTILE_METHOD)
        out.append({"bss_lo": float(lo), "bss_hi": float(hi),
                    "discarded": resamples - kept})
    return out


def bss_of(bs_sum: float, ref_sum: float) -> float | None:
    """Skill, or nothing at all when the reference was never wrong."""
    if ref_sum <= 0:
        return None
    return float(1.0 - bs_sum / ref_sum)


def date_blocks(dates: list[str], size: int = DATE_BLOCK) -> list[dict]:
    """Consecutive runs of `size` start dates (SPEC 5.11 rule 24)."""
    out = []
    for start in range(0, len(dates), size):
        part = dates[start:start + size]
        out.append({"from": part[0], "to": part[-1], "dates": len(part),
                    "short": len(part) < size,
                    "index": list(range(start, start + len(part)))})
    return out


# ------------------------------------------------------------- the writing

def round_floats(value, places: int = PLACES):
    """Round every float on the way out, so two runs give the same bytes."""
    if isinstance(value, float):
        return round(value, places)
    if isinstance(value, dict):
        return {k: round_floats(v, places) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, places) for v in value]
    return value


def bucket_rows(variant: Accumulator, g: int) -> list[dict]:
    rows = []
    for b, band in enumerate(variant.buckets):
        cases = int(variant.buck_n[g, b])
        dates = int(variant.buck_dates[g, b].sum())
        row = {"bucket": band["name"], "k_from": band["k_from"],
               "k_to": band["k_to"], "cases": cases, "dates": dates,
               "counted": cases >= BUCKET_MIN_CASES
                          and dates >= BUCKET_MIN_DATES}
        if cases:
            mean_forecast = float(variant.buck_f[g, b] / cases)
            observed = float(variant.buck_o[g, b] / cases)
            row.update({"mean_forecast": mean_forecast,
                        "observed": observed,
                        "error": abs(observed - mean_forecast)})
        rows.append(row)
    return rows


def group_rows(setup: Setup, variant: Accumulator,
               ranges: list[dict]) -> list[dict]:
    rows = []
    for g in range(setup.n_group):
        n = int(variant.row_n[g].sum())
        if n == 0:
            continue
        bs_sum = float(variant.row_bs[g].sum())
        ref_sum = float(variant.row_ref[g].sum())
        span = ranges[g]
        lo, hi = span["bss_lo"], span["bss_hi"]
        rows.append({
            "variant": variant.name,
            **setup.group_name(g),
            "cases": n,
            "dates": int((variant.row_n[g] > 0).sum()),
            "event_dates": int((variant.row_ev[g] > 0).sum()),
            "events": int(variant.row_ev[g].sum()),
            "base_rate": float(variant.row_ev[g].sum() / n),
            "bs": bs_sum / n,
            "reference_bs": ref_sum / n,
            "bss": bss_of(bs_sum, ref_sum),
            "bss_lo": lo,
            "bss_hi": hi,
            "bss_halfwidth": None if lo is None else float((hi - lo) / 2),
            "resamples_discarded": span["discarded"],
            "cases_with_flat_reference": int(variant.flat_ref[g]),
            "decomposition": decomposition(variant.bin_n[g],
                                           variant.bin_o[g], variant.members),
            "buckets": bucket_rows(variant, g),
        })
    return rows


def by_date_block(setup: Setup, variant: Accumulator,
                  blocks: list[dict]) -> list[dict]:
    """Skill by contiguous blocks of start dates, to show whether it is
    steady or driven by one period (SPEC 5.7)."""
    out = []
    for g in range(setup.n_group):
        name = setup.group_name(g)
        if name["threshold_mm"] not in PUBLISHED_MM:
            continue
        for block in blocks:
            idx = block["index"]
            n = int(variant.row_n[g, idx].sum())
            if n == 0:
                continue
            out.append({
                "variant": variant.name, **name,
                "from": block["from"], "to": block["to"],
                "short": block["short"], "cases": n,
                "bss": bss_of(float(variant.row_bs[g, idx].sum()),
                              float(variant.row_ref[g, idx].sum())),
            })
    return out


def by_two_degrees(setup: Setup, variant: Accumulator,
                   ref: dict) -> list[dict]:
    """Base rate and skill by 2-degree block (SPEC 5.6 and 5.11 rule 24)."""
    cases = ref["cases"].sum(axis=1)              # (square, lead, threshold)
    events = ref["events"].sum(axis=1)
    out = []
    for bi, (block_lat, block_lon) in enumerate(setup.blocks):
        here = setup.sq_block == bi
        squares = int(here.sum())
        for li, lead in enumerate(setup.leads):
            for ti, threshold in enumerate(setup.thresholds):
                if threshold not in PUBLISHED_MM:
                    continue
                n = int(cases[here, li, ti].sum())
                if n == 0:
                    continue
                spot = bi * setup.n_cell + li * setup.n_thr + ti
                out.append({
                    "lat": float(block_lat), "lon": float(block_lon),
                    "squares": squares,
                    "enough_squares": squares >= BLOCK_MIN_SQUARES,
                    "lead_day": lead, "threshold_mm": threshold,
                    "cases": int(variant.blk_n[spot]),
                    "base_rate": float(events[here, li, ti].sum() / n),
                    "bss": bss_of(float(variant.blk_bs[spot]),
                                  float(variant.blk_ref[spot])),
                })
    return out


def build(setup: Setup, obs_cache: dict, report=print,
          load=load_forecast) -> dict:
    report("  pass 1: the reference, from the observations alone")
    ref = reference(setup, obs_cache)
    report(f"    {ref['groups']} reference groups, smallest {ref['smallest']}"
           f", median {ref['median']:.0f}, largest {ref['largest']}")

    inland = ~setup.sq_coastal
    everywhere = np.ones(setup.n_sq, dtype=bool)
    variants = [
        Accumulator(setup, "all51", 51, everywhere,
                    "all 51 members, every India square"),
        Accumulator(setup, "all50", 50, everywhere,
                    "the 50 perturbed members only (SPEC 2.1)"),
        Accumulator(setup, "inland51", 51, inland,
                    "all 51 members, coastal squares left out "
                    "(SPEC 5.11 rule 6)"),
    ]

    report("  pass 2: scoring")
    tally = score(setup, ref, obs_cache, variants, report=report,
                  load=load)

    counts = draws(setup.n_date)
    blocks = date_blocks(setup.dates)
    groups, block_rows = [], []
    for variant in variants:
        ranges = bootstrap(variant.row_bs, variant.row_ref, counts)
        groups.extend(group_rows(setup, variant, ranges))
        block_rows.extend(by_date_block(setup, variant, blocks))

    return {
        "spec_section": "5",
        "period": PERIOD,
        "note_small_reference_groups": SMALL_GROUPS_NOTE,
        "wording": "agreed with the satellite estimate, never correct "
                   "(SPEC 5.9)",
        "crps_compared": False,
        "crps_note": "CRPS and the CORP diagnostic (SPEC 5.7, Tier 2) have "
                     "not been computed yet. Nothing on the site may mention "
                     "them until they are.",
        "regions": setup.regions,
        "leads": list(setup.leads),
        "thresholds_mm": list(setup.thresholds),
        "published_thresholds_mm": list(PUBLISHED_MM),
        "variants": [{"name": v.name, "members": v.members,
                      "squares": int(v.squares.sum()), "note": v.note}
                     for v in variants],
        "buckets": {str(v.members): v.buckets for v in variants},
        "bucket_floor": {"cases": BUCKET_MIN_CASES, "dates": BUCKET_MIN_DATES},
        "bootstrap": {"resamples": RESAMPLES, "seed": SEED,
                      "unit": "whole start dates, with replacement",
                      "percentile_method": PERCENTILE_METHOD,
                      "percentiles": [LOW_PERCENTILE, HIGH_PERCENTILE],
                      "reference": "fixed, computed once from the full "
                                   "sample (SPEC 5.5)",
                      "discard_limit": DISCARD_LIMIT},
        "reference": {
            "key": "square x calendar month of the forecast day x lead day "
                   "x threshold",
            "in_sample": True,
            "groups": ref["groups"],
            "smallest": ref["smallest"],
            "median": ref["median"],
            "largest": ref["largest"],
            "never_or_always": ref["never_or_always"],
        },
        "dates": {"runs": setup.n_date, "first": setup.dates[0],
                  "last": setup.dates[-1], "missing_or_failed": gaps(
                      setup.dates)},
        "date_blocks": [{"from": b["from"], "to": b["to"],
                         "dates": b["dates"], "short": b["short"]}
                        for b in blocks],
        "squares": {"india": setup.n_sq,
                    "coastal": int(setup.sq_coastal.sum()),
                    "inland": int(inland.sum())},
        "cases": tally,
        "groups_scored": groups,
        "skill_by_date_block": block_rows,
        "two_degree": by_two_degrees(setup, variants[0], ref),
    }


# ------------------------------------------------------------------- meta

def spec_sha256() -> str:
    """The hash of SPEC.md as committed: LF, not the working copy's CRLF."""
    raw = (cfg.ROOT / "SPEC.md").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cfg.ROOT,
                              capture_output=True, text=True, check=True)
        return done.stdout.strip()
    except Exception:                                   # noqa: BLE001
        return "unknown"


def meta_record(setup: Setup, result: dict) -> dict:
    regions = json.loads(REGIONS_FILE.read_text(encoding="utf-8"))
    return {
        "spec_section": "6.8, with the additions of 5.11 rule 29",
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(
            microsecond=0).isoformat(),
        "spec_sha256": spec_sha256(),
        "spec_sha256_note": "over SPEC.md with CRLF normalised to LF, which "
                            "are the committed bytes",
        "git_commit": git_commit(),
        "pile_a": {"first": setup.dates[0], "last": setup.dates[-1],
                   "dates": setup.n_date,
                   "missing_or_failed": gaps(setup.dates)},
        "imerg": {"product": "GPM_3IMERGDL",
                  "version": cfg.IMERG_REQUIRED_FILE_VERSION,
                  "doi": cfg.IMERG_REQUIRED_DOI,
                  "first": min(setup.available),
                  "last": max(setup.available),
                  "dates": len(setup.available)},
        "inputs": {
            "india_mask_sha256": file_sha256(MASK_FILE),
            "regions_sha256": file_sha256(REGIONS_FILE),
            "admin1_sha256": regions["source"]["sha256"],
        },
        "bootstrap": result["bootstrap"],
        "cases": result["cases"],
        "period": PERIOD,
    }


# ------------------------------------------------------------------- entry

def read_observations(mask: dict, available) -> dict:
    """Every observation date, cut to the India squares.

    SPEC 5.11 rule 3: the 90% rule of 3.4 is checked again here, against the
    completeness fraction stored beside the rain, rather than trusted.
    """
    out = {}
    for date in sorted(available):
        rain, fraction = load_obs(date)
        usable = fraction >= (cfg.IMERG_MIN_COMPLETE_FRACTION
                              - cfg.IMERG_FRACTION_EPSILON)
        if not np.array_equal(np.isfinite(rain), usable):
            raise SystemExit(
                f"{date}: rain is missing somewhere other than where "
                "complete_fraction is below 0.90")
        out[date] = rain[mask["india"]]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", help="comma-separated run dates")
    parser.add_argument("--no-write", action="store_true",
                        help="compute and report, write nothing")
    args = parser.parse_args()

    mask = load_mask()
    regions = load_regions()
    available = obs_dates()
    dates = run_dates()
    if args.dates:
        wanted = [d.strip() for d in args.dates.split(",") if d.strip()]
        unknown = [d for d in wanted if d not in dates]
        if unknown:
            raise SystemExit(f"not usable Pile A dates: {unknown}")
        dates = wanted
    if not dates:
        raise SystemExit("no usable Pile A dates")

    print(f"  {len(dates)} run dates, {dates[0]} to {dates[-1]}")
    print(f"  {len(available)} observation dates")

    setup = Setup(mask, regions, dates, available)
    obs_cache = read_observations(mask, available)
    result = build(setup, obs_cache)

    if args.no_write:
        print("  --no-write: nothing written")
        return
    RESULTS.mkdir(exist_ok=True)
    text = json.dumps(round_floats(result), indent=1) + "\n"
    OUT.write_bytes(text.encode())
    meta_text = json.dumps(round_floats(meta_record(setup, result)),
                           indent=1) + "\n"
    META.write_bytes(meta_text.encode())
    print(f"  wrote {OUT.name}, {len(text.encode()) / 1e6:.2f} MB")
    print(f"  wrote {META.name}, {len(meta_text.encode())} bytes")


if __name__ == "__main__":
    main()
