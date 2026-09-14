# Ride-Hailing Surge Pricing & Dispatch Simulator

A synthetic marketplace simulation and experimentation platform for studying how **pricing** and **dispatch** policy affect rider wait time, driver earnings, and platform revenue in a ride-hailing marketplace — built to answer one question rigorously rather than to look impressive at a glance.

> **All data in this project is synthetic simulation output** generated from documented, labeled assumptions (see [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md)). Nothing here is real Uber/Ola/Lyft data or a claim about real-world performance.

## The question

> **Can better dispatch reduce rider wait time without raising driver-side or pricing-side cost — or does the marketplace only respond to surge and incentives?**

The answer was not assumed going in. It came out of running **1,080 independent simulations** across 4 pricing policies × 5 dispatch policies × 6 demand/supply scenarios × up to 24 random seeds, then testing the result statistically.

## Headline result

Under the current baseline pricing policy (`BASIC_SURGE`), switching dispatch from naive nearest-driver matching to **`ETA_OPTIMIZED`** dispatch (which also considers drivers about to finish a nearby trip, not just currently-idle ones):

| Metric | Baseline (`NEAREST_DRIVER`) | `ETA_OPTIMIZED` | Change | Significance |
|---|---|---|---|---|
| P90 rider wait | 10.25 min | 9.33 min | **−8.9%** | Wilcoxon p = 1.7×10⁻⁵, n=24 paired seeds |
| Driver earnings/online-hour | 153.71 | 156.67 | **+1.9%** | p = 6.0×10⁻⁷ |
| Cancellation rate | 20.6% | 19.6% | **−4.7%** (relative) | — |
| Platform revenue | 91,043 | 93,493 | **+2.7%** | p = 1.2×10⁻⁷ |
| North Star (trips/online-driver-hour) | 1.948 | 1.990 | **+2.2%** | — |

This holds — with the *same* direction and statistical significance — under all four pricing policies (7.8%–11.3% P90 wait reduction). No guardrail regresses. In this simulation, **dispatch is a Pareto improvement, not a trade-off**: it wasn't necessary to raise prices or pay drivers more to get riders picked up faster.

A follow-up sensitivity sweep (`sensitivity_analysis.py`) perturbed the six most uncertain synthetic parameters (price elasticity, rider patience, driver acceptance sensitivity, congestion, demand intensity, fleet size) by ±30% each: **the direction of the result survived all 12 perturbations**, with the magnitude ranging 4.2%–13.3% — enough to trust the qualitative conclusion, not enough to promise the exact 8.9% figure in a real business case.

Full results, statistical methodology, and — just as importantly — the policy that *didn't* work (`ADVANCED_HEURISTIC`, a more "sophisticated" heuristic that actually made P90 wait 4.5–8.3% *worse* than the naive baseline) are in [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md).

## Why this project exists

Ride-hailing marketplaces balance rider experience, driver earnings, and platform revenue using three levers: **surge pricing**, **driver incentives**, and **dispatch/matching quality**. The first two show up immediately in a P&L; the third is a software investment that's hard to justify without a controlled experiment. This project builds the sandbox to run that experiment safely, before touching real production traffic — the same reasoning a marketplace PM would use to decide where to invest next quarter.

## Architecture

