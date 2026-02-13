"""Add watchtower_items and watchtower_sync_status tables

Revision ID: 003_watchtower_feed
Revises: 
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_watchtower_feed'
down_revision = '002_evidence'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create watchtower_items table for live feed items
    op.create_table(
        'watchtower_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('external_id', sa.String(length=500), nullable=False),
        sa.Column('title', sa.String(length=1000), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('raw_json', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', name='uq_watchtower_item_source_extid')
    )
    op.create_index('ix_watchtower_items_source', 'watchtower_items', ['source'])
    op.create_index('ix_watchtower_items_published_at', 'watchtower_items', ['published_at'])
    op.create_index('ix_watchtower_items_category', 'watchtower_items', ['category'])
    op.create_index('ix_watchtower_items_source_pub', 'watchtower_items', ['source', 'published_at'])
    
    # Create watchtower_sync_status table
    op.create_table(
        'watchtower_sync_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.Text(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', name='uq_watchtower_sync_status_source')
    )
    op.create_index('ix_watchtower_sync_status_source', 'watchtower_sync_status', ['source'])


def downgrade() -> None:
    op.drop_index('ix_watchtower_sync_status_source', table_name='watchtower_sync_status')
    op.drop_table('watchtower_sync_status')
    
    op.drop_index('ix_watchtower_items_source_pub', table_name='watchtower_items')
    op.drop_index('ix_watchtower_items_category', table_name='watchtower_items')
    op.drop_index('ix_watchtower_items_published_at', table_name='watchtower_items')
    op.drop_index('ix_watchtower_items_source', table_name='watchtower_items')
    op.drop_table('watchtower_items')
