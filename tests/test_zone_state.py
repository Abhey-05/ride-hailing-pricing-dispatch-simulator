from src import config, engine, world, zone_state

SHORT_HORIZON = 240


def _run(seed=0, scenario="NORMAL", horizon=SHORT_HORIZON):
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER,
        config.SCENARIOS[scenario], collect_timeseries=True, timeseries_every_ticks=5,
    )
    eng.run()
    return eng


def test_compute_zone_states_covers_every_zone():
    eng = _run(seed=0)
    states = zone_state.compute_zone_states(eng.collector, eng._timeseries, SHORT_HORIZON)
    assert len(states) == config.NUM_ZONES
    assert {s.zone_id for s in states} == {z.id for z in config.ZONES}


def test_zone_request_counts_sum_to_total_requests():
    eng = _run(seed=1)
    states = zone_state.compute_zone_states(eng.collector, eng._timeseries, SHORT_HORIZON)
    assert sum(s.n_requests for s in states) == len(eng.collector.requests)


def test_supply_shortage_scenario_produces_more_stressed_zones_than_normal():
    """Needs a full simulated day (not the short 4h window) so the
    comparison isn't dominated by whichever scenario happens to start in a
    low-driver-count period -- same reasoning as
    test_engine_invariants.py's demand/supply monotonicity checks."""
    horizon = config.DEFAULT_HORIZON_TICKS
    eng_normal = _run(seed=2, scenario="NORMAL", horizon=horizon)
    eng_shortage = _run(seed=2, scenario="SUPPLY_SHORTAGE", horizon=horizon)
    states_normal = zone_state.compute_zone_states(eng_normal.collector, eng_normal._timeseries, horizon)
    states_shortage = zone_state.compute_zone_states(eng_shortage.collector, eng_shortage._timeseries, horizon)
    avg_ratio_normal = sum(s.supply_demand_ratio for s in states_normal) / len(states_normal)
    avg_ratio_shortage = sum(s.supply_demand_ratio for s in states_shortage) / len(states_shortage)
    assert avg_ratio_shortage <= avg_ratio_normal + 1e-9


def test_worst_zones_sorted_ascending_by_ratio():
    eng = _run(seed=3)
    states = zone_state.compute_zone_states(eng.collector, eng._timeseries, SHORT_HORIZON)
    worst = zone_state.worst_zones(states, n=3)
    assert len(worst) == 3
    ratios = [s.supply_demand_ratio for s in worst]
    assert ratios == sorted(ratios)


def test_zone_states_to_dataframe_has_expected_columns():
    eng = _run(seed=4)
    states = zone_state.compute_zone_states(eng.collector, eng._timeseries, SHORT_HORIZON)
    df = zone_state.zone_states_to_dataframe(states)
    assert "supply_demand_ratio" in df.columns
    assert "status" in df.columns
    assert len(df) == config.NUM_ZONES


def test_explain_zone_returns_nonempty_reasons():
    eng = _run(seed=5)
    states = zone_state.compute_zone_states(eng.collector, eng._timeseries, SHORT_HORIZON)
    city_avg_demand = sum(s.demand_per_min for s in states) / len(states)
    city_avg_avail = sum(s.avg_available_drivers for s in states) / len(states)
    for s in states:
        reasons = zone_state.explain_zone(s, city_avg_demand, city_avg_avail)
        assert len(reasons) >= 1
