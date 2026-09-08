"""
World generation: pre-generates the entire exogenous state (driver population,
full day's ride-request stream with all rider attributes) ONCE per
(scenario, seed), independent of any pricing/dispatch policy.

This is the concrete implementation of "common random numbers" described in
docs/EXPERIMENT_DESIGN.md Section P: the same World object (or rather, the
same specs, replayed into fresh entity objects) is fed into every one of the
20 policy combinations tested at a given seed, so the only thing that can
differ between policy runs is the policy itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src import city, config, rng_utils
from src.entities import DriverSpec, RequestSpec


@dataclass
class World:
    scenario_name: str
    seed: int
    seed_material: int
    driver_specs: list[DriverSpec]
    request_specs: list[RequestSpec]
    horizon_ticks: int


def _sample_shift(rng: np.random.Generator) -> tuple[float, float]:
    cluster = rng.integers(0, len(config.SHIFT_START_CLUSTERS_HOURS))
    mean_hour = config.SHIFT_START_CLUSTERS_HOURS[cluster]
    start_hour = rng.normal(mean_hour, config.SHIFT_START_CLUSTER_SIGMA) % 24.0
    length_hours = rng.choice(
        config.SHIFT_LENGTH_HOURS_CHOICES, p=config.SHIFT_LENGTH_HOURS_WEIGHTS
    )
    return float(start_hour), float(length_hours)


def _generate_drivers(rng: np.random.Generator, fleet_size: int) -> list[DriverSpec]:
    shares = np.array([z.driver_share for z in config.ZONES], dtype=float)
    shares = shares / shares.sum()
    specs = []
    for i in range(fleet_size):
        home_zone = int(rng.choice(config.NUM_ZONES, p=shares))
        start_hour, length_hours = _sample_shift(rng)
        start_tick = int(round(start_hour * 60))
        end_tick = start_tick + int(round(length_hours * 60))
        specs.append(DriverSpec(id=i, home_zone=home_zone, shift_start_tick=start_tick, shift_end_tick=end_tick))
    return specs


def _sample_segment(rng: np.random.Generator) -> config.RiderSegment:
    segs = list(config.RIDER_SEGMENT_SHARE.keys())
    probs = list(config.RIDER_SEGMENT_SHARE.values())
    idx = rng.choice(len(segs), p=probs)
    return segs[idx]


def _generate_requests(
    rng: np.random.Generator, scenario: config.Scenario, horizon_ticks: int
) -> list[RequestSpec]:
    specs: list[RequestSpec] = []
    next_id = 0

    shock_zone = None
    shock_start_tick = None
    shock_end_tick = None
    if scenario.shock_mult > 0:
        shock_zone = int(rng.integers(0, config.NUM_ZONES))
        start_hour = scenario.shock_start_hour
        if start_hour is None:
            start_hour = float(rng.uniform(9.0, 19.0))
        shock_start_tick = int(round(start_hour * 60))
        shock_end_tick = shock_start_tick + int(round(scenario.shock_duration_hours * 60))

    for t in range(horizon_ticks):
        hour = (t / 60.0) % 24.0
        for z in config.ZONES:
            tod = city.tod_multiplier(z.archetype, hour)
            shock = 0.0
            if shock_zone == z.id and shock_start_tick <= t < shock_end_tick:
                shock = scenario.shock_mult
            lam_per_hour = z.lambda_base * tod * scenario.demand_mult * (1.0 + shock)
            lam_tick = lam_per_hour * (config.TICK_MINUTES / 60.0)
            n = rng.poisson(lam_tick)
            for _ in range(n):
                dest = city.sample_destination(z.id, hour, rng)
                segment = _sample_segment(rng)
                params = config.RIDER_SEGMENT_PARAMS[segment]
                mu = math.log(params["patience_median"])
                patience = float(rng.lognormal(mu, config.PATIENCE_LOGNORMAL_SIGMA))
                specs.append(
                    RequestSpec(
                        id=next_id,
                        created_tick=t,
                        origin_zone=z.id,
                        destination_zone=dest,
                        segment=segment,
                        patience_min=patience,
                        beta_price=params["beta_price"],
                        beta_wait=params["beta_wait"],
                    )
                )
                next_id += 1
    return specs


def generate_world(
    scenario_name: str,
    seed: int,
    horizon_ticks: int = config.DEFAULT_HORIZON_TICKS,
    scenario_override: config.Scenario | None = None,
) -> World:
    """scenario_override lets a caller (e.g. the AI copilot's what-if tool,
    src/copilot_tools.py) supply a modified Scenario (different demand_mult /
    supply_mult) while still keying the CRN seed off `scenario_name` -- the
    override is a controlled perturbation of the same seeded world, not a
    different world identity."""
    scenario = scenario_override if scenario_override is not None else config.SCENARIOS[scenario_name]
    seed_material = rng_utils.world_seed_material(scenario_name, seed)
    rng = rng_utils.make_rng(seed_material, 1)  # namespace 1 = world generation

    fleet_size = max(1, int(round(config.DEFAULT_FLEET_SIZE * scenario.supply_mult)))
    driver_specs = _generate_drivers(rng, fleet_size)
    request_specs = _generate_requests(rng, scenario, horizon_ticks)

    return World(
        scenario_name=scenario_name,
        seed=seed,
        seed_material=seed_material,
        driver_specs=driver_specs,
        request_specs=request_specs,
        horizon_ticks=horizon_ticks,
    )
