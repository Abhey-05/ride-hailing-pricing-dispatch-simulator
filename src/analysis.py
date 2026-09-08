"""
Statistical analysis of the core experiment (docs/EXPERIMENT_DESIGN.md Section Q).

For each pricing policy, every candidate dispatch policy is compared against
the NEAREST_DRIVER baseline using the SAME 24 seeds (paired design, enabled
by the common-random-numbers world generation in src/world.py). This module
computes, for every (pricing, dispatch) vs (pricing, NEAREST_DRIVER) pair:

  - mean/median paired difference
  - bootstrap percentile 95% CI (10,000 resamples)
  - paired Wilcoxon signed-rank test (primary) + paired t-test (reported alongside)
  - relative effect size and matched-pairs Cohen's d
  - a practical-significance verdict per the pre-registered bar in
    docs/EXPERIMENT_DESIGN.md Section Q/R (>=5% relative improvement AND CI excludes 0)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from src import config

PRIMARY_METRIC = "p90_wait_min"
SECONDARY_METRICS = ["avg_wait_min", "completion_rate", "cancellation_rate"]
GUARDRAIL_METRICS = ["earnings_per_online_hour_mean", "driver_utilization_mean", "platform_revenue"]
# direction: for each metric, is "lower better" or "higher better"?
LOWER_IS_BETTER = {"p90_wait_min", "avg_wait_min", "cancellation_rate"}

BASELINE_DISPATCH = config.BASELINE_DISPATCH.value
N_BOOTSTRAP = 10_000
RNG = np.random.default_rng(12345)  # analysis-only RNG, not part of the simulation's CRN design


def bootstrap_ci(diffs: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05) -> tuple[float, float]:
    n = len(diffs)
    if n == 0:
        return (float("nan"), float("nan"))
    idx = RNG.integers(0, n, size=(n_boot, n))
    resample_means = diffs[idx].mean(axis=1)
    lo, hi = np.percentile(resample_means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def paired_diff_stats(baseline_vals: np.ndarray, treatment_vals: np.ndarray, metric: str) -> dict:
    diffs = treatment_vals - baseline_vals  # positive = treatment higher
    mean_diff = float(diffs.mean())
    median_diff = float(np.median(diffs))
    baseline_mean = float(baseline_vals.mean())
    relative_effect = mean_diff / baseline_mean if baseline_mean != 0 else float("nan")
    std_diff = float(diffs.std(ddof=1)) if len(diffs) > 1 else 0.0
    cohens_d = mean_diff / std_diff if std_diff > 0 else float("nan")

    ci_lo, ci_hi = bootstrap_ci(diffs)

    try:
        w_stat, w_p = stats.wilcoxon(treatment_vals, baseline_vals)
    except ValueError:
        w_stat, w_p = float("nan"), float("nan")
    t_stat, t_p = stats.ttest_rel(treatment_vals, baseline_vals)

    improving_direction = -1 if metric in LOWER_IS_BETTER else 1
    signed_relative_effect = improving_direction * relative_effect  # positive = improvement
    ci_excludes_zero = (ci_lo > 0 or ci_hi < 0)
    practically_significant = (
        ci_excludes_zero
        and signed_relative_effect >= config.PRACTICAL_SIGNIFICANCE_RELATIVE_THRESHOLD
    )

    return {
        "metric": metric,
        "n_seeds": len(diffs),
        "baseline_mean": baseline_mean,
        "treatment_mean": float(treatment_vals.mean()),
        "mean_diff": mean_diff,
        "median_diff": median_diff,
        "relative_effect_pct": relative_effect * 100,
        "signed_relative_effect_pct": signed_relative_effect * 100,
        "cohens_d": cohens_d,
        "bootstrap_ci_95_lo": ci_lo,
        "bootstrap_ci_95_hi": ci_hi,
        "ci_excludes_zero": ci_excludes_zero,
        "wilcoxon_stat": float(w_stat) if w_stat == w_stat else float("nan"),
        "wilcoxon_p": float(w_p) if w_p == w_p else float("nan"),
        "paired_ttest_stat": float(t_stat),
        "paired_ttest_p": float(t_p),
        "practically_significant_improvement": practically_significant,
    }


def run_core_comparisons(df: pd.DataFrame) -> pd.DataFrame:
    core = df[df.experiment_group == "core"].copy()
    rows = []
    metrics = [PRIMARY_METRIC] + SECONDARY_METRICS + GUARDRAIL_METRICS
    for pricing in core.pricing_policy.unique():
        sub = core[core.pricing_policy == pricing]
        baseline = sub[sub.dispatch_policy == BASELINE_DISPATCH].sort_values("seed")
        for dispatch in sub.dispatch_policy.unique():
            if dispatch == BASELINE_DISPATCH:
                continue
            treatment = sub[sub.dispatch_policy == dispatch].sort_values("seed")
            merged = baseline.merge(treatment, on="seed", suffixes=("_base", "_treat"))
            assert len(merged) == 24, f"expected 24 paired seeds, got {len(merged)}"
            for metric in metrics:
                stat_row = paired_diff_stats(
                    merged[f"{metric}_base"].values, merged[f"{metric}_treat"].values, metric
                )
                stat_row["pricing_policy"] = pricing
                stat_row["dispatch_policy"] = dispatch
                stat_row["role"] = (
                    "primary" if metric == PRIMARY_METRIC
                    else "guardrail" if metric in GUARDRAIL_METRICS
                    else "secondary"
                )
                rows.append(stat_row)
    return pd.DataFrame(rows)


def decision_table(df: pd.DataFrame) -> pd.DataFrame:
    """Product Decision Framework, docs/EXPERIMENT_DESIGN.md Section X:
    maximize North Star subject to guardrail thresholds anchored to the
    NORMAL / BASIC_SURGE / NEAREST_DRIVER baseline."""
    core = df[df.experiment_group == "core"].copy()
    baseline = core[(core.pricing_policy == config.BASELINE_PRICING.value) & (core.dispatch_policy == BASELINE_DISPATCH)]
    b_p90 = baseline["p90_wait_min"].mean()
    b_earn = baseline["earnings_per_online_hour_mean"].mean()
    b_cancel = baseline["cancellation_rate"].mean()
    b_revenue = baseline["platform_revenue"].mean()

    agg = core.groupby(["pricing_policy", "dispatch_policy"]).agg(
        p90_wait_min=("p90_wait_min", "mean"),
        earnings_per_online_hour_mean=("earnings_per_online_hour_mean", "mean"),
        cancellation_rate=("cancellation_rate", "mean"),
        platform_revenue=("platform_revenue", "mean"),
        north_star=("north_star_trips_per_online_hour", "mean"),
        completion_rate=("completion_rate", "mean"),
    ).reset_index()

    tol = config.GUARDRAIL_TOLERANCE
    agg["meets_p90_guardrail"] = agg.p90_wait_min <= b_p90 * tol["p90_wait_max_ratio"]
    agg["meets_earnings_guardrail"] = agg.earnings_per_online_hour_mean >= b_earn * tol["earnings_per_hour_min_ratio"]
    agg["meets_cancellation_guardrail"] = agg.cancellation_rate <= b_cancel * tol["cancellation_rate_max_ratio"]
    agg["meets_revenue_guardrail"] = agg.platform_revenue >= b_revenue * tol["revenue_min_ratio"]
    agg["meets_all_guardrails"] = (
        agg.meets_p90_guardrail & agg.meets_earnings_guardrail
        & agg.meets_cancellation_guardrail & agg.meets_revenue_guardrail
    )
    agg = agg.sort_values("north_star", ascending=False).reset_index(drop=True)
    agg["baseline_p90_wait_min"] = b_p90
    agg["baseline_earnings_per_online_hour_mean"] = b_earn
    agg["baseline_cancellation_rate"] = b_cancel
    agg["baseline_platform_revenue"] = b_revenue
    return agg
