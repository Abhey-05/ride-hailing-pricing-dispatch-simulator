#!/usr/bin/env python3
"""
Runs the Real-World Validation pipeline (src/real_data/) against the local
raw dataset and writes a small, fully aggregated, anonymized JSON artifact
to results/real_data_insights.json -- the ONLY thing the dashboard page
(dashboard/pages/1_Real_World_Validation.py) reads. No row-level order_id
or rider_id is ever written to this file.

This script is the sole place the raw ~85MB Rider-Info.csv (gitignored --
see .gitignore) is touched. Re-run it locally whenever the source dataset
changes; commit the resulting results/real_data_insights.json.

This module and its outputs are entirely separate from the simulator: it
reads results/results.csv (read-only, for one calibration comparison) and
writes nothing back to it or to any other simulator file.

Usage:
    python precompute_real_data_insights.py [path/to/Rider-Info.csv]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from src.real_data import analysis, calibration, loader, metrics

ROOT = Path(__file__).parent
DEFAULT_DATA_PATH = ROOT / "Rider-Info.csv"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "real_data_insights.json"


def main():
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DATA_PATH
    t0 = time.time()

    print(f"Loading {data_path} ...")
    df = loader.load_real_world_data(data_path)
    schema_report = loader.validate_schema(df)
    print(f"  {schema_report.row_count:,} rows, {len(schema_report.columns_present)}/{len(schema_report.columns_present) + len(schema_report.columns_missing)} expected columns present")
    if schema_report.columns_missing:
        print(f"  MISSING columns: {schema_report.columns_missing}")
    if schema_report.extra_columns:
        print(f"  EXTRA columns (ignored by analysis): {schema_report.extra_columns}")

    print("Cleaning timestamps ...")
    df, ts_report = metrics.clean_timestamps(df)

    print("Deriving metrics ...")
    df, derive_report = metrics.derive_metrics(df)
    print(f"  {derive_report['duplicate_rows_dropped']} exact duplicate row(s) dropped")
    print(
        f"  {derive_report['rows_excluded_from_timing_analysis']} row(s) "
        f"({derive_report['rows_excluded_from_timing_analysis'] / derive_report['rows_after_dedup'] * 100:.3f}%) "
        "excluded from delay-distribution analysis only (invalid timestamp ordering or implausible duration) "
        "-- still counted in funnel/cancellation/reassignment stats."
    )

    print("Running analysis ...")
    insights = analysis.analyze_data(df)

    print("Comparing to simulator baseline (results/results.csv, read-only) ...")
    sim_baseline = calibration.load_simulator_baseline(RESULTS_DIR / "results.csv")
    calibration_table = calibration.compare_to_simulator(insights["overview"], insights["funnel"], sim_baseline)

    output = {
        "generated_at_unix": time.time(),
        "source_row_count": schema_report.row_count,
        "schema": schema_report.to_dict(),
        "timestamp_parse_report": ts_report,
        "derive_metrics_report": derive_report,
        "insights": insights,
        "simulator_baseline": sim_baseline,
        "calibration": calibration_table,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, default=str)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nWrote {OUTPUT_PATH} ({size_kb:.1f} KB) in {time.time() - t0:.1f}s")
    print("No row-level order_id/rider_id in this file -- safe to commit.")


if __name__ == "__main__":
    main()
