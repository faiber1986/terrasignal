"""Layer 3 — cross-source reconciliation.

Sum of payments.amount_due per lease per month must tie to the contractual
rent schedule derived from the lease (base rent, escalations on anniversaries,
unit RSF) within tolerance. This is the check that catches upstream
property-management-system bugs that actually happen.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel


class ReconciliationResult(BaseModel):
    rule: str = "payments_vs_schedule_mismatch"
    table: str = "leases"
    pks: list[str]


def reconcile(
    leases: pl.DataFrame,
    payments: pl.DataFrame,
    units: pl.DataFrame,
    tolerance: float = 0.01,
) -> ReconciliationResult:
    """Flag leases where any month's amount_due deviates >tolerance from the
    contractual schedule. Leases without a resolvable unit are skipped — they
    are already quarantined by layer 1."""
    enriched = (
        payments.filter(pl.col("amount_due") > 0)
        .join(leases.select("lease_id", "unit_id", "commencement", "expiration",
                            "base_rent_psf", "escalation_pct"), on="lease_id", how="inner")
        .join(units.select("unit_id", "rsf"), on="unit_id", how="inner")
        .filter(
            (pl.col("base_rent_psf") > 0)
            & (pl.col("expiration") > pl.col("commencement"))
            & pl.col("due_date").is_between(pl.col("commencement"), pl.col("expiration"))
        )
        .with_columns(
            months_in=(
                (pl.col("due_date").dt.year() - pl.col("commencement").dt.year()) * 12
                + (pl.col("due_date").dt.month() - pl.col("commencement").dt.month())
            )
        )
        .with_columns(
            contractual=(
                pl.col("base_rent_psf")
                * (1.0 + pl.col("escalation_pct").fill_null(0.0)) ** (pl.col("months_in") // 12)
                * pl.col("rsf")
                / 12.0
            ).round(2)
        )
        .with_columns(
            rel_diff=((pl.col("amount_due") - pl.col("contractual")).abs() / pl.col("contractual"))
        )
    )
    flagged = (
        enriched.group_by("lease_id")
        .agg(max_rel_diff=pl.col("rel_diff").max())
        .filter(pl.col("max_rel_diff") > tolerance)
    )
    return ReconciliationResult(pks=flagged["lease_id"].to_list())
