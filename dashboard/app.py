"""
Streamlit dashboard for the Ride-Hailing Surge Pricing & Dispatch Simulator.

Run with:  streamlit run dashboard/app.py

Two data sources, same as before:
  1. Live simulation -- pick a scenario/pricing/dispatch/seed and run the
     actual engine on demand.
  2. Experimentation -- browse the pre-computed 1,080-run experiment matrix
     and its statistical analysis.

On top of that, this page adds a decision-intelligence layer (src/decision.py,
src/zone_state.py): a Marketplace Health Score, a guardrail-checked policy
recommendation sourced from the pre-computed matrix, a live counterfactual
simulation for the specific change recommended, and a spatial zone map --
all built from real simulation output, never a hardcoded number.
"""
from __future__ import annotations

import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import ai_copilot, charts, config, decision, engine, sim_context, world, zone_state  # noqa: E402
from src.env_utils import load_dotenv  # noqa: E402

load_dotenv()  # picks up ANTHROPIC_API_KEY / GROQ_API_KEY from a local .env for the AI Copilot tab

st.set_page_config(page_title="Ride-Hailing Marketplace Simulator", layout="wide", page_icon="🚕")

RESULTS_DIR = ROOT / "results"


@st.cache_data
def load_results():
    df = pd.read_csv(RESULTS_DIR / "results.csv")
    comparisons = pd.read_csv(RESULTS_DIR / "core_comparisons.csv")
    decision_table = pd.read_csv(RESULTS_DIR / "decision_table.csv")
    return df, comparisons, decision_table


@st.cache_data
def run_live_simulation(scenario_name, pricing_name, dispatch_name, seed, hours):
    """Runs one real simulation and returns everything downstream views
    need: the summary, the timeseries, individual waits, and the per-zone
    spatial state -- all derived from this one run, so every chart/number
    that names this (scenario, pricing, dispatch, seed) combination is
    guaranteed to agree with every other."""
    horizon_ticks = int(round(hours * 60))
    w = world.generate_world(scenario_name, seed=seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy(pricing_name), config.DispatchPolicy(dispatch_name),
        config.SCENARIOS[scenario_name], collect_timeseries=True, timeseries_every_ticks=5,
    )
    result = eng.run()
    ts = pd.DataFrame(eng._timeseries) if hasattr(eng, "_timeseries") else pd.DataFrame()
    waits = [r.wait_min for r in eng.collector.requests if r.wait_min is not None]
    summary = dict(result.summary)
    summary["avg_surge_multiplier"] = decision.avg_surge_multiplier(eng.collector)
    zone_states = zone_state.compute_zone_states(eng.collector, eng._timeseries, horizon_ticks)
    zone_df = zone_state.zone_states_to_dataframe(zone_states)
    return summary, ts, waits, zone_df


@st.cache_data
def cached_recommend_policy(results_df, scenario_name, pricing_name, dispatch_name):
    return decision.recommend_policy(results_df, scenario_name, pricing_name, dispatch_name)


@st.cache_data
def cached_counterfactual(scenario_name, cur_pricing, cur_dispatch, alt_pricing, alt_dispatch):
    return decision.run_counterfactual(scenario_name, cur_pricing, cur_dispatch, alt_pricing, alt_dispatch)


def fmt_delta(value, suffix="", pct=False):
    if value != value:
        return None
    v = value * 100 if pct else value
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}{suffix}"


st.title("🚕 Ride-Hailing Marketplace Simulator")
st.caption(
    "A synthetic marketplace simulation and AI-assisted decision-intelligence layer for studying pricing and "
    "dispatch trade-offs. All data is simulated -- see docs/ASSUMPTIONS.md. Not a real-world performance claim."
)

with st.sidebar:
    st.header("Simulation controls")
    scenario_name = st.selectbox("Demand/supply scenario", list(config.SCENARIOS.keys()), index=0)
    pricing_name = st.selectbox("Pricing policy", [p.value for p in config.PricingPolicy], index=1)
    dispatch_name = st.selectbox("Dispatch policy", [d.value for d in config.DispatchPolicy], index=0)
    seed = st.number_input("Random seed", min_value=0, max_value=9999, value=0, step=1)
    hours = st.slider("Simulated hours", min_value=2, max_value=24, value=24)
    run_clicked = st.button("▶ Run simulation", type="primary", width='stretch')

    st.divider()
    st.subheader("Baseline")
    st.caption("Every comparison on this page is explicit about **current** vs. this **baseline**.")
    baseline_pricing = st.selectbox(
        "Baseline pricing", [p.value for p in config.PricingPolicy],
        index=[p.value for p in config.PricingPolicy].index(config.BASELINE_PRICING.value),
    )
    baseline_dispatch = st.selectbox(
        "Baseline dispatch", [d.value for d in config.DispatchPolicy],
        index=[d.value for d in config.DispatchPolicy].index(config.BASELINE_DISPATCH.value),
    )

