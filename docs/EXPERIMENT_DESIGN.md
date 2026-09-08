# Experiment Design

Companion to `MATHEMATICAL_MODEL.md`. This document is the exact spec `src/experiments/` must implement — policy list, scenario list, seed scheme, run count, and the statistical analysis plan, decided *before* any run executes.

---

## O. Experiment Matrix

### Design decision: power over spread

A naive `4 pricing × 5 dispatch × 6 scenarios × 4 seeds = 480` design gives only **4 independent seeds per cell** — too few for a defensible paired comparison (Section Q). Instead:

**Core experiment (hypothesis test): 4 pricing × 5 dispatch × 24 seeds = 480 runs, all under the `NORMAL` scenario.**
This gives **24 paired seeds per policy comparison** — enough for a paired t-test / Wilcoxon signed-rank test with reasonable power, and it directly targets the primary hypothesis (Section R) without a scenario confound.

**Robustness experiments (separate, smaller): each of the 5 stress scenarios × 4 pricing × 5 dispatch (20 combos) × 6 seeds = 120 runs/scenario × 5 scenarios = 600 additional runs.**
These map directly to Part 13 Experiments 7–11 (demand shock, supply shortage, peak hour, low demand, seed-robustness) and answer "does the core result hold up under stress?" — a different, complementary question from the core hypothesis test.

**Total: 1,080 simulation runs.** This exceeds the ≥480 requirement while being honest about where statistical power actually comes from (24 paired seeds on the core comparison, not 4 spread across 120 cells). Exact robustness seed counts may be reduced from 6 if Phase 4 runtime validation shows the full 600 is impractical — any reduction will be logged in `CHANGELOG.md` with the actual count used.

### Scenarios (all six, used across core + robustness)

| Scenario | Demand mult. | Supply mult. | Congestion mult. | Shock | Duration | Why it matters |
|---|---|---|---|---|---|---|
| **NORMAL** | 1.0 | 1.0 | 1.0 (TOD-driven only) | none | 24h | Representative baseline day — used for the core 480-run hypothesis test |
| **PEAK_DEMAND** | 1.6 | 1.0 | 1.0 | none | 24h | Sustained high demand — tests whether dispatch gains hold when the marketplace is already strained |
| **SUPPLY_SHORTAGE** | 1.0 | 0.6 | 1.0 | none | 24h | Fewer drivers online (e.g., bad weather, holiday) — tests whether better dispatch can partially substitute for missing supply |
| **DEMAND_SHOCK** | 1.0 | 1.0 | 1.0 | +150% demand in one zone for a 90-min window at a random(seeded) hour | 24h | Concert/event-style spike — tests policy reaction speed and localized recovery |
| **LOW_DEMAND** | 0.6 | 1.0 | 1.0 | none | 24h | Oversupplied market — tests whether pricing/dispatch choice matters at all when supply is abundant (expected: smaller effect sizes) |
| **CONGESTED_PEAK** | 1.6 | 1.0 | 1.35 | none | 24h | Demand *and* mobility stress together — tests whether dispatch gains survive when travel times themselves are inflated |

All multipliers apply on top of the zone/TOD baseline defined in `ASSUMPTIONS.md`.

### Policies

**Pricing (4):** `NO_SURGE`, `BASIC_SURGE`, `AGGRESSIVE_SURGE`, `CAPPED_SMOOTHED_SURGE` (formulas in `MATHEMATICAL_MODEL.md` §G).
**Dispatch (5):** `NEAREST_DRIVER`, `ETA_OPTIMIZED`, `DRIVER_EARNINGS_AWARE`, `MARKETPLACE_AWARE`, `ADVANCED_HEURISTIC` (§H).
**Baseline policy pair for "current system" in all before/after comparisons:** `BASIC_SURGE` × `NEAREST_DRIVER` — chosen because it represents the simplest non-trivial real-world-like setup (some surge, naive dispatch), which is a realistic stand-in for "what a platform does before investing in either lever."

---

