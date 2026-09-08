"""City/zone geometry, time-of-day interpolation, and directional flow sampling."""
from __future__ import annotations

import math

import numpy as np

from src import config


def distance_km(zone_a: int, zone_b: int) -> float:
    if zone_a == zone_b:
        return config.MIN_INTRAZONE_DISTANCE_KM
    za, zb = config.ZONES[zone_a], config.ZONES[zone_b]
    d = math.hypot(za.x - zb.x, za.y - zb.y) * config.GRID_SCALE_KM
    return max(d, config.MIN_INTRAZONE_DISTANCE_KM)


def _period_index(hour: float) -> int:
    for i, (_, start, end) in enumerate(config.TOD_PERIODS):
        if start <= hour < end:
            return i
    return len(config.TOD_PERIODS) - 1


def _period_midpoint(i: int) -> float:
    _, start, end = config.TOD_PERIODS[i]
    return (start + end) / 2.0


def current_period_name(hour: float) -> str:
    return config.TOD_PERIODS[_period_index(hour)][0]


def tod_multiplier(archetype: str, hour: float) -> float:
    """Piecewise-linear interpolation between period midpoints (see ASSUMPTIONS.md)."""
    table = config.ARCHETYPE_TOD_MULTIPLIER[archetype]
    n = len(config.TOD_PERIODS)
    i = _period_index(hour)
    mid_i = _period_midpoint(i)
    name_i = config.TOD_PERIODS[i][0]
    if hour >= mid_i:
        j = (i + 1) % n
    else:
        j = (i - 1) % n
    name_j = config.TOD_PERIODS[j][0]
    mid_j = _period_midpoint(j)
    # handle wraparound distance across midnight
    span = (mid_j - mid_i) % 24.0
    if span == 0:
        return table[name_i]
    pos = (hour - mid_i) % 24.0
    frac = min(pos / span, 1.0)
    return table[name_i] * (1 - frac) + table[name_j] * frac


def congestion_multiplier(hour: float, scenario_congestion_mult: float) -> float:
    name = current_period_name(hour)
    return config.CONGESTION_BY_PERIOD[name] * scenario_congestion_mult


def sample_destination(origin_zone: int, hour: float, rng: np.random.Generator) -> int:
    """Sample a destination zone given origin and time period, using flow bias
    plus a baseline-demand-weighted fallback so every zone is reachable."""
    origin_archetype = config.ZONES[origin_zone].archetype
    period = current_period_name(hour)
    bias = config.FLOW_BIAS.get(origin_archetype, {}).get(period, {})

    weights = np.array([z.lambda_base for z in config.ZONES], dtype=float)
    weights = weights / weights.sum()

    if bias:
        biased_mass = sum(bias.values())
        biased_mass = min(biased_mass, 0.95)
        remaining = 1.0 - biased_mass
        final_weights = weights * remaining
        for dest_archetype, w in bias.items():
            idx = [z.id for z in config.ZONES if z.archetype == dest_archetype]
            if not idx:
                continue
            share = w / len(idx)
            for i in idx:
                final_weights[i] += share
        final_weights = final_weights / final_weights.sum()
    else:
        final_weights = weights

    return int(rng.choice(config.NUM_ZONES, p=final_weights))
