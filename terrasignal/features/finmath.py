"""Vectorized financial math (NumPy). Pure functions, property-tested.

This is engine-layer code: floats are allowed here ONLY because these values
feed model feature matrices, never the system of record.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def least_squares_slope(y: NDArray[np.float64]) -> float:
    """Slope of y over its index (per-step trend). NaN-safe: needs >=2 points."""
    y = np.asarray(y, dtype=np.float64)
    mask = ~np.isnan(y)
    if mask.sum() < 2:
        return 0.0
    x = np.arange(len(y), dtype=np.float64)[mask]
    yv = y[mask]
    x_c = x - x.mean()
    denom = float((x_c**2).sum())
    if denom == 0.0:
        return 0.0
    return float((x_c * (yv - yv.mean())).sum() / denom)


def npv(cashflows: NDArray[np.float64], annual_rate: float, periods_per_year: int = 12) -> float:
    """NPV of a cashflow vector starting at period 1."""
    cf = np.asarray(cashflows, dtype=np.float64)
    r = (1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0
    t = np.arange(1, len(cf) + 1, dtype=np.float64)
    return float((cf / (1.0 + r) ** t).sum())


def effective_rent_psf(
    base_rent_psf: float,
    escalation_pct: float,
    term_months: int,
    free_rent_months: int,
    ti_allowance_psf: float,
    annual_discount_rate: float = 0.08,
) -> float:
    """Net-effective rent: NPV of escalated rent net of concessions, levelized
    back to a $/SF/yr figure over the term."""
    if term_months <= 0:
        return 0.0
    months = np.arange(term_months)
    monthly = base_rent_psf / 12.0 * (1.0 + escalation_pct) ** (months // 12)
    monthly[: min(free_rent_months, term_months)] = 0.0
    total_npv = npv(monthly, annual_discount_rate) - ti_allowance_psf
    # levelize: constant monthly payment with the same NPV
    r = (1.0 + annual_discount_rate) ** (1.0 / 12.0) - 1.0
    annuity = (1.0 - (1.0 + r) ** -term_months) / r
    return float(total_npv / annuity * 12.0)


def straight_line_rent_psf(base_rent_psf: float, escalation_pct: float, term_months: int) -> float:
    """GAAP straight-lined average rent over the term, $/SF/yr."""
    if term_months <= 0:
        return 0.0
    months = np.arange(term_months)
    monthly = base_rent_psf / 12.0 * (1.0 + escalation_pct) ** (months // 12)
    return float(monthly.mean() * 12.0)
