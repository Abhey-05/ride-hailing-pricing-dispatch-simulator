"""
Shared synthetic fixture for src/real_data/* tests. Deliberately small
(14 rows) and hand-constructed to exercise every code path the real
Rider-Info.csv exhibited during inspection -- a normal delivered order, a
cancelled order (no accept/pickup/delivered timestamps), an exact
duplicate row, a negative-delay (timestamp-ordering) row, an implausible-
duration row, and a reassigned order -- without depending on the actual
85MB gitignored dataset (never committed, so tests must not require it).
"""
from __future__ import annotations

import pandas as pd


def sample_raw_df() -> pd.DataFrame:
    rows = [
        # 6 riders x 2 orders each, spread across 3 tenure tiers, all "clean"
        dict(order_time="2021-01-26 08:00:00", order_id=1, order_date="2021-01-26", allot_time="2021-01-26 08:00:30",
             accept_time="2021-01-26 08:01:00", pickup_time="2021-01-26 08:12:00", delivered_time="2021-01-26 08:25:00",
             rider_id=101, first_mile_distance=0.5, last_mile_distance=1.5, alloted_orders=10, delivered_orders=10,
             cancelled=0, undelivered_orders=0, lifetime_order_count=5, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=120.0, cancelled_time=None),
        dict(order_time="2021-01-26 09:00:00", order_id=2, order_date="2021-01-26", allot_time="2021-01-26 09:00:20",
             accept_time="2021-01-26 09:00:50", pickup_time="2021-01-26 09:10:00", delivered_time="2021-01-26 09:22:00",
             rider_id=101, first_mile_distance=0.6, last_mile_distance=1.8, alloted_orders=10, delivered_orders=10,
             cancelled=0, undelivered_orders=0, lifetime_order_count=5, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=110.0, cancelled_time=None),
        dict(order_time="2021-01-26 08:05:00", order_id=3, order_date="2021-01-26", allot_time="2021-01-26 08:05:40",
             accept_time="2021-01-26 08:06:10", pickup_time="2021-01-26 08:18:00", delivered_time="2021-01-26 08:32:00",
             rider_id=102, first_mile_distance=1.5, last_mile_distance=3.0, alloted_orders=8, delivered_orders=8,
             cancelled=0, undelivered_orders=0, lifetime_order_count=5, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=100.0, cancelled_time=None),
        dict(order_time="2021-01-26 10:00:00", order_id=4, order_date="2021-01-26", allot_time="2021-01-26 10:00:40",
             accept_time="2021-01-26 10:01:10", pickup_time="2021-01-26 10:14:00", delivered_time="2021-01-26 10:29:00",
             rider_id=102, first_mile_distance=1.6, last_mile_distance=3.2, alloted_orders=8, delivered_orders=8,
             cancelled=0, undelivered_orders=0, lifetime_order_count=5, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=95.0, cancelled_time=None),
        dict(order_time="2021-01-26 08:10:00", order_id=5, order_date="2021-01-26", allot_time="2021-01-26 08:10:30",
             accept_time="2021-01-26 08:11:00", pickup_time="2021-01-26 08:22:00", delivered_time="2021-01-26 08:35:00",
             rider_id=201, first_mile_distance=0.8, last_mile_distance=2.0, alloted_orders=30, delivered_orders=30,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=150.0, cancelled_time=None),
        dict(order_time="2021-01-26 11:00:00", order_id=6, order_date="2021-01-26", allot_time="2021-01-26 11:00:25",
             accept_time="2021-01-26 11:00:55", pickup_time="2021-01-26 11:12:00", delivered_time="2021-01-26 11:24:00",
             rider_id=201, first_mile_distance=0.9, last_mile_distance=2.1, alloted_orders=30, delivered_orders=30,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=140.0, cancelled_time=None),
        dict(order_time="2021-01-26 08:15:00", order_id=7, order_date="2021-01-26", allot_time="2021-01-26 08:15:35",
             accept_time="2021-01-26 08:16:05", pickup_time="2021-01-26 08:28:00", delivered_time="2021-01-26 08:41:00",
             rider_id=202, first_mile_distance=0.7, last_mile_distance=1.9, alloted_orders=28, delivered_orders=28,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=145.0, cancelled_time=None),
        dict(order_time="2021-01-26 12:00:00", order_id=8, order_date="2021-01-26", allot_time="2021-01-26 12:00:20",
             accept_time="2021-01-26 12:00:50", pickup_time="2021-01-26 12:10:00", delivered_time="2021-01-26 12:20:00",
             rider_id=202, first_mile_distance=0.4, last_mile_distance=1.2, alloted_orders=28, delivered_orders=28,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=90.0, cancelled_time=None),
        dict(order_time="2021-01-26 08:20:00", order_id=9, order_date="2021-01-26", allot_time="2021-01-26 08:20:40",
             accept_time="2021-01-26 08:21:10", pickup_time="2021-01-26 08:33:00", delivered_time="2021-01-26 08:47:00",
             rider_id=301, first_mile_distance=2.0, last_mile_distance=4.0, alloted_orders=60, delivered_orders=60,
             cancelled=0, undelivered_orders=0, lifetime_order_count=500, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=200.0, cancelled_time=None),
        dict(order_time="2021-01-26 13:00:00", order_id=10, order_date="2021-01-26", allot_time="2021-01-26 13:00:30",
             accept_time="2021-01-26 13:01:00", pickup_time="2021-01-26 13:11:00", delivered_time="2021-01-26 13:23:00",
             rider_id=301, first_mile_distance=2.2, last_mile_distance=4.5, alloted_orders=60, delivered_orders=60,
             cancelled=0, undelivered_orders=0, lifetime_order_count=500, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=190.0, cancelled_time=None),
        dict(order_time="2021-01-26 08:25:00", order_id=11, order_date="2021-01-26", allot_time="2021-01-26 08:25:45",
             accept_time="2021-01-26 08:26:15", pickup_time="2021-01-26 08:40:00", delivered_time="2021-01-26 08:55:00",
             rider_id=302, first_mile_distance=2.1, last_mile_distance=4.2, alloted_orders=58, delivered_orders=58,
             cancelled=0, undelivered_orders=0, lifetime_order_count=500, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=180.0, cancelled_time=None),
        dict(order_time="2021-01-26 14:00:00", order_id=12, order_date="2021-01-26", allot_time="2021-01-26 14:00:20",
             accept_time="2021-01-26 14:00:50", pickup_time="2021-01-26 14:09:00", delivered_time="2021-01-26 14:18:00",
             rider_id=302, first_mile_distance=1.9, last_mile_distance=3.8, alloted_orders=58, delivered_orders=58,
             cancelled=0, undelivered_orders=0, lifetime_order_count=500, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=170.0, cancelled_time=None),

        # cancelled order: no accept/pickup/delivered timestamps
        dict(order_time="2021-01-26 15:00:00", order_id=13, order_date="2021-01-26", allot_time="2021-01-26 15:00:30",
             accept_time=None, pickup_time=None, delivered_time=None,
             rider_id=101, first_mile_distance=1.0, last_mile_distance=2.0, alloted_orders=10, delivered_orders=9,
             cancelled=1, undelivered_orders=1, lifetime_order_count=5, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=None, cancelled_time="2021-01-26 15:02:00"),

        # reassigned order (delivered, but flagged + has method/reason)
        dict(order_time="2021-01-26 16:00:00", order_id=14, order_date="2021-01-26", allot_time="2021-01-26 16:00:30",
             accept_time="2021-01-26 16:04:00", pickup_time="2021-01-26 16:20:00", delivered_time="2021-01-26 16:45:00",
             rider_id=201, first_mile_distance=1.2, last_mile_distance=2.5, alloted_orders=30, delivered_orders=30,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method="auto",
             reassignment_reason="Auto Reassignment basis Inaction.", reassigned_order=1.0, session_time=150.0, cancelled_time=None),

        # negative-delay row: accept_time BEFORE allot_time (data error)
        dict(order_time="2021-01-26 17:00:00", order_id=15, order_date="2021-01-26", allot_time="2021-01-26 17:01:00",
             accept_time="2021-01-26 17:00:30", pickup_time="2021-01-26 17:12:00", delivered_time="2021-01-26 17:25:00",
             rider_id=202, first_mile_distance=0.9, last_mile_distance=2.0, alloted_orders=28, delivered_orders=28,
             cancelled=0, undelivered_orders=0, lifetime_order_count=50, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=100.0, cancelled_time=None),

        # implausible-duration row: delivered ~8 hours after order
        dict(order_time="2021-01-26 18:00:00", order_id=16, order_date="2021-01-26", allot_time="2021-01-26 18:00:30",
             accept_time="2021-01-26 18:01:00", pickup_time="2021-01-26 18:12:00", delivered_time="2021-01-27 02:00:00",
             rider_id=301, first_mile_distance=1.0, last_mile_distance=2.0, alloted_orders=60, delivered_orders=60,
             cancelled=0, undelivered_orders=0, lifetime_order_count=500, reassignment_method=None, reassignment_reason=None,
             reassigned_order=None, session_time=100.0, cancelled_time=None),

        # exact duplicate of order_id=1's row (to test dedup)
    ]
    df = pd.DataFrame(rows)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)  # duplicate row 0 exactly
    return df
