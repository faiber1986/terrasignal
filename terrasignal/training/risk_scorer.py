"""Tenant Risk Scorer training: XGBoost + isotonic calibration, time splits.

Pipeline (mirrors the SageMaker DAG): load features → time split → train →
calibrate → evaluate vs baseline → metric gates → register(PendingManualApproval).
A worse-than-baseline candidate fails the gate: nothing registers.
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
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from terrasignal.features.build import latest_snapshot
from terrasignal.features.definitions import TENANT_FEATURES, delinquency_events
from terrasignal.settings import get_settings, governed_thresholds
from terrasignal.training.registry import register_model

log = structlog.get_logger(__name__)

MODEL_NAME = "terrasignal-risk-scorer"
TRAIN_END = date(2024, 8, 1)
CALIB_END = date(2025, 2, 1)
TEST_END = date(2025, 11, 1)  # labels right-censored after this


def _matrix(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    x = df.select(TENANT_FEATURES).to_numpy().astype(np.float64)
    y = df["label"].to_numpy().astype(np.int32)
    return x, y


def _precision_at_decile(y: np.ndarray, p: np.ndarray) -> float:
    k = max(1, int(len(p) * 0.10))
    top = np.argsort(-p)[:k]
    return float(y[top].mean())


def _median_lead_time_days(
    test: pl.DataFrame, scores: np.ndarray, threshold: float, frames: dict[str, pl.DataFrame]
) -> float:
    """Median days between first flag >= threshold and the delinquency event."""
    scored = test.select("tenant_id", "as_of_month").with_columns(
        score=pl.Series(scores)
    )
    events = (
        delinquency_events(frames["payments"], frames["leases"],
                           observed_through=date(2026, 6, 1))
        .group_by("tenant_id").agg(event_date=pl.col("event_date").min())
    )
    flagged = (
        scored.filter(pl.col("score") >= threshold)
        .group_by("tenant_id")
        .agg(first_flag=pl.col("as_of_month").min())
        .join(events, on="tenant_id", how="inner")
        .filter(pl.col("event_date") > pl.col("first_flag"))
        .with_columns(lead=(pl.col("event_date") - pl.col("first_flag")).dt.total_days())
    )
    return float(flagged["lead"].median()) if flagged.height else 0.0


def train() -> int:
    settings = get_settings()
    thresholds = governed_thresholds()
    frames, pointer = latest_snapshot()
    feat_meta = json.loads(
        (settings.data_dir / "features" / "LATEST.json").read_text(encoding="utf-8")
    )
    features = pl.read_parquet(
        Path(feat_meta["features_dir"]) / "tenant_risk_features.parquet"
    ).filter(pl.col("as_of_month") <= TEST_END)

    train_df = features.filter(pl.col("as_of_month") <= TRAIN_END)
    calib_df = features.filter(
        (pl.col("as_of_month") > TRAIN_END) & (pl.col("as_of_month") <= CALIB_END)
    )
    test_df = features.filter(pl.col("as_of_month") > CALIB_END)
    log.info("splits", train=train_df.height, calib=calib_df.height, test=test_df.height,
             train_pos_rate=float(train_df["label"].mean()))

    x_train, y_train = _matrix(train_df)
    x_calib, y_calib = _matrix(calib_df)
    x_test, y_test = _matrix(test_df)

    # GLM prior: the candidate is XGBoost boosted FROM a regularized logistic
    # margin (standard credit-risk hybrid). The GLM carries the smooth
    # log-linear risk surface; trees learn the nonlinear/temporal corrections.
    glm = make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
    )
    glm.fit(np.nan_to_num(x_train), y_train)

    def glm_margin(x: np.ndarray) -> np.ndarray:
        p = np.clip(glm.predict_proba(np.nan_to_num(x))[:, 1], 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))

    m_train, m_calib, m_test = glm_margin(x_train), glm_margin(x_calib), glm_margin(x_test)

    spw = float((y_train == 0).sum() / max((y_train == 1).sum(), 1))
    # domain knowledge as monotonicity constraints (standard credit-risk
    # practice; also a governance property reviewers can verify)
    monotone = {
        "days_late_mean_3m": 1, "days_late_mean_6m": 1, "days_late_mean_12m": 1,
        "days_late_max_6m": 1, "late_share_6m": 1, "days_late_trend_6m": 1,
        "unpaid_count": 1, "dispute_rate_12m": 1, "wo_count_12m": 0,
        "rent_to_market": 1, "deposit_coverage_months": -1, "credit_rating_ord": 1,
        "sector_distress_idx": 1, "adverse_clause_share": 1, "tenure_months": 0,
        "n_active_leases": 0, "total_monthly_due": 0,
    }
    constraints = tuple(monotone[f] for f in TENANT_FEATURES)

    # model selection on the calibration fold (never the test fold)
    best_model, best_ap = None, -1.0
    for max_depth, lr, use_mono, use_spw in (
        (3, 0.05, True, True), (4, 0.05, True, True), (3, 0.05, True, False),
        (4, 0.05, True, False), (4, 0.05, False, True), (2, 0.05, True, False),
    ):
        cand = xgb.XGBClassifier(
            n_estimators=1500, max_depth=max_depth, learning_rate=lr, subsample=0.9,
            colsample_bytree=0.8, min_child_weight=6,
            scale_pos_weight=spw if use_spw else 1.0,
            monotone_constraints=constraints if use_mono else None,
            eval_metric="aucpr", random_state=17, n_jobs=4,
            early_stopping_rounds=60,
        )
        cand.fit(
            x_train, y_train,
            base_margin=m_train,
            eval_set=[(x_calib, y_calib)],
            base_margin_eval_set=[m_calib],
            verbose=False,
        )
        ap = float(average_precision_score(
            y_calib, cand.predict_proba(x_calib, base_margin=m_calib)[:, 1]
        ))
        log.info("candidate", max_depth=max_depth, lr=lr, mono=use_mono, spw=use_spw,
                 calib_pr_auc=round(ap, 4), best_iter=int(cand.best_iteration))
        if ap > best_ap:
            best_model, best_ap = cand, ap
    assert best_model is not None
    model = best_model

    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(model.predict_proba(x_calib, base_margin=m_calib)[:, 1], y_calib)

    raw_test = model.predict_proba(x_test, base_margin=m_test)[:, 1]
    cal_test = calibrator.predict(raw_test)

    # baseline: the same regularized logistic, standing alone
    base_p = glm.predict_proba(np.nan_to_num(x_test))[:, 1]

    watchlist_cut = float(np.quantile(cal_test, 0.90))
    metrics = {
        "pr_auc": float(average_precision_score(y_test, cal_test)),
        "roc_auc": float(roc_auc_score(y_test, cal_test)),
        "brier": float(brier_score_loss(y_test, cal_test)),
        "precision_at_decile": _precision_at_decile(y_test, cal_test),
        "base_rate": float(y_test.mean()),
        "median_lead_time_days": _median_lead_time_days(
            test_df, cal_test, watchlist_cut, frames
        ),
    }
    baseline_metrics = {
        "logistic": {
            "pr_auc": float(average_precision_score(y_test, base_p)),
            "roc_auc": float(roc_auc_score(y_test, base_p)),
            "brier": float(brier_score_loss(y_test, base_p)),
            "precision_at_decile": _precision_at_decile(y_test, base_p),
        }
    }
    log.info("eval", **metrics)
    log.info("baseline", **baseline_metrics["logistic"])

    # ---- metric gates (ConditionStep equivalent; gates are code) ----
    gates = thresholds["model_gates"]
    failures = []
    if metrics["pr_auc"] < gates["risk_scorer_min_pr_auc"]:
        failures.append(f"pr_auc {metrics['pr_auc']:.3f} < {gates['risk_scorer_min_pr_auc']}")
    if metrics["brier"] > gates["risk_scorer_max_brier"]:
        failures.append(f"brier {metrics['brier']:.3f} > {gates['risk_scorer_max_brier']}")
    if metrics["pr_auc"] <= baseline_metrics["logistic"]["pr_auc"]:
        failures.append("candidate does not beat logistic baseline on PR-AUC")
    if failures:
        raise RuntimeError("metric gates failed: " + "; ".join(failures))

    # ---- artifacts ----
    artifact_dir = settings.artifacts_dir / MODEL_NAME / "candidate"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(artifact_dir / "model.json")
    joblib.dump(calibrator, artifact_dir / "calibrator.joblib")
    joblib.dump(glm, artifact_dir / "glm_prior.joblib")
    (artifact_dir / "features.json").write_text(json.dumps(TENANT_FEATURES), encoding="utf-8")
    # PSI baseline: per-feature decile edges + proportions from the training set
    psi_baseline = {}
    for i, feat in enumerate(TENANT_FEATURES):
        col = np.nan_to_num(x_train[:, i])
        edges = np.unique(np.quantile(col, np.linspace(0, 1, 11)))
        counts, _ = np.histogram(col, bins=edges)
        psi_baseline[feat] = {
            "edges": edges.tolist(),
            "proportions": (counts / max(counts.sum(), 1)).tolist(),
        }
    (artifact_dir / "psi_baseline.json").write_text(json.dumps(psi_baseline), encoding="utf-8")
    (artifact_dir / "watchlist_threshold.json").write_text(
        json.dumps({"threshold": watchlist_cut}), encoding="utf-8"
    )

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
    _update_artifact_path(MODEL_NAME, version, versioned)
    return version


def _update_artifact_path(model_name: str, version: int, path: Path) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(get_settings().database_url_sync)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE model_registry SET artifact_path=:p "
                 "WHERE model_name=:n AND version=:v"),
            {"p": str(path), "n": model_name, "v": version},
        )
    engine.dispose()


if __name__ == "__main__":
    train()
