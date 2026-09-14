"""
Human-readable labels and one-line explanations for the raw metric keys
produced by src/metrics.py, src/decision.py, and src/analysis.py.

The underlying dataframes/dicts keep their technical column names
everywhere (results/*.csv, the Advanced Analysis tables, downloadable
data) -- this module only supplies display strings for the primary/
secondary UI, so a user never has to parse `p90_wait_min` or
`driver_utilization_mean` to understand a card or a chart.
"""
from __future__ import annotations

METRIC_LABEL: dict[str, str] = {
    "p90_wait_min": "P90 rider wait",
    "avg_wait_min": "Average rider wait",
    "median_wait_min": "Median rider wait",
    "completion_rate": "Completion rate",
    "cancellation_rate": "Cancellation rate",
    "rider_conversion_rate": "Rider conversion rate",
    "platform_revenue": "Platform revenue",
    "gbv": "Gross bookings value",
    "revenue_per_ride": "Revenue per ride",
    "earnings_per_online_hour_mean": "Driver earnings / online-hour",
    "earnings_per_active_hour": "Driver earnings / active-hour",
    "driver_utilization_mean": "Driver utilization",
    "driver_acceptance_rate": "Driver acceptance rate",
    "north_star_trips_per_online_hour": "Trips / driver-hour (North Star)",
    "avg_pickup_distance_km": "Average pickup distance",
    "price_index": "Price index",
    "avg_surge_multiplier": "Average surge multiplier",
    "n_rejected_offer": "Rejected offers",
    "unmatched_requests": "Unmatched requests",
    "n_completed": "Completed trips",
    "n_requests": "Total requests",
    "demand_per_min": "Demand (requests/min)",
    "avg_available_drivers": "Available drivers",
    "supply_demand_ratio": "Supply / demand ratio",
    "signed_relative_effect_pct": "Change vs. current",
    "relative_effect_pct": "Change vs. current",
    "bootstrap_ci_95_lo": "95% CI (low)",
    "bootstrap_ci_95_hi": "95% CI (high)",
    "wilcoxon_p": "p-value",
    "practically_significant_improvement": "Practically significant",
}

METRIC_HELP: dict[str, str] = {
    "p90_wait_min": "Wait time for the slowest 10% of completed requests -- request to pickup.",
    "avg_wait_min": "Average wait time across all completed requests -- request to pickup.",
    "completion_rate": "Share of requests that ended in a completed trip.",
    "cancellation_rate": "Share of requests that did not result in a completed trip (abandoned or cancelled).",
    "rider_conversion_rate": "Share of priced offers a rider accepted, before matching/cancellation.",
    "platform_revenue": "Platform's commission on completed-trip fares over the simulated period.",
    "earnings_per_online_hour_mean": "Average driver payout per hour spent online (not just per active hour).",
    "driver_utilization_mean": "Share of online driver time spent actively on a trip or heading to one.",
    "driver_acceptance_rate": "Share of ride offers a driver accepted when dispatched one.",
    "north_star_trips_per_online_hour": "Completed rides generated per online driver-hour -- the project's chosen efficiency metric.",
    "avg_pickup_distance_km": "Average distance a driver travels to reach the rider.",
    "price_index": "Average realized price vs. the no-surge base fare (1.0 = no markup).",
    "avg_surge_multiplier": "Average price multiplier applied on top of the base fare.",
    "demand_per_min": "Ride requests originating in this zone per simulated minute.",
    "avg_available_drivers": "Drivers idle and available to accept a ride in this zone.",
    "supply_demand_ratio": "Available drivers per outstanding request -- lower means more undersupplied.",
    "practically_significant_improvement": "Passed BOTH a statistical significance test and a minimum effect-size bar.",
}


def label(metric: str) -> str:
    return METRIC_LABEL.get(metric, metric)


def help_text(metric: str) -> str | None:
    return METRIC_HELP.get(metric)


# ---------------------------------------------------------------------------
# Centralized semantic color logic (Part 12: color = good/bad, not +/-)
# ---------------------------------------------------------------------------
# True = higher is better for this metric. A metric absent here has no
# single "good direction" (e.g. driver_utilization_mean, which is only good
# up to a target range, not monotonically) -- callers should treat it
# neutrally rather than guessing.
METRIC_HIGHER_IS_BETTER: dict[str, bool] = {
    "p90_wait_min": False,
    "avg_wait_min": False,
    "median_wait_min": False,
    "cancellation_rate": False,
    "completion_rate": True,
    "rider_conversion_rate": True,
    "platform_revenue": True,
    "gbv": True,
    "revenue_per_ride": True,
    "earnings_per_online_hour_mean": True,
    "earnings_per_active_hour": True,
    "driver_acceptance_rate": True,
    "north_star_trips_per_online_hour": True,
    "avg_pickup_distance_km": False,
    "price_index": False,
    "avg_surge_multiplier": False,
    "n_rejected_offer": False,
    "unmatched_requests": False,
}


def is_improvement(metric: str, delta: float) -> bool | None:
    """Whether a change of `delta` in `metric` is GOOD (not just positive).
    Returns None for a metric with no single good direction (e.g.
    utilization, which callers should render neutrally) so a caller never
    silently guesses the wrong color."""
    higher_better = METRIC_HIGHER_IS_BETTER.get(metric)
    if higher_better is None or delta == 0:
        return None
    return (delta > 0) == higher_better


