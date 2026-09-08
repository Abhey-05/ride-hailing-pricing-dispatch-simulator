# Interview Guide

## A. Explain My Project — Pitches at Every Length

### 30-second explanation
"I built a simulation of a ride-hailing marketplace to answer one question: can better dispatch reduce rider wait time without raising prices or driver costs? I ran 1,080 simulated experiments across different pricing and matching strategies, and found that a smarter dispatch algorithm cut wait times by about 9% while *improving* driver earnings and platform revenue — a real win-win, not a trade-off, and I proved it statistically, not just by eyeballing a chart."

### 1-minute explanation
Add to the 30-second version: "The simulator models 10 city zones, Poisson-distributed demand, and realistic rider/driver behavior — logistic functions for price sensitivity and cancellation, not arbitrary if/else rules. I tested 4 pricing policies and 5 dispatch policies, including a 'smart' one that also considers drivers about to finish a nearby trip, not just idle ones. That one policy — `ETA_OPTIMIZED` — beat the naive nearest-driver baseline in every pricing scenario I tried, with p-values under 0.001. I also found a more 'sophisticated' heuristic that actually performed *worse* — which taught me that adding more objectives to a dispatch algorithm isn't automatically better if the weights aren't validated."

### 3-minute deep explanation
Add: "I didn't want this to be a toy — so before writing any simulation code, I wrote out the full mathematical spec (every equation, every parameter, labeled as a synthetic assumption) and the experiment design (how many runs, what statistical test, what would count as a real result) as separate documents. Then I built the engine, validated it against ten sanity checks (does more demand actually increase wait time? does surge never exceed its cap?), and only then ran the real experiment. I used common random numbers — giving every policy the exact same simulated riders and drivers at a given seed — so I could detect a real effect with only 24 random seeds instead of needing hundreds. I built a Streamlit dashboard and a FastAPI service on top of it, and an AI copilot that can answer questions like 'which zone is most undersupplied' — but the AI never calculates numbers itself, it calls the same deterministic functions the dashboard uses and just explains the result. Every step — including two real bugs I found and fixed, and one 'nearest driver isn't actually pickup-optimal' surprise — is documented in a changelog."

### 10-minute technical walkthrough
Structure: (1) the product question and why it's hard to answer with production data alone → (2) the mathematical model, with 2-3 equations explained (Poisson arrivals, logistic acceptance, the surge formula) → (3) the 5 dispatch policies and *why* a heuristic instead of an exact optimizer (the `O((R+D)³)` argument) → (4) the experiment design decision to trade scenario breadth for seed depth (24 seeds on one scenario for statistical power, vs. spreading 4 seeds across 120 cells) → (5) the actual results, including the honest negative one (`ADVANCED_HEURISTIC`) → (6) the AI copilot's tool-calling architecture and why the LLM never computes a metric → (7) what you'd do next (sensitivity analysis, a driver-supply-response model, a real production A/B test).

### Product-manager version
"I framed this the way a marketplace PM would: define the north star (completed trips per driver-hour — a liquidity metric that can't be gamed by just adding drivers), define guardrails (P90 wait, cancellation, driver earnings, price index) so I couldn't declare victory by breaking something else, then ran a rigorous experiment and built a decision matrix comparing the three levers — surge, incentives, dispatch — on cost, wait time, and driver impact. The recommendation: prioritize dispatch, because it's the only lever that improved rider experience *and* revenue *and* driver earnings simultaneously, at zero incremental cost."

### Data-science version
"The core contribution is treating dispatch-policy comparison as a proper paired experiment: I used common random numbers so the same simulated demand hits every policy, turning what would be a noisy 24-seed unpaired comparison into a much more sensitive paired one. I used bootstrap CIs (not normal-theory, given n=24) and a paired Wilcoxon test, with a pre-registered practical-significance bar so I couldn't cherry-pick a statistically-significant-but-tiny result as a headline. I also built and evaluated an ML cancellation model with an explicit leakage audit — some obviously predictive fields (pickup ETA) had to be excluded because they only exist *because* of the outcome I was predicting."

