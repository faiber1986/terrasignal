"""Local model registry: versions, metric gates evidence, human approval.

Nothing serves traffic without an Approved registry row — the backend refuses
to load artifacts for non-approved versions. Approval writes an audit event in
the same transaction.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import create_engine, text

from shared.audit import AuditEvent, audit_events_table
from terrasignal.settings import TERRASIGNAL_ROOT, get_settings

log = structlog.get_logger(__name__)

CARD_TEMPLATE = TERRASIGNAL_ROOT / "governance" / "model_card_template.md"

INTENDED_USE = {
    "terrasignal-risk-scorer": (
        "Rank commercial tenants by probability of default/material delinquency within "
        "6 months, to prioritize credit & collections outreach. Decision support only."
    ),
    "terrasignal-rent-forecaster": (
        "Estimate achievable base rent ($/SF/yr) at renewal, 6–18 month horizon, as a "
        "pricing range (p10/p50/p90) for asset managers. A human prices the lease."
    ),
}
OUT_OF_SCOPE = {
    "terrasignal-risk-scorer": (
        "- Eviction decisions or lease-application screening (fair-housing-adjacent "
        "boundary, even in commercial).\n- Automated credit denial of any kind.\n"
        "- Tenants with <3 months payment history (insufficient signal)."
    ),
    "terrasignal-rent-forecaster": (
        "- Binding price commitments without human review.\n- Thin submarkets with "
        "<5 trailing comps (range degrades; UI flags low comp count).\n- Asset classes "
        "outside office/retail/industrial."
    ),
}
FAILURE_MODES = {
    "terrasignal-risk-scorer": (
        "- Tenants with <12 months history score near the base rate.\n"
        "- Sudden macro shocks shift the calibration; watch the Brier monitor.\n"
        "- Defaults engineered to look like slow payers are detected late."
    ),
    "terrasignal-rent-forecaster": (
        "- Thin submarkets (low comp_count_6m) widen true uncertainty beyond the band.\n"
        "- Regime changes (e.g. office post-2023) are learned only after comps arrive."
    ),
}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True,
            cwd=TERRASIGNAL_ROOT,
        ).strip()
    except Exception:
        return "unversioned"


def _metrics_table(metrics: dict[str, Any], baselines: dict[str, Any]) -> str:
    lines = ["| Metric | Candidate | Baselines |", "|---|---|---|"]
    for k, v in metrics.items():
        base_str = ", ".join(
            f"{name}: {vals[k]:.4f}" for name, vals in baselines.items() if k in vals
        ) or "—"
        lines.append(f"| {k} | {v:.4f} | {base_str} |")
    return "\n".join(lines)


def register_model(
    model_name: str,
    metrics: dict[str, float],
    baseline_metrics: dict[str, dict[str, float]],
    eval_set_hash: str,
    training_snapshot_uri: str,
    dq_report_uri: str,
    artifact_dir: Path,
) -> int:
    """Insert a PendingManualApproval registry row + write its model card."""
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    now = datetime.now(UTC)
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT COALESCE(MAX(version), 0) + 1 FROM model_registry "
                 "WHERE model_name = :n"),
            {"n": model_name},
        ).scalar_one()

        card_dir = TERRASIGNAL_ROOT / "governance" / "cards"
        card_dir.mkdir(parents=True, exist_ok=True)
        card_path = card_dir / f"{model_name}-v{version}.md"
        card_path.write_text(
            CARD_TEMPLATE.read_text(encoding="utf-8").format(
                model_name=model_name,
                version=version,
                status="PendingManualApproval",
                created_at=now.isoformat(timespec="seconds"),
                git_sha=git_sha(),
                intended_use=INTENDED_USE[model_name],
                out_of_scope=OUT_OF_SCOPE[model_name],
                training_snapshot_uri=training_snapshot_uri,
                dq_report_uri=dq_report_uri,
                eval_set_hash=eval_set_hash,
                metrics_table=_metrics_table(metrics, baseline_metrics),
                failure_modes=FAILURE_MODES[model_name],
                owner="ml-platform@terrasignal.local",
                review_date=f"{now.year + (1 if now.month > 9 else 0)}-"
                            f"{(now.month + 3 - 1) % 12 + 1:02d}-01",
            ),
            encoding="utf-8",
        )

        conn.execute(
            text(
                "INSERT INTO model_registry (model_version_id, model_name, version, "
                "created_at, status, metrics, baseline_metrics, eval_set_hash, "
                "training_snapshot_uri, dq_report_uri, git_sha, artifact_path, "
                "model_card_path) VALUES (:id, :name, :version, :created_at, "
                "'PendingManualApproval', :metrics, :baselines, :eval_hash, :snap, "
                ":dq, :sha, :artifact, :card)"
            ),
            {
                "id": uuid.uuid4(),
                "name": model_name,
                "version": version,
                "created_at": now,
                "metrics": json.dumps(metrics),
                "baselines": json.dumps(baseline_metrics),
                "eval_hash": eval_set_hash,
                "snap": training_snapshot_uri,
                "dq": dq_report_uri,
                "sha": git_sha(),
                "artifact": str(artifact_dir),
                "card": str(card_path),
            },
        )
        event = AuditEvent(
            actor="training-pipeline",
            actor_role="system",
            event_type="model.registered",
            entity_type="model_version",
            entity_id=f"{model_name}:v{version}",
            payload={"metrics": metrics, "status": "PendingManualApproval"},
        )
        conn.execute(audit_events_table.insert().values(**event.model_dump()))
    engine.dispose()
    log.info("model_registered", model=model_name, version=int(version))
    return int(version)


def approve_model(model_name: str, version: int | None, approver: str) -> int:
    """Flip a pending version to Approved (the human gate). Archives any
    previously approved version of the same model."""
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    with engine.begin() as conn:
        if version is None:
            version = conn.execute(
                text("SELECT MAX(version) FROM model_registry WHERE model_name=:n "
                     "AND status='PendingManualApproval'"),
                {"n": model_name},
            ).scalar_one()
        if version is None:
            raise RuntimeError(f"no pending version for {model_name}")
        conn.execute(
            text("UPDATE model_registry SET status='Archived' "
                 "WHERE model_name=:n AND status='Approved'"),
            {"n": model_name},
        )
        updated = conn.execute(
            text("UPDATE model_registry SET status='Approved', approved_by=:a, "
                 "approved_at=:t WHERE model_name=:n AND version=:v "
                 "AND status='PendingManualApproval'"),
            {"a": approver, "t": datetime.now(UTC), "n": model_name, "v": version},
        )
        if updated.rowcount != 1:
            raise RuntimeError(f"{model_name} v{version} is not pending approval")
        event = AuditEvent(
            actor=approver,
            actor_role="approver",
            event_type="model.approved",
            entity_type="model_version",
            entity_id=f"{model_name}:v{version}",
            payload={"version": version},
        )
        conn.execute(audit_events_table.insert().values(**event.model_dump()))
    engine.dispose()
    log.info("model_approved", model=model_name, version=version, approver=approver)
    return int(version)


def active_version(model_name: str) -> dict[str, Any] | None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT model_name, version, status, metrics, artifact_path, "
                 "approved_by, approved_at FROM model_registry "
                 "WHERE model_name=:n AND status='Approved'"),
            {"n": model_name},
        ).mappings().first()
    engine.dispose()
    return dict(row) if row else None
