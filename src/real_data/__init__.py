"""
Real-World Validation module.

Isolated evidence layer around the ride-hailing simulator: loads a real
food-delivery operations dataset, diagnoses operational behavior, and
generates hypotheses that *could* be tested in the existing simulator. This
package never imports from, calls into, or mutates anything in the
simulator (src/engine.py, src/pricing.py, src/dispatch.py, src/decision.py)
-- it only *reads* results/results.csv for one read-only calibration
comparison (src/real_data/calibration.py).

Pipeline:  load_real_world_data -> validate_schema -> clean_timestamps
           -> derive_metrics -> analyze_data -> (precompute_real_data_insights.py)
           -> results/real_data_insights.json -> dashboard/pages/*.py
"""
