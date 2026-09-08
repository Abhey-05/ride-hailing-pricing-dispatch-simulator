# System Design

## 1. Architecture

```
                        ┌─────────────────────┐
                        │   Scenario Config    │  (pricing policy, dispatch
                        │   (Python dataclass)  │   policy, demand/supply level, seed)
                        └──────────┬───────────┘
                                   ▼
                        ┌─────────────────────┐
                        │  SIMULATION ENGINE   │   src/engine.py
                        │  (time-stepped loop) │   1-min ticks, 24h/day
                        └──────────┬───────────┘
                 ┌─────────────────┼──────────────────┐
                 ▼                 ▼                  ▼
        ┌───────────────┐ ┌────────────────┐ ┌────────────────┐
        │ src/world.py   │ │ src/pricing.py  │ │ src/dispatch.py│
        │ (demand/supply │ │ (4 surge        │ │ (5 matching    │
        │  generation,   │ │  policies)      │ │  policies)     │
        │  CRN seeding)  │ │                 │ │                │
        └───────┬────────┘ └────────┬────────┘ └───────┬────────┘
                 └──────────────────┼──────────────────┘
                                    ▼
                          ┌────────────────────┐
                          │ src/metrics.py       │
                          │ (MetricsCollector)   │
                          └──────────┬───────────┘
                                     ▼
                          ┌────────────────────┐
                          │  Results Warehouse   │  results/*.csv, *.parquet
                          │  (file-based, v1)     │  results/manifest.json
                          └──────────┬───────────┘
                     ┌───────────────┼────────────────┐
                     ▼                                ▼
          ┌────────────────────┐          ┌────────────────────────┐
          │ src/experiment_     │          │  src/analysis.py         │
          │  runner.py           │─────────▶│  (bootstrap CI, Wilcoxon,│
          │ (1,080-run matrix)   │          │   effect size, decision  │
          └────────────────────┘          │   table)                 │
                                            └───────────┬────────────┘
                                                        ▼
                                    ┌───────────────────────────────┐
                                    │   api/main.py (FastAPI)        │
                                    └───────────────┬───────────────┘
                                       ┌─────────────┴─────────────┐
                                       ▼                           ▼
                            ┌────────────────────┐     ┌────────────────────┐
                            │ dashboard/app.py     │     │ src/ai_copilot.py    │
                            │ (Streamlit + Plotly)  │     │ (Claude tool-calling)│
                            └────────────────────┘     └──────────┬─────────┘
                                                                    ▼
                                                        ┌────────────────────┐
                                                        │ src/copilot_tools.py │
                                                        │ (deterministic       │
                                                        │  functions only)     │
                                                        └────────────────────┘
```

**Why file-based storage (v1) instead of Postgres:** at 1,080 rows of run-level summary data, a database server adds real operational overhead (Docker, connection pooling, migrations) with zero analytical benefit — pandas reads a 1,080-row CSV in milliseconds. §2 below specifies the schema this *would* become in production, where run volume and concurrent writers justify a real database.

**Why Streamlit instead of a custom React frontend:** this is an internal analytics/experimentation tool for PM/DS/ops audiences, not a consumer product — Streamlit produces a genuinely interactive dashboard in a fraction of the build time, which matters more for a project whose actual substance is the simulation and experiment design, not the frontend.

**Why a thin FastAPI layer at all, if the dashboard could import `src` directly (and does):** it gives the project a real service boundary — the AI copilot, a future mobile ops tool, or a CI job could all consume the same simulation/results without importing Python internals, and it's the natural place to add auth/rate-limiting/logging in a production version.

## 2. Database Schema (Production Path)

Not required to run this project locally (see §1), but specified here as the schema this system would use once run volume, concurrent writers, or multi-user access justify a real database.

