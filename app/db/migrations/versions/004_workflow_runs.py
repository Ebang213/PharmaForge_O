"""Add workflow_runs, risk_findings_records, and action_plans tables

Revision ID: 004_workflow_runs
Revises: 003_watchtower_feed
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_workflow_runs'
down_revision = '003_watchtower_feed'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflow run status enum if it doesn't exist
    workflow_status = postgresql.ENUM('pending', 'running', 'success', 'failed', name='workflowrunstatus', create_type=False)
    
    # Create the enum type
    op.execute("CREATE TYPE workflowrunstatus AS ENUM ('pending', 'running', 'success', 'failed')")
    
    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('status', workflow_status, nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('findings_count', sa.Integer(), default=0),
        sa.Column('correlations_count', sa.Integer(), default=0),
        sa.Column('actions_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflow_runs_id', 'workflow_runs', ['id'])
    op.create_index('ix_workflow_runs_org_id', 'workflow_runs', ['organization_id'])
    op.create_index('ix_workflow_runs_evidence_id', 'workflow_runs', ['evidence_id'])
    op.create_index('ix_workflow_runs_status', 'workflow_runs', ['status'])
    
    # Create risk_findings_records table (persistent findings)
    op.create_table(
        'risk_findings_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_run_id', sa.Integer(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='MEDIUM'),
        sa.Column('cfr_refs', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('citations', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('entities', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id']),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_risk_findings_records_id', 'risk_findings_records', ['id'])
    op.create_index('ix_risk_findings_records_workflow_run_id', 'risk_findings_records', ['workflow_run_id'])
    op.create_index('ix_risk_findings_records_evidence_id', 'risk_findings_records', ['evidence_id'])
    
    # Create action_plans table
    op.create_table(
        'action_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workflow_run_id', sa.Integer(), nullable=False),
        sa.Column('evidence_id', sa.Integer(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('actions', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('owners', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('deadlines', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('correlation_data', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['workflow_run_id'], ['workflow_runs.id']),
        sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_action_plans_id', 'action_plans', ['id'])
    op.create_index('ix_action_plans_workflow_run_id', 'action_plans', ['workflow_run_id'])
    op.create_index('ix_action_plans_evidence_id', 'action_plans', ['evidence_id'])


def downgrade() -> None:
    op.drop_index('ix_action_plans_evidence_id', table_name='action_plans')
    op.drop_index('ix_action_plans_workflow_run_id', table_name='action_plans')
    op.drop_index('ix_action_plans_id', table_name='action_plans')
    op.drop_table('action_plans')
    
    op.drop_index('ix_risk_findings_records_evidence_id', table_name='risk_findings_records')
    op.drop_index('ix_risk_findings_records_workflow_run_id', table_name='risk_findings_records')
    op.drop_index('ix_risk_findings_records_id', table_name='risk_findings_records')
    op.drop_table('risk_findings_records')
    
    op.drop_index('ix_workflow_runs_status', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_evidence_id', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_org_id', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_id', table_name='workflow_runs')
    op.drop_table('workflow_runs')
    
    op.execute("DROP TYPE workflowrunstatus")
