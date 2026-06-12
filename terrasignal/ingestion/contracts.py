"""Layer 2 — Polars contracts: schema-level and statistical checks.

These run on the raw frames *after* layer-1 violations are known, but check
different things: budgets and distributions rather than referential rules.
"""

from __future__ import annotations

import polars as pl
from pydantic import BaseModel


class ContractViolations(BaseModel):
    rule: str
    table: str
    pks: list[str]


def check_escalation_null_budget(leases: pl.DataFrame, budget: float = 0.02) -> ContractViolations | None:
    """escalation_pct nulls must stay within budget; beyond it, the *batch* is
    suspect — we flag the null rows so the report shows scale."""
    null_rows = leases.filter(pl.col("escalation_pct").is_null())
    if leases.height and null_rows.height / leases.height > budget:
        return ContractViolations(
            rule="escalation_null_budget_exceeded",
            table="leases",
            pks=null_rows["lease_id"].to_list(),
        )
    return None


def check_rent_distribution(
    leases: pl.DataFrame, comps: pl.DataFrame, trailing_months: int = 24
) -> ContractViolations:
    """base_rent_psf must sit within a generous band around the trailing-market
    percentile window for its asset class. Catches fat-finger entries
    ($4,250/SF typed instead of $42.50) without flagging merely old leases."""
    recent = comps.filter(
        (pl.col("rent_psf") > 0)
        & (pl.col("signed_date") >= pl.col("signed_date").max() - pl.duration(days=trailing_months * 30))
    )
    bands = recent.group_by("asset_class").agg(
        lo=pl.col("rent_psf").quantile(0.005) * 0.4,
        hi=pl.col("rent_psf").quantile(0.995) * 2.0,
    )
    # leases don't carry asset_class; join through their unit→property is done
    # by the caller, which passes a frame already enriched with asset_class.
    flagged = (
        leases.join(bands, on="asset_class", how="left")
        .filter(
            (pl.col("base_rent_psf") > pl.col("hi")) | (pl.col("base_rent_psf") < pl.col("lo"))
        )
    )
    return ContractViolations(
        rule="rent_outside_market_band",
        table="leases",
        pks=flagged["lease_id"].to_list(),
    )


def check_negative_paid(payments: pl.DataFrame) -> ContractViolations:
    flagged = payments.filter(pl.col("amount_paid") < 0)
    return ContractViolations(
        rule="negative_amount_paid", table="payments", pks=flagged["payment_id"].to_list()
    )
