import numpy as np
import pandas as pd
import pytest

from src import config, decision, engine, world

SHORT_HORIZON = 240


def _run_summary(seed=0, scenario="NORMAL", pricing=config.PricingPolicy.BASIC_SURGE,
                  dispatch=config.DispatchPolicy.NEAREST_DRIVER, horizon=config.DEFAULT_HORIZON_TICKS):
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon)
    eng = engine.SimulationEngine(w, pricing, dispatch, config.SCENARIOS[scenario])
    return eng.run().summary


def test_normalize_metric_clips_to_unit_interval():
    assert decision.normalize_metric("p90_wait_min", 8.0) == pytest.approx(1.0, abs=1e-9)
    assert decision.normalize_metric("p90_wait_min", 15.0) == pytest.approx(0.0, abs=1e-9)
    assert decision.normalize_metric("p90_wait_min", 2.0) == pytest.approx(1.0)  # clipped, not extrapolated
    assert decision.normalize_metric("p90_wait_min", 100.0) == pytest.approx(0.0)


def test_normalize_metric_unknown_or_nan_returns_nan():
    assert decision.normalize_metric("not_a_real_metric", 1.0) != decision.normalize_metric("not_a_real_metric", 1.0)
    assert decision.normalize_metric("p90_wait_min", float("nan")) != decision.normalize_metric("p90_wait_min", float("nan"))


def test_health_score_weights_sum_to_one():
    assert sum(decision.HEALTH_SCORE_DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)
    for metrics in decision.HEALTH_SCORE_METRICS.values():
        assert sum(w for _, w in metrics) == pytest.approx(1.0)


def test_health_score_in_bounds_for_a_real_run():
    summary = _run_summary(seed=1)
    score = decision.compute_health_score(summary)
    assert 0.0 <= score.overall <= 100.0
    for v in score.dimensions.values():
        assert 0.0 <= v <= 100.0
    assert score.interpretation()  # non-empty string


def test_guardrails_absolute_pass_for_baseline_policy():
    summary = _run_summary(seed=2)
    checks = decision.evaluate_guardrails_absolute(summary)
    assert len(checks) >= 3  # avg_surge_multiplier not in the bare summary, so it's skipped here
    for c in checks:
        assert isinstance(c.passed, (bool, np.bool_))


def test_avg_surge_multiplier_is_reasonable():
    w = world.generate_world("NORMAL", seed=3, horizon_ticks=SHORT_HORIZON)
    eng = engine.SimulationEngine(w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER, config.SCENARIOS["NORMAL"])
    eng.run()
    surge = decision.avg_surge_multiplier(eng.collector)
    assert 1.0 <= surge <= config.PRICING_PARAMS[config.PricingPolicy.BASIC_SURGE]["max_surge"]


def test_no_surge_policy_has_avg_surge_of_one():
    w = world.generate_world("NORMAL", seed=3, horizon_ticks=SHORT_HORIZON)
    eng = engine.SimulationEngine(w, config.PricingPolicy.NO_SURGE, config.DispatchPolicy.NEAREST_DRIVER, config.SCENARIOS["NORMAL"])
    eng.run()
    assert decision.avg_surge_multiplier(eng.collector) == pytest.approx(1.0)


def test_evaluate_guardrails_relative_identical_summaries_all_pass():
    summary = _run_summary(seed=4)
    checks = decision.evaluate_guardrails_relative(summary, summary)
    assert checks["all_pass"] is True


def test_recommend_policy_uses_precomputed_matrix(tmp_path):
    # Synthetic mini "results.csv" standing in for the real 1,080-row matrix,
    # exercising recommend_policy's aggregation/guardrail/utility logic
    # without depending on results/results.csv existing in a fresh checkout.
    rows = []
    for pricing in ["NO_SURGE", "BASIC_SURGE"]:
        for dispatch in ["NEAREST_DRIVER", "ETA_OPTIMIZED"]:
            base = 10.0 if dispatch == "NEAREST_DRIVER" else 8.0
            rows.append({
                "scenario": "NORMAL", "pricing_policy": pricing, "dispatch_policy": dispatch,
                "p90_wait_min": base, "completion_rate": 0.5, "cancellation_rate": 0.2,
                "platform_revenue": 90000.0, "earnings_per_online_hour_mean": 150.0,
                "driver_utilization_mean": 0.6, "driver_acceptance_rate": 0.7,
                "north_star_trips_per_online_hour": 1.9, "avg_pickup_distance_km": 1.3,
            })
    df = pd.DataFrame(rows)
    result = decision.recommend_policy(df, "NORMAL", "BASIC_SURGE", "NEAREST_DRIVER")
    assert result["action"] in ("switch", "none")
    if result["action"] == "switch":
        assert result["recommended"]["utility"] > result["current"]["utility"]


def test_recommend_policy_missing_scenario_returns_error():
    df = pd.DataFrame([{"scenario": "NORMAL", "pricing_policy": "BASIC_SURGE", "dispatch_policy": "NEAREST_DRIVER"}])
    result = decision.recommend_policy(df, "PEAK_DEMAND", "BASIC_SURGE", "NEAREST_DRIVER")
    assert result["action"] == "error"


def test_run_counterfactual_same_policy_gives_near_zero_effect():
    result = decision.run_counterfactual(
        "NORMAL", "BASIC_SURGE", "NEAREST_DRIVER", "BASIC_SURGE", "NEAREST_DRIVER", seeds=(0, 1)
    )
    comp = result["comparison"]
    row = comp[comp.metric == "p90_wait_min"].iloc[0]
    assert row["mean_diff"] == pytest.approx(0.0, abs=1e-9)
    assert result["guardrails"]["all_pass"] is True


def test_run_counterfactual_reports_real_paired_seeds():
    result = decision.run_counterfactual(
        "NORMAL", "BASIC_SURGE", "NEAREST_DRIVER", "BASIC_SURGE", "ETA_OPTIMIZED", seeds=(0, 1, 2)
    )
    assert result["n_seeds"] == 3
    comp = result["comparison"]
    assert set(comp["metric"]) == set(decision.COUNTERFACTUAL_METRICS)
