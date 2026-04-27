"""Add DSCSA trading partner fields to vendors table

Revision ID: 007_trading_partner_fields
Revises: 006_watchtower_sync_columns
Create Date: 2026-04-26

Adds DSCSA-specific identifier and status fields to the vendors table
so it can serve as the Trading Partners store for DSCSA compliance.
"""
from alembic import op
import sqlalchemy as sa

revision = '007_trading_partner_fields'
down_revision = '006_watchtower_sync_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('vendors', sa.Column('gln', sa.String(20), nullable=True))
    op.add_column('vendors', sa.Column('dea_number', sa.String(20), nullable=True))
    op.add_column('vendors', sa.Column('state_license_number', sa.String(50), nullable=True))
    op.add_column('vendors', sa.Column('state', sa.String(50), nullable=True))
    op.add_column('vendors', sa.Column('contact_name', sa.String(255), nullable=True))
    op.add_column('vendors', sa.Column('partner_status', sa.String(50), nullable=True, server_default='active'))
    op.add_column('vendors', sa.Column('verification_status', sa.String(50), nullable=True, server_default='not_verified'))
    op.add_column('vendors', sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('vendors', 'last_verified_at')
    op.drop_column('vendors', 'verification_status')
    op.drop_column('vendors', 'partner_status')
    op.drop_column('vendors', 'contact_name')
    op.drop_column('vendors', 'state')
    op.drop_column('vendors', 'state_license_number')
    op.drop_column('vendors', 'dea_number')
    op.drop_column('vendors', 'gln')
