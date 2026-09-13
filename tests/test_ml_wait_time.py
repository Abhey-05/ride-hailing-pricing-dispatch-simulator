import numpy as np

from src import config, ml_wait_time


def test_build_dataset_only_includes_completed_trips():
    df = ml_wait_time.build_dataset(seeds=range(3), scenarios=("NORMAL",))
    assert (df.wait_min >= 0).all()
    assert not df.wait_min.isna().any()


def test_naive_distance_eta_prediction_matches_formula():
    import pandas as pd
    df = pd.DataFrame({"distance_km": [14.0, 28.0]})
    pred = ml_wait_time.naive_distance_eta_prediction(df, assumed_speed_kmh=28.0)
    assert list(pred) == [30.0, 60.0]


def test_train_and_evaluate_beats_naive_baseline_on_a_small_dataset():
    df = ml_wait_time.build_dataset(seeds=range(6), scenarios=("NORMAL", "PEAK_DEMAND"))
    results = ml_wait_time.train_and_evaluate(df, random_state=0)
    assert results["gradient_boosting"]["mae"] < results["naive_distance_eta"]["mae"]
    assert results["n_train"] > 0 and results["n_test"] > 0


def test_predict_wait_time_unknown_zone_returns_error():
    df = ml_wait_time.build_dataset(seeds=range(2), scenarios=("NORMAL",))
    model = ml_wait_time.fit_production_model(df)
    result = ml_wait_time.predict_wait_time("NORMAL", zone_id=999, hour=8.0, model=model)
    assert "error" in result


def test_predict_wait_time_unknown_segment_returns_error():
    df = ml_wait_time.build_dataset(seeds=range(2), scenarios=("NORMAL",))
    model = ml_wait_time.fit_production_model(df)
    result = ml_wait_time.predict_wait_time("NORMAL", zone_id=0, hour=8.0, segment="not_a_segment", model=model)
    assert "error" in result


def test_predict_wait_time_returns_nonnegative_prediction():
    df = ml_wait_time.build_dataset(seeds=range(6), scenarios=("NORMAL", "PEAK_DEMAND"))
    model = ml_wait_time.fit_production_model(df)
    result = ml_wait_time.predict_wait_time("PEAK_DEMAND", zone_id=0, hour=9.0, segment="normal", seed=0, model=model)
    assert "error" not in result
    assert result["predicted_wait_min"] >= 0.0
    assert result["naive_distance_only_eta_min"] >= 0.0
    assert result["zone_name"] == "Downtown"
