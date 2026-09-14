# Real-World Validation module

A separate, additive evidence layer around the simulator: uses a real
food-delivery operations dataset to diagnose operational behavior and
generate hypotheses that could be tested in the existing simulator. It does
not replace the simulator, does not change any simulator parameter, and is
not shown on the Overview page -- it is its own navigation item
("Real World Validation") in the Streamlit sidebar.

## Why this exists

The core question: can real observed marketplace data validate the
simulator's assumptions, surface bottlenecks the simulator's synthetic
world might not capture, and motivate specific hypotheses worth testing?
The dataset is food delivery (customer + delivery partner), not
ride-hailing (rider + car) -- the two are conceptually analogous
(request -> assignment -> pickup -> completion) but not the same business.
Every comparison in this module says so explicitly rather than implying
equivalence.

## Dataset inspection (Rider-Info.csv, gitignored, never committed)

Inspected directly before writing any code (`src/real_data/loader.py`'s
`EXPECTED_COLUMNS` reflects what was actually found, not the task's
description of it):

- **450,000 rows, 20 columns**, one food-delivery order per row, Jan 26 -
  Feb 6 2021 (12 days), 19,537 unique riders (delivery partners).
- `cancelled` (0/1) is complete and consistent: `delivered_time` is null
  **if and only if** `cancelled == 1` -- there is no "undelivered but not
  cancelled" case at the row level in this export (`undelivered_flag` in
  `src/real_data/metrics.py` is still computed generally, not hardcoded to
  zero, in case a future export differs).
- `alloted_orders` / `delivered_orders` / `undelivered_orders` are
  **rider-day rolling totals** (constant within one rider on one day),
  confirmed by grouping and checking `nunique()` per rider -- not a
  per-order fact, so they are not used as per-order features.
- `lifetime_order_count` is essentially static per rider across the whole
  12-day window -- a genuine tenure signal, used for the anonymized
  experience segmentation.
- `reassignment_method` / `reassignment_reason` present for 13,753 orders
  (3.06%); `auto` (13,383) vastly dominates `manual` (361).
- Data quality found and handled explicitly (never silently dropped --
  every exclusion is counted and shown on the dashboard page's "Data
  quality" expander):
  - 1 exact duplicate row.
  - 35 rows (0.008%) with an out-of-order timestamp (e.g. `accept_time`
    before `allot_time`).
  - 287 rows (0.06%) with an implausible end-to-end duration (>240 min --
    chosen as ~2.6x the dataset's own 99.5th-percentile duration of ~92
    min, not an arbitrary round number).
  - A handful of distance outliers (first-mile >15km: 2 rows; last-mile
    >15km: 20 rows).
  - These rows are excluded from delay-distribution statistics only --
    they still count in funnel, cancellation, and reassignment analysis.

## Pipeline

```
Rider-Info.csv (gitignored, local only)
  -> src/real_data/loader.py       load_real_world_data, validate_schema
  -> src/real_data/metrics.py      clean_timestamps, derive_metrics
  -> src/real_data/analysis.py     analyze_data (funnel, delays, reassignment,
                                    distance, rider segments, time-of-day,
                                    opportunities)
  -> src/real_data/calibration.py  compare_to_simulator (reads
                                    results/results.csv read-only)
  -> precompute_real_data_insights.py  (run manually, offline)
  -> results/real_data_insights.json   (committed -- aggregated, anonymized,
                                         ~27KB, no order_id/rider_id)
  -> dashboard/pages/1_Real_World_Validation.py  (reads only this JSON)
```

Re-run `python precompute_real_data_insights.py` locally whenever the
source dataset changes, then commit the regenerated
`results/real_data_insights.json`. The deployed app never reads the raw
CSV -- it isn't present in the deployed environment at all.

## Causality stance

Every relationship this module reports is a plain aggregate contrast
(median/P75/P90, rate differences) -- nothing computes a p-value or claims
statistical significance, and nothing claims a causal effect. Captions use
"associated with" / "observed among", never "caused by" or "will reduce".
`src/real_data/analysis.py::generate_opportunities()` is deliberately
conservative: an opportunity is only surfaced when the observed effect is
in the expected direction and clears a minimum magnitude (see that
function's inline comments for the exact per-opportunity checks) -- e.g.
the first-mile-distance opportunity uses end-to-end time and cancellation
rate, not acceptance delay, because acceptance delay showed no meaningful
(and briefly reversed) relationship with distance in this dataset; a
naive first/last-bucket comparison would have produced a misleading claim.
Similarly, the time-of-day analysis requires a minimum hourly sample size
(500 orders) before ranking hours by cancellation rate, to avoid a
single-digit-order overnight hour dominating the ranking on pure noise.

## Privacy

`order_id` and `rider_id` are never displayed, never included in any chart
label, table cell, or JSON field written by `analyze_data()` or
`compare_to_simulator()` -- verified by
`tests/test_real_data_analysis.py::test_analyze_data_output_has_no_raw_order_or_rider_ids`,
which serializes the full analysis output to JSON and asserts neither
substring appears. Rider-experience segmentation
(`src/real_data/analysis.py::rider_segmentation`) reports only aggregated
per-segment statistics and rider *counts*, never individual rider records.

## What this module is not

It is not a claim that the simulator is "wrong" because a calibration row
shows a mismatch, and it is not an automatic simulator-tuning tool -- the
calibration table's "suggested calibration" note is exactly that, a
suggestion for a human to consider, never applied. It is not a
reconstruction of a real production dispatch algorithm: the dataset lacks
live rider/partner locations, restaurant prep time, the full candidate set
considered at assignment time, quoted pricing/incentives, traffic, and
weather -- see the dashboard page's own Limitations section for the same
list in user-facing form.
