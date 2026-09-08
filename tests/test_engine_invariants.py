import math

from src import config, world, engine

SHORT_HORIZON = 240  # 4 simulated hours -- fast enough for a test suite


def run(seed=0, scenario="NORMAL", pricing=config.PricingPolicy.BASIC_SURGE,
        dispatch=config.DispatchPolicy.NEAREST_DRIVER, horizon=SHORT_HORIZON):
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon)
    eng = engine.SimulationEngine(w, pricing, dispatch, config.SCENARIOS[scenario])
    return eng.run(), w, eng


def test_reproducibility_same_seed_identical_summary():
    res1, _, _ = run(seed=7)
    res2, _, _ = run(seed=7)
    assert res1.summary == res2.summary


def test_different_seed_generally_differs():
    res1, _, _ = run(seed=1)
    res2, _, _ = run(seed=2)
    assert res1.summary != res2.summary


def test_every_request_accounted_for_exactly_once():
    res, w, eng = run(seed=3)
    assert len(eng.collector.requests) == len(w.request_specs)
    ids_seen = {r.id for r in eng.collector.requests}
    assert len(ids_seen) == len(w.request_specs)  # no duplicates


def test_completed_never_exceeds_requested():
    res, w, eng = run(seed=4)
    assert res.summary["n_completed"] <= res.summary["n_requests"]
    assert res.summary["n_requests"] == len(w.request_specs)


def test_driver_earnings_nonnegative_and_utilization_bounded():
    res, w, eng = run(seed=5)
    for d in eng.collector.drivers:
        assert d.gross_earnings >= 0
        if d.online_minutes > 0:
            util = d.active_minutes / d.online_minutes
            assert -1e-9 <= util <= 1.0 + 1e-9


def test_no_negative_prices():
    res, w, eng = run(seed=6)
    for r in eng.collector.requests:
        assert r.final_price >= 0


def test_no_double_booking_including_lookahead_policies():
    """engine.py step 9 asserts a driver is AVAILABLE (or a queue-eligible
    soon-to-be-free ON_TRIP driver with no existing queue slot) before every
    assignment -- an AssertionError here would mean a driver was double-
    booked. Exercise the two look-ahead policies specifically, since they are
    the only ones that can offer a still-busy (ON_TRIP) driver."""
    for policy in (config.DispatchPolicy.ETA_OPTIMIZED, config.DispatchPolicy.ADVANCED_HEURISTIC):
        res, w, eng = run(seed=8, dispatch=policy, horizon=SHORT_HORIZON * 2)
        assert res.summary["n_completed"] >= 0  # reaching here means no AssertionError fired


def test_nearest_driver_minimizes_pickup_distance_among_available_only_policies():
    """Validation Plan check #5 (refined during Phase 4): among policies that
    only ever consider currently-AVAILABLE drivers (NEAREST_DRIVER,
    DRIVER_EARNINGS_AWARE, MARKETPLACE_AWARE), NEAREST_DRIVER greedily picks
    the minimum-distance candidate every time, so it can never do worse than
    the other two. The two look-ahead policies (ETA_OPTIMIZED,
    ADVANCED_HEURISTIC) are explicitly exempt: they also consider drivers who
    are about to free up nearby, which can legitimately beat pure-nearest on
    realized pickup distance -- this was discovered empirically in Phase 4
    and is a real, documented finding (see CHANGELOG.md), not a bug."""
    avg_dist = {}
    for policy in config.DispatchPolicy:
        res, w, eng = run(seed=42, dispatch=policy)
        avg_dist[policy] = res.summary["avg_pickup_distance_km"]
    available_only = [
        avg_dist[config.DispatchPolicy.DRIVER_EARNINGS_AWARE],
        avg_dist[config.DispatchPolicy.MARKETPLACE_AWARE],
    ]
    for d in available_only:
        assert avg_dist[config.DispatchPolicy.NEAREST_DRIVER] <= d + 1e-9


def test_demand_increase_increases_wait_time_fixed_supply():
    """Validation check #1: more demand, same supply -> worse (or equal) P90 wait.
    Needs a full simulated day (not the short 4h window) so every scenario has
    enough completed trips across day/night cycles for a stable P90 estimate."""
    res_low, _, _ = run(seed=10, scenario="LOW_DEMAND", horizon=config.DEFAULT_HORIZON_TICKS)
    res_normal, _, _ = run(seed=10, scenario="NORMAL", horizon=config.DEFAULT_HORIZON_TICKS)
    res_peak, _, _ = run(seed=10, scenario="PEAK_DEMAND", horizon=config.DEFAULT_HORIZON_TICKS)
    assert res_low.summary["p90_wait_min"] <= res_normal.summary["p90_wait_min"] + 1e-6
    assert res_normal.summary["p90_wait_min"] <= res_peak.summary["p90_wait_min"] + 1e-6


def test_supply_increase_decreases_wait_time_fixed_demand():
    """Validation check #4: more supply, same demand -> better (or equal) P90 wait."""
    res_shortage, _, _ = run(seed=11, scenario="SUPPLY_SHORTAGE", horizon=config.DEFAULT_HORIZON_TICKS)
    res_normal, _, _ = run(seed=11, scenario="NORMAL", horizon=config.DEFAULT_HORIZON_TICKS)
    assert res_normal.summary["p90_wait_min"] <= res_shortage.summary["p90_wait_min"] + 1e-6


def test_pricing_does_not_change_fleet_supply():
    """Validation check #2: pricing policy must not retroactively change how
    many drivers are online (supply is exogenous / policy-independent)."""
    results = []
    for policy in config.PricingPolicy:
        res, w, eng = run(seed=12, pricing=policy)
        results.append(res.summary["n_online_drivers"])
    assert len(set(results)) == 1, f"driver count varied across pricing policies: {results}"
