"""DQ-layer tests: deliberately dirty fixtures must be quarantined, and the
halt rule must fire when dirt exceeds the governed threshold. These tests ARE
the spec for the DQ layer."""

import polars as pl

from shared.dq import DQReport
from shared.dq.report import TableStats
from terrasignal.ingestion.contracts import check_negative_paid, check_rent_distribution
from terrasignal.ingestion.reconcile import reconcile
from terrasignal.synth.dirt import inject
from terrasignal.synth.generator import Portfolio, generate


def _dirty(seed: int = 7) -> tuple[Portfolio, object]:
    p = generate(seed=seed, n_properties=40, n_tenants=160)
    manifest = inject(p, rate=0.008, seed=99)
    return p, manifest


def test_fat_finger_rents_caught_by_market_band() -> None:
    p, manifest = _dirty()
    enriched = (
        p.leases.join(p.units.select("unit_id", "property_id"), on="unit_id", how="left")
        .join(p.properties.select("property_id", "asset_class"), on="property_id", how="left")
        .filter(pl.col("asset_class").is_not_null())
    )
    result = check_rent_distribution(enriched, p.market_comps)
    caught = set(result.pks)
    assert set(manifest.leases_fat_finger) <= caught
    # the band must not over-flag: nothing clean gets caught
    dirty_rent_leases = set(manifest.leases_fat_finger) | set(manifest.leases_negative_rent)
    assert caught <= dirty_rent_leases


def test_reconciliation_catches_schedule_drift() -> None:
    p, manifest = _dirty()
    # exclude leases dirtied in other ways, as the pipeline does (layer 1 first)
    other_dirty = manifest.all_lease_pks() - set(manifest.reconciliation_drift_leases)
    clean_leases = p.leases.filter(~pl.col("lease_id").is_in(list(other_dirty)))
    bad_payment_pks = manifest.payments_outside_term + manifest.payments_negative_due
    clean_payments = p.payments.filter(~pl.col("payment_id").is_in(bad_payment_pks))
    result = reconcile(clean_leases, clean_payments, p.units, tolerance=0.01)
    caught = set(result.pks)
    # every drift lease that has in-window payments must be caught; nothing else
    drift_with_payments = {
        lid for lid in manifest.reconciliation_drift_leases
        if clean_payments.filter(pl.col("lease_id") == lid).height > 0
    }
    assert drift_with_payments == caught
    assert len(drift_with_payments) >= 4


def test_negative_paid_contract() -> None:
    payments = pl.DataFrame(
        {
            "payment_id": ["A", "B"],
            "lease_id": ["L", "L"],
            "amount_paid": [-5.0, 10.0],
        }
    )
    assert check_negative_paid(payments).pks == ["A"]


def test_halt_fires_above_governed_threshold() -> None:
    report = DQReport(
        snapshot_uri="x",
        halt_threshold=0.02,
        tables=[TableStats(table="payments", total_rows=1000, quarantined_rows=35)],
    )
    report.evaluate_halt()
    assert report.halted
    assert report.halt_reason is not None and "payments" in report.halt_reason