# ---------------------------------------------------------------------------
# Centralized semantic color PALETTE -- the single source of hex values for
# every chart/badge/status indicator in the app (src/charts.py,
# src/zone_state.py, dashboard/app.py). Restrained, not neon: one shade per
# semantic meaning, reused everywhere rather than picked ad hoc per
# component. Meaning is fixed, never "increased=green":
#   green  = positive / healthy / improvement / guardrail passed
#   red    = negative / risk / guardrail failed / deterioration
#   amber  = warning / moderate pressure / attention needed
#   blue   = neutral-informational / current selection / baseline
#   grey   = secondary / inactive / no single good direction
# ---------------------------------------------------------------------------
SEMANTIC_COLORS: dict[str, str] = {
    "green": "#27ae60",
    "red": "#c0392b",
    "amber": "#e8a33d",
    "amber_dark": "#d35400",
    "blue": "#3d7ea6",
    "grey": "#8a94a6",
}


def color_for_improvement(metric: str, delta: float) -> str:
    """The one place that turns a metric+delta into a hex color -- callers
    (dashboard cards, charts) should never pick green/red themselves."""
    improved = is_improvement(metric, delta)
    if improved is True:
        return SEMANTIC_COLORS["green"]
    if improved is False:
        return SEMANTIC_COLORS["red"]
    return SEMANTIC_COLORS["grey"]


# ---------------------------------------------------------------------------
# Human-readable number formatting (Part 24) -- one consistent format per
# unit type, used everywhere in the primary/secondary UI. Advanced tables
# keep exact raw values (no formatting applied there).
# ---------------------------------------------------------------------------
def fmt_currency(v: float) -> str:
    """132526.9 -> '₹1.33L'; 6800 -> '₹6.8k'; 320 -> '₹320'."""
    if v != v:
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 100_000:
        return f"{sign}₹{v/100_000:.2f}L"
    if v >= 1_000:
        return f"{sign}₹{v/1_000:.1f}k"
    return f"{sign}₹{v:.0f}"


def fmt_pct(v: float, decimals: int = 1) -> str:
    """0.574 -> '57.4%'. Expects a 0-1 fraction, not an already-scaled value."""
    if v != v:
        return "n/a"
    return f"{v*100:.{decimals}f}%"


def fmt_pp(v: float, decimals: int = 1) -> str:
    """0.04 -> '4.0 pp'. For the CHANGE in a rate metric (e.g. completion
    42% -> 46%), not the rate itself -- 'percentage points' avoids the
    reader confusing an absolute 4-point move with a 4% relative change."""
    if v != v:
        return "n/a"
    return f"{v*100:.{decimals}f} pp"


def fmt_minutes(v: float) -> str:
    """8.52 -> '8.5 min'."""
    if v != v:
        return "n/a"
    return f"{v:.1f} min"


def fmt_km(v: float) -> str:
    """1.30 -> '1.30 km'."""
    if v != v:
        return "n/a"
    return f"{v:.2f} km"


def fmt_multiplier(v: float) -> str:
    """1.3 -> '1.30x'."""
    if v != v:
        return "n/a"
    return f"{v:.2f}x"


# ---------------------------------------------------------------------------
# Dispatch policy-aware flow step (Dispatch page conceptual flow)
# ---------------------------------------------------------------------------
# What each dispatch policy (src/dispatch.py) actually scores candidates on
# -- shown as the "scoring" step of the waiting-riders -> ... -> trip flow,
# so the flow diagram doesn't claim ETA scoring for NEAREST_DRIVER (which
# only ever compares raw distance) or vice versa.
DISPATCH_SCORING_STEP: dict[str, str] = {
    "NEAREST_DRIVER": "Distance scoring",
    "ETA_OPTIMIZED": "ETA scoring (incl. soon-free drivers)",
    "DRIVER_EARNINGS_AWARE": "Earnings-likelihood scoring",
    "MARKETPLACE_AWARE": "ETA + imbalance scoring",
    "ADVANCED_HEURISTIC": "Weighted multi-factor scoring",
}


def dispatch_flow(dispatch_policy: str) -> str:
    scoring = DISPATCH_SCORING_STEP.get(dispatch_policy, "Scoring")
    return f"Waiting riders → Candidate drivers → {scoring} → Assignment → Accept / reject → Trip"


# ---------------------------------------------------------------------------
# Marketplace Map legend caption -- one line per selectable metric, so the
# caption never implies a color meaning that doesn't match what's actually
# plotted (e.g. "blue = health" when the metric is Available Drivers).
# ---------------------------------------------------------------------------
MAP_METRIC_CAPTION: dict[str, str] = {
    "Marketplace status": "Color = marketplace status (green = healthy, red = severe shortage). Size = demand.",
    "Demand (req/min)": "Color and size both reflect demand -- darker/larger = more requests per minute.",
    "Available drivers": "Color = available drivers (darker blue = more drivers). Size = demand.",
    "Supply/demand ratio": "Color = supply/demand ratio (darker green = healthier ratio, red = undersupplied). Size = demand.",
    "P90 wait (min)": "Color = P90 rider wait (darker red = longer wait). Size = demand.",
    "Cancellation rate": "Color = cancellation rate (darker red = higher cancellation). Size = demand.",
    "Surge multiplier": "Color = surge multiplier (darker purple = higher surge). Size = demand.",
}


def map_legend_caption(metric_label: str) -> str:
    return MAP_METRIC_CAPTION.get(metric_label, "Size = demand.")
