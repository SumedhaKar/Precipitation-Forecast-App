"""Turn the scores into the three trust labels, and nothing more.

SPEC 6, with the decisions of 6.9. Reads `results/verification.json` and
writes `results/labels.json`: one row for every region x lead day x threshold,
all sixty of them, each carrying the label, the outcome of all four conditions
of 6.2 and the numbers behind them.

    python -m pipeline.labels
    python -m pipeline.labels --no-write

A group is never missing. A group with nothing to say reads "Not enough past
data", which is a statement about our record and not an absence (6.9 rule 1).

The Brier score decides (6.1). CRPS has not been computed, so `crps_compared`
is false and nothing here mentions it (6.9 rule 2).
"""
from __future__ import annotations

import argparse
import json

from .verify import OUT as VERIFICATION
from .verify import PERIOD, PUBLISHED_MM, RESULTS

LABELS_FILE = RESULTS / "labels.json"
SITE_FILE = RESULTS / "site_summary.json"

GOOD = "Good track record"
ROUGH = "Treat as a rough guide"
THIN = "Not enough past data"

# SPEC 6.3.
MIN_CASES = 1000
MIN_DATES = 30
MIN_EVENT_DATES = 20

# SPEC 6.2 conditions 3 and 4, and 5.11 rule 15.
MAX_HALFWIDTH = 0.10
MAX_BUCKET_ERROR = 0.10
MAX_DISCARDED = 0.01

# SPEC 6.5. Fixed wording; not to be made more confident.
LUCK = ("slightly better than the usual rain for this place and month, but "
        "the difference could be luck")

# SPEC 6.1 and 6.9 rule 3. The label still follows Brier.
CRPS_DISAGREES = (
    "the two scores point different ways here: one of them beats its "
    "baseline and the other does not. The label follows the Brier score, "
    "and this is said rather than hidden")

SITE_FILE_LIMIT = 100_000

COLOURS = {GOOD: "green", ROUGH: "amber", THIN: "grey"}


def enough_data(group: dict) -> dict:
    """SPEC 6.3. All three, and the third is the one that binds."""
    return {
        "cases": {"value": group["cases"], "need": MIN_CASES,
                  "pass": group["cases"] >= MIN_CASES},
        "dates": {"value": group["dates"], "need": MIN_DATES,
                  "pass": group["dates"] >= MIN_DATES},
        "event_dates": {"value": group["event_dates"],
                        "need": MIN_EVENT_DATES,
                        "pass": group["event_dates"] >= MIN_EVENT_DATES},
    }


def honesty(group: dict) -> dict:
    """SPEC 6.4, with 5.11 rule 20.

    Every counted bucket within 0.10 of its own mean forecast -- and a group
    with no counted bucket at all fails, because a rule that is true of no
    evidence has not been tested.
    """
    counted = [b for b in group["buckets"] if b["counted"]]
    worst = max((b["error"] for b in counted), default=None)
    return {
        "counted_buckets": len(counted),
        "drawn_buckets": sum(1 for b in group["buckets"] if b["cases"]),
        "worst_error": worst,
        "allowed": MAX_BUCKET_ERROR,
        "pass": bool(counted) and worst <= MAX_BUCKET_ERROR,
    }


def skill_known(group: dict, resamples: int) -> bool:
    """Whether this group has a skill number worth labelling at all.

    SPEC 5.11 rules 8 and 15: no reference to divide by, or too many
    resamples with none, and there is no range to read.
    """
    if group["bss"] is None or group["bss_lo"] is None:
        return False
    return group["resamples_discarded"] <= MAX_DISCARDED * resamples


def phrases(group: dict) -> list[dict]:
    """SPEC 6.7's "came true about N times in 10", per counted bucket.

    Only counted buckets get the phrase: the floor that governs what we test
    in 6.4 also governs what we are willing to say out loud.
    """
    out = []
    for bucket in group["buckets"]:
        if not bucket["counted"]:
            continue
        out.append({
            "k_from": bucket["k_from"], "k_to": bucket["k_to"],
            "cases": bucket["cases"], "dates": bucket["dates"],
            "observed": bucket["observed"],
            "times_in_10": int(round(bucket["observed"] * 10)),
        })
    return out


