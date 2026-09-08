#!/usr/bin/env python3
"""Generates presentation/project_presentation.pptx from actual project
content and real chart images in reports/figures/."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

ROOT = Path(__file__).parent
FIG_DIR = ROOT / "reports" / "figures"
OUT = ROOT / "presentation" / "project_presentation.pptx"

NAVY = RGBColor(0x1A, 0x22, 0x3D)
ACCENT = RGBColor(0x2E, 0xA0, 0x6D)
GREY = RGBColor(0x55, 0x55, 0x55)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(BLANK)


def add_text(slide, left, top, width, height, text, size=18, bold=False, color=NAVY, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    first = True
    for line in text.split("\n"):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.text = line
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color
        p.alignment = align
    return box


def add_bullets(slide, left, top, width, height, items, size=16, color=NAVY):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"•  {item}"
        p.font.size = Pt(size)
        p.font.color.rgb = color
        p.space_after = Pt(10)
    return box


def bg(slide, color=WHITE):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def header_bar(slide, title, subtitle=None):
    bg(slide)
    rect = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(1.1))
    rect.fill.solid()
    rect.fill.fore_color.rgb = NAVY
    rect.line.fill.background()
    add_text(slide, 0.5, 0.18, 12.3, 0.6, title, size=28, bold=True, color=WHITE)
    if subtitle:
        add_text(slide, 0.5, 0.68, 12.3, 0.4, subtitle, size=14, color=RGBColor(0xC8, 0xD0, 0xE8))


def add_pic(slide, path, left, top, width):
    if path.exists():
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(width))


# 1. Title
s = add_slide()
bg(s, NAVY)
add_text(s, 1, 2.3, 11.3, 1.2, "Ride-Hailing Surge Pricing & Dispatch Simulator", size=40, bold=True, color=WHITE)
add_text(s, 1, 3.5, 11.3, 0.8, "A marketplace experimentation platform for pricing and dispatch trade-offs", size=18, color=RGBColor(0xC8, 0xD0, 0xE8))
add_text(s, 1, 6.6, 11.3, 0.5, "All results are from synthetic simulation — see docs/ASSUMPTIONS.md", size=12, color=RGBColor(0x9A, 0xA6, 0xC8))

# 2. Problem
s = add_slide()
header_bar(s, "The Problem", "A two-sided marketplace balancing rider experience, driver earnings, and revenue")
add_bullets(s, 0.6, 1.4, 7.5, 5, [
    "Riders want low price + short wait. Drivers want steady, well-paid work.",
    "When demand > supply, riders wait longer and some cancel; when supply > demand, driver-hours go to waste.",
    "Platforms have three levers to close the gap: surge pricing, driver incentives, dispatch quality.",
    "The first two show up immediately in a P&L. Dispatch is a software investment that's hard to justify without a controlled experiment.",
])
add_text(s, 8.3, 1.6, 4.4, 4, "“Can dispatch reduce wait time without raising cost?”", size=20, bold=True, color=ACCENT)

# 3. Marketplace dynamics
s = add_slide()
header_bar(s, "Marketplace Dynamics", "10-zone synthetic city, Poisson demand, time-of-day patterns")
add_bullets(s, 0.6, 1.4, 12, 5, [
    "10 zones (Downtown, Airport, University, Residential x2, Suburban x2, Transit Hub, Nightlife, Business Park), each with a distinct demand curve and directional flow pattern.",
    "Ride requests: Poisson arrivals per zone per minute, rate driven by time-of-day and scenario.",
    "Riders: 3 segments (price-sensitive / normal / time-sensitive), logistic accept/cancel functions.",
    "Drivers: shift-based online/offline, logistic accept function driven by pay, pickup distance, and current utilization.",
])

# 4. Simulation architecture
s = add_slide()
header_bar(s, "Simulation Architecture", "Time-stepped, 1-minute ticks, 24 simulated hours")
add_bullets(s, 0.6, 1.4, 12, 5.5, [
    "12-step fixed sequence per tick: demand -> driver states -> marketplace state -> surge -> pricing -> rider accept/reject -> dispatch -> driver accept/reject -> trip advance -> cancellations -> metrics.",
    "Common Random Numbers: the same simulated riders/drivers/timing replay identically across every policy at a given seed -- turns policy comparison into a precise paired experiment.",
    "Reproducible: numpy.random.SeedSequence-derived streams (never Python's hash()), verified via bit-identical repeat-run tests.",
    "~0.3s per 24-hour simulation -- the full 1,080-run experiment matrix completes in under 6 minutes.",
])

# 5. Pricing strategies
s = add_slide()
header_bar(s, "Pricing Strategies", "4 policies, capped, tested against a no-surge control")
add_bullets(s, 0.6, 1.4, 6, 5, [
    "NO_SURGE — control",
    "BASIC_SURGE — proportional to imbalance, capped 1.0-2.0x",
    "AGGRESSIVE_SURGE — higher gain, capped 1.0-3.0x, updates every minute",
    "CAPPED_SMOOTHED_SURGE — same signal, exponentially smoothed, capped 1.0-2.5x",
])
add_pic(s, FIG_DIR / "03_pricing_vs_revenue.png", 6.9, 1.3, 6.0)

# 6. Dispatch strategies
s = add_slide()
header_bar(s, "Dispatch Strategies", "5 heuristics — explicitly not a global optimum")
add_bullets(s, 0.6, 1.4, 12, 3.2, [
    "NEAREST_DRIVER — minimize pickup distance among idle drivers",
    "ETA_OPTIMIZED — minimize predicted pickup time, incl. drivers about to free up nearby",
    "DRIVER_EARNINGS_AWARE — among nearest candidates, maximize predicted driver-acceptance probability",
    "MARKETPLACE_AWARE — penalize pulling a driver out of an undersupplied zone",
    "ADVANCED_HEURISTIC — weighted combination of all of the above + cancellation-risk urgency",
])
add_text(s, 0.6, 4.9, 12, 1.5,
         "Why not the exact optimal assignment? O((R+D)^3) per tick via the Hungarian algorithm doesn't scale, "
         "and the state is stale again a minute later anyway — a deliberate optimality-vs-speed trade-off.",
         size=14, color=GREY)

# 7. Experiment design
s = add_slide()
header_bar(s, "Experiment Design", "1,080 runs, statistically powered, not just 'ran it a lot'")
add_bullets(s, 0.6, 1.4, 12, 5, [
    "Core: 4 pricing x 5 dispatch x 24 common-random-number seeds = 480 runs (NORMAL scenario) — prioritizes statistical power on the primary comparison.",
    "Robustness: same 20 combos x 6 seeds x 5 stress scenarios (peak, shortage, shock, low-demand, congested-peak) = 600 runs.",
    "Sensitivity: 6 parameters x +/-30% x 8 seeds = 224 further runs.",
    "Primary metric: P90 rider wait. Guardrails: cancellation rate, driver earnings/hour, driver acceptance rate, price index.",
    "Statistics: bootstrap 95% CI, paired Wilcoxon test, matched-pairs Cohen's d, pre-registered >=5% practical-significance bar.",
])

# 8. Results
s = add_slide()
header_bar(s, "Results", "ETA_OPTIMIZED wins on every metric, every pricing policy")
add_pic(s, FIG_DIR / "10_confidence_intervals.png", 0.4, 1.25, 7.0)
add_bullets(s, 7.6, 1.5, 5.3, 5, [
    "P90 wait: -8.9% (BASIC_SURGE), -7.8% to -11.3% across all 4 pricing policies",
    "Driver earnings/online-hour: +1.9%",
    "Cancellation rate: -4.7% (relative)",
    "Platform revenue: +2.7%",
    "All p < 0.001, n=24 paired seeds",
    "Sign survives all 12 sensitivity perturbations",
])

# 9. Key insight
s = add_slide()
bg(s, NAVY)
add_text(s, 1, 1.3, 11.3, 1, "Key Insight", size=32, bold=True, color=WHITE)
add_text(s, 1, 2.6, 11.3, 2.5,
         "Dispatch is the only lever tested that improved rider experience,\ndriver earnings, AND platform revenue simultaneously —\nat zero incremental marginal cost per ride.",
         size=24, bold=True, color=ACCENT)
add_text(s, 1, 5.3, 11.3, 1.3,
         "A more “sophisticated” hand-tuned heuristic combining more objectives actually performed\nWORSE than the naive baseline — a real, reported negative finding, not hidden.",
         size=16, color=RGBColor(0xC8, 0xD0, 0xE8))

# 10. Product recommendation
s = add_slide()
header_bar(s, "Product Recommendation", "Decision matrix: surge vs. incentives vs. dispatch")
add_bullets(s, 0.6, 1.4, 12, 3.0, [
    "LAUNCH: ETA_OPTIMIZED-style dispatch, in shadow mode first, then phased 1% -> 5% -> 25% -> 100%.",
    "DO NOT LAUNCH: ADVANCED_HEURISTIC — underperformed baseline in every configuration tested.",
    "TEST NEXT: sensitivity analysis (done) + a real production shadow-mode test of the core mechanism.",
])
add_text(s, 0.6, 4.6, 12, 1.6,
         "Real-world data that would sharpen this: actual rider price-sensitivity/cancellation curves, "
         "driver pickup-acceptance logs, and driver-supply-vs-incentive elasticity estimates.",
         size=14, color=GREY)

# 11. Technical architecture / AI
s = add_slide()
header_bar(s, "Technical Architecture & AI", "Engine -> results warehouse -> dashboard / API / AI copilot")
add_bullets(s, 0.6, 1.4, 12, 5, [
    "Engine (Python) -> file-based results warehouse (Parquet/CSV) -> statistical analysis layer",
    "Streamlit + Plotly dashboard for live simulation and experiment browsing",
    "FastAPI service exposing simulation + results (with full Postgres schema specified for production scale)",
    "AI Marketplace Analyst: Claude tool-calling over 5 deterministic functions — the LLM never computes a metric itself, only explains numbers a real function call returned",
])

# 12. Future roadmap
s = add_slide()
header_bar(s, "Future Roadmap", "What's next, prioritized")
add_bullets(s, 0.6, 1.4, 12, 5, [
    "1. Driver supply-response-to-incentive model (biggest remaining gap)",
    "2. 24-seed robustness scenarios (currently 6)",
    "3. Combined (not one-at-a-time) worst-case sensitivity perturbations",
    "4. Live end-to-end test of the AI copilot against a real API key",
    "5. Per-zone fairness/equity guardrails (e.g. driver-earnings Gini coefficient)",
    "6. A real production shadow-mode A/B test of the dispatch mechanism",
])

OUT.parent.mkdir(exist_ok=True)
prs.save(OUT)
print(f"Saved {OUT}")