### Engineering version
"It's a time-stepped discrete-time simulation, not a full discrete-event system — a deliberate simplicity trade-off I can defend. Randomness is seeded through `numpy.random.SeedSequence`, never Python's `hash()`, specifically because `hash()` on strings is randomized per-process and would silently break reproducibility. The trickiest bug was in the look-ahead dispatch policies: an early version let a still-busy driver get double-booked onto a second trip before finishing the first — I fixed it with a proper 'queued next assignment' handoff at trip completion, and wrote a test that would catch a regression via an assertion inside the engine itself, not just an external check."

### Business version
"The insight that matters commercially: of the three ways to fix a supply/demand imbalance — raise prices, pay drivers more, or dispatch smarter — only the third improved the customer experience *and* the P&L at the same time in this simulation, because it has no marginal cost per ride once built. That reframes a common instinct (when wait times are bad, raise surge) — the data here says test the software fix first."

---

## B. 75+ Interview Questions

Each entry: ideal answer → why that's the right answer → a likely follow-up → what a strong candidate says out loud.

### Product (12)

**1. Why did you build this?**
Ideal: to prove a specific, falsifiable hypothesis about dispatch vs. pricing, not to have a portfolio project. Reasoning: shows the project was question-driven, not resume-driven. Follow-up: "What if the hypothesis had been false?" Strong response: "I'd have reported that honestly — the doc even says I'd rather have a real 16.7% than a fabricated 19%."

**2. What problem are you solving?**
Ideal: platforms default to surge/incentives because they're easy to measure, while dispatch improvements are hard to justify without a controlled experiment — this project makes that experiment cheap and safe to run. Follow-up: "Isn't this obvious — of course better software helps?" Strong response: "It's intuitive, but 'obviously true' claims still need a number and a p-value before you spend engineering budget on them — that's exactly what was missing."

**3. Who is the user?**
Ideal: six personas, from Marketplace PM to City Ops (see PRD §3). Follow-up: "Which one would actually use this weekly?" Strong response: "Probably the Dispatch/Optimization DS, screening new matching ideas before a costly production test."

**4. What is the north-star metric, and why?**
Ideal: completed trips per online driver-hour — a liquidity metric, chosen after explicitly rejecting 4 alternatives (Math Model §M). Follow-up: "What's wrong with just using GBV?" Strong response: "GBV rewards charging more regardless of experience — it doesn't distinguish 'we got efficient' from 'we just raised prices.'"

**5. Why this metric and not X?**
Ideal: depends on X — walk through the rejected alternatives table. Follow-up: "What would make you change your mind?" Strong response: "If guardrail gaming showed up in practice — e.g., a policy inflating the north star by quietly starving one zone — I'd add a per-zone floor guardrail."

**6. What trade-offs did you make?**
Ideal: file storage over Postgres, Streamlit over React, 24 deep seeds over 4 shallow×6-scenario seeds, time-stepped over full discrete-event. Follow-up: "Which one would you revisit first?" Strong response: "The scenario/seed trade — I'd want more seeds on the robustness scenarios (currently only 6) before trusting Experiment 7-10's results as strongly as the core one."

**7. Why not optimize revenue directly?**
Ideal: revenue is a guardrail, not the target — optimizing it directly would justify unlimited surge, which the caps explicitly prevent. Follow-up: "So when does revenue matter most?" Strong response: "As a tie-breaker among policies that already clear every experience/driver guardrail — exactly how the decision table is built."

**8. Why not optimize wait time directly, full stop, ignoring guardrails?**
Ideal: an unconstrained wait-time optimizer could hurt driver earnings or revenue arbitrarily to shave a few seconds. Follow-up: "Give a concrete failure mode." Strong response: "Send every driver to the single nearest request regardless of fairness or their own trip economics — technically minimizes average pickup, wrecks driver retention."

