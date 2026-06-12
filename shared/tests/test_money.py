from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shared.core import DateRange, Money, Pct

cents = st.integers(min_value=-10**12, max_value=10**12)


@given(cents, cents)
def test_add_sub_roundtrip(a: int, b: int) -> None:
    ma, mb = Money(cents=a), Money(cents=b)
    assert (ma + mb) - mb == ma


@given(cents, st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=12))
def test_allocate_sums_exactly(total: int, weights: list[int]) -> None:
    if sum(weights) == 0:
        weights[0] = 1
    parts = Money(cents=total).allocate(weights)
    assert sum(p.cents for p in parts) == total


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        Money.from_decimal(1.23)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(cents=100).scale(1.5)  # type: ignore[arg-type]


def test_money_construction_and_display() -> None:
    m = Money.from_str("1234.565")
    assert m.cents == 123457  # half-up
    assert str(m) == "$1,234.57"
    assert str(Money(cents=-50)) == "-$0.50"


def test_currency_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        Money(cents=1, currency="USD") + Money(cents=1, currency="EUR")


def test_pct() -> None:
    p = Pct.from_percent("3")
    assert p.fraction == Decimal("0.03")
    assert str(p) == "3%"
    with pytest.raises(TypeError):
        Pct.from_percent(3.0)  # type: ignore[arg-type]


def test_date_range() -> None:
    from datetime import date

    r = DateRange(start=date(2024, 1, 15), end=date(2026, 1, 14))
    assert r.contains(date(2025, 6, 1))
    assert not r.contains(date(2026, 2, 1))
    assert r.months == 24
    with pytest.raises(ValueError):
        DateRange(start=date(2024, 1, 2), end=date(2024, 1, 1))
