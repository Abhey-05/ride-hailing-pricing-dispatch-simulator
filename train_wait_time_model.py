#!/usr/bin/env python3
"""Builds the realized-wait-time prediction dataset, trains naive-distance-ETA
/linear/GBM models, and prints the comparison. See src/ml_wait_time.py for
the full leakage-prevention and framing discussion (why this predicts
realized wait, not the simulator's already-deterministic pickup ETA)."""
from __future__ import annotations

from src.ml_wait_time import MODEL_PATH, build_dataset, fit_production_model, save_model, train_and_evaluate


def main():
    print("Generating training data from live simulations (10 seeds x 4 scenarios)...")
    df = build_dataset()
    print(f"Dataset: {len(df)} completed-trip rows, mean wait = {df.wait_min.mean():.2f} min")

    results = train_and_evaluate(df)
    print("\n=== Model comparison (held-out test set, split by simulated day) ===")
    for name in ["naive_distance_eta", "linear_regression", "gradient_boosting"]:
        r = results[name]
        print(f"{name:20s}  MAE={r['mae']:.3f} min  P50 err={r['p50_error_min']:.3f} min  P90 err={r['p90_error_min']:.3f} min")

    print(f"\nn_train={results['n_train']}  n_test={results['n_test']}  mean_wait={results['mean_wait_min']:.2f} min")
    print("\n=== Feature importance (gradient boosting) ===")
    for name, imp in results["feature_importance"]:
        print(f"  {name:30s} {imp:.4f}")

    print(f"\nFitting production model on all {len(df)} rows and saving to {MODEL_PATH} ...")
    production_model = fit_production_model(df)
    save_model(production_model)
    print("Done. Use src.ml_wait_time.predict_wait_time() or the AI copilot's forecast_eta tool for inference.")


if __name__ == "__main__":
    main()
