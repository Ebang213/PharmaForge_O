import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { evidenceApi, riskApi, vendorsApi } from '../lib/api';
import {
    Upload, Search, Radio, ClipboardList, ArrowRight, ArrowLeft,
    CheckCircle, AlertTriangle, Download, FileText, Shield,
    Loader2, ChevronRight
} from 'lucide-react';

interface EvidenceItem {
    id: number;
    filename: string;
    sha256: string;
    status: string;
    created_at: string;
}

interface RiskFinding {
    id: number;
    evidence_id: number;
    title: string;
    description: string;
    severity: string;
    cfr_refs: string[];
    citations: string[];
    entities: string[];
    created_at: string;
}

interface ActionItem {
    title: string;
    description: string;
    priority: string;
    owner: string;
    deadline: string;
}

interface ActionPlan {
    top_actions: ActionItem[];
    rationale: string;
    owners: string[];
    deadlines: string[];
    linked_evidence: number;
    audit_entries: object[];
}

interface Vendor {
    id: number;
    name: string;
    risk_level: string;
}

const STEPS = [
    { id: 1, title: 'Upload Evidence', icon: Upload },
    { id: 2, title: 'Identify Findings', icon: Search },
    { id: 3, title: 'Correlate Risks', icon: Radio },
    { id: 4, title: 'Action Plan', icon: ClipboardList },
];

