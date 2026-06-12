"""Deliberate dirt injection. The DQ layer's tests feed on this.

Each trap maps to a specific DQ rule and layer:
- layer 1 (SQL views): negative rent, expiration<=commencement, orphan unit,
  payment outside term, negative amount_due, orphan property, negative TI,
  future comp date.
- layer 2 (contracts): fat-finger rents far outside the market percentile band,
  null escalation beyond budget.
- layer 3 (reconciliation): leases whose payments drift +5% off the contractual
  schedule (the upstream-PMS-bug case).

`rate` scales row counts; the default stays under the 2% halt threshold, and
`rate>=0.03` is the demo lever that trips the halt on purpose.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
from pydantic import BaseModel

from terrasignal.synth.generator import Portfolio


class DirtManifest(BaseModel):
    """What was injected, so tests can assert the DQ layer caught all of it."""

    leases_negative_rent: list[str] = []
    leases_inverted_dates: list[str] = []
    leases_orphan_unit: list[str] = []
    leases_fat_finger: list[str] = []
    payments_outside_term: list[str] = []
    payments_negative_due: list[str] = []
    units_orphan_property: list[str] = []
    comps_nonpositive_rent: list[str] = []
    comps_negative_ti: list[str] = []
    comps_future_date: list[str] = []
    reconciliation_drift_leases: list[str] = []

    def all_lease_pks(self) -> set[str]:
        return set(
            self.leases_negative_rent + self.leases_inverted_dates
            + self.leases_orphan_unit + self.leases_fat_finger
            + self.reconciliation_drift_leases
        )


def inject(portfolio: Portfolio, rate: float = 0.006, seed: int = 1337) -> DirtManifest:
    """Mutate the portfolio's frames in place; return the manifest."""
    rng = np.random.default_rng(seed)
    manifest = DirtManifest()

    leases = portfolio.leases
    n_leases = leases.height
    k = max(2, int(n_leases * rate / 4))  # split lease dirt across 4 traps
    dirty_idx = rng.choice(n_leases, size=4 * k + 8, replace=False)
    groups = [dirty_idx[i * k:(i + 1) * k] for i in range(4)]
    recon_idx = dirty_idx[4 * k: 4 * k + 8]

    lease_ids = leases["lease_id"].to_list()

    def ids(idx: np.ndarray) -> list[str]:
        return [lease_ids[int(i)] for i in idx]

    manifest.leases_negative_rent = ids(groups[0])
    manifest.leases_inverted_dates = ids(groups[1])
    manifest.leases_orphan_unit = ids(groups[2])
    manifest.leases_fat_finger = ids(groups[3])
    manifest.reconciliation_drift_leases = ids(recon_idx)

    portfolio.leases = leases.with_columns(
        base_rent_psf=pl.when(pl.col("lease_id").is_in(manifest.leases_negative_rent))
        .then(pl.lit(-12.50))
        .when(pl.col("lease_id").is_in(manifest.leases_fat_finger))
        .then(pl.col("base_rent_psf") * 100)  # $42.50 typed as $4,250
        .otherwise(pl.col("base_rent_psf")),
        expiration=pl.when(pl.col("lease_id").is_in(manifest.leases_inverted_dates))
        .then(pl.col("commencement") - pl.duration(days=30))
        .otherwise(pl.col("expiration")),
        unit_id=pl.when(pl.col("lease_id").is_in(manifest.leases_orphan_unit))
        .then(pl.lit("U-GHOST-") + pl.col("lease_id"))
        .otherwise(pl.col("unit_id")),
    )

    # payments: outside-term and negative amounts
    payments = portfolio.payments
    pk = max(2, int(payments.height * rate / 2))
    pay_idx = rng.choice(payments.height, size=2 * pk, replace=False)
    pay_ids = payments["payment_id"].to_list()
    manifest.payments_outside_term = [pay_ids[int(i)] for i in pay_idx[:pk]]
    manifest.payments_negative_due = [pay_ids[int(i)] for i in pay_idx[pk:]]
    portfolio.payments = payments.with_columns(
        due_date=pl.when(pl.col("payment_id").is_in(manifest.payments_outside_term))
        .then(pl.col("due_date") + pl.duration(days=4000))
        .otherwise(pl.col("due_date")),
        amount_due=pl.when(pl.col("payment_id").is_in(manifest.payments_negative_due))
        .then(pl.lit(-1.0) * pl.col("amount_due"))
        .otherwise(pl.col("amount_due")),
    )

    # layer-3 trap: drift amount_due +5% for selected (otherwise clean) leases
    portfolio.payments = portfolio.payments.with_columns(
        amount_due=pl.when(
            pl.col("lease_id").is_in(manifest.reconciliation_drift_leases)
            & (pl.col("amount_due") > 0)
        )
        .then((pl.col("amount_due") * 1.05).round(2))
        .otherwise(pl.col("amount_due")),
    )

    # units: orphan property. Keep traps disjoint: never orphan a unit that
    # backs an intentionally-dirtied lease, or the property→asset_class join
    # would null out (e.g.) a fat-finger lease and hide it from the layer-2
    # market-band check, conflating two traps.
    units = portfolio.units
    uk = max(1, int(units.height * rate))
    unit_ids = units["unit_id"].to_list()
    dirtied_lease_units = set(
        leases.filter(pl.col("lease_id").is_in(list(manifest.all_lease_pks())))[
            "unit_id"
        ].to_list()
    )
    candidate_idx = [i for i, uid in enumerate(unit_ids) if uid not in dirtied_lease_units]
    unit_idx = rng.choice(candidate_idx, size=min(uk, len(candidate_idx)), replace=False)
    manifest.units_orphan_property = [unit_ids[int(i)] for i in unit_idx]
    portfolio.units = units.with_columns(
        property_id=pl.when(pl.col("unit_id").is_in(manifest.units_orphan_property))
        .then(pl.lit("P-GHOST"))
        .otherwise(pl.col("property_id")),
    )

    # comps: nonpositive rent, negative TI, future signed date
    comps = portfolio.market_comps
    ck = max(1, int(comps.height * rate / 3))
    comp_idx = rng.choice(comps.height, size=3 * ck, replace=False)
    comp_ids = comps["comp_id"].to_list()
    manifest.comps_nonpositive_rent = [comp_ids[int(i)] for i in comp_idx[:ck]]
    manifest.comps_negative_ti = [comp_ids[int(i)] for i in comp_idx[ck:2 * ck]]
    manifest.comps_future_date = [comp_ids[int(i)] for i in comp_idx[2 * ck:]]
    portfolio.market_comps = comps.with_columns(
        rent_psf=pl.when(pl.col("comp_id").is_in(manifest.comps_nonpositive_rent))
        .then(pl.lit(0.0))
        .otherwise(pl.col("rent_psf")),
        ti_allowance_psf=pl.when(pl.col("comp_id").is_in(manifest.comps_negative_ti))
        .then(pl.lit(-10.0))
        .otherwise(pl.col("ti_allowance_psf")),
        signed_date=pl.when(pl.col("comp_id").is_in(manifest.comps_future_date))
        .then(pl.lit(date.today() + timedelta(days=400)))
        .otherwise(pl.col("signed_date")),
    )

    return manifest
