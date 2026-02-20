import { useState, useEffect } from 'react';
import { vendorsApi } from '../lib/api';
import { Building2, Plus, Edit, Trash2, MapPin, AlertTriangle, Check, X } from 'lucide-react';
import type { Vendor } from '../lib/types';

export default function Vendors() {
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingVendor, setEditingVendor] = useState<Vendor | null>(null);
    const [filter, setFilter] = useState('');
    const [formData, setFormData] = useState({
        name: '', vendor_code: '', vendor_type: '', country: '', contact_email: '', notes: ''
    });

    useEffect(() => {
        loadVendors();
    }, []);

    const loadVendors = async () => {
        try {
            const res = await vendorsApi.list();
            setVendors(res.data.items || []);
        } catch (error) {
            console.error('Failed to load vendors:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingVendor) {
                await vendorsApi.update(editingVendor.id, formData);
            } else {
                await vendorsApi.create(formData);
            }
            setShowModal(false);
            setEditingVendor(null);
            setFormData({ name: '', vendor_code: '', vendor_type: '', country: '', contact_email: '', notes: '' });
            await loadVendors();
        } catch (error) {
            console.error('Save failed:', error);
        }
    };

    const handleEdit = (vendor: Vendor) => {
        setEditingVendor(vendor);
        setFormData({
            name: vendor.name, vendor_code: vendor.vendor_code || '',
            vendor_type: vendor.vendor_type || '', country: vendor.country || '',
            contact_email: vendor.contact_email || '', notes: ''
        });
        setShowModal(true);
    };

    const handleDelete = async (id: number) => {
        if (!confirm('Delete this vendor?')) return;
        try {
            await vendorsApi.delete(id);
            await loadVendors();
        } catch (error) {
            console.error('Delete failed:', error);
        }
    };

    const getRiskBadge = (level: string) => {
        const classes: Record<string, string> = {
            critical: 'badge badge-danger', high: 'badge badge-warning',
            medium: 'badge badge-info', low: 'badge badge-success'
        };
        return <span className={classes[level] || 'badge'}>{level.toUpperCase()}</span>;
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Vendors</h1>
                <p>Manage suppliers, manufacturers, and trading partners</p>
            </div>

            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <input type="text" placeholder="Search vendors..." value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 300 }} />
                    <button className="btn btn-primary" onClick={() => { setEditingVendor(null); setFormData({ name: '', vendor_code: '', vendor_type: '', country: '', contact_email: '', notes: '' }); setShowModal(true); }}>
                        <Plus size={18} /> Add Vendor
                    </button>
                </div>

                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Vendor</th>
                            <th>Type</th>
                            <th>Country</th>
                            <th>Risk</th>
                            <th>Status</th>
                            <th>Alerts</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {vendors.filter(v => !filter || v.name.toLowerCase().includes(filter.toLowerCase())).map(vendor => (
                            <tr key={vendor.id}>
                                <td>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                                        <div style={{ width: 40, height: 40, borderRadius: 8, background: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                            <Building2 size={20} style={{ color: 'var(--accent-primary)' }} />
                                        </div>
                                        <div>
                                            <div style={{ fontWeight: 500 }}>{vendor.name}</div>
                                            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{vendor.vendor_code}</div>
                                        </div>
                                    </div>
                                </td>
                                <td style={{ color: 'var(--text-secondary)' }}>{vendor.vendor_type || '-'}</td>
                                <td><div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><MapPin size={14} /> {vendor.country || '-'}</div></td>
                                <td>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <div style={{ width: 50, height: 4, background: 'var(--bg-tertiary)', borderRadius: 2, overflow: 'hidden' }}>
                                            <div style={{ width: `${vendor.risk_score}%`, height: '100%', background: vendor.risk_score > 50 ? 'var(--danger)' : vendor.risk_score > 25 ? 'var(--warning)' : 'var(--success)' }} />
                                        </div>
                                        {getRiskBadge(vendor.risk_level)}
                                    </div>
                                </td>
                                <td>{vendor.is_approved ? <span className="badge badge-success"><Check size={12} /> Approved</span> : <span className="badge badge-warning">Pending</span>}</td>
                                <td>{vendor.alert_count > 0 && <span className="badge badge-danger"><AlertTriangle size={12} /> {vendor.alert_count}</span>}</td>
                                <td>
                                    <div style={{ display: 'flex', gap: 8 }}>
                                        <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => handleEdit(vendor)}><Edit size={16} /></button>
                                        <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => handleDelete(vendor.id)}><Trash2 size={16} /></button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {showModal && (
                <div className="modal-overlay" onClick={() => setShowModal(false)}>
                    <div className="modal" onClick={(e) => e.stopPropagation()}>
                        <div className="modal-header">
                            <h2>{editingVendor ? 'Edit Vendor' : 'Add Vendor'}</h2>
                            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => setShowModal(false)}><X size={18} /></button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div className="form-group">
                                <label>Vendor Name *</label>
                                <input type="text" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} required />
                            </div>
                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group">
                                    <label>Vendor Code</label>
                                    <input type="text" value={formData.vendor_code} onChange={(e) => setFormData({ ...formData, vendor_code: e.target.value })} />
                                </div>
                                <div className="form-group">
                                    <label>Type</label>
                                    <select value={formData.vendor_type} onChange={(e) => setFormData({ ...formData, vendor_type: e.target.value })}>
                                        <option value="">Select type</option>
                                        <option value="API supplier">API Supplier</option>
                                        <option value="Excipient">Excipient</option>
                                        <option value="Packaging">Packaging</option>
                                        <option value="CMO">CMO</option>
                                    </select>
                                </div>
                            </div>
                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group">
                                    <label>Country</label>
                                    <input type="text" value={formData.country} onChange={(e) => setFormData({ ...formData, country: e.target.value })} />
                                </div>
                                <div className="form-group">
                                    <label>Contact Email</label>
                                    <input type="email" value={formData.contact_email} onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Cancel</button>
                                <button type="submit" className="btn btn-primary">Save Vendor</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
