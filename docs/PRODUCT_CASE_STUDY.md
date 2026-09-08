# Product Case Study — 5 Mock PM Interviews

Each case uses the standard structure: clarify → segment → hypothesize → pick metrics → diagnose → propose solutions → weigh trade-offs → design an experiment → plan rollout. Model answers draw directly on this project's framework and findings, since a real interview answer should sound like it's coming from someone who actually built and measured this.

---

## Case 1: "Rider wait time has increased by 20%. What do you do?"

**Clarify:** Is this citywide or specific zones/times? Sudden (this week) or gradual (this quarter)? Did anything else change — pricing, dispatch, driver payout — in the same window?

**Segment:** Break the 20% down by zone (city-wide vs. localized), by time of day (peak vs. off-peak), and by whether it's driven by more *requests* (demand) or fewer *available drivers* (supply) — the same `imbalance = outstanding/(available+1)` decomposition this project uses.

**Hypothesize:** (a) a real demand surge (event, weather) outpacing supply, (b) a supply-side shock (driver churn, a competing platform's incentive push), (c) a regression in the dispatch or pricing system itself (a bad deploy).

**Metrics to check first:** P90 wait by zone/hour (not just the citywide average — could be a few zones driving the whole number, exactly the concern the North Star's guardrails exist to catch), completion rate, cancellation rate, driver acceptance rate, and whether a code/config change shipped in the same window.

**Diagnose:** If driver acceptance rate also dropped, suspect a dispatch regression (bad matches) or a driver-side incentive problem, not pure demand. If supply (`available_drivers`) actually fell, look upstream (driver churn, competitor activity). If it's demand-only and price-inelastic zones are worst-hit, surge may be under-reacting.

**Solutions, with trade-offs (this project's decision matrix):**
- Raise surge caps → faster relief, but a real rider-experience/brand cost this project's own model doesn't fully price.
- Add driver incentives → costs real cash, no guarantee of full offset if driver supply elasticity is lower than hoped (an explicitly unmodeled parameter in this project).
- Investigate/improve dispatch → this project's finding is that dispatch fixes on the order of 8-11% of P90 wait with *no* incremental driver cost — the first lever to check before assuming you need to spend money.

**Experiment:** shadow-mode test any dispatch fix first (cheapest, safest); a small-percentage surge cap increase second if dispatch alone doesn't close the gap.

**Rollout:** per this project's phased plan (`docs/PRD.md` §16) — shadow → 1% → 5% → 25% → 100%, watching all 5 guardrails at each step.

---

## Case 2: "The CFO wants to cut driver incentive spend by 30% without hurting rider experience. How do you approach it?"

**Clarify:** Is incentive spend currently zone-targeted or blanket? What's the current marginal return (incremental driver-hours per incentive dollar)?

**Segment:** Identify which zones/times actually need the incentive (chronically undersupplied) vs. where it's spend with little marginal effect (already well-supplied) — the zone-level supply/demand ratio this project's `get_zone_supply_demand_ranking` tool computes directly.

**Hypothesize:** most incentive spend is probably concentrated on a few well-known problem zones/times; cutting it uniformly would hurt those disproportionately, while cutting it in already-liquid zones would have near-zero rider impact.

**Metrics:** North-star-per-dollar-of-incentive-spend by zone, P90 wait, driver earnings/hour (must not collapse for the drivers who'd otherwise churn).

**Solutions & trade-offs:** (a) reallocate rather than cut uniformly — this project's data shows dispatch can absorb some of the slack in *any* zone at zero cost, so a natural move is: cut incentives in the least-impacted zones first, and simultaneously ship the dispatch improvement everywhere to partially backfill the wait-time impact of the cut. (b) The decision matrix's core lesson directly applies here: dispatch is the "free" lever — spend cuts should target zones where dispatch improvement alone can hold the guardrails.

**Experiment:** a phased incentive reduction in the lowest-impact zones first, paired with the dispatch rollout, watching P90 wait and completion rate as the trip-wire.

**Rollout:** reduce in 2-3 test zones for 2 weeks, confirm guardrails hold, then expand — the same phased discipline as any other lever change in this framework.

---

## Case 3: "A new dispatch algorithm looks great in offline testing but you're nervous about launching it. Walk me through your decision."

**Clarify:** How was "looks great" measured — a single run, or a proper statistical comparison? (This is precisely this project's central discipline.)

**Segment/diagnose:** Ask the same three questions this project's own Experiments doc had to answer honestly: (1) is the effect size practically significant, not just statistically detectable? (2) does it hold across multiple random conditions (seeds/scenarios), or could it be a lucky run — exactly why the core experiment used 24 paired seeds, not 1? (3) does it pass every guardrail, not just the primary metric — this project caught `ADVANCED_HEURISTIC` failing exactly this way, looking sophisticated but underperforming on the metric that mattered.

**Hypothesize the nervousness is well-founded if:** the offline test used only one scenario/seed, didn't check guardrails, or the underlying heuristic combines many hand-tuned weights that were never independently validated (this project's own post-mortem on why `ADVANCED_HEURISTIC` failed).

**Solutions:** re-run the offline comparison with a proper paired design and pre-registered significance bar before trusting it; if it still holds, proceed to shadow mode — never skip straight from "one good offline run" to a live rollout.

**Experiment/rollout:** identical phased plan as Case 1 — shadow mode is specifically the safety net for "looked great offline, not sure yet."

---

## Case 4: "Riders in low-income neighborhoods report worse service (longer waits, higher cancellation) than riders elsewhere. What do you do?"

**Clarify:** Is "worse service" purely a supply/demand liquidity issue in those zones, or is the matching/pricing algorithm itself treating them differently?

**Segment:** Exactly the zone-level breakdown this project's `MARKETPLACE_AWARE` dispatch policy and zone heatmap chart are built for — check whether those zones are structurally undersupplied (few drivers ever end up there) vs. whether dispatch/pricing logic is actively deprioritizing them.

**Hypothesize:** most likely a supply-side liquidity gap (fewer drivers choose to operate there) compounded by a dispatch policy that — like this project's own `NEAREST_DRIVER` and `DRIVER_EARNINGS_AWARE` — has no mechanism to protect an undersupplied zone's driver pool, pulling its last available driver to serve a nearby, easier request instead.

**Ethics framing (this project's own PRD §18):** this is exactly the geographic-fairness concern flagged in this project's ethics section — algorithmic bias doesn't require any explicit demographic input; a purely geometry-based dispatch policy can still produce disparate outcomes by zone.

**Solutions:** (a) a `MARKETPLACE_AWARE`-style penalty that protects low-liquidity zones from having their supply pulled away, (b) zone-targeted incentives, (c) report fulfillment rate and P90 wait *segmented by zone*, not just pooled, as a standing guardrail (this project's own Future Roadmap item #5).

**Experiment:** A/B test the zone-protective dispatch penalty specifically in the affected zones, primary metric = P90 wait and fulfillment rate *in those zones specifically*, not the citywide average (which could mask the improvement).

**Rollout:** targeted to the affected zones first, not citywide — a geographic-equity fix doesn't need to touch zones that aren't affected.

---

## Case 5: "Your VP asks: 'Should we build a dispatch team or a pricing team next quarter?' Give a recommendation in 5 minutes."

**Clarify:** What's the current team's biggest gap — is there already a working pricing system and a weak dispatch system, or vice versa?

**Frame the trade-off directly using this project's decision matrix (`docs/PRD.md` §13):**
- Pricing changes are faster to ship (a formula change) but have real, harder-to-reverse costs (rider trust, potential regulatory exposure) and, per this project's Experiment 2 finding, can't be evaluated in isolation from an unmodeled driver-supply response.
- Dispatch changes take longer to build (a real matching engine, not a formula) but, per Experiment 4, showed the only *simultaneous* win across wait time, driver earnings, and revenue — with zero marginal cost once shipped.

**Recommendation:** dispatch team, with a specific, falsifiable first project (an ETA/look-ahead-aware matching improvement) and a pre-committed measurement plan (P90 wait primary, the same 4 guardrails) — not a vague "improve dispatch" mandate.

**Trade-off to name explicitly:** a dispatch team is a bigger upfront engineering investment with a payoff proven only in simulation so far — the VP should expect a shadow-mode validation phase before claiming the win, not an immediate quarter-one metric move.

**What you'd ask for:** headcount for 1 dispatch engineer + 1 DS to run the production A/B test this project's simulation results justify, plus access to real driver pickup-acceptance logs to replace this project's synthetic acceptance-sensitivity parameter with a calibrated one before finalizing the business case.