export default function Workflow() {
    const [currentStep, setCurrentStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Step 1: Evidence
    const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
    const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null);
    const [uploading, setUploading] = useState(false);

    // Step 2: Findings
    const [findings, setFindings] = useState<RiskFinding[]>([]);
    const [extracting, setExtracting] = useState(false);

    // Step 3: Correlation
    const [watchtowerSummary, setWatchtowerSummary] = useState<object | null>(null);
    const [, setVendors] = useState<Vendor[]>([]);
    const [vendorRisks, setVendorRisks] = useState<{ id: number; name: string; risk_level: string }[]>([]);
    const [correlationResult, setCorrelationResult] = useState<{
        watchtower_snapshot: object;
        vendor_matches: { vendor_id: number | null; name: string; match_basis: string; risk_score: number | null; risk_level: string | null }[];
        narrative: string[];
        correlation_timestamp: string;
    } | null>(null);
    const [correlating, setCorrelating] = useState(false);

    // Step 4: Action Plan
    const [actionPlan, setActionPlan] = useState<ActionPlan | null>(null);
    const [generating, setGenerating] = useState(false);

    // Workflow Run tracking (NEW)
    const [workflowRunId, setWorkflowRunId] = useState<number | null>(null);
    const [workflowStatus, setWorkflowStatus] = useState<string | null>(null);

    // Load existing evidence on mount
    useEffect(() => {
        loadEvidence();
    }, []);

    async function loadEvidence() {
        try {
            const res = await evidenceApi.list(20);
            setEvidenceList(res.data || []);
        } catch (err) {
            console.error('Failed to load evidence:', err);
        }
    }

    async function handleFileUpload(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file) return;

        setUploading(true);
        setError(null);

        try {
            const res = await evidenceApi.upload(file);
            const newEvidence = res.data;
            setSelectedEvidence(newEvidence);
            await loadEvidence();
            setCurrentStep(2); // Auto-advance
        } catch (err: unknown) {
            const errorMessage = err instanceof Error ? err.message : 'Upload failed';
            setError(errorMessage);
        } finally {
            setUploading(false);
        }
    }

    async function runFindingsExtraction() {
        if (!selectedEvidence) return;

        setExtracting(true);
        setError(null);

        try {
            const res = await riskApi.runFindings(selectedEvidence.id);
            setFindings(res.data.findings || []);
        } catch (err: unknown) {
            const errorMessage = err instanceof Error ? err.message : 'Extraction failed';
            setError(errorMessage);
        } finally {
            setExtracting(false);
        }
    }

    async function loadCorrelationData() {
        if (!selectedEvidence) return;

        setLoading(true);
        setCorrelating(true);
        setError(null);
        try {
            // First, run the server-side correlation which fetches Watchtower data
            // This is the key step that generates REAL correlation output
            const correlationRes = await riskApi.correlate({
                evidence_id: selectedEvidence.id,
                findings: findings
            });
            setCorrelationResult(correlationRes.data);

            // Extract watchtower snapshot from correlation result for display
            setWatchtowerSummary(correlationRes.data.watchtower_snapshot || null);

            // Extract vendor risks from correlation matches
            const matchedVendors = (correlationRes.data.vendor_matches || [])
                .filter((vm: { vendor_id: number | null }) => vm.vendor_id !== null)
                .map((vm: { vendor_id: number; name: string; risk_level: string | null }) => ({
                    id: vm.vendor_id,
                    name: vm.name,
                    risk_level: vm.risk_level || 'unknown'
                }));
            setVendorRisks(matchedVendors);

            // Also load full vendor list for reference
            const vendorsRes = await vendorsApi.list();
            const allVendors = vendorsRes.data || [];
            setVendors(allVendors);

        } catch (err: any) {
            console.error('Failed to run correlation:', err);
            const statusCode = err.response?.status || 'NETWORK';
            const detail = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`Correlation failed (${statusCode}): ${detail}`);
        } finally {
            setLoading(false);
            setCorrelating(false);
        }
    }

    async function generateActionPlan() {
        if (!selectedEvidence) return;

        setGenerating(true);
        setError(null);

        try {
            const res = await riskApi.generatePlan({
                evidence_id: selectedEvidence.id,
                findings: findings,
                watchtower_summary: watchtowerSummary || undefined,
                vendor_risks: vendorRisks
            });
            setActionPlan(res.data);
        } catch (err: unknown) {
            const errorMessage = err instanceof Error ? err.message : 'Plan generation failed';
            setError(errorMessage);
        } finally {
            setGenerating(false);
        }
    }

    // Run the complete workflow end-to-end (NEW - persists to DB)
    async function runCompleteWorkflow() {
        if (!selectedEvidence) return;

        setLoading(true);
        setError(null);

        try {
            const res = await riskApi.runWorkflow(selectedEvidence.id);
            const data = res.data;

            // Update state with workflow run results
            setWorkflowRunId(data.workflow_run_id);
            setWorkflowStatus(data.status);

            // Load the full workflow run details
            const runDetails = await riskApi.getWorkflowRun(data.workflow_run_id);
            const runData = runDetails.data;

            // Populate findings from workflow run
            if (runData.findings && runData.findings.length > 0) {
                const mappedFindings: RiskFinding[] = runData.findings.map((f: {
                    id: number;
                    title: string;
                    description: string;
                    severity: string;
                    cfr_refs: string[];
                    citations: string[];
                    entities: string[];
                }) => ({
                    id: f.id,
                    evidence_id: selectedEvidence.id,
                    title: f.title,
                    description: f.description,
                    severity: f.severity,
                    cfr_refs: f.cfr_refs || [],
                    citations: f.citations || [],
                    entities: f.entities || [],
                    created_at: new Date().toISOString()
                }));
                setFindings(mappedFindings);
            }

            // Populate correlation from workflow run
            if (runData.action_plan?.correlation_data) {
                const corrData = runData.action_plan.correlation_data;
                setCorrelationResult({
                    watchtower_snapshot: corrData.watchtower_snapshot || {},
                    vendor_matches: corrData.vendor_matches || [],
                    narrative: corrData.narrative || [],
                    correlation_timestamp: corrData.correlation_timestamp || new Date().toISOString()
                });
                setWatchtowerSummary(corrData.watchtower_snapshot || null);

                // Extract vendor risks
                const matchedVendors = (corrData.vendor_matches || [])
                    .filter((vm: { vendor_id: number | null }) => vm.vendor_id !== null)
                    .map((vm: { vendor_id: number; name: string; risk_level: string | null }) => ({
                        id: vm.vendor_id,
                        name: vm.name,
                        risk_level: vm.risk_level || 'unknown'
                    }));
                setVendorRisks(matchedVendors);
            }

            // Populate action plan from workflow run
            if (runData.action_plan) {
                setActionPlan({
                    top_actions: runData.action_plan.actions || [],
                    rationale: runData.action_plan.rationale || '',
                    owners: runData.action_plan.owners || [],
                    deadlines: runData.action_plan.deadlines || [],
                    linked_evidence: selectedEvidence.id,
                    audit_entries: []
                });
            }

            // Move to step 4 since we completed everything
            setCurrentStep(4);

        } catch (err: any) {
            console.error('Workflow run failed:', err);
            const statusCode = err.response?.status || 'NETWORK';
            const detail = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`Workflow failed (${statusCode}): ${detail}`);
            setWorkflowStatus('failed');
        } finally {
            setLoading(false);
        }
    }

    async function exportAuditPacket() {
        if (!selectedEvidence) return;

        setError(null);
        try {
            // Request with workflow run ID if available (exports real DB data)
            const res = await riskApi.exportPacket(selectedEvidence.id, workflowRunId || undefined);

            // Extract filename from Content-Disposition header or use default
            const contentDisposition = res.headers?.['content-disposition'] || '';
            const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
            const filename = filenameMatch
                ? filenameMatch[1]
                : `audit_packet_run${workflowRunId || 'none'}_ev${selectedEvidence.id}.md`;

            // Create blob from response data (could be string or blob depending on responseType)
            const content = typeof res.data === 'string' ? res.data : await res.data.text?.() || res.data;
            const blob = new Blob([content], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
        } catch (err: any) {
            console.error('Export failed:', err);
            const statusCode = err.response?.status || 'NETWORK';
            const detail = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`Export failed (${statusCode}): ${detail}`);
        }
    }

    function goToStep(step: number) {
        if (step === 3 && currentStep < 3) {
            loadCorrelationData();
        }
        setCurrentStep(step);
    }

    function getSeverityColor(severity: string) {
        switch (severity?.toUpperCase()) {
            case 'HIGH': return '#ef4444';
            case 'MEDIUM': return '#f59e0b';
            case 'LOW': return '#10b981';
            default: return '#6b7280';
        }
    }

    function getPriorityColor(priority: string) {
        switch (priority?.toUpperCase()) {
            case 'HIGH': return '#ef4444';
            case 'MEDIUM': return '#f59e0b';
            case 'LOW': return '#10b981';
            default: return '#6b7280';
        }
    }

    return (
        <div className="page-container">
            <div className="page-header">
                <div>
                    <h1>Golden Workflow</h1>
                    <p className="text-muted">
                        End-to-end compliance workflow: Evidence → Findings → Correlation → Action Plan
                    </p>
                </div>
            </div>

            {/* Stepper */}
            <div className="workflow-stepper">
                {STEPS.map((step, idx) => {
                    const Icon = step.icon;
                    const isActive = currentStep === step.id;
                    const isComplete = currentStep > step.id;

                    return (
                        <div key={step.id} className="stepper-item-wrapper">
                            <button
                                className={`stepper-item ${isActive ? 'active' : ''} ${isComplete ? 'complete' : ''}`}
                                onClick={() => goToStep(step.id)}
                                disabled={step.id > currentStep + 1}
                            >
                                <div className="stepper-icon">
                                    {isComplete ? <CheckCircle size={24} /> : <Icon size={24} />}
                                </div>
                                <span className="stepper-label">{step.title}</span>
                            </button>
                            {idx < STEPS.length - 1 && (
                                <ChevronRight className="stepper-arrow" size={20} />
                            )}
                        </div>
                    );
                })}
            </div>

            {error && (
                <div className="error-banner">
                    <AlertTriangle size={18} />
                    <span>{error}</span>
                </div>
            )}

            {/* Step Content */}
            <div className="workflow-content">
                {/* Step 1: Upload Evidence */}
                {currentStep === 1 && (
                    <div className="step-panel">
                        <h2><Upload size={24} /> Upload Evidence</h2>
                        <p className="text-muted">
                            Upload a PDF or TXT document for compliance analysis.
                        </p>

                        <div className="upload-zone">
                            <input
                                type="file"
                                accept=".pdf,.txt"
                                onChange={handleFileUpload}
                                disabled={uploading}
                                id="evidence-upload"
                                style={{ display: 'none' }}
                            />
                            <label htmlFor="evidence-upload" className="upload-label">
                                {uploading ? (
                                    <><Loader2 className="spin" size={24} /> Uploading...</>
                                ) : (
                                    <><Upload size={24} /> Click to upload or drag and drop</>
                                )}
                            </label>
                        </div>

                        {evidenceList.length > 0 && (
                            <div className="existing-evidence">
                                <h3>Or select existing evidence:</h3>
                                <div className="evidence-list">
                                    {evidenceList.slice(0, 5).map((ev) => (
                                        <button
                                            key={ev.id}
                                            className={`evidence-item ${selectedEvidence?.id === ev.id ? 'selected' : ''} ${ev.status !== 'processed' ? 'not-ready' : ''}`}
                                            onClick={() => {
                                                if (ev.status !== 'processed') {
                                                    setError(`Evidence "${ev.filename}" is ${ev.status}. Only processed evidence can be analyzed.`);
                                                    return;
                                                }
                                                setSelectedEvidence(ev);
                                                setCurrentStep(2);
                                            }}
                                        >
                                            <FileText size={18} />
                                            <span>{ev.filename}</span>
                                            <span className={`evidence-status ${ev.status}`}>
                                                {ev.status === 'processed' ? '✓' : ev.status === 'failed' ? '✗' : '⏳'}
                                            </span>
                                            <span className="evidence-date">
                                                {new Date(ev.created_at).toLocaleDateString()}
                                            </span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Step 2: Identify Findings */}
                {currentStep === 2 && (
                    <div className="step-panel">
                        <h2><Search size={24} /> Identify Compliance Findings</h2>
                        <p className="text-muted">
                            Selected: <strong>{selectedEvidence?.filename}</strong>
                        </p>

                        {findings.length === 0 && (
                            <div className="workflow-actions">
                                <button
                                    className="btn btn-primary"
                                    onClick={runFindingsExtraction}
                                    disabled={extracting || loading}
                                >
                                    {extracting ? (
                                        <><Loader2 className="spin" size={18} /> Extracting...</>
                                    ) : (
                                        <><Search size={18} /> Run Findings Extraction</>
                                    )}
                                </button>
                                <span className="or-divider">or</span>
                                <button
                                    className="btn btn-success"
                                    onClick={runCompleteWorkflow}
                                    disabled={loading || extracting}
                                    style={{ backgroundColor: '#10b981', borderColor: '#10b981' }}
                                >
                                    {loading ? (
                                        <><Loader2 className="spin" size={18} /> Running Workflow...</>
                                    ) : (
                                        <><CheckCircle size={18} /> Run Complete Workflow (End-to-End)</>
                                    )}
                                </button>
                            </div>
                        )}

                        {workflowStatus && (
                            <div className={`workflow-status ${workflowStatus === 'success' ? 'status-success' : workflowStatus === 'failed' ? 'status-failed' : ''}`}>
                                <Shield size={18} />
                                <span>Workflow Run ID: <strong>{workflowRunId || 'N/A'}</strong></span>
                                <span className="status-badge">Status: {workflowStatus}</span>
                            </div>
                        )}

                        {findings.length > 0 && (
                            <div className="findings-list">
                                <h3>{findings.length} Finding(s) Identified {workflowRunId && <span className="run-badge">(Run #{workflowRunId})</span>}</h3>
                                {findings.map((f) => (
                                    <div key={f.id} className="finding-card">
                                        <div className="finding-header">
                                            <span
                                                className="severity-badge"
                                                style={{ backgroundColor: getSeverityColor(f.severity) }}
                                            >
                                                {f.severity}
                                            </span>
                                            <h4>{f.title}</h4>
                                        </div>
                                        <p>{f.description}</p>
                                        {f.cfr_refs.length > 0 && (
                                            <div className="cfr-refs">
                                                <strong>CFR References:</strong> {f.cfr_refs.join(', ')}
                                            </div>
                                        )}
                                        {f.citations.length > 0 && (
                                            <div className="citations">
                                                <strong>Citations:</strong> {f.citations.join('; ')}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="step-nav">
                            <button className="btn btn-secondary" onClick={() => setCurrentStep(1)}>
                                <ArrowLeft size={18} /> Back
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={() => goToStep(3)}
                                disabled={findings.length === 0}
                            >
                                Continue <ArrowRight size={18} />
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 3: Correlate Risks */}
                {currentStep === 3 && (
                    <div className="step-panel">
                        <h2><Radio size={24} /> Correlate Supply Chain Risks</h2>
                        <p className="text-muted">
                            Analyzing evidence against Watchtower signals and vendor registry...
                        </p>

                        {(loading || correlating) ? (
                            <div className="loading-state">
                                <Loader2 className="spin" size={32} />
                                <p>{correlating ? 'Running correlation analysis...' : 'Loading data...'}</p>
                            </div>
                        ) : (
                            <>
                                {/* Correlation Narrative - the key output */}
                                {correlationResult && correlationResult.narrative && correlationResult.narrative.length > 0 && (
                                    <div className="correlation-narrative">
                                        <h3><Radio size={20} /> Risk Intelligence Summary</h3>
                                        <ul className="narrative-list">
                                            {correlationResult.narrative.map((point, i) => (
                                                <li key={i}>{point}</li>
                                            ))}
                                        </ul>
                                        <p className="correlation-timestamp">
                                            Correlated at: {correlationResult.correlation_timestamp}
                                        </p>
                                    </div>
                                )}

                                <div className="correlation-grid">
                                    <div className="correlation-card">
                                        <h3><Shield size={20} /> Watchtower Snapshot</h3>
                                        {watchtowerSummary ? (
                                            <div className="snapshot-stats">
                                                <div className="stat-row">
                                                    <span>Feed Items:</span>
                                                    <strong>{(watchtowerSummary as { total_feed_items?: number }).total_feed_items || 0}</strong>
                                                </div>
                                                <div className="stat-row">
                                                    <span>Active Alerts:</span>
                                                    <strong>{(watchtowerSummary as { active_alerts?: number }).active_alerts || 0}</strong>
                                                </div>
                                            </div>
                                        ) : (
                                            <p className="text-muted">No Watchtower data available</p>
                                        )}
                                        <Link to="/watchtower" className="card-link">
                                            View Risk Radar <ArrowRight size={14} />
                                        </Link>
                                    </div>

                                    <div className="correlation-card">
                                        <h3><AlertTriangle size={20} /> Vendor Matches</h3>
                                        {vendorRisks.length > 0 ? (
                                            <ul className="vendor-risk-list">
                                                {vendorRisks.map((v, i) => (
                                                    <li key={i}>
                                                        <span className="vendor-name">{String(v.name)}</span>
                                                        <span
                                                            className="risk-badge"
                                                            style={{ backgroundColor: getSeverityColor(String(v.risk_level)) }}
                                                        >
                                                            {String(v.risk_level)}
                                                        </span>
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p className="text-muted">No vendor matches found in evidence</p>
                                        )}
                                        <Link to="/vendors" className="card-link">
                                            View All Vendors <ArrowRight size={14} />
                                        </Link>
                                    </div>

                                    <div className="correlation-card">
                                        <h3><FileText size={20} /> Findings Summary</h3>
                                        <p>
                                            <strong>{findings.length}</strong> finding(s) from evidence
                                        </p>
                                        <ul>
                                            <li>HIGH: {findings.filter(f => f.severity === 'HIGH').length}</li>
                                            <li>MEDIUM: {findings.filter(f => f.severity === 'MEDIUM').length}</li>
                                            <li>LOW: {findings.filter(f => f.severity === 'LOW').length}</li>
                                        </ul>
                                    </div>
                                </div>
                            </>
                        )}

                        <div className="step-nav">
                            <button className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
                                <ArrowLeft size={18} /> Back
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={() => setCurrentStep(4)}
                                disabled={!correlationResult}
                            >
                                Continue <ArrowRight size={18} />
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 4: Action Plan */}
                {currentStep === 4 && (
                    <div className="step-panel">
                        <h2><ClipboardList size={24} /> Generate Action Plan</h2>

                        {!actionPlan && (
                            <button
                                className="btn btn-primary"
                                onClick={generateActionPlan}
                                disabled={generating}
                            >
                                {generating ? (
                                    <><Loader2 className="spin" size={18} /> Generating...</>
                                ) : (
                                    <><ClipboardList size={18} /> Generate Action Plan</>
                                )}
                            </button>
                        )}

                        {actionPlan && (
                            <div className="action-plan">
                                <div className="plan-rationale">
                                    <h3>Rationale</h3>
                                    <p>{actionPlan.rationale}</p>
                                </div>

                                <div className="actions-list">
                                    <h3>Recommended Actions ({actionPlan.top_actions.length})</h3>
                                    {actionPlan.top_actions.map((action, i) => (
                                        <div key={i} className="action-item">
                                            <div className="action-header">
                                                <span
                                                    className="priority-badge"
                                                    style={{ backgroundColor: getPriorityColor(action.priority) }}
                                                >
                                                    {action.priority}
                                                </span>
                                                <h4>{action.title}</h4>
                                            </div>
                                            <p>{action.description}</p>
                                            <div className="action-meta">
                                                <span><strong>Owner:</strong> {action.owner}</span>
                                                <span><strong>Deadline:</strong> {action.deadline}</span>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="export-section">
                                    <button className="btn btn-secondary" onClick={exportAuditPacket}>
                                        <Download size={18} /> Export Audit Packet (Markdown)
                                    </button>
                                    <Link to="/war-council" className="btn btn-outline">
                                        Open Decision Council <ArrowRight size={18} />
                                    </Link>
                                </div>
                            </div>
                        )}

                        <div className="step-nav">
                            <button className="btn btn-secondary" onClick={() => setCurrentStep(3)}>
                                <ArrowLeft size={18} /> Back
                            </button>
                            <Link to="/mission-control" className="btn btn-primary">
                                Return to Mission Control <ArrowRight size={18} />
                            </Link>
                        </div>
                    </div>
                )}
            </div>

            <style>{`
                .workflow-stepper {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 8px;
                    margin: 32px 0;
                    padding: 24px;
                    background: var(--glass-bg, rgba(255,255,255,0.05));
                    border-radius: 16px;
                    border: 1px solid var(--border-color, rgba(255,255,255,0.1));
                }

                .stepper-item-wrapper {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .stepper-item {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 8px;
                    padding: 16px 24px;
                    background: transparent;
                    border: 2px solid var(--border-color, rgba(255,255,255,0.2));
                    border-radius: 12px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    color: var(--text-muted, #9ca3af);
                }

                .stepper-item:hover:not(:disabled) {
                    border-color: var(--primary, #6366f1);
                    color: var(--text-primary, #f9fafb);
                }

                .stepper-item.active {
                    background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2));
                    border-color: var(--primary, #6366f1);
                    color: var(--primary, #6366f1);
                }

                .stepper-item.complete {
                    background: rgba(16, 185, 129, 0.1);
                    border-color: #10b981;
                    color: #10b981;
                }

                .stepper-item:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }

                .stepper-icon {
                    width: 48px;
                    height: 48px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .stepper-label {
                    font-size: 14px;
                    font-weight: 500;
                }

                .stepper-arrow {
                    color: var(--text-muted, #9ca3af);
                }

                .workflow-content {
                    margin-top: 24px;
                }

                .step-panel {
                    background: var(--glass-bg, rgba(255,255,255,0.05));
                    border: 1px solid var(--border-color, rgba(255,255,255,0.1));
                    border-radius: 16px;
                    padding: 32px;
                }

                .step-panel h2 {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin: 0 0 16px 0;
                    font-size: 24px;
                }

                .upload-zone {
                    margin: 24px 0;
                }

                .upload-label {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 12px;
                    padding: 48px;
                    border: 2px dashed var(--border-color, rgba(255,255,255,0.3));
                    border-radius: 12px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    color: var(--text-muted);
                    font-size: 16px;
                }

                .upload-label:hover {
                    border-color: var(--primary, #6366f1);
                    background: rgba(99,102,241,0.1);
                }

                .existing-evidence {
                    margin-top: 32px;
                    padding-top: 24px;
                    border-top: 1px solid var(--border-color);
                }

                .existing-evidence h3 {
                    margin: 0 0 16px 0;
                    font-size: 16px;
                    color: var(--text-muted);
                }

                .evidence-list {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }

                .evidence-item {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 12px 16px;
                    background: rgba(255,255,255,0.05);
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    text-align: left;
                    color: var(--text-primary);
                }

                .evidence-item:hover {
                    background: rgba(99,102,241,0.1);
                    border-color: var(--primary);
                }

                .evidence-item.selected {
                    background: rgba(99,102,241,0.2);
                    border-color: var(--primary);
                }

                .evidence-status {
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                }

                .evidence-status.processed {
                    color: #10b981;
                }

                .evidence-status.pending,
                .evidence-status.processing {
                    color: #f59e0b;
                }

                .evidence-status.failed {
                    color: #ef4444;
                }

                .evidence-item.not-ready {
                    opacity: 0.6;
                    border-style: dashed;
                }

                .evidence-date {
                    margin-left: auto;
                    font-size: 12px;
                    color: var(--text-muted);
                }

                .findings-list {
                    margin-top: 24px;
                }

                .findings-list h3 {
                    margin: 0 0 16px 0;
                    font-size: 18px;
                }

                .finding-card {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid var(--border-color);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 16px;
                }

                .finding-header {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-bottom: 12px;
                }

                .finding-header h4 {
                    margin: 0;
                    font-size: 16px;
                }

                .severity-badge, .priority-badge, .risk-badge {
                    padding: 4px 10px;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: 600;
                    text-transform: uppercase;
                    color: white;
                }

                .cfr-refs, .citations {
                    margin-top: 8px;
                    font-size: 13px;
                    color: var(--text-muted);
                }

                .step-nav {
                    display: flex;
                    justify-content: space-between;
                    margin-top: 32px;
                    padding-top: 24px;
                    border-top: 1px solid var(--border-color);
                }

                .btn {
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    text-decoration: none;
                }

                .btn-primary {
                    background: linear-gradient(135deg, var(--primary, #6366f1), #8b5cf6);
                    color: white;
                    border: none;
                }

                .btn-primary:hover:not(:disabled) {
                    transform: translateY(-2px);
                    box-shadow: 0 4px 20px rgba(99,102,241,0.4);
                }

                .btn-primary:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }

                .btn-secondary {
                    background: rgba(255,255,255,0.1);
                    color: var(--text-primary);
                    border: 1px solid var(--border-color);
                }

                .btn-outline {
                    background: transparent;
                    color: var(--primary);
                    border: 1px solid var(--primary);
                }

                .error-banner {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 16px;
                    background: rgba(239, 68, 68, 0.1);
                    border: 1px solid rgba(239, 68, 68, 0.3);
                    border-radius: 8px;
                    color: #ef4444;
                    margin-bottom: 24px;
                }

                .loading-state {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 16px;
                    padding: 48px;
                    color: var(--text-muted);
                }

                .correlation-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 24px;
                    margin: 24px 0;
                }

                .correlation-card {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid var(--border-color);
                    border-radius: 12px;
                    padding: 20px;
                }

                .correlation-card h3 {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin: 0 0 16px 0;
                    font-size: 16px;
                }

                .summary-data {
                    background: rgba(0,0,0,0.2);
                    padding: 12px;
                    border-radius: 8px;
                    font-size: 11px;
                    overflow-x: auto;
                    max-height: 150px;
                }

                .card-link {
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                    margin-top: 12px;
                    color: var(--primary);
                    font-size: 13px;
                    text-decoration: none;
                }

                .vendor-risk-list {
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }

                .vendor-risk-list li {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 8px 0;
                    border-bottom: 1px solid var(--border-color);
                }

                .vendor-risk-list li:last-child {
                    border-bottom: none;
                }

                .correlation-narrative {
                    background: linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.1));
                    border: 1px solid rgba(99,102,241,0.3);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 24px;
                }

                .correlation-narrative h3 {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    margin: 0 0 16px 0;
                    font-size: 18px;
                    color: var(--primary);
                }

                .narrative-list {
                    list-style: none;
                    padding: 0;
                    margin: 0 0 12px 0;
                }

                .narrative-list li {
                    padding: 8px 0;
                    border-bottom: 1px solid rgba(99,102,241,0.2);
                    font-size: 14px;
                }

                .narrative-list li:last-child {
                    border-bottom: none;
                }

                .correlation-timestamp {
                    font-size: 12px;
                    color: var(--text-muted);
                    margin: 0;
                }

                .snapshot-stats {
                    display: flex;
                    flex-direction: column;
                    gap: 8px;
                }

                .stat-row {
                    display: flex;
                    justify-content: space-between;
                    padding: 8px 0;
                    border-bottom: 1px solid var(--border-color);
                }

                .stat-row:last-child {
                    border-bottom: none;
                }

                .action-plan {
                    margin-top: 24px;
                }

                .plan-rationale {
                    background: rgba(99,102,241,0.1);
                    border: 1px solid rgba(99,102,241,0.3);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 24px;
                }

                .plan-rationale h3 {
                    margin: 0 0 12px 0;
                    font-size: 16px;
                    color: var(--primary);
                }

                .actions-list h3 {
                    margin: 0 0 16px 0;
                    font-size: 18px;
                }

                .action-item {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid var(--border-color);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 16px;
                }

                .action-header {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    margin-bottom: 12px;
                }

                .action-header h4 {
                    margin: 0;
                    font-size: 16px;
                }

                .action-meta {
                    display: flex;
                    gap: 24px;
                    margin-top: 12px;
                    font-size: 13px;
                    color: var(--text-muted);
                }

                .export-section {
                    display: flex;
                    gap: 16px;
                    margin-top: 32px;
                    padding-top: 24px;
                    border-top: 1px solid var(--border-color);
                }

                .workflow-actions {
                    display: flex;
                    align-items: center;
                    gap: 16px;
                    flex-wrap: wrap;
                    margin: 16px 0;
                }

                .or-divider {
                    color: var(--text-muted);
                    font-size: 14px;
                    font-style: italic;
                }

                .workflow-status {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 12px 16px;
                    margin: 16px 0;
                    border-radius: 8px;
                    background: rgba(99, 102, 241, 0.1);
                    border: 1px solid rgba(99, 102, 241, 0.3);
                }

                .workflow-status.status-success {
                    background: rgba(16, 185, 129, 0.1);
                    border-color: rgba(16, 185, 129, 0.3);
                }

                .workflow-status.status-failed {
                    background: rgba(239, 68, 68, 0.1);
                    border-color: rgba(239, 68, 68, 0.3);
                }

                .status-badge {
                    padding: 4px 10px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                    background: rgba(255, 255, 255, 0.1);
                }

                .run-badge {
                    font-size: 14px;
                    font-weight: normal;
                    color: var(--primary, #6366f1);
                }

                .spin {
                    animation: spin 1s linear infinite;
                }

                @keyframes spin {
                    from { transform: rotate(0deg); }
                    to { transform: rotate(360deg); }
                }

                @media (max-width: 768px) {
                    .workflow-stepper {
                        flex-wrap: wrap;
                    }

                    .stepper-arrow {
                        display: none;
                    }

                    .stepper-item {
                        padding: 12px 16px;
                    }
                }
            `}</style>
        </div>
    );
}
