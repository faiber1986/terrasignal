"""Rent forecasting endpoints: on-demand forecast, renewal queue, rationale memo."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.bedrock import RationalePayload, ShapDriver, TemplateMemoBackend
from shared.bedrock.backends import generate_with_guard
from terrasignal.backend.app import queries
from terrasignal.backend.app.audit import audit
from terrasignal.backend.app.auth import User, require_role
from terrasignal.backend.app.db import get_session
from terrasignal.backend.app.flags import baseline_mode
from terrasignal.backend.app.models_service import model_service
from terrasignal.backend.app.schemas import (
    CompOut,
    RationaleResponse,
    RentForecastRequest,
    RentForecastResponse,
    RentQueueItem,
    ShapDriverOut,
)

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.post("/rent", response_model=RentForecastResponse)
async def forecast_rent(
    body: RentForecastRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> RentForecastResponse:
    is_baseline = await baseline_mode(session)
    result = (
        model_service.forecast_unit_baseline(body.unit_id)
        if is_baseline
        else model_service.forecast_unit(body.unit_id)
    )
    if result is None:
        raise HTTPException(404, f"unit {body.unit_id} has no active lease to renew")

    meta = result["meta"]
    prediction_id = uuid.uuid4()
    output = {
        "p10": result["p10"], "p50": result["p50"], "p90": result["p90"],
        "current_rent_psf": float(meta["current_rent_psf"]),
        "lease_expiration": meta["lease_expiration"].isoformat(),
        "current_tenant_id": meta.get("current_tenant_id"),
        "property_name": meta["property_name"],
        "submarket": meta["submarket"],
        "asset_class": meta["asset_class"],
        "unit_rsf": float(meta["unit_rsf"]),
        "term_months": float(meta["term_months"]),
        "comp_median_rent_6m": float(result["features"].get("comp_median_rent_6m", 0.0)),
    }
    await session.execute(
        text(queries.INSERT_PREDICTION),
        {
            "prediction_id": prediction_id,
            "created_at": datetime.now(UTC),
            "model_name": "terrasignal-rent-forecaster",
            "model_version": result["model_version"],
            "entity_type": "unit",
            "entity_id": body.unit_id,
            "as_of": result["as_of"],
            "request_id": getattr(request.state, "request_id", None),
            "features": json.dumps(result["features"]),
            "output": json.dumps(output),
            "shap": json.dumps(result["drivers"]),
            "comps": json.dumps(result["comps"]),
            "baseline_mode": is_baseline,
        },
    )
    await audit(
        session, request, user,
        event_type="forecast.generated", entity_type="unit", entity_id=body.unit_id,
        payload={"prediction_id": str(prediction_id), "p50": result["p50"],
                 "baseline_mode": is_baseline},
    )
    await session.commit()

    return RentForecastResponse(
        prediction_id=prediction_id,
        unit_id=body.unit_id,
        property_name=meta["property_name"],
        submarket=meta["submarket"],
        asset_class=meta["asset_class"],
        unit_rsf=float(meta["unit_rsf"]),
        p10=result["p10"], p50=result["p50"], p90=result["p90"],
        current_rent_psf=float(meta["current_rent_psf"]),
        comp_median_rent_6m=float(result["features"].get("comp_median_rent_6m", 0.0)),
        lease_expiration=meta["lease_expiration"],
        current_tenant_id=meta.get("current_tenant_id"),
        as_of=result["as_of"],
        model_version=result["model_version"],
        baseline_mode=is_baseline,
        drivers=[ShapDriverOut(**d) for d in result["drivers"][:8]],
        comps=[CompOut(**c) for c in result["comps"]],
    )


@router.get("/queue", response_model=list[RentQueueItem])
async def rent_queue(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> list[RentQueueItem]:
    rows = (
        await session.execute(text(queries.RENT_QUEUE), {"limit": limit, "offset": offset})
    ).mappings().all()
    items = []
    for r in rows:
        out = r["output"]
        current = float(out["current_rent_psf"])
        p50 = float(out["p50"])
        items.append(
            RentQueueItem(
                prediction_id=r["prediction_id"],
                unit_id=r["unit_id"],
                property_name=r["property_name"],
                submarket=r["submarket"],
                market=r["market"],
                asset_class=r["asset_class"],
                unit_rsf=int(r["unit_rsf"]),
                floor=int(r["floor"]),
                p50=p50,
                p10=float(out["p10"]),
                p90=float(out["p90"]),
                current_rent_psf=current,
                upside_pct=(p50 / current - 1.0) if current else 0.0,
                lease_expiration=date.fromisoformat(out["lease_expiration"]),
                baseline_mode=r["baseline_mode"],
            )
        )
    return items


@router.post("/{prediction_id}/rationale", response_model=RationaleResponse)
async def rationale(
    prediction_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> RationaleResponse:
    row = (
        await session.execute(text(queries.PREDICTION_BY_ID), {"prediction_id": prediction_id})
    ).mappings().first()
    if row is None or row["model_name"] != "terrasignal-rent-forecaster":
        raise HTTPException(404, "rent forecast prediction not found")

    out = row["output"]
    shap_list = row["shap"] or []
    comps = row["comps"] or []
    payload = RationalePayload(
        unit_id=row["entity_id"],
        property_name=out["property_name"],
        submarket=out["submarket"],
        asset_class=out["asset_class"],
        horizon_months=12,
        p10_rent_psf=round(float(out["p10"]), 2),
        p50_rent_psf=round(float(out["p50"]), 2),
        p90_rent_psf=round(float(out["p90"]), 2),
        current_rent_psf=round(float(out["current_rent_psf"]), 2),
        submarket_median_rent_psf=round(float(out.get("comp_median_rent_6m", 0.0)), 2),
        drivers=[
            ShapDriver(
                feature=d["feature"],
                label=d.get("label", d["feature"]),
                value=round(float(d["value"]), 2),
                shap=round(float(d["shap"]), 2),
            )
            for d in shap_list[:6]
        ],
        comps=[
            {**c, "rent_psf": round(float(c["rent_psf"]), 2),
             "ti_allowance_psf": round(float(c["ti_allowance_psf"]), 2)}
            for c in comps[:5]
        ],
    )
    result = generate_with_guard(TemplateMemoBackend(), payload)
    await audit(
        session, request, user,
        event_type="memo.generated", entity_type="prediction",
        entity_id=str(prediction_id),
        payload={"payload_hash": result.payload_hash, "backend": result.backend,
                 "guard_passed": result.guard_passed},
    )
    await session.commit()
    return RationaleResponse(
        prediction_id=prediction_id,
        memo=result.memo,
        backend=result.backend,
        payload_hash=result.payload_hash,
        guard_passed=result.guard_passed,
        fallback_used=result.fallback_used,
    )
