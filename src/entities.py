"""Domain entities: drivers, requests, and their state machines (MATHEMATICAL_MODEL.md Sec E)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from src import config, rng_utils


class DriverState(str, Enum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE_TO_PICKUP = "EN_ROUTE_TO_PICKUP"
    ON_TRIP = "ON_TRIP"


class RequestState(str, Enum):
    WAITING = "WAITING"
    MATCHED = "MATCHED"
    ON_TRIP = "ON_TRIP"
    COMPLETED = "COMPLETED"
    REJECTED_OFFER = "REJECTED_OFFER"
    ABANDONED = "ABANDONED"
    CANCELLED_POSTMATCH = "CANCELLED_POSTMATCH"


# ---------------------------------------------------------------------------
# Specs: policy-independent "facts" about an agent, pre-generated once per
# (scenario, seed) world and then replayed identically into every policy run.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DriverSpec:
    id: int
    home_zone: int
    shift_start_tick: int
    shift_end_tick: int


@dataclass(frozen=True)
class RequestSpec:
    id: int
    created_tick: int
    origin_zone: int
    destination_zone: int
    segment: config.RiderSegment
    patience_min: float
    beta_price: float
    beta_wait: float


# ---------------------------------------------------------------------------
# Live simulation objects (fresh instance per policy run, built from a Spec)
# ---------------------------------------------------------------------------
@dataclass
class Driver:
    id: int
    home_zone: int
    shift_start_tick: int
    shift_end_tick: int
    state: DriverState = DriverState.OFFLINE
    zone: int = -1
    active_request_id: int | None = None
    release_tick: int | None = None  # tick at which current EN_ROUTE/ON_TRIP phase ends
    destination_zone: int | None = None  # where the driver is headed (pickup or dropoff)
    queued_request_id: int | None = None  # pre-booked next request (look-ahead dispatch policies)
    queued_pickup_travel_min: float | None = None  # travel-only time for the queued pickup
    gross_earnings: float = 0.0
    online_ticks: int = 0
    active_ticks: int = 0
    trips_completed: int = 0
    assignments_offered: int = 0
    assignments_accepted: int = 0
    rng: np.random.Generator = field(default=None, repr=False)

    @classmethod
    def from_spec(cls, spec: DriverSpec, seed_material: int) -> "Driver":
        return cls(
            id=spec.id,
            home_zone=spec.home_zone,
            shift_start_tick=spec.shift_start_tick,
            shift_end_tick=spec.shift_end_tick,
            zone=spec.home_zone,
            rng=rng_utils.make_rng(seed_material, 2, spec.id),
        )

    def next_uniform(self) -> float:
        return float(self.rng.random())


@dataclass
class Request:
    id: int
    created_tick: int
    origin_zone: int
    destination_zone: int
    segment: config.RiderSegment
    patience_min: float
    beta_price: float
    beta_wait: float
    state: RequestState = RequestState.WAITING
    distance_km: float = 0.0
    final_price: float = 0.0
    surge_multiplier: float = 1.0
    imbalance_at_request: float = 0.0
    matched_tick: int | None = None
    pickup_started_tick: int | None = None
    trip_started_tick: int | None = None
    completed_tick: int | None = None
    driver_id: int | None = None
    pickup_eta_min: float | None = None
    pickup_distance_km: float | None = None
    trip_duration_min: float | None = None
    n_cancel_checks: int = 0
    rng: np.random.Generator = field(default=None, repr=False)

    @classmethod
    def from_spec(cls, spec: RequestSpec, seed_material: int) -> "Request":
        return cls(
            id=spec.id,
            created_tick=spec.created_tick,
            origin_zone=spec.origin_zone,
            destination_zone=spec.destination_zone,
            segment=spec.segment,
            patience_min=spec.patience_min,
            beta_price=spec.beta_price,
            beta_wait=spec.beta_wait,
            rng=rng_utils.make_rng(seed_material, 3, spec.id),
        )

    def next_uniform(self) -> float:
        return float(self.rng.random())
