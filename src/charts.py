"""Chart builders (Plotly) shared by make_charts.py (static export) and the
Streamlit dashboard (dashboard/app.py). Every figure has a title, axis labels
with units, and a legend where more than one series is shown."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.labels import SEMANTIC_COLORS

TEMPLATE = "plotly_white"
COLORWAY = px.colors.qualitative.Set2


def pricing_vs_price_index(core: pd.DataFrame) -> go.Figure:
    g = core.groupby("pricing_policy", as_index=False)["price_index"].mean()
    fig = px.bar(g, x="pricing_policy", y="price_index", color="pricing_policy",
                 color_discrete_sequence=COLORWAY, template=TEMPLATE,
                 title="Realized Price Index by Pricing Policy (1.0 = no markup vs. no-surge fare)")
    fig.update_layout(xaxis_title="Pricing policy", yaxis_title="Price index (avg realized price / base fare)", showlegend=False)
    fig.add_hline(y=1.0, line_dash="dot", annotation_text="no markup")
    return fig


def pricing_vs_conversion(core: pd.DataFrame) -> go.Figure:
    g = core.groupby("pricing_policy", as_index=False).agg(
        rider_conversion_rate=("rider_conversion_rate", "mean"),
        completion_rate=("completion_rate", "mean"),
    )
    fig = go.Figure()
    fig.add_bar(x=g.pricing_policy, y=g.rider_conversion_rate * 100, name="Rider conversion rate (%)", marker_color=COLORWAY[0])
    fig.add_bar(x=g.pricing_policy, y=g.completion_rate * 100, name="Completion rate (%)", marker_color=COLORWAY[1])
    fig.update_layout(title="Surge Suppresses Demand: Conversion & Completion by Pricing Policy",
                       xaxis_title="Pricing policy", yaxis_title="Rate (%)", barmode="group", template=TEMPLATE)
    return fig


def pricing_vs_revenue(core: pd.DataFrame) -> go.Figure:
    g = core.groupby("pricing_policy", as_index=False)["platform_revenue"].mean()
    fig = px.bar(g, x="pricing_policy", y="platform_revenue", color="pricing_policy",
                 color_discrete_sequence=COLORWAY, template=TEMPLATE,
                 title="Platform Revenue by Pricing Policy (avg per simulated day)")
    fig.update_layout(xaxis_title="Pricing policy", yaxis_title="Platform revenue (currency units / day)", showlegend=False)
    return fig


def dispatch_vs_wait(core: pd.DataFrame, metric: str, title: str, ylabel: str) -> go.Figure:
    g = core.groupby(["dispatch_policy", "pricing_policy"], as_index=False)[metric].mean()
    fig = px.bar(g, x="dispatch_policy", y=metric, color="pricing_policy", barmode="group",
                 color_discrete_sequence=COLORWAY, template=TEMPLATE, title=title)
    fig.update_layout(xaxis_title="Dispatch policy", yaxis_title=ylabel, legend_title="Pricing policy")
    return fig


def dispatch_vs_utilization(core: pd.DataFrame) -> go.Figure:
    return dispatch_vs_wait(core, "driver_utilization_mean", "Driver Utilization by Dispatch Policy", "Driver utilization (active time / online time)")


def policy_frontier(core: pd.DataFrame) -> go.Figure:
    g = core.groupby(["pricing_policy", "dispatch_policy"], as_index=False).agg(
        p90_wait_min=("p90_wait_min", "mean"), platform_revenue=("platform_revenue", "mean"),
    )
    fig = px.scatter(
        g, x="p90_wait_min", y="platform_revenue", color="dispatch_policy", symbol="pricing_policy",
        color_discrete_sequence=COLORWAY, template=TEMPLATE,
        title="Policy Frontier: P90 Rider Wait vs. Platform Revenue (each point = one of 20 policy combinations)",
    )
    fig.update_layout(xaxis_title="P90 rider wait (minutes, lower is better)", yaxis_title="Platform revenue (currency units / day)")
    fig.update_traces(marker=dict(size=12, line=dict(width=1, color="white")))
    return fig


def confidence_intervals(comparisons: pd.DataFrame) -> go.Figure:
    """P90 wait metric is 'lower is better', so the raw bootstrap CI (computed
    on treatment-minus-baseline) is sign-flipped and rescaled to '% improvement'
    for direct display; error bars are derived from that same flip."""
    primary = comparisons[comparisons.role == "primary"].copy()
    primary["label"] = primary.dispatch_policy + " | " + primary.pricing_policy
    primary = primary.sort_values("signed_relative_effect_pct")

    lo = -primary["bootstrap_ci_95_hi"] / primary["baseline_mean"] * 100
    hi = -primary["bootstrap_ci_95_lo"] / primary["baseline_mean"] * 100

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=primary["signed_relative_effect_pct"], y=primary["label"], orientation="h",
        marker_color=[COLORWAY[0] if v else COLORWAY[2] for v in primary["practically_significant_improvement"]],
        error_x=dict(
            type="data", symmetric=False,
            array=(hi - primary["signed_relative_effect_pct"]).values,
            arrayminus=(primary["signed_relative_effect_pct"] - lo).values,
        ),
        name="P90 wait improvement (%)",
    ))
    fig.update_layout(
        title="P90 Wait Improvement vs. NEAREST_DRIVER Baseline (95% bootstrap CI, n=24 paired seeds)<br>"
              "<sup>Green = clears the pre-registered 5% practical-significance bar; grey = does not</sup>",
        xaxis_title="P90 wait improvement vs. baseline (%, positive = better)",
        yaxis_title="Dispatch policy | Pricing policy",
        template=TEMPLATE, height=500,
    )
    fig.add_vline(x=0, line_dash="dot")
    return fig


def wait_distribution(wait_minutes_by_policy: dict[str, list[float]], context=None) -> go.Figure:
    fig = go.Figure()
    for name, waits in wait_minutes_by_policy.items():
        fig.add_trace(go.Histogram(x=waits, name=name, opacity=0.6, nbinsx=40, histnorm="probability"))
    suffix = f" {context.chart_suffix()}" if context is not None else ""
    fig.update_layout(
        title=f"Rider Wait Time Distribution{suffix}",
        xaxis_title="Wait time (minutes, request to pickup)", yaxis_title="Share of completed trips",
        barmode="overlay", template=TEMPLATE,
    )
    return fig


def demand_and_supply_over_time(ts: pd.DataFrame, context=None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts.hour, y=ts.outstanding_requests, name="Outstanding requests (waiting)", line=dict(color=COLORWAY[0])))
    fig.add_trace(go.Scatter(x=ts.hour, y=ts.available_drivers, name="Available drivers", line=dict(color=COLORWAY[1])))
    suffix = f" {context.chart_suffix()}" if context is not None else "(current run)"
    fig.update_layout(
        title=f"Demand & Supply Over a Simulated Day {suffix}",
        xaxis_title="Hour of day", yaxis_title="Count (city-wide)", template=TEMPLATE,
    )
    return fig


def surge_over_time(ts: pd.DataFrame, context=None) -> go.Figure:
    suffix = f" {context.chart_suffix()}" if context is not None else "(current run)"
    fig = px.line(ts, x="hour", y="avg_surge", template=TEMPLATE,
                  title=f"Average Surge Multiplier Over a Simulated Day {suffix}")
    fig.update_layout(xaxis_title="Hour of day", yaxis_title="Average surge multiplier (city-wide)")
    fig.add_hline(y=1.0, line_dash="dot")
    return fig


MAP_METRIC_OPTIONS = {
    "Marketplace status": ("status_code", "status_label", "RdYlGn", True),
    "Demand (req/min)": ("demand_per_min", None, "Oranges", False),
    "Available drivers": ("avg_available_drivers", None, "Blues", False),
    "Supply/demand ratio": ("supply_demand_ratio", None, "RdYlGn", False),
    "P90 wait (min)": ("p90_wait_min", None, "Reds", False),
    "Cancellation rate": ("cancellation_rate", None, "Reds", False),
    "Surge multiplier": ("avg_surge_multiplier", None, "Purples", False),
}

_STATUS_ORDER = {"severe_shortage": 0, "high_pressure": 1, "moderate": 2, "healthy": 3}


def marketplace_map(zone_df: pd.DataFrame, metric_label: str, context=None) -> go.Figure:
    """Synthetic-city zone map: each of the 10 zones (src/config.py ZONES,
    fixed x/y grid coordinates) is one marker, sized by demand and colored
    by the selected metric. Not a real geographic map -- there is no claim
    about real-world geography here, just the simulator's own zone layout."""
    from src.zone_state import STATUS_COLOR, STATUS_LABEL

    df = zone_df.copy()
    col, _hover_extra, colorscale, reversed_status = MAP_METRIC_OPTIONS[metric_label]
    is_status = col == "status_code"

    size = df["demand_per_min"] - df["demand_per_min"].min()
    size = 22 + 28 * (size / size.max() if size.max() > 0 else 0)

    marker = dict(size=size, line=dict(width=2, color="white"))
    if is_status:
        marker["color"] = [STATUS_COLOR[s] for s in df["status"]]
        hover_value = df["status"].map(STATUS_LABEL)
    else:
        marker.update(color=df[col], colorscale=colorscale, reversescale=reversed_status,
                       showscale=True, colorbar=dict(title=metric_label))
        hover_value = df[col].round(2)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["x"], y=df["y"], mode="markers+text", marker=marker,
        text=df["name"], textposition="top center", customdata=hover_value,
        hovertemplate=f"<b>%{{text}}</b><br>{metric_label}: %{{customdata}}<extra></extra>",
        showlegend=False,
    ))
    if is_status:
        # discrete legend swatches -- a continuous colorbar doesn't read
        # well for 4 categorical states
        for status, hexcolor in STATUS_COLOR.items():
            fig.add_trace(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=12, color=hexcolor), name=STATUS_LABEL[status],
            ))

    suffix = f" {context.chart_suffix()}" if context is not None else ""
    fig.update_layout(
        title=f"Marketplace Map -- {metric_label}{suffix}",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        template=TEMPLATE, height=460,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15) if is_status else {},
        margin=dict(l=10, r=10, t=60, b=10),
        clickmode="event+select",  # a single click on a marker fires Streamlit's on_select immediately
    )
    return fig


