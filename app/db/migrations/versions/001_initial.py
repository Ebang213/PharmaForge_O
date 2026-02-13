"""initial schema with enums

Revision ID: 001_initial
Revises: 
Create Date: 2026-01-07

Creates all enum types and tables for PharmaForge OS.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types first
    userrole_enum = postgresql.ENUM('owner', 'admin', 'operator', 'viewer', name='userrole', create_type=False)
    userrole_enum.create(op.get_bind(), checkfirst=True)
    
    risklevel_enum = postgresql.ENUM('low', 'medium', 'high', 'critical', name='risklevel', create_type=False)
    risklevel_enum.create(op.get_bind(), checkfirst=True)
    
    rfqstatus_enum = postgresql.ENUM('draft', 'pending_approval', 'sent', 'quotes_received', 'evaluating', 'awarded', 'closed', name='rfqstatus', create_type=False)
    rfqstatus_enum.create(op.get_bind(), checkfirst=True)
    
    messagestatus_enum = postgresql.ENUM('draft', 'approved', 'sent', 'failed', name='messagestatus', create_type=False)
    messagestatus_enum.create(op.get_bind(), checkfirst=True)
    
    epcis_enum = postgresql.ENUM('pending', 'valid', 'invalid', 'chain_break', name='epcisvalidationstatus', create_type=False)
    epcis_enum.create(op.get_bind(), checkfirst=True)
    
    # Organizations
    op.create_table('organizations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('settings', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Users
    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255)),
        sa.Column('role', userrole_enum, default='viewer'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_login', sa.DateTime(timezone=True)),
    )
    
    # Projects
    op.create_table('projects',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'name', name='uq_project_org_name'),
    )
    
    # Audit Logs
    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('entity_type', sa.String(100), index=True),
        sa.Column('entity_id', sa.Integer()),
        sa.Column('details', sa.JSON()),
        sa.Column('ip_address', sa.String(50)),
        sa.Column('user_agent', sa.Text()),
        sa.Index('ix_audit_logs_org_timestamp', 'organization_id', 'timestamp'),
    )
    
    # Vendors
    op.create_table('vendors',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('vendor_code', sa.String(50), index=True),
        sa.Column('vendor_type', sa.String(100)),
        sa.Column('duns_number', sa.String(20)),
        sa.Column('address', sa.Text()),
        sa.Column('country', sa.String(100)),
        sa.Column('contact_email', sa.String(255)),
        sa.Column('contact_phone', sa.String(50)),
        sa.Column('risk_score', sa.Float(), default=0.0),
        sa.Column('risk_level', risklevel_enum, default='low'),
        sa.Column('is_approved', sa.Boolean(), default=False),
        sa.Column('approval_date', sa.DateTime(timezone=True)),
        sa.Column('last_audit_date', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('extra_data', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint('organization_id', 'vendor_code', name='uq_vendor_org_code'),
    )
    
    # Facilities
    op.create_table('facilities',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('facility_code', sa.String(50), index=True),
        sa.Column('facility_type', sa.String(100)),
        sa.Column('fei_number', sa.String(20)),
        sa.Column('address', sa.Text()),
        sa.Column('country', sa.String(100)),
        sa.Column('gmp_status', sa.String(50)),
        sa.Column('last_inspection_date', sa.DateTime(timezone=True)),
        sa.Column('risk_score', sa.Float(), default=0.0),
        sa.Column('risk_level', risklevel_enum, default='low'),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('extra_data', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Watchtower Events
    op.create_table('watchtower_events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('event_type', sa.String(100), nullable=False, index=True),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('external_id', sa.String(255), index=True),
        sa.Column('title', sa.String(500)),
        sa.Column('description', sa.Text()),
        sa.Column('severity', risklevel_enum, default='medium'),
        sa.Column('affected_products', sa.JSON()),
        sa.Column('affected_companies', sa.JSON()),
        sa.Column('event_date', sa.DateTime(timezone=True)),
        sa.Column('source_url', sa.Text()),
        sa.Column('raw_data', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('source', 'external_id', name='uq_event_source_external'),
    )
    
    # Watchtower Alerts
    op.create_table('watchtower_alerts',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('watchtower_events.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('facility_id', sa.Integer(), sa.ForeignKey('facilities.id'), nullable=True),
        sa.Column('severity', risklevel_enum, default='medium'),
        sa.Column('is_acknowledged', sa.Boolean(), default=False),
        sa.Column('acknowledged_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True)),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # EPCIS Uploads
    op.create_table('epcis_uploads',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('file_hash', sa.String(64)),
        sa.Column('content_type', sa.String(100)),
        sa.Column('validation_status', epcis_enum, default='pending'),
        sa.Column('validation_results', sa.JSON()),
        sa.Column('event_count', sa.Integer(), default=0),
        sa.Column('chain_break_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('validated_at', sa.DateTime(timezone=True)),
    )
    
    # EPCIS Events
    op.create_table('epcis_events',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('upload_id', sa.Integer(), sa.ForeignKey('epcis_uploads.id'), nullable=False),
        sa.Column('event_type', sa.String(100)),
        sa.Column('action', sa.String(50)),
        sa.Column('event_time', sa.DateTime(timezone=True)),
        sa.Column('event_timezone', sa.String(10)),
        sa.Column('biz_step', sa.String(255)),
        sa.Column('disposition', sa.String(255)),
        sa.Column('read_point', sa.String(255)),
        sa.Column('biz_location', sa.String(255)),
        sa.Column('epc_list', sa.JSON()),
        sa.Column('quantity_list', sa.JSON()),
        sa.Column('source_list', sa.JSON()),
        sa.Column('destination_list', sa.JSON()),
        sa.Column('raw_event', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # EPCIS Issues
    op.create_table('epcis_issues',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('upload_id', sa.Integer(), sa.ForeignKey('epcis_uploads.id'), nullable=False),
        sa.Column('issue_type', sa.String(100), nullable=False),
        sa.Column('severity', risklevel_enum, default='medium'),
        sa.Column('field_path', sa.String(255)),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('event_index', sa.Integer()),
        sa.Column('suggested_fix', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Documents
    op.create_table('documents',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('file_hash', sa.String(64)),
        sa.Column('content_type', sa.String(100)),
        sa.Column('doc_type', sa.String(100)),
        sa.Column('title', sa.String(500)),
        sa.Column('description', sa.Text()),
        sa.Column('is_processed', sa.Boolean(), default=False),
        sa.Column('chunk_count', sa.Integer(), default=0),
        sa.Column('processing_error', sa.Text()),
        sa.Column('extra_data', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
    )
    
    # Document Chunks
    op.create_table('document_chunks',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('page_number', sa.Integer()),
        sa.Column('section_title', sa.String(500)),
        sa.Column('token_count', sa.Integer()),
        sa.Column('vector_id', sa.String(100)),
        sa.Column('extra_data', sa.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
    )
    
    # Copilot Sessions
    op.create_table('copilot_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Copilot Messages
    op.create_table('copilot_messages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('copilot_sessions.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations', sa.JSON()),
        sa.Column('draft_email', sa.Text()),
        sa.Column('token_count', sa.Integer()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # War Council Sessions
    op.create_table('war_council_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(255)),
        sa.Column('context', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # War Council Responses
    op.create_table('war_council_responses',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('war_council_sessions.id'), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('regulatory_response', sa.Text()),
        sa.Column('supply_chain_response', sa.Text()),
        sa.Column('legal_response', sa.Text()),
        sa.Column('synthesis', sa.Text()),
        sa.Column('references', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # RFQ Requests
    op.create_table('rfq_requests',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rfq_number', sa.String(50), unique=True, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('item_type', sa.String(100), nullable=False),
        sa.Column('item_description', sa.Text(), nullable=False),
        sa.Column('specifications', sa.JSON()),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('quantity_unit', sa.String(50)),
        sa.Column('delivery_location', sa.Text()),
        sa.Column('target_date', sa.DateTime(timezone=True)),
        sa.Column('compliance_constraints', sa.JSON()),
        sa.Column('budget_min', sa.Float()),
        sa.Column('budget_max', sa.Float()),
        sa.Column('currency', sa.String(10), default='USD'),
        sa.Column('status', rfqstatus_enum, default='draft'),
        sa.Column('selected_vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=True),
        sa.Column('decision_notes', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('closed_at', sa.DateTime(timezone=True)),
    )
    
    # RFQ Vendors
    op.create_table('rfq_vendors',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rfq_id', sa.Integer(), sa.ForeignKey('rfq_requests.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('invited_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('responded', sa.Boolean(), default=False),
        sa.Column('declined', sa.Boolean(), default=False),
        sa.Column('decline_reason', sa.Text()),
        sa.UniqueConstraint('rfq_id', 'vendor_id', name='uq_rfq_vendor'),
    )
    
    # RFQ Quotes
    op.create_table('rfq_quotes',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rfq_id', sa.Integer(), sa.ForeignKey('rfq_requests.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(255)),
        sa.Column('file_path', sa.Text()),
        sa.Column('price_per_unit', sa.Float()),
        sa.Column('total_price', sa.Float()),
        sa.Column('currency', sa.String(10), default='USD'),
        sa.Column('moq', sa.Float()),
        sa.Column('lead_time_days', sa.Integer()),
        sa.Column('incoterms', sa.String(20)),
        sa.Column('validity_date', sa.DateTime(timezone=True)),
        sa.Column('payment_terms', sa.String(100)),
        sa.Column('notes', sa.Text()),
        sa.Column('raw_parsed_data', sa.JSON()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # RFQ Messages
    op.create_table('rfq_messages',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rfq_id', sa.Integer(), sa.ForeignKey('rfq_requests.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('recipient_email', sa.String(255)),
        sa.Column('status', messagestatus_enum, default='draft'),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.Column('send_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Vendor Scorecards
    op.create_table('vendor_scorecards',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('rfq_id', sa.Integer(), sa.ForeignKey('rfq_requests.id'), nullable=False),
        sa.Column('vendor_id', sa.Integer(), sa.ForeignKey('vendors.id'), nullable=False),
        sa.Column('quote_id', sa.Integer(), sa.ForeignKey('rfq_quotes.id'), nullable=True),
        sa.Column('price_score', sa.Float(), default=0),
        sa.Column('lead_time_score', sa.Float(), default=0),
        sa.Column('moq_score', sa.Float(), default=0),
        sa.Column('compliance_risk_score', sa.Float(), default=0),
        sa.Column('reliability_score', sa.Float(), default=0),
        sa.Column('overall_score', sa.Float(), default=0),
        sa.Column('price_notes', sa.Text()),
        sa.Column('compliance_issues', sa.JSON()),
        sa.Column('historical_performance', sa.JSON()),
        sa.Column('recommendation', sa.Text()),
        sa.Column('is_recommended', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('rfq_id', 'vendor_id', name='uq_scorecard_rfq_vendor'),
    )


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('vendor_scorecards')
    op.drop_table('rfq_messages')
    op.drop_table('rfq_quotes')
    op.drop_table('rfq_vendors')
    op.drop_table('rfq_requests')
    op.drop_table('war_council_responses')
    op.drop_table('war_council_sessions')
    op.drop_table('copilot_messages')
    op.drop_table('copilot_sessions')
    op.drop_table('document_chunks')
    op.drop_table('documents')
    op.drop_table('epcis_issues')
    op.drop_table('epcis_events')
    op.drop_table('epcis_uploads')
    op.drop_table('watchtower_alerts')
    op.drop_table('watchtower_events')
    op.drop_table('facilities')
    op.drop_table('vendors')
    op.drop_table('audit_logs')
    op.drop_table('projects')
    op.drop_table('users')
    op.drop_table('organizations')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS userrole')
    op.execute('DROP TYPE IF EXISTS risklevel')
    op.execute('DROP TYPE IF EXISTS rfqstatus')
    op.execute('DROP TYPE IF EXISTS messagestatus')
    op.execute('DROP TYPE IF EXISTS epcisvalidationstatus')
