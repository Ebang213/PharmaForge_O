import { useState, useEffect } from 'react';
import { sourcingApi, vendorsApi } from '../lib/api';
import { ShoppingCart, Plus, FileText, Send, Check, Award, BarChart3, X } from 'lucide-react';
import type { RFQ, Vendor, Scorecard } from '../lib/types';

export default function Sourcing() {
    const [rfqs, setRfqs] = useState<RFQ[]>([]);
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [loading, setLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedRfq, setSelectedRfq] = useState<any>(null);
    const [comparison, setComparison] = useState<any>(null);
    const [formData, setFormData] = useState({
        title: '', item_type: 'API', item_description: '', quantity: 0, quantity_unit: 'kg',
        delivery_location: '', target_date: '', vendor_ids: [] as number[]
    });

    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        try {
            const [rfqRes, vendorRes] = await Promise.all([sourcingApi.listRfqs(), vendorsApi.list()]);
            setRfqs(rfqRes.data);
            setVendors(vendorRes.data.items || []);
        } catch (error) {
            console.error('Failed to load data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await sourcingApi.createRfq({ ...formData, quantity: Number(formData.quantity) });
            setShowCreateModal(false);
            await loadData();
        } catch (error) {
            console.error('Create failed:', error);
        }
    };

    const handleViewRfq = async (id: number) => {
        try {
            const res = await sourcingApi.getRfq(id);
            setSelectedRfq(res.data);
            setComparison(null);
        } catch (error) {
            console.error('Failed to load RFQ:', error);
        }
    };

    const handleGenerateDrafts = async (rfqId: number) => {
        try {
            await sourcingApi.generateDrafts(rfqId);
            await handleViewRfq(rfqId);
        } catch (error) {
            console.error('Generate drafts failed:', error);
        }
    };

    const handleCompare = async (rfqId: number) => {
        try {
            const res = await sourcingApi.compare(rfqId);
            setComparison(res.data);
        } catch (error) {
            console.error('Compare failed:', error);
        }
    };

    const handleAward = async (rfqId: number, vendorId: number) => {
        if (!confirm('Award this RFQ to the selected vendor?')) return;
        try {
            await sourcingApi.award(rfqId, vendorId);
            await handleViewRfq(rfqId);
            await loadData();
        } catch (error) {
            console.error('Award failed:', error);
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, string> = {
            draft: 'badge badge-info', pending_approval: 'badge badge-warning',
            sent: 'badge badge-info', quotes_received: 'badge badge-warning',
            evaluating: 'badge badge-warning', awarded: 'badge badge-success', closed: 'badge'
        };
        return <span className={colors[status] || 'badge'}>{status.replace('_', ' ').toUpperCase()}</span>;
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Smart Sourcing</h1>
                <p>RFQ management and vendor comparison</p>
            </div>

            <div className="grid" style={{ gridTemplateColumns: '1fr 400px', gap: 24 }}>
                {/* RFQ List */}
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                        <h2 style={{ fontSize: 18, fontWeight: 600 }}>RFQ Requests</h2>
                        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}><Plus size={18} /> New RFQ</button>
                    </div>

                    {rfqs.length === 0 ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <ShoppingCart size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                            <p>No RFQs yet. Create your first request for quote.</p>
                        </div>
                    ) : (
                        <div>
                            {rfqs.map(rfq => (
                                <div key={rfq.id} style={{
                                    padding: 16, borderBottom: '1px solid var(--border-color)', cursor: 'pointer',
                                    background: selectedRfq?.id === rfq.id ? 'var(--bg-tertiary)' : 'transparent'
                                }} onClick={() => handleViewRfq(rfq.id)}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                                        <div>
                                            <span style={{ fontWeight: 500 }}>{rfq.rfq_number}</span>
                                            <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>{rfq.title}</span>
                                        </div>
                                        {getStatusBadge(rfq.status)}
                                    </div>
                                    <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                        {rfq.item_type} • {rfq.quantity} units • {rfq.vendor_count} vendors • {rfq.quote_count} quotes
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* RFQ Details */}
                <div className="card">
                    {!selectedRfq ? (
                        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                            <FileText size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                            <p>Select an RFQ to view details</p>
                        </div>
                    ) : (
                        <div>
                            <div style={{ marginBottom: 20 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <h3>{selectedRfq.rfq_number}</h3>
                                    {getStatusBadge(selectedRfq.status)}
                                </div>
                                <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{selectedRfq.title}</p>
                            </div>

                            <div style={{ background: 'var(--bg-tertiary)', padding: 16, borderRadius: 8, marginBottom: 16 }}>
                                <div className="grid grid-2" style={{ gap: 12, fontSize: 13 }}>
                                    <div><span style={{ color: 'var(--text-muted)' }}>Type:</span> {selectedRfq.item_type}</div>
                                    <div><span style={{ color: 'var(--text-muted)' }}>Quantity:</span> {selectedRfq.quantity}</div>
                                    <div><span style={{ color: 'var(--text-muted)' }}>Vendors:</span> {selectedRfq.vendors?.length || 0}</div>
                                    <div><span style={{ color: 'var(--text-muted)' }}>Quotes:</span> {selectedRfq.quotes?.length || 0}</div>
                                </div>
                            </div>

                            {/* Actions */}
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
                                {selectedRfq.status === 'draft' && (
                                    <button className="btn btn-secondary" onClick={() => handleGenerateDrafts(selectedRfq.id)}>
                                        <Send size={16} /> Generate Drafts
                                    </button>
                                )}
                                {selectedRfq.quotes?.length > 0 && (
                                    <button className="btn btn-secondary" onClick={() => handleCompare(selectedRfq.id)}>
                                        <BarChart3 size={16} /> Compare
                                    </button>
                                )}
                            </div>

                            {/* Comparison Results */}
                            {comparison && (
                                <div style={{ marginBottom: 20 }}>
                                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Vendor Comparison</h4>
                                    {comparison.scorecards?.map((sc: Scorecard) => (
                                        <div key={sc.vendor_id} style={{
                                            padding: 12, background: sc.is_recommended ? 'rgba(34, 197, 94, 0.1)' : 'var(--bg-tertiary)',
                                            borderRadius: 8, marginBottom: 8, border: sc.is_recommended ? '1px solid var(--success)' : 'none'
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                                                <div style={{ fontWeight: 500 }}>{sc.vendor_name}</div>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                    <span style={{ fontSize: 18, fontWeight: 700 }}>{sc.overall_score.toFixed(0)}</span>
                                                    {sc.is_recommended && <span className="badge badge-success"><Check size={12} /> Recommended</span>}
                                                </div>
                                            </div>
                                            <div className="grid grid-4" style={{ gap: 8, fontSize: 11 }}>
                                                <div>Price: {sc.price_score.toFixed(0)}</div>
                                                <div>Lead: {sc.lead_time_score.toFixed(0)}</div>
                                                <div>Compliance: {sc.compliance_score.toFixed(0)}</div>
                                            </div>
                                            {selectedRfq.status !== 'awarded' && (
                                                <button className="btn btn-primary" style={{ marginTop: 12, width: '100%', padding: '8px 12px' }}
                                                    onClick={() => handleAward(selectedRfq.id, sc.vendor_id)}>
                                                    <Award size={16} /> Award to {sc.vendor_name}
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Messages */}
                            {selectedRfq.messages?.length > 0 && (
                                <div>
                                    <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Messages</h4>
                                    {selectedRfq.messages.map((msg: any) => (
                                        <div key={msg.id} style={{ padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8, marginBottom: 8 }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                                                <span style={{ fontWeight: 500, fontSize: 13 }}>{msg.subject}</span>
                                                <span className={`badge badge-${msg.status === 'sent' ? 'success' : msg.status === 'approved' ? 'info' : 'warning'}`} style={{ fontSize: 10 }}>
                                                    {msg.status}
                                                </span>
                                            </div>
                                            <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>{msg.recipient_email}</p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
                    <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 600 }}>
                        <div className="modal-header">
                            <h2>Create RFQ</h2>
                            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => setShowCreateModal(false)}><X size={18} /></button>
                        </div>
                        <form onSubmit={handleCreate}>
                            <div className="form-group">
                                <label>Title *</label>
                                <input type="text" value={formData.title} onChange={(e) => setFormData({ ...formData, title: e.target.value })} required />
                            </div>
                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group">
                                    <label>Item Type *</label>
                                    <select value={formData.item_type} onChange={(e) => setFormData({ ...formData, item_type: e.target.value })}>
                                        <option value="API">API</option>
                                        <option value="Excipient">Excipient</option>
                                        <option value="Packaging">Packaging</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label>Quantity *</label>
                                    <input type="number" value={formData.quantity} onChange={(e) => setFormData({ ...formData, quantity: Number(e.target.value) })} required />
                                </div>
                            </div>
                            <div className="form-group">
                                <label>Description *</label>
                                <textarea value={formData.item_description} onChange={(e) => setFormData({ ...formData, item_description: e.target.value })} rows={3} required />
                            </div>
                            <div className="form-group">
                                <label>Select Vendors</label>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                    {vendors.slice(0, 8).map(v => (
                                        <button key={v.id} type="button"
                                            className={`btn ${formData.vendor_ids.includes(v.id) ? 'btn-primary' : 'btn-secondary'}`}
                                            style={{ padding: '6px 12px', fontSize: 13 }}
                                            onClick={() => setFormData(prev => ({
                                                ...prev, vendor_ids: prev.vendor_ids.includes(v.id) ? prev.vendor_ids.filter(id => id !== v.id) : [...prev.vendor_ids, v.id]
                                            }))}>
                                            {v.name}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                                <button type="submit" className="btn btn-primary">Create RFQ</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
