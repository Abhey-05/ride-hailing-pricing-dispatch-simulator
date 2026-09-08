"""Chart builders (Plotly) shared by make_charts.py (static export) and the
Streamlit dashboard (dashboard/app.py). Every figure has a title, axis labels
with units, and a legend where more than one series is shown."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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


def wait_distribution(wait_minutes_by_policy: dict[str, list[float]]) -> go.Figure:
    fig = go.Figure()
    for name, waits in wait_minutes_by_policy.items():
        fig.add_trace(go.Histogram(x=waits, name=name, opacity=0.6, nbinsx=40, histnorm="probability"))
    fig.update_layout(
        title="Rider Wait Time Distribution: Baseline vs. Best Dispatch Policy (single representative day, seed=0)",
        xaxis_title="Wait time (minutes, request to pickup)", yaxis_title="Share of completed trips",
        barmode="overlay", template=TEMPLATE,
    )
    return fig


def demand_and_supply_over_time(ts: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ts.hour, y=ts.outstanding_requests, name="Outstanding requests (waiting)", line=dict(color=COLORWAY[0])))
    fig.add_trace(go.Scatter(x=ts.hour, y=ts.available_drivers, name="Available drivers", line=dict(color=COLORWAY[1])))
    fig.update_layout(
        title="Demand & Supply Over a Simulated Day (NORMAL scenario, seed=0)",
        xaxis_title="Hour of day", yaxis_title="Count (city-wide)", template=TEMPLATE,
    )
    return fig


def surge_over_time(ts: pd.DataFrame) -> go.Figure:
    fig = px.line(ts, x="hour", y="avg_surge", template=TEMPLATE,
                  title="Average Surge Multiplier Over a Simulated Day")
    fig.update_layout(xaxis_title="Hour of day", yaxis_title="Average surge multiplier (city-wide)")
    fig.add_hline(y=1.0, line_dash="dot")
    return fig


def zone_imbalance_heatmap(zone_hour_ratio: pd.DataFrame, zone_names: list[str]) -> go.Figure:
    fig = px.imshow(
        zone_hour_ratio.values, x=zone_hour_ratio.columns, y=zone_names,
        color_continuous_scale="RdYlGn", aspect="auto", template=TEMPLATE,
        labels=dict(x="Hour of day", y="Zone", color="Supply/demand ratio"),
        title="Zone-Level Supply/Demand Ratio by Hour (green = oversupplied, red = undersupplied)",
    )
    return fig
