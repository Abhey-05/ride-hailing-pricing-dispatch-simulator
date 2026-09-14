"""
Streamlit dashboard for the Ride-Hailing Surge Pricing & Dispatch Simulator.

Run with:  streamlit run dashboard/app.py

Two data sources:
  1. Live simulation -- pick a scenario/pricing/dispatch/seed and run the
     actual engine on demand.
  2. Experimentation -- browse the pre-computed 1,080-run experiment matrix
     and its statistical analysis.

On top of that, this page adds a decision-intelligence layer
(src/decision.py, src/zone_state.py): a Marketplace Health Score, a
guardrail-checked policy recommendation, a live counterfactual simulation,
and a spatial zone map -- all built from real simulation output.

Terminology (kept consistent everywhere, see docs/PRD.md and the note in
`_render_context_header` below):
  - CURRENT: the (scenario, pricing, dispatch, seed) selected in the sidebar.
  - EXPERIMENT BASELINE: the fixed reference policy (config.BASELINE_PRICING
    + config.BASELINE_DISPATCH) the 1,080-run matrix and its statistical
    tests are anchored to. Not user-adjustable, evaluated under the SAME
    scenario as Current for an apples-to-apples comparison.
  - In a counterfactual, "current" and "alternative" refer to the two
    specific policies being compared in that one run -- never called
    "baseline" to avoid a third meaning of the word.

Progressive disclosure: the Overview page leads with health -> active issue
-> recommendation -> map -> tradeoff, with every statistical/tabular detail
moved into "Advanced" expanders. Nothing here is deleted from earlier
versions -- it is re-ordered and re-labeled for a 10-15 second read.
"""
from __future__ import annotations

import sys
from dataclasses import fields as dataclass_fields
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import ai_copilot, charts, config, decision, engine, labels, sim_context, world, zone_state  # noqa: E402
from src.env_utils import load_dotenv  # noqa: E402

load_dotenv()  # picks up ANTHROPIC_API_KEY / GROQ_API_KEY from a local .env for the AI Copilot tab

st.set_page_config(page_title="Ride-Hailing Marketplace Simulator", layout="wide", page_icon="🚕")

# Restrained policy-name pills instead of Streamlit's default bright-green
# inline code styling -- every `POLICY_NAME` badge in the app is a neutral
# label (not a "good"/"bad" signal), so it gets the same muted blue used
# elsewhere for neutral/informational (src.labels.SEMANTIC_COLORS["blue"]),
# at low saturation. This is the one, global place that styling is set.
st.markdown(
    f"""<style>
    code {{
        background-color: {labels.SEMANTIC_COLORS['blue']}22 !important;
        color: {labels.SEMANTIC_COLORS['blue']} !important;
        border-radius: 4px;
        font-weight: 500;
    }}
    </style>""",
    unsafe_allow_html=True,
)

RESULTS_DIR = ROOT / "results"
EXPERIMENT_BASELINE_LABEL = f"{config.BASELINE_PRICING.value} + {config.BASELINE_DISPATCH.value}"


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
def cached_recommend_policy(results_df, scenario_name, pricing_name, dispatch_name, objective):
    return decision.recommend_policy(results_df, scenario_name, pricing_name, dispatch_name, objective=objective)


@st.cache_data
def cached_sensitivity_table(results_df, scenario_name, pricing_name, dispatch_name):
    return decision.objective_sensitivity_table(results_df, scenario_name, pricing_name, dispatch_name)


@st.cache_data
def cached_recommendation_frequency(results_df, objective):
    return decision.recommendation_frequency(results_df, objective=objective)


@st.cache_data
def cached_counterfactual(scenario_name, cur_pricing, cur_dispatch, alt_pricing, alt_dispatch):
    return decision.run_counterfactual(scenario_name, cur_pricing, cur_dispatch, alt_pricing, alt_dispatch)


def fmt_delta(value, suffix="", pct=False):
    if value != value:
        return None
    v = value * 100 if pct else value
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}{suffix}"


def guardrail_row(checks: list) -> None:
    """Compact ✅/🔴 + label row for a list of decision.GuardrailCheck."""
    if not checks:
        st.caption("No guardrail data available for this source.")
        return
    cols = st.columns(len(checks))
    for col, c in zip(cols, checks):
        col.metric(c.label, "🟢 Pass" if c.passed else "🔴 Fail", help=f"{c.value:.2f} vs. limit {c.bound:.2f}")


_METRIC_FORMATTERS = {
    "p90_wait_min": labels.fmt_minutes, "avg_wait_min": labels.fmt_minutes,
    "completion_rate": labels.fmt_pct, "cancellation_rate": labels.fmt_pct,
    "rider_conversion_rate": labels.fmt_pct, "driver_acceptance_rate": labels.fmt_pct,
    "driver_utilization_mean": labels.fmt_pct, "price_index": lambda v: f"{v:.3f}",
    "platform_revenue": labels.fmt_currency, "earnings_per_online_hour_mean": labels.fmt_currency,
    "avg_pickup_distance_km": labels.fmt_km, "avg_surge_multiplier": labels.fmt_multiplier,
    "north_star_trips_per_online_hour": lambda v: f"{v:.3f}",
}


