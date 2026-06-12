import json
from pathlib import Path

from shared.dq import DQReport, RuleResult, write_dq_report
from shared.dq.report import TableStats


def _report(quarantined: int, total: int = 1000) -> DQReport:
    return DQReport(
        snapshot_uri="file://data/snapshots/test",
        halt_threshold=0.02,
        rules=[
            RuleResult(
                rule="nonpositive_rent",
                table="leases",
                layer="sql_view",
                violation_count=quarantined,
                sample_pks=["L-1"],
            )
        ],
        tables=[TableStats(table="leases", total_rows=total, quarantined_rows=quarantined)],
    )


def test_halt_triggers_above_threshold() -> None:
    r = _report(quarantined=21)  # 2.1% > 2%
    r.evaluate_halt()
    assert r.halted
    assert r.halt_reason is not None and "leases" in r.halt_reason


def test_no_halt_at_or_below_threshold() -> None:
    r = _report(quarantined=20)  # exactly 2%
    r.evaluate_halt()
    assert not r.halted


def test_report_written_as_json(tmp_path: Path) -> None:
    r = _report(quarantined=5)
    r.evaluate_halt()
    path = write_dq_report(r, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rules"][0]["rule"] == "nonpositive_rent"
    assert str(r.run_id) in path.name
