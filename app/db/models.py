"""
SQLAlchemy ORM models for PharmaForge OS.
All models are scoped to organization/project for multi-tenancy.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Float, 
    ForeignKey, Enum, JSON, LargeBinary, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.session import Base


# ============= ENUMS =============
# Using create_type=False to prevent recreation attempts on every boot.
# Enums are created via Alembic migration.

class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class RFQStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    SENT = "sent"
    QUOTES_RECEIVED = "quotes_received"
    EVALUATING = "evaluating"
    AWARDED = "awarded"
    CLOSED = "closed"


class MessageStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EPCISValidationStatus(str, enum.Enum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    CHAIN_BREAK = "chain_break"


class WatchtowerAlertStatus(str, enum.Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class EvidenceStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

# Pre-defined SQLAlchemy enum types with create_type=False
# This prevents "type already exists" errors when Base.metadata.create_all() runs
# Using values_callable to ensure we use enum values (lowercase) not names (UPPERCASE)
def enum_values(enum_cls):
    return [e.value for e in enum_cls]

UserRoleType = Enum(
    *enum_values(UserRole), 
    name='userrole', 
    create_type=False
)
RFQStatusType = Enum(
    *enum_values(RFQStatus), 
    name='rfqstatus', 
    create_type=False
)
MessageStatusType = Enum(
    *enum_values(MessageStatus), 
    name='messagestatus', 
    create_type=False
)
RiskLevelType = Enum(
    *enum_values(RiskLevel), 
    name='risklevel', 
    create_type=False
)
EPCISStatusType = Enum(
    *enum_values(EPCISValidationStatus), 
    name='epcisvalidationstatus', 
    create_type=False
)
WatchtowerAlertStatusType = Enum(
    *enum_values(WatchtowerAlertStatus),
    name='watchtoweralertstatus',
    create_type=False
)
EvidenceStatusType = Enum(
    *enum_values(EvidenceStatus),
    name='evidencestatus',
    create_type=False
)

# ============= AUTH & MULTI-TENANCY =============



class Organization(Base):
    """Organization for multi-tenancy."""
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    settings = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", back_populates="organization")
    projects = relationship("Project", back_populates="organization")
    vendors = relationship("Vendor", back_populates="organization")
    facilities = relationship("Facility", back_populates="organization")
    rfq_requests = relationship("RFQRequest", back_populates="organization")
    audit_logs = relationship("AuditLog", back_populates="organization")


class User(Base):
    """User accounts."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(UserRoleType, default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    organization = relationship("Organization", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user")
    copilot_sessions = relationship("CopilotSession", back_populates="user")


class Project(Base):
    """Projects within an organization."""
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="projects")
    epcis_uploads = relationship("EPCISUpload", back_populates="project")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'name', name='uq_project_org_name'),
    )


# ============= AUDIT LOG =============

