"""
Deterministic seeding utilities.

Never use Python's built-in hash() on strings for seeding -- string hashing
is randomized per-process (PYTHONHASHSEED) and is NOT reproducible across
runs/machines. Everything here is built from plain integers via
numpy.random.SeedSequence, which is deterministic by design.
"""
from __future__ import annotations

import numpy as np

SCENARIO_CODES = {
    "NORMAL": 0,
    "PEAK_DEMAND": 1,
    "SUPPLY_SHORTAGE": 2,
    "DEMAND_SHOCK": 3,
    "LOW_DEMAND": 4,
    "CONGESTED_PEAK": 5,
}


def world_seed_material(scenario_name: str, seed: int) -> int:
    """One integer identifying the exogenous 'world' for a (scenario, seed) pair.
    Policy is deliberately NOT an input -- this is what makes the world
    (arrivals, driver population, rider attributes) identical across every
    policy combination tested at this seed (common random numbers)."""
    code = SCENARIO_CODES[scenario_name]
    return seed * 1000 + code


def make_rng(seed_material: int, *namespace: int) -> np.random.Generator:
    """A deterministic, independent RNG stream keyed by seed_material + namespace ints."""
    return np.random.default_rng(np.random.SeedSequence([seed_material, *namespace]))
