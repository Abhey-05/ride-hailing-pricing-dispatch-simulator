# Assumptions, City Model, Parameter Table & Learning Notes

Every numeric value in this document is a **SYNTHETIC ASSUMPTION** chosen for directional realism and internal consistency — none are sourced from a real ride-hailing company's actual data. Where a value is a genuine judgment call, the rationale is given so it can be defended or revised.

---

## Zone Model — 10 Zones

Coordinates are on an arbitrary unit grid, `grid_scale_km = 1.2` (Section F of `MATHEMATICAL_MODEL.md`).

| Zone ID | Name | Archetype | Coord (x,y) | Baseline demand `λ_base` (req/hr) | Baseline driver share |
|---|---|---|---|---|---|
| Z0 | Downtown | Commercial/CBD | (5, 5) | 40 | 18% |
| Z1 | Airport | Airport | (9, 1) | 22 | 8% |
| Z2 | University | University | (2, 7) | 26 | 9% |
| Z3 | Residential North | Residential | (3, 9) | 30 | 13% |
| Z4 | Residential South | Residential | (3, 1) | 28 | 12% |
| Z5 | Suburban East | Suburban | (9, 6) | 14 | 8% |
| Z6 | Suburban West | Suburban | (1, 4) | 14 | 8% |
| Z7 | Transit Hub | Transit hub | (6, 8) | 24 | 8% |
| Z8 | Nightlife District | Nightlife/commercial | (7, 3) | 20 | 8% |
| Z9 | Business Park | Commercial (office) | (6, 2) | 26 | 8% |

"Baseline driver share" seeds how the initial/shift-start driver population is distributed across zones (drivers start their shift near where they live/park, itself an archetype-weighted synthetic choice — commercial-zone-adjacent shares are slightly higher since more drivers position near the CBD).

### Time-of-day periods (shared skeleton, archetype-specific multipliers below)

| Period | Hours | 
|---|---|
| `late_night` | 00:00–05:00 |
| `morning_ramp` | 05:00–07:00 |
| `morning_peak` | 07:00–10:00 |
| `midday` | 10:00–16:00 |
| `evening_peak` | 16:00–19:00 |
| `evening_wind_down` | 19:00–22:00 |
| `night` | 22:00–24:00 |

