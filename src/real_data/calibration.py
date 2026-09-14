"""
Read-only comparison of the real-world dataset's aggregates against the
existing simulator's own pre-computed experiment baseline
(results/results.csv). This module NEVER writes to results/results.csv,
never imports src.engine/src.pricing/src.dispatch/src.decision, and never
changes a simulator parameter -- it only reads the simulator's own
published numbers and reports a side-by-side table plus a non-binding
"suggested calibration" note. See module docstring in analysis.py for the
broader "no silent fixes" stance.

IMPORTANT DOMAIN CAVEAT: the simulator models ride-hailing (rider + car);
this dataset is food delivery (customer + delivery partner). The stages
are conceptually analogous (request -> assignment -> pickup -> completion)
but not the same business. Comparisons here are directional signals for
calibration discussion, not a claim that the two are the same system --
the dashboard page repeats this caveat directly above the comparison
table.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# Thresholds for the traffic-light calibration status, defined once here
# (not tuned per-metric) so the rule is auditable rather than picked to
# make a particular row look good.
CLOSE_THRESHOLD_PCT = 15.0
NEEDS_CALIBRATION_THRESHOLD_PCT = 40.0


def _status(relative_diff_pct: float | None) -> str:
    if relative_diff_pct is None:
        return "not_comparable"
    a = abs(relative_diff_pct)
    if a <= CLOSE_THRESHOLD_PCT:
        return "close"
    if a <= NEEDS_CALIBRATION_THRESHOLD_PCT:
        return "needs_calibration"
    return "significant_mismatch"


def load_simulator_baseline(results_csv_path: str | Path) -> dict | None:
    """Mean metrics for the project's own experiment baseline (BASIC_SURGE
    + NEAREST_DRIVER, NORMAL scenario, core experiment group) -- the same
    baseline dashboard/app.py itself compares every live run against.
    Returns None (not an exception) if the file isn't present, so the
    calibration section can degrade to "not available" rather than crash
    the page."""
    path = Path(results_csv_path)
    if not path.exists():
        return None
    df = pd.read_csv(path)
    base = df[
        (df["scenario"] == "NORMAL")
        & (df["pricing_policy"] == "BASIC_SURGE")
        & (df["dispatch_policy"] == "NEAREST_DRIVER")
        & (df["experiment_group"] == "core")
    ]
    if base.empty:
        return None
    m = base[["p90_wait_min", "median_wait_min", "cancellation_rate", "completion_rate", "avg_pickup_distance_km"]].mean()
    return {
        "p90_wait_min": round(float(m["p90_wait_min"]), 2),
        "median_wait_min": round(float(m["median_wait_min"]), 2),
        "cancellation_rate": round(float(m["cancellation_rate"]), 4),
        "completion_rate": round(float(m["completion_rate"]), 4),
        "avg_pickup_distance_km": round(float(m["avg_pickup_distance_km"]), 3),
        "policy_label": "BASIC_SURGE + NEAREST_DRIVER",
        "scenario": "NORMAL",
    }


def compare_to_simulator(real_overview: dict, real_funnel: list[dict], simulator_baseline: dict | None) -> list[dict]:
    """Builds the Metric | Real data | Simulator | Difference | Status
    table. real_funnel is used to pull the order->pickup P90 time (the
    funnel stage closest in meaning to the simulator's rider-wait metric)."""
    if simulator_baseline is None:
        return []

    pickup_stage = next((s for s in real_funnel if s["stage"] == "Picked up"), None)
    real_pickup_p90 = pickup_stage["p90_min_from_order"] if pickup_stage else None

    rows_spec = [
        (
            "Time to pickup (P90)",
            real_pickup_p90,
            simulator_baseline["p90_wait_min"],
            "min",
            "Order -> pickup time (real) vs. rider P90 wait-for-pickup (simulator) -- both measure request-to-physical-pickup.",
        ),
        (
            "Cancellation rate",
            real_overview["cancellation_rate"] * 100,
            simulator_baseline["cancellation_rate"] * 100,
            "%",
            "Share of orders/requests that did not result in a completed delivery/trip.",
        ),
        (
            "Completion rate",
            real_overview["completion_rate"] * 100,
            simulator_baseline["completion_rate"] * 100,
            "%",
            "Share of orders/requests that completed successfully.",
        ),
        (
            "Pickup-leg distance (median/mean)",
            real_overview["median_first_mile_km"],
            simulator_baseline["avg_pickup_distance_km"],
            "km",
            "Real: median first-mile distance. Simulator: mean pickup distance. Not the same statistic, shown together as a rough scale check only.",
        ),
        (
            "Reassignment rate",
            real_overview["reassignment_rate"] * 100,
            None,
            "%",
            "The simulator does not currently model post-acceptance reassignment -- no comparable simulator number exists.",
        ),
    ]

    out = []
    for label, real_val, sim_val, unit, note in rows_spec:
        if real_val is None or sim_val is None:
            diff = None
            rel_diff_pct = None
        else:
            diff = round(real_val - sim_val, 3)
            rel_diff_pct = round((real_val - sim_val) / sim_val * 100, 1) if sim_val else None
        out.append(
            {
                "metric": label,
                "real_value": round(real_val, 3) if real_val is not None else None,
                "simulator_value": round(sim_val, 3) if sim_val is not None else None,
                "unit": unit,
                "difference": diff,
                "relative_diff_pct": rel_diff_pct,
                "status": _status(rel_diff_pct) if sim_val is not None else "not_modeled",
                "note": note,
            }
        )
    return out
