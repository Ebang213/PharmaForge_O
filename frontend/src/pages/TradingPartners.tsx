import { useState, useEffect } from 'react';
import { tradingPartnersApi } from '../lib/api';
import {
    Building2, Plus, Edit, Trash2, MapPin, CheckCircle,
    AlertTriangle, X, ChevronDown, ChevronUp, RefreshCw
} from 'lucide-react';
import type { TradingPartner } from '../lib/types';

const PARTNER_TYPES = [
    { value: 'MANUFACTURER', label: 'Manufacturer' },
    { value: 'WHOLESALE_DISTRIBUTOR', label: 'Wholesale Distributor' },
    { value: 'DISPENSER', label: 'Dispenser' },
    { value: 'REPACKAGER', label: 'Repackager' },
    { value: 'THIRD_PARTY_LOGISTICS', label: 'Third-Party Logistics (3PL)' },
    { value: 'OTHER', label: 'Other' },
];

const STATUSES = [
    { value: 'active', label: 'Active' },
    { value: 'pending_review', label: 'Pending Review' },
    { value: 'inactive', label: 'Inactive' },
];

const EMPTY_FORM = {
    name: '',
    partner_type: '',
    status: 'active',
    gln: '',
    dea_number: '',
    state_license_number: '',
    state: '',
    country: 'US',
    contact_name: '',
    contact_email: '',
    phone: '',
    address: '',
    notes: '',
};

function VerificationBadge({ status, missingFields }: { status: string; missingFields: string[] }) {
    if (status === 'verified') {
        return (
            <span style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                background: 'rgba(16, 185, 129, 0.15)', color: '#10b981'
            }}>
                <CheckCircle size={12} /> Verified
            </span>
        );
    }
    return (
        <span
            title={missingFields.length ? `Missing: ${missingFields.join(', ')}` : undefined}
            style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
                background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b',
                cursor: missingFields.length ? 'help' : 'default',
            }}
        >
            <AlertTriangle size={12} /> Incomplete
        </span>
    );
}

function DemoSourceBadge() {
    return (
        <span
            title="This row was created by demo seeding and should be removed via cleanup script"
            style={{
                display: 'inline-flex', alignItems: 'center', gap: 4,
                padding: '2px 7px', borderRadius: 10, fontSize: 11, fontWeight: 600,
                background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8',
                marginLeft: 6, verticalAlign: 'middle',
            }}
        >
            Demo
        </span>
    );
}

