"""Ingestion run orchestrator: source Postgres → 3-layer DQ → Parquet snapshot.

The snapshot directory + dq_report.json URI become lineage anchors: every
training run records which snapshot (and therefore which DQ evidence) it used.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import structlog
from sqlalchemy import Engine, create_engine, text

from shared.dq import DQReport, RuleResult, write_dq_report
from shared.dq.report import DQHaltError, TableStats
from terrasignal.ingestion.contracts import (
    check_escalation_null_budget,
    check_negative_paid,
    check_rent_distribution,
)
from terrasignal.ingestion.reconcile import reconcile
from terrasignal.settings import get_settings, governed_thresholds

log = structlog.get_logger(__name__)

SOURCE_TABLES = (
    "properties", "units", "tenants", "leases",
    "lease_clauses", "payments", "work_orders", "market_comps",
)
PK_OF = {
    "properties": "property_id", "units": "unit_id", "tenants": "tenant_id",
    "leases": "lease_id", "lease_clauses": "clause_id", "payments": "payment_id",
    "work_orders": "wo_id", "market_comps": "comp_id",
}
DQ_VIEWS = {
    "leases": "dq.lease_violations",
    "payments": "dq.payment_violations",
    "units": "dq.unit_violations",
    "market_comps": "dq.comp_violations",
}


def _read_table(engine: Engine, table: str) -> pl.DataFrame:
    df = pl.read_database(f"SELECT * FROM {table}", connection=engine)  # noqa: S608 - table names from fixed tuple
    # Postgres NUMERIC arrives as Decimal; snapshots feed the float-domain
    # feature engine, so normalize here (money stays exact in the database).
    return df.with_columns(
        [pl.col(c).cast(pl.Float64) for c, dt in df.schema.items()
         if isinstance(dt, pl.Decimal)]
    )


def run_ingestion(snapshot_root: Path | None = None) -> DQReport:
    settings = get_settings()
    thresholds = governed_thresholds()
    run_id = uuid.uuid4()
    engine = create_engine(settings.database_url_sync)
    snapshot_root = snapshot_root or (settings.data_dir / "snapshots")
    snapshot_dir = snapshot_root / str(run_id)

    quarantine: dict[str, dict[str, tuple[str, str]]] = {t: {} for t in SOURCE_TABLES}

    def add(table: str, pks: list[str], rule: str, layer: str) -> None:
        for pk in pks:
            quarantine[table].setdefault(str(pk), (rule, layer))

    rules: list[RuleResult] = []

    def record_rule(table: str, rule: str, layer: str, pks: list[str]) -> None:
        add(table, pks, rule, layer)
        rules.append(RuleResult(
            rule=rule, table=table, layer=layer,
            violation_count=len(pks), sample_pks=[str(p) for p in pks[:10]],
        ))

    # ---- layer 1: SQL constraint views ----
    with engine.begin() as conn:
        for view in DQ_VIEWS.values():
            conn.execute(text(f"REFRESH MATERIALIZED VIEW {view}"))
    for table, view in DQ_VIEWS.items():
        pk_col = PK_OF[table]
        df = pl.read_database(f"SELECT * FROM {view}", connection=engine)  # noqa: S608
        for (rule,), grp in df.group_by("rule"):
            record_rule(table, str(rule), "sql_view", grp[pk_col].to_list())

    # ---- load raw frames ----
    frames = {t: _read_table(engine, t) for t in SOURCE_TABLES}
    log.info("loaded_source", **{t: f.height for t, f in frames.items()})

    # ---- layer 2: Polars contracts ----
    leases_enriched = (
        frames["leases"]
        .join(frames["units"].select("unit_id", "property_id"), on="unit_id", how="left")
        .join(frames["properties"].select("property_id", "asset_class"), on="property_id",
              how="left")
    )
    v = check_escalation_null_budget(frames["leases"])
    if v is not None:
        record_rule(v.table, v.rule, "contract", v.pks)
    v2 = check_rent_distribution(
        leases_enriched.filter(pl.col("asset_class").is_not_null()), frames["market_comps"]
    )
    record_rule(v2.table, v2.rule, "contract", v2.pks)
    v3 = check_negative_paid(frames["payments"])
    record_rule(v3.table, v3.rule, "contract", v3.pks)

    # ---- layer 3: reconciliation (skip rows already quarantined) ----
    clean_leases = frames["leases"].filter(
        ~pl.col("lease_id").is_in(list(quarantine["leases"].keys()))
    )
    clean_payments = frames["payments"].filter(
        ~pl.col("payment_id").is_in(list(quarantine["payments"].keys()))
    )
    recon = reconcile(
        clean_leases, clean_payments, frames["units"],
        tolerance=float(thresholds["dq"]["reconciliation_tolerance"]),
    )
    record_rule(recon.table, recon.rule, "reconciliation", recon.pks)

    # ---- persist quarantine rows ----
    now = datetime.now(UTC)
    quarantine_rows = [
        {"run_id": run_id, "table_name": t, "pk": pk, "rule": rule, "layer": layer,
         "created_at": now}
        for t, entries in quarantine.items()
        for pk, (rule, layer) in entries.items()
    ]
    if quarantine_rows:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO dq.quarantine "
                    "(run_id, table_name, pk, rule, layer, created_at) "
                    "VALUES (:run_id, :table_name, :pk, :rule, :layer, :created_at)"
                ),
                quarantine_rows,
            )

    # ---- report + halt decision ----
    report = DQReport(
        run_id=run_id,
        snapshot_uri=str(snapshot_dir),
        halt_threshold=float(thresholds["dq"]["quarantine_halt_rate"]),
        rules=rules,
        tables=[
            TableStats(table=t, total_rows=frames[t].height,
                       quarantined_rows=len(quarantine[t]))
            for t in SOURCE_TABLES
        ],
    )
    report.evaluate_halt()
    report_path = write_dq_report(report, settings.data_dir / "dq")
    log.info("dq_report_written", path=str(report_path), halted=report.halted)

    if report.halted:
        engine.dispose()
        raise DQHaltError(report)

    # ---- clean snapshot: drop quarantined rows (and payments of bad leases) ----
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    bad_leases = list(quarantine["leases"].keys())
    for table in SOURCE_TABLES:
        df = frames[table].filter(~pl.col(PK_OF[table]).is_in(list(quarantine[table].keys())))
        if table in ("payments", "lease_clauses"):
            df = df.filter(~pl.col("lease_id").is_in(bad_leases))
        df.write_parquet(snapshot_dir / f"{table}.parquet")
    (snapshot_root / "LATEST.json").write_text(
        json.dumps({
            "run_id": str(run_id),
            "snapshot_dir": str(snapshot_dir),
            "dq_report": str(report_path),
            "created_at": now.isoformat(),
        }, indent=2),
        encoding="utf-8",
    )
    log.info("snapshot_written", dir=str(snapshot_dir))
    engine.dispose()
    return report