`TOD(z, hour)` is computed by **linearly interpolating** between each period's multiplier value, anchored at each period's midpoint — this avoids an unrealistic instantaneous jump at period boundaries (e.g., demand doesn't teleport from "midday" to "evening_peak" at exactly 16:00:00, it ramps).

### Archetype TOD multiplier table

| Archetype | late_night | morning_ramp | morning_peak | midday | evening_peak | evening_wind_down | night |
|---|---|---|---|---|---|---|---|
| Commercial/CBD | 0.2 | 0.6 | 1.9 | 1.1 | 1.7 | 0.9 | 0.4 |
| Airport | 0.5 | 0.8 | 1.1 | 1.3 | 1.2 | 1.0 | 0.7 |
| University | 0.3 | 0.5 | 1.3 | 1.0 | 1.1 | 1.4 | 0.8 |
| Residential | 0.2 | 1.5 | 1.8 | 0.7 | 1.6 | 1.0 | 0.4 |
| Suburban | 0.15 | 1.2 | 1.4 | 0.6 | 1.3 | 0.8 | 0.3 |
| Transit hub | 0.2 | 1.6 | 2.0 | 0.8 | 1.9 | 1.0 | 0.3 |
| Nightlife | 0.6 | 0.2 | 0.3 | 0.6 | 0.9 | 1.6 | 2.2 |

**Rationale:** Residential and Transit hub peak sharply in the morning (commute out) and evening (commute back); Commercial/CBD is the mirror image (people arrive in the morning, leave in the evening) — this asymmetry is what generates the directional flow patterns below. Airport demand is flatter and less peaked (flights run all day) with a slight afternoon/evening bump (typical leisure travel patterns). Nightlife inverts the whole city's rhythm, peaking late night — included specifically so "late night" isn't uniformly low-demand city-wide, which would be unrealistic.

### Directional flow (origin → destination weighting by period, illustrative subset)

| Origin | morning_peak top destination(s) | evening_peak top destination(s) |
|---|---|---|
| Residential North/South | Downtown (45%), Business Park (25%), University (15%) | reversed (Downtown/Business Park → Residential North/South, 55% combined) |
| University | Downtown (30%), stays local (30%) | Nightlife (20%), Residential (30%) |
| Transit Hub | Downtown/Business Park (60%) | Residential North/South (50%) |
| Downtown/Business Park | (low outbound in morning — it's a destination) | Residential North/South (55%), Suburban (20%) |

Implemented as a per-(origin, period) categorical distribution over the 10 zones; remaining probability mass spread across other zones proportional to their baseline demand share, so every (origin, destination) pair is reachable (no zone is fully cut off), just weighted realistically.

### Congestion by period (Section F of `MATHEMATICAL_MODEL.md`)

| Period | Congestion multiplier |
|---|---|
| late_night / night | 1.0 |
| morning_ramp | 1.1 |
| morning_peak | 1.35 |
| midday | 1.1 |
| evening_peak | 1.35 |
| evening_wind_down | 1.15 |

---

## Driver Population Assumptions

- **Fleet size (NORMAL scenario, supply_mult=1.0):** 260 drivers total, distributed per the "baseline driver share" column above.
- **Shift length distribution:** `{6h: 30%, 8h: 45%, 10h: 25%}` (categorical, drawn per driver at creation).
- **Shift start time distribution:** mixture of three normal-ish clusters (`Normal(7,1.5)h`, `Normal(15,1.5)h`, `Normal(20,1.5)h`, truncated to [0,24), equal weight) — models drivers starting around morning peak, afternoon, or evening, rather than uniformly around the clock (which would be unrealistic — driver supply has its own rhythm too, just less peaked than demand).
- **Rider segment shares:** `price_sensitive 30% / normal 50% / time_sensitive 20%` (Mathematical Model §C).
- **Rider patience `τ_i`:** `LogNormal` with segment-specific median: `price_sensitive` 8 min, `normal` 6 min, `time_sensitive` 4 min (time-sensitive riders are impatient almost by definition — it's the same trait expressed two ways: they pay more to avoid waiting, *and* they give up faster if made to wait), `σ=0.4` (log-scale) for all segments.

---

## Parameter Table (single source of truth)

| Parameter | Value | Unit | Distribution/Form | Rationale | Sensitivity tested? |
|---|---|---|---|---|---|
| `Δt` | 1 | min | fixed | Standard fine-grained tick for a marketplace this size | No (structural) |
| `base_fee` | 40 | currency | fixed | **SYNTHETIC ASSUMPTION** | No |
| `distance_rate` | 9 | currency/km | fixed | **SYNTHETIC ASSUMPTION** | No |
| `time_rate` | 1.5 | currency/min | fixed | **SYNTHETIC ASSUMPTION** | No |
| `commission_rate` | 0.25 | ratio | fixed | **SYNTHETIC ASSUMPTION**, common industry ballpark, not sourced | No |
| `grid_scale_km` | 1.2 | km/unit | fixed | Sets city as "small and dense" | No |
| `v_base` | 28 | km/h | fixed | **SYNTHETIC ASSUMPTION**, plausible urban avg incl. stops | No |
| `β0` (accept baseline) | 2.2 | logit | fixed | Tuned so baseline acceptance ≈ 90% | No |
| `β_price` | 0.6 / 1.1 / 2.2 | logit/unit surge | segment-specific | **SYNTHETIC** — biggest driver of demand response | **Yes (§W)** |
| `β_wait` | 1.5 / 0.8 / 0.4 | logit/(W/W_ref) | segment-specific | **SYNTHETIC** | No |
| `τ_i` median | 4 / 6 / 8 | min | LogNormal, segment-specific | **SYNTHETIC** — sets cancellation curve inflection | **Yes (§W)** |
| `P_max_pre` | 0.35 | prob/tick | fixed | Ceiling on abandonment hazard | No |
| `P_max_post` | 0.12 | prob/tick | fixed | Lower — post-match commitment effect | No |
| `γ0..γ_util` (driver accept) | 1.5, 1.8, 2.0, 0.7, 0.5 | logit weights | fixed | **SYNTHETIC** — central to why dispatch policy matters | **Yes (§W, γ_pickup/γ_fare)** |
| `commission split direction` | surge shared 75/25 same as base | policy choice | fixed | Deliberate simplification, documented | No |
| `fleet size` (NORMAL) | 260 | drivers | fixed per scenario | **SYNTHETIC**, sized so NORMAL scenario sits near imbalance≈1 (balanced) at peak — verified in Phase 4 | **Yes (§W, supply intensity)** |
| Surge caps | 2.0 / 3.0 / 2.5 | multiplier | per-policy, §G | Product-rationale documented in Math Model §G | No |
| Congestion mult. | 1.0–1.35 | ratio | period table above | **SYNTHETIC** | **Yes (§W)** |
| `λ_base,z` | 14–40 | req/hr | per zone, table above | **SYNTHETIC**, archetype-driven | **Yes (§W, demand intensity)** |

---

## One-Page Mathematical Cheat Sheet

```
ARRIVALS:      N_z,t ~ Poisson(λ_base,z · TOD(z,hr) · scenario_mult · Δt)
PRICE:         final_price = (base_fee + distance_rate·dist + time_rate·dur) · surge
IMBALANCE:     imbalance(z,t) = outstanding_requests / (available_drivers + 1)
SURGE (basic): surge = clip(1 + 0.5·(imbalance − 1), 1.0, 2.0)
RIDER ACCEPT:  P = σ(2.2 − β_price·(surge−1) − β_wait·(W_exp/5))
CANCEL:        P_abandon(w) = 0.35 · σ(3·(w−τ)/τ)      [per tick, while WAITING]
DRIVER ACCEPT: P = σ(1.5 + 1.8·fare_norm − 2.0·eta_norm + 0.7·A_dest − 0.5·util)
TRAVEL TIME:   t_min = (dist_km / (28/congestion)) · 60 · LogNormal(0,0.15)
DRIVER PAY:    payout = 0.75 · final_price          (commission = 25%)
UTILIZATION:   active_time / online_time,  active = EN_ROUTE + ON_TRIP
NORTH STAR:    completed_trips / Σ driver_online_hours
```

## One-Page Experiment Cheat Sheet

```
CORE:        4 pricing × 5 dispatch × 24 seeds = 480 runs, scenario = NORMAL
ROBUSTNESS:  5 stress scenarios × 20 policy combos × 6 seeds = 600 runs
TOTAL:       1,080 runs
BASELINE:    BASIC_SURGE × NEAREST_DRIVER
PRIMARY METRIC:   P90 rider wait time
GUARDRAILS:       earnings/hr, utilization, revenue, cancellation, price index
SIG. TEST:        paired Wilcoxon signed-rank (+ paired t-test alongside)
CI METHOD:        bootstrap percentile, 10,000 resamples
PRACTICAL BAR:    ≥5% relative improvement AND CI excludes 0 AND guardrails within 2%
```

## ASCII Diagrams

### Timestep flow

```
┌─► 1.Clock/TOD ─► 2.Gen requests ─► 3.Resolve driver states ─► 4.Marketplace state
│                                                                        │
│                                                                        ▼
│   11.Cancellations ◄─ 10.Advance trips ◄─ 9.Driver accept? ◄─ 8.Dispatch ◄─ 7.Rider accept? ◄─ 6.Price ◄─ 5.Surge
│         │
└─────────┴──► 12.Record metrics ──► (next tick)
```

### Driver state machine

```
              dispatched            accepts
 OFFLINE ──► AVAILABLE ──────────► ASSIGNED ─────────► EN_ROUTE_TO_PICKUP ──(ETA elapses)──► ON_TRIP
    ▲            ▲                    │                                                          │
    │            └────rejects─────────┘                                                          │
    └───────────────────(shift ends)───────────────────────────────(trip completes)◄─────────────┘
```

### Request state machine

```
WAITING ──abandon──► ABANDONED
   │
   ├──rejects priced offer──► REJECTED_OFFER
   │
   └──dispatched & driver accepts──► MATCHED ──cancels──► CANCELLED_POSTMATCH
                                         │
                                         └──pickup complete──► ON_TRIP ──► COMPLETED
```

---

## Product Decision Framework (recap — full version in `EXPERIMENT_DESIGN.md` §X)

Maximize North Star subject to guardrail thresholds anchored to the NORMAL/BASIC_SURGE/NEAREST_DRIVER baseline; report the full ranked table, not a single weighted score.

---

## WHAT I MUST UNDERSTAND BEFORE PHASE 3

### 1. Poisson process
**Simple:** a way to model "random events happening at some average rate, independently of each other" — like raindrops hitting a small patch of ground.
**Technical:** a counting process where the number of events in a fixed interval follows the Poisson distribution `P(N=k) = (λt)^k e^(-λt) / k!`, with independent increments.
**This project:** ride requests arriving in each zone each minute — `N_z,t ~ Poisson(λ_z,t · Δt)`.
**Interview Q:** "Why Poisson and not just a fixed number of requests per hour?" → Poisson captures realistic randomness (some minutes get 3 requests, some get 0) rather than an unrealistically smooth, deterministic arrival pattern.

### 2. Logistic function
**Simple:** an S-shaped curve that turns "any number" into "a probability between 0 and 1."
**Technical:** `σ(x) = 1/(1+e^-x)`; as x→∞, σ→1; as x→-∞, σ→0; σ(0)=0.5.
**This project:** every accept/reject/cancel probability (rider acceptance, driver acceptance, cancellation) is a logistic function of some weighted score.
**Interview Q:** "Why logistic instead of a simple linear probability?" → Linear probability can go below 0% or above 100%, which is nonsensical; logistic is automatically bounded and has the right diminishing-returns shape.

### 3. Price elasticity
**Simple:** how much demand drops when price rises.
**Technical:** `% change in quantity demanded / % change in price`; elastic markets (|elasticity|>1) see demand fall faster than price rises.
**This project:** the `β_price` coefficient in the rider acceptance logistic *is* our elasticity parameter — bigger `β_price` = more elastic (price-sensitive) segment.
**Interview Q:** "Which rider segment is most elastic in your model?" → `price_sensitive` (β_price=2.2), by construction.

### 4. Supply-demand imbalance
**Simple:** are there more riders wanting rides than drivers available, or the reverse?
**Technical:** in this project, `imbalance = outstanding_requests/(available_drivers+1)` — a ratio, not a difference, so it's scale-invariant (a zone with 2 requests/1 driver and one with 20/10 are equally imbalanced).
**This project:** drives the surge formula directly.
**Interview Q:** "Why a ratio instead of a difference (requests − drivers)?" → A ratio doesn't need separate calibration for small vs. large zones; a difference of "5 more requests than drivers" means something very different in a 10-driver zone vs. a 200-driver zone.

### 5. Dynamic pricing
**Simple:** prices that change in real time based on conditions, instead of being fixed.
**Technical:** here, a function of the imbalance signal, updated on a policy-specific cadence, bounded by caps.
**This project:** the four pricing policies.
**Interview Q:** "What's the risk of dynamic pricing updating too fast?" → Price "flickering" that riders perceive as unfair/random — exactly why `CAPPED_SMOOTHED_SURGE` exists.

### 6. Dispatch optimization
**Simple:** deciding which driver should be sent to which rider.
**Technical:** an assignment problem — matching two sets (requests, drivers) to maximize/minimize some objective, subject to one-to-one constraints.
**This project:** the 5 dispatch policies, each a different objective/scoring function.
**Interview Q:** "What's actually being optimized?" → Depends on the policy — pickup ETA, driver acceptance probability, zone-level future imbalance, or a weighted blend (§H.5).

### 7. Heuristic
**Simple:** a "good enough, fast" rule instead of a mathematically perfect (but slow) solution.
**Technical:** an approximation algorithm without a global-optimality guarantee, chosen for speed/practicality.
**This project:** all 5 dispatch policies are heuristics — none solves the exact bipartite matching problem.
**Interview Q:** "Why not the exact optimal assignment?" → `O((R+D)³)` per tick doesn't scale, and the state is stale again a minute later anyway (§H.5).

### 8. Simulation (and Monte Carlo simulation)
**Simple:** running a model of a system many times with randomness to see the range of things that could happen.
**Technical:** Monte Carlo = using repeated random sampling to estimate a quantity that's hard to compute analytically.
**This project:** each of our 1,080 runs is one Monte Carlo trial; aggregating across seeds is exactly Monte Carlo estimation of expected policy performance.
**Interview Q:** "Why not just run the simulation once?" → One run is one random draw from a huge space of possible days — you'd be fooled by luck.

### 9. Random seed
**Simple:** the starting number that makes "random" results reproducible.
**Technical:** initializes a pseudo-random number generator's internal state deterministically.
**This project:** every run takes an integer seed; same seed + config → identical output (validation check #10).
**Interview Q:** "How did you make sure your results were reproducible?" → Explicit seeding, `numpy.random.default_rng(seed)`, verified via a repeat-run diff test.

### 10. Confidence interval
**Simple:** a range that likely contains the true answer, given the uncertainty in your sample.
**Technical:** e.g., a 95% CI means "if we repeated this sampling process many times, 95% of the intervals constructed this way would contain the true value."
**This project:** bootstrap percentile CIs on the mean paired difference between two policies.
**Interview Q:** "What does a 95% CI that excludes 0 tell you?" → We're reasonably confident the true effect isn't zero — but says nothing about whether the effect is *large enough to matter* (that's the separate practical-significance bar).

### 11. Common random numbers
**Simple:** giving two experiments the exact same "luck" so you can see the real difference between them, not just noise.
**Technical:** a variance-reduction technique — reusing the same random draws across compared conditions to make a paired comparison instead of an independent one.
**This project:** the CRN world-stream design in `EXPERIMENT_DESIGN.md` §P.
**Interview Q:** "How did you make sure your policy comparisons weren't just noise?" → CRN — same simulated riders/drivers/random draws face every policy at a given seed.

### 12. P90
**Simple:** the value that 90% of observations fall below — "how bad is it for the unluckiest 10%?"
**Technical:** the 90th percentile of a distribution.
**This project:** P90 rider wait time is the *primary* metric, precisely because average wait hides how bad things get for the worst-served riders.
**Interview Q:** "Why P90 instead of average wait as your primary metric?" → A policy can have a great average while badly failing 10% of riders; P90 is standard in reliability/SLA-style thinking for exactly this reason.

### 13. Statistical significance
**Simple:** "is this difference real, or could it just be random luck?"
**Technical:** formally, whether a test statistic's p-value falls below a pre-chosen threshold (e.g., 0.05), under a null hypothesis of no effect.
**This project:** paired Wilcoxon signed-rank test on the 24 seed-level differences.
**Interview Q:** "Is a statistically significant result automatically a good result?" → No — it can be significant but tiny (see practical-significance bar, §Q).

### 14. Effect size
**Simple:** *how big* is the difference, not just whether it's real.
**Technical:** e.g., matched-pairs Cohen's d = mean difference / std of differences — a unit-free measure of magnitude.
**This project:** reported alongside every significance test, and is what the ≥5% practical-significance bar is actually checking.
**Interview Q:** "Give an example of significant-but-not-meaningful." → A 1.2% P90 wait reduction with a tight CI excluding 0 — real, but not worth shipping.

### 15. Sensitivity analysis
**Simple:** checking whether your conclusion still holds if your guesses were slightly wrong.
**Technical:** systematically perturbing uncertain parameters and re-measuring the outcome.
**This project:** §W — ±30% perturbations of the most uncertain synthetic parameters, re-run for the winning policy.
**Interview Q:** "Your parameters are made up — how do you know your conclusion isn't an artifact of one arbitrary choice?" → Exactly why the sensitivity sweep exists — a conclusion that survives ±30% perturbation on its shakiest assumptions is a much stronger claim than one that doesn't.

---

Phase 2 complete. Internal consistency check passed (see `MATHEMATICAL_MODEL.md`, final section) — **no unresolved issues.** Proceeding directly to Phase 3 implementation per instruction.
