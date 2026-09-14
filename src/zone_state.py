"""
Per-zone spatial marketplace state, derived from a completed simulation
run's request records and timeseries snapshots.

This adds no new simulation behavior and does not touch src/engine.py: the
engine already tracks per-zone available-driver and outstanding-request
counts every timeseries tick (see SimulationEngine._record_timeseries), and
every completed/cancelled request already carries its origin zone
(src/metrics.py RequestRecord). This module just aggregates data the engine
already produces, grouped by zone, for the map and the health-score spatial
breakdown -- it is a read-only view over one run's results, not a new
source of randomness or behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from src import config, labels
from src.metrics import MetricsCollector

# Status thresholds on supply/demand ratio = avg available drivers / avg
# outstanding requests in a zone. Bands chosen so "healthy" corresponds to
# at least slightly more available drivers than outstanding requests, and
# "severe_shortage" to fewer than 1 available driver per ~7 outstanding
# requests -- consistent with the same ratio already used by
# src/pricing.py's imbalance-driven surge and src/dispatch.py's
# MARKETPLACE_AWARE policy (MARKETPLACE_AWARE_TARGET_RATIO = 1.0).
STATUS_THRESHOLDS: list[tuple[float, str]] = [
    (0.9, "healthy"),
    (0.5, "moderate"),
    (0.2, "high_pressure"),
    (0.0, "severe_shortage"),
]

STATUS_COLOR = {
    "healthy": labels.SEMANTIC_COLORS["green"],
    "moderate": labels.SEMANTIC_COLORS["amber"],
    "high_pressure": labels.SEMANTIC_COLORS["amber_dark"],
    "severe_shortage": labels.SEMANTIC_COLORS["red"],
}

STATUS_LABEL = {
    "healthy": "Balanced",
    "moderate": "Moderate shortage",
    "high_pressure": "High demand pressure",
    "severe_shortage": "Severe supply shortage",
}


def _status_for_ratio(ratio: float) -> str:
    for threshold, label in STATUS_THRESHOLDS:
        if ratio >= threshold:
            return label
    return STATUS_THRESHOLDS[-1][1]


@dataclass
class ZoneState:
    zone_id: int
    name: str
    archetype: str
    x: float
    y: float
    demand_per_min: float
    avg_available_drivers: float
    avg_outstanding_requests: float
    supply_demand_ratio: float
    avg_wait_min: float
    p90_wait_min: float
    cancellation_rate: float
    completion_rate: float
    avg_surge_multiplier: float
    avg_pickup_distance_km: float
    n_requests: int
    status: str

    @property
    def color(self) -> str:
        return STATUS_COLOR[self.status]

    @property
    def status_label(self) -> str:
        return STATUS_LABEL[self.status]


def compute_zone_states(
    collector: MetricsCollector, timeseries: list[dict], horizon_minutes: float
) -> list[ZoneState]:
    """Aggregate one completed run's collector + timeseries into per-zone
    state. `timeseries` must come from the same run (engine must have been
    constructed with collect_timeseries=True)."""
    n_snaps = len(timeseries)
    avail_sums = {z.id: 0.0 for z in config.ZONES}
    outstanding_sums = {z.id: 0.0 for z in config.ZONES}
    for row in timeseries:
        for zid in avail_sums:
            avail_sums[zid] += row["available_by_zone"].get(zid, 0)
            outstanding_sums[zid] += row["outstanding_by_zone"].get(zid, 0)

    by_zone: dict[int, list] = {z.id: [] for z in config.ZONES}
    for r in collector.requests:
        by_zone[r.origin_zone].append(r)

    states = []
    for z in config.ZONES:
        reqs = by_zone[z.id]
        n = len(reqs)
        completed = [r for r in reqs if r.state == "COMPLETED"]
        cancelled = [r for r in reqs if r.state in ("ABANDONED", "CANCELLED_POSTMATCH")]
        waits = np.array([r.wait_min for r in completed], dtype=float) if completed else np.array([])
        surges = np.array([r.surge_multiplier for r in reqs], dtype=float) if reqs else np.array([1.0])
        pickup = (
            np.array([r.pickup_distance_km for r in completed if r.pickup_distance_km is not None], dtype=float)
            if completed else np.array([])
        )

        avg_avail = avail_sums[z.id] / n_snaps if n_snaps else 0.0
        avg_outstanding = outstanding_sums[z.id] / n_snaps if n_snaps else 0.0
        ratio = avg_avail / (avg_outstanding + 1.0)

        states.append(
            ZoneState(
                zone_id=z.id,
                name=z.name,
                archetype=z.archetype,
                x=z.x,
                y=z.y,
                demand_per_min=(n / horizon_minutes) if horizon_minutes else 0.0,
                avg_available_drivers=avg_avail,
                avg_outstanding_requests=avg_outstanding,
                supply_demand_ratio=ratio,
                avg_wait_min=float(waits.mean()) if len(waits) else float("nan"),
                p90_wait_min=float(np.percentile(waits, 90)) if len(waits) else float("nan"),
                cancellation_rate=(len(cancelled) / n) if n else 0.0,
                completion_rate=(len(completed) / n) if n else 0.0,
                avg_surge_multiplier=float(surges.mean()),
                avg_pickup_distance_km=float(pickup.mean()) if len(pickup) else float("nan"),
                n_requests=n,
                status=_status_for_ratio(ratio),
            )
        )
    return states


def worst_zones(states: list[ZoneState], n: int = 3) -> list[ZoneState]:
    return sorted(states, key=lambda s: s.supply_demand_ratio)[:n]


def zone_states_to_dataframe(states: list[ZoneState]) -> pd.DataFrame:
    return pd.DataFrame([asdict(s) for s in states])


def explain_zone(state: ZoneState, city_avg_demand_per_min: float, city_avg_available: float) -> list[str]:
    """A short list of plain-language causal bullets for why a zone is in
    its current state, purely derived from the zone's own numbers relative
    to the city-wide average -- no LLM involved."""
    reasons = []
    if city_avg_demand_per_min > 0:
        demand_delta_pct = (state.demand_per_min - city_avg_demand_per_min) / city_avg_demand_per_min * 100
        if demand_delta_pct > 15:
            reasons.append(f"Demand is {demand_delta_pct:+.0f}% vs. the city-wide average zone.")
    if city_avg_available > 0:
        supply_delta_pct = (state.avg_available_drivers - city_avg_available) / city_avg_available * 100
        if supply_delta_pct < -15:
            reasons.append(f"Available drivers are {supply_delta_pct:+.0f}% vs. the city-wide average zone.")
    if state.cancellation_rate > 0.25:
        reasons.append(f"Cancellation rate ({state.cancellation_rate*100:.0f}%) is elevated.")
    if state.avg_surge_multiplier > 1.5:
        reasons.append(f"Surge is elevated ({state.avg_surge_multiplier:.2f}x), a symptom of the same imbalance.")
    if not reasons:
        reasons.append("No single dominant driver identified -- metrics are within the normal range for this zone.")
    return reasons[:3]
