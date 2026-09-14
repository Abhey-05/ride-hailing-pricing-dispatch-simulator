"""
Real-World Validation -- a separate, additive page.

This page is a read-only evidence layer around the existing ride-hailing
simulator. It never imports src.engine/src.pricing/src.dispatch/src.decision
and never touches dashboard/app.py, the Overview/Marketplace Map/Pricing/
Dispatch/Experimentation/AI Copilot pages, or any simulator parameter.

It reads exactly one file: results/real_data_insights.json, produced
locally (offline) by precompute_real_data_insights.py from a real food-
delivery operations dataset (Rider-Info.csv, gitignored -- never committed,
never read directly by this page or by anything deployed). That JSON
contains only aggregated, anonymized statistics -- no order_id, no
rider_id, no row-level record.

Purpose (see docs/REAL_DATA_VALIDATION.md for the full writeup): can real
operational data help validate the simulator's assumptions, diagnose real
bottlenecks, and generate hypotheses worth testing in the simulator?  It is
explicitly NOT a claim that this food-delivery dataset proves anything
about the ride-hailing simulator's correctness -- the two are related but
distinct domains, and every comparison on this page says so.

Causality stance: every relationship on this page is described as
"associated with" / "observed among", never "caused by" -- see the
Limitations section at the bottom and src/real_data/analysis.py's
module docstring for why.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src import labels  # noqa: E402 -- reused, not modified: fmt_minutes/fmt_pct/SEMANTIC_COLORS
from src.charts import COLORWAY, TEMPLATE  # noqa: E402 -- reused, not modified: same chart theme as the rest of the app

st.set_page_config(page_title="Real-World Validation", layout="wide", page_icon="🧭")

INSIGHTS_PATH = ROOT / "results" / "real_data_insights.json"

GREEN = labels.SEMANTIC_COLORS["green"]
RED = labels.SEMANTIC_COLORS["red"]
AMBER = labels.SEMANTIC_COLORS["amber"]
BLUE = labels.SEMANTIC_COLORS["blue"]
GREY = labels.SEMANTIC_COLORS["grey"]

STATUS_ICON = {"close": "🟢", "needs_calibration": "🟡", "significant_mismatch": "🔴", "not_modeled": "⚪", "not_comparable": "⚪"}
STATUS_LABEL = {
    "close": "Close",
    "needs_calibration": "Needs calibration",
    "significant_mismatch": "Significant mismatch",
    "not_modeled": "Not modeled in simulator",
    "not_comparable": "Not comparable",
}


@st.cache_data
def load_insights() -> dict | None:
    if not INSIGHTS_PATH.exists():
        return None
    with open(INSIGHTS_PATH) as f:
        return json.load(f)


data = load_insights()

st.title("🧭 Real-World Validation")
st.caption(
    "Observed food-delivery order data used to assess marketplace assumptions, diagnose "
    "operational bottlenecks, and identify policy hypotheses for simulation testing."
)
st.caption(
    "This page is a separate evidence layer around the existing simulator. It does not "
    "replace it, and it never changes a simulator parameter automatically."
)

if data is None:
    st.warning(
        "`results/real_data_insights.json` not found. This page reads a pre-computed, "
        "anonymized summary of a real dataset -- it does not read the raw dataset itself. "
        "Run `python precompute_real_data_insights.py Rider-Info.csv` locally to generate it, "
        "then reload this page."
    )
    st.stop()

insights = data["insights"]
overview = insights["overview"]

# =============================================================================
# EXECUTIVE FINDINGS
# =============================================================================
st.divider()
st.subheader("Executive findings")

findings: list[str] = []
findings.append(f"{overview['reassignment_rate'] * 100:.1f}% of orders experienced reassignment.")
e2e = insights["delay_diagnostics"].get("Order -> Delivery (end-to-end)", {})
if e2e.get("p90") is not None:
    findings.append(f"P90 order-to-delivery time was {e2e['p90']:.1f} min (median {e2e['median']:.1f} min).")

fm_op = next((o for o in insights["opportunities"] if o["problem"] == "First-mile distance friction"), None)
if fm_op:
    findings.append(fm_op["observation"])

reassignment = insights["reassignment"]
r_p90, nr_p90 = reassignment["reassigned"].get("end_to_end_p90_min"), reassignment["not_reassigned"].get("end_to_end_p90_min")
if r_p90 and nr_p90:
    delta_pct = (r_p90 - nr_p90) / nr_p90 * 100
    findings.append(f"Reassigned orders had a {delta_pct:+.0f}% different P90 end-to-end time than non-reassigned orders ({r_p90:.1f} vs. {nr_p90:.1f} min).")

findings.append(f"Cancellation rate was {overview['cancellation_rate'] * 100:.2f}%, with a completion rate of {overview['completion_rate'] * 100:.2f}%.")

for f in findings[:5]:
    st.markdown(f"- {f}")

# =============================================================================
# 1. DATASET OVERVIEW
# =============================================================================
st.divider()
st.subheader("Dataset overview")

st.caption(f"Date range: {overview['date_min']} → {overview['date_max']}")
c1, c2, c3 = st.columns(3)
c1.metric("Rows (orders)", f"{overview['row_count']:,}")
c2.metric("Unique riders", f"{overview['unique_riders']:,}")
c3.metric("Median end-to-end time", labels.fmt_minutes(overview["median_end_to_end_min"]))

c5, c6, c7, c8 = st.columns(4)
c5.metric("Completion rate", labels.fmt_pct(overview["completion_rate"]))
c6.metric("Cancellation rate", labels.fmt_pct(overview["cancellation_rate"]))
c7.metric("Undelivered rate", labels.fmt_pct(overview["undelivered_rate"]))
c8.metric("Reassignment rate", labels.fmt_pct(overview["reassignment_rate"]))

with st.expander("Data quality"):
    schema = data["schema"]
    derive_report = data["derive_metrics_report"]
    st.markdown(f"**{data['source_row_count']:,} rows** loaded, **{len(schema['columns_present'])}/{len(schema['columns_present']) + len(schema['columns_missing'])}** expected columns present.")
    if schema["columns_missing"]:
        st.markdown(f"- Missing expected columns: `{', '.join(schema['columns_missing'])}`")
    st.markdown(f"- {derive_report['duplicate_rows_dropped']} exact duplicate row(s) excluded from all analysis.")
    st.markdown(
        f"- {derive_report['rows_excluded_from_timing_analysis']} row(s) "
        f"({derive_report['rows_excluded_from_timing_analysis'] / derive_report['rows_after_dedup'] * 100:.3f}%) "
        "excluded from delay-distribution analysis only (invalid timestamp ordering or an implausible "
        f"total duration >{240:.0f} min) -- these rows are still counted in funnel, cancellation, and "
        "reassignment statistics, just not in delay percentiles/histograms."
    )
    for col, pct_key in [("accept_time", "accept_time"), ("pickup_time", "pickup_time"), ("delivered_time", "delivered_time")]:
        pct = schema["null_pct"].get(pct_key)
        if pct is not None and pct > 0:
            st.markdown(f"- `{col}` missing for {pct:.2f}% of rows (expected: these orders were cancelled before reaching that stage).")

# =============================================================================
# 2. OPERATIONAL FUNNEL
# =============================================================================
st.divider()
st.subheader("Operational funnel")
st.caption("Order placed → Allotted → Accepted → Picked up → Delivered")

funnel = insights["funnel"]
fig = go.Figure(
    go.Funnel(
        y=[s["stage"] for s in funnel],
        x=[s["count"] for s in funnel],
        textposition="inside",
        textinfo="value+percent initial",
        marker={"color": COLORWAY[: len(funnel)]},
    )
)
fig.update_layout(template=TEMPLATE, height=360, margin=dict(t=10, b=10))
st.plotly_chart(fig, width="stretch")

funnel_cols = st.columns(len(funnel))
for col, stage in zip(funnel_cols, funnel):
    with col:
        st.metric(
            f"{stage['stage']} (of prior)",
            f"{stage['conversion_from_previous_pct']:.1f}%",
            help=f"Median {stage['median_min_from_order']} min / P90 {stage['p90_min_from_order']} min from order creation to this stage.",
        )

# =============================================================================
# 3. WHERE DOES TIME GO? (delay diagnostics)
# =============================================================================
st.divider()
st.subheader("Where does time go?")
st.caption("Delay per operational stage, restricted to rows with valid timestamp ordering and a plausible total duration (see Data quality above).")

delays = insights["delay_diagnostics"]
stage_labels = list(delays.keys())
fig2 = go.Figure()
for pct_key, name in [("median", "Median"), ("p75", "P75"), ("p90", "P90")]:
    fig2.add_trace(go.Bar(name=name, x=stage_labels, y=[delays[s][pct_key] for s in stage_labels]))
fig2.update_layout(template=TEMPLATE, barmode="group", yaxis_title="Minutes", height=380, margin=dict(t=10, b=10), colorway=COLORWAY)
st.plotly_chart(fig2, width="stretch")

with st.expander("Advanced: per-stage distribution"):
    stage_pick = st.selectbox("Stage", stage_labels)
    hist = delays[stage_pick]["histogram"]
    if hist:
        fig3 = go.Figure(go.Bar(x=[f"{b['bin_start']}-{b['bin_end']}" for b in hist], y=[b["count"] for b in hist], marker_color=BLUE))
        fig3.update_layout(template=TEMPLATE, xaxis_title="Minutes", yaxis_title="Orders", height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig3, width="stretch")
    st.caption(f"n={delays[stage_pick]['n']:,} valid rows -- median {delays[stage_pick]['median']} min, P75 {delays[stage_pick]['p75']} min, P90 {delays[stage_pick]['p90']} min.")

# =============================================================================
# 4. REASSIGNMENT ANALYSIS
# =============================================================================
st.divider()
st.subheader("Reassignment analysis")
st.caption(
    f"{reassignment['reassignment_rate'] * 100:.1f}% of orders were reassigned "
    f"({', '.join(f'{k}: {v}' for k, v in reassignment['methods'].items())})."
)

r, nr = reassignment["reassigned"], reassignment["not_reassigned"]
metrics_compared = [
    ("Order → delivery (P90)", "end_to_end_p90_min", "min"),
    ("Acceptance delay (median)", "acceptance_delay_median_min", "min"),
    ("Pickup delay (median)", "pickup_delay_median_min", "min"),
    ("Last-mile time (median)", "last_mile_median_min", "min"),
    ("Cancellation rate", "cancellation_rate", "rate"),
]
fig4 = go.Figure()
labels_x = [m[0] for m in metrics_compared]
r_vals = [r[m[1]] * 100 if m[2] == "rate" else r[m[1]] for m in metrics_compared]
nr_vals = [nr[m[1]] * 100 if m[2] == "rate" else nr[m[1]] for m in metrics_compared]
fig4.add_trace(go.Bar(name="Reassigned", x=labels_x, y=r_vals, marker_color=AMBER))
fig4.add_trace(go.Bar(name="Not reassigned", x=labels_x, y=nr_vals, marker_color=BLUE))
fig4.update_layout(template=TEMPLATE, barmode="group", height=380, margin=dict(t=10, b=10), yaxis_title="Minutes (rate metric shown as %)")
st.plotly_chart(fig4, width="stretch")
st.caption(
    f"Reassigned orders (n={r['n_orders']:,}) were **associated with** a higher cancellation rate "
    f"({r['cancellation_rate'] * 100:.2f}% vs. {nr['cancellation_rate'] * 100:.2f}% for non-reassigned orders, "
    f"n={nr['n_orders']:,}) -- an association, not a demonstrated causal effect of reassignment itself."
)

if reassignment["top_reasons"]:
    with st.expander("Top reassignment reasons"):
        for reason, count in reassignment["top_reasons"].items():
            st.markdown(f"- {reason} -- {count:,} orders")

# =============================================================================
# 5. DISTANCE & EXPERIENCE
# =============================================================================
st.divider()
st.subheader("Distance & experience")

dist = insights["distance"]
d1, d2 = st.columns(2)
with d1:
    st.markdown("**First-mile distance**")
    fm = dist.get("first_mile_distance_buckets", [])
    if fm:
        fig5 = go.Figure()
        fig5.add_trace(go.Bar(x=[b["bucket"] for b in fm], y=[b["end_to_end_median_min"] for b in fm], name="Median end-to-end (min)", marker_color=BLUE))
        fig5.update_layout(template=TEMPLATE, height=320, margin=dict(t=10, b=10), yaxis_title="Minutes")
        st.plotly_chart(fig5, width="stretch")
with d2:
    st.markdown("**Last-mile distance**")
    lm = dist.get("last_mile_distance_buckets", [])
    if lm:
        fig6 = go.Figure()
        fig6.add_trace(go.Bar(x=[b["bucket"] for b in lm], y=[b["end_to_end_median_min"] for b in lm], name="Median end-to-end (min)", marker_color=AMBER))
        fig6.update_layout(template=TEMPLATE, height=320, margin=dict(t=10, b=10), yaxis_title="Minutes")
        st.plotly_chart(fig6, width="stretch")

segments = insights["rider_segments"]
if segments:
    st.markdown("**Rider experience segments** (anonymized -- tertiled by lifetime order count across riders, no rider identity shown)")
    seg_order = {"Low experience": 0, "Medium experience": 1, "High experience": 2}
    segments_sorted = sorted(segments, key=lambda s: seg_order.get(s["segment"], 99))
    seg_cols = st.columns(len(segments_sorted))
    for col, seg in zip(seg_cols, segments_sorted):
        with col:
            st.metric(seg["segment"], f"{seg['n_riders']:,} riders", help=f"{seg['n_orders']:,} orders")
            st.caption(
                f"End-to-end median: {seg['end_to_end_median_min']} min  \n"
                f"Reassignment rate: {seg['reassignment_rate'] * 100:.1f}%  \n"
                f"Cancellation rate: {seg['cancellation_rate'] * 100:.2f}%"
            )

# =============================================================================
# 6. SIMULATOR CALIBRATION
# =============================================================================
st.divider()
st.subheader("Simulator calibration")
st.info(
    "**Domain caveat:** the simulator models ride-hailing (rider + car); this dataset is food "
    "delivery (customer + delivery partner). Stages are conceptually analogous (request → "
    "assignment → pickup → completion) but this is not the same business. Treat the table "
    "below as a directional calibration signal, not a claim the two systems should match exactly. "
    "This is informational only -- no simulator parameter is changed automatically."
)

calib = data.get("calibration", [])
sim_baseline = data.get("simulator_baseline")
if not calib or not sim_baseline:
    st.caption("Simulator baseline (results/results.csv) not available -- calibration comparison skipped.")
else:
    st.caption(f"Simulator baseline used: `{sim_baseline['policy_label']}`, {sim_baseline['scenario']} scenario.")
    rows = []
    for row in calib:
        rows.append(
            {
                "Metric": row["metric"],
                "Real data": f"{row['real_value']:.2f} {row['unit']}" if row["real_value"] is not None else "n/a",
                "Simulator": f"{row['simulator_value']:.2f} {row['unit']}" if row["simulator_value"] is not None else "n/a",
                "Difference": f"{row['difference']:+.2f} {row['unit']}" if row["difference"] is not None else "n/a",
                "Status": f"{STATUS_ICON[row['status']]} {STATUS_LABEL[row['status']]}",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
    with st.expander("Notes on each comparison"):
        for row in calib:
            st.markdown(f"- **{row['metric']}**: {row['note']}")
    st.caption(
        "**Suggested calibration** (recommendation only, not applied automatically): rows marked "
        "🔴 or 🟡 above are candidates for revisiting the simulator's demand/cancellation/patience "
        "parameters if closer real-world alignment is a goal -- see docs/ASSUMPTIONS.md for where "
        "those parameters live."
    )

# =============================================================================
# 7. POLICY OPPORTUNITY AREAS
# =============================================================================
st.divider()
st.subheader("Policy opportunity areas")
st.caption("Each item below is a **hypothesis** generated from observed data, not a proven solution.")

opportunities = insights["opportunities"]
for op in opportunities:
    with st.expander(f"{op['problem']}", expanded=False):
        st.markdown(f"**Observation**  \n{op['observation']}")
        st.markdown(f"**Hypothesis**  \n{op['hypothesis']}")
        st.markdown(f"**Metric to optimize**  \n{op['metric_to_optimize']}")
        st.markdown(f"**Risks / guardrails**  \n{op['risks_guardrails']}")
        if op["candidate_methods"]:
            st.markdown(f"**Candidate methods to test**  \n" + ", ".join(f"`{m}`" for m in op["candidate_methods"]))
        st.markdown(f"**Simulator test**  \n{op['simulator_test']}")

# =============================================================================
# 8. WHAT SHOULD WE TEST NEXT?
# =============================================================================
st.divider()
st.subheader("What should we test next?")
st.caption("Top opportunities, ranked by observed effect size within this dataset.")

top = [o for o in opportunities if o.get("priority_score", 0) > 0][:5]
for i, op in enumerate(top, start=1):
    st.markdown(f"**{i}. {op['problem']}**")
    st.markdown(
        f"- Evidence: {op['observation']}\n"
        f"- Hypothesis: {op['hypothesis']}\n"
        f"- Primary metric: {op['metric_to_optimize']}\n"
        f"- Guardrails: {op['risks_guardrails']}\n"
        f"- Recommended validation: {op['simulator_test']}"
    )

# =============================================================================
# 9. LIMITATIONS
# =============================================================================
st.divider()
st.subheader("Limitations")
st.markdown(
    "This dataset does not necessarily contain: live rider/partner locations, restaurant "
    "preparation time, the complete candidate-driver set considered at assignment time, quoted "
    "pricing or incentives, traffic conditions, weather, or full real-time supply state.\n\n"
    "**The analysis above supports operational diagnosis and hypothesis generation, not "
    "reconstruction of a proprietary production dispatch algorithm.** That is a scope choice, not "
    "a weakness -- the goal of this page is to motivate what to test in the existing simulator, "
    "not to replace it or to make production performance claims.\n\n"
    "Every relationship described above is an **association observed in this dataset**, not a "
    "demonstrated causal effect -- no experiment or randomized design was run against this data. "
    "Treat every hypothesis on this page as something to validate, in the simulator or otherwise, "
    "before acting on it."
)
