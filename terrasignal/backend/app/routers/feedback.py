"""Analyst feedback: accept / override-with-reason. Overrides are first-class
data — a quarterly job reports override rates by segment."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from terrasignal.backend.app import queries
from terrasignal.backend.app.audit import audit
from terrasignal.backend.app.auth import User, require_role
from terrasignal.backend.app.db import get_session
from terrasignal.backend.app.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])

REASON_CODES = {
    "market_knowledge", "tenant_relationship", "data_quality_concern",
    "strategic_decision", "model_distrust", "other",
}


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> FeedbackResponse:
    prediction = (
        await session.execute(
            text(queries.PREDICTION_BY_ID), {"prediction_id": body.prediction_id}
        )
    ).mappings().first()
    if prediction is None:
        raise HTTPException(404, "prediction not found")
    if body.action == "override":
        if not body.reason_code:
            raise HTTPException(422, "override requires a structured reason_code")
        if body.reason_code not in REASON_CODES:
            raise HTTPException(422, f"reason_code must be one of {sorted(REASON_CODES)}")

    feedback_id = uuid.uuid4()
    now = datetime.now(UTC)
    await session.execute(
        text(queries.INSERT_FEEDBACK),
        {
            "feedback_id": feedback_id,
            "prediction_id": body.prediction_id,
            "created_at": now,
            "actor": user.username,
            "action": body.action,
            "reason_code": body.reason_code,
            "comment": body.comment,
            "override_value": json.dumps(body.override_value) if body.override_value else None,
        },
    )
    await audit(
        session, request, user,
        event_type=f"feedback.{body.action}",
        entity_type=prediction["entity_type"],
        entity_id=prediction["entity_id"],
        payload={
            "prediction_id": str(body.prediction_id),
            "reason_code": body.reason_code,
            "override_value": body.override_value,
        },
    )
    await session.commit()
    return FeedbackResponse(
        feedback_id=feedback_id,
        prediction_id=body.prediction_id,
        action=body.action,
        recorded_at=now,
    )
