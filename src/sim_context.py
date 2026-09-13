"""
Central, single-source-of-truth description of "what simulation are we
looking at right now" -- scenario, pricing policy, dispatch policy, seed,
horizon.

Before this module existed, chart titles and captions across the dashboard
either hardcoded a label (e.g. src/charts.py's old
"Demand & Supply Over a Simulated Day (NORMAL scenario, seed=0)" title, which
was wrong the instant a user picked PEAK_DEMAND in the sidebar) or
reconstructed the label ad hoc in several places that could drift out of
sync. Every chart/caption that needs to say what it's showing should build
its label from a SimulationContext instead of formatting its own string.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationContext:
    scenario: str
    pricing_policy: str
    dispatch_policy: str
    seed: int
    horizon_hours: float = 24.0

    def label(self) -> str:
        return (
            f"{self.scenario} scenario / {self.pricing_policy} / "
            f"{self.dispatch_policy} / seed {self.seed}"
        )

    def short_label(self) -> str:
        return f"{self.pricing_policy} + {self.dispatch_policy}"

    def chart_suffix(self) -> str:
        return f"({self.scenario} scenario, seed={self.seed})"
