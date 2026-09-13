"""
Deterministic tool functions for the AI Marketplace Analyst (src/ai_copilot.py).

Hard rule (see docs/... AI guardrails section): the LLM NEVER computes a
metric itself. Every numeric answer the copilot gives must come from one of
these functions, which read either the pre-computed experiment results
(results/*.csv, produced by run_experiments.py + analyze_results.py) or run
a fresh, real simulation via src.engine. The LLM's only job is to decide
which tool to call and to explain the numbers it gets back.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd

from src import config, engine, ml_demand, ml_wait_time, world

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

_ZONE_BY_NAME = {z.name.lower(): z for z in config.ZONES}


def _resolve_zone(zone_name: str):
    zone = _ZONE_BY_NAME.get(zone_name.strip().lower())
    if zone is None:
        return None
    return zone


def _load(name: str) -> pd.DataFrame:
    path = RESULTS_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run run_experiments.py and analyze_results.py first.")
    return pd.read_csv(path)


def get_policy_metrics(pricing_policy: str, dispatch_policy: str, scenario: str = "NORMAL") -> dict:
    """Mean metrics (averaged across all seeds run) for one (scenario, pricing, dispatch)
    combination from the pre-computed experiment matrix."""
    df = _load("results")
    sub = df[
        (df.scenario == scenario) & (df.pricing_policy == pricing_policy) & (df.dispatch_policy == dispatch_policy)
    ]
    if sub.empty:
        return {"error": f"No runs found for scenario={scenario}, pricing={pricing_policy}, dispatch={dispatch_policy}."}
    numeric_cols = sub.select_dtypes("number").columns
    means = sub[numeric_cols].mean().to_dict()
    return {"n_seeds": len(sub), "source": "results/results.csv (pre-computed experiment matrix)", **means}


def compare_dispatch_to_baseline(pricing_policy: str, dispatch_policy: str, metric: str = "p90_wait_min") -> dict:
    """The pre-computed, statistically-tested paired comparison of one dispatch
    policy against the NEAREST_DRIVER baseline, under one pricing policy."""
    df = _load("core_comparisons")
    row = df[(df.pricing_policy == pricing_policy) & (df.dispatch_policy == dispatch_policy) & (df.metric == metric)]
    if row.empty:
        return {"error": f"No comparison found for pricing={pricing_policy}, dispatch={dispatch_policy}, metric={metric}."}
    return {"source": "results/core_comparisons.csv (paired Wilcoxon + bootstrap CI, n=24 seeds)", **row.iloc[0].to_dict()}


def get_decision_table(top_n: int = 5) -> dict:
    """The ranked policy-combination decision table (North Star, subject to guardrails)."""
    df = _load("decision_table")
    return {"source": "results/decision_table.csv", "rows": df.head(top_n).to_dict(orient="records")}


def get_zone_supply_demand_ranking(scenario: str = "NORMAL", pricing_policy: str = "BASIC_SURGE",
                                    dispatch_policy: str = "NEAREST_DRIVER", seed: int = 0) -> dict:
    """Runs one fresh, real simulation and returns each zone's average
    supply/demand ratio over the simulated day, ranked worst (most
    undersupplied) first. This is a live calculation, not a stored number --
    but it is still the deterministic engine doing the math, not the LLM."""
    w = world.generate_world(scenario, seed=seed)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy(pricing_policy), config.DispatchPolicy(dispatch_policy),
        config.SCENARIOS[scenario], collect_timeseries=True,
    )
    eng.run()
    ts = eng._timeseries
    totals = {z.id: [] for z in config.ZONES}
    for row in ts:
        for z in config.ZONES:
            avail = row["available_by_zone"].get(z.id, 0)
            outstanding = row["outstanding_by_zone"].get(z.id, 0)
            totals[z.id].append(avail / (outstanding + 1))
    ranking = sorted(
        ({"zone": z.name, "archetype": z.archetype, "avg_supply_demand_ratio": sum(v) / len(v)} for z, v in
         zip(config.ZONES, totals.values())),
        key=lambda r: r["avg_supply_demand_ratio"],
    )
    return {
        "source": f"live simulation ({scenario}, {pricing_policy}, {dispatch_policy}, seed={seed})",
        "note": "Lower ratio = more undersupplied (fewer available drivers per outstanding request).",
        "ranking": ranking,
    }


def simulate_whatif(pricing_policy: str = "BASIC_SURGE", dispatch_policy: str = "NEAREST_DRIVER",
                     scenario: str = "NORMAL", demand_multiplier_override: float | None = None,
                     supply_multiplier_override: float | None = None, seed: int = 0) -> dict:
    """Runs a fresh, real simulation, optionally overriding the scenario's
    demand/supply multiplier (e.g. 'what if demand increases by 20%?' ->
    demand_multiplier_override = base_scenario_demand_mult * 1.2). Returns the
    full metric summary from that real run -- not an estimate."""
    base_scenario = config.SCENARIOS[scenario]
    overrides = {}
    if demand_multiplier_override is not None:
        overrides["demand_mult"] = demand_multiplier_override
    if supply_multiplier_override is not None:
        overrides["supply_mult"] = supply_multiplier_override
    scenario_obj = dataclasses.replace(base_scenario, **overrides) if overrides else base_scenario

    # scenario_override must be threaded into world generation itself --
    # request volume and fleet size are both derived from scenario.demand_mult
    # / scenario.supply_mult inside generate_world, not just read by the engine.
    w = world.generate_world(scenario, seed=seed, scenario_override=scenario_obj if overrides else None)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy(pricing_policy), config.DispatchPolicy(dispatch_policy), scenario_obj,
    )
    result = eng.run()
    return {
        "source": f"live what-if simulation (scenario={scenario}, demand_mult={scenario_obj.demand_mult}, "
                   f"supply_mult={scenario_obj.supply_mult}, pricing={pricing_policy}, dispatch={dispatch_policy}, seed={seed})",
        **result.summary,
    }


def forecast_demand(zone_name: str, scenario: str = "NORMAL", hour: float = 8.0, seed: int = 0) -> dict:
    """Forecasts near-term (next 15-minute) ride demand for one zone at a
    given hour, using the trained GBM demand model (src/ml_demand.py) fed
    with real recent-demand and available-driver features taken from a live
    simulation run up to that hour. The model supplies the number; this
    tool never guesses one itself."""
    zone = _resolve_zone(zone_name)
    if zone is None:
        return {"error": f"Unknown zone '{zone_name}'. Options: {[z.name for z in config.ZONES]}"}
    return ml_demand.forecast_next_window(scenario, zone.id, hour, seed=seed)


def forecast_eta(zone_name: str, scenario: str = "NORMAL", hour: float = 8.0, segment: str = "normal", seed: int = 0) -> dict:
    """Forecasts the expected REALIZED wait (request to pickup) for a rider
    of the given segment requesting in one zone at a given hour -- a
    learned estimate that accounts for marketplace imbalance and surge, not
    just pickup distance (see src/ml_wait_time.py for why the naive
    distance/speed ETA isn't a useful ML target in this simulator, and what
    this predicts instead). Grounding features come from a live simulation
    run up to that hour, same as forecast_demand."""
    zone = _resolve_zone(zone_name)
    if zone is None:
        return {"error": f"Unknown zone '{zone_name}'. Options: {[z.name for z in config.ZONES]}"}
    return ml_wait_time.predict_wait_time(scenario, zone.id, hour, segment=segment, seed=seed)


TOOL_REGISTRY = {
    "get_policy_metrics": get_policy_metrics,
    "compare_dispatch_to_baseline": compare_dispatch_to_baseline,
    "get_decision_table": get_decision_table,
    "get_zone_supply_demand_ranking": get_zone_supply_demand_ranking,
    "simulate_whatif": simulate_whatif,
    "forecast_demand": forecast_demand,
    "forecast_eta": forecast_eta,
}