def label_for(group: dict, resamples: int) -> dict:
    data = enough_data(group)
    data_ok = all(part["pass"] for part in data.values())
    known = skill_known(group, resamples)
    lo, half = group["bss_lo"], group["bss_halfwidth"]
    above = {"value": lo, "pass": bool(known and lo > 0)}
    narrow = {"value": half, "allowed": MAX_HALFWIDTH,
              "pass": bool(known and half <= MAX_HALFWIDTH)}
    error = honesty(group)

    if not data_ok or not known:
        label = THIN
    elif above["pass"] and narrow["pass"] and error["pass"]:
        label = GOOD
    else:
        label = ROUGH

    row = {
        "region": group["region"], "lead_day": group["lead_day"],
        "threshold_mm": group["threshold_mm"], "variant": group["variant"],
        "label": label, "colour": COLOURS[label],
        "conditions": {
            "1_enough_data": {"pass": data_ok, **data},
            "2_skill_above_zero": above,
            "3_range_narrow_enough": narrow,
            "4_small_honesty_error": error,
        },
        "skill_known": known,
        "bss": group["bss"], "bss_lo": group["bss_lo"],
        "bss_hi": group["bss_hi"], "bss_halfwidth": half,
        "resamples_discarded": group["resamples_discarded"],
        "bs": group["bs"], "reference_bs": group["reference_bs"],
        "base_rate": group["base_rate"], "cases": group["cases"],
        "dates": group["dates"], "event_dates": group["event_dates"],
        "shows": shows_for(label),
        "phrases": phrases(group),
        "period": PERIOD,
    }
    if label == ROUGH and known and lo is not None and lo <= 0 <= group[
            "bss_hi"]:
        row["wording"] = LUCK
    return row


def shows_for(label: str) -> dict:
    """SPEC 6.7. What the page is allowed to print for this label."""
    if label == GOOD:
        return {"percentage_rounded_to_10": True, "count_of_51": True,
                "came_true_phrase": False}
    if label == ROUGH:
        return {"percentage_rounded_to_10": False, "count_of_51": True,
                "came_true_phrase": True}
    return {"percentage_rounded_to_10": False, "count_of_51": True,
            "came_true_phrase": False}


def key(row: dict) -> tuple:
    return (row["region"], row["lead_day"], row["threshold_mm"])


def crps_beside(result: dict) -> dict:
    """CRPS by region and lead day, and where it points the other way.

    SPEC 6.1 and 6.9 rule 3. The label follows Brier whatever this says;
    what changes is that the disagreement is printed beside it instead of
    being quietly dropped.
    """
    if not result.get("crps_compared"):
        return {}
    skill = {(row["region"], row["lead_day"]): row
             for row in result["crps"]["rows"] if row["variant"] == "all51"}
    flags = {(row["region"], row["lead_day"], row["threshold_mm"]): row
             for row in result["crps"]["disagreement"]}
    out = {}
    for spot, row in flags.items():
        here = skill[(spot[0], spot[1])]
        out[spot] = {
            "crpss_fair": here["crpss_fair"],
            "crpss_lo": here["crpss_lo"], "crpss_hi": here["crpss_hi"],
            "brier_above_zero": row["brier_above_zero"],
            "crps_above_zero": row["crps_above_zero"],
            "disagrees": row["disagrees"],
            "note": (CRPS_DISAGREES if row["disagrees"] else None),
        }
    return out


