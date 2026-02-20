import axios, { AxiosInstance } from 'axios';

// Get base URL for API calls
// In production (built and served via nginx), use same-origin (empty string)
// In development (Vite dev server), use the proxied or direct API URL
const getBaseUrl = (): string => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const env = (import.meta as any).env;

    // If VITE_API_URL is explicitly set, use it
    if (env?.VITE_API_URL) {
        return env.VITE_API_URL;
    }

    // In production build (MODE === 'production'), use same-origin
    if (env?.MODE === 'production' || env?.PROD) {
        return '';  // Same origin - nginx proxies /api/* to backend
    }

    // Development: use Vite proxy (configured in vite.config.ts)
    return '';  // Vite dev server also proxies /api/*
};

// Create axios instance with base configuration
const api: AxiosInstance = axios.create({
    baseURL: getBaseUrl(),
    headers: {
        'Content-Type': 'application/json',
    },
});


// Request interceptor to add auth token
api.interceptors.request.use((config) => {
    const token = sessionStorage.getItem('pharmaforge_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Centralized error logger - logs URL + status for all failures
function logApiError(error: unknown): void {
    if (error && typeof error === 'object' && 'config' in error) {
        const axiosError = error as { config?: { url?: string; method?: string }; response?: { status?: number; data?: unknown }; message?: string };
        const url = axiosError.config?.url || 'unknown';
        const method = axiosError.config?.method?.toUpperCase() || 'UNKNOWN';
        const status = axiosError.response?.status || 'NETWORK_ERROR';
        const detail = axiosError.response?.data;
        console.error(`[API FAILURE] ${method} ${url} -> ${status}`, detail || axiosError.message);
    } else {
        console.error('[API FAILURE] Unknown error:', error);
    }
}

// Response interceptor for error handling with centralized logging
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // Always log failures with URL and status
        logApiError(error);

        if (error.response?.status === 401) {
            // Clear auth and redirect to login on 401
            sessionStorage.removeItem('pharmaforge_token');
            sessionStorage.removeItem('pharmaforge_user');
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

// Export for direct use if needed
export { logApiError };

// Auth API
export const authApi = {
    login: (email: string, password: string) =>
        api.post('/api/auth/login', { email, password }),

    register: (data: {
        email: string;
        password: string;
        full_name: string;
        organization_name: string
    }) => api.post('/api/auth/register', data),

    me: () => api.get('/api/auth/me'),

    refreshToken: () => api.post('/api/auth/refresh'),
};

// DSCSA / EPCIS API
export const dscsaApi = {
    // List all uploads
    uploads: () => api.get('/api/dscsa/uploads'),

    // Upload a new file (alias)
    upload: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/api/dscsa/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    uploadEpcis: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/api/dscsa/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    // Get a specific upload by ID
    getUpload: (id: number) => api.get(`/api/dscsa/uploads/${id}`),

    // Download audit packet for an upload
    downloadAuditPacket: (id: number) => api.get(`/api/dscsa/uploads/${id}/audit-packet`),

    getTransactions: (params?: {
        limit?: number;
        offset?: number;
        status?: string
    }) => api.get('/api/dscsa/transactions', { params }),

    getTransaction: (id: string) => api.get(`/api/dscsa/transactions/${id}`),

    validateEpcis: (data: object) => api.post('/api/dscsa/validate', data),

    getComplianceReport: () => api.get('/api/dscsa/compliance-report'),

    // Specific EPCIS paths
    epcisUpload: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/api/dscsa/epcis/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    epcisList: () => api.get('/api/dscsa/epcis/uploads'),
    epcisDetail: (id: number) => api.get(`/api/dscsa/epcis/uploads/${id}`),
};

// Copilot Chat API
export const copilotApi = {
    sendMessage: (message: string, context?: object) =>
        api.post('/api/copilot/chat', { message, context }),

    // Document management
    documents: () => api.get('/api/copilot/documents'),

    uploadDocument: (file: File, docType: string) => {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('doc_type', docType);
        return api.post('/api/copilot/documents', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    // Query with session tracking
    query: (question: string, sessionId?: number) =>
        api.post('/api/copilot/query', { question, session_id: sessionId }),

    getHistory: () => api.get('/api/copilot/history'),

    clearHistory: () => api.delete('/api/copilot/history'),
};

// Evidence API - Knowledge Base uploads
export const evidenceApi = {
    // Upload a new evidence file (PDF/TXT)
    upload: (file: File) => {
        const formData = new FormData();
        formData.append('file', file);
        return api.post('/api/evidence', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    // List recent evidence uploads
    list: (limit: number = 20) => api.get('/api/evidence', { params: { limit } }),

    // Get a specific evidence document
    get: (id: number) => api.get(`/api/evidence/${id}`),
};

// War Council API
export const warCouncilApi = {
    getAgents: () => api.get('/api/war-council/agents'),

    getDiscussions: () => api.get('/api/war-council/discussions'),

    startDiscussion: (topic: string, agents?: string[]) =>
        api.post('/api/war-council/discussions', { topic, agents }),

    getDiscussion: (id: string) => api.get(`/api/war-council/discussions/${id}`),

    // Run a debate/discussion with personas
    runDebate: (topic: string, vendorId?: number) =>
        api.post('/api/war-council/run', { topic, vendor_id: vendorId }),

    // Query the war council with optional vendor context
    query: (question: string, vendorIds?: number[]) =>
        api.post('/api/war-council/query', { question, vendor_ids: vendorIds }),
};

// Watchtower Dashboard API
export const watchtowerApi = {
    getMetrics: () => api.get('/api/watchtower/metrics'),

    // Summary endpoint for dashboard stats
    summary: () => api.get('/api/watchtower/summary'),

    getAlerts: (params?: {
        severity?: string;
        acknowledged?: string | boolean
    }) => api.get('/api/watchtower/alerts', { params }),

    // Alerts with object-based params
    alerts: (params?: { acknowledged?: string }) =>
        api.get('/api/watchtower/alerts', { params }),

    acknowledgeAlert: (id: number | string) =>
        api.post(`/api/watchtower/alerts/${id}/acknowledge`),

    // Recalculate risk scores
    recalculateRisk: () => api.post('/api/watchtower/recalculate-risk'),

    getActivityFeed: (limit?: number) =>
        api.get('/api/watchtower/activity', { params: { limit } }),

    // Evidence
    uploadEvidence: (file: File, options?: {
        vendorId?: number;
        vendorName?: string;
        sourceType?: string;
        notes?: string;
    }) => {
        const formData = new FormData();
        formData.append('file', file);
        if (options?.vendorId) formData.append('vendor_id', options.vendorId.toString());
        if (options?.vendorName) formData.append('vendor_name', options.vendorName);
        if (options?.sourceType) formData.append('source_type', options.sourceType);
        if (options?.notes) formData.append('notes', options.notes);
        return api.post('/api/watchtower/evidence', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
    },

    analyzeEvidence: (id: number) => api.post(`/api/watchtower/evidence/${id}/analyze`),
    listEvidence: (params?: { limit?: number; offset?: number }) =>
        api.get('/api/watchtower/evidence', { params }),

    // Vendors (Shortcut)
    createVendor: (data: { name: string, vendor_type?: string, country?: string }) =>
        api.post('/api/watchtower/vendors', data),

    listVendors: () => api.get('/api/watchtower/vendors'),

    // ============= LIVE FEED =============

    // Get feed items (FDA recalls, etc.)
    feed: (params?: { source?: string; limit?: number; offset?: number }) =>
        api.get('/api/watchtower/feed', { params }),

    // Get available sources with sync status
    sources: () => api.get('/api/watchtower/sources'),

    // Trigger sync (admin only)
    sync: (params?: { source?: string; force?: boolean }) =>
        api.post('/api/watchtower/sync', null, { params }),

    // Get feed summary with counts and status
    feedSummary: () => api.get('/api/watchtower/feed/summary'),

    // Get health status with overall_status and per-source details
    health: () => api.get('/api/watchtower/health'),
};

// Vendors API
export const vendorsApi = {
    getVendors: () => api.get('/api/vendors'),

    // Alias for getVendors
    list: () => api.get('/api/vendors'),

    getVendor: (id: string) => api.get(`/api/vendors/${id}`),

    createVendor: (data: object) => api.post('/api/vendors', data),

    // Alias for createVendor
    create: (data: object) => api.post('/api/vendors', data),

    updateVendor: (id: string, data: object) => api.put(`/api/vendors/${id}`, data),

    // Alias for updateVendor
    update: (id: number, data: object) => api.put(`/api/vendors/${id}`, data),

    // Delete vendor
    delete: (id: number) => api.delete(`/api/vendors/${id}`),

    getVendorScorecard: (id: string) => api.get(`/api/vendors/${id}/scorecard`),
};

// Sourcing / RFQ API
export const sourcingApi = {
    // List all RFQs
    listRfqs: () => api.get('/api/sourcing/rfqs'),

    // Create a new RFQ
    createRfq: (data: {
        title: string;
        item_type: string;
        item_description?: string;
        quantity: number;
        quantity_unit?: string;
        delivery_location?: string;
        target_date?: string;
        vendor_ids?: number[];
    }) => api.post('/api/sourcing/rfqs', data),

    // Get a specific RFQ
    getRfq: (id: number) => api.get(`/api/sourcing/rfqs/${id}`),

    // Generate draft messages for an RFQ
    generateDrafts: (rfqId: number) => api.post(`/api/sourcing/rfqs/${rfqId}/generate-drafts`),

    // Compare quotes for an RFQ
    compare: (rfqId: number) => api.get(`/api/sourcing/rfqs/${rfqId}/compare`),

    // Award an RFQ to a vendor
    award: (rfqId: number, vendorId: number) =>
        api.post(`/api/sourcing/rfqs/${rfqId}/award`, { vendor_id: vendorId }),

    // Submit a quote
    submitQuote: (rfqId: number, data: {
        vendor_id: number;
        unit_price: number;
        lead_time_days: number;
        notes?: string;
    }) => api.post(`/api/sourcing/rfqs/${rfqId}/quotes`, data),
};

// Audit Log API
export const auditApi = {
    getLogs: (params?: {
        action?: string;
        user_id?: string;
        start_date?: string;
        end_date?: string;
        limit?: number;
        offset?: number;
    }) => api.get('/api/audit/logs', { params }),

    // Alias for getLogs with filter object
    logs: (filters?: { action?: string; entity_type?: string; start_date?: string }) =>
        api.get('/api/audit/logs', { params: filters }),

    // Get audit summary stats
    summary: () => api.get('/api/audit/summary'),

    // Get list of available action types
    actions: () => api.get('/api/audit/actions'),

    exportLogs: (params?: object) => api.get('/api/audit/export', {
        params,
        responseType: 'blob'
    }),
};

// Health check
export const healthApi = {
    check: () => api.get('/api/health'),

    // Module health checks
    watchtower: () => api.get('/api/watchtower/health'),
    dscsa: () => api.get('/api/dscsa/health'),
    copilot: () => api.get('/api/copilot/health'),
    warCouncil: () => api.get('/api/war-council/health'),
    risk: () => api.get('/api/risk/health'),
};

// Admin API
export const adminApi = {
    // List all users
    listUsers: () => api.get('/api/admin/users'),

    // Get a specific user
    getUser: (id: number) => api.get(`/api/admin/users/${id}`),

    // Create a new user
    createUser: (data: {
        email: string;
        password: string;
        full_name: string;
        role: string;
    }) => api.post('/api/admin/users', data),

    // Update a user
    updateUser: (id: number, data: {
        full_name?: string;
        role?: string;
        is_active?: boolean;
    }) => api.put(`/api/admin/users/${id}`, data),

    // Delete a user
    deleteUser: (id: number) => api.delete(`/api/admin/users/${id}`),

    // Reset user password
    resetPassword: (id: number, newPassword: string) =>
        api.post(`/api/admin/users/${id}/reset-password`, { new_password: newPassword }),
};

// Risk Findings API - Golden Workflow
export const riskApi = {
    // Run the complete workflow end-to-end (NEW - persists to DB)
    runWorkflow: (evidenceId: number) =>
        api.post('/api/risk/workflow/run', null, { params: { evidence_id: evidenceId } }),

    // List workflow runs
    listWorkflowRuns: (evidenceId?: number, limit: number = 10) =>
        api.get('/api/risk/workflow/runs', { params: { evidence_id: evidenceId, limit } }),

    // Get a specific workflow run with details
    getWorkflowRun: (runId: number) =>
        api.get(`/api/risk/workflow/runs/${runId}`),

    // Run findings extraction on evidence (legacy - stores in cache)
    runFindings: (evidenceId: number) =>
        api.post('/api/risk/findings/run', null, { params: { evidence_id: evidenceId } }),

    // Get stored findings for evidence (from cache)
    getFindings: (evidenceId: number) =>
        api.get('/api/risk/findings', { params: { evidence_id: evidenceId } }),

    // Correlate evidence with Watchtower data (server-side fetch)
    correlate: (data: { evidence_id: number; findings?: object[] }) =>
        api.post('/api/risk/correlate', data),

    // Get stored correlation (from cache)
    getCorrelation: (evidenceId: number) =>
        api.get(`/api/risk/correlation/${evidenceId}`),

    // Generate action plan (legacy)
    generatePlan: (data: {
        evidence_id: number;
        findings: object[];
        watchtower_summary?: object;
        vendor_risks?: object[];
    }) => api.post('/api/risk/warcouncil/plan', data),

    // Export audit packet (now supports run_id parameter)
    exportPacket: (evidenceId: number, runId?: number) =>
        api.get(`/api/risk/export-packet/${evidenceId}`, {
            params: runId ? { run_id: runId } : undefined
        }),

    // Health check
    health: () => api.get('/api/risk/health'),
};


export default api;

