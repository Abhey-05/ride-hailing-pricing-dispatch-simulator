# Critical Self-Review

Written as a skeptical senior PM/engineering interviewer would actually push back — not a self-congratulation pass. Each item: what's weak, why it matters, and what was (or wasn't) done about it.

## What's genuinely strong

- The headline result is real, not reverse-engineered: the analysis script was written and locked *before* looking at results, with a pre-registered practical-significance bar. The `ADVANCED_HEURISTIC` failure is reported as prominently as the `ETA_OPTIMIZED` win — a project that only reports wins would be the tell of an unreliable one.
- The math spec, experiment design, and assumptions were written *before* the engine — and the mathematical model document's own "internal consistency check" section catches real issues (zero-denominator handling, probability bounds) rather than asserting them without verification.
- Every bug that was actually found (grid-scale miscalibration, EMA bootstrapping failure, look-ahead double-booking, NaN JSON serialization, a broken what-if override) is documented in `CHANGELOG.md` with root cause and fix — not hidden.

## What's weak, and what an interviewer would challenge

### 1. The single biggest modeling gap: no driver supply-response to price/incentives
**The problem:** the decision matrix (`docs/PRD.md` §13) compares surge, dispatch, and incentives — but incentives can't actually be evaluated on equal footing, because the model has no mechanism for driver online-probability to respond to price or incentive level. Supply is entirely exogenous (shift schedules drawn independently of any pricing signal).
**Why an interviewer would push on this:** "You built a three-way decision matrix and only two of the three levers are actually modeled — isn't your headline conclusion ('dispatch beats incentives') just an artifact of incentives not being simulated at all?"
**Honest answer:** yes, partially. The dispatch-vs-*surge* comparison is fully simulated and defensible. The dispatch-vs-*incentive* comparison is qualitative/directional, not simulated, and the PRD says so explicitly rather than papering over it with a fabricated incentive model. This was not fixed in this pass — it's the top item in the Future Roadmap, correctly prioritized but still open.

### 2. Statistical power outside the core scenario is thin
**The problem:** the core hypothesis test has 24 paired seeds (strong); every robustness scenario (peak demand, supply shortage, demand shock, low demand, congested peak) has only 6. Experiment 7 (demand shock) and Experiment 10 (low demand) explicitly report non-significant p-values (0.0625 and 0.25) alongside encouraging point estimates.
**Why an interviewer would push:** "You're citing an 8.9% point estimate under demand shock with a p-value that wouldn't clear your own bar — isn't that exactly the kind of number you told me not to trust?"
**Honest answer:** correct, and `docs/EXPERIMENTS.md` says so in the same breath as reporting the number — but it's still a judgment call whether including an underpowered point estimate at all, even with a caveat, invites over-reading it. A stricter version of this project would either run more robustness seeds or omit those numbers until they clear significance. Not fixed in this pass (would require re-running ~500 more simulations, a reasonable next step, not done here due to scope).

### 3. `ADVANCED_HEURISTIC`'s weights were never validated before being included in the "official" experiment matrix
**The problem:** a heuristic combining four objective terms was designed, given specific weights, and run through the full 480-run core matrix *before* anyone checked whether those weights made sense in isolation. It turned out to underperform the naive baseline in every configuration.
**Why an interviewer would push:** "If you're willing to ship an unvalidated heuristic into your 'rigorous' 480-run experiment, what else in this project wasn't checked before being trusted?"
**Honest answer:** this is a fair hit. The fix that *was* applied: report the failure honestly and root-cause it (weight imbalance between the ETA term and the imbalance/cancel-risk terms) rather than quietly dropping the policy or re-tuning it after seeing results (which would have been a subtler form of p-hacking). The fix that *wasn't* applied: retune and re-run it, or add a pre-flight single-tick sanity check for any new heuristic's weight balance before it enters a 24-seed experiment. Flagged as Future Roadmap item #6.

### 4. Everything is synthetic — how much does that matter? (Updated: now tested)
**The problem:** every behavioral parameter — price elasticity, patience, driver acceptance sensitivity — is a labeled guess. `docs/EXPERIMENT_DESIGN.md` §W specifies a sensitivity sweep to test whether the headline conclusion survives a ±30% perturbation of the shakiest assumptions.
**Why an interviewer would push:** "You've told me five times in this documentation that your parameters are made up. What's actually stopping the whole conclusion from flipping if `γ_pickup` were 30% different?"
**Answer (now backed by data, not just intent):** `sensitivity_analysis.py` was run — 12 perturbations (6 parameters × ±30%), 8 seeds each. The *sign* of the core finding survived every single one (`docs/EXPERIMENTS.md` Experiment 12); the *magnitude* ranged from −4.2% to −13.3% depending on the parameter, most sensitive to fleet size and congestion. This upgrades the honest claim from "the qualitative conclusion is probably robust" to "the qualitative conclusion was tested against its six biggest uncertainties and did not break" — while still correctly refusing to promise the exact 8.9% headline number as precise (the PRD recommendation is phrased as a range for exactly this reason). What remains untested: combined/worst-case perturbations (all six moved unfavorably at once) were not run — flagged as the next-most-valuable increment, not claimed as done.

