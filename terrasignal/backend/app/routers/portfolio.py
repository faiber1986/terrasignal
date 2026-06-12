"""Portfolio dashboard API: NOI-at-risk, the 18-month expiration wall, and the
risk-score distribution. Read-only aggregates over the latest prediction per
entity — the same persisted predictions that power the queues and the audit
trail, so the dashboard never disagrees with the drill-downs."""

from __future__ import annotations

from datetime import date

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from terrasignal.backend.app import queries
from terrasignal.backend.app.auth import User, require_role
from terrasignal.backend.app.db import get_session
from terrasignal.backend.app.models_service import model_service
from terrasignal.backend.app.schemas import ExpirationMonth, PortfolioSummary
from terrasignal.settings import governed_thresholds

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

HISTOGRAM_EDGES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 1.0]


def _risk_histogram(pds: list[float]) -> list[dict[str, float]]:
    """Fixed-edge buckets so the chart's x-axis is stable across refreshes and
    aligns with the governed amber (0.15) / red (0.30) band boundaries."""
    arr = np.asarray(pds, dtype=float)
    buckets = []
    for lo, hi in zip(HISTOGRAM_EDGES[:-1], HISTOGRAM_EDGES[1:], strict=True):
        count = int(((arr >= lo) & (arr < hi)).sum()) if arr.size else 0
        buckets.append({"lo": lo, "hi": hi, "count": float(count)})
    return buckets


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("analyst")),
) -> PortfolioSummary:
    today: date = model_service.as_of

    kpis = (
        await session.execute(text(queries.PORTFOLIO_KPIS), {"today": today})
    ).mappings().one()

    pd_rows = (await session.execute(text(queries.PORTFOLIO_RISK_PDS))).mappings().all()
    pds = [float(r["pd"]) for r in pd_rows]
    # Watchlist = top decile by PD (governed `watchlist_decile`); fall back to a
    # value above any real PD when there are no scores yet so counts read zero.
    decile = float(governed_thresholds()["risk_scorer"]["watchlist_decile"])
    watchlist_pd = float(np.quantile(pds, 1.0 - decile)) if pds else 1.01
    watchlist_count = int(sum(1 for p in pds if p >= watchlist_pd))
    avg_pd = float(np.mean(pds)) if pds else 0.0

    noi = (
        await session.execute(
            text(queries.NOI_AT_RISK), {"watchlist_pd": watchlist_pd, "today": today}
        )
    ).scalar_one()
    upside = (await session.execute(text(queries.RENEWAL_UPSIDE))).scalar_one()

    wall_horizon = date(today.year + 1, ((today.month + 5 - 1) % 12) + 1, 1)
    wall_rows = (
        await session.execute(
            text(queries.EXPIRATION_WALL), {"today": today, "horizon": wall_horizon}
        )
    ).mappings().all()

    return PortfolioSummary(
        as_of=today,
        n_properties=int(kpis["n_properties"]),
        n_units=int(kpis["n_units"]),
        total_rsf=int(kpis["total_rsf"]),
        active_leases=int(kpis["active_leases"]),
        noi_at_risk_annual=float(noi),
        watchlist_count=watchlist_count,
        avg_pd=avg_pd,
        risk_histogram=_risk_histogram(pds),
        expiration_wall=[
            ExpirationMonth(
                month=r["month"],
                leases_expiring=int(r["leases_expiring"]),
                annual_rent_expiring=float(r["annual_rent_expiring"]),
            )
            for r in wall_rows
        ],
        renewal_upside_annual=float(upside),
    )
