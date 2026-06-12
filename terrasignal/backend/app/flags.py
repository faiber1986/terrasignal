"""Runtime flag reads (kill switch). One small query, no caching — the whole
point of a kill switch is that it takes effect immediately."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from terrasignal.backend.app import queries


async def baseline_mode(session: AsyncSession) -> bool:
    result = await session.execute(text(queries.GET_FLAG), {"key": "baseline_mode"})
    value = result.scalar_one_or_none()
    return bool(value)
