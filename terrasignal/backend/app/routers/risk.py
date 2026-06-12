"""Risk scoring endpoints: on-demand scoring, ranked queue, tenant drill-down.

Scoring persists prediction + SHAP + model version in the SAME transaction as
the response — the persistence IS the audit trail.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from terrasignal.backend.app import queries
from terrasignal.backend.app.audit import audit
from terrasignal.backend.app.auth import User, require_role
from terrasignal.backend.app.db import get_session
from terrasignal.backend.app.flags import baseline_mode
from terrasignal.backend.app.models_service import FEATURE_LABELS, model_service
from terrasignal.backend.app.schemas import (
    PaymentRow,
    RiskQueueItem,
    RiskScoreRequest,
    RiskScoreResponse,
    ShapDriverOut,
    TenantDetail,
    TenantLease,
)

router = APIRouter(prefix="/risk", tags=["risk"])

TENANT_TRENDS = """
SELECT l.tenant_id,
       date_trunc('month', p.due_date)::date AS month,
       AVG(GREATEST(COALESCE(p.paid_date - p.due_date, :today - p.due_date), 0))::float
         AS mean_days_late
FROM payments p
JOIN leases l USING (lease_id)
WHERE l.tenant_id = ANY(:tenant_ids) AND p.due_date >= :since AND p.due_date <= :today
GROUP BY 1, 2 ORDER BY 1, 2
"""


@router.post("/score", response_model=RiskScoreResponse)
async def score_tenant(
    body: RiskScoreRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> RiskScoreResponse:
    is_baseline = await baseline_mode(session)
    result = (
        model_service.score_tenant_baseline(body.tenant_id)
        if is_baseline
        else model_service.score_tenant(body.tenant_id)
    )
    if result is None:
        raise HTTPException(404, f"tenant {body.tenant_id} not in scoring population")

    tenant_row = (
        await session.execute(text(queries.TENANT_DETAIL), {"tenant_id": body.tenant_id})
    ).mappings().first()
    if tenant_row is None:
        raise HTTPException(404, f"tenant {body.tenant_id} not found")

    prediction_id = uuid.uuid4()
    await session.execute(
        text(queries.INSERT_PREDICTION),
        {
            "prediction_id": prediction_id,
            "created_at": datetime.now(UTC),
            "model_name": "terrasignal-risk-scorer",
            "model_version": result["model_version"],
            "entity_type": "tenant",
            "entity_id": body.tenant_id,
            "as_of": result["as_of"],
            "request_id": getattr(request.state, "request_id", None),
            "features": json.dumps(result["features"]),
            "output": json.dumps({"pd": result["pd"]}),
            "shap": json.dumps(result["drivers"]),
            "comps": None,
            "baseline_mode": is_baseline,
        },
    )
    await audit(
        session, request, user,
        event_type="prediction.scored",
        entity_type="tenant",
        entity_id=body.tenant_id,
        payload={"prediction_id": str(prediction_id), "pd": result["pd"],
                 "baseline_mode": is_baseline},
    )
    await session.commit()

    return RiskScoreResponse(
        prediction_id=prediction_id,
        tenant_id=body.tenant_id,
        tenant_name=tenant_row["name"],
        pd=result["pd"],
        band=model_service.band(result["pd"]),
        as_of=result["as_of"],
        model_version=result["model_version"],
        baseline_mode=is_baseline,
        drivers=[ShapDriverOut(**d) for d in result["drivers"][:8]],
    )


@router.get("/queue", response_model=list[RiskQueueItem])
async def risk_queue(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> list[RiskQueueItem]:
    rows = (
        await session.execute(text(queries.RISK_QUEUE), {"limit": limit, "offset": offset})
    ).mappings().all()

    tenant_ids = [r["tenant_id"] for r in rows]
    today: date = model_service.as_of
    since = date(today.year - 1, today.month, 1)
    trends: dict[str, list[float]] = {t: [] for t in tenant_ids}
    if tenant_ids:
        trend_rows = (
            await session.execute(
                text(TENANT_TRENDS),
                {"tenant_ids": tenant_ids, "since": since, "today": today},
            )
        ).mappings().all()
        for tr in trend_rows:
            trends[tr["tenant_id"]].append(round(float(tr["mean_days_late"]), 2))

    await audit(
        session, request, user,
        event_type="risk_queue.viewed", entity_type="risk_queue", entity_id="queue",
        payload={"limit": limit, "offset": offset, "rows": len(rows)},
    )
    await session.commit()

    items = []
    for r in rows:
        output = r["output"]
        shap_list = r["shap"] or []
        features = {}
        top_feature = shap_list[0]["feature"] if shap_list else "—"
        pd_val = float(output["pd"])
        items.append(
            RiskQueueItem(
                prediction_id=r["prediction_id"],
                tenant_id=r["tenant_id"],
                tenant_name=r["tenant_name"],
                industry=r["industry_naics"],
                credit_rating=r["credit_rating"],
                pd=pd_val,
                band=model_service.band(pd_val),
                model_version=r["model_version"],
                baseline_mode=r["baseline_mode"],
                top_driver=FEATURE_LABELS.get(top_feature, top_feature),
                monthly_rent_due=float(features.get("total_monthly_due", 0.0)),
                trend=trends.get(r["tenant_id"], []),
            )
        )
    return items


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def tenant_detail(
    tenant_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> TenantDetail:
    tenant_row = (
        await session.execute(text(queries.TENANT_DETAIL), {"tenant_id": tenant_id})
    ).mappings().first()
    if tenant_row is None:
        raise HTTPException(404, f"tenant {tenant_id} not found")

    today: date = model_service.as_of
    since = date(today.year - 2, today.month, 1)
    payments = (
        await session.execute(
            text(queries.TENANT_PAYMENT_HISTORY), {"tenant_id": tenant_id, "since": since}
        )
    ).mappings().all()
    leases = (
        await session.execute(text(queries.TENANT_LEASES), {"tenant_id": tenant_id})
    ).mappings().all()
    history = (
        await session.execute(text(queries.TENANT_SCORE_HISTORY), {"tenant_id": tenant_id})
    ).mappings().all()
    latest_pred = (
        await session.execute(
            text(queries.LATEST_PREDICTION_FOR_ENTITY),
            {"entity_type": "tenant", "entity_id": tenant_id,
             "model_name": "terrasignal-risk-scorer"},
        )
    ).mappings().first()

    latest = None
    if latest_pred is not None:
        out = latest_pred["output"]
        shap_list = latest_pred["shap"] or []
        drivers = [
            ShapDriverOut(
                feature=d["feature"],
                label=d.get("label", FEATURE_LABELS.get(d["feature"], d["feature"])),
                value=d["value"],
                shap=d["shap"],
            )
            for d in shap_list[:8]
        ]
        latest = RiskScoreResponse(
            prediction_id=latest_pred["prediction_id"],
            tenant_id=tenant_id,
            tenant_name=tenant_row["name"],
            pd=float(out["pd"]),
            band=model_service.band(float(out["pd"])),
            as_of=latest_pred["as_of"],
            model_version=latest_pred["model_version"],
            baseline_mode=latest_pred["baseline_mode"],
            drivers=drivers,
        )

    await audit(
        session, request, user,
        event_type="tenant.viewed", entity_type="tenant", entity_id=tenant_id,
        payload={},
    )
    await session.commit()

    return TenantDetail(
        tenant_id=tenant_id,
        name=tenant_row["name"],
        industry=tenant_row["industry_naics"],
        credit_rating=tenant_row["credit_rating"],
        latest=latest,
        payment_history=[PaymentRow(**dict(p)) for p in payments],
        leases=[TenantLease(**dict(le)) for le in leases],
        score_history=[
            {"as_of": str(h["as_of"]), "pd": float(h["output"]["pd"]),
             "model_version": h["model_version"]}
            for h in history
        ],
    )
