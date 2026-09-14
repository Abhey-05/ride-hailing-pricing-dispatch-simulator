import json

from src.real_data import analysis, metrics
from tests.real_data_fixtures import sample_raw_df


def _processed_df():
    df = sample_raw_df()
    df, _ = metrics.clean_timestamps(df)
    df, _ = metrics.derive_metrics(df)
    return df


def test_dataset_overview_counts_and_rates():
    df = _processed_df()
    overview = analysis.dataset_overview(df)
    assert overview["row_count"] == len(df)
    assert overview["unique_riders"] == 6
    # 1 cancelled order (order_id=13) out of 16 rows (before dedup happened
    # inside derive_metrics, which already ran)
    assert overview["cancellation_rate"] == round(1 / len(df), 4)


def test_operational_funnel_stage_order_and_monotonic_counts():
    df = _processed_df()
    funnel = analysis.operational_funnel(df)
    stage_names = [s["stage"] for s in funnel]
    assert stage_names == ["Order placed", "Allotted", "Accepted", "Picked up", "Delivered"]
    counts = [s["count"] for s in funnel]
    # funnel counts must be non-increasing (can't pick up more than accepted)
    assert counts == sorted(counts, reverse=True)


def test_operational_funnel_delivered_count_matches_non_cancelled():
    df = _processed_df()
    funnel = analysis.operational_funnel(df)
    delivered = next(s for s in funnel if s["stage"] == "Delivered")
    assert delivered["count"] == int((df["cancelled"] == 0).sum())


def test_delay_diagnostics_excludes_invalid_timing_rows():
    df = _processed_df()
    diagnostics = analysis.delay_diagnostics(df)
    # "Order -> Delivery (end-to-end)" percentiles are computed only over
    # timing_valid rows -- the implausible-duration row (order_id=16, ~8hr)
    # must not appear, so the max shouldn't be anywhere near 480 min.
    e2e = diagnostics["Order -> Delivery (end-to-end)"]
    assert e2e["p90"] is not None
    assert e2e["p90"] < 100  # sanity: nowhere near the 480-min outlier


def test_reassignment_analysis_rate_and_segments():
    df = _processed_df()
    r = analysis.reassignment_analysis(df)
    assert r["reassigned"]["n_orders"] == 1
    assert r["not_reassigned"]["n_orders"] == len(df) - 1
    assert r["methods"] == {"auto": 1}


def test_distance_analysis_returns_bucket_lists():
    df = _processed_df()
    d = analysis.distance_analysis(df)
    assert "first_mile_distance_buckets" in d
    assert "last_mile_distance_buckets" in d
    total_in_buckets = sum(b["n_orders"] for b in d["first_mile_distance_buckets"])
    assert total_in_buckets == len(df)


def test_rider_segmentation_covers_all_riders_no_id_leak():
    df = _processed_df()
    segments = analysis.rider_segmentation(df)
    assert sum(s["n_riders"] for s in segments) == df["rider_id"].nunique()
    # privacy: no segment record may contain a raw rider_id anywhere
    blob = json.dumps(segments)
    assert "101" not in blob.replace("n_riders", "").replace("n_orders", "")  # loose smoke check
    for s in segments:
        assert "rider_id" not in s


def test_time_of_day_analysis_covers_all_orders():
    df = _processed_df()
    tod = analysis.time_of_day_analysis(df)
    assert sum(t["n_orders"] for t in tod) == len(df)
    hours = [t["hour"] for t in tod]
    assert hours == sorted(hours)


def test_analyze_data_output_has_no_raw_order_or_rider_ids():
    df = _processed_df()
    result = analysis.analyze_data(df)
    blob = json.dumps(result, default=str)
    assert "order_id" not in blob
    assert "rider_id" not in blob


def test_analyze_data_is_json_serializable():
    df = _processed_df()
    result = analysis.analyze_data(df)
    json.dumps(result, default=str)  # must not raise


def test_analyze_data_returns_all_expected_top_level_keys():
    df = _processed_df()
    result = analysis.analyze_data(df)
    assert set(result.keys()) == {
        "overview", "funnel", "delay_diagnostics", "reassignment",
        "distance", "rider_segments", "time_of_day", "opportunities",
    }


def test_generate_opportunities_never_claims_causation():
    df = _processed_df()
    result = analysis.analyze_data(df)
    blob = json.dumps(result["opportunities"]).lower()
    # the whole point of this module: never assert a causal claim
    for banned in [" caused ", " causes ", " will reduce ", " will increase "]:
        assert banned not in blob
