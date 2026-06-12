"""Batch scoring with the APPROVED model versions.

- Risk: every tenant in the current scoring population → calibrated PD + SHAP.
- Rent: every unit whose lease expires within 18 months (the renewal wall)
  → p10/p50/p90 + SHAP + the 5 nearest comps used for grounding.

Every prediction row persists features, SHAP vector and model version — the
audit trail is the product, not a side effect.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import shap
import structlog
import xgboost as xgb
from sqlalchemy import create_engine, text

from terrasignal.features.build import latest_snapshot
from terrasignal.features.definitions import (
    PRICING_FEATURES,
    TENANT_FEATURES,
    lease_pricing_features,
)
from terrasignal.settings import get_settings
from terrasignal.synth.markets import OBS_END
from terrasignal.training.registry import active_version

log = structlog.get_logger(__name__)

INSERT_PREDICTION = text(
    "INSERT INTO predictions (prediction_id, created_at, model_name, model_version, "
    "entity_type, entity_id, as_of, features, output, shap, comps, baseline_mode) "
    "VALUES (:prediction_id, :created_at, :model_name, :model_version, :entity_type, "
    ":entity_id, :as_of, :features, :output, :shap, :comps, false)"
)


def _shap_rows(
    explainer: shap.TreeExplainer, x: np.ndarray, features: list[str]
) -> list[list[dict[str, float | str]]]:
    values = explainer.shap_values(x)
    out = []
    for i in range(x.shape[0]):
        row = [
            {"feature": f, "value": float(np.nan_to_num(x[i, j])),
             "shap": float(values[i, j])}
            for j, f in enumerate(features)
        ]
        row.sort(key=lambda d: -abs(float(d["shap"])))
        out.append(row)
    return out


def score_risk(conn, now: datetime) -> int:
    settings = get_settings()
    reg = active_version("terrasignal-risk-scorer")
    if reg is None:
        raise RuntimeError("no approved risk scorer; approve a version first")
    art = Path(str(reg["artifact_path"]))
    model = xgb.XGBClassifier()
    model.load_model(art / "model.json")
    calibrator = joblib.load(art / "calibrator.joblib")
    glm = joblib.load(art / "glm_prior.joblib")

    feat_meta = json.loads(
        (settings.data_dir / "features" / "LATEST.json").read_text(encoding="utf-8")
    )
    features = pl.read_parquet(
        Path(feat_meta["features_dir"]) / "tenant_risk_features.parquet"
    )
    latest = features.filter(pl.col("as_of_month") == features["as_of_month"].max())
    x = latest.select(TENANT_FEATURES).to_numpy().astype(np.float64)
    p_glm = np.clip(glm.predict_proba(np.nan_to_num(x))[:, 1], 1e-6, 1 - 1e-6)
    margin = np.log(p_glm / (1 - p_glm))
    pd_cal = calibrator.predict(model.predict_proba(x, base_margin=margin)[:, 1])
    shap_rows = _shap_rows(shap.TreeExplainer(model), x, TENANT_FEATURES)

    as_of = latest["as_of_month"].max()
    rows = []
    for i, rec in enumerate(latest.to_dicts()):
        feature_dict = {f: float(np.nan_to_num(rec[f])) for f in TENANT_FEATURES}
        rows.append({
            "prediction_id": uuid.uuid4(), "created_at": now,
            "model_name": "terrasignal-risk-scorer",
            "model_version": int(reg["version"]),
            "entity_type": "tenant", "entity_id": rec["tenant_id"], "as_of": as_of,
            "features": json.dumps(feature_dict),
            "output": json.dumps({"pd": float(pd_cal[i])}),
            "shap": json.dumps(shap_rows[i]),
            "comps": None,
        })
    conn.execute(INSERT_PREDICTION, rows)
    log.info("risk_scored", n=len(rows), as_of=str(as_of))
    return len(rows)


def score_rent(conn, now: datetime) -> int:
    reg = active_version("terrasignal-rent-forecaster")
    if reg is None:
        raise RuntimeError("no approved rent forecaster; approve a version first")
    art = Path(str(reg["artifact_path"]))
    models = {}
    for key in ("p10", "p50", "p90"):
        m = xgb.XGBRegressor()
        m.load_model(art / f"model_{key}.json")
        models[key] = m

    frames, _pointer = latest_snapshot()
    leases, units = frames["leases"], frames["units"]
    horizon = OBS_END.replace(year=OBS_END.year + 1, month=OBS_END.month)
    y, m = divmod(OBS_END.year * 12 + (OBS_END.month - 1) + 18, 12)
    from datetime import date as _date

    wall_end = _date(y, m + 1, 1)
    expiring = (
        leases.filter(
            (pl.col("expiration") > OBS_END) & (pl.col("expiration") <= wall_end)
            & (pl.col("base_rent_psf") > 0)
        )
        .sort("expiration")
        .unique(subset=["unit_id"], keep="first")
    )
    events = expiring.select(
        "unit_id",
        pl.lit(OBS_END).alias("event_date"),
        "term_months", "lease_type",
        pl.col("base_rent_psf").alias("current_rent_psf"),
        pl.col("expiration").alias("lease_expiration"),
        pl.col("lease_id").alias("current_lease_id"),
        pl.col("tenant_id").alias("current_tenant_id"),
    )
    feats = lease_pricing_features(frames, events)
    x = feats.select(PRICING_FEATURES).to_numpy().astype(np.float64)
    p10 = models["p10"].predict(x)
    p50 = models["p50"].predict(x)
    p90 = models["p90"].predict(x)
    p10, p90 = np.minimum(p10, p50), np.maximum(p90, p50)
    shap_rows = _shap_rows(shap.TreeExplainer(models["p50"]), x, PRICING_FEATURES)

    comps_all = frames["market_comps"].filter(pl.col("rent_psf") > 0)
    rows = []
    for i, rec in enumerate(feats.to_dicts()):
        nearest = (
            comps_all.filter(
                (pl.col("submarket") == rec["submarket"])
                & (pl.col("asset_class") == rec["asset_class"])
                & (pl.col("signed_date") <= OBS_END)
            )
            .sort("signed_date", descending=True)
            .head(5)
            .select("comp_id", "submarket", "signed_date", "rent_psf", "term_months",
                    "ti_allowance_psf", "free_rent_months")
            .to_dicts()
        )
        for c in nearest:
            c["signed_date"] = c["signed_date"].isoformat()
            for k in ("rent_psf", "ti_allowance_psf"):
                c[k] = float(c[k])
        feature_dict = {f: float(np.nan_to_num(rec[f])) for f in PRICING_FEATURES}
        rows.append({
            "prediction_id": uuid.uuid4(), "created_at": now,
            "model_name": "terrasignal-rent-forecaster",
            "model_version": int(reg["version"]),
            "entity_type": "unit", "entity_id": rec["unit_id"], "as_of": OBS_END,
            "features": json.dumps(feature_dict),
            "output": json.dumps({
                "p10": float(p10[i]), "p50": float(p50[i]), "p90": float(p90[i]),
                "current_rent_psf": float(rec["current_rent_psf"]),
                "lease_expiration": rec["lease_expiration"].isoformat(),
                "current_lease_id": rec["current_lease_id"],
                "current_tenant_id": rec["current_tenant_id"],
                "property_name": rec["property_name"],
                "submarket": rec["submarket"],
                "asset_class": rec["asset_class"],
                "unit_rsf": float(rec["unit_rsf"]),
                "term_months": float(rec["term_months"]),
                "comp_median_rent_6m": float(np.nan_to_num(rec["comp_median_rent_6m"])),
            }),
            "shap": json.dumps(shap_rows[i]),
            "comps": json.dumps(nearest),
        })
        _ = horizon
    conn.execute(INSERT_PREDICTION, rows)
    log.info("rent_scored", n=len(rows))
    return len(rows)


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        n_risk = score_risk(conn, now)
        n_rent = score_rent(conn, now)
    engine.dispose()
    log.info("batch_score_done", risk=n_risk, rent=n_rent)


if __name__ == "__main__":
    main()
