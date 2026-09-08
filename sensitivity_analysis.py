#!/usr/bin/env python3
"""
Experiment 12 (docs/EXPERIMENT_DESIGN.md Section W): perturb the most
uncertain synthetic parameters by +/-30% and re-check whether the core
finding (ETA_OPTIMIZED beats NEAREST_DRIVER on P90 wait under BASIC_SURGE)
survives. This directly answers docs/CRITICAL_REVIEW.md item #4.

Implementation note: src.config values are read directly by other modules
at call time (not copied at import time), so temporarily mutating a config
attribute and restoring it afterward is a valid, safe way to run this sweep
in a single-threaded script -- there is no concurrency here.
"""
from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd

from src import config, engine, world

SEEDS = list(range(8))
PARAM_FACTORS = [0.7, 1.3]


def run_pair(seed: int) -> dict:
    w = world.generate_world("NORMAL", seed=seed)
    results = {}
    for dispatch in (config.DispatchPolicy.NEAREST_DRIVER, config.DispatchPolicy.ETA_OPTIMIZED):
        eng = engine.SimulationEngine(w, config.PricingPolicy.BASIC_SURGE, dispatch, config.SCENARIOS["NORMAL"])
        res = eng.run()
        results[dispatch.value] = res.summary["p90_wait_min"]
    return results


def relative_effect_over_seeds() -> tuple[float, list[float]]:
    diffs = []
    for seed in SEEDS:
        r = run_pair(seed)
        rel = (r["ETA_OPTIMIZED"] - r["NEAREST_DRIVER"]) / r["NEAREST_DRIVER"] * 100
        diffs.append(rel)
    return float(np.mean(diffs)), diffs


# --- perturbation setups: each returns a restore function ---

def perturb_price_elasticity(factor):
    original = {k: dict(v) for k, v in config.RIDER_SEGMENT_PARAMS.items()}
    for seg, params in config.RIDER_SEGMENT_PARAMS.items():
        params["beta_price"] = original[seg]["beta_price"] * factor
    return lambda: config.RIDER_SEGMENT_PARAMS.update({k: dict(v) for k, v in original.items()})


def perturb_patience(factor):
    original = {k: dict(v) for k, v in config.RIDER_SEGMENT_PARAMS.items()}
    for seg, params in config.RIDER_SEGMENT_PARAMS.items():
        params["patience_median"] = original[seg]["patience_median"] * factor
    return lambda: config.RIDER_SEGMENT_PARAMS.update({k: dict(v) for k, v in original.items()})


def perturb_driver_acceptance_sensitivity(factor):
    orig_pickup = config.DRIVER_ACCEPT_GAMMA_PICKUP
    orig_fare = config.DRIVER_ACCEPT_GAMMA_FARE
    config.DRIVER_ACCEPT_GAMMA_PICKUP = orig_pickup * factor
    config.DRIVER_ACCEPT_GAMMA_FARE = orig_fare * factor

    def restore():
        config.DRIVER_ACCEPT_GAMMA_PICKUP = orig_pickup
        config.DRIVER_ACCEPT_GAMMA_FARE = orig_fare
    return restore


def perturb_congestion(factor):
    original = dict(config.CONGESTION_BY_PERIOD)
    for k in config.CONGESTION_BY_PERIOD:
        config.CONGESTION_BY_PERIOD[k] = original[k] * factor
    return lambda: config.CONGESTION_BY_PERIOD.update(original)


def perturb_demand_intensity(factor):
    original_zones = config.ZONES
    config.ZONES = [dataclasses.replace(z, lambda_base=z.lambda_base * factor) for z in original_zones]

    def restore():
        config.ZONES = original_zones
    return restore


def perturb_supply_intensity(factor):
    original = config.DEFAULT_FLEET_SIZE
    config.DEFAULT_FLEET_SIZE = int(round(original * factor))

    def restore():
        config.DEFAULT_FLEET_SIZE = original
    return restore


SWEEPS = {
    "price_elasticity (beta_price)": perturb_price_elasticity,
    "rider_patience": perturb_patience,
    "driver_acceptance_sensitivity (gamma_pickup/fare)": perturb_driver_acceptance_sensitivity,
    "congestion_multiplier": perturb_congestion,
    "demand_intensity (lambda_base)": perturb_demand_intensity,
    "supply_intensity (fleet_size)": perturb_supply_intensity,
}


def main():
    print("Baseline (no perturbation):")
    baseline_mean, _ = relative_effect_over_seeds()
    print(f"  ETA_OPTIMIZED vs NEAREST_DRIVER P90 wait relative effect: {baseline_mean:.2f}% (n={len(SEEDS)} seeds)\n")

    rows = [{"parameter": "baseline", "factor": 1.0, "relative_effect_pct": baseline_mean, "sign_preserved": True}]

    for name, fn in SWEEPS.items():
        for factor in PARAM_FACTORS:
            restore = fn(factor)
            try:
                mean_effect, diffs = relative_effect_over_seeds()
            finally:
                restore()
            sign_preserved = (mean_effect < 0) == (baseline_mean < 0)  # both "improvement" (negative = better)
            print(f"{name:55s} x{factor:.1f}: relative effect = {mean_effect:+.2f}%  (sign preserved: {sign_preserved})")
            rows.append({
                "parameter": name, "factor": factor,
                "relative_effect_pct": mean_effect, "sign_preserved": sign_preserved,
            })

    df = pd.DataFrame(rows)
    df.to_csv("results/sensitivity_analysis.csv", index=False)
    print(f"\nSaved results/sensitivity_analysis.csv ({len(df)} rows)")

    all_preserved = df["sign_preserved"].all()
    print(f"\nConclusion sign preserved across ALL perturbations: {all_preserved}")


if __name__ == "__main__":
    main()
