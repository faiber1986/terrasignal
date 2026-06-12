from datetime import date

import polars as pl

from terrasignal.synth.generator import Portfolio, contractual_monthly_rent, generate
from terrasignal.synth.markets import OBS_END, OBS_START


def test_generator_is_deterministic() -> None:
    a = generate(seed=11, n_properties=5, n_tenants=20)
    b = generate(seed=11, n_properties=5, n_tenants=20)
    assert a.leases.equals(b.leases)
    assert a.payments.equals(b.payments)
    assert a.default_events == b.default_events


def test_default_rate_in_plausible_band(portfolio: Portfolio) -> None:
    rate = len(portfolio.default_events) / portfolio.leases.height
    assert 0.02 < rate < 0.10


def test_clean_payments_tie_to_contractual_schedule(portfolio: Portfolio) -> None:
    """Every generated payment equals the schedule the reconciliation layer
    derives — the generator and the validator must agree on the math."""
    rsf = {r["unit_id"]: r["rsf"] for r in portfolio.units.to_dicts()}
    leases = {r["lease_id"]: r for r in portfolio.leases.to_dicts()}
    sample = portfolio.payments.sample(min(2000, portfolio.payments.height), seed=3)
    for p in sample.to_dicts():
        lease = leases[p["lease_id"]]
        months_in = (p["due_date"].year - lease["commencement"].year) * 12 + (
            p["due_date"].month - lease["commencement"].month
        )
        expected = contractual_monthly_rent(
            lease["base_rent_psf"], lease["escalation_pct"], rsf[lease["unit_id"]], months_in
        )
        assert abs(p["amount_due"] - expected) < 0.011, (
            f"payment {p['payment_id']} amount_due={p['amount_due']} expected={expected}"
        )


def test_payments_within_observation_window(portfolio: Portfolio) -> None:
    due = portfolio.payments["due_date"]
    assert due.min() >= OBS_START
    assert due.max() <= OBS_END


def test_defaulted_leases_stop_paying(portfolio: Portfolio) -> None:
    for lease_id, d_event in list(portfolio.default_events.items())[:25]:
        post = portfolio.payments.filter(
            (pl.col("lease_id") == lease_id) & (pl.col("due_date") >= d_event)
        )
        if post.height:
            assert post["paid_date"].null_count() == post.height
            assert post["amount_paid"].sum() == 0.0


def test_distress_ramp_days_late_exceeds_healthy_baseline(portfolio: Portfolio) -> None:
    """Days-late in the 3 months before a default must be visibly worse than
    the healthy population — otherwise the Risk Scorer has nothing to learn."""
    pays = portfolio.payments.filter(pl.col("paid_date").is_not_null()).with_columns(
        days_late=(pl.col("paid_date") - pl.col("due_date")).dt.total_days()
    )
    defaulters = list(portfolio.default_events.keys())
    pre_default = pays.filter(pl.col("lease_id").is_in(defaulters))
    healthy = pays.filter(~pl.col("lease_id").is_in(defaulters))
    # restrict pre-default to the ramp window
    ramp_rows = []
    for lease_id, d_event in portfolio.default_events.items():
        window_start = date(d_event.year - (1 if d_event.month <= 3 else 0),
                            ((d_event.month - 4) % 12) + 1, 1)
        ramp_rows.append(
            pre_default.filter(
                (pl.col("lease_id") == lease_id)
                & (pl.col("due_date") >= window_start)
                & (pl.col("due_date") < d_event)
            )
        )
    ramp = pl.concat([r for r in ramp_rows if r.height])
    assert ramp["days_late"].mean() > healthy["days_late"].mean() + 8  # type: ignore[operator]


def test_no_real_looking_identifiers(portfolio: Portfolio) -> None:
    names = portfolio.tenants["name"].to_list()
    assert all(n.split()[-1] in {"LLC", "Inc", "Group", "Co"} for n in names)
