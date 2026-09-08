"""
Thin FastAPI service wrapping the simulation engine and pre-computed
experiment results. Run with:

    uvicorn api.main:app --reload --port 8000

Design note: this API does no business logic of its own -- every number it
returns comes straight from src.engine / src.metrics or the results/ files
produced by run_experiments.py + analyze_results.py. That separation is
deliberate: it is the same "engine computes, service serves" boundary the AI
copilot (src/ai_copilot.py) relies on to avoid ever inventing a metric.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src import config, engine, world

app = FastAPI(
    title="Ride-Hailing Marketplace Simulator API",
    description="Run marketplace simulations and query pre-computed experiment results.",
    version="1.0.0",
)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# In-memory run store -- fine for a portfolio/demo service; a production
# version would persist this in Postgres (see docs/SYSTEM_DESIGN.md).
_RUN_STORE: dict[str, dict] = {}


class SimulationRequest(BaseModel):
    scenario: str = Field(default="NORMAL", description="One of the configured scenarios.")
    pricing_policy: str = Field(default="BASIC_SURGE")
    dispatch_policy: str = Field(default="NEAREST_DRIVER")
    seed: int = Field(default=0, ge=0)
    hours: float = Field(default=24.0, gt=0, le=24.0)

    def validate_choices(self):
        if self.scenario not in config.SCENARIOS:
            raise HTTPException(400, f"Unknown scenario '{self.scenario}'. Options: {list(config.SCENARIOS)}")
        if self.pricing_policy not in [p.value for p in config.PricingPolicy]:
            raise HTTPException(400, f"Unknown pricing_policy '{self.pricing_policy}'.")
        if self.dispatch_policy not in [d.value for d in config.DispatchPolicy]:
            raise HTTPException(400, f"Unknown dispatch_policy '{self.dispatch_policy}'.")


class SimulationResponse(BaseModel):
    run_id: str
    scenario: str
    seed: int
    pricing_policy: str
    dispatch_policy: str
    summary: dict


@app.get("/")
def root():
    return {
        "service": "Ride-Hailing Marketplace Simulator API",
        "endpoints": [
            "POST /simulation/run", "GET /simulation/{run_id}", "GET /simulation/{run_id}/metrics",
            "POST /policy/simulate", "GET /policies", "GET /experiments", "GET /experiments/{name}",
        ],
    }


@app.get("/policies")
def list_policies():
    return {
        "scenarios": list(config.SCENARIOS.keys()),
        "pricing_policies": [p.value for p in config.PricingPolicy],
        "dispatch_policies": [d.value for d in config.DispatchPolicy],
    }


def _sanitize_nan(d: dict) -> dict:
    """A run with very few/zero completed trips (e.g. a short horizon
    starting at midnight, before most driver shifts begin) legitimately
    produces NaN for percentile/mean metrics with an empty denominator.
    Python's float('nan') is not valid JSON -- Starlette's default
    JSONResponse only sanitizes NaN for explicitly float-typed Pydantic
    fields, not values inside a plain dict, so it must be done explicitly
    here rather than relying on the framework."""
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in d.items()}


def _run_simulation(req: SimulationRequest) -> SimulationResponse:
    req.validate_choices()
    horizon_ticks = int(round(req.hours * 60))
    w = world.generate_world(req.scenario, seed=req.seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w,
        config.PricingPolicy(req.pricing_policy),
        config.DispatchPolicy(req.dispatch_policy),
        config.SCENARIOS[req.scenario],
    )
    result = eng.run()
    run_id = str(uuid.uuid4())
    payload = {
        "run_id": run_id,
        "scenario": result.scenario,
        "seed": result.seed,
        "pricing_policy": result.pricing_policy,
        "dispatch_policy": result.dispatch_policy,
        "summary": _sanitize_nan(result.summary),
    }
    _RUN_STORE[run_id] = payload
    return SimulationResponse(**payload)


@app.post("/simulation/run", response_model=SimulationResponse)
def simulation_run(req: SimulationRequest):
    return _run_simulation(req)


@app.post("/policy/simulate", response_model=SimulationResponse)
def policy_simulate(req: SimulationRequest):
    """Alias of /simulation/run -- kept as a separate route because product
    stakeholders think of this as 'simulate a policy', not 'run a simulation'."""
    return _run_simulation(req)


@app.get("/simulation/{run_id}", response_model=SimulationResponse)
def get_simulation(run_id: str):
    if run_id not in _RUN_STORE:
        raise HTTPException(404, f"No run with id {run_id} (run store is in-memory and per-process).")
    return SimulationResponse(**_RUN_STORE[run_id])


@app.get("/simulation/{run_id}/metrics")
def get_simulation_metrics(run_id: str):
    if run_id not in _RUN_STORE:
        raise HTTPException(404, f"No run with id {run_id}.")
    return _RUN_STORE[run_id]["summary"]


@app.get("/experiments")
def list_experiments():
    if not (RESULTS_DIR / "results.csv").exists():
        raise HTTPException(404, "No experiment results found. Run `python run_experiments.py` first.")
    df = pd.read_csv(RESULTS_DIR / "results.csv")
    return {
        "n_runs": len(df),
        "groups": df.experiment_group.value_counts().to_dict(),
        "scenarios": sorted(df.scenario.unique().tolist()),
        "available_reports": ["core_comparisons", "decision_table"],
    }


@app.get("/experiments/{name}")
def get_experiment_report(name: str):
    path = RESULTS_DIR / f"{name}.csv"
    if not path.exists():
        raise HTTPException(404, f"No report named '{name}'. Try 'core_comparisons' or 'decision_table'.")
    df = pd.read_csv(path)
    return df.to_dict(orient="records")