tabs = st.tabs(["Overview", "Marketplace Map", "Pricing", "Dispatch", "Experimentation", "AI Copilot"])

if run_clicked or "last_result" in st.session_state:
    if run_clicked:
        summary, ts, waits, zone_df = run_live_simulation(scenario_name, pricing_name, dispatch_name, int(seed), hours)
        st.session_state["last_result"] = (summary, ts, waits, zone_df, scenario_name, pricing_name, dispatch_name, int(seed), hours)
    else:
        summary, ts, waits, zone_df, scenario_name, pricing_name, dispatch_name, seed, hours = st.session_state["last_result"]

    ctx = sim_context.SimulationContext(scenario_name, pricing_name, dispatch_name, seed, hours)
    s = summary

    baseline_summary, _, _, _ = run_live_simulation(scenario_name, baseline_pricing, baseline_dispatch, int(seed), hours)
    baseline_ctx = sim_context.SimulationContext(scenario_name, baseline_pricing, baseline_dispatch, seed, hours)
    is_baseline_run = (pricing_name == baseline_pricing and dispatch_name == baseline_dispatch)

    health = decision.compute_health_score(s)
    baseline_health = decision.compute_health_score(baseline_summary)

    # =====================================================================
    # OVERVIEW
    # =====================================================================
    with tabs[0]:
        st.caption(f"Current run: **{ctx.label()}**  |  Baseline: **{baseline_ctx.short_label()}**"
                   + ("  _(current run = baseline)_" if is_baseline_run else ""))

        # --- Marketplace Health ------------------------------------------------
        h1, h2 = st.columns([1, 3])
        with h1:
            st.metric(
                "MARKETPLACE HEALTH", f"{health.overall:.0f} / 100",
                delta=fmt_delta(health.overall - baseline_health.overall) if not is_baseline_run else None,
                delta_color="normal",
            )
            st.caption(health.interpretation())
        with h2:
            dim_cols = st.columns(4)
            for col, (dim, label) in zip(dim_cols, decision.DIMENSION_LABELS.items()):
                with col:
                    st.metric(label, f"{health.dimensions[dim]:.0f}")

        st.divider()

        # --- Recommendation card -------------------------------------------------
        results_df, comparisons_df, decision_table_df = load_results()
        rec = cached_recommend_policy(results_df, scenario_name, pricing_name, dispatch_name)

        def _failing_guardrails_note(row):
            failed = []
            for metric, (kind, bound, label) in decision.GUARDRAIL_ABSOLUTE.items():
                v = row.get(metric)
                if v is None or v != v:
                    continue
                if (kind == "max" and v > bound) or (kind == "min" and v < bound):
                    failed.append(f"{label} ({v:.2f} vs. limit {bound:.2f})")
            return failed

        st.subheader("🤖 Recommended intervention")
        if rec["action"] == "error":
            st.info(rec["reason"])
        elif rec["action"] == "none":
            st.success(f"No action recommended -- **{pricing_name} + {dispatch_name}** is within target range for "
                       f"{scenario_name}. {rec['reason']}")
            bo = rec.get("best_overall")
            if bo is not None and not bo.get("guardrail_pass", True):
                failed = _failing_guardrails_note(bo)
                st.caption(
                    f"⚠️ `{bo['pricing_policy']} + {bo['dispatch_policy']}` has the highest unconstrained utility, "
                    f"but is rejected because: {'; '.join(failed) if failed else 'a guardrail check failed'}."
                )
        else:
            cur, best = rec["current"], rec["recommended"]
            st.markdown(
                f"**Switch dispatch/pricing:** `{pricing_name} + {dispatch_name}` &rarr; "
                f"`{best['pricing_policy']} + {best['dispatch_policy']}`  \n"
                f"_Source: pre-computed experiment matrix, {scenario_name} scenario "
                f"({'24' if scenario_name == 'NORMAL' else '6'} seeds per combo)._"
            )
            if not rec.get("best_overall_is_recommended", True) and rec.get("best_overall") is not None:
                bo = rec["best_overall"]
                failed = _failing_guardrails_note(bo)
                st.caption(
                    f"ℹ️ `{bo['pricing_policy']} + {bo['dispatch_policy']}` scores higher on raw utility, "
                    f"but is rejected because: {'; '.join(failed) if failed else 'a guardrail check failed'}. "
                    f"Showing the best guardrail-passing policy instead."
                )
            mcols = st.columns(5)
            impact = [
                ("P90 wait", cur["p90_wait_min"], best["p90_wait_min"], "min", False),
                ("Completion", cur["completion_rate"], best["completion_rate"], "%", True),
                ("Cancellation", cur["cancellation_rate"], best["cancellation_rate"], "%", False),
                ("Revenue", cur["platform_revenue"], best["platform_revenue"], "", True),
                ("Driver utilization", cur["driver_utilization_mean"], best["driver_utilization_mean"], "%", True),
            ]
            for col, (label, before, after, unit, higher_better) in zip(mcols, impact):
                if unit == "%":
                    before, after = before * 100, after * 100
                delta = after - before
                col.metric(label, f"{after:,.1f}{unit}", delta=f"{delta:+,.1f}{unit}",
                           delta_color="normal" if higher_better else "inverse")

            gcol1, gcol2 = st.columns([1, 1])
            with gcol1:
                if st.button("🔬 Run Counterfactual (live, CI-backed)", width='stretch'):
                    st.session_state["cf_request"] = (scenario_name, pricing_name, dispatch_name, best["pricing_policy"], best["dispatch_policy"])
            with gcol2:
                st.caption("The card above uses pre-computed matrix means (instant). Counterfactual runs a fresh "
                           "paired simulation with a real bootstrap confidence interval.")

        if "cf_request" in st.session_state:
            cf_scn, cf_cp, cf_cd, cf_ap, cf_ad = st.session_state["cf_request"]
            n_cf_seeds = len(decision.COUNTERFACTUAL_SEEDS)
            with st.spinner(f"Running live counterfactual: {cf_cp}+{cf_cd} vs {cf_ap}+{cf_ad} ({n_cf_seeds} paired seeds)..."):
                cf = cached_counterfactual(cf_scn, cf_cp, cf_cd, cf_ap, cf_ad)
            st.markdown(f"#### Counterfactual: `{cf_cp}+{cf_cd}` (current) vs. `{cf_ap}+{cf_ad}` (alternative) -- {cf['n_seeds']} paired seeds")
            comp = cf["comparison"].copy()
            comp_display = comp[["metric", "baseline_mean", "treatment_mean", "signed_relative_effect_pct",
                                  "bootstrap_ci_95_lo", "bootstrap_ci_95_hi", "wilcoxon_p", "practically_significant_improvement"]]
            comp_display.columns = ["Metric", "Current", "Alternative", "Improvement %", "CI lo (Δ)", "CI hi (Δ)", "p-value", "Practically significant"]
            st.dataframe(comp_display.round(4), width='stretch', hide_index=True)

            g = cf["guardrails"]
            gcols = st.columns(4)
            for col, key, label in zip(gcols, ["p90_wait", "cancellation", "earnings", "revenue"],
                                        ["P90 wait guardrail", "Cancellation guardrail", "Earnings guardrail", "Revenue guardrail"]):
                col.metric(label, "🟢 PASS" if g[key] else "🔴 FAIL")
            if st.button("Clear counterfactual"):
                del st.session_state["cf_request"]
                st.rerun()

        st.divider()

        # --- Map + KPIs ------------------------------------------------------
        m1, m2 = st.columns([2, 1])
        with m1:
            metric_label = st.selectbox("Map metric", list(charts.MAP_METRIC_OPTIONS.keys()), key="overview_map_metric")
            st.plotly_chart(charts.marketplace_map(zone_df, metric_label, ctx), width='stretch')
        with m2:
            st.markdown("**Marketplace KPIs**")
            st.metric("P90 wait (min)", f"{s['p90_wait_min']:.2f}")
            st.metric("Completion rate", f"{s['completion_rate']*100:.1f}%")
            st.metric("Cancellation rate", f"{s['cancellation_rate']*100:.1f}%")
            st.metric("Platform revenue", f"{s['platform_revenue']:,.0f}")
            st.metric("North Star (trips/driver-hr)", f"{s['north_star_trips_per_online_hour']:.3f}")

        worst_rows = zone_df.sort_values("supply_demand_ratio").head(3)
        if not worst_rows.empty and worst_rows.iloc[0]["status"] in ("high_pressure", "severe_shortage"):
            st.warning(
                "⚠️ **Active issue:** " + ", ".join(worst_rows["name"].tolist()) +
                f" -- worst is **{worst_rows.iloc[0]['name']}** "
                f"(supply/demand ratio {worst_rows.iloc[0]['supply_demand_ratio']:.2f}, "
                f"P90 wait {worst_rows.iloc[0]['p90_wait_min']:.1f} min, "
                f"cancellation {worst_rows.iloc[0]['cancellation_rate']*100:.0f}%)."
            )

        st.divider()
        st.markdown("#### Demand vs. supply over the simulated day")
        if not ts.empty:
            st.plotly_chart(charts.demand_and_supply_over_time(ts, ctx), width='stretch')

        st.markdown("#### Policy tradeoff (P90 wait vs. revenue)")
        recommended_pair = (rec["recommended"]["pricing_policy"], rec["recommended"]["dispatch_policy"]) if rec.get("action") == "switch" else None
        scenario_df = results_df[results_df.scenario == scenario_name]
        st.plotly_chart(
            charts.policy_tradeoff_scatter(scenario_df, current=(pricing_name, dispatch_name), recommended=recommended_pair),
            width='stretch',
        )

        with st.expander("Advanced: guardrail detail, zone table, wait distribution"):
            checks = decision.evaluate_guardrails_absolute(s)
            st.plotly_chart(charts.guardrail_bars(checks), width='stretch')
            st.markdown("**Per-zone state**")
            st.dataframe(
                zone_df[["name", "archetype", "status", "demand_per_min", "avg_available_drivers",
                         "supply_demand_ratio", "p90_wait_min", "cancellation_rate", "avg_surge_multiplier"]]
                .sort_values("supply_demand_ratio").round(2),
                width='stretch', hide_index=True,
            )
            if waits:
                st.plotly_chart(charts.wait_distribution({ctx.short_label(): waits}, ctx), width='stretch')

    # =====================================================================
    # MARKETPLACE MAP (dedicated tab: zone click-through detail)
    # =====================================================================
    with tabs[1]:
        st.subheader(f"Marketplace Map -- {ctx.label()}")
        mm_metric = st.selectbox("Metric", list(charts.MAP_METRIC_OPTIONS.keys()), key="map_tab_metric")
        st.plotly_chart(charts.marketplace_map(zone_df, mm_metric, ctx), width='stretch', key="map_tab_chart")

        st.markdown("#### Zone detail")
        zone_pick = st.selectbox("Select a zone", zone_df["name"].tolist())
        zrow = zone_df[zone_df["name"] == zone_pick].iloc[0]
        zc1, zc2, zc3, zc4 = st.columns(4)
        zc1.metric("Demand (req/min)", f"{zrow['demand_per_min']:.2f}")
        zc2.metric("Available drivers", f"{zrow['avg_available_drivers']:.1f}")
        zc3.metric("Supply/demand ratio", f"{zrow['supply_demand_ratio']:.2f}")
        zc4.metric("Health status", zrow["status"].replace("_", " ").title())
        zc5, zc6, zc7 = st.columns(3)
        zc5.metric("P90 wait (min)", f"{zrow['p90_wait_min']:.1f}" if zrow['p90_wait_min'] == zrow['p90_wait_min'] else "n/a")
        zc6.metric("Cancellation rate", f"{zrow['cancellation_rate']*100:.0f}%")
        zc7.metric("Surge multiplier", f"{zrow['avg_surge_multiplier']:.2f}x")

        city_avg_demand = zone_df["demand_per_min"].mean()
        city_avg_avail = zone_df["avg_available_drivers"].mean()
        zstate_obj = zone_state.ZoneState(**{f.name: zrow[f.name] for f in dataclass_fields(zone_state.ZoneState)})
        st.markdown("**Why is this happening?**")
        for reason in zone_state.explain_zone(zstate_obj, city_avg_demand, city_avg_avail):
            st.markdown(f"- {reason}")

    # =====================================================================
    # PRICING
    # =====================================================================
    with tabs[2]:
        st.subheader(f"Pricing -- {ctx.label()}")
        if not ts.empty:
            st.plotly_chart(charts.surge_over_time(ts, ctx), width='stretch')
        st.metric("Price index (realized / no-surge)", f"{s['price_index']:.3f}")
        st.metric("Rider conversion rate", f"{s['rider_conversion_rate']*100:.1f}%")
        st.metric("Rejected offers (price/wait too high)", s["n_rejected_offer"])
        st.metric("Avg surge multiplier", f"{s['avg_surge_multiplier']:.2f}x")

    # =====================================================================
    # DISPATCH
    # =====================================================================
    with tabs[3]:
        st.subheader(f"Dispatch -- {ctx.label()}")
        st.metric("Avg pickup distance (km)", f"{s['avg_pickup_distance_km']:.2f}")
        st.metric("Driver acceptance rate", f"{s['driver_acceptance_rate']*100:.1f}%")
        st.metric("Driver utilization", f"{s['driver_utilization_mean']*100:.1f}%")