## P. Randomization / Seeds — Common Random Numbers (CRN)

**Goal:** when comparing two policies, we want the *only* difference between their runs to be the policy — not incidental randomness (a lucky run with fewer demand spikes). This is the classic variance-reduction technique of **common random numbers**: reuse the same underlying random draws across the runs being compared, so the comparison becomes "paired" (same conditions, different policy) rather than "independent" (different conditions *and* different policy, with the policy effect buried in noise).

**Implementation:**
1. A run is identified by `(scenario, seed)`. A **world stream** `rng_world = default_rng(hash(scenario, seed))` generates everything *exogenous to policy*: how many riders/drivers are created, their zone, their segment, their patience `τ_i`, their shift schedule, travel-time noise, and — critically — a **fixed uniform draw per rider-decision-point** (`u_accept_offer`, `u_cancel_tick[]`, `u_driver_accept`) generated once per agent at creation, independent of which policy will later compute a probability against it.
2. When a policy computes `P_accept` (or any other probability) for an agent, the accept/reject outcome is `u_accept_offer < P_accept`, using that agent's **pre-drawn, policy-independent** `u_accept_offer` — not a fresh random draw. This means: if policy A produces a *higher* `P_accept` for the same rider under the same conditions than policy B, that rider is *more likely* to accept under A, and the comparison is a clean causal statement about the policy, not a coincidence of which random numbers happened to be drawn.
3. Demand generation itself (how many riders arrive, Section B) is **policy-independent by construction** (arrival rate `λ_z,t` never depends on pricing or dispatch policy) — so the same `(scenario, seed)` produces the *exact same sequence of ride requests* regardless of which of the 20 policy combinations is run against it. This is what makes the 24-seed core design a true paired design: for each seed, 20 policy combinations face literally the same riders, arriving at literally the same moments.
4. Where a policy-specific decision needs its own extra randomness (there currently is none beyond accept/reject draws — all dispatch policies are deterministic given state), no additional stream is needed. If one were added later, it would come from a clearly separate `rng_policy = default_rng(hash(scenario, seed, policy))` stream, never reusing or contaminating `rng_world`.

**Caveat, stated honestly:** CRN increases the *precision* of a comparison between two policies under the *same* random world — it does not increase the number of independent worlds observed. Twenty-four seeds still means twenty-four independent worlds; CRN just removes noise *within* each world-vs-world comparison, it doesn't manufacture additional independent evidence. This distinction is repeated in Section Q.

---

## Q. Statistical Analysis Plan

For a comparison between policy A and baseline policy B, run over the same 24 seeds:

