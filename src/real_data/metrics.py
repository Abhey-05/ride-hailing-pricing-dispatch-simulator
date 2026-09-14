"""
Timestamp cleaning + derived-metric computation for the Real-World
Validation module.

Nothing here is silently dropped: clean_timestamps/derive_metrics return a
report dict alongside the dataframe, and every exclusion the downstream
analysis applies is counted and surfaced on the dashboard page (Dataset
Overview -> Data Quality), per the "do not silently drop data" requirement.
"""
from __future__ import annotations

import pandas as pd

TIMESTAMP_COLUMNS: tuple[str, ...] = (
    "order_time",
    "allot_time",
    "accept_time",
    "pickup_time",
    "delivered_time",
    "cancelled_time",
)

# An end-to-end duration beyond this is treated as an implausible data entry
# (rider forgot to close out the order, clock skew, etc.) rather than a
# real 4+ hour food-delivery trip. Chosen from the data itself: the 99.5th
# percentile of end-to-end time in the supplied dataset is ~92 min, so 240
# min (2.6x that) comfortably separates "slow but real" from "broken row"
# without an arbitrary round-number guess. Excluded rows are reported, not
# dropped from the dataframe.
IMPLAUSIBLE_DURATION_MIN = 240.0


def clean_timestamps(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Parse every timestamp column present. Returns (df, report) where
    report counts values that failed to parse (excluding values that were
    already null in the source -- a genuinely missing pickup_time is a data
    fact, not a parse failure)."""
    df = df.copy()
    report: dict[str, int] = {}
    for col in TIMESTAMP_COLUMNS:
        if col not in df.columns:
            continue
        raw_non_null = df[col].notna().sum()
        parsed = pd.to_datetime(df[col], errors="coerce")
        parse_failures = int(raw_non_null - parsed.notna().sum())
        report[f"{col}_parse_failures"] = parse_failures
        df[col] = parsed
    return df, report


def derive_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Add derived delay/outcome columns. Assumes clean_timestamps() has
    already been applied (timestamp columns are real datetimes, not
    strings). Returns (df, report) -- report counts duplicates dropped and
    rows flagged invalid for *timing* analysis specifically; those rows are
    NOT removed from the returned dataframe (funnel counts, cancellation
    rate, and reassignment analysis still use them), only flagged via the
    `timing_valid` column so callers can filter deliberately per-section."""
    report: dict = {"rows_before": len(df)}

    dup_rows = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()
    report["duplicate_rows_dropped"] = dup_rows
    report["rows_after_dedup"] = len(df)

    def _minutes(a: pd.Series, b: pd.Series) -> pd.Series:
        return (a - b).dt.total_seconds() / 60.0

    df["allotment_delay_min"] = _minutes(df["allot_time"], df["order_time"])
    df["acceptance_delay_min"] = _minutes(df["accept_time"], df["allot_time"])
    df["pickup_delay_min"] = _minutes(df["pickup_time"], df["accept_time"])
    df["last_mile_delivery_time_min"] = _minutes(df["delivered_time"], df["pickup_time"])
    df["end_to_end_time_min"] = _minutes(df["delivered_time"], df["order_time"])
    df["order_to_pickup_time_min"] = _minutes(df["pickup_time"], df["order_time"])

    df["cancellation_flag"] = (df["cancelled"] == 1).astype(int)
    df["delivery_success"] = ((df["cancelled"] == 0) & df["delivered_time"].notna()).astype(int)
    # No row in the inspected dataset has delivered_time null with
    # cancelled==0 (verified: 0 such rows) -- this flag is still computed
    # generally rather than assumed always-zero, in case a future export
    # differs.
    df["undelivered_flag"] = ((df["cancelled"] == 0) & df["delivered_time"].isna()).astype(int)
    df["reassignment_flag"] = (df.get("reassigned_order") == 1).astype(int) if "reassigned_order" in df.columns else 0

    # Timing validity: negative deltas mean an out-of-order timestamp
    # (accept before allot, pickup before accept); NaN deltas mean a stage
    # was skipped (e.g. cancelled before that stage) and simply don't count
    # against validity. An implausible total duration invalidates the whole
    # row for delay-distribution purposes.
    delay_cols = ["allotment_delay_min", "acceptance_delay_min", "pickup_delay_min", "last_mile_delivery_time_min"]
    has_negative = pd.Series(False, index=df.index)
    for c in delay_cols:
        has_negative = has_negative | (df[c] < 0).fillna(False)
    implausible = (df["end_to_end_time_min"] > IMPLAUSIBLE_DURATION_MIN).fillna(False)

    df["timing_valid"] = ~(has_negative | implausible)
    report["invalid_timestamp_order_rows"] = int(has_negative.sum())
    report["implausible_duration_rows"] = int(implausible.sum())
    report["rows_excluded_from_timing_analysis"] = int((has_negative | implausible).sum())
    report["rows_valid_for_timing_analysis"] = int(df["timing_valid"].sum())

    return df, report
