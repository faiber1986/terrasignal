"""Load a synthetic portfolio into the Postgres source-of-record tables."""

from __future__ import annotations

import polars as pl
import structlog
from sqlalchemy import create_engine, text

from terrasignal.settings import get_settings
from terrasignal.synth.generator import Portfolio

log = structlog.get_logger(__name__)

SOURCE_TABLES = (
    "properties",
    "units",
    "tenants",
    "leases",
    "lease_clauses",
    "payments",
    "work_orders",
    "market_comps",
)


def load(portfolio: Portfolio) -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    frames = portfolio.frames()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(SOURCE_TABLES)))
    for table in SOURCE_TABLES:
        df: pl.DataFrame = frames[table]
        df.write_database(
            table, settings.database_url_sync, if_table_exists="append", engine="sqlalchemy"
        )
        log.info("loaded", table=table, rows=df.height)
    engine.dispose()
