import { useState, useEffect } from 'react';
import { watchtowerApi, vendorsApi } from '../lib/api';
import { AlertTriangle, Building2, Bell, RefreshCw, CheckCircle, X, Plus, WifiOff, Radio, ExternalLink, Clock, Rss, Shield, FileText } from 'lucide-react';
import type { RiskSummary, WatchtowerAlert, Vendor, FeedItem, FeedSource, FeedSummary, Evidence } from '../lib/types';
import { Link } from 'react-router-dom';

export default function Watchtower() {
    const [summary, setSummary] = useState<RiskSummary | null>(null);
    const [alerts, setAlerts] = useState<WatchtowerAlert[]>([]);
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
    const [sources, setSources] = useState<FeedSource[]>([]);
    const [feedSummary, setFeedSummary] = useState<FeedSummary | null>(null);
    const [healthStatus, setHealthStatus] = useState<{
        overall_status: 'healthy' | 'degraded' | 'down';
        sources: Array<{
            source_id: string;
            source_name: string;
            status: 'ok' | 'error' | 'pending';
            last_success_at: string | null;
            last_attempt_at: string | null;
            last_error: string | null;
        }>;
        all_sources_healthy: boolean;
    } | null>(null);
    const [evidenceItems, setEvidenceItems] = useState<Evidence[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState<string>('');
    const [error, setError] = useState<string | null>(null);
    const [serviceStatus, setServiceStatus] = useState<'online' | 'offline' | 'checking'>('checking');
    const [uploading, setUploading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [analysisResult, setAnalysisResult] = useState<any>(null);
    const [selectedSource, setSelectedSource] = useState<string>('');
    const [activeTab, setActiveTab] = useState<'alerts' | 'feed' | 'evidence'>('feed');
    const [userRole, setUserRole] = useState<string>('viewer');

    useEffect(() => {
        loadData();
        // Get user role from localStorage
        try {
            const userStr = localStorage.getItem('pharmaforge_user');
            if (userStr) {
                const user = JSON.parse(userStr);
                setUserRole(user.role || 'viewer');
            }
        } catch (e) {
            console.error('Failed to parse user:', e);
        }
    }, []);

    const loadData = async () => {
        setError(null);
        setServiceStatus('checking');
        try {
            const [summaryRes, alertsRes, vendorsRes, sourcesRes, feedRes, feedSummaryRes, healthRes, evidenceRes] = await Promise.all([
                watchtowerApi.summary(),
                watchtowerApi.alerts({ acknowledged: 'false' }),
                vendorsApi.list(),
                watchtowerApi.sources(),
                watchtowerApi.feed({ limit: 50 }),
                watchtowerApi.feedSummary(),
                watchtowerApi.health(),
                watchtowerApi.listEvidence({ limit: 25 }),
            ]);
            setSummary(summaryRes.data);
            setAlerts(alertsRes.data);
            setVendors(vendorsRes.data);
            setSources(sourcesRes.data);
            setFeedItems(feedRes.data);
            setFeedSummary(feedSummaryRes.data);
            setHealthStatus(healthRes.data);
            setEvidenceItems(evidenceRes.data);
            setServiceStatus('online');
        } catch (err: any) {
            console.error('Failed to load watchtower data:', err);
            // All non-401 errors should show error state - DO NOT fake success with empty data
            if (err.response?.status === 401) {
                // Will be handled by API interceptor (redirect to login)
                return;
            }
            // Show real error status - no fake "online" with empty fallback data
            const statusCode = err.response?.status || 'NETWORK';
            const errDetail = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`API Error (${statusCode}): ${errDetail}`);
            setServiceStatus('offline');
        } finally {
            setLoading(false);
        }
    };

    const handleSync = async (source?: string) => {
        setSyncing(true);
        setError(null);
        try {
            await watchtowerApi.sync({ source, force: true });
            await loadData();
        } catch (err: any) {
            console.error('Sync failed:', err);
            if (err.response?.status === 403) {
                setError('Only admins can trigger sync.');
            } else {
                setError(err.response?.data?.detail || 'Sync failed');
            }
        } finally {
            setSyncing(false);
        }
    };

    const handleAcknowledge = async (alertId: number) => {
        try {
            await watchtowerApi.acknowledgeAlert(alertId);
            setAlerts(alerts.filter(a => a.id !== alertId));
        } catch (error) {
            console.error('Failed to acknowledge alert:', error);
        }
    };

    const handleRecalculate = async () => {
        setLoading(true);
        try {
            await watchtowerApi.recalculateRisk();
            await loadData();
        } catch (error) {
            console.error('Failed to recalculate risk:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setUploading(true);
        setError(null);
        setAnalysisResult(null);

        try {
            // 1. Upload
            const uploadRes = await watchtowerApi.uploadEvidence(file);
            const evidenceId = uploadRes.data.id;

            // 2. Analyze
            const analysisRes = await watchtowerApi.analyzeEvidence(evidenceId);
            setAnalysisResult(analysisRes.data);

            // 3. Refresh
            await loadData();
            setActiveTab('evidence');
        } catch (err: any) {
            console.error('Analysis failed:', err);
            setError(err.response?.data?.detail || 'Evidence analysis failed');
        } finally {
            setUploading(false);
        }
    };

    const getSeverityBadge = (severity: string) => {
        const classes: Record<string, string> = {
            critical: 'badge badge-danger',
            high: 'badge badge-warning',
            medium: 'badge badge-info',
            low: 'badge badge-success',
        };
        return <span className={classes[severity] || 'badge'}>{severity.toUpperCase()}</span>;
    };

    const getEvidenceStatusBadge = (status: string) => {
        const normalized = status?.toLowerCase();
        const classes: Record<string, string> = {
            processed: 'badge badge-success',
            pending: 'badge badge-warning',
            failed: 'badge badge-danger',
        };
        const label = status ? status.toUpperCase() : 'UNKNOWN';
        return <span className={classes[normalized] || 'badge'}>{label}</span>;
    };

    const formatDate = (dateStr?: string) => {
        if (!dateStr) return '-';
        try {
            return new Date(dateStr).toLocaleString();
        } catch {
            return dateStr;
        }
    };

    const getSourceStatus = (source: FeedSource) => {
        if (!source.last_run_at) {
            return { status: 'pending', label: 'Never synced', color: 'var(--text-muted)' };
        }
        if (source.last_error_at && (!source.last_success_at || new Date(source.last_error_at) > new Date(source.last_success_at))) {
            return { status: 'error', label: 'Error', color: 'var(--danger)' };
        }
        return { status: 'healthy', label: 'Live', color: 'var(--success)' };
    };

    if (loading) {
        return <div className="loading-container"><div className="spinner" /></div>;
    }

    return (
        <div className="fade-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <Shield size={28} style={{ color: 'var(--accent-primary)' }} />
                        Watchtower
                    </h1>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 4 }}>FDA live monitoring and supply chain risk intelligence</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {uploading && <div className="spinner smaller" style={{ margin: 0 }} />}
                    <label className={`btn btn-secondary ${uploading ? 'disabled' : ''}`} style={{ cursor: 'pointer' }}>
                        <Plus size={18} />
                        {uploading ? 'Analyzing...' : 'Upload Evidence'}
                        <input
                            type="file"
                            accept=".pdf,.txt"
                            onChange={handleFileUpload}
                            style={{ display: 'none' }}
                            disabled={uploading}
                        />
                    </label>
                    {(userRole === 'admin' || userRole === 'owner') && (
                        <button
                            className={`btn btn-primary ${syncing ? 'disabled' : ''}`}
                            onClick={() => handleSync()}
                            disabled={syncing}
                        >
                            <RefreshCw size={16} className={syncing ? 'spin' : ''} />
                            {syncing ? 'Syncing...' : 'Sync Now'}
                        </button>
                    )}
                    <div style={{ width: 1, height: 24, background: 'var(--border-color)' }}></div>
                    {serviceStatus === 'offline' || healthStatus?.overall_status === 'down' ? (
                        <span className="badge badge-danger" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <WifiOff size={12} /> Offline
                        </span>
                    ) : healthStatus?.overall_status === 'degraded' || !healthStatus?.all_sources_healthy ? (
                        <span className="badge badge-warning" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <AlertTriangle size={12} /> Degraded
                        </span>
                    ) : (
                        <span className="badge badge-success" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Radio size={12} /> Live
                        </span>
                    )}
                </div>
            </div>

            {/* Analysis Result Notification */}
            {analysisResult && (
                <div className="card fade-in" style={{
                    background: 'rgba(16, 185, 129, 0.1)',
                    border: '1px solid var(--success)',
                    marginBottom: 24,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <CheckCircle size={24} style={{ color: 'var(--success)' }} />
                        <div>
                            <p style={{ fontWeight: 600, color: 'var(--success)' }}>Analysis Complete: {analysisResult.doc_type}</p>
                            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                Detected {analysisResult.doc_type} for <strong>{analysisResult.matched_vendor || 'Unknown Vendor'}</strong>.
                                Severity: <strong>{analysisResult.severity.toUpperCase()}</strong>
                            </p>
                        </div>
                    </div>
                    <button className="btn btn-secondary btn-small" onClick={() => setAnalysisResult(null)}>Dismiss</button>
                </div>
            )}

            {/* Error Banner */}
            {error && (
                <div className="card" style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', marginBottom: 24 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <WifiOff size={24} style={{ color: 'var(--danger)' }} />
                        <div>
                            <p style={{ fontWeight: 500, color: 'var(--danger)' }}>{error}</p>
                            <button className="btn btn-secondary" style={{ marginTop: 8 }} onClick={loadData}>
                                <RefreshCw size={14} /> Retry
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Stats Cards */}
            <div className="grid grid-4" style={{ marginBottom: 32 }}>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Rss size={24} />
                    </div>
                    <div className="content">
                        <h3>Feed Items</h3>
                        <div className="value">{feedSummary?.total_items || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' }}>
                        <Bell size={24} />
                    </div>
                    <div className="content">
                        <h3>Active Alerts</h3>
                        <div className="value">{feedSummary?.active_alerts || summary?.active_alerts || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Building2 size={24} />
                    </div>
                    <div className="content">
                        <h3>Total Vendors</h3>
                        <div className="value">{feedSummary?.total_vendors || summary?.total_vendors || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
                        <AlertTriangle size={24} />
                    </div>
                    <div className="content">
                        <h3>High Risk Vendors</h3>
                        <div className="value">{feedSummary?.high_risk_vendors || summary?.high_risk_vendors || 0}</div>
                    </div>
                </div>
            </div>

            {/* Source Status */}
            <div className="card" style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                    <h2 style={{ fontSize: 16, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Rss size={18} /> Feed Sources
                    </h2>
                    {feedSummary?.last_sync_at && (
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Clock size={12} /> Last sync: {formatDate(feedSummary.last_sync_at)}
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    {sources.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)' }}>No sources configured. Click "Sync Now" to fetch FDA data.</p>
                    ) : (
                        sources.map(source => {
                            const status = getSourceStatus(source);
                            return (
                                <div
                                    key={source.source_id}
                                    onClick={() => setSelectedSource(selectedSource === source.source_id ? '' : source.source_id)}
                                    style={{
                                        padding: '12px 16px',
                                        background: selectedSource === source.source_id ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                                        borderRadius: 8,
                                        cursor: 'pointer',
                                        transition: 'all 0.2s',
                                        border: selectedSource === source.source_id ? '1px solid var(--accent-primary)' : '1px solid var(--border-color)',
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <div style={{
                                            width: 8,
                                            height: 8,
                                            borderRadius: '50%',
                                            background: status.color,
                                            animation: status.status === 'healthy' ? 'pulse 2s infinite' : 'none'
                                        }} />
                                        <span style={{ fontWeight: 500, color: selectedSource === source.source_id ? '#fff' : 'var(--text-primary)' }}>
                                            {source.source_name}
                                        </span>
                                        <span style={{
                                            fontSize: 11,
                                            padding: '2px 6px',
                                            background: selectedSource === source.source_id ? 'rgba(255,255,255,0.2)' : 'var(--bg-secondary)',
                                            borderRadius: 4,
                                            color: selectedSource === source.source_id ? '#fff' : 'var(--text-muted)'
                                        }}>
                                            {source.category}
                                        </span>
                                    </div>
                                    {source.last_run_at && (
                                        <div style={{ fontSize: 11, color: selectedSource === source.source_id ? 'rgba(255,255,255,0.7)' : 'var(--text-muted)', marginTop: 4 }}>
                                            Updated: {formatDate(source.last_run_at)}
                                        </div>
                                    )}
                                    {source.last_success_at && (
                                        <div style={{ fontSize: 11, color: selectedSource === source.source_id ? 'rgba(255,255,255,0.7)' : 'var(--text-muted)', marginTop: 4 }}>
                                            Last success: {formatDate(source.last_success_at)}
                                        </div>
                                    )}
                                    {/* Enhanced tracking: HTTP status and item counts */}
                                    {(source.last_http_status || source.items_fetched !== undefined) && (
                                        <div style={{
                                            fontSize: 10,
                                            color: selectedSource === source.source_id ? 'rgba(255,255,255,0.6)' : 'var(--text-muted)',
                                            marginTop: 4,
                                            display: 'flex',
                                            gap: 8
                                        }}>
                                            {source.last_http_status && (
                                                <span>HTTP: {source.last_http_status}</span>
                                            )}
                                            {source.items_fetched !== undefined && (
                                                <span>Fetched: {source.items_fetched}</span>
                                            )}
                                            {source.items_saved !== undefined && (
                                                <span>Saved: {source.items_saved}</span>
                                            )}
                                        </div>
                                    )}
                                    {source.last_error_at && (
                                        <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
                                            Last error: {formatDate(source.last_error_at)}
                                        </div>
                                    )}
                                    {source.last_error_message && (
                                        <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
                                            Error: {source.last_error_message.substring(0, 60)}...
                                        </div>
                                    )}
                                </div>
                            );
                        })
                    )}
                </div>
            </div>

            {/* Tab Navigation */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
                <button
                    className={`btn ${activeTab === 'feed' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveTab('feed')}
                >
                    <Rss size={16} /> Live Feed ({feedItems.length})
                </button>
                <button
                    className={`btn ${activeTab === 'alerts' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveTab('alerts')}
                >
                    <Bell size={16} /> Alerts ({alerts.length})
                </button>
                <button
                    className={`btn ${activeTab === 'evidence' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveTab('evidence')}
                >
                    <FileText size={16} /> Evidence ({evidenceItems.length})
                </button>
            </div>

            {/* Live Feed Section */}
            {activeTab === 'feed' && (
                <div className="card" style={{ marginBottom: 24 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>
                            {selectedSource ? `${sources.find(s => s.source_id === selectedSource)?.source_name || selectedSource}` : 'All Sources'}
                            <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                                FDA Shortages, Recalls, Warning Letters
                            </span>
                        </h2>
                        {selectedSource && (
                            <button className="btn btn-secondary btn-small" onClick={() => setSelectedSource('')}>
                                Clear Filter
                            </button>
                        )}
                    </div>

                    {feedItems.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <Rss size={48} style={{ marginBottom: 16, opacity: 0.2 }} />
                            <p style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>No feed items yet</p>
                            <p style={{ maxWidth: 400, margin: '0 auto', fontSize: 14 }}>
                                {(userRole === 'admin' || userRole === 'owner')
                                    ? 'Click "Sync Now" to fetch the latest FDA drug recalls and enforcement data.'
                                    : 'Feed data will appear here once an admin triggers a sync.'}
                            </p>
                            {(userRole === 'admin' || userRole === 'owner') && !syncing && (
                                <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => handleSync()}>
                                    <RefreshCw size={16} /> Sync FDA Data
                                </button>
                            )}
                        </div>
                    ) : (
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Source</th>
                                    <th>Title</th>
                                    <th>Tag</th>
                                    <th>Date</th>
                                    <th>Link</th>
                                </tr>
                            </thead>
                            <tbody>
                                {feedItems
                                    .filter(item => !selectedSource || item.source === selectedSource)
                                    .map(item => (
                                        <tr key={item.id}>
                                            <td style={{ whiteSpace: 'nowrap' }}>{item.source.replace(/_/g, ' ').toUpperCase()}</td>
                                            <td style={{ maxWidth: 420 }}>
                                                <div style={{ fontWeight: 500 }}>{item.title}</div>
                                                {item.summary && (
                                                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                                        {item.summary.length > 160 ? `${item.summary.substring(0, 160)}...` : item.summary}
                                                    </div>
                                                )}
                                            </td>
                                            <td>
                                                <span className="badge badge-danger" style={{ fontSize: 10 }}>
                                                    {item.category?.toUpperCase() || 'RECALL'}
                                                </span>
                                            </td>
                                            <td style={{ whiteSpace: 'nowrap' }}>
                                                {item.published_at ? formatDate(item.published_at) : formatDate(item.created_at)}
                                            </td>
                                            <td>
                                                {item.url ? (
                                                    <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                                        Open <ExternalLink size={12} />
                                                    </a>
                                                ) : '-'}
                                            </td>
                                        </tr>
                                    ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}

            {/* Alerts Section */}
            {activeTab === 'alerts' && (
                <div className="card" style={{ marginBottom: 24 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Active Alerts</h2>
                        <button className="btn btn-secondary" onClick={handleRecalculate}>
                            <RefreshCw size={16} /> Recalculate Risk
                        </button>
                    </div>

                    {alerts.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <Bell size={48} style={{ marginBottom: 16, opacity: 0.2 }} />
                            <p style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>No active alerts</p>
                            <p style={{ maxWidth: 400, margin: '0 auto', fontSize: 14 }}>
                                Upload an FDA warning letter, recall notice, or 483 form to generate real intelligence alerts.
                            </p>
                        </div>
                    ) : (
                        <div className="alerts-list">
                            {alerts.map(alert => (
                                <div key={alert.id} className="alert-item" style={{
                                    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                                    padding: 16, borderBottom: '1px solid var(--border-color)'
                                }}>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                                            {getSeverityBadge(alert.severity)}
                                            <span style={{ fontWeight: 500 }}>{alert.vendor_name || 'Unknown Vendor'}</span>
                                        </div>
                                        <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontWeight: 500 }}>
                                            {alert.title || alert.event?.title || 'Alert details not available'}
                                        </p>
                                        {alert.description && (
                                            <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                                                {alert.description}
                                            </p>
                                        )}
                                        <p style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <RefreshCw size={10} /> {new Date(alert.created_at).toLocaleString()}
                                        </p>
                                    </div>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ padding: 8 }}
                                        onClick={() => handleAcknowledge(alert.id)}
                                    >
                                        <X size={16} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Evidence Section */}
            {activeTab === 'evidence' && (
                <div className="card" style={{ marginBottom: 24 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Evidence Uploads</h2>
                    </div>

                    {evidenceItems.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <FileText size={48} style={{ marginBottom: 16, opacity: 0.2 }} />
                            <p style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>No evidence uploaded yet</p>
                            <p style={{ maxWidth: 400, margin: '0 auto', fontSize: 14 }}>
                                Upload a PDF or TXT file to attach evidence directly to Watchtower.
                            </p>
                        </div>
                    ) : (
                        <table className="data-table smaller">
                            <thead>
                                <tr>
                                    <th>File</th>
                                    <th>Source</th>
                                    <th>Status</th>
                                    <th>Uploaded</th>
                                    <th>Vendor</th>
                                    <th>Metadata</th>
                                    <th>Extracted Text</th>
                                </tr>
                            </thead>
                            <tbody>
                                {evidenceItems.map(item => (
                                    <tr key={item.id}>
                                        <td style={{ fontWeight: 500 }}>
                                            {item.filename}
                                            {item.content_type && (
                                                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.content_type}</div>
                                            )}
                                        </td>
                                        <td>
                                            <span className={`badge ${item.source === 'watchtower' ? 'badge-info' : 'badge-success'}`} style={{ fontSize: 10 }}>
                                                {(item.source || 'upload').toUpperCase()}
                                            </span>
                                        </td>
                                        <td>{getEvidenceStatusBadge(item.status)}</td>
                                        <td style={{ whiteSpace: 'nowrap' }}>{formatDate(item.uploaded_at)}</td>
                                        <td>{item.vendor_name || '-'}</td>
                                        <td>
                                            {item.source_type && (
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Type: {item.source_type}</div>
                                            )}
                                            {item.notes && (
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                                    {item.notes.length > 80 ? `${item.notes.substring(0, 80)}...` : item.notes}
                                                </div>
                                            )}
                                            {!item.source_type && !item.notes && '-'}
                                        </td>
                                        <td style={{ maxWidth: 320, fontSize: 12, color: 'var(--text-secondary)' }}>
                                            {item.extracted_text_preview ? (
                                                item.extracted_text_preview.length > 140
                                                    ? `${item.extracted_text_preview.substring(0, 140)}...`
                                                    : item.extracted_text_preview
                                            ) : '-'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            )}

            {/* Vendors Table */}
            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <h2 style={{ fontSize: 18, fontWeight: 600 }}>Vendor Risk Overview</h2>
                    <input
                        type="text"
                        placeholder="Search vendors..."
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        style={{ width: 250 }}
                    />
                </div>

                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Vendor</th>
                            <th>Type</th>
                            <th>Country</th>
                            <th>Risk Score</th>
                            <th>Risk Level</th>
                            <th>Alerts</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {vendors.length === 0 ? (
                            <tr>
                                <td colSpan={7} style={{ textAlign: 'center', padding: 40 }}>
                                    <Building2 size={48} style={{ marginBottom: 16, opacity: 0.3, color: 'var(--text-muted)' }} />
                                    <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>No vendors yet</p>
                                    <Link to="/vendors" className="btn btn-primary">
                                        <Plus size={16} /> Add Your First Vendor
                                    </Link>
                                </td>
                            </tr>
                        ) : (
                            vendors
                                .filter(v => !filter || v.name.toLowerCase().includes(filter.toLowerCase()))
                                .map(vendor => (
                                    <tr key={vendor.id}>
                                        <td style={{ fontWeight: 500 }}>{vendor.name}</td>
                                        <td style={{ color: 'var(--text-secondary)' }}>{vendor.vendor_type || '-'}</td>
                                        <td style={{ color: 'var(--text-secondary)' }}>{vendor.country || '-'}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <div style={{
                                                    width: 60, height: 6, background: 'var(--bg-tertiary)', borderRadius: 3, overflow: 'hidden'
                                                }}>
                                                    <div style={{
                                                        width: `${vendor.risk_score}%`, height: '100%',
                                                        background: vendor.risk_score > 50 ? 'var(--danger)' : vendor.risk_score > 25 ? 'var(--warning)' : 'var(--success)'
                                                    }} />
                                                </div>
                                                <span style={{ fontSize: 13 }}>{vendor.risk_score.toFixed(0)}</span>
                                            </div>
                                        </td>
                                        <td>{getSeverityBadge(vendor.risk_level)}</td>
                                        <td>{vendor.alert_count > 0 && <span className="badge badge-danger">{vendor.alert_count}</span>}</td>
                                        <td>{vendor.is_approved ? <span className="badge badge-success">Approved</span> : <span className="badge badge-warning">Pending</span>}</td>
                                    </tr>
                                ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
