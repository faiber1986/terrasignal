"""Ingestion & validation: Postgres source → 3-layer DQ → clean Parquet snapshot.

Layer 1: SQL constraint views (dq.* materialized views, refreshed here).
Layer 2: Polars contracts (null budgets, distribution sanity vs market window).
Layer 3: cross-source reconciliation (payments tie to contractual schedule ±1%).

Violations quarantine rows; >2% quarantined in any core table halts the run.
Every run writes dq_report.json — the lineage anchor for training runs.
"""