def fmt_metric(metric_key: str, value: float) -> str:
    fn = _METRIC_FORMATTERS.get(metric_key)
    return fn(value) if fn else f"{value:,.2f}"


# Rate metrics (already a 0-1 fraction) report their CHANGE in percentage
# points ("4.0 pp"), not "%", so a reader never confuses an absolute move
# with a relative one. Non-rate metrics (time, currency, distance, ratio)
# just reuse their normal formatter on the raw delta.
_RATE_METRICS = {"completion_rate", "cancellation_rate", "rider_conversion_rate",
                  "driver_acceptance_rate", "driver_utilization_mean"}


def fmt_metric_delta(metric_key: str, delta: float) -> str:
    if metric_key in _RATE_METRICS:
        return labels.fmt_pp(abs(delta))
    return fmt_metric(metric_key, abs(delta))


def impact_table_markdown(metric_keys: list[str], before_dict: dict, after_dict: dict) -> str:
    """Renders a compact 'Current -> Recommended (change)' markdown table
    using human-readable labels, formatting, and centralized good/bad color
    logic (src.labels.is_improvement) -- never hand-colored per metric."""
    lines = ["| Metric | Current | Recommended | Change |", "|---|---|---|---|"]
    for metric_key in metric_keys:
        before, after = before_dict[metric_key], after_dict[metric_key]
        delta = after - before
        improved = labels.is_improvement(metric_key, delta)
        dot = "🟢" if improved else ("🔴" if improved is False else "⚪")
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        change_str = f"{dot} {arrow} {fmt_metric_delta(metric_key, delta)}"
        lines.append(f"| {labels.label(metric_key)} | {fmt_metric(metric_key, before)} | {fmt_metric(metric_key, after)} | {change_str} |")
    return "\n".join(lines)


def failing_guardrails_note(row: dict) -> list[str]:
    failed = []
    for metric, (kind, bound, label_) in decision.GUARDRAIL_ABSOLUTE.items():
        v = row.get(metric)
        if v is None or v != v:
            continue
        if (kind == "max" and v > bound) or (kind == "min" and v < bound):
            failed.append(f"{label_} ({v:.2f} vs. limit {bound:.2f})")
    return failed


OBJECTIVE_HEADLINE_PREFIX = {
    "BALANCED": "Recommended intervention for",
    "RIDER_FIRST": "Improve rider experience during",
    "REVENUE_FIRST": "Improve marketplace revenue during",
    "DRIVER_FIRST": "Improve driver economics during",
}


def recommendation_headline(objective: str, scenario_name: str) -> str:
    """The headline names what the SELECTED objective is actually
    optimizing for, rather than guessing from whichever metric happened to
    move the most -- so "Rider-first" always reads as a rider-experience
    headline even in a scenario where, say, revenue moved more in relative
    terms."""
    prefix = OBJECTIVE_HEADLINE_PREFIX.get(objective, "Recommended intervention for")
    return f"{prefix} {scenario_name.replace('_', ' ').title()}"


def why_this_policy_bullets(cur: dict, best: dict, metric_keys: list[str]) -> list[str]:
    """Plain-language reasons the recommendation was made -- one bullet per
    metric that genuinely improves (via labels.is_improvement, the same
    centralized good/bad logic the impact table uses), so this never drifts
    out of sync with what the table actually shows."""
    bullets = []
    for metric_key in metric_keys:
        delta = best[metric_key] - cur[metric_key]
        if labels.is_improvement(metric_key, delta) is not True:
            continue
        base = cur[metric_key]
        pct = abs(delta / base * 100) if base else 0.0
        bullets.append(f"{labels.label(metric_key)} improves {pct:.1f}% ({fmt_metric(metric_key, cur[metric_key])} → {fmt_metric(metric_key, best[metric_key])})")
    if not bullets:
        bullets.append("Improves the overall objective score without a single dominant metric change -- see the table below for the full breakdown.")
    return bullets


st.title("🚕 Ride-Hailing Marketplace Simulator")
st.caption("AI-assisted decision intelligence for a synthetic ride-hailing marketplace -- pricing, dispatch, and marketplace health at a glance.")
st.caption("Simulation environment -- all marketplace data is synthetic and intended for comparative analysis, not real-world performance claims.")

with st.sidebar:
    st.markdown("##### Simulation controls")
    scenario_name = st.selectbox("Demand/supply scenario", list(config.SCENARIOS.keys()), index=0)
    pricing_name = st.selectbox("Pricing policy", [p.value for p in config.PricingPolicy], index=1)
    dispatch_name = st.selectbox("Dispatch policy", [d.value for d in config.DispatchPolicy], index=0)
    seed = st.number_input("Random seed", min_value=0, max_value=9999, value=0, step=1)
    hours = st.slider("Simulated hours", min_value=2, max_value=24, value=24)
    run_clicked = st.button("▶ Run simulation", type="primary", width='stretch')

    st.markdown("##### Comparison basis")
    st.caption(f"Current vs experiment baseline (`{EXPERIMENT_BASELINE_LABEL}`), same scenario and hours as Current.")

