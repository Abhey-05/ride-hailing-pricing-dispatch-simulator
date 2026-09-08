"""
Centralized configuration for the ride-hailing simulator.

Every numeric parameter used anywhere in the engine lives here so that
experiments are reproducible from a single source of truth. Values are
documented in detail in docs/ASSUMPTIONS.md and docs/MATHEMATICAL_MODEL.md
-- this file must stay in sync with those documents.

All values are SYNTHETIC ASSUMPTIONS unless otherwise noted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Time model
# ---------------------------------------------------------------------------
TICK_MINUTES = 1
DEFAULT_HORIZON_TICKS = 24 * 60  # 24 simulated hours


# ---------------------------------------------------------------------------
# Zones (city model) -- docs/ASSUMPTIONS.md "Zone Model"
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Zone:
    id: int
    name: str
    archetype: str
    x: float
    y: float
    lambda_base: float  # baseline requests/hour
    driver_share: float  # fraction of fleet starting near this zone


ZONES: list[Zone] = [
    Zone(0, "Downtown", "commercial", 5, 5, 40, 0.18),
    Zone(1, "Airport", "airport", 9, 1, 22, 0.08),
    Zone(2, "University", "university", 2, 7, 26, 0.09),
    Zone(3, "Residential North", "residential", 3, 9, 30, 0.13),
    Zone(4, "Residential South", "residential", 3, 1, 28, 0.12),
    Zone(5, "Suburban East", "suburban", 9, 6, 14, 0.08),
    Zone(6, "Suburban West", "suburban", 1, 4, 14, 0.08),
    Zone(7, "Transit Hub", "transit_hub", 6, 8, 24, 0.08),
    Zone(8, "Nightlife District", "nightlife", 7, 3, 20, 0.08),
    Zone(9, "Business Park", "commercial", 6, 2, 26, 0.08),
]
NUM_ZONES = len(ZONES)
GRID_SCALE_KM = 1.2
MIN_INTRAZONE_DISTANCE_KM = 0.8

# Time-of-day periods: (start_hour, end_hour, midpoint_hour)
TOD_PERIODS = [
    ("late_night", 0.0, 5.0),
    ("morning_ramp", 5.0, 7.0),
    ("morning_peak", 7.0, 10.0),
    ("midday", 10.0, 16.0),
    ("evening_peak", 16.0, 19.0),
    ("evening_wind_down", 19.0, 22.0),
    ("night", 22.0, 24.0),
]

# archetype -> {period_name: multiplier}
ARCHETYPE_TOD_MULTIPLIER = {
    "commercial": {
        "late_night": 0.2, "morning_ramp": 0.6, "morning_peak": 1.9,
        "midday": 1.1, "evening_peak": 1.7, "evening_wind_down": 0.9, "night": 0.4,
    },
    "airport": {
        "late_night": 0.5, "morning_ramp": 0.8, "morning_peak": 1.1,
        "midday": 1.3, "evening_peak": 1.2, "evening_wind_down": 1.0, "night": 0.7,
    },
    "university": {
        "late_night": 0.3, "morning_ramp": 0.5, "morning_peak": 1.3,
        "midday": 1.0, "evening_peak": 1.1, "evening_wind_down": 1.4, "night": 0.8,
    },
    "residential": {
        "late_night": 0.2, "morning_ramp": 1.5, "morning_peak": 1.8,
        "midday": 0.7, "evening_peak": 1.6, "evening_wind_down": 1.0, "night": 0.4,
    },
    "suburban": {
        "late_night": 0.15, "morning_ramp": 1.2, "morning_peak": 1.4,
        "midday": 0.6, "evening_peak": 1.3, "evening_wind_down": 0.8, "night": 0.3,
    },
    "transit_hub": {
        "late_night": 0.2, "morning_ramp": 1.6, "morning_peak": 2.0,
        "midday": 0.8, "evening_peak": 1.9, "evening_wind_down": 1.0, "night": 0.3,
    },
    "nightlife": {
        "late_night": 0.6, "morning_ramp": 0.2, "morning_peak": 0.3,
        "midday": 0.6, "evening_peak": 0.9, "evening_wind_down": 1.6, "night": 2.2,
    },
}

CONGESTION_BY_PERIOD = {
    "late_night": 1.0, "morning_ramp": 1.1, "morning_peak": 1.35,
    "midday": 1.1, "evening_peak": 1.35, "evening_wind_down": 1.15, "night": 1.0,
}

# Directional flow bias: origin archetype -> {period: {dest_archetype: weight}}
# Remaining probability mass (to reach 1.0) is spread across all zones
# proportional to their baseline lambda_base, so no zone is ever unreachable.
FLOW_BIAS = {
    "residential": {
        "morning_peak": {"commercial": 0.45, "university": 0.15},
        "evening_peak": {"residential": 0.55},
    },
    "university": {
        "morning_peak": {"commercial": 0.30},
        "evening_peak": {"nightlife": 0.20, "residential": 0.30},
    },
    "transit_hub": {
        "morning_peak": {"commercial": 0.60},
        "evening_peak": {"residential": 0.50},
    },
    "commercial": {
        "evening_peak": {"residential": 0.55, "suburban": 0.20},
    },
}

# ---------------------------------------------------------------------------
# Travel time model
# ---------------------------------------------------------------------------
BASE_SPEED_KMH = 28.0
TRAVEL_NOISE_SIGMA = 0.15  # lognormal sigma, median multiplier = 1.0

# ---------------------------------------------------------------------------
# Rider segments -- docs/MATHEMATICAL_MODEL.md Section C
# ---------------------------------------------------------------------------
class RiderSegment(str, Enum):
    PRICE_SENSITIVE = "price_sensitive"
    NORMAL = "normal"
    TIME_SENSITIVE = "time_sensitive"


RIDER_SEGMENT_SHARE = {
    RiderSegment.PRICE_SENSITIVE: 0.30,
    RiderSegment.NORMAL: 0.50,
    RiderSegment.TIME_SENSITIVE: 0.20,
}

RIDER_SEGMENT_PARAMS = {
    # beta_price, beta_wait, patience_median_min
    RiderSegment.PRICE_SENSITIVE: dict(beta_price=2.2, beta_wait=0.4, patience_median=8.0),
    RiderSegment.NORMAL: dict(beta_price=1.1, beta_wait=0.8, patience_median=6.0),
    RiderSegment.TIME_SENSITIVE: dict(beta_price=0.6, beta_wait=1.5, patience_median=4.0),
}
PATIENCE_LOGNORMAL_SIGMA = 0.4

ACCEPT_BETA0 = 2.2
WAIT_REFERENCE_MIN = 5.0

CANCEL_P_MAX_PRE = 0.35
CANCEL_K_PRE = 3.0
CANCEL_P_MAX_POST = 0.12
CANCEL_K_POST = 3.0
CANCEL_POSTMATCH_PATIENCE_DISCOUNT = 0.6  # phi

# ---------------------------------------------------------------------------
# Driver model -- docs/MATHEMATICAL_MODEL.md Section E
# ---------------------------------------------------------------------------
DEFAULT_FLEET_SIZE = 260
SHIFT_LENGTH_HOURS_CHOICES = [6, 8, 10]
SHIFT_LENGTH_HOURS_WEIGHTS = [0.30, 0.45, 0.25]
SHIFT_START_CLUSTERS_HOURS = [7.0, 15.0, 20.0]
SHIFT_START_CLUSTER_SIGMA = 1.5

DRIVER_ACCEPT_GAMMA0 = 1.5
DRIVER_ACCEPT_GAMMA_FARE = 1.8
DRIVER_ACCEPT_GAMMA_PICKUP = 2.0
DRIVER_ACCEPT_GAMMA_DEST = 0.7
DRIVER_ACCEPT_GAMMA_UTIL = 0.5

# ---------------------------------------------------------------------------
# Pricing model -- docs/MATHEMATICAL_MODEL.md Section G
# ---------------------------------------------------------------------------
BASE_FEE = 40.0
DISTANCE_RATE_PER_KM = 9.0
TIME_RATE_PER_MIN = 1.5
COMMISSION_RATE = 0.25


class PricingPolicy(str, Enum):
    NO_SURGE = "NO_SURGE"
    BASIC_SURGE = "BASIC_SURGE"
    AGGRESSIVE_SURGE = "AGGRESSIVE_SURGE"
    CAPPED_SMOOTHED_SURGE = "CAPPED_SMOOTHED_SURGE"


PRICING_PARAMS = {
    PricingPolicy.NO_SURGE: dict(),
    PricingPolicy.BASIC_SURGE: dict(alpha=0.5, min_surge=1.0, max_surge=2.0, update_every_ticks=5),
    PricingPolicy.AGGRESSIVE_SURGE: dict(alpha=1.0, min_surge=1.0, max_surge=3.0, update_every_ticks=1),
    PricingPolicy.CAPPED_SMOOTHED_SURGE: dict(alpha=0.5, min_surge=1.0, max_surge=2.5, smoothing_lambda=0.2, update_every_ticks=1),
}

# ---------------------------------------------------------------------------
# Dispatch model -- docs/MATHEMATICAL_MODEL.md Section H
# ---------------------------------------------------------------------------
class DispatchPolicy(str, Enum):
    NEAREST_DRIVER = "NEAREST_DRIVER"
    ETA_OPTIMIZED = "ETA_OPTIMIZED"
    DRIVER_EARNINGS_AWARE = "DRIVER_EARNINGS_AWARE"
    MARKETPLACE_AWARE = "MARKETPLACE_AWARE"
    ADVANCED_HEURISTIC = "ADVANCED_HEURISTIC"


DISPATCH_LOOKAHEAD_MIN = 3.0  # H, minutes
DISPATCH_EARNINGS_AWARE_TOPK = 5
MARKETPLACE_AWARE_BETA = 4.0
MARKETPLACE_AWARE_TARGET_RATIO = 1.0

ADVANCED_HEURISTIC_WEIGHTS = dict(
    w_eta=1.0, w_imb=3.0, w_dest=0.5, w_cancel=1.5, target_ratio=1.0,
)

# ---------------------------------------------------------------------------
# Scenarios -- docs/EXPERIMENT_DESIGN.md Section O
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Scenario:
    name: str
    demand_mult: float = 1.0
    supply_mult: float = 1.0
    congestion_mult: float = 1.0
    shock_zone_id: int | None = None
    shock_mult: float = 0.0
    shock_start_hour: float | None = None
    shock_duration_hours: float = 1.5


SCENARIOS = {
    "NORMAL": Scenario("NORMAL"),
    "PEAK_DEMAND": Scenario("PEAK_DEMAND", demand_mult=1.6),
    "SUPPLY_SHORTAGE": Scenario("SUPPLY_SHORTAGE", supply_mult=0.6),
    "DEMAND_SHOCK": Scenario("DEMAND_SHOCK", shock_mult=1.5, shock_duration_hours=1.5),
    "LOW_DEMAND": Scenario("LOW_DEMAND", demand_mult=0.6),
    "CONGESTED_PEAK": Scenario("CONGESTED_PEAK", demand_mult=1.6, congestion_mult=1.35),
}

BASELINE_PRICING = PricingPolicy.BASIC_SURGE
BASELINE_DISPATCH = DispatchPolicy.NEAREST_DRIVER

# ---------------------------------------------------------------------------
# Guardrail tolerance thresholds (relative to baseline) -- EXPERIMENT_DESIGN.md Section X
# ---------------------------------------------------------------------------
GUARDRAIL_TOLERANCE = dict(
    p90_wait_max_ratio=1.00,
    earnings_per_hour_min_ratio=0.98,
    cancellation_rate_max_ratio=1.05,
    revenue_min_ratio=0.98,
)

PRACTICAL_SIGNIFICANCE_RELATIVE_THRESHOLD = 0.05
