"""Metrics collection and computation (MATHEMATICAL_MODEL.md Section L).

The collector only records facts as the engine produces them; every formula
here matches the metric dictionary exactly and is identical regardless of
which pricing/dispatch policy generated the underlying events.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from src import config
from src.entities import Driver, Request, RequestState


@dataclass
class RequestRecord:
    id: int
    created_tick: int
    origin_zone: int
    destination_zone: int
    segment: str
    state: str
    final_price: float
    surge_multiplier: float
    distance_km: float
    pickup_distance_km: float | None
    pickup_eta_min: float | None
    wait_min: float | None  # only set for COMPLETED trips: request->pickup time
    patience_min: float = 0.0
    imbalance_at_request: float = 0.0
    hour_created: float = 0.0


@dataclass
class DriverRecord:
    id: int
    online_minutes: float
    active_minutes: float
    gross_earnings: float
    trips_completed: int
    assignments_offered: int
    assignments_accepted: int


class MetricsCollector:
    def __init__(self):
        self.requests: list[RequestRecord] = []
        self.drivers: list[DriverRecord] = []

    def record_request_terminal(self, r: Request) -> None:
        wait_min = None
        if r.state == RequestState.COMPLETED and r.trip_started_tick is not None:
            wait_min = (r.trip_started_tick - r.created_tick) * config.TICK_MINUTES
        self.requests.append(
            RequestRecord(
                id=r.id,
                created_tick=r.created_tick,
                origin_zone=r.origin_zone,
                destination_zone=r.destination_zone,
                segment=r.segment.value if hasattr(r.segment, "value") else str(r.segment),
                state=r.state.value if hasattr(r.state, "value") else str(r.state),
                final_price=r.final_price,
                surge_multiplier=r.surge_multiplier,
                distance_km=r.distance_km,
                pickup_distance_km=r.pickup_distance_km,
                pickup_eta_min=r.pickup_eta_min,
                wait_min=wait_min,
                patience_min=r.patience_min,
                imbalance_at_request=r.imbalance_at_request,
                hour_created=(r.created_tick / 60.0) % 24.0,
            )
        )

    def record_driver_final(self, d: Driver) -> None:
        self.drivers.append(
            DriverRecord(
                id=d.id,
                online_minutes=d.online_ticks * config.TICK_MINUTES,
                active_minutes=d.active_ticks * config.TICK_MINUTES,
                gross_earnings=d.gross_earnings,
                trips_completed=d.trips_completed,
                assignments_offered=d.assignments_offered,
                assignments_accepted=d.assignments_accepted,
            )
        )

    def compute_summary(self) -> dict:
        reqs = self.requests
        n_total = len(reqs)
        completed = [r for r in reqs if r.state == "COMPLETED"]
        abandoned = [r for r in reqs if r.state == "ABANDONED"]
        cancelled_pm = [r for r in reqs if r.state == "CANCELLED_POSTMATCH"]
        rejected_offer = [r for r in reqs if r.state == "REJECTED_OFFER"]
        n_completed = len(completed)

        waits = np.array([r.wait_min for r in completed], dtype=float) if completed else np.array([])
        prices = np.array([r.final_price for r in completed], dtype=float) if completed else np.array([])
        pickup_dist = np.array(
            [r.pickup_distance_km for r in completed if r.pickup_distance_km is not None], dtype=float
        ) if completed else np.array([])

        base_fare_no_surge = np.array(
            [r.final_price / r.surge_multiplier for r in completed], dtype=float
        ) if completed else np.array([])

        n_cancelled = len(abandoned) + len(cancelled_pm)
        cancellation_rate = n_cancelled / n_total if n_total > 0 else 0.0
        completion_rate = n_completed / n_total if n_total > 0 else 0.0
        n_priced_offers = n_total - 0  # every request is priced/offered exactly once at creation
        rider_conversion_rate = n_completed / n_priced_offers if n_priced_offers > 0 else 0.0

        gbv = float(prices.sum()) if completed else 0.0
        platform_revenue = config.COMMISSION_RATE * gbv
        driver_payout_total = (1 - config.COMMISSION_RATE) * gbv
        revenue_per_ride = platform_revenue / n_completed if n_completed > 0 else 0.0

        price_index = (
            float(prices.mean() / base_fare_no_surge.mean())
            if completed and base_fare_no_surge.mean() > 0
            else 1.0
        )

        drivers = self.drivers
        online_drivers = [d for d in drivers if d.online_minutes > 0]
        total_online_hours = sum(d.online_minutes for d in online_drivers) / 60.0
        total_active_hours = sum(d.active_minutes for d in online_drivers) / 60.0
        total_earnings = sum(d.gross_earnings for d in online_drivers)
        total_offered = sum(d.assignments_offered for d in online_drivers)
        total_accepted = sum(d.assignments_accepted for d in online_drivers)

        utilizations = np.array(
            [d.active_minutes / d.online_minutes for d in online_drivers if d.online_minutes > 0]
        )
        earnings_per_hour = np.array(
            [d.gross_earnings / (d.online_minutes / 60.0) for d in online_drivers if d.online_minutes > 0]
        )

        north_star = (n_completed / total_online_hours) if total_online_hours > 0 else 0.0

        summary = {
            "n_requests": n_total,
            "n_completed": n_completed,
            "n_abandoned": len(abandoned),
            "n_cancelled_postmatch": len(cancelled_pm),
            "n_rejected_offer": len(rejected_offer),
            "avg_wait_min": float(waits.mean()) if len(waits) else float("nan"),
            "median_wait_min": float(np.median(waits)) if len(waits) else float("nan"),
            "p90_wait_min": float(np.percentile(waits, 90)) if len(waits) else float("nan"),
            "cancellation_rate": cancellation_rate,
            "completion_rate": completion_rate,
            "fulfillment_rate": completion_rate,
            "rider_conversion_rate": rider_conversion_rate,
            "avg_price": float(prices.mean()) if len(prices) else float("nan"),
            "price_index": price_index,
            "avg_pickup_distance_km": float(pickup_dist.mean()) if len(pickup_dist) else float("nan"),
            "gbv": gbv,
            "platform_revenue": platform_revenue,
            "driver_payout_total": driver_payout_total,
            "revenue_per_ride": revenue_per_ride,
            "n_online_drivers": len(online_drivers),
            "total_online_hours": total_online_hours,
            "total_active_hours": total_active_hours,
            "driver_utilization_mean": float(utilizations.mean()) if len(utilizations) else float("nan"),
            "earnings_per_online_hour_mean": float(earnings_per_hour.mean()) if len(earnings_per_hour) else float("nan"),
            "earnings_per_active_hour": (total_earnings / total_active_hours) if total_active_hours > 0 else float("nan"),
            "driver_acceptance_rate": (total_accepted / total_offered) if total_offered > 0 else float("nan"),
            "north_star_trips_per_online_hour": north_star,
            "unmatched_requests": len(abandoned) + len(cancelled_pm),
        }
        return summary
