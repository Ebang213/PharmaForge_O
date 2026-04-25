import { useState, useEffect, useRef } from 'react';
import { dscsaApi } from '../lib/api';
import { FileCheck, Upload, Download, AlertCircle, CheckCircle, XCircle, Link2 } from 'lucide-react';
import type { EPCISUpload } from '../lib/types';

export default function Transactions() {
    const [uploads, setUploads] = useState<EPCISUpload[]>([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [selectedUpload, setSelectedUpload] = useState<EPCISUpload | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [detailError, setDetailError] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        loadUploads();
    }, []);

    const loadUploads = async () => {
        setError(null);
        try {
            const response = await dscsaApi.epcisList();
            setUploads(response.data);
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                || 'Failed to load transaction history. Please refresh.';
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Reset input so same file can be re-selected after upload
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }

        setUploading(true);
        setError(null);
        try {
            const response = await dscsaApi.epcisUpload(file);
            setSelectedUpload(response.data);
            setDetailError(null);
            await loadUploads();
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                || 'Upload failed. Check the file format and try again.';
            setError(msg);
        } finally {
            setUploading(false);
        }
    };

    const handleViewDetails = async (id: number) => {
        setDetailError(null);
        try {
            const response = await dscsaApi.epcisDetail(id);
            setSelectedUpload(response.data);
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                || 'Failed to load upload details.';
            setDetailError(msg);
        }
    };

    const handleDownloadAuditPacket = async (id: number) => {
        setError(null);
        try {
            const response = await dscsaApi.downloadAuditPacket(id);
            const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `dscsa_inspection_packet_${id}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                || 'Failed to generate inspection packet.';
            setError(msg);
        }
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'valid': return <CheckCircle size={18} style={{ color: 'var(--success)' }} />;
            case 'invalid': return <XCircle size={18} style={{ color: 'var(--danger)' }} />;
            case 'chain_break': return <Link2 size={18} style={{ color: 'var(--warning)' }} />;
            default: return <AlertCircle size={18} style={{ color: 'var(--text-muted)' }} />;
        }
    };

    const getStatusBadge = (status: string) => {
        const classes: Record<string, string> = {
            valid: 'badge badge-success',
            invalid: 'badge badge-danger',
            chain_break: 'badge badge-warning',
            pending: 'badge badge-info',
        };
        return (
            <span className={classes[status] || 'badge'}>
                {status.replace('_', ' ').toUpperCase()}
            </span>
        );
    };

    const formatBytes = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    if (loading) {
        return <div className="loading-container"><div className="spinner" /></div>;
    }

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Transactions</h1>
                <p>Upload, validate, and store EPCIS transaction files from your wholesalers.</p>
            </div>

            {/* Global error banner */}
            {error && (
                <div className="alert alert-danger" style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <AlertCircle size={16} />
                    <span>{error}</span>
                    <button
                        style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
                        onClick={() => setError(null)}
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* Upload Section */}
            <div className="card" style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <div style={{
                        width: 64, height: 64, background: 'var(--bg-tertiary)', borderRadius: 12,
                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                        <FileCheck size={28} style={{ color: 'var(--accent-primary)' }} />
                    </div>
                    <div style={{ flex: 1 }}>
                        <h3 style={{ marginBottom: 4 }}>Upload EPCIS File</h3>
                        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                            Upload JSON or XML files for validation and chain-of-custody verification
                        </p>
                    </div>
                    <label className="btn btn-primary" style={{ cursor: uploading ? 'not-allowed' : 'pointer', opacity: uploading ? 0.7 : 1 }}>
                        <Upload size={18} />
                        {uploading ? 'Uploading...' : 'Upload File'}
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".json,.xml"
                            onChange={handleFileUpload}
                            style={{ display: 'none' }}
                            disabled={uploading}
                        />
                    </label>
                </div>
            </div>

            <div className="grid grid-2" style={{ gap: 24 }}>
                {/* Uploads List */}
                <div className="card">
                    <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Recent Uploads</h2>

                    {uploads.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <FileCheck size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                            <p>No uploads yet. Upload an EPCIS file to get started.</p>
                        </div>
                    ) : (
                        <div>
                            {uploads.map(upload => (
                                <div
                                    key={upload.id}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: 16, padding: 16,
                                        borderBottom: '1px solid var(--border-color)', cursor: 'pointer',
                                        background: selectedUpload?.id === upload.id ? 'var(--bg-tertiary)' : undefined,
                                    }}
                                    onClick={() => handleViewDetails(upload.id)}
                                >
                                    {getStatusIcon(upload.validation_status)}
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 500, marginBottom: 4 }}>{upload.filename}</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                            {upload.event_count} events
                                            {upload.file_size ? ` • ${formatBytes(upload.file_size)}` : ''}
                                            {' • '}{new Date(upload.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                    {getStatusBadge(upload.validation_status)}
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Details Panel */}
                <div className="card">
                    <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Validation Details</h2>

                    {detailError && (
                        <div className="alert alert-danger" style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <AlertCircle size={16} />
                            <span>{detailError}</span>
                        </div>
                    )}

                    {!selectedUpload && !detailError ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <AlertCircle size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                            <p>Select an upload to view details</p>
                        </div>
                    ) : selectedUpload ? (
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
                                <div>
                                    <h3 style={{ marginBottom: 4 }}>{selectedUpload.filename}</h3>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                        {getStatusBadge(selectedUpload.validation_status)}
                                        {selectedUpload.file_size ? (
                                            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                                {formatBytes(selectedUpload.file_size)}
                                            </span>
                                        ) : null}
                                    </div>
                                    {selectedUpload.validated_at && (
                                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                                            Validated: {new Date(selectedUpload.validated_at).toLocaleString()}
                                        </div>
                                    )}
                                </div>
                                <button
                                    className="btn btn-secondary"
                                    onClick={() => handleDownloadAuditPacket(selectedUpload.id)}
                                    style={{ whiteSpace: 'nowrap', flexShrink: 0 }}
                                >
                                    <Download size={16} /> Download DSCSA Inspection Packet
                                </button>
                            </div>

                            <div className="grid grid-3" style={{ marginBottom: 24 }}>
                                <div style={{ padding: 16, background: 'var(--bg-tertiary)', borderRadius: 8, textAlign: 'center' }}>
                                    <div style={{ fontSize: 24, fontWeight: 700 }}>{selectedUpload.event_count}</div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Events</div>
                                </div>
                                <div style={{ padding: 16, background: 'var(--bg-tertiary)', borderRadius: 8, textAlign: 'center' }}>
                                    <div style={{
                                        fontSize: 24, fontWeight: 700,
                                        color: selectedUpload.chain_break_count > 0 ? 'var(--warning)' : 'var(--success)'
                                    }}>
                                        {selectedUpload.chain_break_count}
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Chain Breaks</div>
                                </div>
                                <div style={{ padding: 16, background: 'var(--bg-tertiary)', borderRadius: 8, textAlign: 'center' }}>
                                    <div style={{ fontSize: 24, fontWeight: 700 }}>{selectedUpload.issues?.length ?? 0}</div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Issues</div>
                                </div>
                            </div>

                            {selectedUpload.issues && selectedUpload.issues.length > 0 && (
                                <div style={{ marginBottom: 24 }}>
                                    <h4 style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>Issues Found</h4>
                                    {selectedUpload.issues.map((issue, idx: number) => (
                                        <div key={idx} style={{
                                            padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8, marginBottom: 8,
                                            borderLeft: `3px solid ${
                                                issue.severity === 'critical' ? 'var(--danger)'
                                                : issue.severity === 'high' ? 'var(--warning)'
                                                : 'var(--info)'
                                            }`
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                                <span style={{ fontWeight: 500, fontSize: 13 }}>
                                                    {issue.type.replace(/_/g, ' ')}
                                                </span>
                                                <span className={`badge badge-${
                                                    issue.severity === 'critical' ? 'danger'
                                                    : issue.severity === 'high' ? 'warning'
                                                    : 'info'
                                                }`} style={{ fontSize: 10 }}>
                                                    {issue.severity}
                                                </span>
                                            </div>
                                            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{issue.message}</p>
                                            {issue.suggested_fix && (
                                                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                                                    Suggested fix: {issue.suggested_fix}
                                                </p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {selectedUpload.events && selectedUpload.events.length > 0 && (
                                <div>
                                    <h4 style={{ marginBottom: 12, color: 'var(--text-secondary)' }}>
                                        Parsed Events ({selectedUpload.events.length})
                                    </h4>
                                    <div style={{ overflowX: 'auto' }}>
                                        <table className="data-table smaller">
                                            <thead>
                                                <tr>
                                                    <th>Type</th>
                                                    <th>Action</th>
                                                    <th>Time</th>
                                                    <th>EPCs</th>
                                                    <th>Biz Step</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {selectedUpload.events.slice(0, 50).map((event, idx: number) => (
                                                    <tr key={idx}>
                                                        <td><span className="badge badge-info">{event.event_type}</span></td>
                                                        <td><span className="badge badge-secondary">{event.action ?? '—'}</span></td>
                                                        <td style={{ fontSize: 11 }}>
                                                            {event.event_time ? new Date(event.event_time).toLocaleString() : '—'}
                                                        </td>
                                                        <td>{event.epc_list?.length ?? 0} items</td>
                                                        <td style={{ fontSize: 11 }}>
                                                            {event.biz_step ? event.biz_step.split(':').pop() : '—'}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            )}

                            {(!selectedUpload.events || selectedUpload.events.length === 0)
                                && (!selectedUpload.issues || selectedUpload.issues.length === 0) && (
                                <div style={{ textAlign: 'center', padding: 24, color: 'var(--text-muted)' }}>
                                    <p>No events or issues found for this upload.</p>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
