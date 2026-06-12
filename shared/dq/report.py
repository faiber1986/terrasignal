"""dq_report.json schema + writer.

Every ingestion run produces exactly one of these; training runs reference its
path for lineage. The halt rule (>N% of any core table quarantined) is decided
here, in code — not in a prompt, not in a human's head.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class RuleResult(BaseModel):
    rule: str
    table: str
    layer: str  # sql_view | contract | reconciliation
    violation_count: int
    sample_pks: list[str] = Field(default_factory=list, max_length=10)


class TableStats(BaseModel):
    table: str
    total_rows: int
    quarantined_rows: int

    @property
    def quarantine_rate(self) -> float:
        return self.quarantined_rows / self.total_rows if self.total_rows else 0.0


class DQReport(BaseModel):
    run_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    snapshot_uri: str
    rules: list[RuleResult] = Field(default_factory=list)
    tables: list[TableStats] = Field(default_factory=list)
    halt_threshold: float
    halted: bool = False
    halt_reason: str | None = None

    def evaluate_halt(self) -> None:
        """Halt if any core table exceeds the quarantine-rate threshold."""
        for t in self.tables:
            if t.quarantine_rate > self.halt_threshold:
                self.halted = True
                self.halt_reason = (
                    f"{t.table}: {t.quarantined_rows}/{t.total_rows} rows quarantined "
                    f"({t.quarantine_rate:.1%}) exceeds threshold {self.halt_threshold:.1%}"
                )
                return
        self.halted = False
        self.halt_reason = None


class DQHaltError(RuntimeError):
    """Raised when an ingestion run trips the halt rule. Pages a human; no model
    trains on this snapshot."""

    def __init__(self, report: DQReport) -> None:
        self.report = report
        super().__init__(report.halt_reason or "DQ halt")


def write_dq_report(report: DQReport, out_dir: Path) -> Path:
    """Write dq_report.json named by run_id; returns the path (the lineage URI)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"dq_report_{report.run_id}.json"
    path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path
