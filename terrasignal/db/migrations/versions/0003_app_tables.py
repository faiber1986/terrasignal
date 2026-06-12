"""Application tables: predictions, audit (append-only, trigger-enforced),
feedback, model registry, drift metrics.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APPEND_ONLY_TRIGGER = """
CREATE FUNCTION audit_no_rewrite() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only; corrections are new events';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION audit_no_rewrite();
"""


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.Uuid, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_name", sa.String, nullable=False),
        sa.Column("model_version", sa.Integer, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),  # tenant | unit
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("request_id", sa.String, nullable=True),
        sa.Column("features", JSONB, nullable=False),  # feature snapshot at score time
        sa.Column("output", JSONB, nullable=False),  # pd / p10-p50-p90 etc.
        sa.Column("shap", JSONB, nullable=False),
        sa.Column("comps", JSONB, nullable=True),
        sa.Column("baseline_mode", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_predictions_entity", "predictions", ["entity_type", "entity_id"])
    op.create_index("ix_predictions_model", "predictions", ["model_name", "model_version"])

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.Uuid, primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("actor_role", sa.String, nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String, nullable=False),
        sa.Column("request_id", sa.String, nullable=True),
        sa.Column("payload", JSONB, nullable=False),
    )
    op.create_index("ix_audit_occurred", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_type", "audit_events", ["event_type"])
    op.execute(APPEND_ONLY_TRIGGER)

    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.Uuid, primary_key=True),
        sa.Column("prediction_id", sa.Uuid, sa.ForeignKey("predictions.prediction_id"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String, nullable=False),
        sa.Column("action", sa.String, nullable=False),  # accept | override
        sa.Column("reason_code", sa.String, nullable=True),  # required when override
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("override_value", JSONB, nullable=True),
    )

    op.create_table(
        "model_registry",
        sa.Column("model_version_id", sa.Uuid, primary_key=True),
        sa.Column("model_name", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String, nullable=False),  # PendingManualApproval|Approved|Rejected|Archived
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("baseline_metrics", JSONB, nullable=False),
        sa.Column("eval_set_hash", sa.String, nullable=False),
        sa.Column("training_snapshot_uri", sa.String, nullable=False),
        sa.Column("dq_report_uri", sa.String, nullable=False),
        sa.Column("git_sha", sa.String, nullable=False),
        sa.Column("artifact_path", sa.String, nullable=False),
        sa.Column("model_card_path", sa.String, nullable=False),
        sa.Column("approved_by", sa.String, nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("model_name", "version", name="uq_registry_name_version"),
    )

    op.create_table(
        "drift_metrics",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_name", sa.String, nullable=False),
        sa.Column("feature_name", sa.String, nullable=False),
        sa.Column("psi", sa.Numeric(10, 6), nullable=False),
        sa.Column("status", sa.String, nullable=False),  # green | amber | red
        sa.Column("baseline_window", sa.String, nullable=False),
        sa.Column("current_window", sa.String, nullable=False),
    )
    op.create_index("ix_drift_model_time", "drift_metrics", ["model_name", "computed_at"])


def downgrade() -> None:
    op.drop_table("drift_metrics")
    op.drop_table("model_registry")
    op.drop_table("feedback")
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION audit_no_rewrite()")
    op.drop_table("audit_events")
    op.drop_table("predictions")
