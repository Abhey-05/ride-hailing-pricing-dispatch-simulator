from pathlib import Path

from src.real_data import analysis, calibration, metrics
from tests.real_data_fixtures import sample_raw_df

RESULTS_CSV = Path(__file__).parent.parent / "results" / "results.csv"


def _real_overview_and_funnel():
    df = sample_raw_df()
    df, _ = metrics.clean_timestamps(df)
    df, _ = metrics.derive_metrics(df)
    return analysis.dataset_overview(df), analysis.operational_funnel(df)


def test_status_thresholds():
    assert calibration._status(5.0) == "close"
    assert calibration._status(-5.0) == "close"
    assert calibration._status(15.0) == "close"
    assert calibration._status(25.0) == "needs_calibration"
    assert calibration._status(40.0) == "needs_calibration"
    assert calibration._status(50.0) == "significant_mismatch"
    assert calibration._status(None) == "not_comparable"


def test_load_simulator_baseline_missing_file_returns_none(tmp_path):
    missing = tmp_path / "no_results.csv"
    assert calibration.load_simulator_baseline(missing) is None


def test_load_simulator_baseline_reads_real_results_csv():
    if not RESULTS_CSV.exists():
        return  # results.csv is a generated artifact; skip if not present
    baseline = calibration.load_simulator_baseline(RESULTS_CSV)
    assert baseline is not None
    assert baseline["policy_label"] == "BASIC_SURGE + NEAREST_DRIVER"
    assert 0 <= baseline["cancellation_rate"] <= 1
    assert baseline["p90_wait_min"] > 0


def test_compare_to_simulator_returns_empty_when_no_baseline():
    overview, funnel = _real_overview_and_funnel()
    result = calibration.compare_to_simulator(overview, funnel, None)
    assert result == []


def test_compare_to_simulator_reassignment_row_is_not_modeled():
    overview, funnel = _real_overview_and_funnel()
    fake_baseline = {
        "p90_wait_min": 10.0, "median_wait_min": 2.0, "cancellation_rate": 0.2,
        "completion_rate": 0.55, "avg_pickup_distance_km": 1.4,
        "policy_label": "X", "scenario": "NORMAL",
    }
    rows = calibration.compare_to_simulator(overview, funnel, fake_baseline)
    reassignment_row = next(r for r in rows if r["metric"] == "Reassignment rate")
    assert reassignment_row["status"] == "not_modeled"
    assert reassignment_row["simulator_value"] is None


def test_compare_to_simulator_computes_relative_diff_correctly():
    overview, funnel = _real_overview_and_funnel()
    fake_baseline = {
        "p90_wait_min": 10.0, "median_wait_min": 2.0, "cancellation_rate": overview["cancellation_rate"],
        "completion_rate": overview["completion_rate"], "avg_pickup_distance_km": 1.4,
        "policy_label": "X", "scenario": "NORMAL",
    }
    rows = calibration.compare_to_simulator(overview, funnel, fake_baseline)
    cancel_row = next(r for r in rows if r["metric"] == "Cancellation rate")
    # real == simulator by construction here -> 0% relative diff -> close
    assert cancel_row["status"] == "close"
    assert abs(cancel_row["relative_diff_pct"]) < 0.01
