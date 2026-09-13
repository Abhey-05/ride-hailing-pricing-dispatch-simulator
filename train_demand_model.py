#!/usr/bin/env python3
"""Builds the 15-minute zone-level demand forecasting dataset, trains
naive/linear/GBM models, and prints the comparison. See src/ml_demand.py
for the full leakage-prevention and methodology discussion."""
from __future__ import annotations

from src.ml_demand import MODEL_PATH, build_dataset, fit_production_model, save_model, train_and_evaluate


def main():
    print("Generating training data from live simulations (10 seeds x 4 scenarios, 15-min buckets)...")
    df = build_dataset()
    print(f"Dataset: {len(df)} (zone, 15-min bucket) rows, mean demand/bucket = {df.demand.mean():.2f}")

    results = train_and_evaluate(df)
    print("\n=== Model comparison (held-out test set, split by simulated day) ===")
    for name in ["naive_last_window", "linear_regression", "gradient_boosting"]:
        r = results[name]
        print(f"{name:20s}  MAE={r['mae']:.3f}  R2={r['r2']:.4f}")

    print(f"\nn_train={results['n_train']} ({results['n_train_days']} days)  "
          f"n_test={results['n_test']} ({results['n_test_days']} days)  "
          f"mean_demand={results['mean_demand']:.2f}")
    print("\n=== Feature importance (gradient boosting) ===")
    for name, imp in results["feature_importance"]:
        print(f"  {name:30s} {imp:.4f}")

    print(f"\nFitting production model on all {len(df)} rows and saving to {MODEL_PATH} ...")
    production_model = fit_production_model(df)
    save_model(production_model)
    print("Done. Use src.ml_demand.forecast_next_window() or the AI copilot's forecast_demand tool for inference.")


if __name__ == "__main__":
    main()
