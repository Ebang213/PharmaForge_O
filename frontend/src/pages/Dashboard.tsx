import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { complianceApi, dscsaApi, tradingPartnersApi } from '../lib/api';
import {
    CheckCircle, Circle, Upload, Building2, Bell, Calendar,
    AlertTriangle, FileCheck, Package, ArrowRight
} from 'lucide-react';
import type { ComplianceReadiness, EPCISUpload, TradingPartnerReadiness } from '../lib/types';

function getDaysUntil(targetDate: string): number {
    const now = new Date();
    const target = new Date(targetDate);
    const diff = target.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

// Where to send the user to fix each failing readiness check
const readinessCheckActions: Record<string, string> = {
    trading_partner_license: '/trading-partners',
    recent_epcis_upload: '/transactions',
    latest_upload_valid: '/transactions',
    chain_integrity: '/transactions',
    audit_packet_generated: '/transactions',
};

const readinessCheckActionLabels: Record<string, string> = {
    trading_partner_license: 'Add Trading Partner',
    recent_epcis_upload: 'Upload File',
    latest_upload_valid: 'View Transactions',
    chain_integrity: 'Review Issues',
    audit_packet_generated: 'Generate Packet',
};

export default function Dashboard() {
    const [readiness, setReadiness] = useState<ComplianceReadiness | null>(null);
    const [partnerReadiness, setPartnerReadiness] = useState<TradingPartnerReadiness>({
        total_trading_partners: 0,
        verified_partners: 0,
        incomplete_partners: 0,
        readiness_percentage: 0,
    });
    const [uploads, setUploads] = useState<EPCISUpload[]>([]);
    const [loading, setLoading] = useState(true);
    const daysUntilDeadline = getDaysUntil('2026-11-27');

    useEffect(() => {
        loadStats();
    }, []);

    const loadStats = async () => {
        const [complianceResult, readinessResult, uploadsResult] = await Promise.allSettled([
            complianceApi.readiness(),
            tradingPartnersApi.readiness(),
            dscsaApi.epcisList(),
        ]);

        if (complianceResult.status === 'fulfilled') {
            setReadiness(complianceResult.value.data);
        }
        if (readinessResult.status === 'fulfilled') {
            setPartnerReadiness(readinessResult.value.data);
        }
        if (uploadsResult.status === 'fulfilled') {
            setUploads(uploadsResult.value.data ?? []);
        }
        setLoading(false);
    };

    // Active DSCSA alerts come from the compliance readiness API — the
    // single backend source of truth. Enterprise Watchtower alerts are
    // intentionally not counted here.
    const activeAlertCount = readiness?.active_alert_count ?? 0;
    const checks = readiness?.checks ?? [];
    const passedCount = checks.filter(c => c.passed).length;

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Dashboard</h1>
                <p>DSCSA compliance overview for your pharmacy</p>
            </div>

            {/* Compliance Readiness Score */}
            {readiness && (() => {
                const failing = readiness.checks.filter(c => !c.passed);
                const ringColor = readiness.score === 100
                    ? 'var(--success)'
                    : readiness.score >= 50 ? 'var(--warning)' : 'var(--danger)';
                const circumference = 2 * Math.PI * 45;
                return (
                    <div className="card" style={{ marginBottom: 32, display: 'flex', gap: 32, alignItems: 'center', flexWrap: 'wrap' }}>
                        <div style={{ position: 'relative', width: 120, height: 120, flexShrink: 0 }}>
                            <svg width="120" height="120" viewBox="0 0 120 120">
                                <circle
                                    cx="60" cy="60" r="45" fill="none"
                                    stroke="var(--bg-tertiary)" strokeWidth="10"
                                />
                                <circle
                                    cx="60" cy="60" r="45" fill="none"
                                    stroke={ringColor} strokeWidth="10" strokeLinecap="round"
                                    strokeDasharray={circumference}
                                    strokeDashoffset={circumference * (1 - readiness.score / 100)}
                                    transform="rotate(-90 60 60)"
                                    style={{ transition: 'stroke-dashoffset 0.5s ease' }}
                                />
                            </svg>
                            <div style={{
                                position: 'absolute', inset: 0,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                fontSize: 24, fontWeight: 700
                            }}>
                                {readiness.score}%
                            </div>
                        </div>
                        <div style={{ flex: 1, minWidth: 260 }}>
                            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 4 }}>Compliance Readiness</h2>
                            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
                                {failing.length === 0
                                    ? 'All readiness checks passed.'
                                    : `${failing.length} item${failing.length > 1 ? 's' : ''} to complete:`}
                            </p>
                            {failing.map(check => (
                                <div key={check.id} style={{
                                    display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 0',
                                    borderTop: '1px solid var(--border-color)'
                                }}>
                                    <Circle size={16} style={{ color: 'var(--text-muted)', flexShrink: 0, marginTop: 2 }} />
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: 14 }}>{check.label}</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{check.detail}</div>
                                    </div>
                                    <Link to={readinessCheckActions[check.id] ?? '/dashboard'} style={{
                                        fontSize: 12, color: 'var(--accent-primary)',
                                        display: 'flex', alignItems: 'center', gap: 4,
                                        textDecoration: 'none', whiteSpace: 'nowrap', marginTop: 2
                                    }}>
                                        Fix <ArrowRight size={12} />
                                    </Link>
                                </div>
                            ))}
                        </div>
                    </div>
                );
            })()}

            {/* Metric Cards */}
            <div className="grid grid-4" style={{ marginBottom: 32 }}>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Building2 size={24} />
                    </div>
                    <div className="content">
                        <h3>Trading Partners</h3>
                        <div className="value">{partnerReadiness.total_trading_partners}</div>
                        {partnerReadiness.total_trading_partners > 0 && (
                            <div style={{ fontSize: 11, color: '#10b981', marginTop: 2 }}>
                                {partnerReadiness.verified_partners} verified
                            </div>
                        )}
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
                {/* DSCSA Readiness Checklist — rendered entirely from the
                    backend readiness response; nothing is recomputed here */}
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>DSCSA Readiness Checklist</h2>
                        {readiness && (
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '6px 14px', borderRadius: 20,
                                background: readiness.score === 100 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                                color: readiness.score === 100 ? '#10b981' : '#f59e0b',
                                fontWeight: 700, fontSize: 14
                            }}>
                                {readiness.score}% Ready
                            </div>
                        )}
                    </div>

                    {readiness ? (
                        <>
                            <div style={{ marginBottom: 16 }}>
                                <div style={{ height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden', marginBottom: 8 }}>
                                    <div style={{
                                        width: `${readiness.score}%`, height: '100%', borderRadius: 4,
                                        background: readiness.score === 100
                                            ? 'var(--success)'
                                            : readiness.score >= 60
                                                ? 'var(--warning)'
                                                : 'var(--accent-primary)',
                                        transition: 'width 0.5s ease'
                                    }} />
                                </div>
                                <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                    {passedCount} of {checks.length} operational checks passed.
                                    Operational readiness — not a legal compliance guarantee.
                                </p>
                            </div>

                            {checks.map((check, idx) => (
                                <div key={check.id} style={{
                                    display: 'flex', alignItems: 'center', gap: 12,
                                    padding: '12px 0',
                                    borderBottom: idx < checks.length - 1 ? '1px solid var(--border-color)' : 'none'
                                }}>
                                    {check.passed
                                        ? <CheckCircle size={20} style={{ color: 'var(--success)', flexShrink: 0 }} />
                                        : <Circle size={20} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                                    }
                                    <div style={{ flex: 1 }}>
                                        <div style={{
                                            fontSize: 14,
                                            color: check.passed ? 'var(--text-primary)' : 'var(--text-secondary)'
                                        }}>
                                            {check.label}
                                        </div>
                                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{check.detail}</div>
                                    </div>
                                    {!check.passed && (
                                        <Link to={readinessCheckActions[check.id] ?? '/dashboard'} style={{
                                            fontSize: 12, color: 'var(--accent-primary)',
                                            display: 'flex', alignItems: 'center', gap: 4,
                                            textDecoration: 'none', whiteSpace: 'nowrap'
                                        }}>
                                            {readinessCheckActionLabels[check.id] ?? 'Fix'} <ArrowRight size={12} />
                                        </Link>
                                    )}
                                </div>
                            ))}
                        </>
                    ) : (
                        <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                            Readiness data is unavailable right now. Refresh to try again.
                        </p>
                    )}
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
