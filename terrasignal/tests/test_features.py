"""Point-in-time correctness: a feature for (entity, as_of) must not move when
data AFTER as_of changes. Built on small handcrafted fixtures."""

from datetime import date

import polars as pl

from terrasignal.features.definitions import (
    delinquency_events,
    lease_pricing_features,
    tenant_risk_features,
)


def _frames() -> dict[str, pl.DataFrame]:
    properties = pl.DataFrame({
        "property_id": ["P-1"], "name": ["Test Plaza"], "market": ["Atlanta"],
        "submarket": ["Midtown"], "asset_class": ["office"], "year_built": [2000],
        "rsf": [10000], "condition_grade": ["B"],
    })
    units = pl.DataFrame({
        "unit_id": ["U-1", "U-2"], "property_id": ["P-1", "P-1"], "floor": [1, 2],
        "rsf": [6000, 4000], "condition_grade": ["B", "B"],
    })
    tenants = pl.DataFrame({
        "tenant_id": ["T-1"], "name": ["Cedar Labs LLC"], "industry_naics": ["54"],
        "credit_rating": ["BBB"], "parent_company": [None],
    })
    leases = pl.DataFrame({
        "lease_id": ["L-1"], "unit_id": ["U-1"], "tenant_id": ["T-1"],
        "commencement": [date(2023, 1, 1)], "expiration": [date(2028, 1, 1)],
        "base_rent_psf": [40.0], "escalation_pct": [0.03], "term_months": [60],
        "lease_type": ["FSG"], "security_deposit": [40000.0],
    })
    payments = pl.DataFrame({
        "payment_id": ["PM-1", "PM-2", "PM-3"],
        "lease_id": ["L-1", "L-1", "L-1"],
        "due_date": [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)],
        "paid_date": [date(2024, 1, 3), date(2024, 2, 10), date(2024, 3, 28)],
        "amount_due": [20000.0, 20000.0, 20000.0],
        "amount_paid": [20000.0, 20000.0, 20000.0],
    })
    comps = pl.DataFrame({
        "comp_id": ["C-1", "C-2"], "market": ["Atlanta", "Atlanta"],
        "submarket": ["Midtown", "Midtown"], "asset_class": ["office", "office"],
        "signed_date": [date(2023, 12, 10), date(2024, 1, 15)],
        "rent_psf": [42.0, 44.0], "term_months": [60, 60],
        "ti_allowance_psf": [50.0, 55.0], "free_rent_months": [2, 3],
        "source": ["broker", "broker"],
    })
    work_orders = pl.DataFrame(schema={
        "wo_id": pl.String, "unit_id": pl.String, "tenant_id": pl.String,
        "opened_at": pl.Date, "closed_at": pl.Date, "category": pl.String,
        "cost": pl.Float64, "tenant_initiated": pl.Boolean, "dispute_flag": pl.Boolean,
    })
    clauses = pl.DataFrame({
        "clause_id": ["CL-1", "CL-2"], "lease_id": ["L-1", "L-1"],
        "clause_type": ["early_termination", "renewal_option"],
        "raw_text": ["...", "..."],
    })
    return {
        "properties": properties, "units": units, "tenants": tenants, "leases": leases,
        "payments": payments, "work_orders": work_orders, "market_comps": comps,
        "lease_clauses": clauses,
    }


def test_future_payment_does_not_change_feature() -> None:
    frames = _frames()
    as_of = [date(2024, 2, 1)]
    base = tenant_risk_features(frames, as_of)

    # add a catastrophic payment AFTER as_of: 90 days late in March
    frames2 = _frames()
    frames2["payments"] = pl.concat([
        frames2["payments"],
        pl.DataFrame({
            "payment_id": ["PM-X"], "lease_id": ["L-1"],
            "due_date": [date(2024, 4, 1)], "paid_date": [date(2024, 6, 30)],
            "amount_due": [20000.0], "amount_paid": [20000.0],
        }),
    ])
    after = tenant_risk_features(frames2, as_of)
    assert base.sort("tenant_id").equals(after.sort("tenant_id"))


def test_unpaid_invoice_counts_days_late_so_far() -> None:
    frames = _frames()
    frames["payments"] = pl.concat([
        frames["payments"],
        pl.DataFrame({
            "payment_id": ["PM-U"], "lease_id": ["L-1"],
            "due_date": [date(2024, 3, 15)], "paid_date": [None],
            "amount_due": [20000.0], "amount_paid": [0.0],
        }).with_columns(pl.col("paid_date").cast(pl.Date)),
    ])
    feats = tenant_risk_features(frames, [date(2024, 4, 1)]).to_dicts()[0]
    assert feats["unpaid_count"] == 1
    assert feats["days_late_max_6m"] >= 17  # 2024-03-15 → 2024-04-01


def test_comp_after_event_date_excluded_from_pricing_features() -> None:
    frames = _frames()
    events = pl.DataFrame({
        "unit_id": ["U-2"], "event_date": [date(2024, 1, 1)],
        "term_months": [60], "lease_type": ["FSG"],
    })
    feats = lease_pricing_features(frames, events).to_dicts()[0]
    # only C-1 (2023-12-10) is visible at 2024-01-01; C-2 signs later that month
    assert feats["comp_median_rent_6m"] == 42.0
    assert feats["comp_count_6m"] == 1


def test_delinquency_event_is_first_unpaid_due_date() -> None:
    frames = _frames()
    frames["payments"] = pl.DataFrame({
        "payment_id": ["A", "B", "C"],
        "lease_id": ["L-1", "L-1", "L-1"],
        "due_date": [date(2024, 5, 1), date(2024, 6, 1), date(2024, 7, 1)],
        "paid_date": [date(2024, 5, 2), None, None],
        "amount_due": [20000.0] * 3,
        "amount_paid": [20000.0, 0.0, 0.0],
    })
    events = delinquency_events(frames["payments"], frames["leases"],
                                observed_through=date(2024, 12, 1))
    assert events.to_dicts() == [
        {"lease_id": "L-1", "tenant_id": "T-1", "event_date": date(2024, 6, 1)}
    ]


def test_building_vacancy_reflects_unleased_units() -> None:
    frames = _frames()
    events = pl.DataFrame({
        "unit_id": ["U-2"], "event_date": [date(2024, 1, 1)],
        "term_months": [60], "lease_type": ["FSG"],
    })
    feats = lease_pricing_features(frames, events).to_dicts()[0]
    # U-1 leased, U-2 vacant → 50% vacancy
    assert abs(feats["building_vacancy"] - 0.5) < 1e-9
