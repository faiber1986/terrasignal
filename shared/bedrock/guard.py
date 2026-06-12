"""Numeric guard: no number reaches a user that the engine didn't produce.

Every numeric token in a generated memo must exist in the grounding payload
(string-matched on normalized values, tolerant of display rounding). A memo
that fails the guard is discarded — regenerated once, then replaced by the
minimal fallback template.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

# $1,234.56 | 12.3% | 42.50 | 1,200 — capture the bare numeric part
_NUMBER_RE = re.compile(r"\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?%?")


class GuardViolation(BaseModel):
    token: str
    normalized: str


def _normalize(integer_part: str, decimal_part: str | None) -> Decimal:
    raw = integer_part.replace(",", "") + (decimal_part or "")
    return Decimal(raw)


def extract_numbers(text: str) -> list[tuple[str, Decimal]]:
    """All numeric tokens in display text, as (original token, normalized value)."""
    out: list[tuple[str, Decimal]] = []
    for m in _NUMBER_RE.finditer(text):
        try:
            out.append((m.group(0), _normalize(m.group(1), m.group(2))))
        except InvalidOperation:  # pragma: no cover - regex guarantees validity
            continue
    return out


def _collect_payload_numbers(value: Any, acc: set[Decimal]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        acc.add(Decimal(value))
    elif isinstance(value, float):
        acc.add(Decimal(str(value)))
    elif isinstance(value, str):
        # numbers embedded in strings (dates, IDs) are legitimate grounding too
        for _, num in extract_numbers(value):
            acc.add(num)
    elif isinstance(value, dict):
        for v in value.values():
            _collect_payload_numbers(v, acc)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _collect_payload_numbers(v, acc)


def _matches(memo_num: Decimal, payload_nums: set[Decimal]) -> bool:
    if memo_num in payload_nums:
        return True
    # display rounding: $42.5 must match payload 42.51; -0.8 must match -0.812
    exponent = memo_num.as_tuple().exponent
    digits = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    quantum = Decimal(1).scaleb(-digits)
    for p in payload_nums:
        if p.quantize(quantum) == memo_num or (-p).quantize(quantum) == memo_num:
            return True
    return False


def numeric_guard(memo: str, payload: dict[str, Any]) -> list[GuardViolation]:
    """Return violations: memo numbers absent from the payload. Empty = pass."""
    payload_nums: set[Decimal] = set()
    _collect_payload_numbers(payload, payload_nums)
    violations = []
    for token, num in extract_numbers(memo):
        if not _matches(num, payload_nums):
            violations.append(GuardViolation(token=token, normalized=str(num)))
    return violations
