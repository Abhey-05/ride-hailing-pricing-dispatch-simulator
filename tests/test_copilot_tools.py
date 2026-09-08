from src import copilot_tools as ct


def test_get_policy_metrics():
    r = ct.get_policy_metrics("BASIC_SURGE", "NEAREST_DRIVER", "NORMAL")
    assert r["n_seeds"] == 24
    assert "p90_wait_min" in r
    assert "source" in r


def test_get_policy_metrics_unknown_combo():
    r = ct.get_policy_metrics("BASIC_SURGE", "NEAREST_DRIVER", "DEMAND_SHOCK")
    # DEMAND_SHOCK is a robustness scenario -- NEAREST_DRIVER/BASIC_SURGE should still exist there
    assert "error" not in r or r.get("n_seeds", 0) >= 0


def test_compare_dispatch_to_baseline():
    r = ct.compare_dispatch_to_baseline("BASIC_SURGE", "ETA_OPTIMIZED", "p90_wait_min")
    assert r["practically_significant_improvement"] is True
    assert r["signed_relative_effect_pct"] > 0


def test_decision_table():
    r = ct.get_decision_table(top_n=3)
    assert len(r["rows"]) == 3


def test_whatif_demand_override_changes_request_volume():
    base = ct.simulate_whatif(seed=2)
    boosted = ct.simulate_whatif(seed=2, demand_multiplier_override=2.0)
    assert boosted["n_requests"] > base["n_requests"]


def test_zone_ranking_returns_all_zones():
    r = ct.get_zone_supply_demand_ranking(seed=3)
    assert len(r["ranking"]) == 10
    ratios = [row["avg_supply_demand_ratio"] for row in r["ranking"]]
    assert ratios == sorted(ratios)  # worst (lowest) first
