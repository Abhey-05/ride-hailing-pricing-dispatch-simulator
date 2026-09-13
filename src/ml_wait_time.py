"""
ML component: predict a rider's realized wait time (request -> pickup),
beyond the naive "distance / constant speed" ETA a rider sees at request
time -- for COMPLETED trips only.

Why this framing and not a literal ETA regressor: this simulator's quoted
pickup ETA (src/dispatch.py::eta_minutes) is an exact deterministic function
of pickup distance and the time-of-day congestion multiplier -- there is no
noise for a model to learn there, so "predict the ETA formula" would not be
a real ML task (see docs/CRITICAL_REVIEW.md-style honesty: don't dress up a
formula as ML). What IS genuinely stochastic and NOT visible in a naive
distance-based ETA is total realized wait -- created_tick to trip_started_tick
-- which also depends on marketplace state at request time (how imbalanced
the zone is, how much surge is suppressing/inducing acceptance, the rider's
own patience). Predicting *that* from request-time-only features is the
same spirit as section 13's ask ("beyond simplistic ETA = distance/speed")
scoped to what this simulator actually has signal for.

Leakage discipline: only fields known at request creation are used --
segment, patience, surge multiplier, price, distance, marketplace imbalance,
hour of day, zone. Anything determined after a match (driver id, pickup
distance/ETA of the specific matched driver) is excluded, exactly as in
src/ml_cancellation.py, for the same reason: those fields' very existence
depends on the outcome being predicted.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src import config, engine, world

NUMERIC_FEATURES = ["patience_min", "surge_multiplier", "final_price", "distance_km", "imbalance_at_request", "hour_created"]
CATEGORICAL_FEATURES = ["segment", "origin_archetype"]

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "wait_time_forecast_model.joblib"


def build_dataset(seeds=range(10), scenarios=("NORMAL", "PEAK_DEMAND", "SUPPLY_SHORTAGE", "CONGESTED_PEAK")) -> pd.DataFrame:
    """Same construction as src/ml_cancellation.py::build_dataset -- regenerated
    fresh each run, not part of the 1,080-run experiment matrix."""
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
                if r.state != "COMPLETED" or r.wait_min is None:
                    continue
                rows.append({
                    "scenario": scenario, "seed": seed,
                    "patience_min": r.patience_min, "surge_multiplier": r.surge_multiplier,
                    "final_price": r.final_price, "distance_km": r.distance_km,
                    "imbalance_at_request": r.imbalance_at_request, "hour_created": r.hour_created,
                    "segment": r.segment, "origin_archetype": zone_archetype[r.origin_zone],
                    "wait_min": r.wait_min,
                })
    return pd.DataFrame(rows)


def _make_pipeline(model):
    pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def naive_distance_eta_prediction(df: pd.DataFrame, assumed_speed_kmh: float = config.BASE_SPEED_KMH) -> np.ndarray:
    """Baseline: the naive ETA a rider is quoted in most simple ride-hailing
    write-ups -- distance / a constant speed, converted to minutes. Ignores
    marketplace imbalance, surge, and time-of-day congestion entirely."""
    return (df["distance_km"].values / assumed_speed_kmh) * 60.0


def train_and_evaluate(df: pd.DataFrame, random_state: int = 0) -> dict:
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df["wait_min"].values
    groups = df["scenario"].astype(str) + "_" + df["seed"].astype(str)  # split by simulated day, not by row

    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=random_state)
    train_idx, test_idx = next(splitter.split(X, y, groups=groups))
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    df_test = df.iloc[test_idx]

    def error_report(pred: np.ndarray) -> dict:
        err = np.abs(pred - y_test)
        return {
            "mae": float(err.mean()),
            "p50_error_min": float(np.percentile(err, 50)),
            "p90_error_min": float(np.percentile(err, 90)),
        }

    results = {}
    results["naive_distance_eta"] = error_report(naive_distance_eta_prediction(df_test))

    lr = _make_pipeline(LinearRegression())
    lr.fit(X_train, y_train)
    results["linear_regression"] = error_report(lr.predict(X_test))

    gbm = _make_pipeline(GradientBoostingRegressor(random_state=random_state))
    gbm.fit(X_train, y_train)
    p_gbm = gbm.predict(X_test)
    results["gradient_boosting"] = error_report(p_gbm)

    feature_names = (
        NUMERIC_FEATURES
        + list(gbm.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    )
    importances = gbm.named_steps["model"].feature_importances_
    results["feature_importance"] = sorted(zip(feature_names, importances.tolist()), key=lambda x: -x[1])

    results["n_train"] = len(X_train)
    results["n_test"] = len(X_test)
    results["mean_wait_min"] = float(y.mean())
    return results


def fit_production_model(df: pd.DataFrame, random_state: int = 0):
    """Fits the final model on ALL available data -- the split in
    train_and_evaluate exists only to report an honest out-of-sample metric."""
    gbm = _make_pipeline(GradientBoostingRegressor(random_state=random_state))
    gbm.fit(df[NUMERIC_FEATURES + CATEGORICAL_FEATURES], df["wait_min"].values)
    return gbm


def save_model(pipeline, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)


def load_model(path: Path = MODEL_PATH):
    if not path.exists():
        return None
    return joblib.load(path)


def predict_wait_time(scenario: str, zone_id: int, hour: float, segment: str = "normal", seed: int = 0, model=None) -> dict:
    """Predict expected realized wait for a rider of the given segment
    requesting in `zone_id` at `hour` of `scenario`. Grounding features
    (marketplace imbalance, surge, price, trip distance) are the REAL
    averages observed among requests in that zone during a live simulation
    run up to `hour` (same engine/CRN seeding as everywhere else) -- not
    guessed. Falls back to city-wide averages if the zone has had no
    requests yet by that hour. The trained GBM model supplies the predicted
    number; this function only assembles grounded inputs for it."""
    model = model or load_model()
    if model is None:
        return {"error": "No trained wait-time model found -- run `python train_wait_time_model.py` first."}
    if zone_id not in {z.id for z in config.ZONES}:
        return {"error": f"Unknown zone_id={zone_id}."}
    if segment not in {s.value for s in config.RiderSegment}:
        return {"error": f"Unknown segment={segment}. Options: {[s.value for s in config.RiderSegment]}"}

    horizon_ticks = max(1, int(round(hour * 60)))
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER, config.SCENARIOS[scenario],
    )
    eng.run()

    zone_reqs = [r for r in eng.collector.requests if r.origin_zone == zone_id]
    pool = zone_reqs if zone_reqs else eng.collector.requests
    if not pool:
        return {"error": f"No requests observed by hour={hour} in this run to ground the forecast -- try a later hour."}

    avg_imbalance = float(np.mean([r.imbalance_at_request for r in pool]))
    avg_surge = float(np.mean([r.surge_multiplier for r in pool]))
    avg_price = float(np.mean([r.final_price for r in pool]))
    avg_distance = float(np.mean([r.distance_km for r in pool]))
    zone_archetype = next(z.archetype for z in config.ZONES if z.id == zone_id)
    zone_name = next(z.name for z in config.ZONES if z.id == zone_id)
    patience = config.RIDER_SEGMENT_PARAMS[config.RiderSegment(segment)]["patience_median"]

    features = pd.DataFrame([{
        "patience_min": patience, "surge_multiplier": avg_surge, "final_price": avg_price,
        "distance_km": avg_distance, "imbalance_at_request": avg_imbalance, "hour_created": hour,
        "segment": segment, "origin_archetype": zone_archetype,
    }])
    pred = max(0.0, float(model.predict(features)[0]))
    naive_eta = (avg_distance / config.BASE_SPEED_KMH) * 60.0

    return {
        "source": f"GBM wait-time model (models/wait_time_forecast_model.joblib), fed with real averaged "
                  f"marketplace conditions from a {scenario} run (seed={seed}) up to hour {hour} "
                  f"({'zone-specific' if zone_reqs else 'city-wide fallback -- no requests yet in this zone'} conditions)",
        "zone_id": zone_id, "zone_name": zone_name, "segment": segment,
        "predicted_wait_min": pred,
        "naive_distance_only_eta_min": naive_eta,
        "n_requests_observed_for_grounding": len(pool),
    }
