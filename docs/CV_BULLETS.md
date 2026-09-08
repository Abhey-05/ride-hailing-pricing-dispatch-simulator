# CV Bullets

Written after the project was actually built and results actually generated — every number below is read directly from `results/` and `docs/EXPERIMENTS.md`. No claim here is made about capabilities the implementation doesn't have.

**Project name:** Ride-Hailing Pricing & Dispatch Simulator

---

## Version 1 — Navi (fintech/consumer-tech, marketplace + risk sensibility)

- Built a marketplace simulation (10-zone city, Poisson demand, logistic behavioral models) and ran a statistically powered 1,080-simulation experiment to test whether a software lever (dispatch) could outperform a spend lever (surge pricing) — found dispatch cut P90 wait 8.9% while *improving* revenue (+2.7%) and driver earnings (+1.9%), with the conclusion validated against a 12-condition sensitivity sweep.
- Designed the statistical framework end-to-end (common-random-numbers paired design, bootstrap confidence intervals, pre-registered significance thresholds) specifically to avoid the failure mode of shipping a change on a lucky-looking but statistically weak result — and used the same framework to catch and report a competing algorithm that looked more sophisticated but measurably underperformed.

## Version 2 — General Tech PM

- Ran a 1,080-simulation experiment across 4 pricing and 5 dispatch strategies for a ride-hailing marketplace, identifying a matching-algorithm change that reduced rider wait time by 8.9% with no increase in price or driver cost — validated with paired statistical tests (p<0.001) and a sensitivity analysis across the model's six most uncertain assumptions.
- Built the full decision-support stack around the finding: a documented product requirements doc with a north-star/guardrail framework, an interactive dashboard and API for stakeholders to explore results, and an AI analyst that answers marketplace questions by calling real data functions rather than generating numbers itself.

## Version 3 — Marketplace PM

- Quantified the trade-off between three classic marketplace-balancing levers (surge pricing, driver incentives, dispatch) using a from-scratch two-sided-market simulation; found dispatch was the only lever that improved wait time, driver earnings, and revenue simultaneously, informing a phased production rollout recommendation (shadow mode -> 1% -> 100%).
- Defined and defended a North Star metric (completed trips per online driver-hour) against four rejected alternatives, paired with 5 guardrail metrics specifically chosen to prevent the North Star from being gamed by starving low-liquidity zones or under-supplying the marketplace.

## Version 4 — AI/Tech PM

- Built an AI Marketplace Analyst using Claude tool-calling over a marketplace simulation's results, enforcing a strict separation between a deterministic calculation engine (source of numerical truth) and the LLM (explanation only) — the model cannot answer a quantitative question without a real function call backing every number.
- Delivered a genuine ML component (gradient-boosted cancellation-risk classifier, AUC 0.82 vs. 0.55 for the existing single-variable heuristic) with an explicit feature-leakage audit, demonstrating where marketplace-condition features (time of day, supply/demand imbalance) mattered far more than rider-specific ones for predicting cancellation.

## Version 5 — ATS-keyword-optimized

- Designed and executed a 1,080-run A/B-style simulation experiment (Python, NumPy, pandas, SciPy) comparing pricing and dispatch algorithms in a two-sided marketplace, using paired statistical testing, bootstrap confidence intervals, and a pre-registered significance framework to identify a dispatch strategy that reduced P90 wait time by 8.9% (p<0.001) with no cost trade-off.
- Built a full-stack analytics product: FastAPI backend, Streamlit/Plotly dashboard, scikit-learn ML model, and an LLM tool-calling AI copilot (Anthropic Claude API), backed by 34 automated tests and complete technical/product documentation (PRD, system design, experiment design).

---

## Navi / Fintech-PM Relevance

Without claiming any knowledge of Navi's actual internal systems, this project demonstrates several transferable capabilities relevant to a fintech/consumer-tech PM role:

- **Experimentation discipline:** pre-registered hypotheses, paired statistical design, significance *and* practical-significance bars, sensitivity analysis before trusting a conclusion — the same discipline a lending or insurance product needs before shipping a risk-model or pricing change.
- **Pricing under constraint:** the surge-cap design (bounded, product-driven, not purely profit-maximizing) is directly analogous to a credit-limit or interest-rate cap decision — trading some theoretical revenue for trust, predictability, and regulatory safety.
- **Marketplace/two-sided thinking:** balancing supply (drivers) and demand (riders) transfers directly to balancing capital supply and borrower demand in a lending marketplace, or risk-pool balance in insurance.
- **Metrics that resist gaming:** the North Star + guardrail framework here exists specifically so a team can't "win" by degrading something the headline metric doesn't capture — the same discipline needed for a metric like approval rate (which can be gamed by lowering underwriting standards) needing a paired default-rate guardrail.
- **AI used with guardrails, not blindly:** the "LLM explains, engine calculates" separation is the same architecture a fintech product would need for e.g. an AI assistant explaining a credit decision — the explanation must never be the source of the number.
- **Honest, quantified trade-off communication:** the decision matrix (cost vs. experience vs. revenue) and the explicit "what would change my recommendation" answers throughout this project's documentation are the same communication style a lending/risk PM needs when presenting a model change to a risk committee.

**Transferring the thinking, concretely:** replace "rider wait time" with "loan decision latency," "driver earnings" with "lender/investor yield," "surge pricing" with "dynamic interest-rate/limit adjustment," and "dispatch quality" with "underwriting-model quality" — the same three-lever decision matrix, the same guardrail-constrained optimization framework, and the same "don't trust a result until it survives a sensitivity check" discipline apply directly.
