from src import behavior


def test_probabilities_bounded():
    for surge in [1.0, 1.5, 2.0, 3.0]:
        for wait in [0, 5, 20, 100]:
            p = behavior.rider_accept_probability(1.1, 0.8, surge, wait)
            assert 0.0 <= p <= 1.0

    for w in [0, 1, 5, 10, 50, 1000]:
        p = behavior.pre_match_abandon_probability(w, patience_min=6.0)
        assert 0.0 <= p <= behavior.config.CANCEL_P_MAX_PRE + 1e-9

    for w in [0, 1, 5, 10, 50, 1000]:
        p = behavior.post_match_cancel_probability(w, patience_min=6.0)
        assert 0.0 <= p <= behavior.config.CANCEL_P_MAX_POST + 1e-9

    p = behavior.driver_accept_probability(100, 100, 5, 6, 0.5, 0.5)
    assert 0.0 <= p <= 1.0


def test_higher_surge_reduces_acceptance():
    p_low = behavior.rider_accept_probability(1.1, 0.8, surge_multiplier=1.0, expected_wait_min=5.0)
    p_high = behavior.rider_accept_probability(1.1, 0.8, surge_multiplier=2.5, expected_wait_min=5.0)
    assert p_high < p_low


def test_longer_wait_increases_cancellation():
    p_short = behavior.pre_match_abandon_probability(1.0, patience_min=6.0)
    p_long = behavior.pre_match_abandon_probability(20.0, patience_min=6.0)
    assert p_long > p_short


def test_cancellation_monotonic_in_wait():
    patience = 6.0
    waits = [0, 1, 2, 3, 5, 8, 12, 20, 40]
    probs = [behavior.pre_match_abandon_probability(w, patience) for w in waits]
    assert all(probs[i] <= probs[i + 1] for i in range(len(probs) - 1))


def test_longer_pickup_reduces_driver_acceptance():
    p_short = behavior.driver_accept_probability(100, 100, pickup_eta_min=3, avg_pickup_eta_min=6, dest_attractiveness=0.5, utilization=0.5)
    p_long = behavior.driver_accept_probability(100, 100, pickup_eta_min=30, avg_pickup_eta_min=6, dest_attractiveness=0.5, utilization=0.5)
    assert p_long < p_short


def test_higher_fare_increases_driver_acceptance():
    p_low_fare = behavior.driver_accept_probability(50, 100, pickup_eta_min=6, avg_pickup_eta_min=6, dest_attractiveness=0.5, utilization=0.5)
    p_high_fare = behavior.driver_accept_probability(200, 100, pickup_eta_min=6, avg_pickup_eta_min=6, dest_attractiveness=0.5, utilization=0.5)
    assert p_high_fare > p_low_fare