1. **Per-seed paired difference:** `d_i = metric(A, seed_i) − metric(B, seed_i)`, for `i = 1..24`.
2. **Point estimate:** mean(`d_i`) and median(`d_i`) — report both, because a metric like P90 wait can be right-skewed across seeds (a few seeds with unusually bad congestion), and mean vs. median divergence is itself informative.
3. **Confidence interval:** **bootstrap percentile CI** (resample the 24 `d_i` with replacement, 10,000 resamples, take the 2.5th/97.5th percentile of resampled means) rather than a normal-theory CI — chosen because `n=24` is small enough that we should not assume the sampling distribution of the mean is normal, and bootstrap makes no such assumption.
4. **Significance test:** **paired Wilcoxon signed-rank test** as the primary test (robust to non-normal, small-sample paired data — exactly our situation), with a **paired t-test reported alongside** for readers more familiar with it, flagging if the two disagree (a disagreement itself would be a signal of a skewed/non-normal effect worth investigating, not something to paper over).
5. **Effect size:** report both **absolute effect** (e.g., "−1.4 minutes P90 wait") and **relative effect** (`mean(d_i)/mean(metric(B))`, e.g., "−14%"), plus a standardized effect size (**matched-pairs Cohen's d** = `mean(d_i)/std(d_i)`) so magnitude is comparable across metrics with different units.
6. **Practical-significance threshold, decided in advance (not after seeing results):** a policy change is only called "materially better" if it clears **both** (a) the 95% CI on the relative effect excludes 0, **and** (b) the relative effect is ≥ 5% in the metric's improving direction. A statistically significant but 1.2% change is reported honestly as "detectable but not practically meaningful," never rounded up to a headline claim.

**Honesty about power:** with 24 independent seeds, we can reliably detect effects on the order of ~10–15% or larger for typically-noisy metrics like P90 wait (this will be re-verified empirically in Phase 8 via the observed standard deviation of `d_i`, not asserted here). A "480 runs" headline number must never be read as "480 independent samples for any single comparison" — it is 24 independent samples, examined across 20 policy pairs. This caveat appears again in the final report's Limitations section.

---

## R. Primary Hypothesis (operationalized)

**Plain-language hypothesis:** "Dispatch optimization can reduce rider wait time without increasing incremental driver cost."

**Operationalized as a family of 4 paired tests** (one per pricing policy, since dispatch is compared *within* a fixed pricing policy to avoid confounding):

For each pricing policy `P ∈ {NO_SURGE, BASIC_SURGE, AGGRESSIVE_SURGE, CAPPED_SMOOTHED_SURGE}`, and each candidate dispatch policy `D ∈ {ETA_OPTIMIZED, DRIVER_EARNINGS_AWARE, MARKETPLACE_AWARE, ADVANCED_HEURISTIC}` vs. baseline `NEAREST_DRIVER`:

- **H0:** `median(P90_wait(P, D)) ≥ median(P90_wait(P, NEAREST_DRIVER))` across the 24 seeds (D does not improve the primary metric).
- **H1:** `median(P90_wait(P, D)) < median(P90_wait(P, NEAREST_DRIVER))`.

| Role | Metric |
|---|---|
| **Primary** | P90 rider wait time |
| **Secondary** | average wait, fulfillment rate, cancellation rate |
| **Guardrails (must not regress)** | driver earnings/online-hour, driver utilization, platform revenue |

**Practically meaningful improvement, decided in advance:** ≥5% reduction in P90 wait (Section Q's threshold), **and** no guardrail regressing by more than 2% (a small tolerance band, since some fluctuation is expected from re-routed drivers even under a genuinely neutral-cost policy). Success is **not** defined as "p < 0.05" alone — see Section Q.

---

## S. "No Incremental Driver Cost" — Precise Definition

This phrase is not used loosely. It is defined and measured as:

```
incremental_driver_cost(D vs NEAREST_DRIVER | P, seed) =
      Δ(total driver payout)
    + incentive_expense_delta          [= 0 in the core experiment — no incentive lever is toggled between dispatch policies]
    + Δ(required online driver-hours to serve the same completed-trip volume)
```

- `Δ(total driver payout)` is read directly from Section K's `driver_payout_total`, differenced across the paired seed.
- Incentive expense is **not a variable in the core dispatch comparison** — the same driver population, with the same shift schedules (drawn from the CRN world stream, Section P), is online under every dispatch policy; dispatch does not pay drivers anything beyond the standard fare split defined in Section J. So `incentive_expense_delta ≡ 0` by construction for the dispatch-only comparison, and this is stated as a *modeling fact*, not a claimed result.
- `Δ(required online driver-hours to serve the same completed-trip volume)` matters because a dispatch policy that requires *more* driver-hours to serve the same number of rides is imposing a real, if indirect, cost (more drivers need to be recruited/retained). This is measured via `Δ(driver_utilization)` at fixed online-hour supply (supply is exogenous per Section P, so this shows up as a utilization/throughput comparison, not an hours comparison).

**If the simulation shows driver payout and driver earnings/online-hour essentially unchanged (within the 2% guardrail tolerance) across dispatch policies at fixed pricing** — which is the model's structural default, since dispatch doesn't touch the fare formula — **then "no incremental driver cost" will be reported exactly as that: a structural property of comparing dispatch policies at fixed pricing, not a surprising empirical discovery.** The genuinely empirical, not-assumed part of the hypothesis is whether wait time and fulfillment actually improve — that part is left entirely to the data in Phase 7. If driver earnings *do* move measurably (e.g., because a policy changes trip-mix composition — more short trips vs. fewer long ones), that will be reported as a real, unexpected finding, not smoothed over.

---

## T. Causality Warning

**Simulation results are not real-world causal evidence.** Specifically:

- All demand, patience, price-sensitivity, and acceptance parameters (Sections B–E of `MATHEMATICAL_MODEL.md`) are **synthetic assumptions** chosen to be directionally plausible, not fit to any real ride-hailing dataset. A different (equally plausible) parameter choice could change magnitudes, and in edge cases, could change which policy wins.
- The model has **no feedback from long-run rider/driver churn** (a rider who has a bad week doesn't reduce their future baseline demand in this simulation; a driver who has a bad week doesn't leave the platform) — real marketplaces have exactly this feedback loop, and it is likely the single biggest source of "the simulation says X but reality could differ."
- **External validity** is limited to the *qualitative* mechanism (surge suppresses demand and pulls supply; better matching reduces wait without touching price) — this is well-supported by real marketplace economics literature — but the *quantitative* magnitude (e.g., "14% P90 wait reduction") is a property of this specific synthetic model and must never be quoted as a real-world prediction.
- **No calibration** against real trip/fare/wait data has been performed (none was available/appropriate to use per project scope) — this is flagged, not hidden.
- Real-world **confounders** absent here: weather, local events not modeled as explicit shocks, multi-platform competition (riders switching to a competitor instead of cancelling), regulatory price caps, driver multi-apping (working for two platforms simultaneously).

**How results are allowed to be used:** as evidence for *which lever is worth prototyping and A/B testing in production first*, and as a rigorous demonstration of experimental method — never as a claimed production outcome.

---

## U. Validation Plan (must pass before any experiment run counts as valid — Phase 4)

| # | Check | Expected direction | Pass criterion |
|---|---|---|---|
| 1 | ↑ demand, fixed supply | ↑ wait time | P90 wait increases monotonically across LOW→NORMAL→PEAK demand at fixed supply |
| 2 | Remove surge (NO_SURGE) | supply unaffected in same tick (surge doesn't retroactively pull drivers online in this model) | online driver count identical across pricing policies at same seed (supply is priced-independent — an explicit modeling fact, checked, not assumed) |
| 3 | Very high price | ↓ rider acceptance | synthetic single-request test: `P_accept` at surge=3.0 < `P_accept` at surge=1.0 for the same rider/wait |
| 4 | ↑ driver supply, fixed demand | ↓ wait time | P90 wait decreases monotonically across SHORTAGE→NORMAL supply at fixed demand |
| 5 | NEAREST_DRIVER minimizes pickup distance **among available-only policies** | `avg_pickup_distance(NEAREST_DRIVER) ≤ avg_pickup_distance(DRIVER_EARNINGS_AWARE)` and `≤ MARKETPLACE_AWARE`, same scenario/seed. **Refined during Phase 4:** the two look-ahead policies (`ETA_OPTIMIZED`, `ADVANCED_HEURISTIC`) are *exempt* from this check — they can legitimately beat pure-nearest on realized pickup distance because they also consider drivers about to free up nearby, a larger candidate set than "currently idle" alone. This was an empirical discovery, not an assumption, and is recorded in `CHANGELOG.md`. | verified directly from run output |
| 6 | Surge never exceeds cap | `max(surge_multiplier) ≤ policy cap` for every tick, every zone | assert over full run history |
| 7 | Utilization bounded | `0 ≤ driver_utilization ≤ 1` for every driver | assert over all drivers, all runs |
| 8 | No double-booking | every driver has ≤ 1 active request at any tick | assert over full run history |
| 9 | No orphan trips | every `COMPLETED` trip traces to a `Request` that was actually generated in step 2 of some tick | assert via foreign-key-style check on IDs |
| 10 | Reproducibility | same seed + config → bit-identical metrics across two runs | run twice, diff the output tables |

**If any check fails, the engine is debugged before any of the 1,080 experiment runs are treated as valid** — this gate is enforced procedurally in Phase 4, not just documented here.

---

## V. Parameter Table

The full, single source-of-truth parameter table (used to configure `src/config.py`) lives in `ASSUMPTIONS.md` §Parameter Table, cross-referenced here so there is exactly one place parameters can drift out of sync. Every row there is labeled **SYNTHETIC ASSUMPTION** unless a public source is cited (none are, in v1 — no public source was used for any behavioral parameter).

---

## W. Sensitivity Analysis Plan

After the core + robustness experiments, a **dedicated sensitivity sweep** (documented as Experiment 12 in the results phase) perturbs the most uncertain parameters one at a time (±30% from base value, holding all else fixed, 6 seeds each) for the winning policy combination identified in Phase 7:

| Parameter | Why most uncertain |
|---|---|
| `β_price` (price elasticity) | No real elasticity data used — pure synthetic assumption, and the single biggest lever on how much surge suppresses demand |
| Rider patience `τ_i` distribution | Directly sets the cancellation curve's inflection point; no behavioral data behind it |
| Driver acceptance sensitivity (`γ_pickup`, `γ_fare`) | Determines how strongly drivers reject long pickups — central to why dispatch policy should matter at all |
| Congestion multiplier magnitude | Affects how much `CONGESTED_PEAK` differs from `PEAK_DEMAND` |
| `λ_base,z` demand intensity | Sets the absolute scale of the whole simulation; a 2x change could shift which regime (supply-constrained vs. demand-constrained) the marketplace sits in |
| Driver supply intensity (fleet size) | Same reasoning, supply side |

**Why this matters:** a headline result that flips sign under a ±30% perturbation of an assumption we made up is a fragile result and must be reported as such — this sweep is what stands between "the simulation shows X" and "the simulation shows X, and X is robust to our biggest modeling uncertainties."

---

## X. Product Decision Framework

**Primary objective:** maximize `completed_trips / online_driver_hour` (North Star).

**Subject to (guardrail constraints, thresholds set from the NORMAL/BASIC_SURGE/NEAREST_DRIVER baseline observed in Phase 4/6 — not arbitrary):**

```
P90_wait          ≤ baseline_P90_wait × 1.00      (must not get worse than today)
earnings_per_hour ≥ baseline_earnings_per_hour × 0.98      (small tolerance band)
cancellation_rate ≤ baseline_cancellation_rate × 1.05
platform_revenue  ≥ baseline_platform_revenue × 0.98
```

**Decision rule:** among all policy combinations satisfying every constraint, select the one maximizing the North Star; report the full ranked table (not just the winner) so the trade-off is visible. **No arbitrary weighted single score is used** — a weighted score would hide exactly the trade-offs (Part 14's decision matrix) that are the actual product point of this project. Baseline threshold values are computed empirically in Phase 4 from the NORMAL-scenario baseline run and hard-coded into `src/config.py` with a comment citing this section — they are **decision assumptions**, explicitly labeled as such, not laws of physics.

---

## Expected Outputs Checklist (for this phase)

- [x] `docs/MATHEMATICAL_MODEL.md`
- [x] `docs/EXPERIMENT_DESIGN.md` (this file)
- [x] `docs/ASSUMPTIONS.md`
- [x] Parameter table (in `ASSUMPTIONS.md`)
- [x] Metric dictionary (`MATHEMATICAL_MODEL.md` §L)
- [x] Policy comparison table (§O policies, §H per-policy strengths/weaknesses)
- [x] Experiment matrix (§O)
- [x] State transition diagram (`MATHEMATICAL_MODEL.md` §E, ASCII)
- [x] Timestep flow diagram (`MATHEMATICAL_MODEL.md` §A, numbered sequence — ASCII diagram also added to `ASSUMPTIONS.md` for a single visual reference)
