"""Add pharmacy fields to organizations table

Revision ID: 009_pharmacy_fields
Revises: 008_vendor_data_source
Create Date: 2026-07-04

Adds pharmacy-specific registration fields for the independent pharmacy
DSCSA MVP. All columns are nullable so existing organizations and
non-pharmacy registrations are unaffected.

employee_count is the full-time pharmacist + pharmacy technician count,
used to determine small-dispenser status (25 or fewer) under the FDA
DSCSA exemption ending November 27, 2026.
"""
from alembic import op
import sqlalchemy as sa

revision = '009_pharmacy_fields'
down_revision = '008_vendor_data_source'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('pharmacy_name', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('state', sa.String(2), nullable=True))
    op.add_column('organizations', sa.Column('employee_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'employee_count')
    op.drop_column('organizations', 'state')
    op.drop_column('organizations', 'pharmacy_name')
