#!/usr/bin/env python3
"""
CLI entry point for running a single simulation.

Example:
    python run_simulation.py --scenario NORMAL --pricing BASIC_SURGE \
        --dispatch NEAREST_DRIVER --seed 0

    python run_simulation.py --scenario PEAK_DEMAND --pricing CAPPED_SMOOTHED_SURGE \
        --dispatch ADVANCED_HEURISTIC --seed 3 --hours 24 --json
"""
from __future__ import annotations

import argparse
import json
import sys

from src import config, engine, world


def main():
    parser = argparse.ArgumentParser(description="Run one ride-hailing marketplace simulation.")
    parser.add_argument("--scenario", choices=list(config.SCENARIOS.keys()), default="NORMAL")
    parser.add_argument("--pricing", choices=[p.value for p in config.PricingPolicy], default="BASIC_SURGE")
    parser.add_argument("--dispatch", choices=[d.value for d in config.DispatchPolicy], default="NEAREST_DRIVER")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hours", type=float, default=24.0, help="Simulated horizon length in hours.")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted report.")
    parser.add_argument("--timeseries", action="store_true", help="Also collect a 5-minute timeseries.")
    args = parser.parse_args()

    horizon_ticks = int(round(args.hours * 60))
    w = world.generate_world(args.scenario, seed=args.seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w,
        config.PricingPolicy(args.pricing),
        config.DispatchPolicy(args.dispatch),
        config.SCENARIOS[args.scenario],
        collect_timeseries=args.timeseries,
    )
    result = eng.run()

    if args.json:
        out = {
            "scenario": result.scenario,
            "seed": result.seed,
            "pricing_policy": result.pricing_policy,
            "dispatch_policy": result.dispatch_policy,
            "summary": result.summary,
        }
        print(json.dumps(out, indent=2))
        return

    print(f"Ride-Hailing Simulator -- scenario={result.scenario} seed={result.seed}")
    print(f"Pricing: {result.pricing_policy}   Dispatch: {result.dispatch_policy}")
    print("-" * 60)
    s = result.summary
    print(f"Requests:            {s['n_requests']:>8}")
    print(f"Completed:           {s['n_completed']:>8}  ({s['completion_rate']*100:.1f}%)")
    print(f"Abandoned/Cancelled: {s['n_abandoned']+s['n_cancelled_postmatch']:>8}  ({s['cancellation_rate']*100:.1f}%)")
    print(f"Rejected offers:     {s['n_rejected_offer']:>8}")
    print("-" * 60)
    print(f"Avg wait (min):      {s['avg_wait_min']:.2f}")
    print(f"Median wait (min):   {s['median_wait_min']:.2f}")
    print(f"P90 wait (min):      {s['p90_wait_min']:.2f}")
    print(f"Avg price:           {s['avg_price']:.2f}  (price index {s['price_index']:.3f})")
    print("-" * 60)
    print(f"Online drivers:      {s['n_online_drivers']}")
    print(f"Driver utilization:  {s['driver_utilization_mean']*100:.1f}%")
    print(f"Earnings/online-hr:  {s['earnings_per_online_hour_mean']:.2f}")
    print(f"Driver acceptance:   {s['driver_acceptance_rate']*100:.1f}%")
    print("-" * 60)
    print(f"GBV:                 {s['gbv']:.2f}")
    print(f"Platform revenue:    {s['platform_revenue']:.2f}")
    print(f"Revenue/ride:        {s['revenue_per_ride']:.2f}")
    print("-" * 60)
    print(f"NORTH STAR (trips/online-driver-hr): {s['north_star_trips_per_online_hour']:.4f}")


if __name__ == "__main__":
    sys.exit(main())
