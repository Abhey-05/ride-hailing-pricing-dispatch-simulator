"""
The simulation engine: executes the exact 12-step timestep sequence defined
in docs/MATHEMATICAL_MODEL.md Section A, tick by tick, for a pre-generated
World (see world.py) under one fixed (pricing policy, dispatch policy) pair.

Implementation notes vs. the spec (documented, not silent deviations):
- Trip/pickup timers are tracked as absolute `release_tick` values rather than
  countdown counters -- functionally identical to "decrement then resolve",
  simpler to implement correctly. Step 10 ("advance trips") is therefore a
  no-op; completions are resolved at the top of step 3 by comparing
  `release_tick == tick`.
- The ASSIGNED driver/request state is logically transient: dispatch (step 8)
  and driver-acceptance resolution (step 9) happen back-to-back within the
  same tick, so ASSIGNED is never persisted as an observable state -- a match
  resolves directly to EN_ROUTE_TO_PICKUP (accept) or reverts to
  AVAILABLE/WAITING (reject) within one tick, exactly as MATHEMATICAL_MODEL.md
  Section A describes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src import behavior, city, config, dispatch as dispatch_mod, pricing
from src.entities import Driver, Request, DriverState, RequestState
from src.metrics import MetricsCollector
from src.world import World

EMA_ALPHA = 0.15
DEFAULT_AVG_PICKUP_ETA = 6.0
DEFAULT_AVG_FARE_DRIVER_SHARE = 75.0


def _ema(prev: float, new: float, alpha: float = EMA_ALPHA) -> float:
    return alpha * new + (1 - alpha) * prev


@dataclass
class SimulationResult:
    scenario: str
    seed: int
    pricing_policy: str
    dispatch_policy: str
    summary: dict
    timeseries: list[dict] = field(default_factory=list)


class SimulationEngine:
    def __init__(
        self,
        world: World,
        pricing_policy: config.PricingPolicy,
        dispatch_policy: config.DispatchPolicy,
        scenario: config.Scenario,
        collect_timeseries: bool = False,
        timeseries_every_ticks: int = 5,
    ):
        self.world = world
        self.pricing_policy = pricing_policy
        self.dispatch_policy = dispatch_policy
        self.scenario = scenario
        self.collect_timeseries = collect_timeseries
        self.timeseries_every_ticks = timeseries_every_ticks

        self.drivers: dict[int, Driver] = {
            s.id: Driver.from_spec(s, world.seed_material) for s in world.driver_specs
        }
        self.requests: dict[int, Request] = {}
        self.requests_by_tick: dict[int, list] = {}
        for spec in world.request_specs:
            self.requests_by_tick.setdefault(spec.created_tick, []).append(spec)

        self.pricing_engine = pricing.PricingEngine(pricing_policy)
        self.collector = MetricsCollector()

        self.avg_pickup_eta_by_zone = {z.id: DEFAULT_AVG_PICKUP_ETA for z in config.ZONES}
        self.avg_pickup_eta_city = DEFAULT_AVG_PICKUP_ETA
        self.avg_fare_driver_share_city = DEFAULT_AVG_FARE_DRIVER_SHARE

    # -- helpers -----------------------------------------------------------
    def _available_by_zone(self) -> dict[int, int]:
        counts = {z.id: 0 for z in config.ZONES}
        for d in self.drivers.values():
            if d.state == DriverState.AVAILABLE:
                counts[d.zone] += 1
        return counts

    def _outstanding_by_zone(self) -> dict[int, int]:
        counts = {z.id: 0 for z in config.ZONES}
        for r in self.requests.values():
            if r.state == RequestState.WAITING:
                counts[r.origin_zone] += 1
        return counts

    def _finalize_driver(self, d: Driver, tick: int) -> None:
        if tick >= d.shift_end_tick:
            d.state = DriverState.OFFLINE
        else:
            d.state = DriverState.AVAILABLE

    # -- main loop -----------------------------------------------------------
    def run(self) -> SimulationResult:
        horizon = self.world.horizon_ticks

        for tick in range(horizon):
            hour = (tick / 60.0) % 24.0
            congestion_mult = city.congestion_multiplier(hour, self.scenario.congestion_mult)

            # --- counters (state as carried over from previous tick) ------
            for d in self.drivers.values():
                if d.state != DriverState.OFFLINE:
                    d.online_ticks += 1
                    if d.state in (DriverState.EN_ROUTE_TO_PICKUP, DriverState.ON_TRIP):
                        d.active_ticks += 1

            # --- step 2: generate ride requests ----------------------------
            new_specs = self.requests_by_tick.get(tick, [])
            new_requests = []
            for spec in new_specs:
                r = Request.from_spec(spec, self.world.seed_material)
                r.distance_km = city.distance_km(r.origin_zone, r.destination_zone)
                new_requests.append(r)

            # --- step 3: resolve driver state transitions ------------------
            for d in self.drivers.values():
                if d.state == DriverState.EN_ROUTE_TO_PICKUP and d.release_tick == tick:
                    req = self.requests[d.active_request_id]
                    req.state = RequestState.ON_TRIP
                    req.trip_started_tick = tick
                    noise = float(d.rng.lognormal(0.0, config.TRAVEL_NOISE_SIGMA))
                    speed = config.BASE_SPEED_KMH / congestion_mult
                    trip_dist = city.distance_km(req.origin_zone, req.destination_zone)
                    duration = (trip_dist / speed) * 60.0 * noise
                    req.trip_duration_min = duration
                    d.destination_zone = req.destination_zone
                    d.release_tick = tick + max(1, round(duration / config.TICK_MINUTES))
                    d.state = DriverState.ON_TRIP
                elif d.state == DriverState.ON_TRIP and d.release_tick == tick:
                    req = self.requests.pop(d.active_request_id)
                    payout = (1 - config.COMMISSION_RATE) * req.final_price
                    d.gross_earnings += payout
                    d.trips_completed += 1
                    req.state = RequestState.COMPLETED
                    req.completed_tick = tick
                    self.collector.record_request_terminal(req)
                    d.zone = req.destination_zone
                    d.active_request_id = None
                    d.destination_zone = None
                    d.release_tick = None
                    if d.queued_request_id is not None:
                        # Pre-booked via look-ahead dispatch (ETA_OPTIMIZED /
                        # ADVANCED_HEURISTIC): head straight to the queued
                        # pickup instead of going idle, honoring the
                        # commitment even if the shift technically just ended.
                        queued = self.requests.get(d.queued_request_id)
                        if queued is not None and queued.state == RequestState.MATCHED:
                            d.active_request_id = d.queued_request_id
                            d.destination_zone = queued.origin_zone
                            d.release_tick = tick + max(1, round(d.queued_pickup_travel_min / config.TICK_MINUTES))
                            d.state = DriverState.EN_ROUTE_TO_PICKUP
                        d.queued_request_id = None
                        d.queued_pickup_travel_min = None
                        if d.state != DriverState.EN_ROUTE_TO_PICKUP:
                            self._finalize_driver(d, tick)
                    else:
                        self._finalize_driver(d, tick)

            for d in self.drivers.values():
                if d.state == DriverState.OFFLINE and d.shift_start_tick == tick:
                    d.state = DriverState.AVAILABLE
                    d.zone = d.home_zone
                elif d.state == DriverState.AVAILABLE and d.shift_end_tick == tick:
                    d.state = DriverState.OFFLINE

            # --- step 4: marketplace state ----------------------------------
            available_by_zone = self._available_by_zone()
            outstanding_by_zone = self._outstanding_by_zone()

            def imbalance(zone_id: int) -> float:
                return outstanding_by_zone.get(zone_id, 0) / (available_by_zone.get(zone_id, 0) + 1.0)

            # --- step 5+6: surge + price new requests -----------------------
            for r in new_requests:
                surge = self.pricing_engine.surge_for_zone(r.origin_zone, tick, imbalance(r.origin_zone))
                r.surge_multiplier = surge
                r.imbalance_at_request = imbalance(r.origin_zone)
                speed = config.BASE_SPEED_KMH / congestion_mult
                quoted_duration = (r.distance_km / speed) * 60.0
                r.final_price = pricing.base_fare(r.distance_km, quoted_duration) * surge

            # --- step 7: rider accept/reject offer --------------------------
            for r in new_requests:
                w_exp = self.avg_pickup_eta_by_zone.get(r.origin_zone, DEFAULT_AVG_PICKUP_ETA)
                p_accept = behavior.rider_accept_probability(r.beta_price, r.beta_wait, r.surge_multiplier, w_exp)
                u = r.next_uniform()
                if u < p_accept:
                    self.requests[r.id] = r
                else:
                    r.state = RequestState.REJECTED_OFFER
                    self.collector.record_request_terminal(r)

            # --- step 8: dispatch --------------------------------------------
            waiting_requests = sorted(
                (r for r in self.requests.values() if r.state == RequestState.WAITING),
                key=lambda r: (r.created_tick, r.id),
            )
            available_drivers = [d for d in self.drivers.values() if d.state == DriverState.AVAILABLE]
            soon_free_drivers = [
                d for d in self.drivers.values()
                if d.state == DriverState.ON_TRIP
                and d.queued_request_id is None
                and d.release_tick is not None
                and 0 <= (d.release_tick - tick) <= config.DISPATCH_LOOKAHEAD_MIN
            ]
            avg_outstanding = (
                sum(outstanding_by_zone.values()) / config.NUM_ZONES if config.NUM_ZONES else 0.0
            )
            ctx = dispatch_mod.MarketContext(
                tick=tick,
                hour=hour,
                congestion_mult=congestion_mult,
                available_by_zone=available_by_zone,
                outstanding_by_zone=outstanding_by_zone,
                avg_outstanding=avg_outstanding,
                avg_fare_driver_share=self.avg_fare_driver_share_city,
                avg_pickup_eta_min=self.avg_pickup_eta_city,
            )
            matches = dispatch_mod.run_dispatch_tick(
                self.dispatch_policy, waiting_requests, available_drivers, soon_free_drivers, ctx
            )

            # --- step 9: resolve driver acceptance ----------------------------
            for request, driver, eta, dist in matches:
                is_lookahead = driver.state == DriverState.ON_TRIP
                if is_lookahead:
                    assert driver.queued_request_id is None, "queue-slot invariant violated"
                else:
                    assert driver.state == DriverState.AVAILABLE, "dispatch offered a non-AVAILABLE/non-soon-free driver"
                    assert driver.active_request_id is None, "no-double-booking invariant violated"
                driver.assignments_offered += 1
                fare_share = (1 - config.COMMISSION_RATE) * request.final_price
                util = driver.active_ticks / driver.online_ticks if driver.online_ticks > 0 else 0.0
                dest_attr = behavior.destination_attractiveness(
                    request.destination_zone, outstanding_by_zone, avg_outstanding
                )
                p_accept = behavior.driver_accept_probability(
                    fare_share, self.avg_fare_driver_share_city, eta, self.avg_pickup_eta_city, dest_attr, util
                )
                # Normalizers track the average OFFERED eta/fare (not just
                # accepted ones) -- updating only on acceptance creates a
                # self-reinforcing bootstrapping failure (a too-low initial
                # normalizer crushes P_accept, so it never gets evidence to
                # correct itself). Updating on every offer is the fix.
                self.avg_pickup_eta_city = _ema(self.avg_pickup_eta_city, eta)
                self.avg_fare_driver_share_city = _ema(self.avg_fare_driver_share_city, fare_share)

                u = driver.next_uniform()
                if u < p_accept:
                    driver.assignments_accepted += 1
                    request.state = RequestState.MATCHED
                    request.matched_tick = tick
                    request.driver_id = driver.id
                    request.pickup_eta_min = eta
                    request.pickup_distance_km = dist

                    if is_lookahead:
                        # Driver is still finishing their current trip; queue
                        # the pickup rather than transitioning state now (see
                        # step 3's ON_TRIP-completion branch for the handoff).
                        release_in = max(0, driver.release_tick - tick)
                        driver.queued_request_id = request.id
                        driver.queued_pickup_travel_min = max(0.1, eta - release_in)
                    else:
                        driver.state = DriverState.EN_ROUTE_TO_PICKUP
                        driver.active_request_id = request.id
                        driver.destination_zone = request.origin_zone
                        driver.release_tick = tick + max(1, round(eta / config.TICK_MINUTES))

                    self.avg_pickup_eta_by_zone[request.origin_zone] = _ema(
                        self.avg_pickup_eta_by_zone[request.origin_zone], eta
                    )
                # else: driver stays in its current state, request stays WAITING (retried next tick)

            # --- step 10: advance trips (no-op, see module docstring) --------

            # --- step 11: cancellations ---------------------------------------
            for r in list(self.requests.values()):
                if r.state == RequestState.WAITING:
                    elapsed = (tick - r.created_tick) * config.TICK_MINUTES
                    p = behavior.pre_match_abandon_probability(elapsed, r.patience_min)
                    r.n_cancel_checks += 1
                    u = r.next_uniform()
                    if u < p:
                        r.state = RequestState.ABANDONED
                        self.collector.record_request_terminal(r)
                        del self.requests[r.id]
                elif r.state == RequestState.MATCHED:
                    elapsed_pm = (tick - r.matched_tick) * config.TICK_MINUTES
                    p = behavior.post_match_cancel_probability(elapsed_pm, r.patience_min)
                    u = r.next_uniform()
                    if u < p:
                        r.state = RequestState.CANCELLED_POSTMATCH
                        self.collector.record_request_terminal(r)
                        d = self.drivers[r.driver_id]
                        if d.queued_request_id == r.id:
                            # Driver hadn't started heading there yet (still
                            # finishing an earlier trip) -- just drop the
                            # queued pickup, their current trip is unaffected.
                            d.queued_request_id = None
                            d.queued_pickup_travel_min = None
                        elif d.active_request_id == r.id:
                            self._finalize_driver(d, tick)
                            d.active_request_id = None
                            d.destination_zone = None
                            d.release_tick = None
                        del self.requests[r.id]

            # --- step 12: metrics (timeseries snapshot, optional) -------------
            if self.collect_timeseries and tick % self.timeseries_every_ticks == 0:
                self._record_timeseries(tick, hour, available_by_zone, outstanding_by_zone)

        # --- finalize: flush anything still active at horizon end -----------
        for r in list(self.requests.values()):
            self.collector.record_request_terminal(r)
        for d in self.drivers.values():
            self.collector.record_driver_final(d)

        summary = self.collector.compute_summary()
        return SimulationResult(
            scenario=self.scenario.name,
            seed=self.world.seed,
            pricing_policy=self.pricing_policy.value,
            dispatch_policy=self.dispatch_policy.value,
            summary=summary,
            timeseries=getattr(self, "_timeseries", []),
        )

    def _record_timeseries(self, tick, hour, available_by_zone, outstanding_by_zone):
        if not hasattr(self, "_timeseries"):
            self._timeseries = []
        self._timeseries.append(
            {
                "tick": tick,
                "hour": hour,
                "available_drivers": sum(available_by_zone.values()),
                "outstanding_requests": sum(outstanding_by_zone.values()),
                "avg_surge": sum(self.pricing_engine._last_surge.values()) / config.NUM_ZONES,
                "available_by_zone": dict(available_by_zone),
                "outstanding_by_zone": dict(outstanding_by_zone),
            }
        )