def build(result: dict) -> dict:
    resamples = result["bootstrap"]["resamples"]
    scored = result["groups_scored"]
    rows = {}
    for group in scored:
        rows[(group["variant"], *key(group))] = label_for(group, resamples)

    headline = []
    for region in result["regions"]:
        for lead in result["leads"]:
            for threshold in PUBLISHED_MM:
                spot = ("all51", region, lead, threshold)
                row = rows.get(spot)
                if row is None:
                    row = {"region": region, "lead_day": lead,
                           "threshold_mm": threshold, "variant": "all51",
                           "label": THIN, "colour": COLOURS[THIN],
                           "conditions": None, "skill_known": False,
                           "note": "no case of this group was scored",
                           "shows": shows_for(THIN), "phrases": [],
                           "period": PERIOD}
                headline.append(row)

    # SPEC 5.6 and 5.11 rules 6, 21 and 22: a label that does not survive a
    # small change in the threshold, the member set or the coastline is a
    # label with something to disclose beside it.
    changes = []
    for row in headline:
        region, lead, threshold = key(row)
        others = {}
        if threshold == 10.0:
            for other in (8.0, 12.0):
                spot = ("all51", region, lead, other)
                if spot in rows:
                    others[f"{other:g} mm"] = rows[spot]["label"]
        for variant, name in (("all50", "50 members"),
                              ("inland51", "inland only")):
            spot = (variant, region, lead, threshold)
            if spot in rows:
                others[name] = rows[spot]["label"]
        row["also"] = others
        differs = {k: v for k, v in others.items() if v != row["label"]}
        if differs:
            row["disclose"] = differs
            changes.append({"region": region, "lead_day": lead,
                            "threshold_mm": threshold,
                            "label": row["label"], "differs": differs})

    expected = (len(result["regions"]) * len(result["leads"])
                * len(PUBLISHED_MM))
    if len(headline) != expected:
        raise SystemExit(f"{len(headline)} labels, not {expected}")

    # Beside the label, never deciding it: the frequency check and CRPS.
    frequency = {(r["region"], r["lead_day"], r["threshold_mm"]): r
                 for r in result["frequency_check"]["rows"]
                 if r["variant"] == "all51"}
    crps = crps_beside(result)
    for row in headline:
        spot = key(row)
        said = frequency.get(spot)
        row["frequency_check"] = None if said is None else {
            "mean_forecast": said["mean_forecast"],
            "observed": said["observed"], "ratio": said["ratio"],
            "wording": said["wording"]}
        row["crps"] = crps.get(spot)

    counts = {}
    for row in headline:
        counts[row["label"]] = counts.get(row["label"], 0) + 1

    return {
        "spec_section": "6",
        "period": PERIOD,
        "wording": result["wording"],
        "crps_compared": result["crps_compared"],
        "luck_wording": LUCK,
        "rules": {"min_cases": MIN_CASES, "min_dates": MIN_DATES,
                  "min_event_dates": MIN_EVENT_DATES,
                  "max_halfwidth": MAX_HALFWIDTH,
                  "max_bucket_error": MAX_BUCKET_ERROR,
                  "bucket_floor": result["bucket_floor"]},
        "regions": result["regions"],
        "leads": result["leads"],
        "thresholds_mm": list(PUBLISHED_MM),
        "counts": counts,
        "labels": headline,
        "sensitivity_changes": changes,
        "all_variants": [rows[spot] for spot in sorted(rows)],
    }


