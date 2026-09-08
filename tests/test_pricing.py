from src import config
from src.pricing import PricingEngine, base_fare


def test_no_surge_always_one():
    eng = PricingEngine(config.PricingPolicy.NO_SURGE)
    for imbalance in [0, 1, 5, 100]:
        assert eng.surge_for_zone(0, 0, imbalance) == 1.0


def test_surge_never_exceeds_cap():
    for policy in config.PricingPolicy:
        eng = PricingEngine(policy)
        cap = config.PRICING_PARAMS[policy].get("max_surge", 1.0)
        floor = config.PRICING_PARAMS[policy].get("min_surge", 1.0)
        for tick in range(0, 200):
            surge = eng.surge_for_zone(0, tick, imbalance=1000.0)  # extreme imbalance
            assert surge <= cap + 1e-9, f"{policy} exceeded cap: {surge} > {cap}"
            assert surge >= floor - 1e-9


def test_surge_at_zero_imbalance_is_floor():
    for policy in [config.PricingPolicy.BASIC_SURGE, config.PricingPolicy.AGGRESSIVE_SURGE]:
        eng = PricingEngine(policy)
        surge = eng.surge_for_zone(0, 0, imbalance=0.0)
        assert surge >= config.PRICING_PARAMS[policy]["min_surge"]


def test_base_fare_non_negative_and_monotonic():
    f1 = base_fare(distance_km=1.0, duration_min=2.0)
    f2 = base_fare(distance_km=5.0, duration_min=10.0)
    assert f1 > 0
    assert f2 > f1  # more distance/time -> higher fare


def test_smoothed_surge_reduces_flicker():
    """CAPPED_SMOOTHED_SURGE should move less tick-to-tick than AGGRESSIVE_SURGE
    under the same oscillating imbalance signal."""
    smoothed = PricingEngine(config.PricingPolicy.CAPPED_SMOOTHED_SURGE)
    aggressive = PricingEngine(config.PricingPolicy.AGGRESSIVE_SURGE)
    imbalances = [0.2, 5.0, 0.2, 5.0, 0.2, 5.0] * 5
    smoothed_vals, aggressive_vals = [], []
    for t, imb in enumerate(imbalances):
        smoothed_vals.append(smoothed.surge_for_zone(0, t, imb))
        aggressive_vals.append(aggressive.surge_for_zone(0, t, imb))

    def total_variation(vals):
        return sum(abs(vals[i] - vals[i - 1]) for i in range(1, len(vals)))

    assert total_variation(smoothed_vals) < total_variation(aggressive_vals)
