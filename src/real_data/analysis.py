"""
Aggregation layer for the Real-World Validation module.

Every function here takes a dataframe already processed by
metrics.derive_metrics() and returns a small, JSON-serializable, fully
aggregated dict or list of dicts -- no row-level order_id/rider_id ever
appears in a return value from this module. analyze_data() is the single
entry point precompute_real_data_insights.py calls; everything else is
called by it internally (kept as separate functions for isolated testing).

Statistical stance (see docs/REAL_DATA_VALIDATION.md "Causality"): every
comparison here is a plain aggregate contrast (median/P75/P90, rate
differences). Nothing here runs a hypothesis test or claims a causal
effect -- captions in the dashboard page use "associated with", never
"caused by", and this module doesn't compute p-values for that reason
(avoiding exactly the "run dozens of tests, cherry-pick the favorable one"
pattern the task explicitly warns against).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERCENTILES = (0.50, 0.75, 0.90)


def _pctiles(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) == 0:
        return {"median": None, "p75": None, "p90": None, "n": 0}
    q = s.quantile(PERCENTILES)
    return {"median": round(float(q[0.50]), 2), "p75": round(float(q[0.75]), 2), "p90": round(float(q[0.90]), 2), "n": int(len(s))}


def _histogram(s: pd.Series, bins: int = 12, clip_p99: bool = True) -> list[dict]:
    s = s.dropna()
    if len(s) == 0:
        return []
    if clip_p99:
        hi = s.quantile(0.99)
        s = s[s <= hi]
    if s.nunique() < 2:
        return []
    counts, edges = np.histogram(s, bins=bins)
    return [
        {"bin_start": round(float(edges[i]), 2), "bin_end": round(float(edges[i + 1]), 2), "count": int(counts[i])}
        for i in range(len(counts))
    ]


def dataset_overview(df: pd.DataFrame) -> dict:
    n = len(df)
    return {
        "row_count": n,
        "unique_orders": int(df["order_id"].nunique()) if "order_id" in df.columns else None,
        "unique_riders": int(df["rider_id"].nunique()) if "rider_id" in df.columns else None,
        "date_min": str(pd.to_datetime(df["order_date"]).min().date()) if "order_date" in df.columns else None,
        "date_max": str(pd.to_datetime(df["order_date"]).max().date()) if "order_date" in df.columns else None,
        "completion_rate": round(float(df["delivery_success"].mean()), 4),
        "cancellation_rate": round(float(df["cancellation_flag"].mean()), 4),
        "undelivered_rate": round(float(df["undelivered_flag"].mean()), 4),
        "reassignment_rate": round(float(df["reassignment_flag"].mean()), 4),
        "median_end_to_end_min": round(float(df["end_to_end_time_min"].median()), 2),
        "median_first_mile_km": round(float(df["first_mile_distance"].median()), 3) if "first_mile_distance" in df.columns else None,
        "median_last_mile_km": round(float(df["last_mile_distance"].median()), 3) if "last_mile_distance" in df.columns else None,
    }


def operational_funnel(df: pd.DataFrame) -> list[dict]:
    """order -> allot -> accept -> pickup -> deliver, with count, conversion
    from both the previous stage and from order, and median/P90 time to
    reach that stage from order creation."""
    n_order = len(df)
    stages = [
        ("Order placed", df["order_time"].notna(), None),
        ("Allotted", df["allot_time"].notna(), "allotment_delay_min"),
        ("Accepted", df["accept_time"].notna(), None),  # cumulative allot+accept below
        ("Picked up", df["pickup_time"].notna(), None),
        ("Delivered", df["delivered_time"].notna(), None),
    ]
    # cumulative time-from-order to reach each stage
    time_from_order = {
        "Order placed": pd.Series(0.0, index=df.index),
        "Allotted": df["allotment_delay_min"],
        "Accepted": df["allotment_delay_min"] + df["acceptance_delay_min"],
        "Picked up": df["order_to_pickup_time_min"],
        "Delivered": df["end_to_end_time_min"],
    }
    out = []
    prev_count = None
    for name, reached_mask, _ in stages:
        count = int(reached_mask.sum())
        t = time_from_order[name].where(df["timing_valid"] | (name == "Order placed"))
        pct = _pctiles(t)
        out.append(
            {
                "stage": name,
                "count": count,
                "conversion_from_order_pct": round(count / n_order * 100, 2) if n_order else 0.0,
                "conversion_from_previous_pct": round(count / prev_count * 100, 2) if prev_count else 100.0,
                "median_min_from_order": pct["median"],
                "p90_min_from_order": pct["p90"],
            }
        )
        prev_count = count
    return out


def delay_diagnostics(df: pd.DataFrame) -> dict:
    """Per-stage delay distributions, restricted to rows flagged
    timing_valid by derive_metrics() -- see that function's docstring for
    exactly what's excluded and why. The excluded count is reported
    separately (dataset_overview + data_quality), never silently."""
    valid = df[df["timing_valid"]]
    stages = {
        "Order -> Allotment": "allotment_delay_min",
        "Allotment -> Acceptance": "acceptance_delay_min",
        "Acceptance -> Pickup": "pickup_delay_min",
        "Pickup -> Delivery": "last_mile_delivery_time_min",
        "Order -> Delivery (end-to-end)": "end_to_end_time_min",
    }
    out = {}
    for label, col in stages.items():
        out[label] = {**_pctiles(valid[col]), "histogram": _histogram(valid[col])}
    return out


def reassignment_analysis(df: pd.DataFrame) -> dict:
    reasons = (
        df["reassignment_reason"].dropna().value_counts().head(5).to_dict()
        if "reassignment_reason" in df.columns
        else {}
    )
    methods = df["reassignment_method"].dropna().value_counts().to_dict() if "reassignment_method" in df.columns else {}

    def _segment(mask: pd.Series) -> dict:
        sub = df[mask]
        valid = sub[sub["timing_valid"]]
        return {
            "n_orders": int(len(sub)),
            "cancellation_rate": round(float(sub["cancellation_flag"].mean()), 4) if len(sub) else None,
            "undelivered_rate": round(float(sub["undelivered_flag"].mean()), 4) if len(sub) else None,
            "acceptance_delay_median_min": round(float(valid["acceptance_delay_min"].median()), 2) if len(valid) else None,
            "pickup_delay_median_min": round(float(valid["pickup_delay_min"].median()), 2) if len(valid) else None,
            "last_mile_median_min": round(float(valid["last_mile_delivery_time_min"].median()), 2) if len(valid) else None,
            "end_to_end_p90_min": round(float(valid["end_to_end_time_min"].quantile(0.90)), 2) if len(valid) else None,
        }

    reassigned_mask = df["reassignment_flag"] == 1
    return {
        "reassignment_rate": round(float(reassigned_mask.mean()), 4),
        "top_reasons": {str(k): int(v) for k, v in reasons.items()},
        "methods": {str(k): int(v) for k, v in methods.items()},
        "reassigned": _segment(reassigned_mask),
        "not_reassigned": _segment(~reassigned_mask),
    }


def _bucket_by_quantile(s: pd.Series, n_buckets: int = 4, unit: str = "km") -> pd.Categorical:
    """Returns an ORDERED categorical (low -> high) so callers can sort by
    category order instead of re-parsing numeric ranges out of the label
    string (which breaks on a negative lower edge, e.g. qcut's first bin
    left-extended slightly below the true minimum)."""
    try:
        cats = pd.qcut(s, n_buckets, duplicates="drop")
    except ValueError:
        return pd.Categorical([pd.NA] * len(s))
    labels = [f"{max(iv.left, 0):.2f}-{iv.right:.2f} {unit}" for iv in cats.cat.categories]
    return cats.cat.rename_categories(labels)


def distance_analysis(df: pd.DataFrame) -> dict:
    out = {}
    for col, label in [("first_mile_distance", "first_mile_distance_buckets"), ("last_mile_distance", "last_mile_distance_buckets")]:
        if col not in df.columns:
            continue
        bucket_col = f"_{col}_bucket"
        work = df.copy()
        work[bucket_col] = _bucket_by_quantile(work[col])
        rows = []
        # groupby on the ordered categorical preserves low->high bucket
        # order directly -- no need to re-parse the label string.
        for bucket in work[bucket_col].cat.categories:
            sub = work[work[bucket_col] == bucket]
            if sub.empty:
                continue
            valid = sub[sub["timing_valid"]]
            rows.append(
                {
                    "bucket": str(bucket),
                    "n_orders": int(len(sub)),
                    "acceptance_delay_median_min": round(float(valid["acceptance_delay_min"].median()), 2) if len(valid) else None,
                    "pickup_delay_median_min": round(float(valid["pickup_delay_min"].median()), 2) if len(valid) else None,
                    "end_to_end_median_min": round(float(valid["end_to_end_time_min"].median()), 2) if len(valid) else None,
                    "cancellation_rate": round(float(sub["cancellation_flag"].mean()), 4),
                }
            )
        out[label] = rows
    return out


def rider_segmentation(df: pd.DataFrame) -> list[dict]:
    """Anonymized rider-experience segments from lifetime_order_count,
    tertiled across RIDERS (not order rows, so a handful of very active
    riders don't dominate the segment boundaries), then order-level
    outcomes are aggregated within each segment. No rider_id is returned."""
    if "lifetime_order_count" not in df.columns or "rider_id" not in df.columns:
        return []
    rider_tenure = df.groupby("rider_id")["lifetime_order_count"].median().dropna()
    if len(rider_tenure) < 3:
        return []
    try:
        tenure_bucket = pd.qcut(rider_tenure, 3, labels=["Low experience", "Medium experience", "High experience"], duplicates="drop")
    except ValueError:
        return []
    rider_segment_map = tenure_bucket.to_dict()
    work = df.copy()
    work["_segment"] = work["rider_id"].map(rider_segment_map)

    out = []
    for seg, sub in work.groupby("_segment", observed=True):
        valid = sub[sub["timing_valid"]]
        out.append(
            {
                "segment": str(seg),
                "n_riders": int(sub["rider_id"].nunique()),
                "n_orders": int(len(sub)),
                "acceptance_delay_median_min": round(float(valid["acceptance_delay_min"].median()), 2) if len(valid) else None,
                "pickup_delay_median_min": round(float(valid["pickup_delay_min"].median()), 2) if len(valid) else None,
                "end_to_end_median_min": round(float(valid["end_to_end_time_min"].median()), 2) if len(valid) else None,
                "reassignment_rate": round(float(sub["reassignment_flag"].mean()), 4),
                "cancellation_rate": round(float(sub["cancellation_flag"].mean()), 4),
            }
        )
    return out


def time_of_day_analysis(df: pd.DataFrame) -> list[dict]:
    work = df.copy()
    work["_hour"] = pd.to_datetime(work["order_time"]).dt.hour
    out = []
    for hour, sub in work.groupby("_hour"):
        valid = sub[sub["timing_valid"]]
        out.append(
            {
                "hour": int(hour),
                "n_orders": int(len(sub)),
                "acceptance_delay_median_min": round(float(valid["acceptance_delay_min"].median()), 2) if len(valid) else None,
                "end_to_end_median_min": round(float(valid["end_to_end_time_min"].median()), 2) if len(valid) else None,
                "cancellation_rate": round(float(sub["cancellation_flag"].mean()), 4),
                "reassignment_rate": round(float(sub["reassignment_flag"].mean()), 4),
            }
        )
    out.sort(key=lambda r: r["hour"])
    return out


def generate_opportunities(overview: dict, reassignment: dict, distance: dict, segments: list[dict], time_of_day: list[dict]) -> list[dict]:
    """Rule-based candidate-opportunity generation. Every number quoted in
    an observation is read from the already-computed aggregates passed in
    -- nothing here is a hardcoded percentage. Each record is explicitly a
    hypothesis, never a claim (see module docstring)."""
    ops: list[dict] = []

    # 1. Reassignment
    r_rate = reassignment["reassignment_rate"] * 100
    reassigned = reassignment["reassigned"]
    not_reassigned = reassignment["not_reassigned"]
    if reassigned.get("end_to_end_p90_min") and not_reassigned.get("end_to_end_p90_min"):
        delta_pct = (reassigned["end_to_end_p90_min"] - not_reassigned["end_to_end_p90_min"]) / not_reassigned["end_to_end_p90_min"] * 100
        ops.append(
            {
                "problem": "Reassignment friction",
                "observation": (
                    f"{r_rate:.1f}% of orders were reassigned. Reassigned orders had a P90 end-to-end "
                    f"time of {reassigned['end_to_end_p90_min']:.1f} min vs. {not_reassigned['end_to_end_p90_min']:.1f} min for "
                    f"non-reassigned orders ({delta_pct:+.0f}%), and a cancellation rate of "
                    f"{(reassigned['cancellation_rate'] or 0) * 100:.1f}% vs. {(not_reassigned['cancellation_rate'] or 0) * 100:.1f}%."
                ),
                "hypothesis": "Improving initial candidate assignment (better ranking, acceptance-probability-aware selection) could reduce the reassignment rate and the delay it is associated with.",
                "metric_to_optimize": "Order -> Delivery P90 time; reassignment rate",
                "risks_guardrails": "A stricter initial-assignment policy could reduce driver/partner choice or increase decline rate if pushed too far -- watch acceptance rate and partner earnings.",
                "candidate_methods": ["Better candidate ranking", "Acceptance-probability modeling", "Assignment confidence scoring", "Backup rider pre-selection"],
                "simulator_test": "Existing simulator can test assignment-quality effects via ETA_OPTIMIZED vs. NEAREST_DRIVER (dispatch policy comparison) as a partial proxy -- reassignment itself is not currently modeled in the simulator.",
                "priority_score": abs(delta_pct) * (r_rate / 100),
            }
        )

    # 2. Distance-aware dispatch (first-mile). Uses end_to_end + cancellation
    # rate, not acceptance delay -- acceptance delay showed no meaningful
    # (or even a slightly reversed) relationship with distance in this
    # dataset, while pickup delay / end-to-end time / cancellation all
    # increase monotonically across distance buckets. Only fires if the
    # direction is the expected one (longer distance -> more friction) and
    # the magnitude clears a minimum bar -- otherwise it would be forcing
    # a finding the acceptance-delay number doesn't support.
    fm_buckets = distance.get("first_mile_distance_buckets", [])
    valid_fm = [b for b in fm_buckets if b.get("end_to_end_median_min") is not None]
    if len(valid_fm) >= 2:
        lo, hi = valid_fm[0], valid_fm[-1]
        e2e_delta = hi["end_to_end_median_min"] - lo["end_to_end_median_min"]
        cancel_delta_pp = (hi["cancellation_rate"] - lo["cancellation_rate"]) * 100
        if e2e_delta >= 1.0 and hi["cancellation_rate"] > lo["cancellation_rate"]:
            ops.append(
                {
                    "problem": "First-mile distance friction",
                    "observation": (
                        f"Orders in the longest first-mile-distance bucket ({hi['bucket']}) showed a median end-to-end "
                        f"time of {hi['end_to_end_median_min']:.1f} min vs. {lo['end_to_end_median_min']:.1f} min in the "
                        f"shortest bucket ({lo['bucket']}), a difference of {e2e_delta:+.1f} min, and a cancellation rate "
                        f"of {hi['cancellation_rate'] * 100:.2f}% vs. {lo['cancellation_rate'] * 100:.2f}% "
                        f"({cancel_delta_pp:+.2f} pp). (Acceptance delay itself showed no meaningful relationship with distance.)"
                    ),
                    "hypothesis": "Distance-aware dispatch (weighting candidate proximity more heavily, or capping maximum assignment distance) may reduce end-to-end time and cancellation for long first-mile orders.",
                    "metric_to_optimize": "End-to-end time and cancellation rate for long-distance orders",
                    "risks_guardrails": "Over-weighting proximity could reduce match rate in low-density zones or increase load imbalance across partners -- watch completion rate and partner utilization.",
                    "candidate_methods": ["Distance-aware dispatch", "ETA prediction", "Zone-aware allocation"],
                    "simulator_test": "Existing simulator's ETA_OPTIMIZED and NEAREST_DRIVER dispatch policies both incorporate distance; compare P90 wait and avg pickup distance across scenarios as a proxy for this hypothesis.",
                    "priority_score": abs(e2e_delta) + abs(cancel_delta_pp),
                }
            )

    # 3. Experience-aware allocation
    if len(segments) >= 2:
        low = next((s for s in segments if "Low" in s["segment"]), None)
        high = next((s for s in segments if "High" in s["segment"]), None)
        if low and high and low.get("end_to_end_median_min") and high.get("end_to_end_median_min"):
            delta = low["end_to_end_median_min"] - high["end_to_end_median_min"]
            if abs(delta) >= 1.0:  # only surface if the effect is at least ~1 minute -- avoid forcing a finding
                ops.append(
                    {
                        "problem": "Experience-linked outcome gap",
                        "observation": (
                            f"Low-experience riders had a median end-to-end time of {low['end_to_end_median_min']:.1f} min "
                            f"vs. {high['end_to_end_median_min']:.1f} min for high-experience riders ({delta:+.1f} min), and a "
                            f"reassignment rate of {low['reassignment_rate'] * 100:.1f}% vs. {high['reassignment_rate'] * 100:.1f}%."
                        ),
                        "hypothesis": "Experience-aware allocation (e.g. routing simpler/shorter orders to newer riders, or pairing new riders with more forgiving zones) may reduce the outcome gap.",
                        "metric_to_optimize": "End-to-end time and reassignment rate for the low-experience segment",
                        "risks_guardrails": "Segmenting by experience could reduce new-rider order volume/earnings if applied too aggressively -- watch new-rider retention and earnings.",
                        "candidate_methods": ["Experience-aware allocation", "Onboarding-zone restriction", "Graduated order complexity"],
                        "simulator_test": "Candidate future policy -- not currently simulated (the simulator has no driver-experience dimension).",
                        "priority_score": abs(delta),
                    }
                )
            else:
                ops.append(
                    {
                        "problem": "Experience-linked outcome gap",
                        "observation": (
                            f"Low-experience riders had a median end-to-end time of {low['end_to_end_median_min']:.1f} min "
                            f"vs. {high['end_to_end_median_min']:.1f} min for high-experience riders -- a difference of "
                            f"only {delta:+.1f} min. Rider experience shows little relationship with delivery outcomes in this data."
                        ),
                        "hypothesis": "No experience-targeted intervention is well-supported by this dataset; not recommended as a near-term priority.",
                        "metric_to_optimize": "N/A",
                        "risks_guardrails": "N/A",
                        "candidate_methods": [],
                        "simulator_test": "Not recommended for simulator testing based on this data.",
                        "priority_score": 0.0,
                    }
                )

    # 4. Time-of-day pressure. Restricted to hours with a reasonable sample
    # size (>=500 orders in this ~12-day window) before ranking by
    # cancellation rate -- an unfiltered ranking is dominated by single-
    # digit-order overnight hours where one cancellation swings the rate by
    # double digits, which is noise, not a real operational-pressure signal.
    MIN_HOUR_SAMPLE = 500
    reliable_hours = [r for r in time_of_day if r["n_orders"] >= MIN_HOUR_SAMPLE]
    if reliable_hours:
        by_cancel = sorted(reliable_hours, key=lambda r: r["cancellation_rate"], reverse=True)
        worst = by_cancel[0]
        med_cancel = float(np.median([r["cancellation_rate"] for r in reliable_hours]))
        if worst["cancellation_rate"] > med_cancel * 1.3:
            ops.append(
                {
                    "problem": "Time-of-day operational pressure",
                    "observation": (
                        f"Hour {worst['hour']:02d}:00 showed a cancellation rate of {worst['cancellation_rate'] * 100:.1f}% "
                        f"vs. a median of {med_cancel * 100:.1f}% across all hours, with {worst['n_orders']} orders in that hour."
                    ),
                    "hypothesis": "This hour shows high operational pressure; demand-aware incentives or dispatch prioritization during this window may reduce cancellations.",
                    "metric_to_optimize": "Cancellation rate during high-pressure hours",
                    "risks_guardrails": "Blanket incentives could raise cost without addressing the underlying assignment friction -- watch cost per delivered order alongside cancellation rate.",
                    "candidate_methods": ["Demand-aware incentives", "Dispatch prioritization", "ETA-based ranking", "Targeted surge/incentive experiments"],
                    "simulator_test": "Existing simulator's PEAK_DEMAND / SUPPLY_SHORTAGE scenarios and pricing policies (AGGRESSIVE_SURGE etc.) can be used to test demand-throttling hypotheses for this kind of high-pressure window.",
                    "priority_score": (worst["cancellation_rate"] - med_cancel) * 100,
                }
            )

    ops.sort(key=lambda o: o.get("priority_score", 0), reverse=True)
    return ops


def analyze_data(df: pd.DataFrame) -> dict:
    """Single entry point: df must already have derive_metrics() applied.
    Returns one JSON-serializable dict -- the exact structure written to
    results/real_data_insights.json."""
    overview = dataset_overview(df)
    funnel = operational_funnel(df)
    delays = delay_diagnostics(df)
    reassignment = reassignment_analysis(df)
    distance = distance_analysis(df)
    segments = rider_segmentation(df)
    time_of_day = time_of_day_analysis(df)
    opportunities = generate_opportunities(overview, reassignment, distance, segments, time_of_day)

    return {
        "overview": overview,
        "funnel": funnel,
        "delay_diagnostics": delays,
        "reassignment": reassignment,
        "distance": distance,
        "rider_segments": segments,
        "time_of_day": time_of_day,
        "opportunities": opportunities,
    }
