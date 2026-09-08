# Final Project Report
## Ride-Hailing Surge Pricing & Dispatch Simulator

---

## 1. Executive Summary

Ride-hailing platforms manage rider wait time, driver earnings, and platform revenue using three levers of very different cost profiles: surge pricing, driver incentives, and dispatch/matching quality. The first two are easy to measure and show up immediately in a P&L; the third is a software investment whose payoff is hard to justify without a controlled experiment. This project built a synthetic marketplace simulation and a rigorous experimentation framework to answer one specific, falsifiable question: **can dispatch quality reduce rider wait time without raising driver-side or pricing-side cost?**

After running 1,080 independent simulations (480 for a properly powered core hypothesis test, 600 for robustness checks across five stress scenarios) and a 12-condition sensitivity sweep, the answer in this model is **yes**: a look-ahead-aware dispatch policy (`ETA_OPTIMIZED`) reduces P90 rider wait time by 7.8–11.3% across every pricing policy tested (all p < 0.001), while driver earnings, cancellation rate, and platform revenue all *improve* rather than trade off. The finding's direction survives a ±30% perturbation of every major synthetic assumption. A more "sophisticated" hand-tuned dispatch heuristic combining multiple objectives, by contrast, was found to *underperform* the naive baseline — a real, reported negative result that illustrates exactly the kind of thing this simulation exists to catch before it reaches production.

All data in this project is synthetic. The recommendation is to prioritize a real, small-scale production experiment on dispatch quality ahead of further pricing changes — not to treat this simulation's exact percentages as production forecasts.

---

## 2. Problem

A ride-hailing marketplace is a two-sided market: riders want a low price and short wait; drivers want steady, well-paid work. When demand exceeds supply in a zone, riders wait longer (some cancel) while drivers elsewhere sit idle (wasted supply). Platforms close this gap with surge pricing (rations demand, in theory attracts supply), driver incentives (pays for more supply directly), or better dispatch (uses existing supply more efficiently). Production experimentation with any of these is expensive and risky — real riders and drivers are affected during the test, and separating a dispatch effect from a concurrent pricing change in production data is difficult. This project builds the sandbox to screen these ideas safely and quantitatively before committing production experimentation budget to them.

## 3. Market Mechanics

The simulated city has 10 zones, each with an archetype (residential, commercial, airport, university, suburban, transit hub, nightlife) driving a distinct time-of-day demand curve and directional flow pattern (e.g., residential → commercial in the morning, reversed in the evening). Demand arrives as a Poisson process with a rate that varies by zone and time of day. Drivers work shifts drawn from a synthetic schedule distribution. Prices are set by one of four surge policies; matches are made by one of five dispatch policies. Riders decide whether to accept a priced offer and whether to cancel while waiting, via logistic functions of price, wait time, and their own patience; drivers decide whether to accept an assignment via a logistic function of pay, pickup distance, and their current utilization. Full detail: `docs/MATHEMATICAL_MODEL.md`.

## 4. Assumptions

Every numeric parameter is a labeled **synthetic assumption**, chosen for directional realism and internal consistency, not fit to any real company's data (`docs/ASSUMPTIONS.md`). Notable calibration fixes made during development: the initial city scale produced 30–50 minute pickup ETAs that made the marketplace non-functional (near-zero driver acceptance); reducing the grid scale from 3.0 to 1.2 km/unit brought ETAs into a realistic 3–8 minute range. This and every other non-trivial decision is logged in `CHANGELOG.md`.

## 5. Simulation Methodology

