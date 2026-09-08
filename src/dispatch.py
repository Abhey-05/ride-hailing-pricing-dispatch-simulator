"""Dispatch policies (MATHEMATICAL_MODEL.md Section H).

Each policy is a pure function: given the current waiting-request queue
(oldest-wait-first, fixed ordering across all policies) and available/soon-
free drivers, it greedily assigns drivers to requests, one request at a time,
removing the chosen driver from the candidate pool as it goes. This is a
*greedy per-tick heuristic*, not a joint optimal assignment -- see
MATHEMATICAL_MODEL.md Section H.5 for why an exact solver is not used.
"""
from __future__ import annotations

from dataclasses import dataclass

from src import behavior, city, config
from src.entities import Driver, Request


@dataclass
class MarketContext:
    tick: int
    hour: float
    congestion_mult: float
    available_by_zone: dict[int, int]
    outstanding_by_zone: dict[int, int]
    avg_outstanding: float
    avg_fare_driver_share: float
    avg_pickup_eta_min: float


def eta_minutes(from_zone: int, to_zone: int, congestion_mult: float) -> float:
    dist = city.distance_km(from_zone, to_zone)
    speed = config.BASE_SPEED_KMH / congestion_mult
    return (dist / speed) * 60.0


def _post_dispatch_ratio(zone: int, ctx: MarketContext) -> float:
    avail = max(0, ctx.available_by_zone.get(zone, 0) - 1)
    outstanding = ctx.outstanding_by_zone.get(zone, 0)
    return avail / (outstanding + 1.0)


