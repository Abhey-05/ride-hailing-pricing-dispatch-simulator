"""
ML component: predict whether a rider request will cancel (abandon while
waiting, or cancel after being matched) vs. complete -- and compare against
the rule-based baseline already built into the simulator.

Why this ML use case and not another: cancellation is the single largest
driver of lost bookings in the simulation (see docs/EXPERIMENTS.md), and a
real platform would want a live cancellation-risk score to prioritize
dispatch toward at-risk requests (exactly what ADVANCED_HEURISTIC's
`w_cancel` term tries to do with a hand-written formula, Math Model Sec H.5).
Comparing a learned model against that hand-written rule is a genuine,
useful question, not ML for its own sake.

Leakage discipline: features are restricted to information known at the
moment a request is created and enters the WAITING pool -- segment, patience,
surge multiplier, price, distance, marketplace imbalance at request time, and
time of day. Anything determined *after* a match happens (pickup ETA, pickup
distance, matched driver) is deliberately excluded, because whether those
fields exist at all is itself a function of the outcome we're trying to
predict (a request that never got matched has no pickup_eta_min) -- including
them would leak the label.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from src import config, engine, world

NUMERIC_FEATURES = ["patience_min", "surge_multiplier", "final_price", "distance_km",
                     "imbalance_at_request", "hour_created"]
CATEGORICAL_FEATURES = ["segment", "origin_archetype"]


def build_dataset(seeds=range(10), scenarios=("NORMAL", "PEAK_DEMAND", "SUPPLY_SHORTAGE")) -> pd.DataFrame:
    """Runs several simulations under varied conditions purely to generate a
    request-level training set -- these are NOT part of the experiment
    matrix in results/results.csv, and this dataset is regenerated fresh
    each time this function runs (no held-out leakage across script runs)."""
    rows = []
    zone_archetype = {z.id: z.archetype for z in config.ZONES}
    for scenario in scenarios:
        for seed in seeds:
            w = world.generate_world(scenario, seed=seed)
            eng = engine.SimulationEngine(
                w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER,
                config.SCENARIOS[scenario],
            )
            eng.run()
            for r in eng.collector.requests:
                if r.state == "REJECTED_OFFER":
                    continue  # never entered the waiting pool; not part of this prediction task
                label = 1 if r.state in ("ABANDONED", "CANCELLED_POSTMATCH") else 0
                rows.append({
                    "patience_min": r.patience_min,
                    "surge_multiplier": r.surge_multiplier,
                    "final_price": r.final_price,
                    "distance_km": r.distance_km,
                    "imbalance_at_request": r.imbalance_at_request,
                    "hour_created": r.hour_created,
                    "segment": r.segment,
                    "origin_archetype": zone_archetype[r.origin_zone],
                    "cancelled": label,
                })
    return pd.DataFrame(rows)


def _make_pipeline(model):
    pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def rule_based_baseline_predictions(df: pd.DataFrame) -> np.ndarray:
    """A simple one-variable heuristic in the same spirit as
    ADVANCED_HEURISTIC's `w_cancel` term (Math Model Sec H.5): score risk as
    inversely proportional to the rider's own patience, min-max normalized to
    [0,1]. This is deliberately simple (a real ops team's first heuristic
    would look exactly like this) so the ML models below have a real,
    non-trivial baseline to beat rather than a straw man."""
    inv_patience = 1.0 / df["patience_min"].values
    lo, hi = inv_patience.min(), inv_patience.max()
    return (inv_patience - lo) / (hi - lo + 1e-9)


def train_and_evaluate(df: pd.DataFrame, random_state: int = 0) -> dict:
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df["cancelled"].values
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=random_state, stratify=y
    )

    results = {}

    # Baseline 1: the rule-based simulator formula itself, as a "model"
    baseline_scores = rule_based_baseline_predictions(X_test)
    results["rule_based_formula"] = {
        "auc": roc_auc_score(y_test, baseline_scores),
        "log_loss": log_loss(y_test, np.clip(baseline_scores, 1e-6, 1 - 1e-6)),
        "brier": brier_score_loss(y_test, baseline_scores),
    }

    # Baseline 2: plain logistic regression on all features
    lr = _make_pipeline(LogisticRegression(max_iter=1000))
    lr.fit(X_train, y_train)
    p_lr = lr.predict_proba(X_test)[:, 1]
    results["logistic_regression"] = {
        "auc": roc_auc_score(y_test, p_lr), "log_loss": log_loss(y_test, p_lr),
        "brier": brier_score_loss(y_test, p_lr),
    }

    # ML model: gradient boosting
    gbm = _make_pipeline(GradientBoostingClassifier(random_state=random_state))
    gbm.fit(X_train, y_train)
    p_gbm = gbm.predict_proba(X_test)[:, 1]
    results["gradient_boosting"] = {
        "auc": roc_auc_score(y_test, p_gbm), "log_loss": log_loss(y_test, p_gbm),
        "brier": brier_score_loss(y_test, p_gbm),
    }

    # Feature importance (gradient boosting)
    feature_names = (
        NUMERIC_FEATURES
        + list(gbm.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    )
    importances = gbm.named_steps["model"].feature_importances_
    results["feature_importance"] = sorted(
        zip(feature_names, importances.tolist()), key=lambda x: -x[1]
    )

    results["n_train"] = len(X_train)
    results["n_test"] = len(X_test)
    results["base_rate"] = float(y.mean())
    return results