### 5. No real-world calibration, at all
**The problem:** not one parameter in this project is fit to, or checked against, real ride-hailing data (none was available/appropriate for this project's scope). The qualitative mechanism (surge suppresses demand, better dispatch reduces wait) is well-supported by real marketplace economics; the specific magnitudes are not.
**Why an interviewer would push:** "If I put this in front of a real pricing team, what would they say?" Honest answer: "Probably 'the mechanism is right but I don't believe your specific 8.9% until I see it against our own elasticity numbers' — which is exactly the correct reaction, and exactly why this project's every results doc repeats the causality warning instead of only stating it once."

### 6. The AI copilot was never actually run end-to-end
**The problem:** `src/ai_copilot.py` and `src/copilot_tools.py` are complete and the tool functions are unit-tested, but the Claude tool-calling loop itself was never exercised with a real API key (none was available in the build environment).
**Why an interviewer would push:** "You're claiming an AI feature works. Did you ever actually watch it answer a question?"
**Honest answer:** no — this is stated plainly in `CHANGELOG.md` and should be stated plainly in any interview, not glossed over. The deterministic half (the part that matters most for correctness — never letting the LLM compute a number) is tested; the conversational half is not verified beyond code review.

### 7. Utilization dropping while everything else improves needed a real explanation, not a hand-wave
**The problem:** `ETA_OPTIMIZED` lowers driver utilization by 1.5% relative to baseline even as it raises earnings and completed trips. This is real and correctly explained in `docs/EXPERIMENTS.md` Experiment 5 (shorter pickup legs reduce "committed time" per trip) — but it's the kind of number a less careful version of this project could have either hidden or gotten wrong.
**Status:** addressed — explained, not hidden — but worth flagging here because it's exactly the kind of metric interaction a reviewer should specifically probe for in any project claiming a "Pareto improvement."

### 8. The dashboard and API were smoke-tested, not stress-tested
**The problem:** the dashboard was verified to load, run a simulation, and render the experimentation tab via real browser automation — genuinely tested, not just assumed. But edge cases (very short horizons producing all-NaN metrics, concurrent users, malformed inputs beyond the one 400-path tested) were not exhaustively probed.
**Status:** the one edge case that *was* found (NaN JSON serialization) was found by a real test and fixed. This suggests more edge cases likely exist but weren't specifically hunted for.

## What would make this top 5% among student/portfolio PM projects

1. ~~Actually run the sensitivity analysis and report whether the headline result survives it~~ — **done in this pass** (`sensitivity_analysis.py`, `docs/EXPERIMENTS.md` Experiment 12): sign preserved across all 12 perturbations, magnitude ranges 4.2%–13.3%.
2. Add the driver-supply-response mechanism, even a simple one, so the three-lever decision matrix stops being two-thirds simulated and one-third asserted. *(Still open.)*
3. Re-run the robustness scenarios with 24 seeds each (not 6) so Experiments 7 and 10 stop needing a "not statistically significant, but..." caveat. *(Still open.)*
4. Actually exercise the AI copilot against a live API key and include a real transcript, not just tested tool functions. *(Still open — no API key available in the build environment.)*
5. Add a per-zone fairness/equity guardrail (Gini coefficient on driver earnings, or fulfillment-rate floor per zone) and report it alongside the existing five guardrails — the ethics section names this risk but the metrics layer doesn't yet measure it. *(Still open.)*
6. Test combined worst-case parameter perturbations (all six moved unfavorably simultaneously), not just one-at-a-time — the one-at-a-time sweep in item 1 could still miss a compounding failure mode. *(Still open.)*

Item 1 was prioritized and completed in this pass because it was the highest-leverage open question (whether the headline number could be trusted at all); items 2–6 remain explicit, prioritized scope cuts under real time constraints, not oversights — and saying so directly is itself supposed to be the strongest signal in this document: the project is being held to the same evidentiary standard it asks everyone else to meet.