function StatusBadge({ status }: { status: string }) {
    const map: Record<string, { label: string; color: string; bg: string }> = {
        active: { label: 'Active', color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' },
        pending_review: { label: 'Pending Review', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' },
        inactive: { label: 'Inactive', color: '#6b7280', bg: 'rgba(107, 114, 128, 0.12)' },
    };
    const cfg = map[status] ?? map.inactive;
    return (
        <span style={{
            padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600,
            background: cfg.bg, color: cfg.color
        }}>
            {cfg.label}
        </span>
    );
}

export default function TradingPartners() {
    const [partners, setPartners] = useState<TradingPartner[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [formError, setFormError] = useState<string | null>(null);
    const [showModal, setShowModal] = useState(false);
    const [editing, setEditing] = useState<TradingPartner | null>(null);
    const [filter, setFilter] = useState('');
    const [expandedId, setExpandedId] = useState<number | null>(null);
    const [formData, setFormData] = useState({ ...EMPTY_FORM });
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadPartners();
    }, []);

    const loadPartners = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await tradingPartnersApi.list();
            setPartners(res.data.items ?? []);
        } catch (err: unknown) {
            const msg = extractErrorMessage(err, 'Failed to load trading partners.');
            setError(msg);
        } finally {
            setLoading(false);
        }
    };

    const extractErrorMessage = (err: unknown, fallback: string): string => {
        if (err && typeof err === 'object' && 'response' in err) {
            const axErr = err as { response?: { data?: { detail?: string | { msg: string }[] } } };
            const detail = axErr.response?.data?.detail;
            if (typeof detail === 'string') return detail;
            if (Array.isArray(detail)) return detail.map(d => d.msg).join('; ');
        }
        return fallback;
    };

    const openCreate = () => {
        setEditing(null);
        setFormData({ ...EMPTY_FORM });
        setFormError(null);
        setShowModal(true);
    };

    const openEdit = (p: TradingPartner) => {
        setEditing(p);
        setFormData({
            name: p.name,
            partner_type: p.partner_type ?? '',
            status: p.status,
            gln: p.gln ?? '',
            dea_number: p.dea_number ?? '',
            state_license_number: p.state_license_number ?? '',
            state: p.state ?? '',
            country: p.country ?? 'US',
            contact_name: p.contact_name ?? '',
            contact_email: p.contact_email ?? '',
            phone: p.phone ?? '',
            address: p.address ?? '',
            notes: p.notes ?? '',
        });
        setFormError(null);
        setShowModal(true);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        setFormError(null);

        const payload = {
            name: formData.name.trim(),
            partner_type: formData.partner_type || undefined,
            status: formData.status,
            gln: formData.gln.trim() || undefined,
            dea_number: formData.dea_number.trim() || undefined,
            state_license_number: formData.state_license_number.trim() || undefined,
            state: formData.state.trim() || undefined,
            country: formData.country.trim() || undefined,
            contact_name: formData.contact_name.trim() || undefined,
            contact_email: formData.contact_email.trim() || undefined,
            phone: formData.phone.trim() || undefined,
            address: formData.address.trim() || undefined,
            notes: formData.notes.trim() || undefined,
        };

        try {
            if (editing) {
                await tradingPartnersApi.update(editing.id, payload);
            } else {
                await tradingPartnersApi.create(payload);
            }
            setShowModal(false);
            await loadPartners();
        } catch (err: unknown) {
            setFormError(extractErrorMessage(err, 'Save failed. Please check your inputs and try again.'));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (p: TradingPartner) => {
        if (!confirm(`Delete trading partner "${p.name}"? This cannot be undone.`)) return;
        try {
            await tradingPartnersApi.delete(p.id);
            await loadPartners();
        } catch (err: unknown) {
            setError(extractErrorMessage(err, 'Delete failed.'));
        }
    };

    const set = (field: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
        setFormData(prev => ({ ...prev, [field]: e.target.value }));

    const filtered = partners.filter(p =>
        !filter || p.name.toLowerCase().includes(filter.toLowerCase()) ||
        (p.contact_email ?? '').toLowerCase().includes(filter.toLowerCase())
    );

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Trading Partners</h1>
                <p>Manage licensed wholesalers, distributors, and supply chain partners for DSCSA traceability</p>
            </div>

            {error && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 16px', borderRadius: 8, marginBottom: 20,
                    background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                    color: '#ef4444'
                }}>
                    <AlertTriangle size={16} style={{ flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 14 }}>{error}</span>
                    <button
                        onClick={loadPartners}
                        style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 13 }}
                    >
                        <RefreshCw size={14} /> Retry
                    </button>
                </div>
            )}

            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, gap: 12 }}>
                    <input
                        type="text"
                        placeholder="Search by name or email..."
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                        style={{ width: 300 }}
                    />
                    <button className="btn btn-primary" onClick={openCreate} style={{ display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}>
                        <Plus size={18} /> Add Trading Partner
                    </button>
                </div>

                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Partner</th>
                            <th>Type</th>
                            <th>Location</th>
                            <th>Identifiers</th>
                            <th>Status</th>
                            <th>Verification</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map(p => (
                            <>
                                <tr key={p.id}>
                                    <td>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                            <div style={{
                                                width: 38, height: 38, borderRadius: 8,
                                                background: 'var(--bg-tertiary)',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0
                                            }}>
                                                <Building2 size={18} style={{ color: 'var(--accent-primary)' }} />
                                            </div>
                                            <div>
                                                <div style={{ fontWeight: 500, fontSize: 14 }}>
                                                    {p.name}
                                                    {p.data_source === 'demo' && <DemoSourceBadge />}
                                                </div>
                                                {p.contact_email && (
                                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{p.contact_email}</div>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                                        {p.partner_type ? PARTNER_TYPES.find(t => t.value === p.partner_type)?.label ?? p.partner_type : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                    </td>
                                    <td style={{ fontSize: 13 }}>
                                        {(p.state || p.country) ? (
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-secondary)' }}>
                                                <MapPin size={12} />
                                                {[p.state, p.country].filter(Boolean).join(', ')}
                                            </div>
                                        ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                                    </td>
                                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                                            {p.gln && <span>GLN: {p.gln}</span>}
                                            {p.dea_number && <span>DEA: {p.dea_number}</span>}
                                            {p.state_license_number && <span>Lic: {p.state_license_number}</span>}
                                            {!p.gln && !p.dea_number && !p.state_license_number && (
                                                <span style={{ color: 'var(--text-muted)' }}>None on file</span>
                                            )}
                                        </div>
                                    </td>
                                    <td><StatusBadge status={p.status} /></td>
                                    <td>
                                        <div>
                                            <VerificationBadge status={p.verification_status} missingFields={p.missing_fields} />
                                            {p.missing_fields.length > 0 && (
                                                <button
                                                    onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                                                    style={{ display: 'flex', alignItems: 'center', gap: 2, marginTop: 4, background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}
                                                >
                                                    {expandedId === p.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                                    {p.missing_fields.length} missing
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                    <td>
                                        <div style={{ display: 'flex', gap: 8 }}>
                                            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => openEdit(p)} title="Edit">
                                                <Edit size={15} />
                                            </button>
                                            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => handleDelete(p)} title="Delete">
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {expandedId === p.id && p.missing_fields.length > 0 && (
                                    <tr key={`${p.id}-expand`}>
                                        <td colSpan={7} style={{ padding: '8px 16px 16px 68px', background: 'rgba(245, 158, 11, 0.05)' }}>
                                            <div style={{ fontSize: 12, color: '#f59e0b' }}>
                                                <strong>Missing for DSCSA verification:</strong>{' '}
                                                {p.missing_fields.join(' · ')}
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </>
                        ))}
                        {filtered.length === 0 && (
                            <tr>
                                <td colSpan={7} style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-muted)' }}>
                                    <Building2 size={40} style={{ marginBottom: 12, opacity: 0.25, display: 'block', margin: '0 auto 12px' }} />
                                    {filter
                                        ? <p>No partners match your search.</p>
                                        : <p>No trading partners yet. Add your first wholesaler or distributor.</p>
                                    }
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {showModal && (
                <div className="modal-overlay" onClick={() => !saving && setShowModal(false)}>
                    <div className="modal" style={{ maxWidth: 640, width: '100%' }} onClick={e => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editing ? 'Edit Trading Partner' : 'Add Trading Partner'}</h2>
                            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => setShowModal(false)} disabled={saving}>
                                <X size={18} />
                            </button>
                        </div>

                        {formError && (
                            <div style={{
                                display: 'flex', alignItems: 'flex-start', gap: 10,
                                padding: '10px 14px', borderRadius: 6, marginBottom: 16,
                                background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)',
                                color: '#ef4444', fontSize: 13
                            }}>
                                <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: 1 }} />
                                {formError}
                            </div>
                        )}

                        <form onSubmit={handleSubmit}>
                            {/* Core identity */}
                            <div className="form-group">
                                <label>Partner Name <span style={{ color: 'var(--danger)' }}>*</span></label>
                                <input type="text" value={formData.name} onChange={set('name')} required placeholder="e.g. AmerisourceBergen Drug Corporation" />
                            </div>

                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group">
                                    <label>Partner Type <span style={{ color: 'var(--danger)' }}>*</span></label>
                                    <select value={formData.partner_type} onChange={set('partner_type')} required>
                                        <option value="">Select type</option>
                                        {PARTNER_TYPES.map(t => (
                                            <option key={t.value} value={t.value}>{t.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Status</label>
                                    <select value={formData.status} onChange={set('status')}>
                                        {STATUSES.map(s => (
                                            <option key={s.value} value={s.value}>{s.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            {/* DSCSA Identifiers */}
                            <div style={{ marginTop: 4, marginBottom: 8 }}>
                                <p style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    DSCSA Identifiers (at least one required for verification)
                                </p>
                            </div>
                            <div className="grid grid-3" style={{ gap: 12 }}>
                                <div className="form-group">
                                    <label>GLN</label>
                                    <input type="text" value={formData.gln} onChange={set('gln')} placeholder="0000000000000" maxLength={13} />
                                </div>
                                <div className="form-group">
                                    <label>DEA Number</label>
                                    <input type="text" value={formData.dea_number} onChange={set('dea_number')} placeholder="AB1234567" />
                                </div>
                                <div className="form-group">
                                    <label>State License #</label>
                                    <input type="text" value={formData.state_license_number} onChange={set('state_license_number')} placeholder="e.g. W12345" />
                                </div>
                            </div>

                            {/* Location */}
                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group">
                                    <label>State</label>
                                    <input type="text" value={formData.state} onChange={set('state')} placeholder="e.g. PA" maxLength={2} />
                                </div>
                                <div className="form-group">
                                    <label>Country</label>
                                    <input type="text" value={formData.country} onChange={set('country')} placeholder="US" maxLength={3} />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Address</label>
                                <input type="text" value={formData.address} onChange={set('address')} placeholder="Street address" />
                            </div>

                            {/* Contact */}
                            <div style={{ marginTop: 4, marginBottom: 8 }}>
                                <p style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    Contact (email or phone required for verification)
                                </p>
                            </div>
                            <div className="grid grid-3" style={{ gap: 12 }}>
                                <div className="form-group">
                                    <label>Contact Name</label>
                                    <input type="text" value={formData.contact_name} onChange={set('contact_name')} placeholder="Full name" />
                                </div>
                                <div className="form-group">
                                    <label>Contact Email</label>
                                    <input type="email" value={formData.contact_email} onChange={set('contact_email')} placeholder="contact@partner.com" />
                                </div>
                                <div className="form-group">
                                    <label>Phone</label>
                                    <input type="tel" value={formData.phone} onChange={set('phone')} placeholder="555-000-0000" />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Notes</label>
                                <textarea
                                    value={formData.notes}
                                    onChange={set('notes')}
                                    placeholder="Additional notes about this trading partner"
                                    rows={2}
                                    style={{ width: '100%', resize: 'vertical' }}
                                />
                            </div>

                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)} disabled={saving}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary" disabled={saving}>
                                    {saving ? 'Saving…' : editing ? 'Save Changes' : 'Add Trading Partner'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
