"""Audit event schema. Every state change in either project becomes one of these.

Events are append-only: corrections are new events, never updates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str
    actor_role: str
    event_type: str  # e.g. prediction.scored, feedback.override, model.approved
    entity_type: str  # e.g. tenant, unit, model_version, prediction
    entity_id: str
    request_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
