"""Audit helper for routers: same-transaction event writes with request_id."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit import AuditEvent, write_audit_event
from terrasignal.backend.app.auth import User


async def audit(
    session: AsyncSession,
    request: Request,
    user: User,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await write_audit_event(
        session,
        AuditEvent(
            actor=user.username,
            actor_role=user.role,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=getattr(request.state, "request_id", None),
            payload=payload or {},
        ),
    )