**9. What would you launch first?**
Ideal: `ETA_OPTIMIZED` dispatch, in shadow mode, per the PRD rollout plan. Follow-up: "Why shadow mode and not straight to 1%?" Strong response: "To validate the algorithm's real-world decision logic and latency without any rider/driver ever being affected by a bug."

**10. What would you measure after launch?**
Ideal: the same 5 guardrails plus the primary metric, in a real A/B test (PRD §15). Follow-up: "What's different about measuring it for real vs. in simulation?" Strong response: "Real variance, real confounders (weather, competitor pricing) — I'd need the actual production P90-wait variance to size the experiment correctly, which I don't have from a simulation."

**11. What's the single biggest weakness in your product thinking here?**
Ideal: no modeled driver supply-response to incentives, so the three-lever comparison in the decision matrix is incomplete for the incentive column. Follow-up: "How would you fix it?" Strong response: "Add a driver online-probability function conditioned on local surge/incentive level, with its own elasticity parameter — flagged as future work, not hidden."

**12. If you had one more week, what would you build?**
Ideal: the sensitivity analysis (Experiment 12) — it's the most important open item because every headline number rests on synthetic parameters. Follow-up: "Why that over more features?" Strong response: "A flashy new feature on top of an unvalidated foundation is worse than a validated foundation with fewer features."

### Marketplace (8)

**13. Why does surge exist?**
Ideal: see Learning Guide #3. Follow-up: "Does your data support that?" Strong response: "Yes — Experiment 3 shows surge simultaneously raising revenue and lowering cancellation, a real market-clearing signature."

**14. How does surge affect demand?**
Ideal: suppresses it, modestly, via the price-sensitivity logistic — a 6.5% price rise costs about 0.3-0.4 points of conversion in this model. Follow-up: "Is that elasticity realistic?" Strong response: "It's a synthetic, labeled assumption, not fit to real data — the sensitivity analysis (not yet run) would test how much the conclusion depends on it."

**15. How does it affect supply?**
Ideal: not modeled in v1 — flagged explicitly as the project's biggest scope gap. Follow-up: "Why leave that out?" Strong response: "Time-boxing — modeling driver online-probability-vs-price well requires its own calibration effort, and I'd rather ship an honest gap than a rushed, unvalidated mechanism."

**16. What happens if surge is too high?**
Ideal: demand collapses, and in the real world, brand/regulatory backlash — which is exactly why every policy has a hard cap (2.0-3.0x). Follow-up: "Why cap at 3.0 and not 5.0?" Strong response: "A synthetic decision assumption, documented as such — a real cap would come from historical rider-churn-vs-surge-level data."

**17. What happens if surge is too low (or banned)?**
Ideal: `NO_SURGE` in the results has the *highest* cancellation rate (21.7%) of any pricing policy — no mechanism to relieve congestion during imbalance. Follow-up: "So is surge always good?" Strong response: "Within the range tested and this model's assumptions, yes on net — but the model can't see brand/regulatory costs, so that's not the full picture in reality."

**18. What is marketplace liquidity, concretely, in your numbers?**
Ideal: the North Star value itself, 1.948 trips/driver-hour at baseline, 1.990 with `ETA_OPTIMIZED`. Follow-up: "Is that a big or small improvement?" Strong response: "2.2% on the North Star, but the more decision-relevant number is the 8.9% P90 wait improvement it comes with, which is what riders actually feel."

**19. What's a supply/demand imbalance signal you *didn't* use?**
Ideal: absolute driver count difference, real-time competitor pricing, weather. Follow-up: "Why ratio over absolute difference?" Strong response: "Scale invariance — a ratio treats a small and a large zone consistently; a difference doesn't."

**20. How would you detect a zone going into imbalance in production?**
Ideal: live per-zone `imbalance` computation, the same formula, alerting past a threshold. Follow-up: "What would you do about it automatically?" Strong response: "Feed it straight into the same surge/dispatch mechanisms this project already models — that's the whole point of computing it in real time."

### Technical (12)