```sql
CREATE TABLE zones (
    zone_id         SMALLINT PRIMARY KEY,
    name            TEXT NOT NULL,
    archetype       TEXT NOT NULL,
    x               REAL NOT NULL,
    y               REAL NOT NULL,
    lambda_base     REAL NOT NULL,
    driver_share    REAL NOT NULL
);

CREATE TABLE simulation_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_group    TEXT NOT NULL,             -- 'core' | 'robustness' | 'adhoc'
    scenario            TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    pricing_policy      TEXT NOT NULL,
    dispatch_policy     TEXT NOT NULL,
    horizon_ticks       INTEGER NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    engine_version      TEXT NOT NULL,              -- git SHA of src/ at run time
    UNIQUE (experiment_group, scenario, seed, pricing_policy, dispatch_policy)
);
CREATE INDEX idx_runs_scenario_policy ON simulation_runs (scenario, pricing_policy, dispatch_policy);

CREATE TABLE metrics (
    run_id              UUID REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    metric_name         TEXT NOT NULL,
    metric_value        DOUBLE PRECISION,
    PRIMARY KEY (run_id, metric_name)
);
-- Narrow (run_id, metric_name, value) table rather than one wide column per
-- metric: new metrics can be added without a schema migration, and every
-- chart/analysis query in src/analysis.py becomes a simple filter+pivot.

CREATE TABLE drivers (
    driver_id           BIGINT,
    run_id              UUID REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    home_zone           SMALLINT REFERENCES zones(zone_id),
    shift_start_tick    INTEGER NOT NULL,
    shift_end_tick      INTEGER NOT NULL,
    gross_earnings      DOUBLE PRECISION NOT NULL,
    online_minutes      DOUBLE PRECISION NOT NULL,
    active_minutes      DOUBLE PRECISION NOT NULL,
    trips_completed     INTEGER NOT NULL,
    PRIMARY KEY (run_id, driver_id)
);

CREATE TABLE ride_requests (
    request_id          BIGINT,
    run_id              UUID REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    created_tick         INTEGER NOT NULL,
    origin_zone          SMALLINT REFERENCES zones(zone_id),
    destination_zone      SMALLINT REFERENCES zones(zone_id),
    segment               TEXT NOT NULL,
    final_state           TEXT NOT NULL,            -- COMPLETED | ABANDONED | ...
    final_price            DOUBLE PRECISION,
    surge_multiplier        DOUBLE PRECISION,
    wait_min                DOUBLE PRECISION,
    driver_id               BIGINT,
    PRIMARY KEY (run_id, request_id)
);
CREATE INDEX idx_requests_run_state ON ride_requests (run_id, final_state);

CREATE TABLE policies (
    policy_type          TEXT NOT NULL,             -- 'pricing' | 'dispatch'
    policy_name           TEXT NOT NULL,
    params                 JSONB NOT NULL,
    PRIMARY KEY (policy_type, policy_name)
);

CREATE TABLE experiments (
    experiment_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL,
    description              TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_ids                    UUID[] NOT NULL       -- which simulation_runs belong to this experiment
);
```

**Design notes:**
- `metrics` is narrow (entity-attribute-value shaped) rather than one column per metric, so adding a new metric never requires a migration — every consumer (dashboard, analysis, API) already queries by `metric_name`.
- `ride_requests`/`drivers` are keyed `(run_id, local_id)` rather than a single global surrogate key, since IDs are only ever meaningful within one run.
- `simulation_runs.engine_version` exists specifically so a later analysis can detect "this run used an old, buggy version of the engine" — a real lesson from this project's own Phase 3/4 bug fixes (`CHANGELOG.md`), where several early runs would have needed to be invalidated had they been persisted before the fix.

## 3. API Reference (`api/main.py`)

