"""
Data ingestion + schema validation for the Real-World Validation module.

Deliberately dumb: loads whatever is on disk and reports what it actually
found, rather than assuming the dataset matches a spec. See
docs/REAL_DATA_VALIDATION.md for the inspection this was built against
(450,000 rows, 20 columns, Jan 26 - Feb 6 2021, 19,537 riders, one food-
delivery order per row).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Columns actually present in the supplied Rider-Info.csv, confirmed by
# direct inspection (not assumed from the task description). A dataset
# missing any of these will still load -- validate_schema() reports exactly
# what's missing rather than raising, so the pipeline degrades gracefully
# instead of hard-failing on a slightly different export.
EXPECTED_COLUMNS: tuple[str, ...] = (
    "order_time",
    "order_id",
    "order_date",
    "allot_time",
    "accept_time",
    "pickup_time",
    "delivered_time",
    "rider_id",
    "first_mile_distance",
    "last_mile_distance",
    "alloted_orders",
    "delivered_orders",
    "cancelled",
    "undelivered_orders",
    "lifetime_order_count",
    "reassignment_method",
    "reassignment_reason",
    "reassigned_order",
    "session_time",
    "cancelled_time",
)

TIMESTAMP_COLUMNS: tuple[str, ...] = (
    "order_time",
    "order_date",
    "allot_time",
    "accept_time",
    "pickup_time",
    "delivered_time",
    "cancelled_time",
)


@dataclass
class SchemaReport:
    """Pure inspection result -- no mutation, no exclusion decisions."""

    row_count: int
    columns_present: list[str]
    columns_missing: list[str]
    extra_columns: list[str]
    dtypes: dict[str, str]
    null_counts: dict[str, int]
    null_pct: dict[str, float]
    duplicate_rows: int
    duplicate_order_ids: int

    def to_dict(self) -> dict:
        return {
            "row_count": self.row_count,
            "columns_present": self.columns_present,
            "columns_missing": self.columns_missing,
            "extra_columns": self.extra_columns,
            "dtypes": self.dtypes,
            "null_counts": self.null_counts,
            "null_pct": self.null_pct,
            "duplicate_rows": self.duplicate_rows,
            "duplicate_order_ids": self.duplicate_order_ids,
        }


def load_real_world_data(path: str | Path) -> pd.DataFrame:
    """Load the raw dataset. Supports .csv, .parquet, .xlsx/.xls by
    extension -- no format-sniffing magic beyond that, per the instruction
    not to add unnecessary complexity."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Real-world dataset not found at {path}. This file is intentionally "
            "gitignored (see .gitignore) -- place it locally and re-run "
            "precompute_real_data_insights.py to regenerate results/real_data_insights.json."
        )
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file extension {suffix!r} for {path}")
    return df


def validate_schema(df: pd.DataFrame) -> SchemaReport:
    """Report what the dataframe actually contains vs. EXPECTED_COLUMNS.
    Never raises on mismatch -- downstream code decides what to do with a
    missing column (skip that analysis section, don't crash the page)."""
    present = [c for c in EXPECTED_COLUMNS if c in df.columns]
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    extra = [c for c in df.columns if c not in EXPECTED_COLUMNS]

    null_counts = df.isnull().sum().to_dict()
    n = len(df)
    null_pct = {k: (v / n * 100 if n else 0.0) for k, v in null_counts.items()}

    dup_order_ids = 0
    if "order_id" in df.columns:
        dup_order_ids = int(df["order_id"].duplicated().sum())

    return SchemaReport(
        row_count=n,
        columns_present=present,
        columns_missing=missing,
        extra_columns=extra,
        dtypes={c: str(t) for c, t in df.dtypes.items()},
        null_counts={k: int(v) for k, v in null_counts.items()},
        null_pct={k: round(v, 4) for k, v in null_pct.items()},
        duplicate_rows=int(df.duplicated().sum()),
        duplicate_order_ids=dup_order_ids,
    )
