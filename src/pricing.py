"""Pricing policies (MATHEMATICAL_MODEL.md Section G)."""
from __future__ import annotations

from src import config


class PricingEngine:
    """Stateful surge engine -- holds per-zone last-computed surge and
    smoothing state so update cadence / exponential smoothing works correctly
    across ticks."""

    def __init__(self, policy: config.PricingPolicy):
        self.policy = policy
        self.params = config.PRICING_PARAMS[policy]
        self._last_surge = {z.id: 1.0 for z in config.ZONES}
        self._last_update_tick = {z.id: -10_000 for z in config.ZONES}

    def surge_for_zone(self, zone_id: int, tick: int, imbalance: float) -> float:
        if self.policy == config.PricingPolicy.NO_SURGE:
            return 1.0

        update_every = self.params["update_every_ticks"]
        due = (tick - self._last_update_tick[zone_id]) >= update_every
        if not due:
            return self._last_surge[zone_id]

        min_s = self.params["min_surge"]
        max_s = self.params["max_surge"]
        alpha = self.params["alpha"]

        if self.policy == config.PricingPolicy.BASIC_SURGE:
            raw = 1.0 + alpha * (imbalance - 1.0)
            surge = min(max(raw, min_s), max_s)
        elif self.policy == config.PricingPolicy.AGGRESSIVE_SURGE:
            raw = 1.0 + alpha * imbalance
            surge = min(max(raw, min_s), max_s)
        elif self.policy == config.PricingPolicy.CAPPED_SMOOTHED_SURGE:
            raw = 1.0 + alpha * (imbalance - 1.0)
            raw = min(max(raw, min_s), max_s)
            lam = self.params["smoothing_lambda"]
            prev = self._last_surge[zone_id]
            surge = lam * raw + (1 - lam) * prev
            surge = min(max(surge, min_s), max_s)
        else:
            raise ValueError(f"Unknown pricing policy: {self.policy}")

        self._last_surge[zone_id] = surge
        self._last_update_tick[zone_id] = tick
        return surge


def base_fare(distance_km: float, duration_min: float) -> float:
    return config.BASE_FEE + config.DISTANCE_RATE_PER_KM * distance_km + config.TIME_RATE_PER_MIN * duration_min
