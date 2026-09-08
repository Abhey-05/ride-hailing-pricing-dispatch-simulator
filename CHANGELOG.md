# Changelog

Major implementation decisions and calibration fixes, in the order they happened. This is the honest paper trail for "how did you know your simulation was correct?"

## Phase 1 — Product & architecture

- Chose file-based (Parquet/CSV) result storage over Postgres, and Streamlit+Plotly over a React dashboard, to keep the build tractable within scope while still documenting the "production path" (Postgres schema, API docs) for credibility.

## Phase 2 — Mathematical specification

- Designed the full timestep sequence, demand/pricing/dispatch/cancellation math, and experiment design before writing any simulation code (`docs/MATHEMATICAL_MODEL.md`, `docs/EXPERIMENT_DESIGN.md`, `docs/ASSUMPTIONS.md`).
- Re-designed the experiment matrix from a naive `4×5×6×4=480` grid to `4×5×24 seeds=480` (core, single scenario) + `600` robustness runs across the other 5 scenarios — chosen because 24 paired seeds gives real statistical power for the primary hypothesis test, whereas 4 seeds spread across 120 cells would not.

## Phase 3 — Engine implementation

- **Bug found & fixed (calibration):** initial `grid_scale_km = 3.0` produced a city with a ~34 km diagonal. Combined with a fleet of 260 drivers spread across 10 zones, this made typical pickup ETAs 20–50 minutes — far outside the range the rest of the model (5-minute wait reference, 4–8 minute rider patience) was calibrated for. This crushed driver acceptance probability toward zero (observed acceptance rate: 11%) and completion rate to 34%, with an unrealistic 43% cancellation rate. **Fix:** reduced `grid_scale_km` to `1.2` (≈13.6 km diagonal), bringing typical pickup ETAs into the 3–8 minute range. Updated `docs/MATHEMATICAL_MODEL.md` and `docs/ASSUMPTIONS.md` to match. Post-fix baseline (NORMAL / BASIC_SURGE / NEAREST_DRIVER, seed 0): 69% driver acceptance, 54% completion rate, 22% cancellation rate, P90 wait 11 min — all directionally sane.
- **Bug found & fixed (bootstrapping failure):** the driver-acceptance normalizers (`avg_pickup_eta_city`, `avg_fare_driver_share_city`) were only updated via EMA when a driver *accepted* an assignment. Since a too-low initial default value crushed acceptance probability near zero, the EMA had no successful matches to learn from and never corrected itself — a self-reinforcing failure. **Fix:** normalizers now update via EMA on every dispatch *offer*, not just accepted ones, so they reflect the true offered distribution regardless of the current acceptance rate.
- **Design fix (double-booking risk in look-ahead dispatch):** `ETA_OPTIMIZED` and `ADVANCED_HEURISTIC` can offer a still-busy (`ON_TRIP`) driver who is about to free up nearby. The first implementation immediately transitioned such a driver to `EN_ROUTE_TO_PICKUP` for the new request, silently abandoning their current trip — a real correctness bug. **Fix:** added a `queued_request_id` / `queued_pickup_travel_min` pair on `Driver`; a look-ahead match is "pre-booked" and only takes effect when the driver's current trip actually completes (engine.py step 3). Post-match cancellation on a still-queued request now correctly leaves the driver's current trip untouched rather than erroneously freeing them. Covered by `tests/test_engine_invariants.py::test_no_double_booking_including_lookahead_policies`.
- **Empirical finding, not a bug:** Validation Plan check #5 ("nearest-driver minimizes pickup distance") turned out to be false in the unqualified form originally written — `ETA_OPTIMIZED` and `ADVANCED_HEURISTIC` can achieve a *lower* average realized pickup distance than `NEAREST_DRIVER`, because their look-ahead candidate set (drivers about to free up nearby) is strictly larger than "currently idle only." The check was refined to compare `NEAREST_DRIVER` only against the other available-only policies (`DRIVER_EARNINGS_AWARE`, `MARKETPLACE_AWARE`), where it does hold exactly. Documented in `docs/EXPERIMENT_DESIGN.md` Section U.
- Chose **absolute `release_tick` bookkeeping** over countdown-timer decrementing for trip/pickup phases — behaviorally identical to the spec's "decrement then resolve" language, simpler and less error-prone to implement.
- Chose to resolve `ASSIGNED → {EN_ROUTE_TO_PICKUP | AVAILABLE}` synchronously within a single tick rather than persisting an observable `ASSIGNED` state across ticks — the spec's step 8/9 sequence describes dispatch and driver-acceptance resolution happening back-to-back in the same tick, so no information is lost.

## Phase 4 — Validation

- Full pytest suite (22 tests) covers: reproducibility (bit-identical output for the same seed), all ten Validation Plan checks from `docs/EXPERIMENT_DESIGN.md` Section U, and every "invariant that must never break" from Part 42 of the project brief (no negative price, surge within cap, utilization bounded, no double-booking, driver earnings ≥ 0, completed ≤ requested).

## Phase 6 — Full experiment matrix

- Ran the full 1,080-run matrix (480 core + 600 robustness) in 327s wall-clock, single-threaded, on a laptop -- confirmed the "6 minutes" runtime estimate from a 60-run timing probe.
- Results saved to `results/results.csv` / `.parquet` plus `results/manifest.json` (seed lists, versions, wall-clock time) for reproducibility.

## Phase 7 — Statistical analysis & charts

