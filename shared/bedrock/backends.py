"""Rationale backends behind one interface.

TemplateMemoBackend is the active local-demo backend: deterministic prose built
exclusively from payload values, so the guard passes by construction (we still
run it — the seam must stay tested). BedrockBackend is the production path and
fails loudly without AWS credentials instead of pretending.
"""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from pydantic import BaseModel

from shared.bedrock.guard import GuardViolation, numeric_guard
from shared.bedrock.payloads import RationalePayload

BEDROCK_SYSTEM_PROMPT = """\
You are a commercial real estate analyst writing a forecast rationale memo.
You will receive a JSON payload with a prediction range, SHAP drivers and comps.
HARD RULES:
- Use ONLY numbers present in the payload. Never compute, derive or invent figures.
- Attribute the forecast to the listed drivers; do not speculate beyond them.
- Three short paragraphs: the range, the drivers, the comp context.
"""


class MemoResult(BaseModel):
    memo: str
    backend: str
    payload_hash: str
    guard_violations: list[GuardViolation]
    guard_passed: bool
    fallback_used: bool = False


class RationaleBackend(Protocol):
    name: str

    def generate(self, payload: RationalePayload) -> str: ...


def _payload_hash(payload: RationalePayload) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


class TemplateMemoBackend:
    """Deterministic memo composed from payload values only."""

    name = "template-v1"

    def generate(self, payload: RationalePayload) -> str:
        p = payload
        direction = "above" if p.p50_rent_psf >= p.current_rent_psf else "below"
        lines = [
            f"Over a {p.horizon_months}-month horizon, the model projects an achievable "
            f"base rent of ${_fmt(p.p50_rent_psf)}/SF/yr for unit {p.unit_id} at "
            f"{p.property_name} ({p.submarket}, {p.asset_class}), with a likely range of "
            f"${_fmt(p.p10_rent_psf)} to ${_fmt(p.p90_rent_psf)}. That midpoint sits "
            f"{direction} the current in-place rent of ${_fmt(p.current_rent_psf)} and "
            f"compares with a submarket median of ${_fmt(p.submarket_median_rent_psf)}.",
        ]
        if p.drivers:
            driver_bits = []
            for d in p.drivers:
                verb = "lifted" if d.shap >= 0 else "lowered"
                driver_bits.append(
                    f"{d.label} (value {_fmt(d.value)}) {verb} the forecast by "
                    f"${_fmt(abs(d.shap))}/SF"
                )
            lines.append("Key drivers: " + "; ".join(driver_bits) + ".")
        if p.comps:
            comp_bits = [
                f"{c.comp_id} signed {c.signed_date} at ${_fmt(c.rent_psf)}/SF for "
                f"{c.term_months} months ({c.free_rent_months} months free rent, "
                f"${_fmt(c.ti_allowance_psf)}/SF TI)"
                for c in p.comps
            ]
            lines.append("Nearest comparables: " + "; ".join(comp_bits) + ".")
        return "\n\n".join(lines)


class FallbackMemoBackend:
    """Minimal memo used when a richer memo fails the numeric guard."""

    name = "fallback-minimal"

    def generate(self, payload: RationalePayload) -> str:
        p = payload
        return (
            f"Model forecast for unit {p.unit_id}: ${_fmt(p.p50_rent_psf)}/SF/yr "
            f"(range ${_fmt(p.p10_rent_psf)}–${_fmt(p.p90_rent_psf)}) over "
            f"{p.horizon_months} months. See SHAP drivers and comps panels for detail."
        )


class BedrockBackend:
    """Production path: Claude via Amazon Bedrock. Stub locally — fails loudly.

    Wiring it up means: boto3 bedrock-runtime client, BEDROCK_SYSTEM_PROMPT,
    payload JSON as the user message, structured-output parse. The guard and
    fallback logic in generate_with_guard stay exactly the same.
    """

    name = "bedrock-claude"

    def __init__(self, model_id: str = "anthropic.claude-sonnet-4-5") -> None:
        self.model_id = model_id

    def generate(self, payload: RationalePayload) -> str:
        raise RuntimeError(
            "BedrockBackend requires AWS credentials and is not enabled in the "
            "local demo. Set RATIONALE_BACKEND=template or configure AWS."
        )


def generate_with_guard(backend: RationaleBackend, payload: RationalePayload) -> MemoResult:
    """Generate → guard → regenerate once → fall back. Gates are code, not prompts."""
    payload_dict = payload.model_dump(mode="json")
    phash = _payload_hash(payload)

    for _attempt in range(2):
        memo = backend.generate(payload)
        violations = numeric_guard(memo, payload_dict)
        if not violations:
            return MemoResult(
                memo=memo,
                backend=backend.name,
                payload_hash=phash,
                guard_violations=[],
                guard_passed=True,
            )

    fallback = FallbackMemoBackend()
    memo = fallback.generate(payload)
    violations = numeric_guard(memo, payload_dict)
    return MemoResult(
        memo=memo,
        backend=fallback.name,
        payload_hash=phash,
        guard_violations=violations,
        guard_passed=not violations,
        fallback_used=True,
    )
