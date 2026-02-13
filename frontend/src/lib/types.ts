// Document types for Copilot
export interface Document {
    id: number;
    filename: string;
    title?: string;
    doc_type: string;
    is_processed: boolean;
    chunk_count: number;
    created_at: string;
}

export interface Citation {
    doc_name: string;
    content_preview: string;
    confidence: number;
    page?: number;
}

export interface CopilotResponse {
    answer: string;
    citations: Citation[];
    session_id: number;
    latency_ms: number;
    draft_email?: string;
}

// Watchtower types
export interface RiskSummary {
    total_vendors: number;
    high_risk_vendors: number;
    total_facilities: number;
    high_risk_facilities: number;
    active_alerts: number;
    recent_events: number;
    evidence_count: number;
    feed_items?: number;
    provider_statuses?: FeedSource[];
}

export interface WatchtowerAlert {
    id: number;
    vendor_id: number;
    vendor_name?: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    title?: string;
    description?: string;
    event?: {
        title: string;
        description?: string;
    };
    status: 'active' | 'resolved';
    created_at: string;
}

export interface Evidence {
    id: number;
    filename: string;
    content_type?: string;
    uploaded_at: string;
    status: string;
    vendor_id?: number;
    vendor_name?: string;
    source_type?: string;
    source?: string;  // 'watchtower' or 'copilot'
    notes?: string;
    extracted_text_preview?: string;
}

export interface AnalysisResponse {
    doc_type: string;
    severity: string;
    matched_vendor?: string;
    alert_id?: number;
    event_id?: number;
}

// Live Feed types
export interface FeedItem {
    id: number;
    source: string;
    external_id: string;
    title: string;
    url?: string;
    published_at?: string;
    summary?: string;
    category?: string;
    created_at: string;
}

export interface FeedSource {
    source_id: string;
    source_name: string;
    category: string;
    last_success_at?: string;
    last_error_at?: string;
    last_error_message?: string;
    last_run_at?: string;
    // Enhanced tracking fields
    last_http_status?: number;
    items_fetched?: number;
    items_saved?: number;
}

export interface FeedSummary {
    total_items: number;
    by_source: Record<string, number>;
    last_sync_at?: string;
    all_sources_healthy: boolean;
    sources_count: number;
    sources_detail: {
        source: string;
        last_success_at?: string;
        last_error_at?: string;
        last_error_message?: string;
        healthy: boolean;
    }[];
    total_vendors: number;
    high_risk_vendors: number;
    active_alerts: number;
}

// Correlation types (Risk Intelligence Loop)
export interface VendorMatch {
    vendor_id: number | null;
    name: string;
    match_basis: string;
    risk_score: number | null;
    risk_level: string | null;
}

export interface WatchtowerSnapshot {
    total_feed_items: number;
    active_alerts: number;
    sources_status: { source: string; last_success_at: string | null; healthy: boolean }[];
    top_items: { id: number; source: string; title: string; category: string; published_at: string | null }[];
    timestamp: string;
}

export interface CorrelationResult {
    evidence_id: number;
    watchtower_snapshot: WatchtowerSnapshot;
    vendor_matches: VendorMatch[];
    narrative: string[];
    correlation_timestamp: string;
}

// Vendor types
export interface Vendor {
    id: number;
    name: string;
    vendor_code?: string;
    vendor_type?: string;
    country?: string;
    contact_email?: string;
    risk_score: number;
    risk_level: string;
    alert_count: number;
    is_approved: boolean;
    created_at: string;
    source?: string;  // 'watchtower' or 'copilot'
}

// Sourcing / RFQ types
export interface RFQ {
    id: number;
    rfq_number: string;
    title: string;
    item_type: string;
    item_description?: string;
    quantity: number;
    quantity_unit?: string;
    delivery_location?: string;
    target_date?: string;
    status: string;
    vendor_count?: number;
    quote_count?: number;
    vendors?: Vendor[];
    quotes?: Quote[];
    messages?: any[];
    created_at: string;
}

export interface Quote {
    id: number;
    rfq_id: number;
    vendor_id: number;
    vendor_name?: string;
    unit_price: number;
    lead_time_days: number;
    notes?: string;
    created_at: string;
}

export interface Scorecard {
    vendor_id: number;
    vendor_name: string;
    overall_score: number;
    price_score: number;
    lead_time_score: number;
    compliance_score: number;
    is_recommended: boolean;
}

// War Council types
export interface Agent {
    id: string;
    name: string;
    role: string;
    avatar?: string;
    specialty: string;
}

export interface Discussion {
    id: number;
    topic: string;
    agents: string[];
    messages: DiscussionMessage[];
    status: 'active' | 'completed';
    created_at: string;
}

export interface DiscussionMessage {
    agent_id: string;
    agent_name: string;
    content: string;
    timestamp: string;
}

// DSCSA / EPCIS types
export interface EpcisTransaction {
    id: number;
    event_type: string;
    event_id: string;
    status: 'valid' | 'invalid' | 'warning';
    product_name?: string;
    gtin?: string;
    lot?: string;
    created_at: string;
    errors?: string[];
}

export interface ComplianceReport {
    total_transactions: number;
    valid_count: number;
    invalid_count: number;
    warning_count: number;
    compliance_rate: number;
}

// Audit Log types
export interface AuditLogEntry {
    id: number;
    timestamp: string;
    user_id?: string;
    user_email?: string;
    action: string;
    entity_type?: string;
    entity_id?: string;
    details?: Record<string, unknown>;
    ip_address?: string;
}

// User types
export interface User {
    id: string;
    email: string;
    full_name: string;
    organization_id: string;
    organization_name: string;
    role: string;
}

// API response wrapper
export interface ApiResponse<T> {
    data: T;
    message?: string;
    success: boolean;
}

// EPCIS Upload types for DSCSA page
export interface EPCISUpload {
    id: number;
    filename: string;
    validation_status: 'valid' | 'invalid' | 'chain_break' | 'pending';
    event_count: number;
    chain_break_count: number;
    issues?: EPCISIssue[];
    events?: any[];
    validation_results?: any;
    created_at: string;
}

export interface EPCISIssue {
    type: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    message: string;
    suggested_fix?: string;
}

// War Council types
export interface PersonaResponse {
    persona: string;
    response: string;
    risk_level: 'critical' | 'high' | 'medium' | 'low';
    key_points: string[];
    recommended_actions: string[];
}

export interface WarCouncilResult {
    synthesis: string;
    overall_risk: 'critical' | 'high' | 'medium' | 'low';
    priority_actions: string[];
    regulatory: PersonaResponse;
    supply_chain: PersonaResponse;
    legal: PersonaResponse;
}
