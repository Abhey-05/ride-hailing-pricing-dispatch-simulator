#!/usr/bin/env python3
"""Runs the full statistical analysis over results/results.csv and saves:
    results/core_comparisons.csv   -- every dispatch-vs-baseline paired test
    results/decision_table.csv     -- ranked policy combos vs guardrails
Prints the headline finding for the primary hypothesis.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import analysis

RESULTS_DIR = Path(__file__).parent / "results"


def main():
    df = pd.read_csv(RESULTS_DIR / "results.csv")

    comparisons = analysis.run_core_comparisons(df)
    comparisons.to_csv(RESULTS_DIR / "core_comparisons.csv", index=False)

    decision = analysis.decision_table(df)
    decision.to_csv(RESULTS_DIR / "decision_table.csv", index=False)

    print("=" * 78)
    print("PRIMARY HYPOTHESIS: dispatch policy vs P90 wait, baseline = NEAREST_DRIVER")
    print("=" * 78)
    primary = comparisons[comparisons.role == "primary"].sort_values(
        "signed_relative_effect_pct", ascending=False
    )
    cols = [
        "pricing_policy", "dispatch_policy", "baseline_mean", "treatment_mean",
        "signed_relative_effect_pct", "bootstrap_ci_95_lo", "bootstrap_ci_95_hi",
        "wilcoxon_p", "practically_significant_improvement",
    ]
    with pd.option_context("display.width", 200, "display.max_rows", 50):
        print(primary[cols].round(4).to_string(index=False))

    print()
    print("=" * 78)
    print("DECISION TABLE (ranked by North Star, guardrails vs NORMAL/BASIC_SURGE/NEAREST_DRIVER baseline)")
    print("=" * 78)
    with pd.option_context("display.width", 220, "display.max_rows", 50):
        print(decision.round(4).to_string(index=False))

    winners = primary[primary.practically_significant_improvement]
    print()
    print("=" * 78)
    if len(winners) > 0:
        best = winners.sort_values("signed_relative_effect_pct", ascending=False).iloc[0]
        print(
            f"HEADLINE: {best.dispatch_policy} vs NEAREST_DRIVER under {best.pricing_policy} pricing "
            f"reduces P90 wait by {best.signed_relative_effect_pct:.1f}% "
            f"(95% CI [{-best.bootstrap_ci_95_hi:.2f}, {-best.bootstrap_ci_95_lo:.2f}] min improvement), "
            f"Wilcoxon p={best.wilcoxon_p:.4f}, n=24 paired seeds."
        )
    else:
        print("HEADLINE: no dispatch policy cleared the pre-registered practical-significance bar.")
    print("=" * 78)


if __name__ == "__main__":
    main()
