"""
Rider and driver behavioral probability functions.
MATHEMATICAL_MODEL.md Sections C (rider acceptance), D (cancellation), E.2 (driver acceptance).

All probabilities are logistic-shaped and bounded by construction -- no
manual clipping should ever be necessary; that itself is a documented
internal-consistency check (see MATHEMATICAL_MODEL.md, final section).
"""
from __future__ import annotations

import math

from src import config


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def rider_accept_probability(beta_price: float, beta_wait: float, surge_multiplier: float, expected_wait_min: float) -> float:
    z = (
        config.ACCEPT_BETA0
        - beta_price * (surge_multiplier - 1.0)
        - beta_wait * (expected_wait_min / config.WAIT_REFERENCE_MIN)
    )
    return sigmoid(z)


def pre_match_abandon_probability(elapsed_wait_min: float, patience_min: float) -> float:
    x = config.CANCEL_K_PRE * (elapsed_wait_min - patience_min) / patience_min
    return config.CANCEL_P_MAX_PRE * sigmoid(x)


def post_match_cancel_probability(elapsed_since_match_min: float, patience_min: float) -> float:
    post_patience = patience_min * config.CANCEL_POSTMATCH_PATIENCE_DISCOUNT
    x = config.CANCEL_K_POST * (elapsed_since_match_min - post_patience) / post_patience
    return config.CANCEL_P_MAX_POST * sigmoid(x)


def destination_attractiveness(dest_zone: int, outstanding_by_zone: dict[int, int], avg_outstanding: float) -> float:
    if avg_outstanding <= 0:
        return 0.5
    val = outstanding_by_zone.get(dest_zone, 0) / (avg_outstanding + 1.0)
    return min(1.0, val)


def driver_accept_probability(
    fare_driver_share: float,
    avg_fare_driver_share: float,
    pickup_eta_min: float,
    avg_pickup_eta_min: float,
    dest_attractiveness: float,
    utilization: float,
) -> float:
    fare_norm = fare_driver_share / avg_fare_driver_share if avg_fare_driver_share > 0 else 1.0
    eta_norm = pickup_eta_min / avg_pickup_eta_min if avg_pickup_eta_min > 0 else 1.0
    score = (
        config.DRIVER_ACCEPT_GAMMA_FARE * fare_norm
        - config.DRIVER_ACCEPT_GAMMA_PICKUP * eta_norm
        + config.DRIVER_ACCEPT_GAMMA_DEST * dest_attractiveness
        - config.DRIVER_ACCEPT_GAMMA_UTIL * utilization
    )
    return sigmoid(config.DRIVER_ACCEPT_GAMMA0 + score)
