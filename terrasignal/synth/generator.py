"""Core synthetic generator. One seed → one deterministic portfolio.

Embedded signals (the models must be able to find these):
- Rent curves per (submarket, asset class) over time → Rent Forecaster target.
- Distress process: ~4-5% of leases default; their payment timing drifts upward
  3–6 months before the event; disputes and adverse clauses correlate.
Everything money-related ties out: payments equal the contractual schedule
derived from the lease (escalations applied on anniversaries) — except where
dirt.py deliberately breaks it for the DQ layer to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import polars as pl

from terrasignal.synth.clauses import (
    ADVERSE_CLAUSE_TYPES,
    BENIGN_CLAUSE_TYPES,
    CLAUSE_TEMPLATES,
)
from terrasignal.synth.markets import (
    ASSET_CLASSES,
    NAICS_SECTORS,
    OBS_END,
    OBS_START,
    SUBMARKETS,
    market_rent_psf,
)

N_PROPERTIES = 200
N_TENANTS = 800

_ADJ = ["Cedar", "Summit", "Harbor", "Granite", "Lakeside", "Ironwood", "Beacon", "Crestline",
        "Palmetto", "Bluffview", "Stonegate", "Riverbend", "Oakline", "Copper", "Meridian",
        "Falcon", "Juniper", "Marble", "Pinnacle", "Quarry"]
_PNOUN = ["Plaza", "Center", "Commons", "Park", "Tower", "Crossing", "Exchange", "Yards",
          "Station", "Pointe", "Court", "Gateway", "Works", "Landing"]
_TNOUN = ["Logistics", "Analytics", "Outfitters", "Dental", "Brands", "Studios", "Foods",
          "Partners", "Systems", "Clinics", "Freight", "Supply", "Labs", "Media", "Holdings",
          "Fitness", "Staffing", "Robotics", "Interiors", "Provisions"]
_TSUF = ["LLC", "Inc", "Group", "Co"]

CREDIT_RATINGS = ["AA", "A", "BBB", "BB", "B", "CCC"]
_RATING_P = [0.05, 0.15, 0.30, 0.28, 0.16, 0.06]
_RATING_RISK = {"AA": 0.55, "A": 0.72, "BBB": 0.95, "BB": 1.15, "B": 1.45, "CCC": 1.85}

LEASE_TYPE_BY_AC = {"office": "FSG", "retail": "NNN", "industrial": "NNN"}


def _month_add(d: date, months: int) -> date:
    y, m = divmod((d.year * 12 + d.month - 1) + months, 12)
    return date(y, m + 1, 1)


@dataclass
class Portfolio:
    properties: pl.DataFrame
    units: pl.DataFrame
    tenants: pl.DataFrame
    leases: pl.DataFrame
    lease_clauses: pl.DataFrame
    payments: pl.DataFrame
    work_orders: pl.DataFrame
    market_comps: pl.DataFrame
    # ground truth kept OUT of the database — used only by tests
    default_events: dict[str, date] = field(default_factory=dict)

    def frames(self) -> dict[str, pl.DataFrame]:
        return {
            "properties": self.properties,
            "units": self.units,
            "tenants": self.tenants,
            "leases": self.leases,
            "lease_clauses": self.lease_clauses,
            "payments": self.payments,
            "work_orders": self.work_orders,
            "market_comps": self.market_comps,
        }


def _quality_adj(condition: str, year_built: int) -> float:
    cond = {"A": 1.10, "B": 1.0, "C": 0.88}[condition]
    age_penalty = max(0.0, (2026 - year_built - 15)) * 0.0025
    return cond * (1.0 - min(age_penalty, 0.12))


def _unit_adj(asset_class: str, floor: int, rsf: int) -> float:
    """Nonlinear unit-level pricing effects: view premium on office high floors,
    bulk discount for very large units, drive-in premium for small industrial."""
    adj = 1.0
    if asset_class == "office" and floor > 1:
        adj *= 1.0 + min(0.004 * (floor - 1) ** 1.3, 0.09)
    if rsf > 15_000:
        adj *= 0.94
    elif rsf < 4_000 and asset_class == "industrial":
        adj *= 1.05
    return adj


def generate(
    seed: int = 42, n_properties: int = N_PROPERTIES, n_tenants: int = N_TENANTS
) -> Portfolio:
    rng = np.random.default_rng(seed)

    # ---- properties & units -------------------------------------------------
    props: list[dict[str, object]] = []
    units: list[dict[str, object]] = []
    for i in range(n_properties):
        sm = SUBMARKETS[int(rng.integers(len(SUBMARKETS)))]
        ac = str(rng.choice(ASSET_CLASSES, p=[0.45, 0.25, 0.30]))
        cond = str(rng.choice(["A", "B", "C"], p=[0.3, 0.5, 0.2]))
        n_units = int(rng.integers(3, 13))
        unit_rsf = rng.integers(2_000, 28_000, n_units)
        pid = f"P-{i + 1:04d}"
        props.append(
            {
                "property_id": pid,
                "name": f"{_ADJ[int(rng.integers(len(_ADJ)))]} "
                        f"{_PNOUN[int(rng.integers(len(_PNOUN)))]}",
                "market": sm.market,
                "submarket": sm.name,
                "asset_class": ac,
                "year_built": int(rng.integers(1975, 2021)),
                "rsf": int(unit_rsf.sum()),
                "condition_grade": cond,
            }
        )
        for j in range(n_units):
            units.append(
                {
                    "unit_id": f"U-{len(units) + 1:05d}",
                    "property_id": pid,
                    "floor": int(rng.integers(1, 2 + (12 if ac == 'office' else 2))),
                    "rsf": int(unit_rsf[j]),
                    "condition_grade": cond if rng.random() < 0.8 else
                    str(rng.choice(["A", "B", "C"])),
                }
            )
    properties_df = pl.DataFrame(props)
    units_df = pl.DataFrame(units)
    prop_by_id = {p["property_id"]: p for p in props}

    # ---- tenants ------------------------------------------------------------
    naics_codes = list(NAICS_SECTORS.keys())
    tenants: list[dict[str, object]] = []
    for i in range(n_tenants):
        tenants.append(
            {
                "tenant_id": f"T-{i + 1:04d}",
                "name": f"{_ADJ[int(rng.integers(len(_ADJ)))]} "
                        f"{_TNOUN[int(rng.integers(len(_TNOUN)))]} "
                        f"{_TSUF[int(rng.integers(len(_TSUF)))]}",
                "industry_naics": str(rng.choice(naics_codes)),
                "credit_rating": str(rng.choice(CREDIT_RATINGS, p=_RATING_P)),
                "parent_company": None,
            }
        )
    tenants_df = pl.DataFrame(tenants, schema_overrides={"parent_company": pl.String})
    tenant_by_id = {t["tenant_id"]: t for t in tenants}
    sm_by_name = {s.name: s for s in SUBMARKETS}

    # ---- leases (sequential per unit, no overlaps) --------------------------
    leases: list[dict[str, object]] = []
    default_events: dict[str, date] = {}
    default_archetype: dict[str, str] = {}
    horizon_end = _month_add(OBS_END, 18)  # some leases extend past "today"
    for u in units:
        prop = prop_by_id[u["property_id"]]
        sm = sm_by_name[prop["submarket"]]
        ac = str(prop["asset_class"])
        cursor = date(2016, 1, 1) + timedelta(days=int(rng.integers(0, 5 * 365)))
        cursor = date(cursor.year, cursor.month, 1)
        while cursor < OBS_END:
            term = int(rng.choice([24, 36, 48, 60, 84, 120], p=[0.1, 0.25, 0.2, 0.3, 0.1, 0.05]))
            tenant = tenants[int(rng.integers(len(tenants)))]
            market_level = market_rent_psf(sm, ac, cursor)
            achieved = market_level * _quality_adj(
                str(u["condition_grade"]), int(prop["year_built"])
            ) * _unit_adj(ac, int(u["floor"]), int(u["rsf"])) * float(rng.normal(1.0, 0.035))
            esc = float(rng.choice([0.02, 0.025, 0.03, 0.035, 0.04]))
            rent = round(max(achieved, 1.0), 2)
            lease_id = f"L-{len(leases) + 1:05d}"
            expiration = _month_add(cursor, term)
            monthly_rent_y0 = rent * int(u["rsf"]) / 12.0
            leases.append(
                {
                    "lease_id": lease_id,
                    "unit_id": u["unit_id"],
                    "tenant_id": tenant["tenant_id"],
                    "commencement": cursor,
                    "expiration": expiration,
                    "base_rent_psf": rent,
                    "escalation_pct": esc,
                    "term_months": term,
                    "lease_type": LEASE_TYPE_BY_AC[ac],
                    "security_deposit": round(
                        monthly_rent_y0 * float(rng.choice([1, 2, 3], p=[0.5, 0.35, 0.15])), 2
                    ),
                }
            )
            # ---- distress assignment ----
            rating = str(tenant["credit_rating"])
            sector_risk = NAICS_SECTORS[str(tenant["industry_naics"])][1]
            rent_premium = achieved / market_level  # paying above market stresses tenants
            sector_c = 1.0 + (sector_risk - 1.0) * 0.5  # compressed sector effect
            base_p = 0.065
            p_default = base_p * _RATING_RISK[rating] * sector_c * (rent_premium ** 2)
            # threshold interaction: weak credit in a distressed sector while
            # overpaying compounds — a genuinely nonlinear effect
            if _RATING_RISK[rating] >= 1.4 and sector_risk >= 1.2 and rent_premium > 1.0:
                p_default *= 2.2
            p_default = min(0.6, p_default)
            window_start = max(_month_add(cursor, 8), _month_add(OBS_START, 10))
            window_end = min(expiration, OBS_END)
            if rng.random() < p_default and window_start < window_end:
                span = (window_end.year * 12 + window_end.month) - (
                    window_start.year * 12 + window_start.month
                )
                default_events[lease_id] = _month_add(window_start, int(rng.integers(0, span)))
                # distress archetype: gradual drifter vs sudden cliff
                default_archetype[lease_id] = (
                    "cliff" if rng.random() < 0.40 else "drift"
                )
            gap = int(rng.choice([0, 1, 2, 3, 6], p=[0.35, 0.2, 0.2, 0.15, 0.1]))
            cursor = _month_add(expiration, gap)
            if expiration >= horizon_end:
                break
    leases_df = pl.DataFrame(leases)

    # ---- payments: tie to contractual schedule ------------------------------
    rsf_by_unit = {u["unit_id"]: int(u["rsf"]) for u in units}
    pay_rows: list[dict[str, object]] = []
    for lease in leases:
        lid = str(lease["lease_id"])
        commencement: date = lease["commencement"]  # type: ignore[assignment]
        expiration_d: date = lease["expiration"]  # type: ignore[assignment]
        rsf = rsf_by_unit[str(lease["unit_id"])]
        esc = float(lease["escalation_pct"])  # type: ignore[arg-type]
        base = float(lease["base_rent_psf"])  # type: ignore[arg-type]
        d_event = default_events.get(lid)
        stop = min(expiration_d, OBS_END)
        if d_event is not None:
            stop = min(stop, _month_add(d_event, 3))  # eviction ~3 months post-default
        m = 0
        due = commencement
        while due < stop:
            if due >= OBS_START:
                amount_due = round(base * (1.0 + esc) ** (m // 12) * rsf / 12.0, 2)
                paid_date: date | None
                if d_event is not None and due >= d_event:
                    paid_date, amount_paid = None, 0.0
                else:
                    archetype = default_archetype.get(lid, "drift")
                    months_to = 999
                    if d_event is not None:
                        months_to = (d_event.year * 12 + d_event.month) - (
                            due.year * 12 + due.month
                        )
                    if d_event is not None and archetype == "drift" and months_to <= 9:
                        # gradual drifter: timing decays over 9 months, which
                        # precedes the 6-month label horizon
                        ramp = (9 - months_to) / 9.0
                        days_late = max(0.0, float(rng.normal(3 + 30 * ramp, 5)))
                    elif d_event is not None and archetype == "cliff" and months_to <= 3:
                        # cliff: looks healthy, then collapses 3 months out
                        days_late = max(0.0, float(rng.normal(30, 7)))
                    else:
                        days_late = max(0.0, float(rng.normal(2.2, 3.4)))
                        if rng.random() < 0.012:  # occasional one-off late month
                            days_late = float(rng.normal(22, 5))
                    paid_date = due + timedelta(days=int(round(days_late)))
                    amount_paid = amount_due
                pay_rows.append(
                    {
                        "payment_id": f"PMT-{len(pay_rows) + 1:07d}",
                        "lease_id": lid,
                        "due_date": due,
                        "paid_date": paid_date,
                        "amount_due": amount_due,
                        "amount_paid": amount_paid,
                    }
                )
            m += 1
            due = _month_add(commencement, m)
    payments_df = pl.DataFrame(pay_rows, schema_overrides={"paid_date": pl.Date})

    # ---- work orders ---------------------------------------------------------
    wo_rows: list[dict[str, object]] = []
    categories = ["HVAC", "plumbing", "electrical", "janitorial", "roof", "tenant_improvement"]
    for lease in leases:
        lid = str(lease["lease_id"])
        commencement = lease["commencement"]  # type: ignore[assignment]
        stop = min(lease["expiration"], OBS_END)  # type: ignore[type-var,assignment]
        if stop <= max(commencement, OBS_START):
            continue
        d_event = default_events.get(lid)
        months = (stop.year * 12 + stop.month) - (commencement.year * 12 + commencement.month)
        n_wo = int(rng.poisson(max(months, 1) * 0.10))
        for _ in range(n_wo):
            opened = _month_add(commencement, int(rng.integers(0, max(months, 1))))
            opened += timedelta(days=int(rng.integers(0, 28)))
            if opened < OBS_START or opened > OBS_END:
                continue
            in_distress = d_event is not None and _month_add(d_event, -8) <= opened <= d_event
            dispute_p = 0.30 if in_distress else 0.05
            wo_rows.append(
                {
                    "wo_id": f"WO-{len(wo_rows) + 1:06d}",
                    "unit_id": str(lease["unit_id"]),
                    "tenant_id": str(lease["tenant_id"]),
                    "opened_at": opened,
                    "closed_at": opened + timedelta(days=int(rng.integers(1, 45))),
                    "category": str(rng.choice(categories)),
                    "cost": round(float(rng.lognormal(6.2, 0.9)), 2),
                    "tenant_initiated": bool(rng.random() < 0.6),
                    "dispute_flag": bool(rng.random() < dispute_p),
                }
            )
    work_orders_df = pl.DataFrame(wo_rows)

    # ---- market comps ---------------------------------------------------------
    comp_rows: list[dict[str, object]] = []
    month = OBS_START
    while month < OBS_END:
        for sm in SUBMARKETS:
            for ac in ASSET_CLASSES:
                for _ in range(int(rng.poisson(2.2))):
                    level = market_rent_psf(sm, ac, month)
                    softness = max(0.0, -((level / market_rent_psf(sm, ac, OBS_START)) - 1.0))
                    comp_rows.append(
                        {
                            "comp_id": f"C-{len(comp_rows) + 1:06d}",
                            "market": sm.market,
                            "submarket": sm.name,
                            "asset_class": ac,
                            "signed_date": month + timedelta(days=int(rng.integers(0, 28))),
                            "rent_psf": round(level * float(rng.normal(1.0, 0.055)), 2),
                            "term_months": int(rng.choice([36, 60, 84, 120])),
                            "ti_allowance_psf": round(
                                {"office": 45.0, "retail": 25.0, "industrial": 6.0}[ac]
                                * (1.0 + softness * 3.0) * float(rng.normal(1.0, 0.15)), 2
                            ),
                            "free_rent_months": int(
                                min(8, rng.poisson(1.0 + softness * 25.0))
                            ),
                            "source": str(rng.choice(["broker", "costar", "internal"])),
                        }
                    )
        month = _month_add(month, 1)
    comps_df = pl.DataFrame(comp_rows)

    # ---- clauses ---------------------------------------------------------------
    clause_rows: list[dict[str, object]] = []
    for lease in leases:
        lid = str(lease["lease_id"])
        is_defaulter = lid in default_events
        p_adverse = 0.55 if is_defaulter else 0.20
        for _ in range(int(rng.integers(2, 6))):
            pool = ADVERSE_CLAUSE_TYPES if rng.random() < p_adverse else BENIGN_CLAUSE_TYPES
            ctype = str(pool[int(rng.integers(len(pool)))])
            template = CLAUSE_TEMPLATES[ctype][int(rng.integers(len(CLAUSE_TEMPLATES[ctype])))]
            clause_rows.append(
                {
                    "clause_id": f"CL-{len(clause_rows) + 1:06d}",
                    "lease_id": lid,
                    "clause_type": ctype,
                    "raw_text": template.format(n=int(rng.integers(2, 96))),
                }
            )
    clauses_df = pl.DataFrame(clause_rows)

    return Portfolio(
        properties=properties_df,
        units=units_df,
        tenants=tenants_df,
        leases=leases_df,
        lease_clauses=clauses_df,
        payments=payments_df,
        work_orders=work_orders_df,
        market_comps=comps_df,
        default_events=default_events,
    )


def contractual_monthly_rent(base_rent_psf: float, escalation_pct: float, rsf: int,
                             months_since_commencement: int) -> float:
    """The schedule both the generator and the reconciliation layer agree on."""
    year_index = months_since_commencement // 12
    return round(base_rent_psf * (1.0 + escalation_pct) ** year_index * rsf / 12.0, 2)


def summarize(p: Portfolio) -> str:
    n_defaults = len(p.default_events)
    return (
        f"properties={p.properties.height} units={p.units.height} "
        f"tenants={p.tenants.height} leases={p.leases.height} "
        f"payments={p.payments.height} work_orders={p.work_orders.height} "
        f"comps={p.market_comps.height} clauses={p.lease_clauses.height} "
        f"defaults={n_defaults} ({n_defaults / p.leases.height:.1%} of leases)"
    )


if __name__ == "__main__":
    print(summarize(generate(42)))