```
Scenario config (pricing × dispatch × demand/supply)
        │
        ▼
Simulation Engine (1-minute timesteps, 24h/day)
  ├─ Demand generator (Poisson arrivals, zone/time-of-day driven)
  ├─ Driver supply model (shift schedules, online/offline)
  ├─ Pricing engine (4 surge policies)
  ├─ Dispatch engine (5 matching policies)
  └─ Metrics collector
        │
        ▼
Results warehouse (results/*.csv, *.parquet — 1,080 runs)
        │
        ├──▶ Statistical analysis        (src/analysis.py: paired bootstrap CI, Wilcoxon, effect size)
        │
        ▼
Decision-intelligence layer            (src/decision.py, src/zone_state.py)
  ├─ Marketplace Health Score (4 weighted, empirically-normalized dimensions)
  ├─ Guardrails (absolute + baseline-relative)
  ├─ Policy recommendation (best overall vs. best under guardrails)
  └─ Live counterfactual simulation (fresh paired run, real bootstrap CI)
        │
        ▼
ML forecasting layer                   (src/ml_demand.py, src/ml_wait_time.py, src/ml_cancellation.py)
  └─ Trained models persisted to models/*.joblib, used for live inference (no retraining)
        │
        ├──▶ Streamlit + Plotly dashboard   (dashboard/app.py — Overview, Marketplace Map, Experimentation, ...)
        ├──▶ FastAPI service                (api/main.py)
        └──▶ AI Marketplace Analyst         (src/ai_copilot.py, tool-calling over the layers above)
                    │
                    ▼
            Human reviews recommendation → approves/runs counterfactual → (optionally) experiments further
```

The AI layer sits strictly on top: it orchestrates and explains via tool calls into the layers above, and never computes a metric, forecast, or recommendation itself (docs/PRD.md "AI guardrails").

