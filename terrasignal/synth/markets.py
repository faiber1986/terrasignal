"""Synthetic market universe: markets, submarkets, asset-class rent curves.

Rent levels follow smooth per-(submarket, asset_class) curves over time with
distinct regimes (office softening post-2023, industrial compressing upward).
The Rent Forecaster's job is to recover these curves from comps — so the
curves must exist and must NOT be flat noise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

OBS_START = date(2021, 7, 1)
OBS_END = date(2026, 6, 1)  # "today" for the demo
ASSET_CLASSES = ("office", "retail", "industrial")

# $/SF/yr baseline at OBS_START and annual drift rate per asset class
_BASE_RENT = {"office": 38.0, "retail": 30.0, "industrial": 11.0}
_ANNUAL_DRIFT = {"office": -0.015, "retail": 0.01, "industrial": 0.055}


@dataclass(frozen=True)
class Submarket:
    market: str
    name: str
    quality: float  # multiplier vs market baseline, ~0.8–1.3


SUBMARKETS: list[Submarket] = [
    Submarket("Atlanta", "Midtown", 1.22),
    Submarket("Atlanta", "Buckhead", 1.28),
    Submarket("Atlanta", "Airport South", 0.84),
    Submarket("Dallas", "Uptown", 1.25),
    Submarket("Dallas", "Las Colinas", 1.02),
    Submarket("Dallas", "South Stemmons", 0.82),
    Submarket("Charlotte", "South End", 1.18),
    Submarket("Charlotte", "University City", 0.90),
    Submarket("Charlotte", "Airport West", 0.86),
    Submarket("Nashville", "The Gulch", 1.30),
    Submarket("Nashville", "Metro Center", 0.95),
    Submarket("Nashville", "Airport North", 0.88),
]

NAICS_SECTORS = {
    "23": ("Construction", 1.25),
    "31": ("Manufacturing", 1.05),
    "44": ("Retail Trade", 1.35),
    "48": ("Transportation & Warehousing", 1.10),
    "51": ("Information", 0.95),
    "52": ("Finance & Insurance", 0.70),
    "54": ("Professional Services", 0.80),
    "56": ("Administrative Services", 1.20),
    "62": ("Health Care", 0.65),
    "72": ("Accommodation & Food", 1.50),
}
# second element: relative default-risk multiplier (distress index by sector)


def months_since_start(d: date) -> float:
    return (d.year - OBS_START.year) * 12 + (d.month - OBS_START.month) + (d.day - 1) / 30.0


def market_rent_psf(submarket: Submarket, asset_class: str, when: date) -> float:
    """Deterministic market rent level (before idiosyncratic noise).

    Curve = baseline * quality * (1+drift)^years * a mild cyclical wobble.
    Office takes an extra step-down after mid-2023 (the regime change that
    makes random train/test splits leak — see ADR on time-based splits).
    """
    years = months_since_start(when) / 12.0
    level = _BASE_RENT[asset_class] * submarket.quality
    level *= (1.0 + _ANNUAL_DRIFT[asset_class]) ** years
    # cyclical wobble, ±2%, period ~3 years, phase varies by submarket name hash
    import math

    phase = (hash(submarket.name) % 12) / 12.0 * 2 * math.pi
    level *= 1.0 + 0.02 * math.sin(2 * math.pi * years / 3.0 + phase)
    if asset_class == "office" and when >= date(2023, 7, 1):
        level *= 0.94
    return level