- Built `src/analysis.py`: paired bootstrap CI (10,000 resamples), paired Wilcoxon + t-test, matched-pairs Cohen's d, and a pre-registered practical-significance bar (≥5% relative effect AND CI excludes 0) applied uniformly to every comparison -- decided in `docs/EXPERIMENT_DESIGN.md` Section Q *before* the experiment ran, not fit to the results afterward.
- Headline, unmanipulated finding: `ETA_OPTIMIZED` beats the `NEAREST_DRIVER` baseline on P90 wait in every one of the 4 pricing policies (7.8%-11.3%, all p<0.001), with driver earnings and platform revenue both *improving* rather than trading off. Full writeup: `docs/EXPERIMENTS.md`.
- Equally important negative finding, also unmanipulated: `ADVANCED_HEURISTIC` -- the policy combining the most objectives -- performed *worse* than the naive baseline in every configuration. Root-caused to its hand-tuned weights over-prioritizing marketplace-imbalance/cancel-risk terms relative to pickup ETA (`src/config.py::ADVANCED_HEURISTIC_WEIGHTS`). Reported as-is rather than re-tuned after the fact, since re-tuning post-hoc to fix an inconvenient result would defeat the point of pre-registering a decision framework.
- **Bug found & fixed:** `pandas.DataFrame.fillna(method="ffill")` no longer exists in pandas 3.0 (used in the zone-heatmap chart) -- replaced with `.ffill()`.

## Phase 8-9 — Dashboard & API

- Streamlit dashboard (`dashboard/app.py`) and FastAPI service (`api/main.py`) both read directly from `results/*.csv` / call `src.engine` -- no separate business logic duplicated between them.
- **Bug found & fixed:** `api/main.py`'s `/simulation/run` endpoint raised `ValueError: Out of range float values are not JSON compliant: nan` for any run with too few completed trips (e.g. a short horizon starting at midnight, before most driver shifts begin) -- Starlette's default `JSONResponse` only auto-sanitizes NaN for explicitly float-typed Pydantic fields, not values inside a generic `dict`. Fixed with an explicit `_sanitize_nan` pass before constructing the response. Found by `tests/test_api.py`, not by inspection.
- Both the dashboard (via `claude-in-chrome` browser automation) and the API (via direct HTTP calls) were actually exercised end-to-end, not just started and assumed to work.

## Phase 10 — ML component & AI copilot

- Added a genuine ML use case: predicting whether a ride request will cancel, using only pre-dispatch, request-creation-time features (segment, patience, surge, price, distance, marketplace imbalance, hour of day) -- deliberately excluding any post-match field (pickup ETA/distance), since those only exist *because* a match happened, which would leak the label.
- Real result (`train_cancellation_model.py`, ~149k request-level training rows from live simulations): a naive single-variable "shorter patience = higher risk" rule scores AUC 0.55 (barely better than chance); a full-feature logistic regression scores 0.78; gradient boosting scores 0.82. Feature importance shows **time of day and marketplace imbalance dominate patience** (0.75 + 0.17 vs. 0.05 combined importance) -- the actual driver of cancellation risk in this simulation is *when/where* you request a ride, not *who* you are, which the existing single-variable heuristic almost entirely misses.
- AI Marketplace Analyst (`src/ai_copilot.py`, `src/copilot_tools.py`): Claude tool-calling over 5 deterministic functions (pre-computed result lookups + live what-if simulation). The LLM never computes a metric itself.
- **Bug found & fixed:** the first draft of `simulate_whatif`'s demand/supply multiplier override was silently a no-op -- `world.generate_world` only ever looked up `config.SCENARIOS[scenario_name]` internally, so a locally-modified `Scenario` object passed to the engine never actually changed how many requests were generated. Fixed by adding a `scenario_override` parameter to `world.generate_world` itself. Caught by `tests/test_copilot_tools.py::test_whatif_demand_override_changes_request_volume` actually asserting the request count changes, not just that the call succeeds.
- Not runnable end-to-end in this environment (no `ANTHROPIC_API_KEY` present in the sandbox this was built in) -- code is complete and unit-tested at the tool-function layer; the Claude tool-calling loop itself needs a live key to exercise.

## Phase 11-13 — Documentation, sensitivity analysis, and critical review

- Wrote the full documentation set (PRD, System Design, Learning Guide, Interview Guide, Product Case Study, this file) grounded in the actual experiment numbers, not placeholder text.
- Ran `sensitivity_analysis.py` (Experiment 12, previously only designed, not executed) in response to the critical review's own top-priority finding: perturbed the 6 most uncertain parameters ±30% each (12 conditions, 8 seeds each, 224 additional simulations). Result: the core finding's *sign* survives every perturbation; its *magnitude* ranges 4.2%-13.3%. Updated `docs/EXPERIMENTS.md`, `docs/PRD.md`, and `docs/CRITICAL_REVIEW.md` to reflect this rather than leaving it as an open item once it was actually feasible to close within scope.
- Performed a skeptical self-review (`docs/CRITICAL_REVIEW.md`) against this project's own standards -- identified 8 concrete weaknesses (missing driver-supply-response model, thin robustness-scenario power, an unvalidated heuristic that made it into the official experiment matrix, no real-world calibration, an untested AI copilot, etc.), fixed the one most worth fixing given remaining scope (sensitivity analysis), and left the rest explicitly prioritized rather than quietly patched over.