def dispatch_one(
    policy: config.DispatchPolicy,
    request: Request,
    available: list[Driver],
    soon_free: list[Driver],
    ctx: MarketContext,
) -> tuple[Driver, float, float] | None:
    """Returns (driver, pickup_eta_min, pickup_distance_km) or None if no candidate."""
    if not available and not soon_free:
        return None

    if policy == config.DispatchPolicy.NEAREST_DRIVER:
        if not available:
            return None
        best = min(available, key=lambda d: (city.distance_km(d.zone, request.origin_zone), d.id))
        dist = city.distance_km(best.zone, request.origin_zone)
        eta = eta_minutes(best.zone, request.origin_zone, ctx.congestion_mult)
        return best, eta, dist

    if policy == config.DispatchPolicy.ETA_OPTIMIZED:
        best_driver, best_score, best_eta, best_dist = None, float("inf"), None, None
        for d in available:
            eta = eta_minutes(d.zone, request.origin_zone, ctx.congestion_mult)
            if eta < best_score or (eta == best_score and (best_driver is None or d.id < best_driver.id)):
                best_driver, best_score, best_eta = d, eta, eta
                best_dist = city.distance_km(d.zone, request.origin_zone)
        for d in soon_free:
            release_in = max(0, d.release_tick - ctx.tick) if d.release_tick is not None else 0
            future_zone = d.destination_zone if d.destination_zone is not None else d.zone
            eta = release_in + eta_minutes(future_zone, request.origin_zone, ctx.congestion_mult)
            if eta < best_score:
                best_driver, best_score, best_eta = d, eta, eta
                best_dist = city.distance_km(future_zone, request.origin_zone)
        if best_driver is None:
            return None
        return best_driver, best_eta, best_dist

    if policy == config.DispatchPolicy.DRIVER_EARNINGS_AWARE:
        if not available:
            return None
        ranked = sorted(available, key=lambda d: (city.distance_km(d.zone, request.origin_zone), d.id))
        topk = ranked[: config.DISPATCH_EARNINGS_AWARE_TOPK]
        best_driver, best_p, best_eta, best_dist = None, -1.0, None, None
        fare_share = (1 - config.COMMISSION_RATE) * request.final_price
        dest_attr = behavior.destination_attractiveness(
            request.destination_zone, ctx.outstanding_by_zone, ctx.avg_outstanding
        )
        for d in topk:
            eta = eta_minutes(d.zone, request.origin_zone, ctx.congestion_mult)
            util = (d.active_ticks / d.online_ticks) if d.online_ticks > 0 else 0.0
            p = behavior.driver_accept_probability(
                fare_share, ctx.avg_fare_driver_share, eta, ctx.avg_pickup_eta_min, dest_attr, util
            )
            if p > best_p:
                best_driver, best_p, best_eta = d, p, eta
                best_dist = city.distance_km(d.zone, request.origin_zone)
        return best_driver, best_eta, best_dist

    if policy == config.DispatchPolicy.MARKETPLACE_AWARE:
        if not available:
            return None
        best_driver, best_score, best_eta, best_dist = None, float("inf"), None, None
        for d in available:
            eta = eta_minutes(d.zone, request.origin_zone, ctx.congestion_mult)
            penalty = config.MARKETPLACE_AWARE_BETA * max(
                0.0, config.MARKETPLACE_AWARE_TARGET_RATIO - _post_dispatch_ratio(d.zone, ctx)
            )
            score = eta + penalty
            if score < best_score:
                best_driver, best_score, best_eta = d, score, eta
                best_dist = city.distance_km(d.zone, request.origin_zone)
        return best_driver, best_eta, best_dist

    if policy == config.DispatchPolicy.ADVANCED_HEURISTIC:
        w = config.ADVANCED_HEURISTIC_WEIGHTS
        avg_eta = ctx.avg_pickup_eta_min if ctx.avg_pickup_eta_min > 0 else 8.0
        elapsed_wait = ctx.tick - request.created_tick
        cancel_urgency = elapsed_wait / max(request.patience_min, 0.1)
        dest_attr = behavior.destination_attractiveness(
            request.destination_zone, ctx.outstanding_by_zone, ctx.avg_outstanding
        )
        best_driver, best_score, best_eta, best_dist = None, float("inf"), None, None
        candidates = [(d, 0, d.zone) for d in available]
        for d in soon_free:
            release_in = max(0, d.release_tick - ctx.tick) if d.release_tick is not None else 0
            future_zone = d.destination_zone if d.destination_zone is not None else d.zone
            candidates.append((d, release_in, future_zone))
        for d, release_in, from_zone in candidates:
            eta = release_in + eta_minutes(from_zone, request.origin_zone, ctx.congestion_mult)
            imb_penalty = max(0.0, w["target_ratio"] - _post_dispatch_ratio(from_zone, ctx))
            cost = (
                w["w_eta"] * (eta / avg_eta)
                + w["w_imb"] * imb_penalty
                - w["w_dest"] * dest_attr
                - w["w_cancel"] * cancel_urgency
            )
            if cost < best_score:
                best_driver, best_score, best_eta = d, cost, eta
                best_dist = city.distance_km(from_zone, request.origin_zone)
        if best_driver is None:
            return None
        return best_driver, best_eta, best_dist

    raise ValueError(f"Unknown dispatch policy: {policy}")


def run_dispatch_tick(
    policy: config.DispatchPolicy,
    waiting_requests: list[Request],
    available_drivers: list[Driver],
    soon_free_drivers: list[Driver],
    ctx: MarketContext,
) -> list[tuple[Request, Driver, float, float]]:
    """Greedily match, oldest-waiting-request first. Drivers are removed by id
    (not dataclass equality) once matched, so a driver can only be picked
    once per tick."""
    available_pool = {d.id: d for d in available_drivers}
    soon_free_pool = {d.id: d for d in soon_free_drivers}
    matches = []
    for request in waiting_requests:
        result = dispatch_one(
            policy, request, list(available_pool.values()), list(soon_free_pool.values()), ctx
        )
        if result is None:
            continue
        driver, eta, dist = result
        matches.append((request, driver, eta, dist))
        available_pool.pop(driver.id, None)
        soon_free_pool.pop(driver.id, None)
    return matches
