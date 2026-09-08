"""
Streamlit dashboard for the Ride-Hailing Surge Pricing & Dispatch Simulator.

Run with:  streamlit run dashboard/app.py

Two modes:
  1. Live simulation -- pick a scenario/pricing/dispatch/seed and run the
     actual engine on demand (Overview / Marketplace / Pricing / Dispatch tabs).
  2. Experimentation -- browse the pre-computed 1,080-run experiment matrix
     and its statistical analysis (Experimentation tab).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import charts, config, engine, world  # noqa: E402

st.set_page_config(page_title="Ride-Hailing Marketplace Simulator", layout="wide")

RESULTS_DIR = ROOT / "results"


@st.cache_data
def load_results():
    df = pd.read_csv(RESULTS_DIR / "results.csv")
    comparisons = pd.read_csv(RESULTS_DIR / "core_comparisons.csv")
    decision = pd.read_csv(RESULTS_DIR / "decision_table.csv")
    return df, comparisons, decision


@st.cache_data
def run_live_simulation(scenario_name, pricing_name, dispatch_name, seed, hours, collect_ts):
    horizon_ticks = int(round(hours * 60))
    w = world.generate_world(scenario_name, seed=seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy(pricing_name), config.DispatchPolicy(dispatch_name),
        config.SCENARIOS[scenario_name], collect_timeseries=collect_ts,
    )
    result = eng.run()
    ts = pd.DataFrame(eng._timeseries) if collect_ts and hasattr(eng, "_timeseries") else pd.DataFrame()
    waits = [r.wait_min for r in eng.collector.requests if r.wait_min is not None]
    return result, ts, waits


st.title("🚕 Ride-Hailing Surge Pricing & Dispatch Simulator")
st.caption(
    "A synthetic marketplace simulation for studying pricing and dispatch trade-offs. "
    "All data is simulated -- see docs/ASSUMPTIONS.md. Not a real-world performance claim."
)

with st.sidebar:
    st.header("Simulation controls")
    scenario_name = st.selectbox("Demand/supply scenario", list(config.SCENARIOS.keys()), index=0)
    pricing_name = st.selectbox("Pricing policy", [p.value for p in config.PricingPolicy], index=1)
    dispatch_name = st.selectbox("Dispatch policy", [d.value for d in config.DispatchPolicy], index=0)
    seed = st.number_input("Random seed", min_value=0, max_value=9999, value=0, step=1)
    hours = st.slider("Simulated hours", min_value=2, max_value=24, value=24)
    run_clicked = st.button("▶ Run simulation", type="primary", use_container_width=True)

tabs = st.tabs(["Overview", "Marketplace", "Pricing", "Dispatch", "Experimentation"])

if run_clicked or "last_result" in st.session_state:
    if run_clicked:
        result, ts, waits = run_live_simulation(scenario_name, pricing_name, dispatch_name, int(seed), hours, True)
        st.session_state["last_result"] = (result, ts, waits)
    else:
        result, ts, waits = st.session_state["last_result"]
    s = result.summary

    with tabs[0]:
        st.subheader(f"Overview -- {result.scenario} / {result.pricing_policy} / {result.dispatch_policy} (seed {result.seed})")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Completed rides", s["n_completed"])
        c2.metric("Avg wait (min)", f"{s['avg_wait_min']:.2f}")
        c3.metric("P90 wait (min)", f"{s['p90_wait_min']:.2f}")
        c4.metric("Platform revenue", f"{s['platform_revenue']:.0f}")
        c5.metric("Earnings/online-hr", f"{s['earnings_per_online_hour_mean']:.1f}")
        c6.metric("North Star (trips/driver-hr)", f"{s['north_star_trips_per_online_hour']:.3f}")
        c7, c8, c9, c10 = st.columns(4)
        c7.metric("Completion rate", f"{s['completion_rate']*100:.1f}%")
        c8.metric("Cancellation rate", f"{s['cancellation_rate']*100:.1f}%")
        c9.metric("Driver utilization", f"{s['driver_utilization_mean']*100:.1f}%")
        c10.metric("Driver acceptance", f"{s['driver_acceptance_rate']*100:.1f}%")
        if not ts.empty:
            st.plotly_chart(charts.demand_and_supply_over_time(ts), use_container_width=True)
        if waits:
            st.plotly_chart(charts.wait_distribution({f"{result.dispatch_policy}": waits}), use_container_width=True)

    with tabs[1]:
        st.subheader("Marketplace state")
        if not ts.empty:
            st.plotly_chart(charts.demand_and_supply_over_time(ts), use_container_width=True, key="mkt_ts")
        st.metric("Unmatched requests (abandoned + cancelled)", s["unmatched_requests"])
        st.metric("Avg pickup distance (km)", f"{s['avg_pickup_distance_km']:.2f}")

    with tabs[2]:
        st.subheader("Pricing")
        if not ts.empty:
            st.plotly_chart(charts.surge_over_time(ts), use_container_width=True)
        st.metric("Price index (realized / no-surge)", f"{s['price_index']:.3f}")
        st.metric("Rider conversion rate", f"{s['rider_conversion_rate']*100:.1f}%")
        st.metric("Rejected offers (price/wait too high)", s["n_rejected_offer"])

    with tabs[3]:
        st.subheader("Dispatch")
        st.metric("Avg pickup distance (km)", f"{s['avg_pickup_distance_km']:.2f}")
        st.metric("Driver acceptance rate", f"{s['driver_acceptance_rate']*100:.1f}%")
        st.metric("Driver utilization", f"{s['driver_utilization_mean']*100:.1f}%")
else:
    for t in tabs[:4]:
        with t:
            st.info("Pick a scenario/pricing/dispatch policy in the sidebar and click **Run simulation**.")

with tabs[4]:
    st.subheader("Experimentation: 1,080-run experiment matrix")
    try:
        df, comparisons, decision = load_results()
        st.caption(f"{len(df)} total simulation runs -- {(df.experiment_group=='core').sum()} core (NORMAL scenario, 24 seeds) + "
                   f"{(df.experiment_group=='robustness').sum()} robustness runs across 5 stress scenarios.")
        core = df[df.experiment_group == "core"]

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(charts.dispatch_vs_wait(core, "p90_wait_min", "P90 Rider Wait by Dispatch Policy", "P90 wait (min)"), use_container_width=True)
            st.plotly_chart(charts.policy_frontier(core), use_container_width=True)
        with col2:
            st.plotly_chart(charts.confidence_intervals(comparisons), use_container_width=True)
            st.plotly_chart(charts.dispatch_vs_utilization(core), use_container_width=True)

        st.markdown("#### Decision table (ranked by North Star, subject to guardrails)")
        st.dataframe(decision, use_container_width=True)

        st.markdown("#### Full paired statistical comparisons vs. NEAREST_DRIVER baseline")
        st.dataframe(comparisons, use_container_width=True)
    except FileNotFoundError:
        st.warning("Run `python run_experiments.py` and `python analyze_results.py` first to populate this tab.")