**21. Explain your architecture.**
Ideal: engine → results warehouse → analysis/dashboard/API/copilot, all reading the same source of truth (System Design doc). Follow-up: "What's the single point of failure?" Strong response: "The results CSV itself in v1 — no concurrent-write protection, which is exactly why the doc specifies Postgres as the production path."

**22. Why this database (or lack thereof)?**
Ideal: file-based for now, deliberately, because 1,080 rows don't need a server; Postgres schema fully specified for when they would. Follow-up: "What's the tipping point?" Strong response: "Concurrent writers or per-request-level data retention at real scale — the `ride_requests` table would be the first to actually need a database."

**23. How does dispatch work, mechanically?**
Ideal: each tick, sort waiting requests oldest-first, greedily assign each to its best-scoring available (or soon-free) driver per the active policy, remove that driver from the pool. Follow-up: "Why oldest-first, not by policy-specific priority?" Strong response: "To isolate policy differences to the scoring function alone, not request-ordering — a controlled-comparison design choice, not just convenience."

**24. What's the computational complexity of your dispatch policies?**
Ideal: O(R·D) per tick for 4 of 5 policies, same order for the 5th (a fixed top-K prefilter) — see Math Model §H. Follow-up: "What would the exact optimal algorithm cost?" Strong response: "O((R+D)³) via the Hungarian algorithm, re-solved every tick — infeasible at any real scale."

**25. How would you scale this to millions of requests?**
Ideal: the experiment runner is embarrassingly parallel across independent runs; the per-tick dispatch loop itself would need spatial indexing (e.g., a zone/grid-based candidate lookup) rather than scanning all drivers. Follow-up: "Where's the real bottleneck?" Strong response: "Single-threaded Python wall-clock time for a huge number of *runs*, not the per-tick logic within one run, which is already bounded and cheap."

**26. Walk me through a bug you found and fixed.**
Ideal: the look-ahead dispatch double-booking bug (CHANGELOG.md, Phase 3). Follow-up: "How did you catch it?" Strong response: "I added the assertion directly into the engine's assignment code, not just an external test — so any regression fails loudly at the exact moment it happens, not three steps downstream."

**27. Why not a full discrete-event simulation?**
Ideal: 1-minute resolution is fine given nothing in this marketplace changes meaningfully faster than that; discrete-event adds real complexity (event queues) without proportionate insight gain. Follow-up: "When would that trade-off flip?" Strong response: "If I needed sub-minute precision — e.g. modeling exact GPS ping timing — which this project's product question doesn't require."

**28. How do you guarantee reproducibility?**
Ideal: `numpy.random.SeedSequence`-derived streams, tested via an explicit repeat-run diff (`test_reproducibility_same_seed_identical_summary`). Follow-up: "What would break it?" Strong response: "Any code path that consumes randomness in an order that depends on dict iteration order or wall-clock time instead of the seeded RNG — which is why the whole design routes every random decision through explicit seeded generators."

**29. What test gave you the most confidence in this system?**
Ideal: the ten Validation Plan checks (does more demand increase wait, does surge respect its cap, etc.) — because they test *behavioral sanity*, not just code correctness. Follow-up: "What would you add next?" Strong response: "A property-based test (e.g. Hypothesis) fuzzing scenario parameters to search for invariant violations I haven't thought to test directly."

**30. How does the API handle errors?**
Ideal: explicit 400 for unknown policy/scenario values, 404 for unknown run IDs/report names — validated before any simulation runs. Follow-up: "What's an error case you missed at first?" Strong response: "NaN metrics from a near-empty run breaking JSON serialization — found by a test, not by inspection, and fixed with an explicit sanitization step."

**31. Why FastAPI and not Flask/Django?**
Ideal: built-in request/response validation via Pydantic, automatic OpenAPI docs, async-ready — all useful for a service meant to be a clean contract for other consumers (dashboard, copilot, future clients). Follow-up: "Did you need async here?" Strong response: "Not yet — the sync endpoints are fast enough — but FastAPI doesn't cost anything for that headroom."

