"""Add data_source provenance field to vendors table

Revision ID: 008_vendor_data_source
Revises: 007_trading_partner_fields
Create Date: 2026-04-26

Tracks how a vendor/trading-partner row was created so demo/legacy
rows can be identified and cleaned up without touching real partner data.

Allowed values: user_created, imported, legacy_vendor, demo, system
"""
from alembic import op
import sqlalchemy as sa

revision = '008_vendor_data_source'
down_revision = '007_trading_partner_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vendors', sa.Column(
        'data_source',
        sa.String(50),
        nullable=True,
        server_default='user_created',
    ))


def downgrade() -> None:
    op.drop_column('vendors', 'data_source')
