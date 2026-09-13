"""
ML component: near-term demand forecasting -- for a given zone and a given
15-minute window, predict how many ride requests will originate there,
using only information available at the START of that window.

Why this task, framed this way (same discipline as src/ml_cancellation.py):
a real ops team doesn't need to forecast a whole day in advance -- they need
"is the next 15 minutes about to get worse in this zone" to decide whether
to push a driver incentive or adjust dispatch before it happens. That's a
genuinely useful, genuinely hard (Poisson-noisy) prediction task, not ML for
its own sake.

Leakage discipline: features are restricted to what is known at the instant
a window begins -- the window's own hour/zone/scenario, up to two lags of
*already-completed* prior windows' demand at that zone, and the count of
available drivers in that zone at the window's start (a real-time signal, not
influenced by demand that hasn't happened yet). The window's own demand is
never used to predict itself.

The trained model is persisted to models/demand_forecast_model.joblib (run
train_demand_model.py once to produce it) so it can be loaded and reused for
inference -- e.g. by src.copilot_tools.forecast_demand -- without retraining
on every call. forecast_next_window() below assembles the model's input
features from a REAL live simulation run up to the requested hour (same
engine, same common-random-numbers seeding as everywhere else in this
project); the model only supplies the predicted number, never the LLM.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src import config, engine, world

BUCKET_TICKS = 15  # 15-minute forecast window
NUMERIC_FEATURES = ["hour", "lag_1", "lag_2", "avg_available_drivers"]
CATEGORICAL_FEATURES = ["zone_archetype", "scenario"]

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "demand_forecast_model.joblib"


def bucketize(collector, timeseries: list[dict], scenario: str, seed: int, horizon_ticks: int) -> pd.DataFrame:
    """Pure aggregation of an already-completed run's collector + timeseries
    into one row per (zone, 15-min bucket) -- no engine call. Shared by
    dataset construction (_bucketize_run below) and live inference
    (forecast_next_window), so training and serving use identical feature
    logic."""
    zone_archetype = {z.id: z.archetype for z in config.ZONES}
    n_buckets = horizon_ticks // BUCKET_TICKS

    demand_counts = {z.id: [0] * n_buckets for z in config.ZONES}
    for r in collector.requests:
        bucket = r.created_tick // BUCKET_TICKS
        if bucket < n_buckets:
            demand_counts[r.origin_zone][bucket] += 1

    avail_at_bucket_start = {z.id: [0] * n_buckets for z in config.ZONES}
    for row in timeseries:
        bucket = row["tick"] // BUCKET_TICKS
        if bucket < n_buckets:
            for z in config.ZONES:
                avail_at_bucket_start[z.id][bucket] = row["available_by_zone"].get(z.id, 0)

    rows = []
    for z in config.ZONES:
        counts = demand_counts[z.id]
        for b in range(n_buckets):
            rows.append({
                "scenario": scenario, "seed": seed, "zone_id": z.id, "zone_archetype": zone_archetype[z.id],
                "bucket": b, "hour": (b * BUCKET_TICKS) / 60.0,
                "lag_1": counts[b - 1] if b >= 1 else 0,
                "lag_2": counts[b - 2] if b >= 2 else 0,
                "avg_available_drivers": avail_at_bucket_start[z.id][b],
                "demand": counts[b],
            })
    return pd.DataFrame(rows)


def _bucketize_run(scenario: str, seed: int, horizon_ticks: int = config.DEFAULT_HORIZON_TICKS) -> pd.DataFrame:
    """Runs one simulation and bucketizes it -- used only for dataset
    construction (training needs many independent simulated days)."""
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER,
        config.SCENARIOS[scenario], collect_timeseries=True, timeseries_every_ticks=BUCKET_TICKS,
    )
    eng.run()
    return bucketize(eng.collector, eng._timeseries, scenario, seed, horizon_ticks)


def build_dataset(seeds=range(10), scenarios=("NORMAL", "PEAK_DEMAND", "SUPPLY_SHORTAGE", "CONGESTED_PEAK")) -> pd.DataFrame:
    """Each (scenario, seed) is one independent simulated day -- regenerated
    fresh each time this runs, same as src/ml_cancellation.py::build_dataset."""
    frames = [_bucketize_run(scenario, seed) for scenario in scenarios for seed in seeds]
    return pd.concat(frames, ignore_index=True)


def _make_pipeline(model):
    pre = ColumnTransformer([
        ("num", "passthrough", NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def _seed_split(df: pd.DataFrame, test_frac: float = 0.2, random_state: int = 0):
    """Splits by (scenario, seed) -- i.e. by whole simulated day -- rather
    than shuffling rows, since rows from the same day are autocorrelated
    (today's 9am demand is not independent of today's 9:15am demand). A
    row-level shuffle would leak same-day information into the test set."""
    days = df[["scenario", "seed"]].drop_duplicates()
    rng = np.random.default_rng(random_state)
    idx = rng.permutation(len(days))
    n_test = max(1, int(round(len(days) * test_frac)))
    test_days = days.iloc[idx[:n_test]]
    is_test = df.set_index(["scenario", "seed"]).index.isin(test_days.set_index(["scenario", "seed"]).index)
    return df[~is_test].reset_index(drop=True), df[is_test].reset_index(drop=True)


def naive_last_window_prediction(df: pd.DataFrame) -> np.ndarray:
    """Baseline: 'the next 15 minutes will look like the last 15 minutes.'
    A real ops team's first-pass forecast looks exactly like this -- the ML
    model needs to beat it, not a straw man."""
    return df["lag_1"].values.astype(float)


def train_and_evaluate(df: pd.DataFrame, random_state: int = 0) -> dict:
    train, test = _seed_split(df, random_state=random_state)
    X_train, y_train = train[NUMERIC_FEATURES + CATEGORICAL_FEATURES], train["demand"].values
    X_test, y_test = test[NUMERIC_FEATURES + CATEGORICAL_FEATURES], test["demand"].values

    results = {}

    naive = naive_last_window_prediction(test)
    results["naive_last_window"] = {"mae": mean_absolute_error(y_test, naive), "r2": r2_score(y_test, naive)}

    lr = _make_pipeline(LinearRegression())
    lr.fit(X_train, y_train)
    p_lr = lr.predict(X_test)
    results["linear_regression"] = {"mae": mean_absolute_error(y_test, p_lr), "r2": r2_score(y_test, p_lr)}

    gbm = _make_pipeline(GradientBoostingRegressor(random_state=random_state))
    gbm.fit(X_train, y_train)
    p_gbm = gbm.predict(X_test)
    results["gradient_boosting"] = {"mae": mean_absolute_error(y_test, p_gbm), "r2": r2_score(y_test, p_gbm)}

    feature_names = (
        NUMERIC_FEATURES
        + list(gbm.named_steps["pre"].named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    )
    importances = gbm.named_steps["model"].feature_importances_
    results["feature_importance"] = sorted(zip(feature_names, importances.tolist()), key=lambda x: -x[1])

    results["n_train"] = len(X_train)
    results["n_test"] = len(X_test)
    results["n_train_days"] = train[["scenario", "seed"]].drop_duplicates().shape[0]
    results["n_test_days"] = test[["scenario", "seed"]].drop_duplicates().shape[0]
    results["mean_demand"] = float(df["demand"].mean())
    return results


def fit_production_model(df: pd.DataFrame, random_state: int = 0):
    """Fits the final model on ALL available data (not the held-out split
    used for evaluation) -- the split in train_and_evaluate exists to report
    an honest out-of-sample metric, not to withhold data from the model that
    actually ships."""
    gbm = _make_pipeline(GradientBoostingRegressor(random_state=random_state))
    gbm.fit(df[NUMERIC_FEATURES + CATEGORICAL_FEATURES], df["demand"].values)
    return gbm


def save_model(pipeline, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)


def load_model(path: Path = MODEL_PATH):
    if not path.exists():
        return None
    return joblib.load(path)


def forecast_next_window(scenario: str, zone_id: int, hour: float, seed: int = 0, model=None) -> dict:
    """Forecast near-term (next 15-minute) demand for one zone at a given
    hour of a given scenario. Features (recent demand trend, current
    available drivers) are taken from a REAL live simulation run up to
    `hour` -- the same engine and CRN seeding used everywhere else in this
    project, not guessed or interpolated. The trained GBM model
    (models/demand_forecast_model.joblib) supplies the predicted number;
    this function only assembles grounded inputs for it."""
    model = model or load_model()
    if model is None:
        return {"error": "No trained demand model found -- run `python train_demand_model.py` first."}
    if zone_id not in {z.id for z in config.ZONES}:
        return {"error": f"Unknown zone_id={zone_id}."}

    n_buckets = max(2, int(round(hour * 60 / BUCKET_TICKS)))
    horizon_ticks = n_buckets * BUCKET_TICKS
    w = world.generate_world(scenario, seed=seed, horizon_ticks=horizon_ticks)
    eng = engine.SimulationEngine(
        w, config.PricingPolicy.BASIC_SURGE, config.DispatchPolicy.NEAREST_DRIVER,
        config.SCENARIOS[scenario], collect_timeseries=True, timeseries_every_ticks=BUCKET_TICKS,
    )
    eng.run()
    df = bucketize(eng.collector, eng._timeseries, scenario, seed, horizon_ticks)
    zone_rows = df[df.zone_id == zone_id].sort_values("bucket")
    last = zone_rows.iloc[-1]
    lag_2 = float(zone_rows.iloc[-2]["demand"]) if len(zone_rows) >= 2 else 0.0

    features = pd.DataFrame([{
        "hour": hour, "lag_1": float(last["demand"]), "lag_2": lag_2,
        "avg_available_drivers": float(last["avg_available_drivers"]),
        "zone_archetype": last["zone_archetype"], "scenario": scenario,
    }])
    pred = max(0.0, float(model.predict(features)[0]))
    zone_name = next(z.name for z in config.ZONES if z.id == zone_id)

    return {
        "source": f"GBM demand model (models/demand_forecast_model.joblib), fed live-simulated features "
                  f"from a {scenario} run (seed={seed}) up to hour {hour}",
        "zone_id": zone_id, "zone_name": zone_name,
        "forecast_next_15min_demand": pred,
        "recent_demand_last_15min": float(last["demand"]),
        "available_drivers_now": float(last["avg_available_drivers"]),
    }
