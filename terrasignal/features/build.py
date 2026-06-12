"""Build feature parquets from the latest clean snapshot (the offline store).

  uv run python -m terrasignal.features.build
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl
import structlog

from terrasignal.features.definitions import (
    delinquency_events,
    lease_pricing_features,
    tenant_risk_features,
    tenant_risk_labels,
)
from terrasignal.settings import get_settings
from terrasignal.synth.markets import OBS_END, OBS_START

log = structlog.get_logger(__name__)

SNAPSHOT_TABLES = (
    "properties", "units", "tenants", "leases",
    "lease_clauses", "payments", "work_orders", "market_comps",
)


def latest_snapshot() -> tuple[dict[str, pl.DataFrame], dict[str, str]]:
    settings = get_settings()
    pointer = json.loads(
        (settings.data_dir / "snapshots" / "LATEST.json").read_text(encoding="utf-8")
    )
    snap_dir = Path(pointer["snapshot_dir"])
    frames = {t: pl.read_parquet(snap_dir / f"{t}.parquet") for t in SNAPSHOT_TABLES}
    return frames, pointer


def month_grid(start: date, end: date) -> list[date]:
    months = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        months.append(cur)
        y, m = divmod(cur.year * 12 + (cur.month - 1) + 1, 12)
        cur = date(y, m + 1, 1)
    return months


def build_features() -> Path:
    settings = get_settings()
    frames, pointer = latest_snapshot()
    out_dir = settings.data_dir / "features" / pointer["run_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    # risk: monthly grid from one year into the window to "today"
    risk_months = month_grid(date(OBS_START.year + 1, OBS_START.month, 1), OBS_END)
    risk = tenant_risk_features(frames, risk_months)
    labels = tenant_risk_labels(frames, risk_months, observed_through=OBS_END)
    risk = risk.join(labels, on=["tenant_id", "as_of_month"], how="left").with_columns(
        label=pl.col("label").fill_null(0)
    )
    # scoring population rule: once a tenant has had a delinquency event, it
    # leaves the predictive population (it's in collections, not scoring).
    # The event date is known at as_of, so this uses no future information.
    first_event = (
        delinquency_events(frames["payments"], frames["leases"], observed_through=OBS_END)
        .group_by("tenant_id")
        .agg(first_event_date=pl.col("event_date").min())
    )
    risk = (
        risk.join(first_event, on="tenant_id", how="left")
        .filter(
            pl.col("first_event_date").is_null()
            | (pl.col("as_of_month") < pl.col("first_event_date"))
        )
        .drop("first_event_date")
    )
    risk.write_parquet(out_dir / "tenant_risk_features.parquet")
    log.info("tenant_risk_features", rows=risk.height,
             positives=int(risk["label"].sum()),
             rate=float(risk["label"].mean()))

    # pricing: every lease signing in the window is a priced event
    signings = (
        frames["leases"]
        .filter(pl.col("commencement") >= date(OBS_START.year + 1, OBS_START.month, 1))
        .select(
            "unit_id",
            pl.col("commencement").alias("event_date"),
            "term_months", "lease_type",
            pl.col("base_rent_psf").alias("target_rent_psf"),
            "lease_id",
        )
    )
    pricing = lease_pricing_features(frames, signings)
    pricing.write_parquet(out_dir / "lease_pricing_features.parquet")
    log.info("lease_pricing_features", rows=pricing.height)

    (out_dir / "META.json").write_text(json.dumps({
        "snapshot_run_id": pointer["run_id"],
        "dq_report": pointer["dq_report"],
        "snapshot_dir": pointer["snapshot_dir"],
    }, indent=2), encoding="utf-8")
    (settings.data_dir / "features" / "LATEST.json").write_text(json.dumps({
        "features_dir": str(out_dir),
        "snapshot_run_id": pointer["run_id"],
        "dq_report": pointer["dq_report"],
        "snapshot_dir": pointer["snapshot_dir"],
    }, indent=2), encoding="utf-8")
    return out_dir


if __name__ == "__main__":
    build_features()
    sys.exit(0)
