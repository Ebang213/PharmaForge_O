import { useState, useEffect } from 'react';
import { auditApi } from '../lib/api';
import { ScrollText, Filter, Download, Calendar, User, Activity } from 'lucide-react';
import type { AuditLogEntry } from '../lib/types';

export default function AuditLog() {
    const [logs, setLogs] = useState<AuditLogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [summary, setSummary] = useState<any>(null);
    const [filters, setFilters] = useState({ action: '', entity_type: '', start_date: '' });
    const [actions, setActions] = useState<string[]>([]);

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [logsRes, summaryRes, actionsRes] = await Promise.all([
                auditApi.logs(filters),
                auditApi.summary(),
                auditApi.actions()
            ]);
            setLogs(logsRes.data);
            setSummary(summaryRes.data);
            setActions(actionsRes.data);
        } catch (error) {
            console.error('Failed to load audit data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleFilter = async () => {
        setLoading(true);
        try {
            const res = await auditApi.logs(filters);
            setLogs(res.data);
        } catch (error) {
            console.error('Filter failed:', error);
        } finally {
            setLoading(false);
        }
    };

    const exportLogs = () => {
        const csv = [
            ['Timestamp', 'User', 'Action', 'Entity Type', 'Entity ID', 'IP Address'].join(','),
            ...logs.map(log => [
                log.timestamp, log.user_email || '', log.action, log.entity_type || '',
                log.entity_id || '', log.ip_address || ''
            ].join(','))
        ].join('\n');

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'audit_log.csv';
        a.click();
    };

    const getActionBadge = (action: string) => {
        if (action.includes('create') || action.includes('upload')) return 'badge badge-success';
        if (action.includes('delete') || action.includes('logout')) return 'badge badge-danger';
        if (action.includes('update') || action.includes('change')) return 'badge badge-warning';
        return 'badge badge-info';
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Audit Log</h1>
                <p>Compliance-grade activity tracking and audit trail</p>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-4" style={{ marginBottom: 24 }}>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <ScrollText size={24} />
                    </div>
                    <div className="content">
                        <h3>Total Events</h3>
                        <div className="value">{summary?.total_events?.toLocaleString() || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e' }}>
                        <Calendar size={24} />
                    </div>
                    <div className="content">
                        <h3>Today</h3>
                        <div className="value">{summary?.events_today || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
                        <Activity size={24} />
                    </div>
                    <div className="content">
                        <h3>Action Types</h3>
                        <div className="value">{summary?.top_actions?.length || 0}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(139, 92, 246, 0.15)', color: '#8b5cf6' }}>
                        <User size={24} />
                    </div>
                    <div className="content">
                        <h3>Active Users</h3>
                        <div className="value">{summary?.top_users?.length || 0}</div>
                    </div>
                </div>
            </div>

            <div className="card">
                {/* Filters */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                        <Filter size={18} style={{ color: 'var(--text-muted)' }} />
                        <select value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} style={{ width: 150 }}>
                            <option value="">All Actions</option>
                            {actions.map(a => <option key={a} value={a}>{a}</option>)}
                        </select>
                        <input type="date" value={filters.start_date} onChange={(e) => setFilters({ ...filters, start_date: e.target.value })} />
                        <button className="btn btn-secondary" onClick={handleFilter}>Apply</button>
                    </div>
                    <button className="btn btn-secondary" onClick={exportLogs}>
                        <Download size={16} /> Export CSV
                    </button>
                </div>

                {/* Log Table */}
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>User</th>
                            <th>Action</th>
                            <th>Entity</th>
                            <th>Details</th>
                            <th>IP Address</th>
                        </tr>
                    </thead>
                    <tbody>
                        {logs.map(log => (
                            <tr key={log.id}>
                                <td style={{ whiteSpace: 'nowrap', fontSize: 13 }}>
                                    {new Date(log.timestamp).toLocaleString()}
                                </td>
                                <td>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <div style={{
                                            width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-gradient)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600
                                        }}>
                                            {log.user_email?.charAt(0).toUpperCase() || '?'}
                                        </div>
                                        <span style={{ fontSize: 13 }}>{log.user_email || 'System'}</span>
                                    </div>
                                </td>
                                <td><span className={getActionBadge(log.action)}>{log.action}</span></td>
                                <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                                    {log.entity_type ? `${log.entity_type}${log.entity_id ? `:${log.entity_id}` : ''}` : '-'}
                                </td>
                                <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12, color: 'var(--text-muted)' }}>
                                    {log.details ? JSON.stringify(log.details) : '-'}
                                </td>
                                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{log.ip_address || '-'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                {logs.length === 0 && (
                    <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                        <ScrollText size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                        <p>No audit logs found</p>
                    </div>
                )}
            </div>
        </div>
    );
}
