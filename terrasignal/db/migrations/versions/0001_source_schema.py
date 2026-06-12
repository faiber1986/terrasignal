"""Source-of-record schema (mirrors PMS extracts).

Deliberately NO foreign-key constraints between source tables: extracts from
property-management systems arrive dirty (orphan units, impossible dates) and
the DQ layer must catch and quarantine them rather than the database silently
rejecting the load. Referential integrity is asserted by dq.* views.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("property_id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("market", sa.String, nullable=False),
        sa.Column("submarket", sa.String, nullable=False),
        sa.Column("asset_class", sa.String, nullable=False),  # office | retail | industrial
        sa.Column("year_built", sa.Integer, nullable=False),
        sa.Column("rsf", sa.Integer, nullable=False),
        sa.Column("condition_grade", sa.String, nullable=False),  # A | B | C
    )
    op.create_table(
        "units",
        sa.Column("unit_id", sa.String, primary_key=True),
        sa.Column("property_id", sa.String, nullable=False),
        sa.Column("floor", sa.Integer, nullable=False),
        sa.Column("rsf", sa.Integer, nullable=False),
        sa.Column("condition_grade", sa.String, nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("industry_naics", sa.String, nullable=False),
        sa.Column("credit_rating", sa.String, nullable=True),  # AAA..CCC, internal scale
        sa.Column("parent_company", sa.String, nullable=True),
    )
    op.create_table(
        "leases",
        sa.Column("lease_id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, nullable=False),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("commencement", sa.Date, nullable=False),
        sa.Column("expiration", sa.Date, nullable=False),
        sa.Column("base_rent_psf", sa.Numeric(10, 2), nullable=False),
        sa.Column("escalation_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("term_months", sa.Integer, nullable=False),
        sa.Column("lease_type", sa.String, nullable=False),  # NNN | FSG | MG
        sa.Column("security_deposit", sa.Numeric(12, 2), nullable=False),
    )
    op.create_table(
        "lease_clauses",
        sa.Column("clause_id", sa.String, primary_key=True),
        sa.Column("lease_id", sa.String, nullable=False),
        sa.Column("clause_type", sa.String, nullable=False),
        sa.Column("raw_text", sa.Text, nullable=False),
    )
    op.create_table(
        "payments",
        sa.Column("payment_id", sa.String, primary_key=True),
        sa.Column("lease_id", sa.String, nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("paid_date", sa.Date, nullable=True),
        sa.Column("amount_due", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.create_table(
        "work_orders",
        sa.Column("wo_id", sa.String, primary_key=True),
        sa.Column("unit_id", sa.String, nullable=False),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("opened_at", sa.Date, nullable=False),
        sa.Column("closed_at", sa.Date, nullable=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("tenant_initiated", sa.Boolean, nullable=False),
        sa.Column("dispute_flag", sa.Boolean, nullable=False),
    )
    op.create_table(
        "market_comps",
        sa.Column("comp_id", sa.String, primary_key=True),
        sa.Column("market", sa.String, nullable=False),
        sa.Column("submarket", sa.String, nullable=False),
        sa.Column("asset_class", sa.String, nullable=False),
        sa.Column("signed_date", sa.Date, nullable=False),
        sa.Column("rent_psf", sa.Numeric(10, 2), nullable=False),
        sa.Column("term_months", sa.Integer, nullable=False),
        sa.Column("ti_allowance_psf", sa.Numeric(10, 2), nullable=False),
        sa.Column("free_rent_months", sa.Integer, nullable=False),
        sa.Column("source", sa.String, nullable=False),
    )
    op.create_index("ix_payments_lease_due", "payments", ["lease_id", "due_date"])
    op.create_index("ix_leases_tenant", "leases", ["tenant_id"])
    op.create_index("ix_leases_unit", "leases", ["unit_id"])
    op.create_index(
        "ix_comps_submarket_date", "market_comps", ["submarket", "asset_class", "signed_date"]
    )
    op.create_index("ix_wo_tenant", "work_orders", ["tenant_id", "opened_at"])


def downgrade() -> None:
    for t in (
        "market_comps",
        "work_orders",
        "payments",
        "lease_clauses",
        "leases",
        "tenants",
        "units",
        "properties",
    ):
        op.drop_table(t)
