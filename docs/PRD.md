# Product Requirements Document — Ride-Hailing Surge Pricing & Dispatch Simulator

## 1. Executive Summary

Marketplace teams at ride-hailing platforms must decide how to close supply/demand gaps: raise prices, pay drivers more, or improve matching. The first two show up immediately in a P&L; the third is a software investment whose payoff is hard to prove without a controlled experiment. This project builds a simulation and experimentation platform to run that experiment safely, then uses it to answer a specific question: **can dispatch quality reduce rider wait time without increasing driver-side or pricing-side cost?** After 1,080 simulated experiments, the answer in this model is **yes** — a look-ahead dispatch policy (`ETA_OPTIMIZED`) reduces P90 wait by 7.8–11.3% across every pricing policy tested, with driver earnings and platform revenue both *improving*, not degrading. The recommendation is to prioritize a production dispatch experiment over further pricing changes.

## 2. Problem Statement

See `README.md` "Why this project exists" for the short version. In full: a ride-hailing marketplace is a two-sided market where rider wait time and driver earnings/utilization are in tension whenever supply and demand are imbalanced. The platform has three levers — surge pricing, driver incentives, and dispatch/matching — of very different cost profiles, and production experimentation with any of them is expensive and risky (real riders and drivers are affected during the test). A safe, fast, statistically rigorous simulation sandbox lets a marketplace team screen ideas before committing production experimentation budget to them.

## 3. User Personas

| Persona | Primary question this tool answers for them |
|---|---|
| Marketplace PM | "Which lever should we invest in this quarter?" |
| Pricing PM | "Is our surge cap too conservative or too aggressive?" |
| Dispatch/Optimization DS/Engineer | "Does my new matching algorithm actually help, and by how much?" |
| Driver Ops / Growth PM | "Does this change hurt driver earnings?" |
| City Ops Manager | "Which zones are chronically undersupplied?" |
| Data Science / Risk | "Is this result real, or noise?" |

## 4. User Pain Points

- No clean way to isolate the effect of a dispatch change from a pricing change in live/production data — everything is confounded by whatever else changed that week.
- Production A/B tests on dispatch are expensive to set up and risky to run at scale before there's reasonable prior confidence the idea works.
- "It felt faster" is not evidence; teams need P90-level, statistically tested claims before recommending a launch.

## 5. Business Objective

Increase marketplace efficiency (successful rides per unit of driver supply) without increasing the platform's price to riders or its cost per driver-hour — because dispatch improvements, unlike surge or incentives, have near-zero marginal cost per ride once built.

## 6. Product Hypothesis

> A better dispatch policy can reduce rider wait time and/or increase completed rides without increasing platform pricing (surge) or driver-side cost (incentives) beyond baseline.

Stated as falsifiable (`docs/EXPERIMENT_DESIGN.md` §R), tested experimentally (`docs/EXPERIMENTS.md`), not assumed true in advance.

## 7. Goals

- Build a simulation credible enough that its qualitative conclusions (which lever helps, in which direction) transfer to a real production hypothesis worth A/B testing.
- Produce a statistically defensible answer to the core hypothesis, with honest confidence intervals and effect sizes — not just a point estimate.
- Make every design decision (why this metric, why this dispatch policy, why this statistical test) explainable without hand-waving.

## 8. Non-Goals

- **Not** a claim about any real ride-hailing company's actual metrics, elasticities, or fleet size.
- **Not** a production-ready dispatch system — the heuristics here are a research/exploration tool, not code meant to run a real fleet.
- **Not** modeling driver supply's response to price (see `docs/EXPERIMENTS.md` Experiment 2) — this is an explicit, documented scope cut, not an oversight.
- **Not** a multi-platform competitive model (no rider "switches to a competitor" behavior).

## 9. Functional Requirements

