"""Feature drift via PSI against the training baseline (local stand-in for
SageMaker Model Monitor data-quality schedules).

PSI thresholds come from governed config: green < amber <= psi_amber,
red > psi_red. Red on a top-importance feature is the retrain trigger.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
import structlog
from sqlalchemy import create_engine, text

from terrasignal.features.definitions import PRICING_FEATURES, TENANT_FEATURES
from terrasignal.settings import get_settings, governed_thresholds
from terrasignal.training.registry import active_version

log = structlog.get_logger(__name__)


def psi(baseline: dict[str, list[float]], current: np.ndarray) -> float:
    """Population Stability Index of `current` against stored baseline bins."""
    edges = np.array(baseline["edges"])
    expected = np.array(baseline["proportions"])
    if len(edges) < 3 or current.size == 0:
        return 0.0
    counts, _ = np.histogram(np.nan_to_num(current), bins=edges)
    # clip values outside the baseline range into the edge bins
    below = (np.nan_to_num(current) < edges[0]).sum()
    above = (np.nan_to_num(current) > edges[-1]).sum()
    counts[0] += below
    counts[-1] += above
    actual = counts / max(counts.sum(), 1)
    eps = 1e-4
    e = np.clip(expected, eps, None)
    a = np.clip(actual, eps, None)
    return float(np.sum((a - e) * np.log(a / e)))


def _status(value: float, amber: float, red: float) -> str:
    if value > red:
        return "red"
    if value > amber:
        return "amber"
    return "green"


def compute_drift(current_window_months: int = 3) -> list[dict[str, object]]:
    settings = get_settings()
    thresholds = governed_thresholds()["drift"]
    feat_meta = json.loads(
        (settings.data_dir / "features" / "LATEST.json").read_text(encoding="utf-8")
    )
    feat_dir = Path(feat_meta["features_dir"])
    engine = create_engine(settings.database_url_sync)
    now = datetime.now(UTC)
    results: list[dict[str, object]] = []

    jobs = [
        ("terrasignal-risk-scorer", "tenant_risk_features.parquet", TENANT_FEATURES,
         "as_of_month"),
        ("terrasignal-rent-forecaster", "lease_pricing_features.parquet", PRICING_FEATURES,
         "event_date"),
    ]
    for model_name, parquet, feature_list, date_col in jobs:
        version = active_version(model_name)
        if version is None:
            log.warning("no_approved_version", model=model_name)
            continue
        baseline_path = Path(str(version["artifact_path"])) / "psi_baseline.json"
        baselines = json.loads(baseline_path.read_text(encoding="utf-8"))
        df = pl.read_parquet(feat_dir / parquet)
        max_date: date = df[date_col].max()  # type: ignore[assignment]
        y, m = divmod(max_date.year * 12 + (max_date.month - 1) - current_window_months, 12)
        cutoff = date(y, m + 1, 1)
        recent = df.filter(pl.col(date_col) > cutoff)
        rows = []
        for feat in feature_list:
            value = psi(baselines[feat], recent[feat].to_numpy().astype(np.float64))
            status = _status(value, thresholds["psi_amber"], thresholds["psi_red"])
            rows.append({
                "computed_at": now, "model_name": model_name, "feature_name": feat,
                "psi": round(value, 6), "status": status,
                "baseline_window": "training", "current_window": f"last_{current_window_months}m",
            })
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO drift_metrics (computed_at, model_name, feature_name, "
                     "psi, status, baseline_window, current_window) VALUES "
                     "(:computed_at, :model_name, :feature_name, :psi, :status, "
                     ":baseline_window, :current_window)"),
                rows,
            )
        worst = max(rows, key=lambda r: float(r["psi"]))  # type: ignore[arg-type]
        log.info("drift_computed", model=model_name,
                 worst_feature=worst["feature_name"], worst_psi=worst["psi"])
        results.extend(rows)
    engine.dispose()
    return results


if __name__ == "__main__":
    compute_drift()
