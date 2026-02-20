"""Add missing columns to watchtower_sync_status table

Revision ID: 006_watchtower_sync_columns
Revises: 005_evidence_status
Create Date: 2026-02-20

Adds columns that exist in the model but were missing from migration 003:
- last_http_status: HTTP status code from last provider fetch attempt
- items_fetched: Number of items returned from provider
- items_saved: Number of new items persisted to DB
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '006_watchtower_sync_columns'
down_revision = '005_evidence_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('watchtower_sync_status', sa.Column('last_http_status', sa.Integer(), nullable=True))
    op.add_column('watchtower_sync_status', sa.Column('items_fetched', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('watchtower_sync_status', sa.Column('items_saved', sa.Integer(), nullable=True, server_default='0'))


def downgrade() -> None:
    op.drop_column('watchtower_sync_status', 'items_saved')
    op.drop_column('watchtower_sync_status', 'items_fetched')
    op.drop_column('watchtower_sync_status', 'last_http_status')