1. Simulate a 10-zone city with time-of-day-varying, Poisson-distributed ride demand.
2. Support 4 configurable pricing policies and 5 configurable dispatch policies, selectable independently.
3. Run a reproducible experiment matrix across policies × scenarios × seeds and persist full results.
4. Compute a fixed, documented set of rider/driver/platform/marketplace metrics identically regardless of policy.
5. Provide a statistical analysis layer producing confidence intervals, significance tests, and effect sizes for any policy comparison.
6. Provide an interactive dashboard to run ad-hoc simulations and browse experiment results.
7. Provide an API for programmatic access to simulation and results.
8. Provide a natural-language interface (AI copilot) over the results that never fabricates a number.

## 10. Non-Functional Requirements

- **Reproducibility:** identical seed + config → bit-identical output (tested).
- **Performance:** a full 24-simulated-hour run completes in well under 1 second; the full 1,080-run matrix completes in single-digit minutes on a laptop.
- **Explainability:** every metric, equation, and policy choice has a documented rationale (`docs/MATHEMATICAL_MODEL.md`, `docs/ASSUMPTIONS.md`).
- **Testability:** invariants (no negative price, surge within cap, bounded utilization, no double-booking, etc.) are enforced and tested, not just assumed.

## 11. Metrics

**North Star:** Completed trips per online driver-hour — see `docs/MATHEMATICAL_MODEL.md` §M for the full critical evaluation against four alternatives.
**Guardrails:** P90 rider wait time, rider cancellation rate, driver earnings/online-hour, driver acceptance rate, price index — see §N for why these five and not twenty.

## 12. Experiment Plan

See `docs/EXPERIMENT_DESIGN.md` in full. Summary: 480-run core hypothesis test (4 pricing × 5 dispatch × 24 common-random-number seeds, `NORMAL` scenario) + 600-run robustness sweep across 5 stress scenarios.

## 13. Decision Matrix — Which Lever Should the Platform Pull?

Populated with actual simulation results (`docs/EXPERIMENTS.md`), comparing the three levers at the point where each produces a meaningful supply/demand response:

