"""Runtime flags (kill switch state). Flipping a flag is an audited action;
the flag itself must survive an API restart, hence a table not memory.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_flags",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.Boolean, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String, nullable=False),
    )
    op.execute(
        "INSERT INTO runtime_flags (key, value, updated_at, updated_by) "
        "VALUES ('baseline_mode', false, now(), 'migration')"
    )


def downgrade() -> None:
    op.drop_table("runtime_flags")
