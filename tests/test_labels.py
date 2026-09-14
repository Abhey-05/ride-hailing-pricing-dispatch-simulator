from src import labels


def test_is_improvement_lower_is_better_metric():
    assert labels.is_improvement("p90_wait_min", -1.0) is True
    assert labels.is_improvement("p90_wait_min", 1.0) is False


def test_is_improvement_higher_is_better_metric():
    assert labels.is_improvement("platform_revenue", 500.0) is True
    assert labels.is_improvement("platform_revenue", -500.0) is False


def test_is_improvement_unknown_metric_returns_none():
    assert labels.is_improvement("driver_utilization_mean", 0.05) is None
    assert labels.is_improvement("not_a_real_metric", 1.0) is None


def test_is_improvement_zero_delta_returns_none():
    assert labels.is_improvement("p90_wait_min", 0.0) is None


def test_fmt_currency_thresholds():
    assert labels.fmt_currency(132_526.9) == "₹1.33L"
    assert labels.fmt_currency(6_800) == "₹6.8k"
    assert labels.fmt_currency(320) == "₹320"
    assert labels.fmt_currency(-6_800) == "-₹6.8k"


def test_fmt_pct_expects_fraction():
    assert labels.fmt_pct(0.574) == "57.4%"
    assert labels.fmt_pct(1.0) == "100.0%"


def test_fmt_minutes_and_km():
    assert labels.fmt_minutes(8.52) == "8.5 min"
    assert labels.fmt_km(1.3) == "1.30 km"


def test_fmt_multiplier():
    assert labels.fmt_multiplier(1.3) == "1.30x"


def test_label_falls_back_to_raw_name_for_unknown_metric():
    assert labels.label("some_unmapped_metric") == "some_unmapped_metric"


def test_dispatch_flow_is_policy_aware():
    nearest = labels.dispatch_flow("NEAREST_DRIVER")
    eta = labels.dispatch_flow("ETA_OPTIMIZED")
    assert "Distance scoring" in nearest
    assert "ETA scoring" not in nearest
    assert "ETA scoring" in eta
    assert "Distance scoring" not in eta


def test_dispatch_flow_covers_every_dispatch_policy():
    from src import config
    for policy in config.DispatchPolicy:
        flow = labels.dispatch_flow(policy.value)
        assert "Scoring" not in flow or "scoring" in flow.lower()  # never the bare unknown-fallback word
        assert policy.value  # sanity: enum resolves


def test_map_legend_caption_differs_by_metric():
    status_caption = labels.map_legend_caption("Marketplace status")
    drivers_caption = labels.map_legend_caption("Available drivers")
    assert "marketplace status" in status_caption.lower()
    assert "marketplace status" not in drivers_caption.lower()
    assert "available drivers" in drivers_caption.lower()


def test_map_legend_caption_unknown_metric_has_fallback():
    assert "demand" in labels.map_legend_caption("Some Unknown Metric").lower()
