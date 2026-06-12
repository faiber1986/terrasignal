import numpy as np
from hypothesis import given
from hypothesis import strategies as st

from terrasignal.features.finmath import (
    effective_rent_psf,
    least_squares_slope,
    npv,
    straight_line_rent_psf,
)


def test_slope_recovers_known_trend() -> None:
    y = np.array([1.0, 3.0, 5.0, 7.0])
    assert abs(least_squares_slope(y) - 2.0) < 1e-12


def test_slope_handles_nans_and_degenerate_input() -> None:
    assert least_squares_slope(np.array([np.nan, 2.0])) == 0.0
    assert least_squares_slope(np.array([5.0])) == 0.0
    assert abs(least_squares_slope(np.array([1.0, np.nan, 3.0]))) - 1.0 < 1e-9


@given(st.floats(min_value=0.0, max_value=0.3))
def test_npv_below_undiscounted_sum_for_positive_rates(rate: float) -> None:
    cf = np.full(24, 100.0)
    value = npv(cf, rate)
    assert value <= cf.sum() + 1e-9
    if rate > 1e-6:
        assert value < cf.sum()


@given(
    st.floats(min_value=5.0, max_value=80.0),
    st.floats(min_value=0.0, max_value=0.05),
    st.integers(min_value=12, max_value=120),
)
def test_straight_line_at_least_base_rent(base: float, esc: float, term: int) -> None:
    """Escalations only go up, so straight-lined rent >= year-1 base rent."""
    assert straight_line_rent_psf(base, esc, term) >= base - 1e-9


@given(
    st.floats(min_value=5.0, max_value=80.0),
    st.integers(min_value=12, max_value=120),
    st.integers(min_value=0, max_value=6),
    st.floats(min_value=0.0, max_value=60.0),
)
def test_effective_rent_never_exceeds_face_rent(
    base: float, term: int, free: int, ti: float
) -> None:
    """Concessions only subtract: net-effective <= straight-lined face rent."""
    eff = effective_rent_psf(base, 0.03, term, free, ti)
    face = straight_line_rent_psf(base, 0.03, term)
    assert eff <= face + 1e-6


def test_effective_rent_monotone_in_concessions() -> None:
    base = effective_rent_psf(40.0, 0.03, 60, 0, 0.0)
    with_free = effective_rent_psf(40.0, 0.03, 60, 3, 0.0)
    with_ti = effective_rent_psf(40.0, 0.03, 60, 0, 50.0)
    assert with_free < base
    assert with_ti < base
