import pandas as pd
import pytest

from src.real_data import loader
from tests.real_data_fixtures import sample_raw_df


def test_validate_schema_reports_all_expected_columns_present():
    df = sample_raw_df()
    report = loader.validate_schema(df)
    assert report.columns_missing == []
    assert report.row_count == len(df)


def test_validate_schema_reports_missing_columns_without_raising():
    df = sample_raw_df().drop(columns=["reassignment_method", "session_time"])
    report = loader.validate_schema(df)
    assert set(report.columns_missing) == {"reassignment_method", "session_time"}
    assert "reassignment_method" not in report.columns_present


def test_validate_schema_reports_extra_columns():
    df = sample_raw_df()
    df["some_new_field"] = 1
    report = loader.validate_schema(df)
    assert "some_new_field" in report.extra_columns


def test_validate_schema_detects_duplicate_order_ids():
    df = sample_raw_df()  # last row duplicates order_id=1
    report = loader.validate_schema(df)
    assert report.duplicate_order_ids == 1


def test_validate_schema_null_counts_match_actual_nulls():
    df = sample_raw_df()
    report = loader.validate_schema(df)
    assert report.null_counts["accept_time"] == df["accept_time"].isnull().sum()


def test_load_real_world_data_missing_file_raises_clear_error(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match="gitignored"):
        loader.load_real_world_data(missing)


def test_load_real_world_data_reads_csv(tmp_path):
    df = sample_raw_df()
    path = tmp_path / "sample.csv"
    df.to_csv(path, index=False)
    loaded = loader.load_real_world_data(path)
    assert len(loaded) == len(df)


def test_load_real_world_data_unsupported_extension_raises(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("not a real dataset")
    with pytest.raises(ValueError):
        loader.load_real_world_data(path)


def test_schema_report_to_dict_is_json_serializable():
    import json

    df = sample_raw_df()
    report = loader.validate_schema(df)
    json.dumps(report.to_dict())  # must not raise