| Endpoint | Method | Purpose | Validation | Errors |
|---|---|---|---|---|
| `/` | GET | Service metadata / endpoint list | — | — |
| `/policies` | GET | List available scenarios/pricing/dispatch policies | — | — |
| `/simulation/run` | POST | Run one simulation synchronously | `scenario`/`pricing_policy`/`dispatch_policy` must be known enum values; `hours` in (0, 24] | 400 on unknown policy/scenario |
| `/policy/simulate` | POST | Alias of `/simulation/run` | same | same |
| `/simulation/{run_id}` | GET | Fetch a previously-run simulation's config + summary | `run_id` must exist in the in-memory store | 404 if unknown |
| `/simulation/{run_id}/metrics` | GET | Fetch just the metrics dict for a run | same | 404 |
| `/experiments` | GET | Metadata about the pre-computed 1,080-run matrix | `results/results.csv` must exist | 404 if experiments haven't been run yet |
| `/experiments/{name}` | GET | Fetch a named report (`core_comparisons`, `decision_table`) | `name` must match an existing `results/{name}.csv` | 404 |

Request/response bodies are Pydantic models (`SimulationRequest`, `SimulationResponse`) — FastAPI auto-generates OpenAPI docs at `/docs` when the service is running.

**NaN handling:** a run with too few completed trips (e.g. a very short horizon starting at midnight) can legitimately produce `NaN` for a percentile/mean metric with an empty denominator. Raw Python `float('nan')` is not valid JSON, and Starlette's default `JSONResponse` only auto-sanitizes NaN for explicitly float-typed Pydantic fields — not values inside a generic `dict` (which is what `summary` is, since the metric set is meant to be extensible without changing the API schema). `api/main.py::_sanitize_nan` converts NaN to `null` explicitly before the response is serialized. Found and fixed via `tests/test_api.py`, not by inspection — see `CHANGELOG.md`.

## 4. Data Flow

1. `run_experiments.py` generates one `World` per `(scenario, seed)` (`src/world.py`), replays it through all 20 policy combinations, and appends one summary row per run to a pandas DataFrame.
2. `analyze_results.py` reads that DataFrame, computes every paired statistical comparison (`src/analysis.py`), and writes `results/core_comparisons.csv` + `results/decision_table.csv`.
3. `make_charts.py` reads all three result files (plus running two fresh "detailed" simulations for distribution/timeseries charts that need per-request/per-tick data the aggregated summary doesn't carry) and writes every figure in `reports/figures/`.
4. The dashboard and API both read the same `results/*.csv` files directly — there is exactly one source of truth for "what happened in the experiment," and the AI copilot's tools (`src/copilot_tools.py`) read the same files too.

## 5. Scalability, Latency, Caching, Async Jobs

- **Current scale:** ~0.3s per 24-simulated-hour run in pure Python; 1,080 runs in ~5.5 minutes single-threaded. This is adequate for the current experiment design and does not need optimization.
- **If scaled to 10,000+ runs:** the runner is embarrassingly parallel across `(scenario, seed, pricing, dispatch)` — a straightforward next step would be `multiprocessing.Pool` or a job queue (e.g., Celery/RQ) with each worker running one simulation and writing its row to a shared Parquet dataset or the Postgres schema in §2, rather than any code-level rewrite of the engine itself.
- **API caching:** `/experiments` and `/experiments/{name}` re-read CSVs on every request; at production scale these would be cached in-process (or in Redis) with invalidation on a new `run_experiments.py` execution, rather than re-reading disk per request.
- **Async jobs:** `/simulation/run` currently runs synchronously (fast enough at 24h/~0.3s not to need this); a production version exposing longer simulations (e.g., a multi-day run) would make this a background job with a `POST` returning a `run_id` immediately and a `GET /simulation/{run_id}` polling for completion — the schema in §2 already supports this (`started_at`/`finished_at` columns).
- **Experiment storage growth:** the narrow `metrics` table (§2) keeps storage growth linear in (runs × metrics), not requiring a schema change as new metrics are added — the main growth lever to watch in production would be `ride_requests`, which is one row per simulated request; a real deployment would likely sample or aggregate this table rather than storing every request indefinitely.
