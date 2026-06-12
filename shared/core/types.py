"""Core domain value types.

Money is integer cents — financial math never touches floats. Floats are
permitted only inside model feature matrices, at the very edge of the system.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

CENTS = Decimal("0.01")


class Money(BaseModel):
    """An exact amount of money stored as integer cents.

    Construct via `Money.from_decimal(...)`, `Money.from_str(...)` or
    `Money(cents=...)`. Floats are rejected at the boundary on purpose.
    """

    model_config = ConfigDict(frozen=True)

    cents: int
    currency: str = "USD"

    @classmethod
    def from_decimal(cls, amount: Decimal | int | str, currency: str = "USD") -> Self:
        if isinstance(amount, float):  # defensive: pydantic would coerce silently
            raise TypeError("Money must not be built from float; use Decimal or str")
        quantized = Decimal(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
        return cls(cents=int(quantized * 100), currency=currency)

    @classmethod
    def from_str(cls, amount: str, currency: str = "USD") -> Self:
        return cls.from_decimal(Decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str = "USD") -> Self:
        return cls(cents=0, currency=currency)

    @property
    def amount(self) -> Decimal:
        return Decimal(self.cents) / 100

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(cents=self.cents + other.cents, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(cents=self.cents - other.cents, currency=self.currency)

    def __neg__(self) -> Money:
        return Money(cents=-self.cents, currency=self.currency)

    def scale(self, factor: Decimal | int) -> Money:
        """Multiply by an exact factor, rounding half-up to the cent."""
        if isinstance(factor, float):
            raise TypeError("scale factor must be Decimal or int, not float")
        scaled = (Decimal(self.cents) * Decimal(factor)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return Money(cents=int(scaled), currency=self.currency)

    def allocate(self, weights: list[int]) -> list[Money]:
        """Split into parts proportional to integer weights; remainder cents go
        to the earliest parts so the result always sums exactly to self."""
        if not weights or any(w < 0 for w in weights) or sum(weights) == 0:
            raise ValueError("weights must be non-empty, non-negative, with positive sum")
        total = sum(weights)
        base = [self.cents * w // total for w in weights]
        remainder = self.cents - sum(base)
        for i in range(abs(remainder)):
            base[i % len(base)] += 1 if remainder > 0 else -1
        return [Money(cents=c, currency=self.currency) for c in base]

    def __lt__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.cents < other.cents

    def __le__(self, other: Money) -> bool:
        self._check_currency(other)
        return self.cents <= other.cents

    def __str__(self) -> str:
        sign = "-" if self.cents < 0 else ""
        return f"{sign}${abs(self.amount):,.2f}"


class Pct(BaseModel):
    """A percentage stored as an exact Decimal fraction (0.03 == 3%)."""

    model_config = ConfigDict(frozen=True)

    fraction: Decimal

    @classmethod
    def from_percent(cls, percent: Decimal | int | str) -> Self:
        if isinstance(percent, float):
            raise TypeError("Pct must not be built from float; use Decimal or str")
        return cls(fraction=Decimal(percent) / 100)

    @property
    def percent(self) -> Decimal:
        return self.fraction * 100

    def __str__(self) -> str:
        return f"{self.percent.normalize():f}%"


class DateRange(BaseModel):
    """A closed date interval [start, end] with end >= start."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"end {self.end} precedes start {self.start}")
        return self

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    @property
    def months(self) -> int:
        """Whole calendar months spanned, counting partial last month."""
        return (
            (self.end.year - self.start.year) * 12
            + (self.end.month - self.start.month)
            + (1 if self.end.day >= self.start.day else 0)
        )