def guardrail_bars(checks: list) -> go.Figure:
    """checks: list[src.decision.GuardrailCheck]. One horizontal bar per
    guardrail, filled to `utilization_pct` of its limit, red past 100%."""
    labels = [f"{c.label} ({c.value:.2f} vs. limit {c.bound:.2f})" for c in checks]
    pct = [min(c.utilization_pct, 120.0) for c in checks]
    colors = [SEMANTIC_COLORS["green"] if c.passed else SEMANTIC_COLORS["red"] for c in checks]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pct, y=labels, orientation="h", marker_color=colors))
    fig.add_vline(x=100, line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Guardrail status (% of limit used)",
        xaxis_title="% of guardrail limit", yaxis_title="",
        template=TEMPLATE, height=120 + 40 * len(checks), showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


def _pareto_efficient_mask(wait: pd.Series, revenue: pd.Series) -> pd.Series:
    """True where no other point has both <= wait and >= revenue (with at
    least one strictly better) -- i.e. the point isn't dominated. Used to
    highlight the frontier of "genuinely competitive" policies on the
    tradeoff chart, so a viewer isn't left to eyeball 20 points."""
    wait_v, rev_v = wait.values, revenue.values
    n = len(wait_v)
    efficient = []
    for i in range(n):
        dominated = False
        for j in range(n):
            if i == j:
                continue
            not_worse = wait_v[j] <= wait_v[i] and rev_v[j] >= rev_v[i]
            strictly_better = wait_v[j] < wait_v[i] or rev_v[j] > rev_v[i]
            if not_worse and strictly_better:
                dominated = True
                break
        efficient.append(not dominated)
    return pd.Series(efficient, index=wait.index)


def policy_tradeoff_scatter(
    df: pd.DataFrame, current: tuple[str, str] | None = None, recommended: tuple[str, str] | None = None,
    current_label: str = "Current",
) -> go.Figure:
    """Like charts.policy_frontier but highlights the current policy, the
    recommended policy, and the Pareto-efficient frontier (policies no
    other policy beats on both wait and revenue at once), so a viewer isn't
    forced to inspect the whole matrix to see which points are genuinely
    competitive."""
    from src import decision  # local import: avoids any top-level circularity, matches marketplace_map's convention

    g = df.groupby(["pricing_policy", "dispatch_policy"], as_index=False).agg(
        p90_wait_min=("p90_wait_min", "mean"), platform_revenue=("platform_revenue", "mean"),
        north_star_trips_per_online_hour=("north_star_trips_per_online_hour", "mean"),
    )
    g["label"] = g.pricing_policy + " + " + g.dispatch_policy
    g["guardrail_status"] = g.apply(
        lambda r: "Pass" if decision.guardrail_pass_row(r.to_dict()) else "Fails a guardrail", axis=1
    )
    g["role"] = "other"
    g.loc[_pareto_efficient_mask(g.p90_wait_min, g.platform_revenue), "role"] = "pareto"
    if current is not None:
        g.loc[(g.pricing_policy == current[0]) & (g.dispatch_policy == current[1]), "role"] = "current"
    if recommended is not None:
        g.loc[(g.pricing_policy == recommended[0]) & (g.dispatch_policy == recommended[1]), "role"] = "recommended"

    color_map = {
        "other": SEMANTIC_COLORS["grey"], "pareto": SEMANTIC_COLORS["amber"],
        "current": SEMANTIC_COLORS["blue"], "recommended": SEMANTIC_COLORS["green"],
    }
    size_map = {"other": 9, "pareto": 12, "current": 18, "recommended": 20}
    name_map = {"other": "Other", "pareto": "Pareto-efficient", "current": current_label, "recommended": "Recommended"}
    hover = (
        "<b>%{text}</b><br>P90 wait: %{x:.2f} min<br>Revenue: %{y:,.0f}<br>"
        "North Star: %{customdata[0]:.3f} trips/driver-hr<br>Guardrails: %{customdata[1]}<extra></extra>"
    )
    fig = go.Figure()
    for role in ["other", "pareto", "current", "recommended"]:
        sub = g[g.role == role]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub.p90_wait_min, y=sub.platform_revenue, mode="markers", name=name_map[role],
            marker=dict(size=size_map[role], color=color_map[role], line=dict(width=1, color="white")),
            text=sub.label, customdata=sub[["north_star_trips_per_online_hour", "guardrail_status"]].values,
            hovertemplate=hover,
        ))
    fig.update_layout(
        title="Policy Tradeoff: P90 Rider Wait vs. Platform Revenue",
        xaxis_title="P90 rider wait (minutes, lower is better)", yaxis_title="Platform revenue (lower is worse)",
        template=TEMPLATE, height=420,
    )
    return fig


