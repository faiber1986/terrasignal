import pytest

from shared.bedrock import (
    BedrockBackend,
    CompRecord,
    RationalePayload,
    ShapDriver,
    TemplateMemoBackend,
    numeric_guard,
)
from shared.bedrock.backends import generate_with_guard


def _payload() -> RationalePayload:
    return RationalePayload(
        unit_id="U-0042",
        property_name="Meridian Plaza",
        submarket="North Loop",
        asset_class="office",
        horizon_months=12,
        p10_rent_psf=38.25,
        p50_rent_psf=42.51,
        p90_rent_psf=46.1,
        current_rent_psf=40.0,
        submarket_median_rent_psf=41.75,
        drivers=[
            ShapDriver(
                feature="comp_median_rent_6m",
                label="Submarket comp median (6m)",
                value=41.75,
                shap=1.8,
            ),
            ShapDriver(
                feature="building_vacancy",
                label="Building vacancy",
                value=0.12,
                shap=-0.85,
            ),
        ],
        comps=[
            CompRecord(
                comp_id="C-9001",
                submarket="North Loop",
                signed_date="2026-03-14",
                rent_psf=43.0,
                term_months=60,
                ti_allowance_psf=55.0,
                free_rent_months=3,
            )
        ],
    )


def test_guard_rejects_foreign_numbers() -> None:
    payload = _payload().model_dump(mode="json")
    violations = numeric_guard("The forecast is $99.99/SF over 7 months.", payload)
    assert {v.token for v in violations} == {"$99.99", "7"}


def test_guard_accepts_payload_numbers_with_display_rounding() -> None:
    payload = _payload().model_dump(mode="json")
    memo = "Range $38.25 to $46.10, midpoint $42.5, signed 2026-03-14, vacancy 0.12."
    assert numeric_guard(memo, payload) == []


def test_template_memo_passes_guard() -> None:
    result = generate_with_guard(TemplateMemoBackend(), _payload())
    assert result.guard_passed
    assert not result.fallback_used
    assert result.backend == "template-v1"
    assert "$42.51" in result.memo
    assert len(result.payload_hash) == 64


class _LyingBackend:
    name = "lying"

    def generate(self, payload: RationalePayload) -> str:
        return "Trust me, rents will hit $123.45/SF."


def test_guard_failure_falls_back_to_minimal_memo() -> None:
    result = generate_with_guard(_LyingBackend(), _payload())
    assert result.fallback_used
    assert result.backend == "fallback-minimal"
    assert result.guard_passed  # the fallback itself must be clean
    assert "$123.45" not in result.memo


def test_bedrock_stub_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="AWS credentials"):
        BedrockBackend().generate(_payload())