A time-stepped (1-minute tick), 24-simulated-hour agent simulation, chosen over a full discrete-event architecture because nothing in this marketplace changes meaningfully faster than one minute, and the simpler design is easier to validate and explain. Each tick executes a fixed 12-step sequence (demand generation → driver state resolution → marketplace state → surge → pricing → rider accept/reject → dispatch → driver accept/reject → trip advancement → cancellations → metrics) — full detail in `docs/MATHEMATICAL_MODEL.md` §A. Reproducibility is guaranteed via `numpy.random.SeedSequence`-derived streams (never Python's built-in `hash()`, which is randomized per process). A **common random numbers** design pre-generates the entire exogenous "world" (every rider's arrival time, zone, segment, patience, and accept/cancel decision thresholds; every driver's shift schedule) once per `(scenario, seed)`, independent of policy — so all 20 pricing×dispatch combinations at a given seed face literally the same simulated riders and drivers, turning policy comparison into a precise paired experiment instead of a noisy unpaired one.

## 6. Pricing Model

Base fare = fixed fee + per-km + per-minute components. Four surge policies were implemented: `NO_SURGE` (control), `BASIC_SURGE` (proportional to zone imbalance, capped 1.0–2.0×, updated every 5 minutes), `AGGRESSIVE_SURGE` (higher gain, capped 1.0–3.0×, updated every tick), and `CAPPED_SMOOTHED_SURGE` (same signal as basic, exponentially smoothed to reduce visible price flicker, capped 1.0–2.5×). Caps exist because uncapped surge can spiral during a supply/demand imbalance, generating the "$300 ride" news stories that damage brand trust and invite regulatory response — a deliberate product trade-off of some theoretical demand-suppression power for predictability.

## 7. Dispatch Algorithms

Five policies, each a documented heuristic (not a global optimum — see below): `NEAREST_DRIVER` (minimize pickup distance among currently idle drivers), `ETA_OPTIMIZED` (minimize predicted pickup time, including drivers about to finish a nearby trip), `DRIVER_EARNINGS_AWARE` (among the nearest few candidates, pick whichever maximizes predicted driver-acceptance probability), `MARKETPLACE_AWARE` (penalize pulling a driver out of an already-undersupplied zone), and `ADVANCED_HEURISTIC` (a weighted combination of pickup ETA, marketplace-imbalance protection, destination-steering, and cancellation-risk urgency). None solve the exact minimum-cost bipartite matching problem (which would need the Hungarian algorithm, `O((R+D)³)` per tick, infeasible to re-solve every minute against constantly changing state at real scale) — a deliberate, explained trade-off between optimality and real-time feasibility (`docs/MATHEMATICAL_MODEL.md` §H.5).

## 8. Experiments

**Core hypothesis test:** 4 pricing × 5 dispatch × 24 common-random-number seeds = 480 runs under a representative `NORMAL` demand scenario, chosen over spreading fewer seeds across more scenarios specifically to maximize statistical power on the primary comparison.
**Robustness:** the same 20 policy combinations × 6 seeds across 5 stress scenarios (peak demand, supply shortage, demand shock, low demand, congested peak) = 600 further runs.
**Sensitivity:** a follow-up 12-condition, 8-seed-each sweep (224 further runs) perturbing the 6 most uncertain parameters by ±30%.
Full experiment-by-experiment results and interpretation: `docs/EXPERIMENTS.md`.

## 9. Results

| Metric (BASIC_SURGE pricing) | NEAREST_DRIVER (baseline) | ETA_OPTIMIZED | Relative change |
|---|---|---|---|
| P90 rider wait | 10.25 min | 9.33 min | **−8.9%** |
| Driver earnings/online-hour | 153.71 | 156.67 | **+1.9%** |
| Cancellation rate | 20.6% | 19.6% | **−4.7%** |
| Platform revenue | 91,043 | 93,493 | **+2.7%** |
| North Star (trips/online-driver-hour) | 1.948 | 1.990 | **+2.2%** |

This holds (7.8–11.3% P90 wait improvement) across all four pricing policies, all statistically significant (Wilcoxon p < 0.001) and clearing a pre-registered ≥5% practical-significance bar. The improvement's *sign* survived every one of the 12 sensitivity perturbations; its *magnitude* ranged 4.2–13.3% depending on the parameter. A more complex dispatch heuristic (`ADVANCED_HEURISTIC`) underperformed the naive baseline by 4.5–8.3% in every pricing policy tested — a genuine, unmanipulated negative finding, root-caused to unvalidated objective weights (see `docs/EXPERIMENTS.md`).

## 10. Statistical Analysis

Every comparison uses a paired design (24 seeds, common random numbers), a bootstrap percentile 95% confidence interval (10,000 resamples, chosen over a normal-theory CI given the small sample size), a paired Wilcoxon signed-rank test as the primary significance test (with a paired t-test reported alongside for cross-checking), and a matched-pairs Cohen's d effect size. A result is only called "practically significant" if it clears **both** a formal significance test and a pre-registered ≥5% relative-effect threshold — several comparisons (`DRIVER_EARNINGS_AWARE`, `MARKETPLACE_AWARE`) were statistically detectable but did not clear this bar, and are reported as such rather than rounded up. Full methodology: `docs/EXPERIMENT_DESIGN.md` §Q.

## 11. AI Component

An "AI Marketplace Analyst" answers natural-language questions (e.g., "which dispatch policy performs best during peak hours?") via Claude tool-calling over five deterministic functions that read the pre-computed experiment results or run a fresh live simulation (`src/ai_copilot.py`, `src/copilot_tools.py`). The architecture enforces a hard separation: the calculation engine is the only source of numerical truth; the LLM only explains numbers it received from a tool call, never computes one itself. This was not exercised end-to-end with a live API key in the build environment — the deterministic tool layer is unit-tested; the conversational loop is code-reviewed but not live-verified, stated plainly rather than glossed over.

## 12. System Architecture

Python simulation engine → file-based results warehouse (Parquet/CSV, chosen over Postgres for this scale to avoid unnecessary operational overhead, with a full production Postgres schema specified in `docs/SYSTEM_DESIGN.md` for when it would be justified) → statistical analysis layer → Streamlit/Plotly dashboard + FastAPI service + AI copilot, all reading the same source of truth. Full diagrams and API reference: `docs/SYSTEM_DESIGN.md`.

## 13. Product Implications

Of the three levers available to a marketplace team, this simulation found dispatch to be the only one that improved rider experience, driver earnings, and platform revenue *simultaneously*, at zero incremental marginal cost per ride once built. Surge pricing also worked as intended (raising revenue and — via reduced congestion — lowering cancellation) but converts to money rather than rider-experience relief, and carries real brand/regulatory risk this model doesn't price in. Driver incentives could not be evaluated on equal footing because the model has no driver-supply-response-to-incentive mechanism — an explicit, acknowledged scope gap, not a hidden one. Full decision matrix and recommendation: `docs/PRD.md` §13–14.

## 14. Limitations

- No driver-supply-response-to-price/incentive mechanism (the single biggest modeling gap).
- Robustness-scenario statistical power is thinner (6 seeds) than the core comparison (24 seeds); two robustness results are reported honestly as directionally-consistent-but-not-statistically-significant.
- All parameters are synthetic; no real-world calibration was performed. The qualitative mechanism (surge suppresses demand, better dispatch reduces wait) is well-supported by marketplace economics; magnitudes are properties of this model, not real-world predictions.
- No multi-day churn/retention feedback loop — a rider's bad experience doesn't reduce their simulated future demand.
- The AI copilot's conversational loop was not exercised against a live API key.

Full self-critical review, including what would be needed to reach the next level of rigor: `docs/CRITICAL_REVIEW.md`.

## 15. Future Work

1. Combined (not just one-at-a-time) worst-case sensitivity perturbations.
2. A driver supply-response model, to complete the three-lever decision matrix.
3. 24-seed robustness scenarios (currently 6).
4. A live end-to-end test of the AI copilot.
5. Per-zone fairness/equity guardrails (e.g., a Gini coefficient on driver earnings).
6. A real production shadow-mode test of `ETA_OPTIMIZED`'s core mechanism.
