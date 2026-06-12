"""Rent Forecaster training: three XGBoost quantile models (p10/p50/p90).

Baselines to beat (both, by the governed relative-MAPE margin): Ridge on the
same features, and the naive last-comp-median. Time-based split only.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import structlog
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from terrasignal.features.definitions import PRICING_FEATURES
from terrasignal.settings import get_settings, governed_thresholds
from terrasignal.training.registry import register_model

log = structlog.get_logger(__name__)

MODEL_NAME = "terrasignal-rent-forecaster"
TRAIN_END = date(2025, 1, 1)
QUANTILES = (0.1, 0.5, 0.9)


def _mape(y: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs((y - pred) / y)))


def train() -> int:
    settings = get_settings()
    thresholds = governed_thresholds()
    feat_meta = json.loads(
        (settings.data_dir / "features" / "LATEST.json").read_text(encoding="utf-8")
    )
    pricing = pl.read_parquet(
        Path(feat_meta["features_dir"]) / "lease_pricing_features.parquet"
    ).filter(pl.col("target_rent_psf") > 0)

    train_df = pricing.filter(pl.col("event_date") < TRAIN_END)
    test_df = pricing.filter(pl.col("event_date") >= TRAIN_END)
    log.info("splits", train=train_df.height, test=test_df.height)

    def matrix(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        return (
            df.select(PRICING_FEATURES).to_numpy().astype(np.float64),
            df["target_rent_psf"].to_numpy().astype(np.float64),
        )

    x_train, y_train = matrix(train_df)
    x_test, y_test = matrix(test_df)

    models: dict[str, xgb.XGBRegressor] = {}
    preds: dict[str, np.ndarray] = {}
    for q in QUANTILES:
        m = xgb.XGBRegressor(
            objective="reg:quantileerror", quantile_alpha=q,
            n_estimators=500, max_depth=5, learning_rate=0.05, subsample=0.9,
            colsample_bytree=0.8, min_child_weight=4, random_state=17, n_jobs=4,
        )
        m.fit(x_train, y_train)
        key = f"p{int(q * 100)}"
        models[key] = m
        preds[key] = m.predict(x_test)

    # quantile crossing guard: enforce p10 <= p50 <= p90
    p10 = np.minimum(preds["p10"], preds["p50"])
    p90 = np.maximum(preds["p90"], preds["p50"])
    coverage = float(np.mean((y_test >= p10) & (y_test <= p90)))

    # baselines
    ridge = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
    ridge.fit(x_train, y_train)
    ridge_pred = ridge.predict(x_test)
    comp_median_pred = np.nan_to_num(
        test_df["comp_median_rent_6m"].to_numpy().astype(np.float64),
        nan=float(np.nanmedian(y_train)),
    )

    metrics = {
        "mape_p50": _mape(y_test, preds["p50"]),
        "rmse_p50": float(np.sqrt(np.mean((y_test - preds["p50"]) ** 2))),
        "p10_p90_coverage": coverage,
        "n_eval": float(len(y_test)),
    }
    baseline_metrics = {
        "ridge": {"mape_p50": _mape(y_test, ridge_pred)},
        "comp_median": {"mape_p50": _mape(y_test, comp_median_pred)},
    }
    log.info("eval", **metrics)
    log.info("baselines", ridge=baseline_metrics["ridge"]["mape_p50"],
             comp_median=baseline_metrics["comp_median"]["mape_p50"])

    # ---- metric gates ----
    gates = thresholds["model_gates"]
    min_improvement = gates["rent_forecaster_min_mape_improvement"]
    failures = []
    if metrics["mape_p50"] > gates["rent_forecaster_max_mape"]:
        failures.append(
            f"mape {metrics['mape_p50']:.4f} > cap {gates['rent_forecaster_max_mape']}"
        )
    for name, b in baseline_metrics.items():
        rel = (b["mape_p50"] - metrics["mape_p50"]) / b["mape_p50"]
        if rel < min_improvement:
            failures.append(
                f"improvement vs {name} {rel:.1%} < required {min_improvement:.0%}"
            )
    if failures:
        raise RuntimeError("metric gates failed: " + "; ".join(failures))

    # ---- artifacts ----
    artifact_dir = settings.artifacts_dir / MODEL_NAME / "candidate"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for key, m in models.items():
        m.save_model(artifact_dir / f"model_{key}.json")
    joblib.dump(ridge, artifact_dir / "baseline_ridge.joblib")
    (artifact_dir / "features.json").write_text(json.dumps(PRICING_FEATURES), encoding="utf-8")
    psi_baseline = {}
    for i, feat in enumerate(PRICING_FEATURES):
        col = np.nan_to_num(x_train[:, i])
        edges = np.unique(np.quantile(col, np.linspace(0, 1, 11)))
        counts, _ = np.histogram(col, bins=edges)
        psi_baseline[feat] = {
            "edges": edges.tolist(),
            "proportions": (counts / max(counts.sum(), 1)).tolist(),
        }
    (artifact_dir / "psi_baseline.json").write_text(json.dumps(psi_baseline), encoding="utf-8")

    eval_hash = hashlib.sha256(test_df.write_csv().encode()).hexdigest()
    version = register_model(
        MODEL_NAME,
        metrics=metrics,
        baseline_metrics=baseline_metrics,
        eval_set_hash=eval_hash,
        training_snapshot_uri=feat_meta["snapshot_dir"],
        dq_report_uri=feat_meta["dq_report"],
        artifact_dir=artifact_dir,
    )
    versioned = settings.artifacts_dir / MODEL_NAME / f"v{version}"
    if versioned.exists():
        import shutil

        shutil.rmtree(versioned)
    artifact_dir.rename(versioned)
    from terrasignal.training.risk_scorer import _update_artifact_path

    _update_artifact_path(MODEL_NAME, version, versioned)
    return version


if __name__ == "__main__":
    train()
