"""API schemas (Pydantic v2). The OpenAPI spec generated from these is the
contract the frontend's TypeScript types are generated from — never edit the
TS types by hand."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str
    name: str


class ShapDriverOut(BaseModel):
    feature: str
    label: str
    value: float
    shap: float


class RiskScoreRequest(BaseModel):
    tenant_id: str


class RiskScoreResponse(BaseModel):
    prediction_id: uuid.UUID
    tenant_id: str
    tenant_name: str
    pd: float = Field(description="Calibrated probability of default within 6 months")
    band: Literal["green", "amber", "red"]
    as_of: date
    model_version: int
    baseline_mode: bool
    drivers: list[ShapDriverOut]


class RiskQueueItem(BaseModel):
    prediction_id: uuid.UUID
    tenant_id: str
    tenant_name: str
    industry: str
    credit_rating: str | None
    pd: float
    band: Literal["green", "amber", "red"]
    model_version: int
    baseline_mode: bool
    top_driver: str
    monthly_rent_due: float
    trend: list[float] = Field(description="Monthly mean days-late, last 12 months")


class PaymentRow(BaseModel):
    due_date: date
    paid_date: date | None
    amount_due: float
    amount_paid: float
    days_late: int | None
    lease_id: str


class TenantLease(BaseModel):
    lease_id: str
    unit_id: str
    property_name: str
    submarket: str
    asset_class: str
    commencement: date
    expiration: date
    base_rent_psf: float
    term_months: int
    lease_type: str
    unit_rsf: int


class TenantDetail(BaseModel):
    tenant_id: str
    name: str
    industry: str
    credit_rating: str | None
    latest: RiskScoreResponse | None
    payment_history: list[PaymentRow]
    leases: list[TenantLease]
    score_history: list[dict[str, Any]]


class RentForecastRequest(BaseModel):
    unit_id: str


class CompOut(BaseModel):
    comp_id: str
    submarket: str
    signed_date: str
    rent_psf: float
    term_months: int
    ti_allowance_psf: float
    free_rent_months: int


class RentForecastResponse(BaseModel):
    prediction_id: uuid.UUID
    unit_id: str
    property_name: str
    submarket: str
    asset_class: str
    unit_rsf: float
    p10: float
    p50: float
    p90: float
    current_rent_psf: float
    comp_median_rent_6m: float
    lease_expiration: date
    current_tenant_id: str | None
    as_of: date
    model_version: int
    baseline_mode: bool
    drivers: list[ShapDriverOut]
    comps: list[CompOut]


class RentQueueItem(BaseModel):
    prediction_id: uuid.UUID
    unit_id: str
    property_name: str
    submarket: str
    market: str
    asset_class: str
    unit_rsf: int
    floor: int
    p50: float
    p10: float
    p90: float
    current_rent_psf: float
    upside_pct: float
    lease_expiration: date
    baseline_mode: bool


class RationaleResponse(BaseModel):
    prediction_id: uuid.UUID
    memo: str
    backend: str
    payload_hash: str
    guard_passed: bool
    fallback_used: bool
    label: str = "AI-generated explanation"


class FeedbackRequest(BaseModel):
    prediction_id: uuid.UUID
    action: Literal["accept", "override"]
    reason_code: str | None = None
    comment: str | None = None
    override_value: dict[str, Any] | None = None


class FeedbackResponse(BaseModel):
    feedback_id: uuid.UUID
    prediction_id: uuid.UUID
    action: str
    recorded_at: datetime


class AuditEventOut(BaseModel):
    event_id: uuid.UUID
    occurred_at: datetime
    actor: str
    actor_role: str
    event_type: str
    entity_type: str
    entity_id: str
    request_id: str | None
    payload: dict[str, Any]


class ModelVersionOut(BaseModel):
    model_name: str
    version: int
    status: str
    created_at: datetime
    metrics: dict[str, float]
    baseline_metrics: dict[str, dict[str, float]]
    eval_set_hash: str
    training_snapshot_uri: str
    dq_report_uri: str
    git_sha: str
    model_card_path: str
    approved_by: str | None
    approved_at: datetime | None


class DriftMetricOut(BaseModel):
    model_name: str
    feature_name: str
    psi: float
    status: Literal["green", "amber", "red"]
    computed_at: datetime
    baseline_window: str
    current_window: str


class LineageOut(BaseModel):
    prediction_id: uuid.UUID
    created_at: datetime
    model_name: str
    model_version: int
    entity_type: str
    entity_id: str
    as_of: date
    baseline_mode: bool
    features: dict[str, float]
    output: dict[str, Any]
    training_snapshot_uri: str | None
    dq_report_uri: str | None
    git_sha: str | None
    eval_set_hash: str | None
    model_metrics: dict[str, float] | None
    approved_by: str | None
    approved_at: datetime | None
    feedback: list[dict[str, Any]]


class KillSwitchRequest(BaseModel):
    baseline_mode: bool
    reason: str


class KillSwitchState(BaseModel):
    baseline_mode: bool


class ExpirationMonth(BaseModel):
    month: date
    leases_expiring: int
    annual_rent_expiring: float


class PortfolioSummary(BaseModel):
    as_of: date
    n_properties: int
    n_units: int
    total_rsf: int
    active_leases: int
    noi_at_risk_annual: float
    watchlist_count: int
    avg_pd: float
    risk_histogram: list[dict[str, float]]
    expiration_wall: list[ExpirationMonth]
    renewal_upside_annual: float
