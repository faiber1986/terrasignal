"""Data-quality report schema and writer, shared by both projects' ingestion jobs."""

from shared.dq.report import DQReport, RuleResult, write_dq_report

__all__ = ["DQReport", "RuleResult", "write_dq_report"]
