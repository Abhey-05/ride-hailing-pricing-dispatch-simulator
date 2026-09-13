"""
Decision-intelligence layer on top of the simulation engine, results/*.csv,
and src/analysis.py's statistical machinery: Marketplace Health Score,
guardrail evaluation, live counterfactual simulation, and policy
recommendation.

Same hard rule as src/copilot_tools.py: every number surfaced by this module
comes from either a real simulation run (src.engine) or the pre-computed
experiment matrix (results/results.csv) -- nothing here is a hardcoded or
guessed recommendation. See docs/MATHEMATICAL_MODEL.md-style discipline:
formulas are documented in this module's docstrings, not buried in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import analysis, config, engine, world

# ---------------------------------------------------------------------------
# Shared normalization bands
# ---------------------------------------------------------------------------
# (direction, good_value, bad_value) per metric. "good_value" maps to a
# normalized score of 1.0, "bad_value" to 0.0; values beyond either end are
# clipped, not extrapolated. Bands are the empirical 5th/95th percentiles of
# results/results.csv (1,080 runs spanning all 6 demand/supply scenarios and
# all 20 policy combinations), computed once with:
#
#   python -c "import pandas as pd; d=pd.read_csv('results/results.csv'); \
#              print(d[[<metric columns>]].quantile([.05, .95]))"
#
# Re-run that and update the constants below if the experiment matrix
# (src/config.py SCENARIOS / PRICING_PARAMS / dispatch weights) changes
# materially -- these are a property of the empirical distribution, not
# arbitrary targets. Using percentiles from a matrix that already spans
# every scenario (not just NORMAL) means metrics like platform_revenue,
# which scale with a scenario's demand_mult, are already normalized in a
# scenario-aware way.
NORMALIZATION_BANDS: dict[str, tuple[str, float, float]] = {
    "p90_wait_min": ("lower", 8.0, 15.0),
    "cancellation_rate": ("lower", 0.1538, 0.3016),
    "completion_rate": ("higher", 0.6255, 0.3296),
    "earnings_per_online_hour_mean": ("higher", 207.22, 104.04),
    "driver_acceptance_rate": ("higher", 0.7081, 0.6792),
    "driver_utilization_mean": ("higher", 0.8063, 0.3653),
    "north_star_trips_per_online_hour": ("higher", 2.3879, 1.3033),
    "avg_pickup_distance_km": ("lower", 1.1595, 1.8812),
    "platform_revenue": ("higher", 119_624.55, 61_248.76),
}


def normalize_metric(metric: str, value: float) -> float:
    """Map a raw metric value to [0, 1] using NORMALIZATION_BANDS. Returns
    NaN if the metric is unknown or the value is NaN (e.g. a zero-completed-
    trips edge case), so callers can decide how to handle missing data
    rather than silently treating it as 0."""
    if metric not in NORMALIZATION_BANDS or value != value:
        return float("nan")
    direction, good, bad = NORMALIZATION_BANDS[metric]
    if good == bad:
        return 0.5
    frac = (bad - value) / (bad - good) if direction == "lower" else (value - bad) / (good - bad)
    return float(np.clip(frac, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Marketplace Health Score
# ---------------------------------------------------------------------------
# Four dimensions, each a weighted blend of normalized metrics (weights sum
# to 1.0 within a dimension, and dimension weights sum to 1.0 overall).
# Chosen to mirror the marketplace's actual stakeholders: riders, drivers,
# the marketplace's own matching efficiency, and the business. This is a
# design choice, not a law of nature -- it is intentionally documented here,
# not hidden, so it can be argued with.
HEALTH_SCORE_METRICS: dict[str, list[tuple[str, float]]] = {
    "rider_experience": [
        ("p90_wait_min", 0.40),
        ("cancellation_rate", 0.35),
        ("completion_rate", 0.25),
    ],
    "driver_experience": [
        ("earnings_per_online_hour_mean", 0.45),
        ("driver_acceptance_rate", 0.25),
        ("driver_utilization_mean", 0.30),
    ],
    "marketplace_efficiency": [
        ("north_star_trips_per_online_hour", 0.60),
        ("avg_pickup_distance_km", 0.40),
    ],
    "business_performance": [
        ("platform_revenue", 1.00),
    ],
}

HEALTH_SCORE_DIMENSION_WEIGHTS: dict[str, float] = {
    "rider_experience": 0.30,
    "driver_experience": 0.25,
    "marketplace_efficiency": 0.25,
    "business_performance": 0.20,
}

DIMENSION_LABELS = {
    "rider_experience": "Rider Experience",
    "driver_experience": "Driver Experience",
    "marketplace_efficiency": "Marketplace Efficiency",
    "business_performance": "Business Performance",
}


@dataclass
class HealthScore:
    overall: float
    dimensions: dict[str, float]
    metric_scores: dict[str, float]
    metric_values: dict[str, float]

    def interpretation(self) -> str:
        if self.overall >= 80:
            return "Healthy -- marketplace is operating within its normal, well-balanced range."
        if self.overall >= 60:
            return "Fair -- some dimensions are under strain; worth a closer look."
        if self.overall >= 40:
            return "Degraded -- at least one dimension is meaningfully out of range."
        return "Poor -- multiple dimensions are stressed; an intervention is likely warranted."


def compute_health_score(summary: dict) -> HealthScore:
    dimension_scores: dict[str, float] = {}
    metric_scores: dict[str, float] = {}
    metric_values: dict[str, float] = {}
    for dim, metrics in HEALTH_SCORE_METRICS.items():
        dim_total = 0.0
        for name, weight in metrics:
            value = summary.get(name, float("nan"))
            score01 = normalize_metric(name, value)
            score100 = 0.0 if score01 != score01 else score01 * 100.0
            metric_scores[name] = score100
            metric_values[name] = value
            dim_total += score100 * weight
        dimension_scores[dim] = dim_total
    overall = sum(dimension_scores[d] * w for d, w in HEALTH_SCORE_DIMENSION_WEIGHTS.items())
    return HealthScore(overall=overall, dimensions=dimension_scores, metric_scores=metric_scores, metric_values=metric_values)


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
# Absolute guardrails: fixed operational limits, independent of any
# baseline. Used for the live "guardrail status" widget and for rejecting
# recommendation candidates outright (see recommend_policy below).
GUARDRAIL_ABSOLUTE: dict[str, tuple[str, float, str]] = {
    "cancellation_rate": ("max", 0.30, "Cancellation rate"),
    "driver_utilization_mean": ("max", 0.90, "Driver utilization"),
    "avg_surge_multiplier": ("max", 2.5, "Avg surge multiplier"),
    "earnings_per_online_hour_mean": ("min", 100.0, "Driver earnings / online-hour"),
}


@dataclass
class GuardrailCheck:
    metric: str
    label: str
    value: float
    bound_kind: str
    bound: float
    passed: bool

    @property
    def utilization_pct(self) -> float:
        """How 'full' the guardrail is, as a percent of its limit -- for a
        progress-bar-style display. Not meaningful past 100%."""
        if self.bound == 0:
            return 0.0
        if self.bound_kind == "max":
            return float(np.clip(self.value / self.bound * 100.0, 0.0, 999.0))
        return float(np.clip(self.bound / self.value * 100.0, 0.0, 999.0)) if self.value else 999.0


def avg_surge_multiplier(collector) -> float:
    """Not part of MetricsCollector.compute_summary() (src/metrics.py) --
    derived here from the same RequestRecord data every request already
    carries, so no engine change is required to support this guardrail."""
    surges = [r.surge_multiplier for r in collector.requests]
    return float(np.mean(surges)) if surges else 1.0


def evaluate_guardrails_absolute(summary: dict) -> list[GuardrailCheck]:
    checks = []
    for metric, (kind, bound, label) in GUARDRAIL_ABSOLUTE.items():
        value = summary.get(metric, float("nan"))
        if value != value:
            continue
        passed = (value <= bound) if kind == "max" else (value >= bound)
        checks.append(GuardrailCheck(metric, label, value, kind, bound, passed))
    return checks


def evaluate_guardrails_relative(candidate: dict, baseline: dict, tolerance: dict | None = None) -> dict:
    """Generalizes src/analysis.py's decision_table() guardrail logic
    (guardrails measured relative to a baseline run) to an arbitrary
    candidate/baseline pair, so it can be reused for a live counterfactual
    or an ad hoc recommendation, not just the pre-computed 1,080-run
    decision table."""
    tol = tolerance or config.GUARDRAIL_TOLERANCE
    checks = {
        "p90_wait": candidate["p90_wait_min"] <= baseline["p90_wait_min"] * tol["p90_wait_max_ratio"],
        "earnings": candidate["earnings_per_online_hour_mean"] >= baseline["earnings_per_online_hour_mean"] * tol["earnings_per_hour_min_ratio"],
        "cancellation": candidate["cancellation_rate"] <= baseline["cancellation_rate"] * tol["cancellation_rate_max_ratio"],
        "revenue": candidate["platform_revenue"] >= baseline["platform_revenue"] * tol["revenue_min_ratio"],
    }
    checks["all_pass"] = all(checks.values())
    return checks


# ---------------------------------------------------------------------------
# Policy optimization objective
# ---------------------------------------------------------------------------
DEFAULT_OBJECTIVE_WEIGHTS: dict[str, float] = {
    "completion_rate": 0.35,
    "platform_revenue": 0.25,
    "earnings_per_online_hour_mean": 0.20,
    "p90_wait_min": 0.20,
}


def objective_utility(row: dict | pd.Series, weights: dict[str, float] | None = None) -> float:
    """Weighted marketplace utility (docs PRD-style objective, Overview
    section 14): completion + revenue + driver earnings, minus wait,
    each normalized via NORMALIZATION_BANDS so metrics on very different
    scales (a 0-1 rate vs. a 5-figure revenue number) combine sensibly.
    Returns NaN if any weighted metric is NaN."""
    w = weights or DEFAULT_OBJECTIVE_WEIGHTS
    total = 0.0
    for metric, weight in w.items():
        score = normalize_metric(metric, row[metric])
        if score != score:
            return float("nan")
        total += weight * score
    return total


# ---------------------------------------------------------------------------
# Recommendation from the pre-computed experiment matrix
# ---------------------------------------------------------------------------
UTILITY_IMPROVEMENT_MARGIN = 0.02  # candidate must beat current by >=2 utility points (of 1.0) to be worth recommending


def recommend_policy(
    results_df: pd.DataFrame,
    scenario: str,
    current_pricing: str,
    current_dispatch: str,
    objective_weights: dict[str, float] | None = None,
) -> dict:
    """Recommend the best (pricing, dispatch) combo for `scenario` using the
    pre-computed experiment matrix (results/results.csv covers all 6
    scenarios x 20 combos already -- 24 seeds for NORMAL, 6 for the other 5
    scenarios). This is instant (no live simulation) so it can run on every
    page load; use run_counterfactual() below to get a fresh, live,
    confidence-interval-backed comparison of the specific change this
    recommends before approving it.
    """
    sub = results_df[results_df.scenario == scenario]
    if sub.empty:
        return {"action": "error", "reason": f"No pre-computed results for scenario={scenario}."}

    agg = sub.groupby(["pricing_policy", "dispatch_policy"], as_index=False).mean(numeric_only=True)

    current_row = agg[(agg.pricing_policy == current_pricing) & (agg.dispatch_policy == current_dispatch)]
    if current_row.empty:
        return {"action": "error", "reason": f"No pre-computed row for {current_pricing}/{current_dispatch} in {scenario}."}
    current = current_row.iloc[0].to_dict()
    current["utility"] = objective_utility(current, objective_weights)

    # avg_surge_multiplier isn't in the pre-computed matrix (metrics.py's
    # summary doesn't include it) -- skip that one guardrail for
    # matrix-sourced candidates rather than silently pretending it passed.
    def guardrail_pass(row: dict) -> bool:
        for metric, (kind, bound, _label) in GUARDRAIL_ABSOLUTE.items():
            if metric not in row or row[metric] != row[metric]:
                continue
            if kind == "max" and row[metric] > bound:
                return False
            if kind == "min" and row[metric] < bound:
                return False
        return True

    records = agg.to_dict(orient="records")
    candidates = [r for r in records if not (r["pricing_policy"] == current_pricing and r["dispatch_policy"] == current_dispatch)]
    for r in candidates:
        r["utility"] = objective_utility(r, objective_weights)
        r["guardrail_pass"] = guardrail_pass(r)

    passing = sorted(
        (r for r in candidates if r["guardrail_pass"] and r["utility"] == r["utility"]),
        key=lambda r: r["utility"], reverse=True,
    )
    # "Best overall" (unconstrained) and "best under guardrails" are
    # reported separately and are NOT necessarily the same combo -- e.g. a
    # policy with the single highest utility might do it by pushing surge or
    # cancellation past an operational limit. Surfacing both, rather than
    # only the guardrail-passing one, is the point: it lets a viewer see
    # what was traded away to stay within guardrails.
    all_scored = sorted(
        (r for r in candidates if r["utility"] == r["utility"]), key=lambda r: r["utility"], reverse=True,
    )
    best_overall = all_scored[0] if all_scored else None

    if not passing or passing[0]["utility"] < current["utility"] + UTILITY_IMPROVEMENT_MARGIN:
        return {
            "action": "none",
            "reason": "No candidate policy clears guardrails with a meaningful utility improvement over the current policy.",
            "scenario": scenario,
            "current": current,
            "best_overall": best_overall,
        }

    return {
        "action": "switch",
        "scenario": scenario,
        "current": current,
        "recommended": passing[0],
        "runner_up": passing[1] if len(passing) > 1 else None,
        "best_overall": best_overall,
        "best_overall_is_recommended": (
            best_overall is not None
            and best_overall["pricing_policy"] == passing[0]["pricing_policy"]
            and best_overall["dispatch_policy"] == passing[0]["dispatch_policy"]
        ),
    }


# ---------------------------------------------------------------------------
# Live counterfactual simulation
# ---------------------------------------------------------------------------
COUNTERFACTUAL_SEEDS: tuple[int, ...] = tuple(range(8))
COUNTERFACTUAL_METRICS: tuple[str, ...] = (
    "p90_wait_min", "avg_wait_min", "completion_rate", "cancellation_rate",
    "platform_revenue", "earnings_per_online_hour_mean", "driver_utilization_mean",
    "north_star_trips_per_online_hour",
)


def run_counterfactual(
    scenario_name: str,
    current_pricing: str,
    current_dispatch: str,
    alt_pricing: str,
    alt_dispatch: str,
    seeds: tuple[int, ...] = COUNTERFACTUAL_SEEDS,
) -> dict:
    """Runs BOTH the current and alternative policy across the same seeds
    (common random numbers -- same World object reused for both policies at
    each seed, exactly like src/experiment_runner.py's core matrix), and
    computes a real paired comparison with src.analysis.paired_diff_stats --
    the same statistical machinery behind results/core_comparisons.csv, just
    over fewer seeds because this runs live in response to a UI click
    rather than as an offline batch job. Every number here is a genuine
    simulation output, never an estimate or interpolation.
    """
    current_rows, alt_rows = [], []
    for seed in seeds:
        w = world.generate_world(scenario_name, seed=seed)
        eng_cur = engine.SimulationEngine(
            w, config.PricingPolicy(current_pricing), config.DispatchPolicy(current_dispatch),
            config.SCENARIOS[scenario_name],
        )
        current_rows.append(eng_cur.run().summary)
        eng_alt = engine.SimulationEngine(
            w, config.PricingPolicy(alt_pricing), config.DispatchPolicy(alt_dispatch),
            config.SCENARIOS[scenario_name],
        )
        alt_rows.append(eng_alt.run().summary)

    stats_rows = []
    for m in COUNTERFACTUAL_METRICS:
        base_vals = np.array([r[m] for r in current_rows], dtype=float)
        treat_vals = np.array([r[m] for r in alt_rows], dtype=float)
        stat = analysis.paired_diff_stats(base_vals, treat_vals, m)
        stats_rows.append(stat)
    comparison_df = pd.DataFrame(stats_rows)

    current_mean = {m: float(np.mean([r[m] for r in current_rows])) for m in COUNTERFACTUAL_METRICS}
    alt_mean = {m: float(np.mean([r[m] for r in alt_rows])) for m in COUNTERFACTUAL_METRICS}
    guardrails = evaluate_guardrails_relative(alt_mean, current_mean)

    return {
        "scenario": scenario_name,
        "seeds": list(seeds),
        "n_seeds": len(seeds),
        "current_policy": {"pricing": current_pricing, "dispatch": current_dispatch, "mean": current_mean},
        "alternative_policy": {"pricing": alt_pricing, "dispatch": alt_dispatch, "mean": alt_mean},
        "comparison": comparison_df,
        "guardrails": guardrails,
    }
