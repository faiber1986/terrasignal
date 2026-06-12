"""Governance console APIs: registry, approvals, drift, audit trail, lineage,
model cards. The page most platforms never build."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from terrasignal.backend.app import queries
from terrasignal.backend.app.audit import audit
from terrasignal.backend.app.auth import User, require_role
from terrasignal.backend.app.db import get_session
from terrasignal.backend.app.flags import baseline_mode
from terrasignal.backend.app.schemas import (
    AuditEventOut,
    DriftMetricOut,
    KillSwitchRequest,
    KillSwitchState,
    LineageOut,
    ModelVersionOut,
)

router = APIRouter(tags=["governance"])


@router.get("/models/active", response_model=list[ModelVersionOut])
async def models_active(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> list[ModelVersionOut]:
    rows = (await session.execute(text(queries.REGISTRY_ALL))).mappings().all()
    return [
        ModelVersionOut(
            model_name=r["model_name"], version=r["version"], status=r["status"],
            created_at=r["created_at"], metrics=r["metrics"],
            baseline_metrics=r["baseline_metrics"], eval_set_hash=r["eval_set_hash"],
            training_snapshot_uri=r["training_snapshot_uri"],
            dq_report_uri=r["dq_report_uri"], git_sha=r["git_sha"],
            model_card_path=r["model_card_path"], approved_by=r["approved_by"],
            approved_at=r["approved_at"],
        )
        for r in rows
    ]


@router.post("/models/{model_name}/versions/{version}/approve")
def approve(
    model_name: str,
    version: int,
    user: User = Depends(require_role("approver")),
) -> dict[str, str]:
    """Human approval gate. Runs sync (registry helper) in the threadpool."""
    from terrasignal.training.registry import approve_model

    try:
        approve_model(model_name, version, approver=user.username)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
    return {"status": "Approved", "model": model_name, "version": str(version),
            "note": "restart backend to serve the newly approved version"}


@router.get("/governance/drift", response_model=list[DriftMetricOut])
async def drift(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> list[DriftMetricOut]:
    rows = (await session.execute(text(queries.DRIFT_LATEST))).mappings().all()
    return [DriftMetricOut(**dict(r)) for r in rows]


@router.get("/governance/audit", response_model=list[AuditEventOut])
async def audit_trail(
    request: Request,
    event_type: str | None = None,
    entity_id: str | None = None,
    actor: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("approver")),
) -> list[AuditEventOut]:
    rows = (
        await session.execute(
            text(queries.AUDIT_TRAIL),
            {"event_type": event_type, "entity_id": entity_id, "actor": actor,
             "limit": limit, "offset": offset},
        )
    ).mappings().all()
    return [AuditEventOut(**dict(r)) for r in rows]


@router.get("/governance/lineage/{prediction_id}", response_model=LineageOut)
async def lineage(
    prediction_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> LineageOut:
    row = (
        await session.execute(text(queries.LINEAGE), {"prediction_id": prediction_id})
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "prediction not found")
    feedback_rows = (
        await session.execute(
            text(queries.FEEDBACK_FOR_PREDICTION), {"prediction_id": prediction_id}
        )
    ).mappings().all()
    return LineageOut(
        prediction_id=row["prediction_id"],
        created_at=row["created_at"],
        model_name=row["model_name"],
        model_version=row["model_version"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        as_of=row["as_of"],
        baseline_mode=row["baseline_mode"],
        features=row["features"],
        output=row["output"],
        training_snapshot_uri=row["training_snapshot_uri"],
        dq_report_uri=row["dq_report_uri"],
        git_sha=row["git_sha"],
        eval_set_hash=row["eval_set_hash"],
        model_metrics=row["metrics"],
        approved_by=row["approved_by"],
        approved_at=row["approved_at"],
        feedback=[
            {
                "feedback_id": str(f["feedback_id"]),
                "action": f["action"],
                "actor": f["actor"],
                "reason_code": f["reason_code"],
                "comment": f["comment"],
                "created_at": f["created_at"].isoformat(),
            }
            for f in feedback_rows
        ],
    )


@router.get("/governance/kill-switch", response_model=KillSwitchState)
async def kill_switch_state(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> KillSwitchState:
    """Current baseline-mode flag. Analysts may read it (the UI banners on it);
    only admins may flip it."""
    return KillSwitchState(baseline_mode=await baseline_mode(session))


@router.post("/governance/kill-switch", response_model=KillSwitchState)
async def set_kill_switch(
    body: KillSwitchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("admin")),
) -> KillSwitchState:
    """Flip the API into (or out of) baseline mode without a redeploy. The flag
    lives in the DB so it survives a restart and takes effect on the next
    request; the flip is an audited action (§8.6)."""
    await session.execute(
        text(queries.SET_FLAG),
        {"key": "baseline_mode", "value": body.baseline_mode,
         "updated_at": datetime.now(UTC), "updated_by": user.username},
    )
    await audit(
        session, request, user,
        event_type="kill_switch.flipped", entity_type="runtime_flag",
        entity_id="baseline_mode",
        payload={"baseline_mode": body.baseline_mode, "reason": body.reason},
    )
    await session.commit()
    return KillSwitchState(baseline_mode=body.baseline_mode)


@router.get("/governance/cards/{model_name}/{version}", response_class=PlainTextResponse)
async def model_card(
    model_name: str,
    version: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> str:
    rows = (await session.execute(text(queries.REGISTRY_ALL))).mappings().all()
    for r in rows:
        if r["model_name"] == model_name and r["version"] == version:
            path = Path(r["model_card_path"])
            if path.exists():
                return path.read_text(encoding="utf-8")
            raise HTTPException(404, "model card file missing")
    raise HTTPException(404, "model version not found")
