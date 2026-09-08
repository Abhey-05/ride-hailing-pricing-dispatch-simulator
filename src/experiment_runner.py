"""
Experiment orchestration -- runs the full matrix defined in
docs/EXPERIMENT_DESIGN.md Section O:

- CORE: 4 pricing x 5 dispatch x 24 seeds, scenario=NORMAL -> 480 runs.
  One World is generated per seed and re-used across all 20 policy
  combinations for that seed (common random numbers, Section P).
- ROBUSTNESS: the other 5 scenarios x 4 pricing x 5 dispatch x 6 seeds
  -> 600 runs.

Every row of the output table is one simulation run's full config + full
metric summary -- the single source of truth for all downstream statistical
analysis and charts.
"""
from __future__ import annotations

import time
from dataclasses import asdict

from src import config, engine, world

CORE_SCENARIO = "NORMAL"
CORE_SEEDS = list(range(24))
ROBUSTNESS_SCENARIOS = [s for s in config.SCENARIOS if s != CORE_SCENARIO]
ROBUSTNESS_SEEDS = list(range(6))


def _run_one(scenario_name, seed, pricing, dispatch, group, w=None):
    if w is None:
        w = world.generate_world(scenario_name, seed=seed)
    eng = engine.SimulationEngine(w, pricing, dispatch, config.SCENARIOS[scenario_name])
    result = eng.run()
    row = {
        "experiment_group": group,
        "scenario": scenario_name,
        "seed": seed,
        "pricing_policy": pricing.value,
        "dispatch_policy": dispatch.value,
    }
    row.update(result.summary)
    return row


def run_all(progress_every: int = 50, log=print):
    rows = []
    t0 = time.time()
    total = len(CORE_SEEDS) * 4 * 5 + len(ROBUSTNESS_SCENARIOS) * len(ROBUSTNESS_SEEDS) * 4 * 5
    done = 0

    log(f"Starting CORE experiment: {CORE_SCENARIO}, {len(CORE_SEEDS)} seeds x 20 policy combos = {len(CORE_SEEDS)*20} runs")
    for seed in CORE_SEEDS:
        w = world.generate_world(CORE_SCENARIO, seed=seed)
        for pricing in config.PricingPolicy:
            for dispatch in config.DispatchPolicy:
                rows.append(_run_one(CORE_SCENARIO, seed, pricing, dispatch, "core", w=w))
                done += 1
                if done % progress_every == 0:
                    log(f"  [{done}/{total}] elapsed {time.time()-t0:.1f}s")

    log(f"Starting ROBUSTNESS experiments: {len(ROBUSTNESS_SCENARIOS)} scenarios x {len(ROBUSTNESS_SEEDS)} seeds x 20 combos")
    for scenario_name in ROBUSTNESS_SCENARIOS:
        for seed in ROBUSTNESS_SEEDS:
            w = world.generate_world(scenario_name, seed=seed)
            for pricing in config.PricingPolicy:
                for dispatch in config.DispatchPolicy:
                    rows.append(_run_one(scenario_name, seed, pricing, dispatch, "robustness", w=w))
                    done += 1
                    if done % progress_every == 0:
                        log(f"  [{done}/{total}] elapsed {time.time()-t0:.1f}s")

    log(f"Done: {len(rows)} total runs in {time.time()-t0:.1f}s")
    return rows