else:
    for t in tabs[:4]:
        with t:
            st.info("Pick a scenario/pricing/dispatch policy in the sidebar and click **Run simulation**.")

# =========================================================================
# EXPERIMENTATION
# =========================================================================
with tabs[4]:
    st.subheader("Experimentation: 1,080-run experiment matrix")
    try:
        df, comparisons, decision_table = load_results()
        st.caption(f"{len(df)} total simulation runs -- {(df.experiment_group=='core').sum()} core (NORMAL scenario, 24 seeds) + "
                   f"{(df.experiment_group=='robustness').sum()} robustness runs across 5 stress scenarios.")

        # --- Best policy card (progressive disclosure: this first) -----------
        top = decision_table[decision_table.meets_all_guardrails].sort_values("north_star", ascending=False)
        if top.empty:
            top_row = decision_table.sort_values("north_star", ascending=False).iloc[0]
            guardrail_note = "⚠️ No combination clears every guardrail vs. baseline; showing the North-Star leader anyway."
        else:
            top_row = top.iloc[0]
            guardrail_note = "✅ Clears every guardrail vs. the NORMAL/BASIC_SURGE/NEAREST_DRIVER baseline."

        st.markdown("### 🏆 Recommended Policy (NORMAL scenario, 1,080-run matrix)")
        st.markdown(f"#### `{top_row.pricing_policy} + {top_row.dispatch_policy}`")
        bc1, bc2, bc3 = st.columns(3)
        bc1.metric("P90 wait", f"{top_row.p90_wait_min:.2f} min")
        bc2.metric("Revenue", f"₹{top_row.platform_revenue:,.0f}")
        bc3.metric("Driver earnings/hr", f"₹{top_row.earnings_per_online_hour_mean:.0f}")
        st.caption(guardrail_note)

        with st.expander("Why was this selected?", expanded=True):
            b_p90 = top_row.baseline_p90_wait_min
            wait_delta_pct = (top_row.p90_wait_min - b_p90) / b_p90 * 100 if b_p90 else 0
            b_rev = top_row.baseline_platform_revenue
            rev_delta_pct = (top_row.platform_revenue - b_rev) / b_rev * 100 if b_rev else 0
            st.markdown(
                f"- P90 wait changed **{wait_delta_pct:+.1f}%** vs. baseline ({b_p90:.2f} min)\n"
                f"- Revenue changed **{rev_delta_pct:+.1f}%** vs. baseline (₹{b_rev:,.0f})\n"
                f"- Guardrails: P90 {'🟢' if top_row.meets_p90_guardrail else '🔴'} | "
                f"Earnings {'🟢' if top_row.meets_earnings_guardrail else '🔴'} | "
                f"Cancellation {'🟢' if top_row.meets_cancellation_guardrail else '🔴'} | "
                f"Revenue {'🟢' if top_row.meets_revenue_guardrail else '🔴'}\n"
                f"- Ranked by **North Star** (trips / online-driver-hour): {top_row.north_star:.3f}"
            )
            match = comparisons[
                (comparisons.pricing_policy == top_row.pricing_policy)
                & (comparisons.dispatch_policy == top_row.dispatch_policy)
                & (comparisons.role == "primary")
            ]
            if not match.empty:
                m = match.iloc[0]
                sig = "statistically significant" if m.practically_significant_improvement else "not statistically significant at the pre-registered bar"
                st.markdown(
                    f"- P90 wait improvement: **{m.signed_relative_effect_pct:+.1f}%**, "
                    f"95% CI [{-m.bootstrap_ci_95_hi:.2f}, {-m.bootstrap_ci_95_lo:.2f}] min, "
                    f"Wilcoxon p={m.wilcoxon_p:.2e}, n=24 paired seeds -- **{sig}**."
                )

        st.divider()

        core = df[df.experiment_group == "core"]
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(charts.dispatch_vs_wait(core, "p90_wait_min", "P90 Rider Wait by Dispatch Policy", "P90 wait (min)"), width='stretch')
            st.plotly_chart(charts.policy_frontier(core), width='stretch')
        with col2:
            st.plotly_chart(charts.confidence_intervals(comparisons), width='stretch')
            st.plotly_chart(charts.dispatch_vs_utilization(core), width='stretch')

        with st.expander("Advanced Analysis: full policy matrix, bootstrap comparisons, decision table"):
            st.markdown("#### Decision table (ranked by North Star, subject to guardrails)")
            st.dataframe(decision_table, width='stretch')
            st.markdown("#### Full paired statistical comparisons vs. NEAREST_DRIVER baseline")
            st.dataframe(comparisons, width='stretch')
    except FileNotFoundError:
        st.warning("Run `python run_experiments.py` and `python analyze_results.py` first to populate this tab.")