tabs = st.tabs(["Overview", "Marketplace Map", "Pricing", "Dispatch", "Experimentation", "AI Copilot"])

if run_clicked or "last_result" in st.session_state:
    if run_clicked:
        summary, ts, waits, zone_df = run_live_simulation(scenario_name, pricing_name, dispatch_name, int(seed), hours)
        st.session_state["last_result"] = (summary, ts, waits, zone_df, scenario_name, pricing_name, dispatch_name, int(seed), hours)
    else:
        summary, ts, waits, zone_df, scenario_name, pricing_name, dispatch_name, seed, hours = st.session_state["last_result"]

    ctx = sim_context.SimulationContext(scenario_name, pricing_name, dispatch_name, seed, hours)
    s = summary

    # Experiment baseline: FIXED reference policy, evaluated under the SAME
    # scenario/seed/hours as Current so the comparison is apples-to-apples.
    # Not user-adjustable -- this is the one thing "baseline" ever means on
    # this page (see module docstring).
    baseline_summary, _, _, _ = run_live_simulation(scenario_name, config.BASELINE_PRICING.value, config.BASELINE_DISPATCH.value, int(seed), hours)
    is_baseline_run = (pricing_name == config.BASELINE_PRICING.value and dispatch_name == config.BASELINE_DISPATCH.value)

    health = decision.compute_health_score(s)
    baseline_health = decision.compute_health_score(baseline_summary)

    # =====================================================================
    # OVERVIEW
    # =====================================================================
    with tabs[0]:
        st.markdown(
            f"**Current:** `{ctx.short_label()}`  ·  {scenario_name.replace('_',' ').title()} scenario, seed {seed}  \n"
            f"**Experiment baseline:** `{EXPERIMENT_BASELINE_LABEL}`"
            + (" _(current = baseline)_" if is_baseline_run else "  ·  same scenario, for comparison")
        )

        # --- Marketplace Health ------------------------------------------------
        h1, h2 = st.columns([1, 3])
        with h1:
            st.metric(
                "Marketplace health", f"{health.overall:.0f} / 100",
                delta=fmt_delta(health.overall - baseline_health.overall) if not is_baseline_run else None,
                delta_color="normal", help="Weighted blend of rider experience, driver experience, marketplace efficiency, and business performance. See 'About this simulation' below for the formula.",
            )
            st.caption(health.interpretation())
        with h2:
            dim_cols = st.columns(4)
            for col, (dim, label_) in zip(dim_cols, decision.DIMENSION_LABELS.items()):
                with col:
                    st.metric(label_, f"{health.dimensions[dim]:.0f}")

        # --- Active issue (worst zone), right after health ---------------------
        worst_rows = zone_df.sort_values("supply_demand_ratio").head(3)
        if not worst_rows.empty and worst_rows.iloc[0]["status"] in ("high_pressure", "severe_shortage"):
            worst = worst_rows.iloc[0]
            st.warning(
                f"⚠️ **Active issue -- {worst['name']}**: "
                f"supply/demand ratio {worst['supply_demand_ratio']:.2f}, "
                f"P90 wait {worst['p90_wait_min']:.1f} min, cancellation {worst['cancellation_rate']*100:.0f}%. "
                f"_See the Marketplace Map tab for full zone detail._"
            )

        st.divider()

        # --- Recommendation card (hero) -----------------------------------------
        results_df, comparisons_df, decision_table_df = load_results()

        st.subheader("🤖 Recommended action")
        obj_col, obj_help_col = st.columns([1, 3])
        with obj_col:
            objective = st.selectbox(
                "Optimization objective", list(decision.OBJECTIVE_PROFILES.keys()),
                format_func=lambda k: decision.OBJECTIVE_PROFILE_LABELS[k], index=1, key="objective_select",
            )
        with obj_help_col:
            st.caption(decision.OBJECTIVE_PROFILE_DESCRIPTIONS[objective])

        rec = cached_recommend_policy(results_df, scenario_name, pricing_name, dispatch_name, objective)

        # Always show all 6 -- driver earnings must be visible even when the
        # objective isn't Driver-first, so a viewer can see what every
        # objective is (and isn't) trading off, not just what it optimized for.
        IMPACT_METRICS = [
            "p90_wait_min", "completion_rate", "cancellation_rate",
            "platform_revenue", "driver_utilization_mean", "earnings_per_online_hour_mean",
        ]

        if rec["action"] == "error":
            st.info(rec["reason"])
        elif rec["action"] == "none":
            st.success(f"No action recommended -- **{pricing_name} + {dispatch_name}** is within target range for "
                       f"{scenario_name} under the {decision.OBJECTIVE_PROFILE_LABELS[objective]} objective. {rec['reason']}")
            bo = rec.get("best_overall")
            if bo is not None and not bo.get("guardrail_pass", True):
                failed = failing_guardrails_note(bo)
                st.caption(
                    f"`{bo['pricing_policy']} + {bo['dispatch_policy']}` scores highest on raw utility, "
                    f"but is rejected because: {'; '.join(failed) if failed else 'a guardrail check failed'}."
                )
        else:
            cur, best = rec["current"], rec["recommended"]
            st.markdown(f"##### {recommendation_headline(objective, scenario_name)}")
            cc1, cc2 = st.columns(2)
            cc1.markdown(f"**Current policy**  \n`{pricing_name} + {dispatch_name}`")
            cc2.markdown(f"**Recommended policy**  \n`{best['pricing_policy']} + {best['dispatch_policy']}`")

            st.markdown("**Why this policy?**")
            for bullet in why_this_policy_bullets(cur, best, IMPACT_METRICS):
                st.markdown(f"- {bullet}")

            st.markdown("**Expected impact** _(instant estimate -- pre-computed matrix means)_")
            st.markdown(impact_table_markdown(IMPACT_METRICS, cur, best))
            st.caption(f"Evidence: {decision.OBJECTIVE_PROFILE_LABELS[objective]} objective, selected from the pre-computed "
                       f"experiment matrix ({scenario_name} scenario, {'24' if scenario_name == 'NORMAL' else '6'} seeds per combo).")

            if not rec.get("best_overall_is_recommended", True) and rec.get("best_overall") is not None:
                bo = rec["best_overall"]
                failed = failing_guardrails_note(bo)
                st.caption(
                    f"ℹ️ `{bo['pricing_policy']} + {bo['dispatch_policy']}` scores higher on raw utility, "
                    f"but is rejected because: {'; '.join(failed) if failed else 'a guardrail check failed'}. "
                    f"Showing the best guardrail-passing policy instead."
                )

            st.markdown("**Guardrails**")
            guardrail_row(decision.evaluate_guardrails_absolute(best))

            gcol1, gcol2 = st.columns([1, 2])
            with gcol1:
                if st.button("🔬 Run counterfactual", width='stretch', type="primary"):
                    st.session_state["cf_request"] = (scenario_name, pricing_name, dispatch_name, best["pricing_policy"], best["dispatch_policy"])
            with gcol2:
                st.caption("Above is an **instant estimate**. Click to get a **validated counterfactual**: a fresh "
                           "paired live simulation with a real bootstrap confidence interval.")

            with st.expander("Does this change with priorities? (objective sensitivity)", expanded=True):
                st.caption("What each objective would recommend for this scenario -- confirms the recommendation "
                           "engine is sensitive to marketplace conditions and business priorities, not a fixed answer.")
                sens = cached_sensitivity_table(results_df, scenario_name, pricing_name, dispatch_name)
                sens_display = sens.copy()
                sens_display["policy"] = sens_display.pricing_policy + " + " + sens_display.dispatch_policy
                sens_display["p90_wait_min"] = sens_display.p90_wait_min.map(labels.fmt_minutes)
                sens_display["platform_revenue"] = sens_display.platform_revenue.map(labels.fmt_currency)
                sens_display["earnings_per_online_hour_mean"] = sens_display.earnings_per_online_hour_mean.map(labels.fmt_currency)
                sens_display = sens_display[["objective", "policy", "p90_wait_min", "platform_revenue", "earnings_per_online_hour_mean", "matches_current"]]
                sens_display.columns = ["Objective", "Recommended policy", "P90 wait", "Revenue", "Driver earnings/hr", "Matches current"]
                st.dataframe(sens_display, width='stretch', hide_index=True)

                n_distinct_policies = (sens["pricing_policy"] + "+" + sens["dispatch_policy"]).nunique()
                if n_distinct_policies == 1:
                    top = sens.iloc[0]
                    st.caption(
                        f"All 4 objectives agree here: `{top.pricing_policy} + {top.dispatch_policy}` improves rider "
                        f"wait, cancellation, revenue, and driver earnings **simultaneously** in {scenario_name} -- "
                        f"there's no real tradeoff to prioritize between in this specific condition. Objectives "
                        f"diverge in lower-stress scenarios, where demand-throttling costs riders more than it helps "
                        f"them (see CHANGELOG's objective audit)."
                    )
                else:
                    st.caption(
                        f"Objectives genuinely diverge here ({n_distinct_policies} different recommended policy "
                        f"combinations across 4 objectives) -- which one is \"best\" depends on whose outcomes you "
                        f"weight most."
                    )

        if "cf_request" in st.session_state:
            cf_scn, cf_cp, cf_cd, cf_ap, cf_ad = st.session_state["cf_request"]
            n_cf_seeds = len(decision.COUNTERFACTUAL_SEEDS)
            with st.spinner(f"Running live counterfactual: {cf_cp}+{cf_cd} vs {cf_ap}+{cf_ad} ({n_cf_seeds} paired seeds)..."):
                cf = cached_counterfactual(cf_scn, cf_cp, cf_cd, cf_ap, cf_ad)
            st.markdown(f"##### ✅ Validated counterfactual: `{cf_cp}+{cf_cd}` (current) vs. `{cf_ap}+{cf_ad}` (alternative) -- {cf['n_seeds']} paired seeds")
            comp = cf["comparison"].copy()
            comp_display = comp[["metric", "baseline_mean", "treatment_mean", "signed_relative_effect_pct",
                                  "bootstrap_ci_95_lo", "bootstrap_ci_95_hi", "wilcoxon_p", "practically_significant_improvement"]].copy()
            comp_display["metric"] = comp_display["metric"].map(labels.label)
            comp_display.columns = ["Metric", "Current", "Alternative", "Change vs. current (%)", "95% CI (low)", "95% CI (high)", "p-value", "Practically significant"]
            st.dataframe(comp_display.round(4), width='stretch', hide_index=True)
            st.caption("Statistically significant = the 95% CI excludes zero. Practically significant = also clears the pre-registered minimum effect-size bar.")

            st.markdown("**Guardrails** _(alternative vs. current, this counterfactual)_")
            g = cf["guardrails"]
            gcols = st.columns(4)
            for col, key, label_ in zip(gcols, ["p90_wait", "cancellation", "earnings", "revenue"],
                                        [labels.label("p90_wait_min"), labels.label("cancellation_rate"), "Driver earnings", "Revenue"]):
                col.metric(label_, "🟢 Pass" if g[key] else "🔴 Fail")
            if st.button("Clear counterfactual"):
                del st.session_state["cf_request"]
                st.rerun()

        st.divider()

        # --- Map ---------------------------------------------------------------
        st.markdown("#### Marketplace map")
        st.caption(f"{labels.map_legend_caption('Marketplace status')} Click into the Marketplace Map tab for per-zone detail.")
        st.plotly_chart(charts.marketplace_map(zone_df, "Marketplace status", ctx), width='stretch')

        st.markdown("#### Demand vs. supply over the simulated day")
        if not ts.empty:
            st.plotly_chart(charts.demand_and_supply_over_time(ts, ctx), width='stretch')

        st.markdown("#### Policy tradeoff")
        st.caption(
            "Each point is a pricing + dispatch policy. Better policies sit toward lower wait (left) and higher "
            "revenue (up). Yellow points are Pareto-efficient -- no other policy beats them on both at once."
        )
        recommended_pair = (rec["recommended"]["pricing_policy"], rec["recommended"]["dispatch_policy"]) if rec.get("action") == "switch" else None
        scenario_df = results_df[results_df.scenario == scenario_name]
        st.plotly_chart(
            charts.policy_tradeoff_scatter(scenario_df, current=(pricing_name, dispatch_name), recommended=recommended_pair),
            width='stretch',
        )

        with st.expander("Advanced: guardrail detail, zone table, wait distribution"):
            st.markdown("**Guardrail status -- current policy**")
            checks = decision.evaluate_guardrails_absolute(s)
            st.plotly_chart(charts.guardrail_bars(checks), width='stretch')
            st.markdown("**Per-zone state** _(technical column names -- see Marketplace Map tab for a plain-language view)_")
            st.dataframe(
                zone_df[["name", "archetype", "status", "demand_per_min", "avg_available_drivers",
                         "supply_demand_ratio", "p90_wait_min", "cancellation_rate", "avg_surge_multiplier"]]
                .sort_values("supply_demand_ratio").round(2),
                width='stretch', hide_index=True,
            )
            if waits:
                st.plotly_chart(charts.wait_distribution({ctx.short_label(): waits}, ctx), width='stretch')

        with st.expander("ℹ️ About this simulation"):
            st.markdown(
                "All marketplace data here is **synthetic**, generated from documented assumptions "
                "(see `docs/ASSUMPTIONS.md`) -- not real-world ride-hailing data. Results are useful for "
                "comparing policies against each other under consistent assumptions; treat them as "
                "**hypothesis-generating, not a real-world performance claim**. Production validation would "
                "require calibrating the model against historical data, then shadow testing and a controlled "
                "A/B experiment before any live rollout.\n\n"
                "**Marketplace Health Score formula:** 4 weighted dimensions (Rider Experience 30%, Driver "
                "Experience 25%, Marketplace Efficiency 25%, Business Performance 20%), each a blend of metrics "
                "normalized against the empirical 5th/95th percentiles of the 1,080-run experiment matrix -- "
                "see `src/decision.py` for the exact weights."
            )

    # =====================================================================
    # MARKETPLACE MAP (dedicated tab: zone click-through detail)
    # =====================================================================
    with tabs[1]:
        st.subheader("Marketplace Map")
        st.caption(f"Current: `{ctx.short_label()}` -- {scenario_name.replace('_',' ').title()} scenario, seed {seed}.")
        mm_metric = st.selectbox("Metric", list(charts.MAP_METRIC_OPTIONS.keys()), key="map_tab_metric")
        st.caption(f"{labels.map_legend_caption(mm_metric)} Click a zone marker to inspect it, or use the dropdown below.")
        map_state = st.plotly_chart(
            charts.marketplace_map(zone_df, mm_metric, ctx), width='stretch', key="map_tab_chart",
            on_select="rerun", selection_mode="points",
        )
        clicked_points = (map_state or {}).get("selection", {}).get("points", []) if hasattr(map_state, "get") else []
        if clicked_points:
            clicked_zone = zone_df.iloc[clicked_points[0]["point_index"]]["name"]
            if st.session_state.get("_last_clicked_zone") != clicked_zone:
                st.session_state["_last_clicked_zone"] = clicked_zone
                st.session_state["zone_pick_select"] = clicked_zone

        st.markdown("#### Zone detail")
        zone_pick = st.selectbox("Select a zone", zone_df["name"].tolist(), key="zone_pick_select")
        zrow = zone_df[zone_df["name"] == zone_pick].iloc[0]
        zc1, zc2, zc3, zc4 = st.columns(4)
        zc1.metric(labels.label("demand_per_min"), f"{zrow['demand_per_min']:.2f}", help=labels.help_text("demand_per_min"))
        zc2.metric(labels.label("avg_available_drivers"), f"{zrow['avg_available_drivers']:.1f}", help=labels.help_text("avg_available_drivers"))
        zc3.metric(labels.label("supply_demand_ratio"), f"{zrow['supply_demand_ratio']:.2f}", help=labels.help_text("supply_demand_ratio"))
        zc4.metric("Status", zrow["status"].replace("_", " ").title())
        zc5, zc6, zc7 = st.columns(3)
        zc5.metric(labels.label("p90_wait_min"), f"{zrow['p90_wait_min']:.1f} min" if zrow['p90_wait_min'] == zrow['p90_wait_min'] else "n/a", help=labels.help_text("p90_wait_min"))
        zc6.metric(labels.label("cancellation_rate"), f"{zrow['cancellation_rate']*100:.0f}%", help=labels.help_text("cancellation_rate"))
        zc7.metric(labels.label("avg_surge_multiplier"), f"{zrow['avg_surge_multiplier']:.2f}x", help=labels.help_text("avg_surge_multiplier"))

        city_avg_demand = zone_df["demand_per_min"].mean()
        city_avg_avail = zone_df["avg_available_drivers"].mean()
        zstate_obj = zone_state.ZoneState(**{f.name: zrow[f.name] for f in dataclass_fields(zone_state.ZoneState)})
        st.markdown("**Why?**")
        for reason in zone_state.explain_zone(zstate_obj, city_avg_demand, city_avg_avail):
            st.markdown(f"- {reason}")

    # =====================================================================
    # PRICING
    # =====================================================================
    with tabs[2]:
        st.subheader("Pricing")
        st.caption(f"`{pricing_name}` -- how a price change flows through to revenue:")
        st.markdown("`Marketplace imbalance` → `Surge` → `Quoted price` → `Rider conversion / rejection` → `Completed rides` → `Revenue`")
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric(labels.label("avg_surge_multiplier"), f"{s['avg_surge_multiplier']:.2f}x", help=labels.help_text("avg_surge_multiplier"))
        pc2.metric(labels.label("price_index"), f"{s['price_index']:.3f}", help=labels.help_text("price_index"))
        pc3.metric(labels.label("rider_conversion_rate"), f"{s['rider_conversion_rate']*100:.1f}%", help=labels.help_text("rider_conversion_rate"))
        pc4.metric(labels.label("n_rejected_offer"), f"{s['n_rejected_offer']}")
        if not ts.empty:
            st.plotly_chart(charts.surge_over_time(ts, ctx), width='stretch')

    # =====================================================================
    # DISPATCH
    # =====================================================================
    with tabs[3]:
        st.subheader("Dispatch")
        st.caption(f"`{dispatch_name}` -- how a ride gets matched:")
        st.markdown(" → ".join(f"`{step}`" for step in labels.dispatch_flow(dispatch_name).split(" → ")))
        dc1, dc2, dc3, dc4 = st.columns(4)
        dc1.metric(labels.label("p90_wait_min"), labels.fmt_minutes(s["p90_wait_min"]), help=labels.help_text("p90_wait_min"))
        dc2.metric(labels.label("avg_pickup_distance_km"), f"{s['avg_pickup_distance_km']:.2f} km", help=labels.help_text("avg_pickup_distance_km"))
        dc3.metric(labels.label("driver_acceptance_rate"), f"{s['driver_acceptance_rate']*100:.1f}%", help=labels.help_text("driver_acceptance_rate"))
        dc4.metric(labels.label("driver_utilization_mean"), f"{s['driver_utilization_mean']*100:.1f}%", help=labels.help_text("driver_utilization_mean"))
        dc5, dc6, dc7 = st.columns(3)
        dc5.metric(labels.label("completion_rate"), f"{s['completion_rate']*100:.1f}%", help=labels.help_text("completion_rate"))
        dc6.metric(labels.label("cancellation_rate"), f"{s['cancellation_rate']*100:.1f}%", help=labels.help_text("cancellation_rate"))
        dc7.metric("Driver earnings/online-hr", labels.fmt_currency(s["earnings_per_online_hour_mean"]), help=labels.help_text("earnings_per_online_hour_mean"))

        st.markdown("#### NEAREST_DRIVER vs. ETA_OPTIMIZED, this scenario")
        st.caption(f"Mean across all pricing policies, {scenario_name} scenario, from the pre-computed matrix -- "
                   f"the project's own headline finding (see README).")
        _results_df, _, _ = load_results()
        cmp_df = _results_df[
            (_results_df.scenario == scenario_name) & (_results_df.dispatch_policy.isin(["NEAREST_DRIVER", "ETA_OPTIMIZED"]))
        ]
        if not cmp_df.empty:
            cmp = cmp_df.groupby("dispatch_policy")[
                ["p90_wait_min", "avg_pickup_distance_km", "driver_acceptance_rate",
                 "driver_utilization_mean", "completion_rate", "cancellation_rate", "earnings_per_online_hour_mean"]
            ].mean()
            cmp_display = cmp.copy()
            cmp_display["earnings_per_online_hour_mean"] = cmp_display["earnings_per_online_hour_mean"].map(labels.fmt_currency)
            for col in ["p90_wait_min"]:
                cmp_display[col] = cmp_display[col].map(labels.fmt_minutes)
            for col in ["avg_pickup_distance_km"]:
                cmp_display[col] = cmp_display[col].map(labels.fmt_km)
            for col in ["driver_acceptance_rate", "driver_utilization_mean", "completion_rate", "cancellation_rate"]:
                cmp_display[col] = cmp_display[col].map(labels.fmt_pct)
            cmp_display.columns = [labels.label(c) for c in cmp_display.columns]
            st.dataframe(cmp_display.T, width='stretch')
