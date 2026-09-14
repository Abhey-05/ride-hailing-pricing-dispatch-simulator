import pandas as pd

from src.real_data import metrics
from tests.real_data_fixtures import sample_raw_df


def _cleaned_and_derived():
    df = sample_raw_df()
    df, ts_report = metrics.clean_timestamps(df)
    df, derive_report = metrics.derive_metrics(df)
    return df, ts_report, derive_report


def test_clean_timestamps_parses_all_timestamp_columns():
    df = sample_raw_df()
    df, report = metrics.clean_timestamps(df)
    for col in ["order_time", "allot_time", "accept_time", "pickup_time", "delivered_time"]:
        assert pd.api.types.is_datetime64_any_dtype(df[col])


def test_clean_timestamps_preserves_genuine_nulls_not_parse_failures():
    df = sample_raw_df()
    df, report = metrics.clean_timestamps(df)
    # accept_time is genuinely null for the cancelled order (order_id=13) --
    # that's a missing value, not a parse failure.
    assert report["accept_time_parse_failures"] == 0
    assert df["accept_time"].isna().sum() == 1


def test_derive_metrics_drops_exact_duplicate_row():
    df, ts_report, derive_report = _cleaned_and_derived()
    assert derive_report["duplicate_rows_dropped"] == 1
    assert derive_report["rows_after_dedup"] == derive_report["rows_before"] - 1


def test_derive_metrics_computes_expected_delay_columns():
    df, _, _ = _cleaned_and_derived()
    for col in [
        "allotment_delay_min", "acceptance_delay_min", "pickup_delay_min",
        "last_mile_delivery_time_min", "end_to_end_time_min", "order_to_pickup_time_min",
    ]:
        assert col in df.columns


def test_cancellation_flag_matches_cancelled_column():
    df, _, _ = _cleaned_and_derived()
    assert (df["cancellation_flag"] == df["cancelled"]).all()


def test_delivery_success_is_zero_for_cancelled_order():
    df, _, _ = _cleaned_and_derived()
    cancelled_row = df[df["order_id"] == 13].iloc[0]
    assert cancelled_row["delivery_success"] == 0
    assert cancelled_row["cancellation_flag"] == 1


def test_delivery_success_is_one_for_delivered_order():
    df, _, _ = _cleaned_and_derived()
    delivered_row = df[df["order_id"] == 1].iloc[0]
    assert delivered_row["delivery_success"] == 1


def test_reassignment_flag_true_only_for_flagged_order():
    df, _, _ = _cleaned_and_derived()
    assert df.loc[df["order_id"] == 14, "reassignment_flag"].iloc[0] == 1
    assert df.loc[df["order_id"] == 1, "reassignment_flag"].iloc[0] == 0
    assert df["reassignment_flag"].sum() == 1


def test_timing_valid_false_for_negative_delay_row():
    df, _, _ = _cleaned_and_derived()
    # order_id=15 has accept_time before allot_time
    assert df.loc[df["order_id"] == 15, "timing_valid"].iloc[0] == False  # noqa: E712


def test_timing_valid_false_for_implausible_duration_row():
    df, _, _ = _cleaned_and_derived()
    # order_id=16 has an ~8-hour end-to-end duration
    assert df.loc[df["order_id"] == 16, "timing_valid"].iloc[0] == False  # noqa: E712


def test_timing_valid_true_for_normal_row():
    df, _, _ = _cleaned_and_derived()
    assert df.loc[df["order_id"] == 1, "timing_valid"].iloc[0] == True  # noqa: E712


def test_derive_metrics_report_counts_invalid_rows_correctly():
    _, _, derive_report = _cleaned_and_derived()
    assert derive_report["invalid_timestamp_order_rows"] == 1  # order_id=15
    assert derive_report["implausible_duration_rows"] == 1  # order_id=16
    assert derive_report["rows_excluded_from_timing_analysis"] == 2


def test_missing_data_handling_does_not_crash_derive_metrics():
    # cancelled order (order_id=13) has NaT for accept/pickup/delivered --
    # derive_metrics must not raise on the resulting NaN delay values.
    df, _, _ = _cleaned_and_derived()
    cancelled_row = df[df["order_id"] == 13].iloc[0]
    assert pd.isna(cancelled_row["end_to_end_time_min"])
    assert pd.isna(cancelled_row["last_mile_delivery_time_min"])