def site_summary(result: dict, record: dict) -> dict:
    """The one file the website reads. Small enough to send every time.

    Everything a page needs to show a label honestly and nothing else: the
    label, why it is that label with the numbers behind it, the skill and
    its range, the counted buckets the "came true about N times in 10"
    phrase comes from, the frequency check, and the period. The big files
    stay in the repository for anyone who wants to check the working.
    """
    groups = []
    for row in record["labels"]:
        conditions = row["conditions"] or {}
        data = conditions.get("1_enough_data", {})
        error = conditions.get("4_small_honesty_error", {})
        skill = conditions.get("2_skill_above_zero") or {}
        narrow = conditions.get("3_range_narrow_enough") or {}
        crps = row.get("crps") or {}
        groups.append({
            "region": row["region"], "lead_day": row["lead_day"],
            "threshold_mm": row["threshold_mm"],
            "label": row["label"], "colour": row["colour"],
            "conditions": {
                "enough_data": {
                    "pass": data.get("pass", False),
                    "cases": data.get("cases", {}).get("value"),
                    "dates": data.get("dates", {}).get("value"),
                    "event_dates": data.get("event_dates", {}).get("value")},
                "skill_above_zero": {"pass": skill.get("pass", False),
                                     "value": skill.get("value")},
                "range_narrow_enough": {"pass": narrow.get("pass", False),
                                        "value": narrow.get("value")},
                "small_honesty_error": {
                    "pass": error.get("pass", False),
                    "counted_buckets": error.get("counted_buckets"),
                    "worst_error": error.get("worst_error")},
            },
            "bss": row.get("bss"), "bss_lo": row.get("bss_lo"),
            "bss_hi": row.get("bss_hi"),
            "base_rate": row.get("base_rate"),
            "buckets": [{"k_from": b["k_from"], "k_to": b["k_to"],
                         "cases": b["cases"], "observed": b["observed"],
                         "times_in_10": b["times_in_10"]}
                        for b in row["phrases"]],
            "frequency_check": row.get("frequency_check"),
            "crps_disagrees": bool(crps.get("disagrees")),
            "luck": row.get("wording") == LUCK,
            "disclose": row.get("disclose"),
        })
    india = [{"lead_day": r["lead_day"], "threshold_mm": r["threshold_mm"],
              "cases": r["cases"], "mean_forecast": r["mean_forecast"],
              "observed": r["observed"], "ratio": r["ratio"],
              "wording": r["wording"]}
             for r in result["frequency_check"]["rows"]
             if r["variant"] == "all51" and r["region"] == "All India"
             and r["threshold_mm"] in PUBLISHED_MM]
    crps = [{"region": row["region"], "lead_day": row["lead_day"],
             "crpss_fair": row["crpss_fair"], "crpss_lo": row["crpss_lo"],
             "crpss_hi": row["crpss_hi"]}
            for row in result["crps"]["rows"]
            if row["variant"] == "all51"] if result["crps_compared"] else []
    return {
        "spec_section": "6",
        "period": record["period"],
        # The sentence belongs to every label; it is stored once because
        # this file is sent to a browser, and the page puts it on each.
        "period_on_every_label": True,
        "wording": record["wording"],
        "luck_wording": LUCK,
        "crps_compared": result["crps_compared"],
        "crps_disagrees_wording": CRPS_DISAGREES,
        "crps_baseline": result["crps"]["baseline"],
        "crps": crps,
        "not_computed": sorted(result["not_computed"]),
        "rules": record["rules"],
        "shows_by_label": {name: shows_for(name)
                           for name in (GOOD, ROUGH, THIN)},
        "regions": record["regions"], "leads": record["leads"],
        "thresholds_mm": record["thresholds_mm"],
        "counts": record["counts"],
        "frequency_check": {
            "wording": result["frequency_check"]["wording"],
            "ratio": result["frequency_check"]["ratio"],
            "all_india": india},
        "groups": groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    if not VERIFICATION.exists():
        raise SystemExit(f"{VERIFICATION} does not exist; run verify first")
    result = json.loads(VERIFICATION.read_text(encoding="utf-8"))
    record = build(result)
    for label, count in sorted(record["counts"].items()):
        print(f"  {label:<24} {count:>3} of {len(record['labels'])}")
    if record["sensitivity_changes"]:
        print(f"  {len(record['sensitivity_changes'])} labels have a "
              "sensitivity to disclose")
    site = site_summary(result, record)
    site_text = json.dumps(site, separators=(",", ":")) + "\n"
    size = len(site_text.encode())
    if size > SITE_FILE_LIMIT:
        raise SystemExit(
            f"{SITE_FILE.name} is {size} bytes, over the {SITE_FILE_LIMIT} "
            "the site is allowed")
    if args.no_write:
        print("  --no-write: nothing written")
        return
    text = json.dumps(record, indent=1) + "\n"
    LABELS_FILE.write_bytes(text.encode())
    print(f"  wrote {LABELS_FILE.name}, {len(text.encode()) / 1e6:.2f} MB")
    SITE_FILE.write_bytes(site_text.encode())
    print(f"  wrote {SITE_FILE.name}, {size} bytes of the "
          f"{SITE_FILE_LIMIT} allowed")


if __name__ == "__main__":
    main()
