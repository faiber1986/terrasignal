"""DQ layer 1: in-database constraint views + quarantine table.

Materialized views quarantine violations instead of silently dropping them.
The ingestion job refreshes these, merges with layer-2/3 findings, and writes
dq_report.json. Hand-written SQL on purpose — this IS the spec.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

LEASE_VIOLATIONS = """
CREATE MATERIALIZED VIEW dq.lease_violations AS
SELECT lease_id, 'expiration_before_commencement' AS rule
FROM leases WHERE expiration <= commencement
UNION ALL
SELECT lease_id, 'nonpositive_rent' FROM leases WHERE base_rent_psf <= 0
UNION ALL
SELECT l.lease_id, 'orphan_unit' FROM leases l
LEFT JOIN units u USING (unit_id) WHERE u.unit_id IS NULL
UNION ALL
SELECT l.lease_id, 'orphan_tenant' FROM leases l
LEFT JOIN tenants t USING (tenant_id) WHERE t.tenant_id IS NULL
"""

PAYMENT_VIOLATIONS = """
CREATE MATERIALIZED VIEW dq.payment_violations AS
SELECT p.payment_id, 'payment_outside_term' AS rule
FROM payments p
JOIN leases l USING (lease_id)
WHERE p.due_date NOT BETWEEN l.commencement AND l.expiration + INTERVAL '90 days'
UNION ALL
SELECT payment_id, 'orphan_lease' FROM payments p
WHERE NOT EXISTS (SELECT 1 FROM leases l WHERE l.lease_id = p.lease_id)
UNION ALL
SELECT payment_id, 'negative_amount_due' FROM payments WHERE amount_due < 0
UNION ALL
SELECT payment_id, 'paid_before_due_minus_60d' FROM payments
WHERE paid_date IS NOT NULL AND paid_date < due_date - INTERVAL '60 days'
"""

UNIT_VIOLATIONS = """
CREATE MATERIALIZED VIEW dq.unit_violations AS
SELECT u.unit_id, 'orphan_property' AS rule
FROM units u
LEFT JOIN properties p USING (property_id) WHERE p.property_id IS NULL
UNION ALL
SELECT unit_id, 'nonpositive_rsf' FROM units WHERE rsf <= 0
"""

COMP_VIOLATIONS = """
CREATE MATERIALIZED VIEW dq.comp_violations AS
SELECT comp_id, 'nonpositive_rent' AS rule FROM market_comps WHERE rent_psf <= 0
UNION ALL
SELECT comp_id, 'negative_ti' FROM market_comps WHERE ti_allowance_psf < 0
UNION ALL
SELECT comp_id, 'future_signed_date' FROM market_comps WHERE signed_date > CURRENT_DATE
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA dq")
    op.execute(LEASE_VIOLATIONS)
    op.execute(PAYMENT_VIOLATIONS)
    op.execute(UNIT_VIOLATIONS)
    op.execute(COMP_VIOLATIONS)
    op.create_table(
        "quarantine",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("run_id", sa.Uuid, nullable=False),
        sa.Column("table_name", sa.String, nullable=False),
        sa.Column("pk", sa.String, nullable=False),
        sa.Column("rule", sa.String, nullable=False),
        sa.Column("layer", sa.String, nullable=False),  # sql_view | contract | reconciliation
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="dq",
    )
    op.create_index("ix_quarantine_run", "quarantine", ["run_id"], schema="dq")


def downgrade() -> None:
    op.drop_table("quarantine", schema="dq")
    for v in ("comp_violations", "unit_violations", "payment_violations", "lease_violations"):
        op.execute(f"DROP MATERIALIZED VIEW dq.{v}")
    op.execute("DROP SCHEMA dq")