else:
    for t in tabs[:4]:
        with t:
            st.info("Pick a scenario/pricing/dispatch policy in the sidebar and click **Run simulation**.")

# =========================================================================
# EXPERIMENTATION
# =========================================================================
with tabs[4]:
    st.subheader("Experimentation")
    try:
        df, comparisons, decision_table = load_results()
        st.caption(f"{len(df)} total simulation runs -- {(df.experiment_group=='core').sum()} core (NORMAL scenario, 24 seeds) + "
                   f"{(df.experiment_group=='robustness').sum()} robustness runs across 5 stress scenarios.")

        # --- Best policy card (progressive disclosure: this first) -----------
        top = decision_table[decision_table.meets_all_guardrails].sort_values("north_star", ascending=False)
        if top.empty:
            top_row = decision_table.sort_values("north_star", ascending=False).iloc[0]
            guardrail_note = "⚠️ No combination clears every guardrail vs. the experiment baseline; showing the North-Star leader anyway."
        else:
            top_row = top.iloc[0]
            guardrail_note = f"✅ Clears every guardrail vs. the experiment baseline (`{EXPERIMENT_BASELINE_LABEL}`, NORMAL scenario)."

        st.markdown("### 🏆 Best policy under current experiment criteria")
        st.markdown(f"#### `{top_row.pricing_policy} + {top_row.dispatch_policy}`")
        st.caption("Selected from 1,080 simulated runs, ranked by North Star subject to guardrails.")
        bc1, bc2, bc3 = st.columns(3)
        bc1.metric(labels.label("p90_wait_min"), f"{top_row.p90_wait_min:.2f} min")
        bc2.metric(labels.label("platform_revenue"), f"₹{top_row.platform_revenue:,.0f}")
        bc3.metric("Driver earnings/hr", f"₹{top_row.earnings_per_online_hour_mean:.0f}")
        st.caption(guardrail_note)

        with st.expander("Why was this selected?", expanded=True):
            b_p90 = top_row.baseline_p90_wait_min
            wait_delta_pct = (top_row.p90_wait_min - b_p90) / b_p90 * 100 if b_p90 else 0
            b_rev = top_row.baseline_platform_revenue
            rev_delta_pct = (top_row.platform_revenue - b_rev) / b_rev * 100 if b_rev else 0
            wait_word = "decreased" if wait_delta_pct <= 0 else "increased"
            rev_word = "increased" if rev_delta_pct >= 0 else "decreased"
            st.markdown(
                f"- P90 rider wait {wait_word} **{abs(wait_delta_pct):.1f}%** vs. the experiment baseline ({b_p90:.2f} min)\n"
                f"- Platform revenue {rev_word} **{abs(rev_delta_pct):.1f}%** vs. the experiment baseline (₹{b_rev:,.0f})\n"
                f"- Guardrails: P90 wait {'🟢' if top_row.meets_p90_guardrail else '🔴'} | "
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
                direction = "decreased" if m.signed_relative_effect_pct >= 0 else "increased"
                st.markdown(
                    f"- P90 rider wait {direction} **{abs(m.signed_relative_effect_pct):.1f}%**, "
                    f"95% CI for wait reduction: {-m.bootstrap_ci_95_hi:.2f}–{-m.bootstrap_ci_95_lo:.2f} min, "
                    f"p={m.wilcoxon_p:.2e}, n=24 paired seeds -- **{sig}**."
                )

        st.markdown("#### Policy tradeoff")
        st.caption(
            "Each point is a pricing + dispatch policy. Better policies sit toward lower wait (left) and higher "
            "revenue (up). Yellow points are Pareto-efficient; blue is the experiment baseline."
        )
        core = df[df.experiment_group == "core"]
        st.plotly_chart(
            charts.policy_tradeoff_scatter(
                core, current=(config.BASELINE_PRICING.value, config.BASELINE_DISPATCH.value),
                recommended=(top_row.pricing_policy, top_row.dispatch_policy),
                current_label="Experiment baseline",
            ),
            width='stretch',
        )

        st.markdown("#### Guardrails -- best policy vs. absolute limits")
        top_row_checks = decision.evaluate_guardrails_absolute(top_row.to_dict())
        st.plotly_chart(charts.guardrail_bars(top_row_checks), width='stretch')
        n_shown, n_total = len(top_row_checks), len(decision.GUARDRAIL_ABSOLUTE)
        if n_shown < n_total:
            st.caption(f"Only {n_shown} of {n_total} absolute guardrails are tracked in the pre-computed experiment "
                       f"matrix (decision_table.csv) -- the rest need a live run; see the Overview tab's Advanced "
                       f"section for the full set against the current live policy.")

        st.markdown("#### Recommendation distribution")
        st.caption(
            "Does the optimizer actually respond to marketplace conditions, or does one policy always win? "
            "The top pick for each of the 6 scenarios, tallied -- see the CHANGELOG's objective audit for why "
            "this matters and what was found."
        )
        freq_objective = st.selectbox(
            "Objective", list(decision.OBJECTIVE_PROFILES.keys()),
            format_func=lambda k: decision.OBJECTIVE_PROFILE_LABELS[k], index=1, key="freq_objective_select",
        )
        freq = cached_recommendation_frequency(df, freq_objective)
        st.plotly_chart(
            charts.recommendation_frequency_bar(freq, decision.OBJECTIVE_PROFILE_LABELS[freq_objective]),
            width='stretch',
        )
        if len(freq) == 1:
            st.caption(f"One combo wins all 6 scenarios under {decision.OBJECTIVE_PROFILE_LABELS[freq_objective]} -- "
                       f"try RIDER_FIRST or DRIVER_FIRST above to see genuine scenario-sensitivity.")

        with st.expander("Advanced Analysis: supporting charts and full statistical comparisons"):
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(charts.dispatch_vs_wait(core, "p90_wait_min", "P90 Rider Wait by Dispatch Policy", "P90 wait (min)"), width='stretch')
            with col2:
                st.plotly_chart(charts.confidence_intervals(comparisons), width='stretch')
            st.plotly_chart(charts.dispatch_vs_utilization(core), width='stretch')
            st.markdown("#### Full paired statistical comparisons vs. the experiment baseline")
            st.dataframe(comparisons, width='stretch')

        with st.expander("View full experiment matrix (1,080 runs)"):
            st.markdown("#### Decision table (ranked by North Star, subject to guardrails)")
            st.dataframe(decision_table, width='stretch')
    except FileNotFoundError:
        st.warning("Run `python run_experiments.py` and `python analyze_results.py` first to populate this tab.")

# =========================================================================
# AI COPILOT
# =========================================================================
with tabs[5]:
    st.subheader("🤖 AI Marketplace Analyst")
    st.caption("Ask questions about marketplace health, policies, experiments, or counterfactuals.")
    st.caption(
        "Answers are grounded in simulator, experiment, and ML tool outputs -- metrics are not invented. "
        "Expand \"Show tool calls\" under any answer to see the evidence."
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
            "Which policy should we use?",
            "Why are cancellations high?",
            "What happens if we remove surge?",
            "Where is supply most constrained?",
            "How much demand is expected in Downtown soon?",
        ]
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
                    with st.expander(f"Show tool calls ({len(turn['tool_calls'])})"):
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
                    with st.expander(f"Show tool calls ({len(result['tool_calls'])})"):
                        for tc in result["tool_calls"]:
                            st.markdown(f"**`{tc['name']}`**`({tc['input']})`")
                            st.json(tc["result"], expanded=False)
            st.session_state["copilot_history"].append(
                {"question": question, "answer": result["answer"], "tool_calls": result["tool_calls"]}
            )

        if st.session_state["copilot_history"] and st.button("Clear conversation"):
            st.session_state["copilot_history"] = []
            st.rerun()