Full design rationale, database schema (as it would be operationalized in production), and API docs: [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

## What's actually implemented

**Simulation & experimentation core:**
- **Simulation engine** (`src/engine.py`): a from-scratch, time-stepped agent simulation — 10 zones, Poisson demand, logistic accept/cancel/dispatch-acceptance models, all specified in [`docs/MATHEMATICAL_MODEL.md`](docs/MATHEMATICAL_MODEL.md) *before* any code was written.
- **4 pricing policies**: `NO_SURGE`, `BASIC_SURGE`, `AGGRESSIVE_SURGE`, `CAPPED_SMOOTHED_SURGE` (`src/pricing.py`).
- **5 dispatch policies**: `NEAREST_DRIVER`, `ETA_OPTIMIZED`, `DRIVER_EARNINGS_AWARE`, `MARKETPLACE_AWARE`, `ADVANCED_HEURISTIC` (`src/dispatch.py`) — each a documented heuristic, explicitly *not* claimed to be globally optimal (see Math Model §H.5 for why an exact optimal-assignment solver isn't used).
- **Experiment framework**: 1,080 runs with common-random-numbers variance reduction for paired statistical comparisons (`src/experiment_runner.py`, `src/world.py`).
- **Statistical analysis**: bootstrap CIs, paired Wilcoxon + t-tests, effect sizes, a pre-registered practical-significance bar (`src/analysis.py`).

**Decision-intelligence layer** (`src/decision.py`, `src/zone_state.py`, `src/sim_context.py`) — sits on top of the engine, makes no independent claims:
- **Marketplace Health Score**: 4 weighted dimensions (Rider Experience, Driver Experience, Marketplace Efficiency, Business Performance), each a documented blend of metrics normalized against the empirical 5th/95th percentiles of the 1,080-run matrix — not arbitrary targets.
- **Guardrails**: absolute operational limits (cancellation, utilization, surge, driver earnings) plus baseline-relative guardrails (generalized from the decision table's own logic), surfaced as pass/fail with the specific binding constraint named.
- **Policy recommendation, 4 objective profiles**: `recommend_policy()` scores every pre-computed (pricing, dispatch) combo for a scenario against one of 4 named, documented objectives (`OBJECTIVE_PROFILES`: Rider-first, Balanced, Revenue-first, Driver-first — selectable in the UI), and reports both the guardrail-passing recommendation *and* the unconstrained best (they are not always the same). Added after an audit found the single old default objective had no term penalizing rider price — see CHANGELOG "Objective audit" for the full investigation, including why `AGGRESSIVE_SURGE + ETA_OPTIMIZED` won so often and the empirical crossover point where a rider-first weighting flips the recommendation. A "Recommendation distribution" chart and an "objective sensitivity" table make this context-sensitivity visible rather than asserted.
- **Live counterfactual simulation**: `run_counterfactual()` runs a fresh, paired, common-random-numbers comparison of any two policies on demand, with a real bootstrap CI and Wilcoxon p-value — not an estimate. Explicitly labeled "validated counterfactual" in the UI to distinguish it from the instant pre-computed-matrix estimate.
- **Marketplace Map**: a spatial view over the existing 10-zone city (Plotly, zone x/y grid already in `src/config.py` — no new geo dependency), with a metric selector, click-to-select zone markers, and per-zone click-through detail with a rule-based causal explanation.

**ML layer** (`src/ml_cancellation.py`, `src/ml_demand.py`, `src/ml_wait_time.py`) — each with a documented target, features, leakage discipline, train/test split, and a naive baseline the model has to beat:
- **Cancellation-risk prediction**: GBM vs. logistic regression vs. a rule-based baseline (AUC 0.82 vs. 0.78 vs. 0.55) — feature importance shows time-of-day and marketplace imbalance dominate, not rider patience (`train_cancellation_model.py`).
- **Near-term demand forecasting**: predicts a zone's next-15-minute request volume from recent lags + time + available supply (GBM MAE 2.35 vs. a "same as last window" naive baseline's 3.01, R² 0.70 vs. 0.48) (`train_demand_model.py`).
- **Realized wait-time prediction**: predicts a rider's actual request-to-pickup wait — not the simulator's already-deterministic distance-based ETA — from request-time marketplace conditions (GBM MAE 2.75 min vs. a naive distance/speed ETA's 8.12 min; dominant feature is marketplace imbalance, not distance) (`train_wait_time_model.py`).
- Both forecasting models persist to `models/*.joblib` and are used for *live* inference (no retraining) by the AI Copilot's `forecast_demand` / `forecast_eta` tools.

**Product surfaces:**
- **Streamlit dashboard** (`dashboard/app.py`): Overview (health score, recommendation card, live counterfactual, map, policy tradeoff), a dedicated Marketplace Map tab, Pricing/Dispatch detail, Experimentation (best-policy card + progressive disclosure into the full 1,080-run matrix), and an AI Copilot tab.
- **FastAPI service** exposing the engine and results (`api/main.py`).
- **AI Marketplace Analyst**: an LLM tool-calling copilot (8 tools: pre-computed lookups, the objective-aware recommendation engine, live what-if simulation, and the two ML forecast tools) that answers marketplace questions by calling deterministic functions against real results — it never computes a metric itself (`src/ai_copilot.py`, `src/copilot_tools.py`). Provider-agnostic: works with `ANTHROPIC_API_KEY` (Claude) or `GROQ_API_KEY` (Groq), verified live against both — see `docs/AI_COPILOT_TRANSCRIPT.md` for a real transcript. Every answer in the dashboard shows its full tool-call trace (name, input, result), not just the final text.
- **99 automated tests** covering reproducibility, every invariant in the Validation Plan, API endpoints, the decision layer (including all 4 objective profiles), zone aggregation, both ML models, and centralized formatting/color logic (`tests/`).

## Setup & running it

```bash
git clone <this-repo>
cd meltwater

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run one simulation
python run_simulation.py --scenario NORMAL --pricing BASIC_SURGE --dispatch ETA_OPTIMIZED --seed 0

# Run the full 1,080-run experiment matrix (~5-6 minutes)
python run_experiments.py

# Run the statistical analysis over it
python analyze_results.py

# Regenerate every chart in reports/figures/
python make_charts.py

# Run the sensitivity analysis (Experiment 12)
python sensitivity_analysis.py

# Train and compare the rule-based vs. ML cancellation-prediction models
python train_cancellation_model.py

# Train the demand-forecasting and wait-time-forecasting models
# (persists to models/*.joblib -- the AI copilot's forecast tools need these)
python train_demand_model.py
python train_wait_time_model.py

# Run the test suite
pytest -q

# Launch the dashboard (Overview / Marketplace Map / Pricing / Dispatch / Experimentation / AI Copilot)
streamlit run dashboard/app.py

# Launch the API
uvicorn api.main:app --reload

# Ask the AI Marketplace Analyst (requires ANTHROPIC_API_KEY or GROQ_API_KEY)
# put ONE of these in a local, gitignored .env file (auto-loaded by both
# ask_copilot.py and the dashboard's AI Copilot tab), e.g.:
#   GROQ_API_KEY=gsk_...
python ask_copilot.py "Which dispatch policy performs best, and is it statistically real?"
# force a specific provider if both keys are set: AI_PROVIDER=groq python ask_copilot.py "..."
```

## Reproducibility

Every run takes an explicit integer seed; `numpy.random.SeedSequence` (never Python's built-in `hash()`, which is randomized per-process) derives every downstream random stream deterministically. `results/manifest.json` records the exact configuration, seed list, and library versions used to produce `results/results.csv`. Re-running `python run_experiments.py` reproduces it exactly.

## Documentation map

| Doc | What's in it |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product requirements: personas, north star, guardrails, goals/non-goals, rollout plan |
| [`docs/MATHEMATICAL_MODEL.md`](docs/MATHEMATICAL_MODEL.md) | Every equation, with variables, intuition, and a worked numeric example |
| [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) | City/zone model, full parameter table, all labeled SYNTHETIC ASSUMPTION |
| [`docs/EXPERIMENT_DESIGN.md`](docs/EXPERIMENT_DESIGN.md) | Experiment matrix, CRN methodology, statistical test plan, decided *before* results existed |
| [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md) | The 11 experiments, actual results, interpretation, and honest limitations |
| [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) | Architecture, DB schema, API reference, scaling notes |
| [`docs/LEARNING_GUIDE.md`](docs/LEARNING_GUIDE.md) | 38 concepts (Poisson processes to LLM tool-calling) explained from zero |
| [`docs/INTERVIEW_GUIDE.md`](docs/INTERVIEW_GUIDE.md) | 30-sec to 10-min pitches, 4 audience-specific versions, 75+ Q&A |
| [`docs/PRODUCT_CASE_STUDY.md`](docs/PRODUCT_CASE_STUDY.md) | 5 mock PM case interviews built on this project |
| [`docs/CRITICAL_REVIEW.md`](docs/CRITICAL_REVIEW.md) | A skeptical senior-PM review of this project's weaknesses, run honestly against itself |
| [`docs/AI_COPILOT_TRANSCRIPT.md`](docs/AI_COPILOT_TRANSCRIPT.md) | Real, verified Q&A transcript from a live run of the AI copilot |
| [`docs/CV_BULLETS.md`](docs/CV_BULLETS.md) | 5 CV bullet variants + fintech/Navi relevance discussion |
| [`reports/FINAL_REPORT.md`](reports/FINAL_REPORT.md) | The condensed end-to-end project report |
| [`presentation/project_presentation.pptx`](presentation/project_presentation.pptx) | 12-slide recruiter/interviewer-facing deck |
| [`CHANGELOG.md`](CHANGELOG.md) | Every non-trivial implementation decision and bug found, in order |

## Limitations (see `docs/EXPERIMENTS.md` and `docs/CRITICAL_REVIEW.md` for the full list)

- All behavioral parameters (price elasticity, patience, driver acceptance sensitivity) are synthetic, not fit to real data — magnitudes are a property of this model, not a real-world prediction.
- The core statistical comparison has real power from 24 paired seeds (via common random numbers), but "1,080 runs" is not "1,080 independent samples" for any one comparison — this is stated explicitly, not glossed over.
- No long-run churn feedback loop (a bad week doesn't reduce a rider's future demand or a driver's future participation) — likely the single biggest gap vs. reality.

## License

MIT — see `LICENSE`.