# =========================================================================
# AI COPILOT
# =========================================================================
with tabs[5]:
    st.subheader("🤖 AI Marketplace Analyst")
    st.caption(
        "Tool-calling copilot over the simulator and experiment results -- it never computes a metric itself. "
        "Every number in its answer comes from a real tool call (a pre-computed result lookup, a live "
        "simulation, or a trained ML forecast); expand \"Tool calls\" under any answer to see exactly which "
        "ones ran and what they returned. This is a Q&A analyst, not a policy-change button -- to actually "
        "change the current policy, use the recommendation card and Approve/Counterfactual flow on Overview."
    )

    try:
        copilot_provider = ai_copilot.resolve_provider()
    except RuntimeError:
        copilot_provider = None

    if copilot_provider is None:
        st.info(
            "No LLM API key found. Set `ANTHROPIC_API_KEY` or `GROQ_API_KEY` in a local `.env` file "
            "(gitignored, auto-loaded) to enable the AI Copilot -- see README.md."
        )
    else:
        st.caption(f"Provider: `{copilot_provider}`")
        if "copilot_history" not in st.session_state:
            st.session_state["copilot_history"] = []

        example_questions = [
            "Which dispatch policy performs best, and is it statistically real?",
            "Why might cancellations be high during PEAK_DEMAND?",
            "What should we change during peak demand?",
            "What happens if we remove surge pricing?",
            "How much demand is expected in Downtown around hour 9 during PEAK_DEMAND?",
        ]
        st.caption("Try:")
        ecols = st.columns(len(example_questions))
        example_clicked = None
        for col, q in zip(ecols, example_questions):
            if col.button(q, key=f"ex_{q}", width='stretch'):
                example_clicked = q

        for turn in st.session_state["copilot_history"]:
            with st.chat_message("user"):
                st.markdown(turn["question"])
            with st.chat_message("assistant"):
                st.markdown(turn["answer"])
                if turn["tool_calls"]:
                    with st.expander(f"🔧 Tool calls ({len(turn['tool_calls'])})"):
                        for tc in turn["tool_calls"]:
                            st.markdown(f"**`{tc['name']}`**`({tc['input']})`")
                            st.json(tc["result"], expanded=False)

        typed_question = st.chat_input("Ask about pricing, dispatch, experiment results, or a what-if scenario...")
        question = example_clicked or typed_question

        if question:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Investigating (calling tools)..."):
                    try:
                        result = ai_copilot.ask_with_trace(question)
                    except Exception as e:
                        result = {"answer": f"Error calling the LLM provider: {e}", "tool_calls": []}
                st.markdown(result["answer"])
                if result["tool_calls"]:
                    with st.expander(f"🔧 Tool calls ({len(result['tool_calls'])})"):
                        for tc in result["tool_calls"]:
                            st.markdown(f"**`{tc['name']}`**`({tc['input']})`")
                            st.json(tc["result"], expanded=False)
            st.session_state["copilot_history"].append(
                {"question": question, "answer": result["answer"], "tool_calls": result["tool_calls"]}
            )

        if st.session_state["copilot_history"] and st.button("Clear conversation"):
            st.session_state["copilot_history"] = []
            st.rerun()