def recommendation_frequency_bar(freq_df: pd.DataFrame, objective_label: str) -> go.Figure:
    """How often each (pricing, dispatch) combo is the top pick across all
    6 scenarios under one objective -- reveals whether the optimizer is
    context-sensitive (several combos win in different scenarios) or
    degenerate (one combo wins everywhere)."""
    g = freq_df.sort_values("times_recommended")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=g.times_recommended, y=g.combo, orientation="h",
        marker_color=COLORWAY[0],
        text=[f"{p:.0f}%" for p in g.pct_of_scenarios], textposition="outside",
        hovertemplate="<b>%{y}</b><br>Recommended in %{x} of 6 scenarios (%{text})<extra></extra>",
    ))
    fig.update_layout(
        title=f"Recommendation Distribution -- {objective_label} objective, across all 6 scenarios",
        xaxis_title="Scenarios where this combo was the top pick (of 6)", yaxis_title="",
        template=TEMPLATE, height=120 + 40 * len(g), margin=dict(l=10, r=40, t=50, b=10),
    )
    return fig


def zone_imbalance_heatmap(zone_hour_ratio: pd.DataFrame, zone_names: list[str]) -> go.Figure:
    fig = px.imshow(
        zone_hour_ratio.values, x=zone_hour_ratio.columns, y=zone_names,
        color_continuous_scale="RdYlGn", aspect="auto", template=TEMPLATE,
        labels=dict(x="Hour of day", y="Zone", color="Supply/demand ratio"),
        title="Zone-Level Supply/Demand Ratio by Hour (green = oversupplied, red = undersupplied)",
    )
    return fig
