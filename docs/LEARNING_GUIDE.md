# Learning Guide — Everything Behind This Project, From Zero

38 concepts, each with: a plain-language explanation, the technical version, exactly how this project uses it, and a question an interviewer might ask about it. Read this once start to finish before Phase 3 style implementation work, then use it as a reference.

---

## Part A — Marketplace Economics

### 1. Ride-hailing marketplace economics
**Simple:** a business that connects two groups of people (riders who need a ride, drivers who have a car) and makes money by taking a cut of each transaction.
**Technical:** a two-sided platform market — value for one side (riders) depends on the number/quality of participants on the other side (drivers), and vice versa (a "network effect").
**This project:** every design decision — pricing, dispatch, metrics — exists because the platform sits between two groups with different, sometimes conflicting interests.
**Interview Q:** "Why is a two-sided market harder to optimize than a normal business?" — because a change that helps one side (e.g. lower prices for riders) can hurt the other (lower earnings for drivers), and an imbalance on one side (too few drivers) directly degrades the experience for the other.

### 2. Supply and demand
**Simple:** how many drivers are available (supply) vs. how many people want a ride (demand) at a given moment.
**Technical:** in this project, `available_drivers[z,t]` and `outstanding_requests[z,t]`, tracked per zone per minute.
**Example:** at 8am in Residential North, demand spikes (commute) while supply is still thin (drivers haven't started their shift yet) — a supply/demand imbalance.
**Interview Q:** "How do you actually measure imbalance?" — `imbalance = outstanding_requests / (available_drivers + 1)`, a ratio, not a difference, so it's comparable across zones of different sizes.

### 3. Why surge pricing exists
**Simple:** raising the price during a supply/demand imbalance discourages some riders from requesting (so the remaining demand better matches supply) and encourages drivers to come online.
**Technical:** a real-time market-clearing mechanism.
**This project:** `docs/EXPERIMENTS.md` Experiment 3 shows surge raising revenue *and* lowering cancellation simultaneously — a real market-clearing effect, not just "charge more."
**Interview Q:** "Why not just ban surge pricing?" — because without it, high-demand periods would have no mechanism to ration scarce rides or attract more drivers, and *everyone* waits longer instead of some riders paying more to skip the wait.

### 4. Dispatch
**Simple:** the decision of which driver gets sent to which rider.
**Technical:** an assignment/matching operation running continuously as new requests and drivers become available.
**This project:** `src/dispatch.py`, 5 different policies, all operating on the same inputs each tick.
**Interview Q:** "Is dispatch a one-time decision or ongoing?" — ongoing; every tick re-evaluates the current pool of waiting requests and available drivers.

### 5. Matching
**Simple:** pairing one rider with one driver.
**Technical:** formally, a bipartite matching problem (two distinct sets, edges between them, each node used at most once).
**This project:** every dispatch policy solves a *greedy, one-request-at-a-time* version of this — not the full joint optimization (see #16, Heuristic).
**Interview Q:** "What would the 'exact' version of this problem look like?" — a minimum-cost bipartite matching over ALL waiting requests and available drivers simultaneously (e.g. via the Hungarian algorithm), re-solved every tick.

### 6. Why nearest-driver matching isn't always optimal
**Simple:** sending the closest driver to *this* rider might leave a worse driver-request pairing for someone else, or drain a zone that needed that driver more.
**Technical:** nearest-driver is a myopic, local optimization — it never considers the state of the marketplace beyond the current pair.
**This project:** proven empirically — `ETA_OPTIMIZED` (which also looks at soon-to-be-free drivers) beats pure nearest-driver by 7.8-11.3% on P90 wait (`docs/EXPERIMENTS.md`, Experiment 4).
**Interview Q:** "Give a concrete example of nearest-driver failing." — a driver 1 minute from finishing a trip 0.5km from the rider is a better match than an idle driver 3km away, but nearest-driver (which only looks at currently-idle drivers) can't see the first driver at all.

### 7. Marketplace liquidity
**Simple:** how easily supply and demand find each other — a "liquid" marketplace matches quickly and reliably.
**Technical:** commonly measured as successful transactions per unit of available supply.
**This project:** the North Star metric (`completed_trips / online_driver_hours`) *is* a liquidity metric.
**Interview Q:** "Why does liquidity matter more than raw volume?" — volume can be inflated by just adding more drivers; liquidity asks "how efficiently did we use the drivers we had," which is what pricing/dispatch actually control.

### 8. Driver utilization
**Simple:** what fraction of a driver's online time is spent actually working (driving to or with a rider) vs. idle.
**Technical:** `active_time / online_time`, where `active_time` = time in `EN_ROUTE_TO_PICKUP` + `ON_TRIP`.
**This project:** a *diagnostic*, not the North Star — Experiment 5 shows a policy can lower utilization while still being strictly better (fewer wasted pickup minutes, more completed trips).
**Interview Q:** "Is higher utilization always good?" — no; 100% utilization with terrible pickup ETAs is possible and bad. Utilization must always be read next to earnings and completion rate.

### 9. Rider conversion
**Simple:** of the riders who saw a price and could have accepted it, how many actually did?
**Technical:** `completed_trips / priced_offers`.
**This project:** tracked as a diagnostic under `rider_conversion_rate`; falls modestly as surge rises (Experiment 1).
**Interview Q:** "How is conversion different from completion rate?" — in this model they're numerically similar (every request is priced exactly once), but conceptually conversion is about the *pricing* decision, completion is about the *whole* pipeline including matching and cancellation.

### 10. Cancellation
**Simple:** a rider backing out — either before a driver is found (abandonment) or after (post-match cancellation).
**Technical:** two distinct hazard-rate functions in this project (Math Model §D), because the psychology and cost differ (pre-match costs nothing but a lost booking; post-match wastes a driver's trip).
**This project:** the largest single loss channel in the baseline simulation (~20% of all requests).
**Interview Q:** "Why model two kinds of cancellation instead of one?" — because a rider who already sees a driver assigned is more committed (sunk-cost effect) — using one function would either overstate early abandonment or understate post-match churn.

### 11. P90 (90th percentile)
**Simple:** the value that 90% of observations are below — "how bad is it for the unluckiest 10%?"
**Technical:** a percentile statistic; robust to outliers unlike max, more informative about tail experience than mean.
**This project:** the *primary* metric for the core hypothesis test — chosen specifically because average wait can look great while the worst 10% of riders are badly served.
**Interview Q:** "Why not P99?" — with a moderate sample size per run, P99 is noisier (fewer data points define it); P90 balances tail-sensitivity against statistical stability.

### 12. Opportunity cost
**Simple:** what you give up by choosing one option over another.
**Technical:** the value of the next-best alternative forgone.
**This project:** the "driver surplus proxy" metric subtracts a `reservation_wage × active_hours` opportunity-cost term from driver payout, to approximate a driver's true economic gain from driving vs. their next-best use of that time.
**Interview Q:** "Why does a driver's opportunity cost matter for pricing?" — a driver won't accept a low-paying trip if their opportunity cost (another platform, another job, leisure) exceeds the payout — this is exactly what the driver-acceptance formula's fare term captures.

### 13. Price elasticity
**Simple:** how much demand changes when price changes.
**Technical:** `%Δquantity / %Δprice`; the `β_price` coefficient in the rider-acceptance logistic *is* this project's elasticity parameter.
**This project:** three different elasticities by rider segment (0.6 to 2.2) — deliberately not a single city-wide number, since real riders aren't uniform.
**Interview Q:** "Which segment is most elastic here, and why does that matter for surge design?" — `price_sensitive` (β=2.2); it means a flat surge cap protects this segment disproportionately less than a segment-aware pricing scheme would (a real product idea this project doesn't implement).

### 14. Dynamic pricing
**Simple:** prices that change based on real-time conditions rather than staying fixed.
**Technical:** a function of a live signal (here, marketplace imbalance), recomputed on some cadence, typically bounded.
**This project:** 4 policies differing in formula, cap, and update cadence (Math Model §G).
**Interview Q:** "What's the risk of updating price too frequently?" — visible price "flickering" that riders perceive as unfair or gameable — the reason `CAPPED_SMOOTHED_SURGE` exponentially smooths its signal.

---

## Part B — Optimization, Simulation & Statistics

### 15. Optimization
**Simple:** finding the best possible choice given constraints.
**Technical:** formally, minimizing (or maximizing) an objective function subject to constraints.
**This project:** every dispatch policy has an explicit objective (Math Model §H); none of them actually *solves* the joint optimization exactly (see #16).
**Interview Q:** "What's the objective function for `ADVANCED_HEURISTIC`?" — a weighted sum of normalized pickup ETA, marketplace-imbalance penalty, destination attractiveness bonus, and cancellation-urgency bonus (Math Model §H.5) — and it's worth noting this project found that objective's weights were miscalibrated (`docs/EXPERIMENTS.md`).

### 16. Heuristic
**Simple:** a fast, "good enough" rule instead of a guaranteed-best (but slow) method.
**Technical:** an approximation algorithm without an optimality guarantee.
**This project:** all 5 dispatch policies are heuristics, explicitly not exact solvers, because an exact bipartite-matching solve is `O((R+D)³)` per tick and would need to be redone every minute as the state changes (Math Model §H.5).
**Interview Q:** "When would you *not* use a heuristic?" — when the problem is small enough and static enough that an exact solve's cost is negligible, or when the cost of a suboptimal decision is very high and irreversible (this project's real-time, constantly-changing marketplace is the opposite case).

### 17. Simulation
**Simple:** a model of a system you can run and observe instead of experimenting on the real thing.
**Technical:** a computational representation of a system's state and dynamics over time.
**This project:** the entire `src/engine.py` — a synthetic marketplace, not real data.
**Interview Q:** "What's the biggest risk of trusting a simulation's conclusion?" — that the model's assumptions don't match reality closely enough for the *magnitude* of a result to transfer, even if the *direction* does (see `docs/EXPERIMENT_DESIGN.md` §T, Causality Warning).

### 18. Monte Carlo simulation
**Simple:** running a simulation many times with different randomness to see the range of possible outcomes, not just one guess.
**Technical:** repeated random sampling used to estimate a quantity or distribution that's hard to compute analytically.
**This project:** each of the 1,080 runs is one Monte Carlo trial; averaging across seeds estimates each policy's expected performance.
**Interview Q:** "Why not just run the simulation once per policy?" — one run is one random draw from many possible "days" — a single lucky or unlucky run could completely mislead you about which policy is actually better.

### 19. Random seed
**Simple:** the starting number that makes "random" output reproducible.
**Technical:** initializes a pseudo-random number generator's internal state deterministically.
**This project:** every run takes an integer seed; `numpy.random.SeedSequence` (never Python's built-in `hash()`, which is randomized per process) derives every downstream stream — tested explicitly (`test_reproducibility_same_seed_identical_summary`).
**Interview Q:** "Why not use Python's `hash()` for seeding?" — `hash()` on strings is randomized per process for security reasons (hash-flooding protection); the same string can hash differently across two runs, silently breaking reproducibility.

### 20. Poisson process
**Simple:** a way to model random events (like ride requests) happening at some average rate, independently of each other.
**Technical:** `P(N=k) = (λt)^k e^{-λt}/k!`; the number of events in a fixed window follows this distribution when arrivals are independent and rare in any instant.
**This project:** `N_z,t ~ Poisson(λ_z,t · Δt)` — new ride requests per zone per minute.
**Interview Q:** "What does a Poisson process assume that might not hold in reality?" — independence between arrivals; a real transit-hub surge (a train unloading 40 people at once) is a *correlated batch arrival*, which Poisson does not capture — flagged explicitly as a limitation in Math Model §B.

### 21. Why Poisson was used for ride requests specifically
**Simple:** because it needs only one number (the rate) to describe "random arrivals," and that's exactly the shape ride requests take.
**Technical:** the standard first-choice arrival model in queueing theory for the same reason it's used for call centers and web traffic.
**This project:** kept simple deliberately — a more complex arrival process (e.g. a Hawkes process for correlated bursts) was considered out of scope for v1.
**Interview Q:** "When would Poisson clearly be the wrong choice?" — modeling event-driven demand spikes (concerts letting out, a subway arrival) where many requests genuinely arrive together, not independently.

### 22. A/B test
**Simple:** splitting users into two groups, giving one group the new thing and the other the old thing, and comparing outcomes.
**Technical:** a randomized controlled experiment; randomization is what allows a causal (not just correlational) claim.
**This project:** not run here (this is a simulation) — but `docs/PRD.md` §15 designs the production A/B test this project's finding would justify running.
**Interview Q:** "Why can't your simulation result substitute for a real A/B test?" — the simulation's parameters are synthetic; only a real randomized experiment on real riders/drivers can prove a causal production effect (`docs/EXPERIMENT_DESIGN.md` §T).

### 23. Statistical significance
**Simple:** is this difference likely real, or could it just be random luck?
**Technical:** whether a test statistic's p-value falls below a pre-chosen threshold (e.g. 0.05) under a null hypothesis of no effect.
**This project:** paired Wilcoxon signed-rank test on 24 seed-level differences per comparison — e.g. `ETA_OPTIMIZED` vs. baseline under `BASIC_SURGE`: p = 1.7×10⁻⁵.
**Interview Q:** "Is a significant result always a good result?" — no — see #24 and #14(effect size) — significance says "probably real," not "big enough to matter."

### 24. Confidence interval
**Simple:** a range that probably contains the true value, given the uncertainty in your data.
**Technical:** a 95% CI means "if this sampling process were repeated many times, 95% of the intervals constructed this way would contain the true value."
**This project:** bootstrap percentile CIs (10,000 resamples) on the mean paired difference — e.g. `ETA_OPTIMIZED`'s P90 wait improvement under `BASIC_SURGE`: [0.71, 1.13] minutes.
**Interview Q:** "Why bootstrap instead of a normal-theory CI?" — with only 24 paired samples, assuming the sampling distribution of the mean is normal is a real risk; bootstrap makes no such assumption.

---

## Part C — Machine Learning

### 25. ML model
**Simple:** a program that learns a pattern from data instead of being explicitly told the rule.
**Technical:** a function fit to minimize a loss on training data, evaluated on held-out data to check it generalizes.
**This project:** a gradient-boosting classifier predicting whether a ride request will cancel (`src/ml_cancellation.py`).
**Interview Q:** "Why is this a good use of ML and not ML-for-its-own-sake?" — because the alternative (the existing hand-written, single-variable heuristic) is measurably worse (AUC 0.55 vs. 0.82) — the improvement is real and quantified, not assumed.

### 26. Why gradient boosting (not linear regression alone)
**Simple:** gradient boosting can learn non-linear patterns and interactions between features that a single straight-line model can't.
**Technical:** an ensemble of shallow decision trees, each correcting the previous ones' errors.
**This project:** logistic regression already substantially beats the rule-based baseline (AUC 0.78 vs. 0.55); gradient boosting adds a further, smaller improvement (0.82) — reported honestly as an incremental, not miraculous, gain.
**Interview Q:** "Was the big jump from the LR baseline or the GBM baseline?" — from *adding features* (rule-based → LR, +0.23 AUC), not from the specific model class (LR → GBM, +0.03 AUC) — a genuinely important nuance about where the value actually came from.

### 27. Feature engineering
**Simple:** choosing and shaping the inputs you give a model.
**Technical:** transforming raw data into a representation that makes the underlying pattern easier for a model to learn.
**This project:** `hour_created` and `imbalance_at_request` (marketplace-condition features) turned out to dominate feature importance (0.75 + 0.17) over rider-intrinsic features like `patience_min` (0.05) — a real, somewhat surprising finding about *what actually drives* cancellation risk in this simulation.
**Interview Q:** "What feature would you add next if you had more data?" — a rolling per-rider historical cancellation rate — the single most predictive feature in most real cancellation models, and one this project cannot construct because each simulated rider only appears once.

### 28. Model leakage
**Simple:** accidentally letting the model see information it wouldn't actually have at prediction time — making it look better than it really is.
**Technical:** including a feature that is causally downstream of, or otherwise entangled with, the label.
**This project:** `pickup_eta_min` and `pickup_distance_km` were deliberately excluded from the feature set — a request only has these values *if it was matched*, and whether it was ever matched in time is itself entangled with whether it cancelled. Including them would let the model implicitly see the outcome.
**Interview Q:** "How would you have discovered this leak if you hadn't thought of it upfront?" — a suspiciously high AUC (e.g. >0.95) for a genuinely hard prediction problem is the classic tell; the fix is to audit every feature's availability timeline before training, which is what was done here.

### 29. Model drift
**Simple:** a model getting worse over time because the real world changed since it was trained.
**Technical:** a shift in the input distribution (covariate drift) or the input-output relationship (concept drift) relative to training data.
**This project:** not directly demonstrated (single-snapshot training data), but the mechanism is visible: if `λ_base,z` (zone demand) or driver population shifted materially (a real platform's city expanding), a cancellation model trained on the old distribution would need retraining — exactly the argument for periodic recalibration in `docs/PRD.md` Future Roadmap.
**Interview Q:** "How would you detect drift in production?" — monitor the model's live AUC/calibration against a rolling window of recent labeled outcomes, and alert if it degrades past a threshold.

---

## Part D — AI / LLM Concepts

### 30. LLM tool calling
**Simple:** letting an AI model call real functions/programs to get facts, instead of guessing.
**Technical:** the model is given a schema of available functions; it decides which to call and with what arguments, the caller executes them, and the results are fed back for the model to use in its answer.
**This project:** `src/ai_copilot.py` — the AI Marketplace Analyst never invents a number; every metric it cites comes from a tool call to `src/copilot_tools.py`.
**Interview Q:** "What happens if the model wants a number no tool provides?" — the system prompt instructs it to say so explicitly rather than approximate; there's no fallback path that lets it guess.

### 31. RAG (Retrieval-Augmented Generation)
**Simple:** giving a model relevant documents/data to read before it answers, instead of relying only on what it memorized during training.
**Technical:** typically an embedding-based similarity search over a document store, injecting the top results into the model's context.
**This project:** not used — the copilot's tool-calling design (structured function calls against exact result tables) is a better fit here than semantic document retrieval, since the "knowledge" is precise, tabular experiment data, not unstructured text a similarity search would suit.
**Interview Q:** "Why tool-calling over RAG for this use case?" — RAG is for *fuzzy* retrieval over documents; this project's ground truth is *exact* numbers in a table — tool-calling lets the model query them precisely rather than semantically-retrieve an approximate match.

### 32. Why an LLM shouldn't be the source of truth for numerical metrics
**Simple:** LLMs are good at language, not arithmetic — they can plausibly state a wrong number with total confidence.
**Technical:** LLMs generate token sequences by pattern, not by executing a calculation; there's no guarantee an unaided numeric claim is correct, especially for a specific project's exact synthetic data.
**This project:** the architecture enforces `database/calculation engine → numerical truth, LLM → explanation` as a hard boundary — `src/copilot_tools.py` computes every number; the system prompt in `src/ai_copilot.py` explicitly forbids the model from calculating metrics itself.
**Interview Q:** "How would you catch it if the model violated this rule anyway?" — every number in a response should be traceable to a specific tool call's `source` field in the conversation log; an untraceable number in an answer is a bug to fix in the prompt/tool design.

---

## Part E — Backend / Systems

### 33. API
**Simple:** a defined way for one piece of software to ask another piece of software to do something.
**Technical:** a contract (endpoints, request/response shapes) that lets services interoperate without sharing internals.
**This project:** `api/main.py` — e.g. `POST /simulation/run` lets the dashboard, copilot, or any future client run a simulation without importing `src.engine` directly.
**Interview Q:** "Why put an API in front of code you could just import directly?" — a service boundary, not just convenience — it's the natural place to add auth, rate-limiting, and multi-language clients later without touching the simulation code.

### 34. REST
**Simple:** a common style of API design using URLs and standard HTTP verbs (GET, POST) to represent actions.
**Technical:** Representational State Transfer — resources identified by URLs, manipulated via standard HTTP methods, typically stateless between requests.
**This project:** `GET /experiments/{name}`, `POST /simulation/run` — resource-oriented URLs, standard verbs.
**Interview Q:** "Is this API fully RESTful?" — mostly, with one pragmatic exception: `/simulation/run` and `/policy/simulate` are aliases of the same action for two different audiences (engineers vs. product stakeholders) — a small deviation from strict "one URL per resource" for usability.

### 35. PostgreSQL
**Simple:** a popular, reliable, open-source relational (table-based) database.
**Technical:** an ACID-compliant RDBMS supporting complex queries, joins, and JSON columns.
**This project:** not used for the local demo (a 1,080-row CSV needs no database), but a full schema is specified in `docs/SYSTEM_DESIGN.md` §2 as the production path once run volume or concurrent access justifies it.
**Interview Q:** "When would you actually need to add Postgres here?" — once multiple people/services need to write results concurrently, or the per-request table (`ride_requests`) grows past what's comfortable to hold as flat files.

### 36. Caching
**Simple:** storing a result so the next request for the same thing is instant instead of redone from scratch.
**Technical:** trading memory for compute time, with an invalidation strategy for when the underlying data changes.
**This project:** not implemented in the demo API (fast enough not to need it) but specified in `docs/SYSTEM_DESIGN.md` §5 — `/experiments` endpoints would cache the results file in-process/Redis, invalidated on a new `run_experiments.py` execution.
**Interview Q:** "What's the risk of caching without an invalidation plan?" — serving stale results after a new experiment run — exactly why the invalidation trigger (a fresh `run_experiments.py`) is specified alongside the caching idea, not left implicit.

### 37. Asynchronous processing
**Simple:** starting a long task and letting the caller move on, instead of making them wait for it to finish.
**Technical:** a job is queued, runs in the background, and the caller polls or is notified when it's done.
**This project:** not needed for a single 24h simulation (~0.3s) but specified in `docs/SYSTEM_DESIGN.md` §5 for a hypothetical longer (multi-day) simulation: `POST` returns a `run_id` immediately, `GET /simulation/{run_id}` polls for completion.
**Interview Q:** "Why didn't you build this now?" — because building infrastructure for a problem you don't have yet (sub-second runs) is premature complexity — the schema already supports adding it later (`started_at`/`finished_at` columns) without a redesign.

### 38. How this system would scale
**Simple:** running many more simulations, faster, without changing how correct any single simulation is.
**Technical:** the experiment runner is embarrassingly parallel across `(scenario, seed, pricing, dispatch)` combinations — no shared mutable state between runs (each `World` and `SimulationEngine` is independent).
**This project:** `docs/SYSTEM_DESIGN.md` §5 spells out the concrete next step (a process pool or job queue, one worker per run, writing to a shared Parquet dataset or the Postgres schema) with no change needed to the simulation engine itself.
**Interview Q:** "What's the bottleneck if you tried to run 100,000 simulations?" — single-threaded Python's per-run wall-clock time (~0.3s) — the fix is horizontal (more workers), not a rewrite of the simulation logic, because runs are fully independent by construction (a direct consequence of the common-random-numbers design in `docs/EXPERIMENT_DESIGN.md` §P, which requires each run to be a fresh, isolated replay of a pre-generated world).
