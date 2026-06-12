"""In-process model serving (local stand-in for the SageMaker endpoint).

Loads ONLY Approved registry versions at startup. Features come from the
latest offline-store parquets held in memory — the online-store read path.
Baseline mode (kill switch) swaps every prediction for a labeled heuristic
without touching the models.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import polars as pl
import shap
import structlog
import xgboost as xgb

from terrasignal.features.build import latest_snapshot
from terrasignal.features.definitions import (
    PRICING_FEATURES,
    TENANT_FEATURES,
    lease_pricing_features,
)
from terrasignal.settings import get_settings, governed_thresholds
from terrasignal.synth.markets import OBS_END
from terrasignal.training.registry import active_version

log = structlog.get_logger(__name__)

FEATURE_LABELS: dict[str, str] = {
    "days_late_mean_3m": "Avg days late (3m)",
    "days_late_mean_6m": "Avg days late (6m)",
    "days_late_mean_12m": "Avg days late (12m)",
    "days_late_max_6m": "Worst days late (6m)",
    "late_share_6m": "Share of late payments (6m)",
    "days_late_trend_6m": "Payment timing trend (6m)",
    "unpaid_count": "Unpaid invoices outstanding",
    "dispute_rate_12m": "Disputed work-order rate (12m)",
    "wo_count_12m": "Work orders (12m)",
    "rent_to_market": "Rent vs market ratio",
    "deposit_coverage_months": "Deposit coverage (months)",
    "credit_rating_ord": "Credit rating",
    "sector_distress_idx": "Industry distress index",
    "adverse_clause_share": "Adverse clause share",
    "tenure_months": "Tenure (months)",
    "n_active_leases": "Active leases",
    "total_monthly_due": "Monthly rent obligation",
    "comp_median_rent_6m": "Submarket comp median (6m)",
    "comp_median_rent_12m": "Submarket comp median (12m)",
    "comp_count_6m": "Comp count (6m)",
    "comp_median_ti_6m": "Median TI allowance (6m)",
    "comp_median_free_rent_6m": "Median free rent (6m)",
    "property_age": "Property age (years)",
    "condition_ord": "Condition grade",
    "asset_class_ord": "Asset class",
    "floor": "Floor",
    "unit_rsf": "Unit RSF",
    "term_months": "Term (months)",
    "lease_type_ord": "Lease type",
    "building_vacancy": "Building vacancy",
    "submarket_rent_momentum": "Submarket rent momentum",
}


class ModelService:
    def __init__(self) -> None:
        self.ready = False
        self.as_of: date = OBS_END
        self.risk_version: int = 0
        self.rent_version: int = 0

    def load(self) -> None:
        settings = get_settings()
        thresholds = governed_thresholds()
        self.amber_pd = float(thresholds["risk_scorer"]["amber_pd"])
        self.red_pd = float(thresholds["risk_scorer"]["red_pd"])

        risk_reg = active_version("terrasignal-risk-scorer")
        rent_reg = active_version("terrasignal-rent-forecaster")
        if risk_reg is None or rent_reg is None:
            raise RuntimeError(
                "no Approved model versions in the registry — run training and approve"
            )
        self.risk_version = int(risk_reg["version"])
        self.rent_version = int(rent_reg["version"])

        art = Path(str(risk_reg["artifact_path"]))
        self.risk_model = xgb.XGBClassifier()
        self.risk_model.load_model(art / "model.json")
        self.calibrator = joblib.load(art / "calibrator.joblib")
        self.glm_prior = joblib.load(art / "glm_prior.joblib")
        self.risk_explainer = shap.TreeExplainer(self.risk_model)

        art = Path(str(rent_reg["artifact_path"]))
        self.rent_models: dict[str, xgb.XGBRegressor] = {}
        for key in ("p10", "p50", "p90"):
            m = xgb.XGBRegressor()
            m.load_model(art / f"model_{key}.json")
            self.rent_models[key] = m
        self.rent_explainer = shap.TreeExplainer(self.rent_models["p50"])

        # ---- online feature store (in-memory parquet) ----
        feat_meta = json.loads(
            (settings.data_dir / "features" / "LATEST.json").read_text(encoding="utf-8")
        )
        risk_feats = pl.read_parquet(
            Path(feat_meta["features_dir"]) / "tenant_risk_features.parquet"
        )
        self.risk_features = risk_feats.filter(
            pl.col("as_of_month") == risk_feats["as_of_month"].max()
        )
        self.risk_as_of: date = self.risk_features["as_of_month"].max()  # type: ignore[assignment]

        frames, _ = latest_snapshot()
        self.frames = frames
        active = (
            frames["leases"]
            .filter(
                (pl.col("commencement") <= OBS_END) & (pl.col("expiration") > OBS_END)
                & (pl.col("base_rent_psf") > 0)
            )
            .sort("expiration")
            .unique(subset=["unit_id"], keep="first")
        )
        events = active.select(
            "unit_id",
            pl.lit(OBS_END).alias("event_date"),
            "term_months", "lease_type",
            pl.col("base_rent_psf").alias("current_rent_psf"),
            pl.col("expiration").alias("lease_expiration"),
            pl.col("tenant_id").alias("current_tenant_id"),
        )
        self.pricing_features = lease_pricing_features(frames, events)
        self.comps = frames["market_comps"].filter(pl.col("rent_psf") > 0)
        self.ready = True
        log.info(
            "models_loaded",
            risk_version=self.risk_version,
            rent_version=self.rent_version,
            tenants=self.risk_features.height,
            units=self.pricing_features.height,
        )

    # ---- helpers -----------------------------------------------------------

    def _glm_margin(self, x: np.ndarray) -> np.ndarray:
        p = np.clip(self.glm_prior.predict_proba(np.nan_to_num(x))[:, 1], 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p))

    def band(self, pd_value: float) -> str:
        if pd_value >= self.red_pd:
            return "red"
        if pd_value >= self.amber_pd:
            return "amber"
        return "green"

    @staticmethod
    def _drivers(x: np.ndarray, shap_vals: np.ndarray, features: list[str],
                 top: int | None = None) -> list[dict[str, Any]]:
        rows = [
            {
                "feature": f,
                "label": FEATURE_LABELS.get(f, f),
                "value": float(np.nan_to_num(x[j])),
                "shap": float(shap_vals[j]),
            }
            for j, f in enumerate(features)
        ]
        rows.sort(key=lambda d: -abs(float(d["shap"])))
        return rows[:top] if top else rows

    # ---- scoring -----------------------------------------------------------

    def score_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        row = self.risk_features.filter(pl.col("tenant_id") == tenant_id)
        if row.height == 0:
            return None
        x = row.select(TENANT_FEATURES).to_numpy().astype(np.float64)
        margin = self._glm_margin(x)
        raw = self.risk_model.predict_proba(x, base_margin=margin)[:, 1]
        pd_cal = float(self.calibrator.predict(raw)[0])
        shap_vals = self.risk_explainer.shap_values(x)[0]
        return {
            "features": {f: float(np.nan_to_num(x[0, j]))
                         for j, f in enumerate(TENANT_FEATURES)},
            "pd": pd_cal,
            "drivers": self._drivers(x[0], shap_vals, TENANT_FEATURES),
            "as_of": self.risk_as_of,
            "model_version": self.risk_version,
        }

    def score_tenant_baseline(self, tenant_id: str) -> dict[str, Any] | None:
        """Kill-switch heuristic: banded prior by credit rating, no model."""
        row = self.risk_features.filter(pl.col("tenant_id") == tenant_id)
        if row.height == 0:
            return None
        rating = float(row["credit_rating_ord"][0])
        late6 = float(np.nan_to_num(row["days_late_mean_6m"][0]))
        pd_prior = min(0.95, 0.01 * rating**2 + (0.02 * max(late6 - 5, 0)))
        return {
            "features": {"credit_rating_ord": rating, "days_late_mean_6m": late6},
            "pd": pd_prior,
            "drivers": [],
            "as_of": self.risk_as_of,
            "model_version": 0,
        }

    def forecast_unit(self, unit_id: str) -> dict[str, Any] | None:
        row = self.pricing_features.filter(pl.col("unit_id") == unit_id)
        if row.height == 0:
            return None
        x = row.select(PRICING_FEATURES).to_numpy().astype(np.float64)
        p10 = float(self.rent_models["p10"].predict(x)[0])
        p50 = float(self.rent_models["p50"].predict(x)[0])
        p90 = float(self.rent_models["p90"].predict(x)[0])
        p10, p90 = min(p10, p50), max(p90, p50)
        shap_vals = self.rent_explainer.shap_values(x)[0]
        rec = row.to_dicts()[0]
        return {
            "features": {f: float(np.nan_to_num(x[0, j]))
                         for j, f in enumerate(PRICING_FEATURES)},
            "p10": p10, "p50": p50, "p90": p90,
            "drivers": self._drivers(x[0], shap_vals, PRICING_FEATURES),
            "meta": rec,
            "comps": self.nearest_comps(rec["submarket"], rec["asset_class"]),
            "as_of": OBS_END,
            "model_version": self.rent_version,
        }

    def forecast_unit_baseline(self, unit_id: str) -> dict[str, Any] | None:
        row = self.pricing_features.filter(pl.col("unit_id") == unit_id)
        if row.height == 0:
            return None
        rec = row.to_dicts()[0]
        median = float(np.nan_to_num(rec["comp_median_rent_6m"]))
        return {
            "features": {"comp_median_rent_6m": median},
            "p10": median * 0.92, "p50": median, "p90": median * 1.08,
            "drivers": [],
            "meta": rec,
            "comps": self.nearest_comps(rec["submarket"], rec["asset_class"]),
            "as_of": OBS_END,
            "model_version": 0,
        }

    def nearest_comps(self, submarket: str, asset_class: str) -> list[dict[str, Any]]:
        nearest = (
            self.comps.filter(
                (pl.col("submarket") == submarket)
                & (pl.col("asset_class") == asset_class)
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
        return nearest


model_service = ModelService()
