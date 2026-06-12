"""CLI: run one ingestion+DQ pass. Exit 0 = clean snapshot written, 2 = halted."""

from __future__ import annotations

import sys

import structlog

from shared.dq.report import DQHaltError
from terrasignal.ingestion.run import run_ingestion

log = structlog.get_logger(__name__)


def main() -> int:
    try:
        report = run_ingestion()
    except DQHaltError as e:
        log.error("DQ_HALT", reason=e.report.halt_reason, run_id=str(e.report.run_id))
        return 2
    total_q = sum(t.quarantined_rows for t in report.tables)
    log.info("ingestion_ok", run_id=str(report.run_id), quarantined_rows=total_q)
    return 0


if __name__ == "__main__":
    sys.exit(main())
