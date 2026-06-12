"""Append-only writer for the audit_events table.

The table is created by each project's migrations (same shape, convention over
import). A DB trigger forbids UPDATE/DELETE; this writer only ever INSERTs.
"""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Uuid
from sqlalchemy.ext.asyncio import AsyncSession

from shared.audit.schemas import AuditEvent

_metadata = MetaData()

audit_events_table = Table(
    "audit_events",
    _metadata,
    Column("event_id", Uuid, primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("actor", String, nullable=False),
    Column("actor_role", String, nullable=False),
    Column("event_type", String, nullable=False),
    Column("entity_type", String, nullable=False),
    Column("entity_id", String, nullable=False),
    Column("request_id", String, nullable=True),
    Column("payload", JSON, nullable=False),
)


async def write_audit_event(session: AsyncSession, event: AuditEvent) -> None:
    """Insert one audit event inside the caller's transaction.

    Sharing the caller's transaction is deliberate: a state change and its
    audit record commit or roll back together.
    """
    await session.execute(
        audit_events_table.insert().values(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            actor=event.actor,
            actor_role=event.actor_role,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            request_id=event.request_id,
            payload=event.payload,
        )
    )
