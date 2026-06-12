"""Typed payloads handed to rationale backends.

The payload is the *only* source of numbers a memo may contain. It is stored
(hashed) with the prediction for audit, so a memo can always be checked against
exactly what the model produced.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ShapDriver(BaseModel):
    feature: str
    label: str  # human-readable, e.g. "Payment timing trend (6m)"
    value: float  # the feature's value for this entity
    shap: float  # signed contribution in output units


class CompRecord(BaseModel):
    comp_id: str
    submarket: str
    signed_date: str  # ISO date
    rent_psf: float
    term_months: int
    ti_allowance_psf: float
    free_rent_months: int


class RationalePayload(BaseModel):
    """Grounding context for a rent-forecast rationale memo."""

    unit_id: str
    property_name: str
    submarket: str
    asset_class: str
    horizon_months: int
    p10_rent_psf: float
    p50_rent_psf: float
    p90_rent_psf: float
    current_rent_psf: float
    submarket_median_rent_psf: float
    drivers: list[ShapDriver] = Field(max_length=6)
    comps: list[CompRecord] = Field(max_length=5)
