#!/usr/bin/env python3
"""Generates every chart in reports/figures/ (PNG + HTML) from actual
experiment output -- nothing here is hand-drawn or hard-coded."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import charts, config, engine, world

RESULTS_DIR = Path(__file__).parent / "results"
FIG_DIR = Path(__file__).parent / "reports" / "figures"


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.write_html(FIG_DIR / f"{name}.html", include_plotlyjs="cdn")
    fig.write_image(FIG_DIR / f"{name}.png", width=1000, height=600, scale=2)
    print("saved", name)


def detailed_run(pricing, dispatch, seed=0, scenario="NORMAL"):
    w = world.generate_world(scenario, seed=seed)
    eng = engine.SimulationEngine(w, pricing, dispatch, config.SCENARIOS[scenario], collect_timeseries=True)
    result = eng.run()
    return result, eng


def main():
    df = pd.read_csv(RESULTS_DIR / "results.csv")
    comparisons = pd.read_csv(RESULTS_DIR / "core_comparisons.csv")
    core = df[df.experiment_group == "core"]

    save(charts.pricing_vs_price_index(core), "01_pricing_vs_price_index")
    save(charts.pricing_vs_conversion(core), "02_pricing_vs_conversion")
    save(charts.pricing_vs_revenue(core), "03_pricing_vs_revenue")
    save(charts.dispatch_vs_wait(core, "p90_wait_min", "P90 Rider Wait by Dispatch Policy", "P90 wait (minutes)"), "04_dispatch_vs_p90_wait")
    save(charts.dispatch_vs_wait(core, "avg_wait_min", "Average Rider Wait by Dispatch Policy", "Average wait (minutes)"), "05_dispatch_vs_avg_wait")
    save(charts.dispatch_vs_utilization(core), "06_dispatch_vs_utilization")
    save(charts.policy_frontier(core), "07_policy_frontier")
    save(charts.confidence_intervals(comparisons), "10_confidence_intervals")

    print("Running two detailed simulations for distribution/timeseries charts...")
    res_baseline, eng_baseline = detailed_run(config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER)
    res_best, eng_best = detailed_run(config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.ETA_OPTIMIZED)

    waits = {
        "NEAREST_DRIVER (baseline)": [r.wait_min for r in eng_baseline.collector.requests if r.wait_min is not None],
        "ETA_OPTIMIZED (best)": [r.wait_min for r in eng_best.collector.requests if r.wait_min is not None],
    }
    save(charts.wait_distribution(waits), "08_wait_distribution")

    ts = pd.DataFrame(eng_baseline._timeseries)
    save(charts.demand_and_supply_over_time(ts), "11_demand_supply_over_time")
    save(charts.surge_over_time(ts), "12_surge_over_time")

    zone_names = [z.name for z in config.ZONES]
    hours = sorted(ts.hour.round(0).unique())
    zone_ratio = pd.DataFrame(index=[z.id for z in config.ZONES], columns=hours, dtype=float)
    for _, row in ts.iterrows():
        h = round(row.hour)
        for z in config.ZONES:
            avail = row.available_by_zone.get(str(z.id), row.available_by_zone.get(z.id, 0))
            outstanding = row.outstanding_by_zone.get(str(z.id), row.outstanding_by_zone.get(z.id, 0))
            ratio = avail / (outstanding + 1)
            prev = zone_ratio.loc[z.id, h]
            zone_ratio.loc[z.id, h] = ratio if pd.isna(prev) else (prev + ratio) / 2
    zone_ratio = zone_ratio.ffill(axis=1).fillna(1.0)
    save(charts.zone_imbalance_heatmap(zone_ratio, zone_names), "09_zone_heatmap")

    print("All charts saved to", FIG_DIR)


if __name__ == "__main__":
    main()
