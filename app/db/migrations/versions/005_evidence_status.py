"""Add status, error_message, and processed_at to evidence table

Revision ID: 005_evidence_status
Revises: 004_workflow_runs
Create Date: 2026-01-27

Adds proper evidence processing status tracking:
- status: PENDING -> PROCESSING -> PROCESSED/FAILED
- error_message: Error details if processing fails
- processed_at: Timestamp when processing completed
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005_evidence_status'
down_revision = '004_workflow_runs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create evidence status enum
    op.execute("CREATE TYPE evidencestatus AS ENUM ('pending', 'processing', 'processed', 'failed')")

    # Add new columns to evidence table
    op.add_column('evidence', sa.Column('status', sa.Enum('pending', 'processing', 'processed', 'failed', name='evidencestatus'), nullable=True))
    op.add_column('evidence', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('evidence', sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True))

    # Set existing evidence with extracted_text to 'processed', others to 'pending'
    op.execute("""
        UPDATE evidence
        SET status = 'processed', processed_at = uploaded_at
        WHERE extracted_text IS NOT NULL AND extracted_text != ''
    """)
    op.execute("""
        UPDATE evidence
        SET status = 'pending'
        WHERE extracted_text IS NULL OR extracted_text = ''
    """)

    # Make status NOT NULL after setting defaults
    op.alter_column('evidence', 'status', nullable=False, server_default='pending')


def downgrade() -> None:
    op.drop_column('evidence', 'processed_at')
    op.drop_column('evidence', 'error_message')
    op.drop_column('evidence', 'status')
    op.execute("DROP TYPE evidencestatus")