| Lever | Wait time | Revenue | Driver cost | Rider conversion | Marketplace health | Simulated in this project? |
|---|---|---|---|---|---|---|
| **Higher surge** (AGGRESSIVE_SURGE vs. NO_SURGE) | ↓ (indirectly, via less congestion) | ↑ +6.0% | ≈ (surge premium shared with drivers by construction, §J) | ↓ slightly (−0.33pp) | Mixed — real revenue/cancellation gains, but no modeled supply response and a real brand/regulatory risk not captured here | Yes — Experiments 1, 3 |
| **Better dispatch** (ETA_OPTIMIZED vs. NEAREST_DRIVER) | **↓↓ −7.8% to −11.3%** | **↑ +2.7%** (BASIC_SURGE) | **≈/↓** (earnings/hr **+1.9%**) | not directly tested (dispatch doesn't change price) | **↑** — fewer cancellations, higher fulfillment, no new supply required | Yes — Experiment 4, the project's core finding |
| **Driver incentive** (pay drivers extra to come online) | Would ↓ (more supply) | ↑ (more completed rides) but **↑ direct cash cost** | **↑↑** (explicit new spend) | ↑ (shorter waits) | ↑, but at a real, ongoing dollar cost per driver-hour | **Not simulated** — v1 has no driver online-probability-vs-incentive model (Experiment 2 limitation) |

**Reading the matrix:** dispatch is the only lever in this model that improves wait time *and* revenue *and* driver earnings simultaneously, at zero incremental marginal cost once built. Surge is a real, working lever here too, but converts to revenue rather than wait-time relief. Incentives could not be evaluated on the same footing because the model doesn't yet include a driver supply-response mechanism — flagged, not glossed over.

## 14. Recommendation

**Launch:** a production shadow-mode / small-percentage A/B test of an ETA-and-look-ahead-aware dispatch policy (the production analogue of `ETA_OPTIMIZED`), prioritized ahead of further pricing-policy changes.
**Why:**
1. 7.8–11.3% lower P90 wait across every pricing regime tested, with p < 0.001 and large effect sizes.
2. Driver earnings/online-hour *improved* (+1.9%), not degraded — no driver-side cost.
3. Cancellation rate fell (a **relative** 4.7% reduction under BASIC_SURGE), improving fulfillment.
4. Platform revenue improved (+2.7%) as a side effect of fewer cancelled/unmatched rides, not a fare increase.

**Do not launch (yet):** `ADVANCED_HEURISTIC` — it underperformed the naive baseline in every configuration tested (`docs/EXPERIMENTS.md`, "Advanced Heuristic finding"). This is exactly the kind of result simulation is for catching before it reaches riders.

**Test next:** the sensitivity sweep (Experiment 12, not yet run) before finalizing a magnitude claim for a real production business case; a small real-world shadow-mode test of `ETA_OPTIMIZED`'s core mechanism (looking ahead to soon-to-be-free drivers) to check whether real driver acceptance behaves the way the synthetic model assumes.

**Real-world data that would sharpen this recommendation:** actual rider price-sensitivity/cancellation curves (from historical fare experiments), actual driver pickup-distance acceptance/rejection logs, and any existing driver-supply-vs-incentive elasticity estimates.

## 15. A/B Test Design for a Production Follow-Up

**Note: this simulation does not prove a production causal effect — it is evidence for what to test next, not a substitute for testing it.**

- **Experiment unit:** driver-side randomization by driver ID (cleaner than rider-side because dispatch operates on the driver-request pairing) within a single city, stratified by zone to balance geography across arms.
- **Control:** current production dispatch (nearest-driver-equivalent). **Treatment:** ETA/look-ahead dispatch.
- **Primary metric:** P90 rider wait time. **Guardrails:** driver earnings/online-hour, cancellation rate, platform revenue, driver acceptance rate.
- **Sample size:** powered off the *real* production variance of P90 wait (not this simulation's), targeting the ability to detect a 5% relative change at 80% power, α=0.05 — must be computed from real pre-period data before launch.
- **Duration:** at least 2 full weekly cycles, to average out day-of-week effects (weekday commute patterns vs. weekend nightlife patterns, both present in this project's own zone model).
- **Contamination risk:** drivers who serve multiple zones/times could be exposed to both arms if randomization is by trip rather than by driver — mitigated by driver-level (not trip-level) randomization.
- **Novelty effects:** a new dispatch behavior might temporarily confuse ops/support workflows before drivers adapt — monitor cancellation rate and driver support-ticket volume in week 1 specifically.
- **Rollout:** see §16.

## 16. Rollout Strategy

| Phase | Scope | Success criteria | Rollback criteria | Monitoring |
|---|---|---|---|---|
| 0 — Offline simulation | This project | Statistically + practically significant improvement in simulation | N/A | N/A |
| 1 — Shadow mode | 100% of traffic, decisions logged but not acted on | Shadow-computed dispatch decisions differ from production in the expected direction (shorter predicted pickup) without engine errors | Any crash/latency regression in the shadow service | Shadow-vs-production decision diff rate, latency |
| 2 — 1% live traffic | 1 city, 1% of trips | P90 wait improves or holds, no guardrail regression, at the smallest detectable scale | Any guardrail regression beyond noise band | Real-time dashboards on all 5 guardrails |
| 3 — 5% | Same city | Guardrails hold at higher volume; no ops/support ticket spike | Guardrail regression, support ticket spike | Same + support ticket volume |
| 4 — 25% | Same city, then a second city | Effect size consistent with simulation's predicted direction (magnitude may differ) | Any guardrail regression | Same + cross-city consistency check |
| 5 — 100% | Full city, then broader rollout | Sustained guardrail health over 2+ weeks | Any guardrail regression | Same, moved to standard ops dashboards |

## 17. Failure Modes

| Problem | Detection | Mitigation |
|---|---|---|
| Surge causes demand collapse | Rider conversion rate guardrail | Auto-revert to previous surge cap if conversion drops beyond threshold |
| Dispatch starves certain zones | Per-zone fulfillment rate monitoring (not yet built as a live guardrail — flagged in Future Roadmap) | Marketplace-aware penalty term (already in `ADVANCED_HEURISTIC`/`MARKETPLACE_AWARE`, though the former needs re-tuning per Experiments doc) |
| Drivers reject too many trips | Driver acceptance rate guardrail | Investigate pickup-distance distribution; consider earnings-aware dispatch |
| Optimizes average wait but worsens P90 | P90 is the *primary* metric specifically to prevent this | N/A by design |
| High-value riders receive worse service | Not currently segmented/monitored | Future work: report metrics segmented by rider segment, not just pooled |
| Model drift (real-world parameters diverge from synthetic assumptions) | Periodic recalibration against real data (not yet built) | Sensitivity analysis (Experiment 12) bounds how much this could matter |
| Demand/supply shocks | Explicitly modeled scenarios (Experiments 7–9) | Confirmed dispatch improvement holds under shock, with lower confidence (fewer seeds) |
| GPS/ETA prediction errors | Not modeled (ETAs are analytically computed from distance, not "measured") | Flagged as a simplification in `docs/ASSUMPTIONS.md` |
| Feedback loops (bad experience → less future demand) | Not modeled — flagged as the top limitation | Future work: multi-day simulation with a demand-decay mechanism |

## 18. Ethics & Fairness Considerations

- **Price discrimination:** this model does not implement rider-specific pricing (no personalization by rider history/willingness-to-pay) — a deliberate scope decision, and a real product would need a fairness review before ever doing so.
- **Geographic fairness:** `MARKETPLACE_AWARE` and `ADVANCED_HEURISTIC` exist specifically to prevent dispatch from silently underserving low-liquidity zones in favor of easy, dense ones — though `ADVANCED_HEURISTIC`'s current weights need retuning (Experiments doc).
- **Algorithmic bias:** none of the dispatch policies here condition on any rider or driver demographic attribute — the only inputs are trip geometry, price, timing, and marketplace state.
- **Driver fairness:** `DRIVER_EARNINGS_AWARE` improves acceptance-likelihood matching, but risks concentrating better-paying trips among fewer drivers if left unchecked — flagged in Math Model §H.3 and worth a fairness metric (e.g., earnings Gini coefficient across drivers) before a real launch.
- **Surge during emergencies:** the surge caps (2.0–3.0×) exist partly for exactly this reason — real platforms have faced public criticism for uncapped surge during emergencies; this project treats a cap as a non-negotiable product requirement, not a nice-to-have.
- **Accessibility:** not explicitly modeled — a real deployment would need to verify dispatch/pricing doesn't disproportionately affect riders who need wheelchair-accessible vehicles or have limited smartphone literacy.

## 19. Risks

- Synthetic parameters could be wrong in ways that flip a qualitative conclusion — mitigated by (planned) sensitivity analysis, not yet executed.
- Missing driver-supply-response mechanism limits how much this model can say about incentives vs. dispatch.
- Small robustness-scenario seed counts (6) limit statistical confidence outside the core `NORMAL` scenario.

## 20. Dependencies

Python 3.11+, numpy/pandas/scipy/scikit-learn, FastAPI, Streamlit, Plotly, Anthropic API (for the AI copilot only — everything else runs with no external API dependency).

## 21. Future Roadmap

1. ~~Sensitivity analysis (Experiment 12)~~ — **done**: sign of the core finding survives ±30% perturbation of all 6 most-uncertain parameters (`docs/EXPERIMENTS.md` Experiment 12). Next increment: combined worst-case perturbations, not yet tested.
2. Driver supply-response-to-price/incentive model, to make the incentive-vs-dispatch comparison in §13 complete. *(Highest-priority remaining item.)*
3. Multi-day simulation with a churn/retention feedback loop.
4. Per-zone live fulfillment guardrail in the dashboard.
5. Rider-segment-level (not just pooled) metric reporting, for the fairness considerations in §18.
6. Retune or retire `ADVANCED_HEURISTIC`'s weights based on the Experiments-doc finding.
7. Re-run robustness scenarios (Experiments 7–10) with 24 seeds instead of 6, to remove the "not statistically significant" caveat currently attached to two of them.