class AuditLog(Base):
    """Compliance-grade audit log."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(100), index=True)
    entity_id = Column(Integer)
    details = Column(JSON)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    organization = relationship("Organization", back_populates="audit_logs")
    
    __table_args__ = (
        Index('ix_audit_logs_org_timestamp', 'organization_id', 'timestamp'),
    )


# ============= WATCHTOWER =============

class Vendor(Base):
    """Vendor/Supplier master data."""
    __tablename__ = "vendors"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    vendor_code = Column(String(50), index=True)
    vendor_type = Column(String(100))  # API supplier, excipient, packaging, CMO, etc.
    duns_number = Column(String(20))
    address = Column(Text)
    country = Column(String(100))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    risk_score = Column(Float, default=0.0)
    risk_level = Column(RiskLevelType, default=RiskLevel.LOW)
    is_approved = Column(Boolean, default=False)
    approval_date = Column(DateTime(timezone=True))
    last_audit_date = Column(DateTime(timezone=True))
    notes = Column(Text)
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="vendors")
    facilities = relationship("Facility", back_populates="vendor")
    alerts = relationship("WatchtowerAlert", back_populates="vendor")
    rfq_vendors = relationship("RFQVendor", back_populates="vendor")
    scorecards = relationship("VendorScorecard", back_populates="vendor")
    evidence = relationship("Evidence", back_populates="vendor")
    
    __table_args__ = (
        UniqueConstraint('organization_id', 'vendor_code', name='uq_vendor_org_code'),
    )


class Facility(Base):
    """Manufacturing/distribution facilities."""
    __tablename__ = "facilities"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    name = Column(String(255), nullable=False)
    facility_code = Column(String(50), index=True)
    facility_type = Column(String(100))  # manufacturing, warehouse, distribution
    fei_number = Column(String(20))  # FDA Establishment Identifier
    address = Column(Text)
    country = Column(String(100))
    gmp_status = Column(String(50))
    last_inspection_date = Column(DateTime(timezone=True))
    risk_score = Column(Float, default=0.0)
    risk_level = Column(RiskLevelType, default=RiskLevel.LOW)
    latitude = Column(Float)
    longitude = Column(Float)
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="facilities")
    vendor = relationship("Vendor", back_populates="facilities")
    alerts = relationship("WatchtowerAlert", back_populates="facility")


class WatchtowerEvent(Base):
    """FDA enforcement/shortage events ingested from external sources."""
    __tablename__ = "watchtower_events"
    
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    event_type = Column(String(100), nullable=False, index=True)  # shortage, recall, warning_letter, inspection
    source = Column(String(100), nullable=False)  # fda, ema, upload
    external_id = Column(String(255), index=True)
    title = Column(String(500))
    description = Column(Text)
    severity = Column(RiskLevelType, default=RiskLevel.MEDIUM)
    affected_products = Column(JSON)  # list of product names/NDCs
    affected_companies = Column(JSON)  # list of company names
    event_date = Column(DateTime(timezone=True))
    source_url = Column(Text)
    raw_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    alerts = relationship("WatchtowerAlert", back_populates="event")
    
    __table_args__ = (
        UniqueConstraint('source', 'external_id', name='uq_event_source_external'),
    )


class WatchtowerAlert(Base):
    """Alerts linking events to org vendors/facilities."""
    __tablename__ = "watchtower_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("watchtower_events.id"), nullable=True) # Nullable if triggered by evidence
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    facility_id = Column(Integer, ForeignKey("facilities.id"), nullable=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    severity = Column(RiskLevelType, default=RiskLevel.MEDIUM)
    title = Column(String(500))
    description = Column(Text)
    status = Column(WatchtowerAlertStatusType, default=WatchtowerAlertStatus.ACTIVE)
    source = Column(String(100)) # "system", "upload", "feed"
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    event = relationship("WatchtowerEvent", back_populates="alerts")
    vendor = relationship("Vendor", back_populates="alerts")
    facility = relationship("Facility", back_populates="alerts")
    evidence = relationship("Evidence", back_populates="alerts")


class Evidence(Base):
    """Uploaded documents for risk evidence."""
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100))
    storage_path = Column(Text, nullable=False)
    sha256 = Column(String(64), index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    extracted_text = Column(Text)
    source = Column(String(50), default="upload")
    meta_data = Column(JSON, default={})
    # Processing status fields
    status = Column(EvidenceStatusType, default=EvidenceStatus.PENDING)
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    alerts = relationship("WatchtowerAlert", back_populates="evidence")
    vendor = relationship("Vendor", back_populates="evidence")


# ============= WATCHTOWER LIVE FEED =============

class WatchtowerItem(Base):
    """Items from external feeds (FDA RSS, etc.) for Watchtower live monitoring."""
    __tablename__ = "watchtower_items"
    
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False, index=True)  # e.g., "fda_recalls"
    external_id = Column(String(500), nullable=False)
    title = Column(String(1000), nullable=False)
    url = Column(Text)
    published_at = Column(DateTime(timezone=True), index=True)
    summary = Column(Text)
    category = Column(String(100), index=True)  # "recall", "shortage", "warning_letter"
    raw_json = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('source', 'external_id', name='uq_watchtower_item_source_extid'),
        Index('ix_watchtower_items_source_pub', 'source', 'published_at'),
    )


class WatchtowerSyncStatus(Base):
    """
    Tracks sync status for each Watchtower feed source.

    Provides per-source health tracking including:
    - Last run timestamps (success/error)
    - Error messages for diagnostics
    - HTTP status codes for debugging
    - Item counts for monitoring
    """
    __tablename__ = "watchtower_sync_status"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), unique=True, nullable=False, index=True)
    last_success_at = Column(DateTime(timezone=True))
    last_error_at = Column(DateTime(timezone=True))
    last_error_message = Column(Text)
    last_run_at = Column(DateTime(timezone=True))
    # Additional tracking fields
    last_http_status = Column(Integer, nullable=True)  # HTTP status code from last attempt
    items_fetched = Column(Integer, default=0)  # Items returned from provider
    items_saved = Column(Integer, default=0)  # New items persisted to DB
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============= DSCSA / EPCIS =============

class EPCISUpload(Base):
    """EPCIS file uploads and validation results."""
    __tablename__ = "epcis_uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    file_hash = Column(String(64))  # SHA-256
    content_type = Column(String(100))  # json, xml
    validation_status = Column(EPCISStatusType, default=EPCISValidationStatus.PENDING)
    validation_results = Column(JSON)  # detailed validation output
    error_message = Column(Text) # Explicit error message for failures
    event_count = Column(Integer, default=0)
    chain_break_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True))
    
    # Relationships
    project = relationship("Project", back_populates="epcis_uploads")
    events = relationship("EPCISEvent", back_populates="upload")
    issues = relationship("EPCISIssue", back_populates="upload")


class EPCISEvent(Base):
    """Parsed EPCIS events from uploads."""
    __tablename__ = "epcis_events"
    
    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("epcis_uploads.id"), nullable=False)
    event_type = Column(String(100))  # ObjectEvent, AggregationEvent, TransactionEvent, TransformationEvent
    action = Column(String(50))  # ADD, OBSERVE, DELETE
    event_time = Column(DateTime(timezone=True))
    event_timezone = Column(String(10))
    biz_step = Column(String(255))
    disposition = Column(String(255))
    read_point = Column(String(255))
    biz_location = Column(String(255))
    epc_list = Column(JSON)  # List of EPCs
    quantity_list = Column(JSON)
    source_list = Column(JSON)
    destination_list = Column(JSON)
    raw_event = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    upload = relationship("EPCISUpload", back_populates="events")


class EPCISIssue(Base):
    """Validation issues found in EPCIS uploads."""
    __tablename__ = "epcis_issues"
    
    id = Column(Integer, primary_key=True, index=True)
    upload_id = Column(Integer, ForeignKey("epcis_uploads.id"), nullable=False)
    issue_type = Column(String(100), nullable=False)  # missing_field, invalid_format, chain_break, etc.
    severity = Column(RiskLevelType, default=RiskLevel.MEDIUM)
    field_path = Column(String(255))
    message = Column(Text, nullable=False)
    event_index = Column(Integer)
    suggested_fix = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    upload = relationship("EPCISUpload", back_populates="issues")


# ============= REGULATORY COPILOT =============

class Document(Base):
    """Uploaded documents for RAG."""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    file_hash = Column(String(64))
    content_type = Column(String(100))
    doc_type = Column(String(100))  # fda_guidance, cfr, sop, policy
    title = Column(String(500))
    description = Column(Text)
    is_processed = Column(Boolean, default=False)
    chunk_count = Column(Integer, default=0)
    processing_error = Column(Text)
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document")


class DocumentChunk(Base):
    """Document chunks for RAG retrieval."""
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer)
    section_title = Column(String(500))
    token_count = Column(Integer)
    vector_id = Column(String(100))  # ID in vector DB
    extra_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_doc_index'),
    )


class CopilotSession(Base):
    """Copilot Q&A sessions."""
    __tablename__ = "copilot_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="copilot_sessions")
    messages = relationship("CopilotMessage", back_populates="session")


class CopilotMessage(Base):
    """Individual Q&A messages in a copilot session."""
    __tablename__ = "copilot_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("copilot_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    citations = Column(JSON)  # Array of {doc_name, chunk_id, page, confidence}
    draft_email = Column(Text)
    token_count = Column(Integer)
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("CopilotSession", back_populates="messages")


# ============= WAR COUNCIL =============

class WarCouncilSession(Base):
    """War Council multi-persona sessions."""
    __tablename__ = "war_council_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255))
    context = Column(JSON)  # Related vendors, shipments, events
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    responses = relationship("WarCouncilResponse", back_populates="session")


class WarCouncilResponse(Base):
    """Multi-persona responses in War Council."""
    __tablename__ = "war_council_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("war_council_sessions.id"), nullable=False)
    question = Column(Text, nullable=False)
    regulatory_response = Column(Text)
    supply_chain_response = Column(Text)
    legal_response = Column(Text)
    synthesis = Column(Text)
    references = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("WarCouncilSession", back_populates="responses")


# ============= SMART SOURCING SDR =============

class RFQRequest(Base):
    """Request for Quote."""
    __tablename__ = "rfq_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    rfq_number = Column(String(50), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    item_type = Column(String(100), nullable=False)  # API, excipient, packaging
    item_description = Column(Text, nullable=False)
    specifications = Column(JSON)  # Detailed specs
    quantity = Column(Float, nullable=False)
    quantity_unit = Column(String(50))
    delivery_location = Column(Text)
    target_date = Column(DateTime(timezone=True))
    compliance_constraints = Column(JSON)  # e.g., GMP, FDA-approved, ICH
    budget_min = Column(Float)
    budget_max = Column(Float)
    currency = Column(String(10), default="USD")
    status = Column(RFQStatusType, default=RFQStatus.DRAFT)
    selected_vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    decision_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True))
    
    # Relationships
    organization = relationship("Organization", back_populates="rfq_requests")
    rfq_vendors = relationship("RFQVendor", back_populates="rfq_request")
    quotes = relationship("RFQQuote", back_populates="rfq_request")
    messages = relationship("RFQMessage", back_populates="rfq_request")


class RFQVendor(Base):
    """Vendors invited to an RFQ."""
    __tablename__ = "rfq_vendors"
    
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfq_requests.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    invited_at = Column(DateTime(timezone=True), server_default=func.now())
    responded = Column(Boolean, default=False)
    declined = Column(Boolean, default=False)
    decline_reason = Column(Text)
    
    # Relationships
    rfq_request = relationship("RFQRequest", back_populates="rfq_vendors")
    vendor = relationship("Vendor", back_populates="rfq_vendors")
    
    __table_args__ = (
        UniqueConstraint('rfq_id', 'vendor_id', name='uq_rfq_vendor'),
    )


class RFQQuote(Base):
    """Quotes received from vendors."""
    __tablename__ = "rfq_quotes"
    
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfq_requests.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255))
    file_path = Column(Text)
    price_per_unit = Column(Float)
    total_price = Column(Float)
    currency = Column(String(10), default="USD")
    moq = Column(Float)  # Minimum Order Quantity
    lead_time_days = Column(Integer)
    incoterms = Column(String(20))  # FOB, CIF, DDP, etc.
    validity_date = Column(DateTime(timezone=True))
    payment_terms = Column(String(100))
    notes = Column(Text)
    raw_parsed_data = Column(JSON)  # Full parsed output
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    rfq_request = relationship("RFQRequest", back_populates="quotes")


class RFQMessage(Base):
    """Outbound messages for RFQs (require approval)."""
    __tablename__ = "rfq_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfq_requests.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    recipient_email = Column(String(255))
    status = Column(MessageStatusType, default=MessageStatus.DRAFT)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    send_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    rfq_request = relationship("RFQRequest", back_populates="messages")


class VendorScorecard(Base):
    """Vendor scorecards for comparison."""
    __tablename__ = "vendor_scorecards"
    
    id = Column(Integer, primary_key=True, index=True)
    rfq_id = Column(Integer, ForeignKey("rfq_requests.id"), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False)
    quote_id = Column(Integer, ForeignKey("rfq_quotes.id"), nullable=True)
    
    # Scores (0-100)
    price_score = Column(Float, default=0)
    lead_time_score = Column(Float, default=0)
    moq_score = Column(Float, default=0)
    compliance_risk_score = Column(Float, default=0)  # Lower is better
    reliability_score = Column(Float, default=0)
    overall_score = Column(Float, default=0)
    
    # Details
    price_notes = Column(Text)
    compliance_issues = Column(JSON)
    historical_performance = Column(JSON)
    recommendation = Column(Text)
    is_recommended = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    vendor = relationship("Vendor", back_populates="scorecards")
    
    __table_args__ = (
        UniqueConstraint('rfq_id', 'vendor_id', name='uq_scorecard_rfq_vendor'),
    )


# ============= GOLDEN WORKFLOW =============

class WorkflowRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


WorkflowRunStatusType = Enum(
    *enum_values(WorkflowRunStatus),
    name='workflowrunstatus',
    create_type=False
)


class WorkflowRun(Base):
    """Tracks Golden Workflow runs for audit and export."""
    __tablename__ = "workflow_runs"
    
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(WorkflowRunStatusType, default=WorkflowRunStatus.PENDING)
    error_message = Column(Text)
    findings_count = Column(Integer, default=0)
    correlations_count = Column(Integer, default=0)
    actions_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    findings = relationship("RiskFindingRecord", back_populates="workflow_run")
    action_plan = relationship("ActionPlanRecord", back_populates="workflow_run", uselist=False)


class RiskFindingRecord(Base):
    """Persistent risk findings from workflow runs."""
    __tablename__ = "risk_findings_records"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    severity = Column(String(20), default="MEDIUM")
    cfr_refs = Column(JSON, default=[])
    citations = Column(JSON, default=[])
    entities = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="findings")


class ActionPlanRecord(Base):
    """Persistent action plans from workflow runs."""
    __tablename__ = "action_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    rationale = Column(Text)
    actions = Column(JSON, default=[])
    owners = Column(JSON, default=[])
    deadlines = Column(JSON, default=[])
    correlation_data = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    workflow_run = relationship("WorkflowRun", back_populates="action_plan")
