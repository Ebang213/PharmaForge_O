import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { dscsaApi, vendorsApi, watchtowerApi } from '../lib/api';
import {
    CheckCircle, Circle, Upload, Building2, Bell, Calendar,
    AlertTriangle, FileCheck, Package, ArrowRight
} from 'lucide-react';
import type { EPCISUpload } from '../lib/types';

function getDaysUntil(targetDate: string): number {
    const now = new Date();
    const target = new Date(targetDate);
    const diff = target.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

export default function Dashboard() {
    const [tradingPartnerCount, setTradingPartnerCount] = useState(0);
    const [uploads, setUploads] = useState<EPCISUpload[]>([]);
    const [activeAlertCount, setActiveAlertCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const daysUntilDeadline = getDaysUntil('2026-11-27');

    useEffect(() => {
        loadStats();
    }, []);

    const loadStats = async () => {
        const [vendorsResult, uploadsResult, alertsResult] = await Promise.allSettled([
            vendorsApi.list(),
            dscsaApi.epcisList(),
            watchtowerApi.summary(),
        ]);

        if (vendorsResult.status === 'fulfilled') {
            const data = vendorsResult.value.data;
            setTradingPartnerCount(data.items?.length ?? (Array.isArray(data) ? data.length : 0));
        }
        if (uploadsResult.status === 'fulfilled') {
            setUploads(uploadsResult.value.data ?? []);
        }
        if (alertsResult.status === 'fulfilled') {
            setActiveAlertCount(alertsResult.value.data.active_alerts ?? 0);
        }
        setLoading(false);
    };

    const latestUpload = uploads[0];
    const validStatuses = ['valid', 'success'];
    const latestValid =
        uploads.length > 0 &&
        validStatuses.includes(latestUpload?.validation_status as string ?? '');
    const hasChainBreaks = uploads.some(u => (u.chain_break_count ?? 0) > 0);
    const auditPacketAvailable = uploads.some(u =>
        validStatuses.includes(u.validation_status as string)
    );

    const checklistItems = [
        {
            label: 'At least one trading partner on file',
            met: tradingPartnerCount > 0,
            action: '/trading-partners',
            actionLabel: 'Add Trading Partner',
        },
        {
            label: 'EPCIS transaction file uploaded',
            met: uploads.length > 0,
            action: '/transactions',
            actionLabel: 'Upload File',
        },
        {
            label: 'Latest EPCIS upload is valid',
            met: uploads.length > 0 && latestValid,
            action: '/transactions',
            actionLabel: 'View Transactions',
        },
        {
            label: 'No unresolved chain breaks',
            met: uploads.length > 0 && !hasChainBreaks,
            action: '/transactions',
            actionLabel: 'Review Issues',
        },
        {
            label: 'Inspection packet available',
            met: auditPacketAvailable,
            action: '/transactions',
            actionLabel: 'Generate Packet',
        },
    ];

    const metCount = checklistItems.filter(i => i.met).length;
    const readinessPercent = Math.round((metCount / checklistItems.length) * 100);

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Dashboard</h1>
                <p>DSCSA compliance overview for your pharmacy</p>
            </div>

            {/* Metric Cards */}
            <div className="grid grid-4" style={{ marginBottom: 32 }}>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Building2 size={24} />
                    </div>
                    <div className="content">
                        <h3>Trading Partners</h3>
                        <div className="value">{tradingPartnerCount}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#10b981' }}>
                        <FileCheck size={24} />
                    </div>
                    <div className="content">
                        <h3>EPCIS Files Uploaded</h3>
                        <div className="value">{uploads.length}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{
                        background: activeAlertCount > 0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                        color: activeAlertCount > 0 ? '#ef4444' : '#10b981'
                    }}>
                        <Bell size={24} />
                    </div>
                    <div className="content">
                        <h3>Active Alerts</h3>
                        <div className="value">{activeAlertCount}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
                        <Calendar size={24} />
                    </div>
                    <div className="content">
                        <h3>Days Until Nov 27, 2026</h3>
                        <div className="value">{daysUntilDeadline}</div>
                    </div>
                </div>
            </div>

            <div className="grid grid-2" style={{ gap: 24 }}>
                {/* DSCSA Readiness Checklist */}
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>DSCSA Readiness Checklist</h2>
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: 8,
                            padding: '6px 14px', borderRadius: 20,
                            background: readinessPercent === 100 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                            color: readinessPercent === 100 ? '#10b981' : '#f59e0b',
                            fontWeight: 700, fontSize: 14
                        }}>
                            {readinessPercent}% Ready
                        </div>
                    </div>

                    <div style={{ marginBottom: 16 }}>
                        <div style={{ height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                            <div style={{
                                width: `${readinessPercent}%`, height: '100%', borderRadius: 4,
                                background: readinessPercent === 100
                                    ? 'var(--success)'
                                    : readinessPercent >= 60
                                        ? 'var(--warning)'
                                        : 'var(--accent-primary)',
                                transition: 'width 0.5s ease'
                            }} />
                        </div>
                        <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            {metCount} of {checklistItems.length} operational checks passed.
                            This reflects operational readiness, not a legal compliance guarantee.
                        </p>
                    </div>

                    {checklistItems.map((item, idx) => (
                        <div key={idx} style={{
                            display: 'flex', alignItems: 'center', gap: 12,
                            padding: '12px 0',
                            borderBottom: idx < checklistItems.length - 1 ? '1px solid var(--border-color)' : 'none'
                        }}>
                            {item.met
                                ? <CheckCircle size={20} style={{ color: 'var(--success)', flexShrink: 0 }} />
                                : <Circle size={20} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                            }
                            <span style={{
                                flex: 1, fontSize: 14,
                                color: item.met ? 'var(--text-primary)' : 'var(--text-secondary)'
                            }}>
                                {item.label}
                            </span>
                            {!item.met && (
                                <Link to={item.action} style={{
                                    fontSize: 12, color: 'var(--accent-primary)',
                                    display: 'flex', alignItems: 'center', gap: 4,
                                    textDecoration: 'none', whiteSpace: 'nowrap'
                                }}>
                                    {item.actionLabel} <ArrowRight size={12} />
                                </Link>
                            )}
                        </div>
                    ))}
                </div>

                {/* Right column */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {/* Quick Actions */}
                    <div className="card">
                        <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>Quick Actions</h2>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                            <Link to="/transactions" style={{ textDecoration: 'none' }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 16,
                                    padding: 16, background: 'var(--bg-tertiary)', borderRadius: 10,
                                    cursor: 'pointer', border: '1px solid var(--border-color)'
                                }}>
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 10,
                                        background: 'rgba(99, 102, 241, 0.15)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                                    }}>
                                        <Upload size={20} style={{ color: 'var(--accent-primary)' }} />
                                    </div>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: 14 }}>Upload EPCIS File</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                            Validate transaction data from your wholesalers
                                        </div>
                                    </div>
                                    <ArrowRight size={16} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
                                </div>
                            </Link>

                            <Link to="/trading-partners" style={{ textDecoration: 'none' }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 16,
                                    padding: 16, background: 'var(--bg-tertiary)', borderRadius: 10,
                                    cursor: 'pointer', border: '1px solid var(--border-color)'
                                }}>
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 10,
                                        background: 'rgba(16, 185, 129, 0.15)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                                    }}>
                                        <Building2 size={20} style={{ color: '#10b981' }} />
                                    </div>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: 14 }}>Add Trading Partner</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                            Register wholesalers and distributors
                                        </div>
                                    </div>
                                    <ArrowRight size={16} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
                                </div>
                            </Link>

                            <Link to="/transactions" style={{ textDecoration: 'none' }}>
                                <div style={{
                                    display: 'flex', alignItems: 'center', gap: 16,
                                    padding: 16, background: 'var(--bg-tertiary)', borderRadius: 10,
                                    cursor: 'pointer', border: '1px solid var(--border-color)'
                                }}>
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 10,
                                        background: 'rgba(245, 158, 11, 0.15)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                                    }}>
                                        <Package size={20} style={{ color: '#f59e0b' }} />
                                    </div>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: 14 }}>Generate Inspection Packet</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                            Download audit-ready compliance documentation
                                        </div>
                                    </div>
                                    <ArrowRight size={16} style={{ marginLeft: 'auto', color: 'var(--text-muted)' }} />
                                </div>
                            </Link>
                        </div>
                    </div>

                    {/* Deadline Banner */}
                    <div className="card" style={{
                        background: daysUntilDeadline < 90 ? 'rgba(239, 68, 68, 0.08)' : 'rgba(245, 158, 11, 0.08)',
                        border: `1px solid ${daysUntilDeadline < 90 ? 'var(--danger)' : 'rgba(245, 158, 11, 0.3)'}`,
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                            <AlertTriangle size={24} style={{
                                color: daysUntilDeadline < 90 ? 'var(--danger)' : '#f59e0b',
                                flexShrink: 0
                            }} />
                            <div>
                                <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
                                    FDA DSCSA Enforcement Deadline
                                </div>
                                <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                    November 27, 2026 — <strong>{daysUntilDeadline} days</strong> remaining.
                                    All dispensers must be interoperable with the electronic drug tracing system by this date.
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
