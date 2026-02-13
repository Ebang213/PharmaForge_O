import { useState, useEffect } from 'react';
import { copilotApi, evidenceApi } from '../lib/api';
import { MessageSquare, Upload, Send, FileText, BookOpen, Copy, Mail, CheckCircle, AlertCircle } from 'lucide-react';
import type { CopilotResponse } from '../lib/types';

interface EvidenceItem {
    id: number;
    filename: string;
    sha256: string;
    content_type: string | null;
    status: string;
    created_at: string;
    uploaded_by: number;
}

export default function Copilot() {
    const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
    const [question, setQuestion] = useState('');
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
    const [response, setResponse] = useState<CopilotResponse | null>(null);
    const [sessionId, setSessionId] = useState<number | undefined>();
    const [loadError, setLoadError] = useState<string | null>(null);
    const [queryError, setQueryError] = useState<string | null>(null);

    useEffect(() => {
        loadEvidence();
    }, []);

    const loadEvidence = async () => {
        setLoadError(null);
        try {
            const res = await evidenceApi.list(20);
            setEvidenceList(res.data);
        } catch (error: any) {
            console.error('Failed to load evidence:', error);
            const statusCode = error.response?.status || 'NETWORK';
            const detail = error.response?.data?.detail || error.message || 'Unknown error';
            setLoadError(`Failed to load evidence (${statusCode}): ${detail}`);
        }
    };

    const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Clear previous messages
        setUploadError(null);
        setUploadSuccess(null);
        setUploading(true);

        try {
            const res = await evidenceApi.upload(file);
            setUploadSuccess(`Uploaded: ${res.data.filename}`);
            await loadEvidence();
        } catch (error: any) {
            console.error('Upload failed:', error);
            setUploadError(error.response?.data?.detail || 'Upload failed. Please try again.');
        } finally {
            setUploading(false);
            // Clear the file input
            event.target.value = '';
        }
    };

    const handleAsk = async () => {
        if (!question.trim()) return;

        setLoading(true);
        setQueryError(null);
        try {
            const res = await copilotApi.query(question, sessionId);
            setResponse(res.data);
            setSessionId(res.data.session_id);
            setQuestion('');
        } catch (error: any) {
            console.error('Query failed:', error);
            const statusCode = error.response?.status || 'NETWORK';
            const detail = error.response?.data?.detail || error.message || 'Unknown error';
            setQueryError(`Query failed (${statusCode}): ${detail}`);
        } finally {
            setLoading(false);
        }
    };

    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text);
    };

    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Regulatory Copilot</h1>
                <p>Ask the FDA - AI-powered regulatory guidance with document citations</p>
            </div>

            {/* Error Banners - Real errors only, no fake success */}
            {loadError && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
                    padding: 12, background: 'rgba(239, 68, 68, 0.1)', borderRadius: 8, border: '1px solid var(--danger)'
                }}>
                    <AlertCircle size={18} style={{ color: 'var(--danger)' }} />
                    <span style={{ color: 'var(--danger)' }}>{loadError}</span>
                </div>
            )}
            {queryError && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
                    padding: 12, background: 'rgba(239, 68, 68, 0.1)', borderRadius: 8, border: '1px solid var(--danger)'
                }}>
                    <AlertCircle size={18} style={{ color: 'var(--danger)' }} />
                    <span style={{ color: 'var(--danger)' }}>{queryError}</span>
                </div>
            )}

            <div className="grid" style={{ gridTemplateColumns: '1fr 320px', gap: 24 }}>
                {/* Main Chat Area */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                    {/* Response Area */}
                    <div className="card" style={{ flex: 1, minHeight: 400 }}>
                        {!response ? (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
                                <div style={{
                                    width: 80, height: 80, background: 'var(--accent-gradient)', borderRadius: 20,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 24
                                }}>
                                    <MessageSquare size={36} color="white" />
                                </div>
                                <h3 style={{ marginBottom: 8, color: 'var(--text-secondary)' }}>Ask the FDA</h3>
                                <p style={{ maxWidth: 400, textAlign: 'center' }}>
                                    Ask questions about FDA guidance, CFR requirements, or regulatory compliance.
                                    Responses include citations from uploaded documents.
                                </p>
                            </div>
                        ) : (
                            <div>
                                <div style={{ marginBottom: 24 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                                        <h3 style={{ fontSize: 16, fontWeight: 600 }}>Response</h3>
                                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{response.latency_ms}ms</span>
                                    </div>
                                    <div style={{ background: 'var(--bg-tertiary)', padding: 20, borderRadius: 12, lineHeight: 1.8 }}>
                                        {response.answer}
                                    </div>
                                </div>

                                {response.citations.length > 0 && (
                                    <div style={{ marginBottom: 24 }}>
                                        <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: 'var(--text-secondary)' }}>
                                            <BookOpen size={16} style={{ marginRight: 8 }} />
                                            Citations ({response.citations.length})
                                        </h4>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                            {response.citations.map((citation, idx) => (
                                                <div key={idx} style={{
                                                    padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8,
                                                    borderLeft: '3px solid var(--accent-primary)'
                                                }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                                                        <span style={{ fontWeight: 500, fontSize: 13 }}>{citation.doc_name}</span>
                                                        <span className="badge badge-info">{Math.round(citation.confidence * 100)}%</span>
                                                    </div>
                                                    <p style={{ fontSize: 13, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                                                        "{citation.content_preview}..."
                                                    </p>
                                                    {citation.page && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Page {citation.page}</span>}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {response.draft_email && (
                                    <div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                                            <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' }}>
                                                <Mail size={16} style={{ marginRight: 8 }} />
                                                Draft Email
                                            </h4>
                                            <button className="btn btn-secondary" style={{ padding: '6px 12px' }} onClick={() => copyToClipboard(response.draft_email!)}>
                                                <Copy size={14} /> Copy
                                            </button>
                                        </div>
                                        <pre style={{
                                            background: 'var(--bg-tertiary)', padding: 16, borderRadius: 8,
                                            whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6
                                        }}>
                                            {response.draft_email}
                                        </pre>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Question Input */}
                    <div className="card" style={{ padding: 16 }}>
                        <div style={{ display: 'flex', gap: 12 }}>
                            <input
                                type="text"
                                placeholder="Ask about FDA guidance, DSCSA requirements, GMP compliance..."
                                value={question}
                                onChange={(e) => setQuestion(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
                                style={{ flex: 1 }}
                                disabled={loading}
                            />
                            <button className="btn btn-primary" onClick={handleAsk} disabled={loading || !question.trim()}>
                                {loading ? 'Thinking...' : <><Send size={18} /> Ask</>}
                            </button>
                        </div>
                    </div>
                </div>

                {/* Knowledge Base Panel */}
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h3 style={{ fontSize: 16, fontWeight: 600 }}>Knowledge Base</h3>
                        <label className="btn btn-secondary" style={{ padding: '6px 12px', cursor: uploading ? 'wait' : 'pointer' }}>
                            {uploading ? 'Uploading...' : <Upload size={14} />}
                            <input
                                type="file"
                                accept=".pdf,.txt"
                                onChange={handleUpload}
                                style={{ display: 'none' }}
                                disabled={uploading}
                            />
                        </label>
                    </div>

                    {/* Upload Status Messages */}
                    {uploadSuccess && (
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                            padding: 10, background: 'rgba(34, 197, 94, 0.1)', borderRadius: 8, fontSize: 13
                        }}>
                            <CheckCircle size={16} style={{ color: 'var(--success)' }} />
                            <span style={{ color: 'var(--success)' }}>{uploadSuccess}</span>
                        </div>
                    )}
                    {uploadError && (
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
                            padding: 10, background: 'rgba(239, 68, 68, 0.1)', borderRadius: 8, fontSize: 13
                        }}>
                            <AlertCircle size={16} style={{ color: 'var(--danger)' }} />
                            <span style={{ color: 'var(--danger)' }}>{uploadError}</span>
                        </div>
                    )}

                    {evidenceList.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                            <FileText size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
                            <p style={{ fontSize: 13 }}>Upload PDF or TXT documents to enhance responses</p>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {evidenceList.map(doc => (
                                <div key={doc.id} style={{
                                    padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8,
                                    display: 'flex', alignItems: 'center', gap: 12
                                }}>
                                    <FileText size={20} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontWeight: 500, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            {doc.filename}
                                        </div>
                                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                            {formatDate(doc.created_at)}
                                        </div>
                                    </div>
                                    {doc.status === 'processed' ? (
                                        <span className="badge badge-success" style={{ fontSize: 10 }}>Ready</span>
                                    ) : (
                                        <span className="badge badge-warning" style={{ fontSize: 10 }}>Processing</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
