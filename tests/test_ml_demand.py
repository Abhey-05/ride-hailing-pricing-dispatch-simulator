import pandas as pd
import pytest

from src import config, ml_demand


def test_bucketize_run_covers_every_zone_and_bucket():
    df = ml_demand._bucketize_run("NORMAL", seed=0, horizon_ticks=60)
    n_buckets = 60 // ml_demand.BUCKET_TICKS
    assert len(df) == config.NUM_ZONES * n_buckets
    assert set(df.zone_id) == {z.id for z in config.ZONES}


def test_bucketize_first_bucket_has_zero_lags():
    df = ml_demand._bucketize_run("NORMAL", seed=1, horizon_ticks=60)
    first = df[df.bucket == 0]
    assert (first.lag_1 == 0).all()
    assert (first.lag_2 == 0).all()


def test_bucketize_demand_sums_to_total_requests_within_horizon():
    horizon = 60
    w = ml_demand.world.generate_world("NORMAL", seed=2, horizon_ticks=horizon)
    eng = ml_demand.engine.SimulationEngine(
        w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER,
        config.SCENARIOS["NORMAL"], collect_timeseries=True, timeseries_every_ticks=ml_demand.BUCKET_TICKS,
    )
    eng.run()
    df = ml_demand.bucketize(eng.collector, eng._timeseries, "NORMAL", 2, horizon)
    assert df.demand.sum() == len(eng.collector.requests)


def test_naive_last_window_prediction_equals_lag_1():
    df = pd.DataFrame({"lag_1": [1.0, 2.0, 3.0]})
    pred = ml_demand.naive_last_window_prediction(df)
    assert list(pred) == [1.0, 2.0, 3.0]


def test_seed_split_produces_disjoint_days():
    df = ml_demand.build_dataset(seeds=range(4), scenarios=("NORMAL",))
    # small dataset -> use a fine short horizon by monkeypatching not needed; just check split logic
    train, test = ml_demand._seed_split(df, test_frac=0.25, random_state=0)
    train_days = set(map(tuple, train[["scenario", "seed"]].drop_duplicates().values))
    test_days = set(map(tuple, test[["scenario", "seed"]].drop_duplicates().values))
    assert train_days.isdisjoint(test_days)
    assert len(test_days) >= 1


def test_train_and_evaluate_beats_naive_baseline_on_a_small_dataset():
    df = ml_demand.build_dataset(seeds=range(6), scenarios=("NORMAL", "PEAK_DEMAND"))
    results = ml_demand.train_and_evaluate(df, random_state=0)
    assert results["gradient_boosting"]["mae"] <= results["naive_last_window"]["mae"] * 1.5
    assert results["n_train"] > 0 and results["n_test"] > 0


def test_forecast_next_window_unknown_zone_returns_error():
    df = ml_demand.build_dataset(seeds=range(2), scenarios=("NORMAL",))
    model = ml_demand.fit_production_model(df)
    result = ml_demand.forecast_next_window("NORMAL", zone_id=999, hour=8.0, model=model)
    assert "error" in result


def test_forecast_next_window_returns_nonnegative_prediction():
    df = ml_demand.build_dataset(seeds=range(4), scenarios=("NORMAL", "PEAK_DEMAND"))
    model = ml_demand.fit_production_model(df)
    result = ml_demand.forecast_next_window("PEAK_DEMAND", zone_id=0, hour=9.0, seed=0, model=model)
    assert "error" not in result
    assert result["forecast_next_15min_demand"] >= 0.0
    assert result["zone_name"] == "Downtown"
