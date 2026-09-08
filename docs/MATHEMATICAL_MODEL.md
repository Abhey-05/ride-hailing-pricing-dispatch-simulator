# Mathematical Model Specification

Status: **final for v1 implementation**. Every equation here is what `src/simulation` must implement, unmodified. If an implementation detail must deviate, this document is updated first.

All values in this document are **synthetic simulation assumptions**, not measurements from any real ride-hailing company. They are chosen to be directionally realistic and internally consistent, not calibrated to any market.

---

## A. Simulation Time Model

- **Tick length (Δt):** 1 simulated minute.
- **Horizon:** configurable; default run = **1,440 ticks (24 simulated hours)**, clock starting at 00:00.
- **Reproducibility:** every run takes one integer `seed`. All randomness derives from `numpy.random.default_rng(seed)` via deterministic child streams (see Section P). Same seed + same config ⇒ bit-identical metrics.

### Timestep sequence (fixed order — order affects results and must not change)

At every tick `t`:

1. **Advance clock** — compute hour-of-day, TOD multiplier, active scenario shocks.
2. **Generate ride requests** — draw `N_z,t ~ Poisson(λ_z,t·Δt)` per zone, instantiate `Request` objects, add to zone's `WAITING` pool.
3. **Update driver states** — resolve any drivers whose `EN_ROUTE_TO_PICKUP` timer elapsed (→ `ON_TRIP`) or whose `ON_TRIP` timer elapsed (→ `AVAILABLE`, earnings booked); resolve online/offline transitions for the tick.
4. **Compute marketplace state** — per zone: `available_drivers[z,t]`, `outstanding_requests[z,t]`, `imbalance[z,t]`.
5. **Compute surge multiplier** — per zone, per active pricing policy (may not update every tick — see Section G).
6. **Price outstanding requests** — any `WAITING` request not yet priced this tick gets `final_price` computed from current surge.
7. **Rider accept/reject offer** — each priced `WAITING` request rolls its (pre-drawn, CRN-fixed) acceptance draw against `P_accept`. Rejected requests are removed (counted as `REJECTED_OFFER`, distinct from cancellation).
8. **Dispatch eligible requests** — for each remaining `WAITING` request (oldest wait time first, to avoid starvation), the active dispatch policy selects a candidate driver from `AVAILABLE` (+ soon-to-free, where the policy allows). Request → `ASSIGNED`, driver → `ASSIGNED`.
9. **Resolve driver acceptance** — assigned driver rolls acceptance draw against `P_driver_accept`. Accept → driver `EN_ROUTE_TO_PICKUP`, request → `MATCHED`, pickup ETA timer starts. Reject → driver back to `AVAILABLE`, request back to `WAITING` (flagged to skip that driver on immediate re-try this tick).
10. **Update active trips** — decrement `EN_ROUTE_TO_PICKUP` and `ON_TRIP` timers by Δt (completions are actually applied at the *start* of the next tick's step 3, keeping a strict "decrement here, resolve there" boundary so a trip can never both progress and complete inconsistently within one tick).
11. **Process cancellations** — every `WAITING` request rolls its per-tick abandonment probability; every `MATCHED` (pre-pickup) request rolls its per-tick post-match cancellation probability. Cancelled requests exit the system.
12. **Record metrics** — append per-tick and (on completion) per-trip records to the metrics collector.

Steps 6–9 repeat implicitly every tick for the pool of still-`WAITING` requests (a request that fails to match this tick simply waits and is retried next tick from step 6 onward, one tick older).

---

## B. Demand / Arrival Model

**Process:** inhomogeneous Poisson process, approximated as a homogeneous Poisson draw per 1-minute tick with a rate that changes tick-to-tick.

```
N_z,t ~ Poisson(λ_z,t · Δt)
```

| Symbol | Meaning | Unit |
|---|---|---|
| `N_z,t` | number of new ride requests generated in zone `z` during tick `t` | requests |
| `λ_z,t` | instantaneous arrival rate for zone `z` at time `t` | requests/hour |
| `Δt` | tick length | hours (1/60) |

```
λ_z,t = λ_base,z · TOD(z, hour(t)) · scenario_demand_mult · (1 + shock_z(t))
```

| Symbol | Meaning |
|---|---|
| `λ_base,z` | zone's baseline hourly demand (archetype-driven, Section C of ASSUMPTIONS.md) |
| `TOD(z, hour)` | time-of-day multiplier, piecewise-linear over 7 named periods, zone-archetype-specific (defined in ASSUMPTIONS.md §Zones) |
| `scenario_demand_mult` | global multiplier set by the experiment scenario (1.0 = normal) |
| `shock_z(t)` | 0 normally; a scenario can inject a temporary additive shock (e.g., +1.5 for 90 minutes in one zone) |

**Why Poisson:** ride requests are the result of many independent riders each individually deciding, with low probability, to request a ride in a given minute. That is exactly the regime the Poisson process models (large number of independent low-probability trials → count of arrivals in a fixed window is Poisson). It's the standard first-choice model for arrival processes in queueing and marketplace simulation (call centers, web traffic, ride requests) precisely because it needs only one parameter (the rate) and is memoryless.

**Why "inhomogeneous, approximated stepwise":** true demand isn't constant across a day — it has rush hours. A *homogeneous* Poisson process assumes a constant rate forever, which is wrong here. We approximate an inhomogeneous process by holding `λ_z,t` fixed within each 1-minute tick and changing it minute to minute — a standard piecewise-constant approximation that becomes exact in the limit as tick length → 0. At 1-minute resolution against multi-hour demand curves, the approximation error is negligible.

**Limitations (documented honestly):** Poisson arrivals assume requests are independent of each other. In reality, ride requests can be correlated (a train arrives and 40 people request rides within the same minute at a transit hub). We do not model this batch-arrival correlation in v1 — it's flagged as a future-work item in ASSUMPTIONS.md, and its absence means our model likely *understates* short-burst congestion at hubs.

**Directional flows:** each zone has an outbound destination distribution `P(dest | origin, hour)` — e.g., `Residential → Commercial` weighted heavily in the morning, reversed in the evening. This is a categorical distribution per (origin zone, time period), defined per-zone in ASSUMPTIONS.md and sampled independently for each generated request.

---

## C. Rider Price Sensitivity / Acceptance Model

When a `WAITING` request is priced, the rider decides whether to accept the quoted price/wait combination (this models the real "see price, then confirm or abandon the app" moment).

```
z_accept = β0 − β_price · (surge_multiplier − 1) − β_wait · (W_exp / W_ref)
P_accept = 1 / (1 + exp(−z_accept))
```

| Symbol | Meaning | Typical value |
|---|---|---|
| `β0` | baseline acceptance logit (at surge = 1.0, no wait penalty) | 2.2 (→ ≈90% baseline acceptance) |
| `β_price` | price-sensitivity coefficient — how much a unit of extra surge hurts acceptance | segment-dependent, 0.6–2.2 |
| `β_wait` | wait-sensitivity coefficient | segment-dependent, 0.3–1.5 |
| `surge_multiplier − 1` | "how much above baseline price" (0 at no surge) | dimensionless |
| `W_exp` | expected wait shown to rider at request time, estimated as current zone's trailing average pickup ETA | minutes |
| `W_ref` | reference wait (normalizer) = 5 minutes | minutes |

**Why logistic:** the logistic function is the standard choice for "probability as a function of a linear score" because it is smooth, monotonic, and bounded in (0,1) by construction — no manual clipping needed, and its shape (S-curve) matches the real intuition that acceptance is very high at low surge/wait, falls off increasingly fast around a "tipping point," then flattens near 0 rather than going negative.

**Rider segments** (drawn once per rider at creation, fixed for that rider):

| Segment | Share of riders | β_price | β_wait | Interpretation |
|---|---|---|---|---|
| `price_sensitive` | 30% | 2.2 | 0.4 | Punishes surge hard, tolerates wait |
| `normal` | 50% | 1.1 | 0.8 | Balanced |
| `time_sensitive` | 20% | 0.6 | 1.5 | Will pay surge to avoid waiting |

**Numerical example:** a `normal` rider (β0=2.2, β_price=1.1, β_wait=0.8), surge = 1.0, `W_exp` = 5 min (=W_ref):
`z = 2.2 − 1.1·0 − 0.8·1 = 1.4` → `P_accept = 1/(1+e^-1.4) ≈ 0.80`.
Same rider at surge = 2.0, `W_exp` = 10 min:
`z = 2.2 − 1.1·1 − 0.8·2 = −0.5` → `P_accept ≈ 0.38`.
This is the mechanism by which surge suppresses demand — it is *not* a separate rule, it falls directly out of this one function.

---

## D. Rider Cancellation Model

Two distinct cancellation points are modeled, because they represent different rider psychology and have different real-world consequences (a pre-match abandonment costs nothing but a lost booking; a post-match cancellation wastes a driver's pickup trip):

### D.1 Pre-match abandonment (rider is `WAITING`, no driver assigned yet)

```
P_abandon(w) = P_max_pre · σ( k_pre · (w − τ_i) / τ_i )      where σ(x) = 1 / (1 + e^-x)
```

| Symbol | Meaning | Value |
|---|---|---|
| `w` | elapsed wait time so far | minutes |
| `τ_i` | rider `i`'s individual patience | drawn per rider, `LogNormal(μ, σ)` with median ≈ segment-specific 4–9 min |
| `k_pre` | steepness of the abandonment curve around the patience point | 3.0 |
| `P_max_pre` | ceiling per-tick abandonment probability (never reaches 1 — some riders wait indefinitely) | 0.35 |

At `w = 0`: `σ(−k) ≈ 0.047` → abandonment probability ≈ `0.35 × 0.047 ≈ 1.6%`/min (some early abandonment happens even immediately — riders who opened the app on a whim). At `w = τ_i` (exactly at patience): `σ(0) = 0.5` → probability = `P_max_pre/2 = 17.5%`/min. As `w → ∞`: approaches `P_max_pre = 35%`/min. This is evaluated **every tick** the request remains `WAITING`, so cumulative abandonment probability compounds correctly over multiple ticks (it is a hazard rate, not a one-shot check).

### D.2 Post-match cancellation (rider is `MATCHED`, driver en route)

Same functional form, different (smaller) parameters, because a rider who already saw a driver assigned is more committed:

```
P_cancel_postmatch(w_pm) = P_max_post · σ( k_post · (w_pm − τ_i·φ) / (τ_i·φ) )
```

| Symbol | Meaning | Value |
|---|---|---|
| `w_pm` | elapsed time since match (i.e., time watching the driver approach) | minutes |
| `φ` | post-match patience discount — post-match patience is a fraction of pre-match patience | 0.6 |
| `k_post` | steepness | 3.0 |
| `P_max_post` | ceiling | 0.12 (much lower — sunk-cost / commitment effect) |

**Sensible-behavior check:** both functions are strictly increasing in wait time by construction (σ is monotonic), and both are bounded in `[0, P_max]` — cancellation probability can never exceed 100%, and never goes negative. ✅ (verified again in Section U validation checks).

---

## E. Driver Model

### States and valid transitions

```
OFFLINE ──(goes online, Section E.1)──▶ AVAILABLE
AVAILABLE ──(dispatched)──▶ ASSIGNED
ASSIGNED ──(driver accepts)──▶ EN_ROUTE_TO_PICKUP
ASSIGNED ──(driver rejects)──▶ AVAILABLE
EN_ROUTE_TO_PICKUP ──(pickup ETA elapses)──▶ ON_TRIP
ON_TRIP ──(trip duration elapses)──▶ AVAILABLE
AVAILABLE ──(goes offline, Section E.1)──▶ OFFLINE
```

No other transition is legal. In particular: a driver can never be `ASSIGNED`/`EN_ROUTE_TO_PICKUP`/`ON_TRIP` for more than one request at a time — the driver object holds at most one `active_request_id`, enforced by construction in the dispatch step (only `AVAILABLE`, or explicitly-eligible soon-to-free, drivers are candidates).

### E.1 Online/offline (supply participation)

Each driver has a **shift schedule** drawn at creation: a start hour and a shift length (e.g., 6h, 8h, 10h), from an empirical-feeling but synthetic distribution (ASSUMPTIONS.md §Drivers). At the shift's start tick, driver → `AVAILABLE`; at the shift's end tick, driver finishes its current trip (if any) then → `OFFLINE`. Scenario supply multipliers work by scaling *how many drivers are generated with a shift active at time t* (Section F of EXPERIMENT_DESIGN.md), not by forcing mid-shift exits — this avoids the unrealistic behavior of drivers vanishing mid-trip.

### E.2 Driver acceptance probability

```
score = γ_fare · (fare_driver_share / avg_fare_driver_share) − γ_pickup · (pickup_eta / avg_pickup_eta) + γ_dest · A_dest − γ_util · u
P_driver_accept = 1 / (1 + exp( −(γ0 + score) ))
```

| Symbol | Meaning | Value |
|---|---|---|
| `fare_driver_share` | driver's payout for this specific trip (Section J) | currency |
| `avg_fare_driver_share` | rolling city-wide average driver payout per trip (normalizer) | currency |
| `pickup_eta` | predicted minutes to reach the rider | minutes |
| `avg_pickup_eta` | rolling city-wide average pickup ETA (normalizer) | minutes |
| `A_dest` | destination attractiveness = normalized current demand level of the destination zone, `[0,1]` | dimensionless |
| `u` | driver's utilization so far this shift (Section J) | `[0,1]` |
| `γ0, γ_fare, γ_pickup, γ_dest, γ_util` | shape parameters | `γ0=1.5, γ_fare=1.8, γ_pickup=2.0, γ_dest=0.7, γ_util=0.5` |

**Numerical example:** average trip, `fare_driver_share/avg = 1.0`, `pickup_eta/avg_pickup_eta = 1.0`, `A_dest=0.5`, `u=0.5`:
`score = 1.8(1.0) − 2.0(1.0) + 0.7(0.5) − 0.5(0.5) = 1.8−2.0+0.35−0.25 = −0.10`
`P_accept = 1/(1+e^-(1.5−0.10)) = 1/(1+e^-1.4) ≈ 0.80`.
A long pickup (`pickup_eta/avg = 2.0`, everything else same): `score = 1.8−4.0+0.35−0.25=−2.10` → `P_accept = 1/(1+e^-(1.5−2.1)) = 1/(1+e^0.6) ≈ 0.35`. This is the mechanism by which long deadhead pickups get rejected more — directly relevant to why `NEAREST_DRIVER` and `DRIVER_EARNINGS_AWARE` dispatch produce different acceptance rates.

---

## F. Travel Time Model

Each zone `z` has a fixed synthetic coordinate `(x_z, y_z)` on a unit grid (ASSUMPTIONS.md §Zones). Distance between zones:

```
distance_km(a,b) = euclidean((x_a,y_a),(x_b,y_b)) · grid_scale_km
```

`grid_scale_km = 1.2` (so adjacent grid cells ≈ 1.2 km apart — a small, dense city (this value was tuned during Phase 4 validation: an initial 3.0 km/unit produced 30–50 min pickup ETAs that crushed driver acceptance probability toward zero and made the marketplace non-functional; 1.2 km/unit keeps the city compact enough that typical pickup ETAs land in the 3–8 min range the rest of the model's parameters -- rider patience, wait reference -- were calibrated against, see CHANGELOG.md).

```
trip_time_min(a,b,t) = (distance_km(a,b) / v_eff(t)) · 60 · noise
v_eff(t) = v_base / congestion(t)
noise ~ LogNormal(0, 0.15)      (median noise = 1.0, i.e., unbiased jitter)
```

| Symbol | Meaning | Value |
|---|---|---|
| `v_base` | uncongested effective speed | 28 km/h |
| `congestion(t)` | time-of-day congestion multiplier ≥ 1 (higher = slower) | 1.0 off-peak, 1.35 at peak hours (Section TOD table), scenario can add further multiplier |
| `noise` | trip-specific random jitter (traffic lights, exact routing) | log-normal, median 1.0 |

**Why this matters for the marketplace:** travel time drives (a) pickup ETA, which drives both rider cancellation and driver acceptance, and (b) trip duration, which drives driver occupied-time and how quickly a driver becomes available again — i.e., effective supply. Congestion is the mechanism by which a "CONGESTED_PEAK" scenario can worsen wait times *even if raw demand and raw driver count are unchanged*, which is an important, realistic effect to be able to isolate in experiments.

Same-zone trips (`a == b`) use a fixed minimum intra-zone distance of `0.8 km` rather than zero, to avoid a degenerate zero-duration trip.

---

## G. Pricing Model

### Base fare

```
base_fare(a,b) = base_fee + distance_rate · distance_km(a,b) + time_rate · trip_time_min(a,b)
final_price = base_fare(a,b) · surge_multiplier(z_origin, t)
```

| Symbol | Value |
|---|---|
| `base_fee` | ₹40 |
| `distance_rate` | ₹9 / km |
| `time_rate` | ₹1.5 / min |

(Currency unit is arbitrary/synthetic — labelled "currency units," not tied to INR/USD reality; ₹ symbol used only for readability.)

### Marketplace imbalance signal

```
imbalance(z,t) = outstanding_requests(z,t) / (available_drivers(z,t) + 1)
```

The `+1` in the denominator is the **exact, documented fix for division-by-zero**: when a zone has zero available drivers, imbalance is `outstanding_requests / 1`, a large-but-finite number, rather than `inf` or `NaN`. When a zone has zero requests, imbalance is exactly `0` regardless of driver count (no demand ⇒ no pressure to surge), which is the desired behavior.

### Four pricing policies

| Policy | Formula | Cap | Update frequency | Rationale |
|---|---|---|---|---|
| **NO_SURGE** | `surge = 1.0` always | n/a | n/a | Control/baseline — isolates dispatch effects from pricing effects |
| **BASIC_SURGE** | `surge = clip(1 + α_b·(imbalance − 1), 1.0, 2.0)`, `α_b = 0.5` | **[1.0, 2.0]** | every 5 minutes | Textbook proportional surge around a "balanced" target of 1 request per available driver |
| **AGGRESSIVE_SURGE** | `surge = clip(1 + α_a·imbalance, 1.0, 3.0)`, `α_a = 1.0` | **[1.0, 3.0]** | every tick (1 min) | No subtracted target, higher gain, more reactive/noisier — models a platform prioritizing fast supply response over rider price stability |
| **CAPPED_SMOOTHED_SURGE** | raw = `clip(1 + α_b·(imbalance−1), 1.0, 2.5)`; applied = `λ_s·raw + (1−λ_s)·applied_{t−1}`, `λ_s = 0.2` | **[1.0, 2.5]** | every tick, but exponentially smoothed | Same signal as BASIC but low-pass filtered — avoids surge "flickering" minute to minute, which is the #1 rider complaint about naive surge systems |

**Why caps exist (product rationale):** an uncapped multiplier can spiral (very few drivers + a burst of requests → imbalance → ∞ → surge → ∞), which is exactly the failure mode that generates news stories about "$300 rides" and regulatory backlash. A cap trades away some theoretical supply-pulling power for predictability, brand trust, and (in some jurisdictions) regulatory compliance. `CAPPED_SMOOTHED_SURGE` additionally trades reactivity for rider-perceived fairness (a price that doesn't visibly jump between refreshes).

**Update frequency matters:** `AGGRESSIVE_SURGE` recomputing every tick means it can double-count a transient one-minute demand blip; `BASIC_SURGE`'s 5-minute cadence and `CAPPED_SMOOTHED_SURGE`'s exponential smoothing are both, in different ways, noise-reduction choices — this difference is itself an experimental variable we can observe in results (does noisier pricing hurt rider acceptance more than it helps supply?).

---

## H. Dispatch Models

All dispatch policies operate on the same inputs each tick: the sorted list of `WAITING` requests (oldest-wait-first — this FIFO-by-age ordering is fixed across all policies specifically so that differences in outcomes are attributable to *scoring/candidate logic*, not to *request-processing order*), and the pool of currently `AVAILABLE` drivers (plus, for policies 2 and 5, drivers who will free up within a short look-ahead horizon `H = 3` minutes).

For every candidate driver `d` and request `r`, define reusable primitives:
- `eta(d,r)` = predicted pickup ETA if `d` is dispatched to `r` (Section F)
- `release(d)` = 0 if `d` is `AVAILABLE` now, else minutes remaining until `d` finishes its current trip (only used by policies with look-ahead)
- `fare(r)` = predicted `final_price` for `r`
- `A_dest(r)` = destination attractiveness of `r`'s destination zone (Section E.2)
- `imbalance_origin(d)` = current `imbalance(zone_of(d), t)` — the health of the zone `d` would be pulled *out of*

### H.1 NEAREST_DRIVER
**Objective:** minimize immediate pickup distance. **Candidates:** `AVAILABLE` only. **Score:** `distance_km(zone(d), zone(r))` (raw distance, not time). **Decision:** pick `argmin` score. **Tie-break:** lowest `driver_id` (deterministic). **Complexity:** `O(D)` per request, `O(R·D)` per tick (`D`=available drivers in candidate radius, `R`=waiting requests). **Strengths:** minimizes pickup for *this* rider, trivial to explain/audit. **Weaknesses:** myopic — ignores whether pulling the nearest driver empties out an already-tight zone; ignores congestion (distance ≠ time).

### H.2 ETA_OPTIMIZED
**Objective:** minimize predicted pickup *time*, including soon-to-free drivers. **Candidates:** `AVAILABLE` ∪ {on-trip drivers with `release(d) ≤ H`}. **Score:** `release(d) + eta(d,r)` computed from the driver's *drop-off* location for soon-to-free drivers. **Decision:** `argmin` score. **Complexity:** `O(R·D')`, `D'` slightly larger than `D`. **Strengths:** accounts for congestion (uses time, not raw distance) and captures "a driver 2 minutes from finishing nearby is better than one 6 minutes away right now" — a real improvement nearest-driver cannot make. **Weaknesses:** still fully myopic about zone-level consequences; a released-driver prediction can be wrong if that driver's trip runs long (compounds a small risk of double-booking-like delay, mitigated by only reconsidering it fresh each tick since it isn't actually reserved).

### H.3 DRIVER_EARNINGS_AWARE
**Objective:** maximize the chance of a driver actually accepting the trip (Section E.2), not just minimize pickup. **Candidates:** top-`K=5` drivers by `eta(d,r)` from the `AVAILABLE` pool (a pre-filter, not the full fleet — see complexity note). **Score:** predicted `P_driver_accept(d,r)` (Section E.2 formula, evaluated hypothetically). **Decision:** `argmax` predicted acceptance among the K nearest. **Complexity:** `O(R·D)` for the pre-filter + `O(R·K)` for scoring, `K` constant ⇒ same order as nearest-driver. **Strengths:** fewer wasted dispatch cycles (a driver who is offered a trip they're likely to reject wastes an entire dispatch round-trip — this policy reduces churn and, in practice, tends to raise realized driver earnings per trip since it slightly favors better-paying assignments). **Weaknesses:** trades a small amount of pickup ETA for acceptance probability — riders may wait marginally longer on average; can systematically favor drivers on long/high-fare trips, which (left unchecked) could concentrate earnings among fewer drivers — a fairness consideration flagged in `docs/` ethics section later.

### H.4 MARKETPLACE_AWARE
**Objective:** avoid worsening an already-undersupplied zone by pulling its last available driver. **Candidates:** `AVAILABLE`. **Score:** `eta(d,r) + β_mp · max(0, target_ratio − post_dispatch_ratio(d))`, where `post_dispatch_ratio(d)` = the origin zone's supply/demand ratio *after* hypothetically removing `d` from its available pool, and `target_ratio = 1.0`. `β_mp = 4.0` (minutes of "penalty" per unit of ratio shortfall — chosen so the penalty is comparable in magnitude to a few minutes of extra pickup, not dominant). **Decision:** `argmin` score. **Complexity:** `O(R·D)`, identical order to nearest-driver (the penalty term is a cheap lookup, not a re-simulation). **Strengths:** directly protects zone-level supply, which nearest-driver and ETA-optimized structurally ignore — this is the first policy that reasons about the *marketplace*, not just the *one match*. **Weaknesses:** can increase pickup ETA for the rider being served now in exchange for a *future* benefit to other riders — a genuine, honest trade-off, not a free win.

### H.5 ADVANCED_HEURISTIC
**Objective:** a single weighted score combining all the above considerations plus cancellation-risk prioritization:

```
cost(d,r) = w_eta · (eta(d,r)/avg_eta) 
          + w_imb · max(0, target_ratio − post_dispatch_ratio(d))
          + w_dest· (−A_dest(r))
          − w_cancel · (elapsed_wait(r) / τ_typical)
```
`argmin cost(d,r)` over `AVAILABLE ∪ {release(d) ≤ H}`.

| Weight | Value | Meaning |
|---|---|---|
| `w_eta` | 1.0 | base pickup-time cost |
| `w_imb` | 3.0 | marketplace-protection penalty |
| `w_dest` | 0.5 | small bonus for sending drivers toward high-demand destinations (pre-positions supply) |
| `w_cancel` | 1.5 | requests closer to their patience limit get prioritized for the *best* available match, not just served in FIFO order among ties |

**Complexity:** `O(R·D')`, same order as ETA_OPTIMIZED — this is a heuristic combination of already-computed cheap terms, **not** a joint optimization over all `R×D` pairs simultaneously.

**Explicit non-claim:** this is a **greedy, per-request heuristic**, not a global optimum. The true "best possible" assignment at any tick is a **minimum-cost bipartite matching problem** (assign each waiting request to at most one driver, each driver to at most one request, minimizing total cost) — solvable exactly with, e.g., the Hungarian algorithm in `O((R+D)³)`, or faster with LP relaxations/auction algorithms. We do not implement an exact solver, for three concrete reasons: (1) `O((R+D)³)` recomputed every 1-minute tick does not scale as the fleet grows — real dispatch systems serve city-wide, sub-second SLAs; (2) the state changes every tick anyway (new requests, drivers finishing trips), so an "exact" solution is instantly stale and the marginal benefit over a good greedy heuristic shrinks in a rolling-horizon setting; (3) greedy heuristics are simpler to monitor, debug, and explain to regulators/ops — a real, material product consideration, not just an engineering shortcut. This trade-off (optimal-but-slow vs. good-and-fast-and-explainable) is exactly the kind of thing production dispatch systems (and this project) choose deliberately, and it is a strong, honest answer to "why didn't you use a perfect optimization algorithm?"

---

## I. Marketplace State Variables

| Variable | Updated when | Definition |
|---|---|---|
| `available_drivers[z,t]` | Step 3 (start of tick) | count of drivers in state `AVAILABLE` with `zone == z` |
| `outstanding_requests[z,t]` | Step 4 | count of requests in state `WAITING` with `origin_zone == z` |
| `active_trips[t]` | Step 3 | count of requests in state `EN_ROUTE_TO_PICKUP` or `ON_TRIP`, city-wide |
| `imbalance[z,t]` | Step 4 | `outstanding_requests[z,t] / (available_drivers[z,t]+1)` (Section G) |
| `average_pickup_eta[z,t]` | Step 12 (rolling) | trailing 15-minute mean of `eta(d,r)` for matches *made* in zone `z` |

These are the only state variables read by pricing/dispatch — no policy is allowed to read state that wouldn't exist in a real-time system (e.g., no policy can see future arrivals).

---

## J. Driver Economics

```
driver_payout(trip) = (1 − commission_rate) · final_price(trip)
driver_gross_earnings = Σ driver_payout(trip)   over all trips completed by that driver
driver_online_hours = (offline_tick − online_tick) / 60   [includes idle + assigned + en-route + on-trip time]
active_time = time spent in EN_ROUTE_TO_PICKUP + ON_TRIP
driver_utilization = active_time / driver_online_hours          (∈ [0,1] by construction — both are non-negative and active_time ≤ online_time)
driver_earnings_per_online_hour = driver_gross_earnings / driver_online_hours
driver_earnings_per_active_hour = driver_gross_earnings / (active_time in hours)
```

`commission_rate = 0.25` (synthetic assumption — platform takes 25% of every fare, driver keeps 75%, **including** the surge premium — i.e., surge revenue is shared in the same 75/25 split as base fare, not routed disproportionately to either side; this is a deliberate simplifying choice documented in ASSUMPTIONS.md, not a claim about any real company's split).

`driver_earnings_per_active_hour` is always ≥ `driver_earnings_per_online_hour` (same numerator, smaller-or-equal denominator) and is a **diagnostic**, not a headline metric — it answers "how good is the pay when I'm actually working," while `per_online_hour` answers "how good is this job overall," which is what a driver actually experiences and decides shifts around.

---

## K. Platform Economics

```
GBV (Gross Booking Value) = Σ final_price(trip)   over all completed trips
platform_revenue = commission_rate · GBV
driver_payout_total = (1 − commission_rate) · GBV
```

**By construction:** `platform_revenue + driver_payout_total ≡ GBV` exactly — there is no separate fee that breaks this identity in v1 (no cancellation fees, no surge-specific fee routing). This is a deliberate simplification, stated explicitly so no one can find an accounting inconsistency: **there are no hidden fees in this model.**

```
revenue_per_ride = platform_revenue / completed_trips
```

---

## L. Metric Dictionary

Every metric below is computed identically regardless of policy — the metrics layer has no knowledge of which pricing/dispatch policy produced the underlying events.

| Metric | Formula | Unit | Type |
|---|---|---|---|
| Average wait | mean(`time_from_request_to_pickup`) over completed trips | min | Diagnostic |
| Median wait | median(same) | min | Diagnostic |
| P90 wait | 90th percentile(same) | min | **Primary / Guardrail** |
| Cancellation rate | (`abandoned` + `cancelled_postmatch`) / `total_requests` | % | **Guardrail** |
| Completion rate (fulfillment rate) | `completed_trips` / `total_requests` | % | Diagnostic / Marketplace |
| Average rider price | mean(`final_price`) over completed trips | currency | Diagnostic |
| Price index | mean(`final_price`) / mean(`base_fare` at surge=1.0 for same trips) | ratio | **Guardrail** |
| Rider conversion rate | (requests that resulted in a completed trip) / (requests that were priced/offered) | % | Diagnostic |
| Driver utilization | Section J | % | Diagnostic |
| Earnings/online-hour | Section J | currency/hr | **Guardrail** |
| Driver acceptance rate | accepted assignments / total assignments offered | % | **Guardrail** |
| Idle time | `online_hours − active_hours`, aggregated | hours | Diagnostic |
| GBV | Section K | currency | Diagnostic |
| Platform revenue | Section K | currency | Diagnostic/Guardrail |
| Revenue/ride | Section K | currency | Diagnostic |
| Fulfillment rate | same as completion rate, reported at marketplace level | % | Diagnostic |
| Unmatched requests | `abandoned` + `cancelled_postmatch` + still-`WAITING` at horizon end | count | Diagnostic |
| Supply-demand ratio | `available_drivers / (outstanding_requests+1)`, city or zone level | ratio | Diagnostic |
| Average pickup distance | mean(`distance_km(driver, rider origin)`) at match time | km | Diagnostic |
| **North Star:** Completed trips per online driver-hour | `completed_trips / Σ driver_online_hours` | trips/driver-hr | **North Star** |
| Rider surplus proxy | Σ over completed trips of `(willingness_to_pay_proxy − final_price)`, where `willingness_to_pay_proxy = base_fare · (1 + 1/β_price_segment)` (the price at which that segment's P_accept would be ≈50% above 1) | currency | Diagnostic (proxy, not a real consumer-surplus measurement) |
| Driver surplus proxy | Σ `(driver_payout − opportunity_cost_of_time)`, `opportunity_cost_of_time = reservation_wage · active_hours`, `reservation_wage` = synthetic constant | currency | Diagnostic (proxy) |
| Social welfare proxy | rider surplus proxy + driver surplus proxy + platform revenue | currency | Diagnostic (proxy) |

**Potential gaming behavior**, called out explicitly per metric family:
- *North Star alone*: could be inflated by starving low-liquidity zones (fewer, easier-to-serve requests raise the ratio) — guarded by P90 wait and fulfillment rate.
- *Average wait alone*: hides a bad tail — guarded by P90.
- *Driver earnings/hour alone*: could be inflated by keeping very few drivers online (less competition for trips) — guarded by driver acceptance rate and fulfillment rate (fewer drivers online should show up as worse fulfillment).
- *Revenue alone*: inflated by unlimited surge — guarded by cancellation rate and price index.

---

## M. North Star Metric — Critical Evaluation

**Alternatives considered:**

| Candidate | Verdict | Why |
|---|---|---|
| Completed trips (raw count) | ❌ Rejected | Trivially inflated by adding more drivers; says nothing about marketplace *efficiency* |
| Gross Booking Value | ❌ Rejected | Rewards higher prices regardless of rider experience; a platform could "win" by surging everything |
| Completed trips / available driver-hour (hours spent specifically in `AVAILABLE`, not online) | ❌ Rejected | Perverse: a policy that keeps drivers busy (less time `AVAILABLE`) shrinks this denominator and *inflates* the ratio without doing anything good — rewards under-supplying, not efficient matching |
| Contribution margin / driver-hour | ⚠️ Considered, kept as a secondary diagnostic | Excellent for a finance-focused review but conflates pricing power with matching efficiency; harder to explain in one sentence to ops/driver teams |
| **Completed trips / online driver-hour** | ✅ **Selected** | Numerator (successful matches) is exactly what pricing+dispatch jointly control; denominator (online hours) is the driver's own participation choice, largely exogenous to the policy being tested — so the ratio isolates "how well did we use the supply that showed up," which is the precise question a marketplace PM asks when deciding between pricing and dispatch levers |

**What it captures:** how efficiently the platform converts driver participation into completed rides — the textbook definition of marketplace liquidity/efficiency.
**What it misses:** rider price paid, and tail experience — which is exactly why it is reported **only alongside** P90 wait, cancellation rate, and driver earnings/hour, never alone (Section N).
**How it can be gamed:** see Section L's gaming note above — guardrails specifically target this.

**Conclusion: the originally proposed North Star from Phase 1 is retained**, but its definition and denominator were explicitly stress-tested against four alternatives rather than accepted by default.

---

## N. Guardrail Metrics (final, prioritized set of five — not twenty)

| Guardrail | Why this one, specifically |
|---|---|
| **P90 rider wait time** | Catches tail-experience harm the North Star and even average wait would miss |
| **Rider cancellation rate** | Direct, immediate signal of price or wait driving riders away — the fastest-moving warning light |
| **Driver earnings/online-hour** | Protects the supply side from a policy that "wins" by exploiting drivers |
| **Driver acceptance rate** | Leading indicator that dispatch is producing bad (long-pickup, low-value) matches before it shows up in earnings |
| **Price index** | Distinguishes "we got more efficient" from "we just charged more," the single most important distinction for the core hypothesis test |

Five, deliberately — enough to catch every gaming vector identified in Section L without producing a report nobody can hold in their head.

---

## Internal Consistency Check (performed before Phase 3 implementation)

- **Equations compatible?** Yes — pricing (G) feeds rider acceptance (C) and driver payout (J/K) using the same `final_price`; dispatch (H) reads only state variables defined in (I); metrics (L) reference only quantities defined in (J)/(K)/state.
- **Units consistent?** Yes — all times in minutes internally (converted to hours only at the earnings/utilization boundary, explicitly), all distances in km, all money in one unlabeled "currency unit" throughout (never mixed with a real-world currency claim).
- **Probabilities bounded?** Yes — every probability in B–E is a logistic or a logistic-scaled-by-a-constant-≤1, so bounded in `[0, P_max] ⊆ [0,1]` by construction; no manual `min(p,1)` patch is needed anywhere, which is itself a check that the functional forms were chosen correctly.
- **Zero denominators?** The only ratios with a variable denominator are `imbalance` (fixed via `+1`), utilization/earnings-per-hour (denominator is `online_hours`/`active_hours`, which is zero only if a driver never went online — such a driver contributes no rows to any aggregate, handled by excluding zero-online-hour drivers from per-driver rate metrics, not by dividing by zero), and `completion_rate`/`revenue_per_ride` (denominator `total_requests`/`completed_trips` — a tick or run with literally zero requests is a degenerate config we exclude from analysis, not divide through).
- **State transitions valid?** Yes — the transition table in Section E is exhaustive and enforced by the driver object only ever holding one `active_request_id`; a request's own state machine (`WAITING → {MATCHED, REJECTED_OFFER, ABANDONED}`, `MATCHED → {ON_TRIP, CANCELLED_POSTMATCH}`, `ON_TRIP → COMPLETED`) is similarly exhaustive.
- **Impossible situations?** The ordering in Section A (decrement timers in step 10, resolve completions in step 3 of the *next* tick) specifically prevents a trip from both "still en route" and "completed" being true in the same tick's metrics.
- **Metrics consistent?** Yes — every metric in Section L is defined purely in terms of quantities from A–K, with no metric-specific re-derivation of, e.g., price or distance.
- **Pricing/driver economics consistent?** Yes — `platform_revenue + driver_payout ≡ GBV` by construction (Section K), verified as an explicit unit test in Phase 3, not just asserted here.
- **Does the experiment actually test the stated hypothesis?** Addressed in `EXPERIMENT_DESIGN.md` Section R/S — the core 480-run matrix holds pricing policy fixed and varies dispatch policy (and vice versa), specifically so the "dispatch reduces wait without raising driver cost" hypothesis can be isolated from a pricing confound.

**No unresolved issues identified.** Proceeding to Phase 3.
