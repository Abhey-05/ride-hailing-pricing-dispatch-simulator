#!/usr/bin/env python3
"""Builds the cancellation-prediction dataset, trains rule-based/LR/GBM
models, and prints the comparison. See src/ml_cancellation.py for the full
leakage-prevention and methodology discussion."""
from __future__ import annotations

import json

from src.ml_cancellation import build_dataset, train_and_evaluate


def main():
    print("Generating training data from live simulations (10 seeds x 3 scenarios)...")
    df = build_dataset()
    print(f"Dataset: {len(df)} rows, cancellation base rate = {df.cancelled.mean():.3f}")

    results = train_and_evaluate(df)
    print("\n=== Model comparison (held-out test set) ===")
    for name in ["rule_based_formula", "logistic_regression", "gradient_boosting"]:
        r = results[name]
        print(f"{name:22s}  AUC={r['auc']:.4f}  log_loss={r['log_loss']:.4f}  brier={r['brier']:.4f}")

    print(f"\nn_train={results['n_train']}  n_test={results['n_test']}  base_rate={results['base_rate']:.3f}")
    print("\n=== Feature importance (gradient boosting) ===")
    for name, imp in results["feature_importance"]:
        print(f"  {name:30s} {imp:.4f}")


if __name__ == "__main__":
    main()
