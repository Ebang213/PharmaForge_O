import { useState, useEffect } from 'react';
import { watchtowerApi } from '../lib/api';
import {
    Bell, RefreshCw, X, ExternalLink, Clock,
    Rss, CheckCircle, WifiOff, Radio
} from 'lucide-react';
import type { WatchtowerAlert, FeedItem } from '../lib/types';

export default function Alerts() {
    const [alerts, setAlerts] = useState<WatchtowerAlert[]>([]);
    const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'alerts' | 'feed'>('alerts');
    const [serviceStatus, setServiceStatus] = useState<'online' | 'offline' | 'checking'>('checking');

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setError(null);
        setServiceStatus('checking');
        try {
            const [alertsRes, feedRes] = await Promise.all([
                watchtowerApi.alerts({ acknowledged: 'false' }),
                watchtowerApi.feed({ limit: 50 }),
            ]);
            setAlerts(alertsRes.data);
            setFeedItems(feedRes.data);
            setServiceStatus('online');
        } catch (err: any) {
            if (err.response?.status === 401) return;
            const statusCode = err.response?.status || 'NETWORK';
            const errDetail = err.response?.data?.detail || err.message || 'Unknown error';
            setError(`API Error (${statusCode}): ${errDetail}`);
            setServiceStatus('offline');
        } finally {
            setLoading(false);
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

    const getSeverityBadge = (severity: string) => {
        const classes: Record<string, string> = {
            critical: 'badge badge-danger',
            high: 'badge badge-warning',
            medium: 'badge badge-info',
            low: 'badge badge-success',
        };
        return <span className={classes[severity] || 'badge'}>{severity.toUpperCase()}</span>;
    };

    const formatDate = (dateStr?: string) => {
        if (!dateStr) return '-';
        try { return new Date(dateStr).toLocaleString(); } catch { return dateStr; }
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1>Alerts</h1>
                    <p>FDA recalls, drug shortages, and supply chain alerts</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <button className="btn btn-secondary" onClick={loadData}>
                        <RefreshCw size={16} /> Refresh
                    </button>
                    {serviceStatus === 'offline' ? (
                        <span className="badge badge-danger" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <WifiOff size={12} /> Offline
                        </span>
                    ) : serviceStatus === 'online' ? (
                        <span className="badge badge-success" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Radio size={12} /> Live
                        </span>
                    ) : null}
                </div>
            </div>

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

            {/* Stats */}
            <div style={{ display: 'flex', gap: 16, marginBottom: 24 }}>
                <div className="stat-card" style={{ flex: '0 0 auto', minWidth: 200 }}>
                    <div className="icon" style={{
                        background: alerts.length > 0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                        color: alerts.length > 0 ? '#ef4444' : '#10b981'
                    }}>
                        <Bell size={24} />
                    </div>
                    <div className="content">
                        <h3>Active Alerts</h3>
                        <div className="value">{alerts.length}</div>
                    </div>
                </div>
                <div className="stat-card" style={{ flex: '0 0 auto', minWidth: 200 }}>
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Rss size={24} />
                    </div>
                    <div className="content">
                        <h3>FDA Feed Items</h3>
                        <div className="value">{feedItems.length}</div>
                    </div>
                </div>
            </div>

            {/* Tab Navigation */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 24 }}>
                <button
                    className={`btn ${activeTab === 'alerts' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveTab('alerts')}
                >
                    <Bell size={16} /> Alerts ({alerts.length})
                </button>
                <button
                    className={`btn ${activeTab === 'feed' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setActiveTab('feed')}
                >
                    <Rss size={16} /> FDA Feed ({feedItems.length})
                </button>
            </div>

            {/* Alerts Tab */}
            {activeTab === 'alerts' && (
                <div className="card">
                    <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>Active Alerts</h2>
                    {alerts.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <CheckCircle size={48} style={{ marginBottom: 16, opacity: 0.3, color: 'var(--success)' }} />
                            <p style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>
                                No active alerts
                            </p>
                            <p style={{ maxWidth: 400, margin: '0 auto', fontSize: 14 }}>
                                No FDA recalls, drug shortages, or chain-break events are currently active.
                            </p>
                        </div>
                    ) : (
                        alerts.map(alert => (
                            <div key={alert.id} style={{
                                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                                padding: 16, borderBottom: '1px solid var(--border-color)'
                            }}>
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                                        {getSeverityBadge(alert.severity)}
                                        <span style={{ fontWeight: 500 }}>
                                            {(alert as any).vendor_name || 'Unknown Source'}
                                        </span>
                                    </div>
                                    <p style={{ color: 'var(--text-secondary)', fontSize: 14, fontWeight: 500 }}>
                                        {alert.title || (alert as any).event?.title || 'Alert details not available'}
                                    </p>
                                    {(alert as any).description && (
                                        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
                                            {(alert as any).description}
                                        </p>
                                    )}
                                    <p style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <Clock size={10} /> {new Date(alert.created_at).toLocaleString()}
                                    </p>
                                </div>
                                <button
                                    className="btn btn-secondary"
                                    style={{ padding: 8 }}
                                    onClick={() => handleAcknowledge(alert.id)}
                                    title="Acknowledge"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            )}

            {/* FDA Feed Tab */}
            {activeTab === 'feed' && (
                <div className="card">
                    <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 20 }}>FDA Live Feed</h2>
                    {feedItems.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <Rss size={48} style={{ marginBottom: 16, opacity: 0.2 }} />
                            <p style={{ fontSize: 16, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>
                                No feed items yet
                            </p>
                            <p style={{ maxWidth: 400, margin: '0 auto', fontSize: 14 }}>
                                FDA drug recall and shortage data will appear here once synced by your administrator.
                            </p>
                        </div>
                    ) : (
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Source</th>
                                    <th>Title</th>
                                    <th>Category</th>
                                    <th>Date</th>
                                    <th>Link</th>
                                </tr>
                            </thead>
                            <tbody>
                                {feedItems.map(item => (
                                    <tr key={item.id}>
                                        <td style={{ whiteSpace: 'nowrap' }}>
                                            {item.source.replace(/_/g, ' ').toUpperCase()}
                                        </td>
                                        <td style={{ maxWidth: 420 }}>
                                            <div style={{ fontWeight: 500 }}>{item.title}</div>
                                            {(item as any).summary && (
                                                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                                    {(item as any).summary.length > 120
                                                        ? `${(item as any).summary.substring(0, 120)}...`
                                                        : (item as any).summary}
                                                </div>
                                            )}
                                        </td>
                                        <td>
                                            <span className="badge badge-danger" style={{ fontSize: 10 }}>
                                                {item.category?.toUpperCase() || 'RECALL'}
                                            </span>
                                        </td>
                                        <td style={{ whiteSpace: 'nowrap', fontSize: 13 }}>
                                            {formatDate(item.published_at || (item as any).created_at)}
                                        </td>
                                        <td>
                                            {item.url ? (
                                                <a href={item.url} target="_blank" rel="noopener noreferrer"
                                                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
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
        </div>
    );
}
