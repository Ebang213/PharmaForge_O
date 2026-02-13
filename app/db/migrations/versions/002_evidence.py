"""evidence and hardening

Revision ID: 002_evidence
Revises: 001_initial
Create Date: 2026-01-08

Adds Evidence table and updates Watchtower/EPCIS tables.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_evidence'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create WatchtowerAlertStatus enum
    alertstatus_enum = postgresql.ENUM('active', 'resolved', name='watchtoweralertstatus')
    alertstatus_enum.create(op.get_bind(), checkfirst=True)

    # 2. Create Evidence table
    op.create_table('evidence',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('content_type', sa.String(100)),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(64), index=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('extracted_text', sa.Text()),
        sa.Column('source', sa.String(50), default='upload'),
        sa.Column('meta_data', sa.JSON(), default={}),
    )

    # 3. Update WatchtowerEvent
    op.add_column('watchtower_events', sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=True))

    # 4. Update WatchtowerAlert
    # Note: event_id becomes nullable
    op.alter_column('watchtower_alerts', 'event_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('watchtower_alerts', sa.Column('evidence_id', sa.Integer(), sa.ForeignKey('evidence.id'), nullable=True))
    op.add_column('watchtower_alerts', sa.Column('title', sa.String(500), nullable=True))
    op.add_column('watchtower_alerts', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('watchtower_alerts', sa.Column('status', sa.Enum('active', 'resolved', name='watchtoweralertstatus'), nullable=True))
    op.add_column('watchtower_alerts', sa.Column('source', sa.String(100), nullable=True))
    
    # Set default status for existing alerts
    op.execute("UPDATE watchtower_alerts SET status = 'active' WHERE status IS NULL")

    # 5. Update EPCISUpload
    op.add_column('epcis_uploads', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove columns from EPCISUpload
    op.drop_column('epcis_uploads', 'error_message')

    # Remove columns from WatchtowerAlert
    op.drop_column('watchtower_alerts', 'source')
    op.drop_column('watchtower_alerts', 'status')
    op.drop_column('watchtower_alerts', 'description')
    op.drop_column('watchtower_alerts', 'title')
    op.drop_column('watchtower_alerts', 'evidence_id')
    op.alter_column('watchtower_alerts', 'event_id', existing_type=sa.Integer(), nullable=False)

    # Remove columns from WatchtowerEvent
    op.drop_column('watchtower_events', 'vendor_id')

    # Drop Evidence table
    op.drop_table('evidence')

    # Drop enum
    op.execute('DROP TYPE IF EXISTS watchtoweralertstatus')
