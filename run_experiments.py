#!/usr/bin/env python3
"""
Runs the full experiment matrix (docs/EXPERIMENT_DESIGN.md Section O) and
saves results to results/results.parquet + results/results.csv, plus a
run manifest (results/manifest.json) recording exactly how the results were
produced, for reproducibility (Part 43 of the project brief).

Usage:
    python run_experiments.py
"""
from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

import numpy
import pandas as pd

from src import experiment_runner

RESULTS_DIR = Path(__file__).parent / "results"


def main():
    t0 = time.time()
    rows = experiment_runner.run_all()
    df = pd.DataFrame(rows)

    RESULTS_DIR.mkdir(exist_ok=True)
    csv_path = RESULTS_DIR / "results.csv"
    parquet_path = RESULTS_DIR / "results.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False)

    manifest = {
        "generated_at_unix": time.time(),
        "n_runs": len(df),
        "n_core_runs": int((df["experiment_group"] == "core").sum()),
        "n_robustness_runs": int((df["experiment_group"] == "robustness").sum()),
        "wall_clock_seconds": time.time() - t0,
        "python_version": sys.version,
        "numpy_version": numpy.__version__,
        "pandas_version": pd.__version__,
        "core_scenario": experiment_runner.CORE_SCENARIO,
        "core_seeds": experiment_runner.CORE_SEEDS,
        "robustness_scenarios": experiment_runner.ROBUSTNESS_SCENARIOS,
        "robustness_seeds": experiment_runner.ROBUSTNESS_SEEDS,
    }
    with open(RESULTS_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nSaved {len(df)} rows to {csv_path} and {parquet_path}")
    print(f"Manifest: {RESULTS_DIR / 'manifest.json'}")
    print(f"Total wall clock: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