**32. What would you refactor if this became a real production system?**
Ideal: move results storage to Postgres, add auth/rate-limiting to the API, parallelize the experiment runner, add per-zone live guardrail monitoring. Follow-up: "What would you explicitly NOT change?" Strong response: "The core engine's tick-sequence logic — it's been validated against ten behavioral checks; I'd want very strong justification before touching it."

### Data / Experimentation (10)

**33. Why simulation instead of just analyzing existing data?**
Ideal: no real ride-hailing dataset was available/appropriate to use for this project, and simulation lets you test *counterfactual* policies (a dispatch algorithm that's never been run) that don't exist in any dataset. Follow-up: "What's the cost of that choice?" Strong response: "External validity — the magnitude of every result is a property of this synthetic model, stated explicitly throughout, not a real-world number."

**34. Why 1,080 runs specifically?**
Ideal: not arbitrary — 480 for a properly powered core hypothesis test (24 seeds × 20 policy combos) plus 600 for robustness across 5 stress scenarios, exceeding the ≥480 target while prioritizing statistical power over raw scenario coverage. Follow-up: "Why not just do 4 seeds × 120 cells = 480 and call it done?" Strong response: "Because that gives only 4 independent samples per comparison — nowhere near enough power; I'd rather have fewer, deeper comparisons than many shallow ones."

**35. How did you choose your parameters?**
Ideal: directional realism + internal consistency, every value labeled SYNTHETIC ASSUMPTION in `docs/ASSUMPTIONS.md`, several recalibrated after Phase 4 validation caught unrealistic behavior (e.g., grid scale). Follow-up: "What's an example of a bad initial choice you caught?" Strong response: "A city scale that produced 30-50 minute pickup ETAs, crushing driver acceptance to near zero — caught by simply running the simulation and looking at whether the output was economically sane."

**36. How did you validate the simulator?**
Ideal: ten behavioral sanity checks (more demand → more wait, surge respects cap, etc.), run as automated tests, gating before any experiment run counted as valid. Follow-up: "What would you have done if a check failed and you couldn't find why?" Strong response: "Stopped and treated it as a blocking issue — the design explicitly says not to proceed to large experiments until sanity checks pass."

**37. What are the limitations of your experiment design?**
Ideal: robustness scenarios have only 6 seeds (lower power than the core 24); no sensitivity analysis yet; no real-world calibration. Follow-up: "Which limitation worries you most?" Strong response: "The missing sensitivity analysis — without it, I can't yet say how much the headline number would move if my elasticity or patience assumptions were off by 30%."

**38. Explain common random numbers to a non-technical stakeholder.**
Ideal: "I give every policy I test the exact same simulated riders, arriving at the exact same times, with the exact same luck — so any difference I see is really about the policy, not about one run getting an easier day." Follow-up: "Does this ever backfire?" Strong response: "It only reduces noise *within* a seed's comparison — it doesn't create more independent evidence, so I still needed 24 separate seeds, not just 1 run replayed cleverly."

**39. Mean vs. median — when do they disagree, and did they here?**
Ideal: they diverge under skew (a few extreme outliers pull the mean but not the median); checked explicitly for P90 wait and found no case where the two told a different story. Follow-up: "Why check this at all?" Strong response: "Because reporting only the mean could hide a story where a policy is 'better on average' due to a few lucky seeds while being worse for most of them — checking the median is a cheap robustness check."

**40. What's your practical-significance bar, and why have one at all?**
Ideal: ≥5% relative effect AND a 95% CI excluding zero, decided before results existed. Follow-up: "What if a result was significant at 4.9%?" Strong response: "Reported honestly as 'real but below the pre-registered bar' — exactly what happened with `DRIVER_EARNINGS_AWARE` and `MARKETPLACE_AWARE` in the results."

**41. How do you know your statistical test was appropriate?**
Ideal: paired Wilcoxon chosen specifically because n=24 is small and non-normality can't be ruled out; paired t-test reported alongside as a cross-check, with any disagreement between them flagged as worth investigating. Follow-up: "Did they ever disagree?" Strong response: "No — in this run, Wilcoxon and the paired t-test agreed on every significant/non-significant call, which is itself a small piece of evidence the effect is genuine and not an artifact of one test's assumptions."

**42. What's a result you found that you didn't expect?**
Ideal: `ADVANCED_HEURISTIC` underperforming the naive baseline, and `ETA_OPTIMIZED` beating `NEAREST_DRIVER` on pickup distance itself (not just wait time) despite the latter being literally designed to minimize that. Follow-up: "What did you do when you saw that?" Strong response: "Investigated the mechanism (look-ahead candidate pool is structurally larger) and updated the relevant validation-check documentation rather than either hiding the result or assuming it was a bug."

### AI (10)

**43. Where is AI used in this project?**
Ideal: one place — the AI Marketplace Analyst copilot — deliberately not sprinkled everywhere. Follow-up: "Why so narrow?" Strong response: "Because the instruction I held myself to was 'AI only where it adds real value,' and question-answering over structured results is a good fit; forcing AI into the core simulation or pricing logic would have made both worse and harder to audit."

**44. Why use an LLM here at all?**
Ideal: natural-language access to structured results for non-technical stakeholders (a City Ops manager shouldn't need to write pandas to ask "which zone is worst"). Follow-up: "Could you have built this without an LLM?" Strong response: "Yes, as a fixed set of dashboard filters — the LLM adds value specifically for open-ended, compositional questions a fixed UI can't anticipate."

**45. Why not let the LLM make the dispatch/pricing decision live?**
Ideal: those decisions need to be fast, deterministic, and auditable at massive scale — an LLM call is slow, non-deterministic, and expensive compared to the closed-form logistic functions already used. Follow-up: "Is there ANY place an LLM belongs in the live decision path?" Strong response: "Possibly for tuning/reviewing the *weights* of a heuristic offline (exactly the kind of miscalibration that hurt `ADVANCED_HEURISTIC`), not for making the per-request decision itself."

**46. How do you prevent hallucination?**
Ideal: tool-calling architecture — every number must come from a real function call; system prompt explicitly forbids self-calculated numbers. Follow-up: "Is that enough on its own?" Strong response: "It's necessary but not sufficient — I'd also want output validation checking that every number in a final answer matches a number that actually appeared in a tool result, which isn't built yet."

**47. What is RAG, and why didn't you use it?**
Ideal: see Learning Guide #31. Follow-up: "When would you add it?" Strong response: "If the copilot needed to answer questions against this project's *documentation* (e.g. 'why did you choose this elasticity value') rather than its structured results — that's a better RAG fit than the numeric-lookup use case I actually built."

**48. What is tool calling, mechanically?**
Ideal: see Learning Guide #30 — model picks a function + arguments from a schema, caller executes it, result is fed back. Follow-up: "What happens if the model calls a tool with bad arguments?" Strong response: "The tool functions validate/raise on bad input and the error is returned to the model as a tool result, not thrown — so the model can see the failure and try a different approach instead of crashing the whole exchange."

**49. How would a prompt injection attack apply here, if at all?**
Ideal: low surface area — the copilot only reads from a fixed, code-controlled results directory; it doesn't ingest arbitrary user-supplied documents or web content that could carry injected instructions. Follow-up: "Where would the risk go up?" Strong response: "If the copilot were extended to read rider-submitted free-text (e.g. support tickets) as context — that content should be treated as data, never as instructions, the same principle used everywhere else in this system's design."

**50. What access control does the copilot have?**
Ideal: read-only access to `results/*.csv` and the ability to run new simulations (which don't touch any production system) — no write access to anything. Follow-up: "Is that appropriate for this use case?" Strong response: "Yes — a PM-facing analyst tool has no legitimate reason to need write access to anything."

**51. Why Claude specifically?**
Ideal: strong native tool-calling support, and consistency with the rest of the toolchain used to build this project. Follow-up: "Would GPT-4 work as well?" Strong response: "Almost certainly, for this use case — the architecture (deterministic tools, thin LLM layer) is model-agnostic by design, which is itself a good practice."

**52. How would you evaluate the copilot's answer quality?**
Ideal: not yet built — would need a small labeled set of question/expected-tool-call pairs to check the model picks the right tool, plus human review of explanation quality. Follow-up: "What's the single most important failure mode to catch?" Strong response: "The model citing a number that doesn't match any tool result it actually received — a hard correctness bug, not just a style issue."

### Business (10)

**53. Would you increase surge or improve dispatch?**
Ideal: dispatch, per the decision matrix — it's the only lever that improved rider experience, driver earnings, and revenue simultaneously. Follow-up: "Forever, or just for now?" Strong response: "For now — this conclusion could shift if a real driver-supply-response model showed incentives outperforming dispatch at solving actual supply shortages, which this version can't test."

**54. How does this make money?**
Ideal: it doesn't directly — it's a decision-support tool that de-risks which lever to invest engineering/marketing budget in. Follow-up: "So what's the ROI?" Strong response: "Avoided cost of a wrong bet — e.g., not spending a quarter on a driver-incentive program if dispatch would have gotten more of the benefit for free."

**55. What is the ROI of dispatch investment specifically, per your numbers?**
Ideal: +2.7% platform revenue and +1.9% driver earnings/hour at zero incremental marginal cost per ride, vs. AGGRESSIVE_SURGE's +6.0% revenue that comes with real rider-experience and brand risk this model doesn't price in. Follow-up: "Which is bigger, and does that change the recommendation?" Strong response: "Surge's revenue number is bigger, but it's not a fair comparison — dispatch's gain is closer to 'free money,' surge's gain has real (unmodeled) costs attached."

**56. What would you launch?**
Ideal: `ETA_OPTIMIZED` dispatch, shadow mode first. Follow-up (repeat of #9, expect consistency): confirm same answer, same reasoning.

**57. What could cause this project — or its real-world analogue — to fail?**
Ideal: the missing driver-supply-response mechanism means the "dispatch beats incentives" conclusion could be wrong if real incentive elasticity is much higher than assumed. Follow-up: "How would you find out before betting the roadmap on it?" Strong response: "Run the sensitivity analysis first, then a small real shadow-mode test — exactly the rollout plan already specified."

**58. How would you pitch this to a driver-ops stakeholder skeptical of an algorithm change?**
Ideal: lead with the guardrail, not the headline — "driver earnings per hour go up, not down, and I can show you the confidence interval." Follow-up: "What if they don't trust the simulation at all?" Strong response: "Fair — that's exactly why the recommendation is shadow mode first: prove it on real data before any driver's actual assignment changes."

**59. How does this connect to fintech/lending (Navi-style) product thinking?**
Ideal: same shape of problem — balancing a two-sided or resource-constrained system (credit risk vs. approval rate is a supply/demand-style trade-off), same experimentation discipline (A/B test design, guardrails, pre-registered significance bars), same "don't let the model make the final call, keep a deterministic ground truth" principle for e.g. a credit-decision-explaining LLM tool. Follow-up: "Give one concrete lending analogue." Strong response: "Loan approval threshold ≈ surge cap: both are a lever that trades an easy-to-measure metric (approval rate/GBV) against a harder-to-measure risk (default rate/rider churn), and both need a guardrail-constrained decision framework, not a single optimized number."

**60. What real-world data would most improve this project's business case?**
Ideal: real rider price-elasticity and cancellation curves, real driver pickup-distance acceptance logs, any existing incentive-elasticity estimates. Follow-up: "If you could only get one?" Strong response: "Driver acceptance-vs-pickup-distance data — it's the parameter the core finding (`ETA_OPTIMIZED` winning) is most mechanically dependent on."

### About You / The Project (8, behavioral-style)

**61. What was the hardest part of building this?**
Strong response: "Debugging the look-ahead dispatch double-booking issue — it only showed up under specific timing conditions, and I only caught it because I'd already written an invariant assertion directly into the engine, not because I spotted it by reading the code."

**62. What would you do differently if you started over?**
Strong response: "Write the driver-supply-response model from the start — retrofitting it now means re-running the whole 1,080-run matrix, whereas building it into world generation from day one would have cost little extra."

**63. How did you decide when a result was 'done' vs. needed more work?**
Strong response: "Against the pre-registered practical-significance bar, not vibes — a result either cleared the bar or it didn't, decided before I saw the data."

**64. What's a piece of feedback (from yourself, in the changelog) you took seriously?**
Strong response: "The zero-acceptance bug taught me to sanity-check a model's *emergent* behavior, not just its equations in isolation — every individual formula was 'correct' and the system was still broken."

**65. How do you stay honest about a simulation's limits when presenting results?**
Strong response: "Every results doc in this project repeats the same caveat: this is not real-world causal evidence, and I say exactly why in `docs/EXPERIMENT_DESIGN.md` §T rather than only in a buried footnote."

**66. What's a decision you made that you're least confident in?**
Strong response: "The synthetic price-elasticity and patience parameters — directionally reasonable, but I have no real data backing the specific numbers, which is exactly why the sensitivity analysis matters."

**67. How do you know you're not fooling yourself with a good-looking result?**
Strong response: "Pre-registering the significance bar before seeing results, and reporting the `ADVANCED_HEURISTIC` failure just as prominently as the `ETA_OPTIMIZED` win — a project that only ever reports wins is the tell of one that got tuned to its own answer."

**68. What are you proudest of in this project?**
Strong response: "That the headline number is real — I didn't have a target percentage in mind and back into it; the 8.9% came out of the analysis script, and I'd have reported 3% or 15% exactly the same way."

### Extra depth (rounding out to 75+)

**69. Why 10 zones and not more/fewer?**
Strong response: "Enough to have distinct archetypes (residential, commercial, airport, etc.) with real directional flow patterns, small enough to reason about and debug by hand."

**70. Why a 24-hour simulated day instead of a full week?**
Strong response: "A day captures every time-of-day pattern already; a week would mainly add day-of-week effects, which weren't part of this project's core question."

**71. What's the difference between abandonment and post-match cancellation in your model, and why track separately?**
Strong response: "Abandonment (pre-match) costs nothing but a lost booking; post-match cancellation wastes a driver's pickup trip — different product costs, different parameters, tracked as separate hazard functions."

**72. Why did you cap dispatch look-ahead at 3 minutes?**
Strong response: "A synthetic assumption balancing 'enough lookahead to matter' against 'not so much that the prediction of a driver's future position becomes unreliable' — a good sensitivity-analysis candidate I haven't run yet."

**73. How do you know your dispatch policies are actually different from each other, not just noise?**
Strong response: "The confidence intervals in the results — `ETA_OPTIMIZED`'s CI never overlaps zero, and it's visibly separated from the other four policies' CIs in the chart, not just a different point estimate."

**74. What was your biggest assumption you'd most want to validate with real data first?**
Strong response: "Driver acceptance sensitivity to pickup distance (`γ_pickup`) — it's the parameter that makes dispatch policy matter at all in this model, so if real drivers are far less pickup-distance-sensitive than assumed, the whole headline result would shrink."

**75. If a real company's data showed the opposite result — dispatch didn't help — what would you conclude?**
Strong response: "That the bottleneck in that market is genuinely absolute supply, not matching quality — which is itself a useful, actionable finding, not a failure of the exercise."

**76. How would you explain 'common random numbers' to your own dispatch/optimization engineering team?**
Strong response: "We're not comparing algorithm A's Tuesday to algorithm B's Wednesday — we're replaying the identical Tuesday through both algorithms and only changing the one variable we're testing."

**77. What's the one chart you'd show a VP who has 30 seconds?**
Strong response: "The confidence-interval chart (`reports/figures/10_confidence_intervals.png`) — it shows the winner, the losers, and the statistical uncertainty in one image."
