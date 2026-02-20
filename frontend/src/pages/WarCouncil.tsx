import { useState } from 'react';
import { warCouncilApi, vendorsApi } from '../lib/api';
import { Users, Send, Scale, Truck, Gavel, Zap } from 'lucide-react';
import type { WarCouncilResult, PersonaResponse, Vendor } from '../lib/types';
import { useEffect } from 'react';

export default function WarCouncil() {
    const [question, setQuestion] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<WarCouncilResult | null>(null);
    const [vendors, setVendors] = useState<Vendor[]>([]);
    const [selectedVendors, setSelectedVendors] = useState<number[]>([]);

    useEffect(() => {
        vendorsApi.list().then(res => setVendors(res.data.items || [])).catch(console.error);
    }, []);

    const handleSubmit = async () => {
        if (!question.trim()) return;

        setLoading(true);
        try {
            const res = await warCouncilApi.query(question, selectedVendors.length > 0 ? selectedVendors : undefined);
            setResult(res.data);
        } catch (error) {
            console.error('Query failed:', error);
        } finally {
            setLoading(false);
        }
    };

    const getRiskColor = (level: string) => {
        switch (level) {
            case 'critical': return 'var(--danger)';
            case 'high': return 'var(--warning)';
            case 'medium': return 'var(--info)';
            default: return 'var(--success)';
        }
    };

    const PersonaCard = ({ persona, icon: Icon, color }: { persona: PersonaResponse; icon: any; color: string }) => (
        <div className="card" style={{ borderTop: `3px solid ${color}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{ width: 40, height: 40, borderRadius: 8, background: `${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon size={20} style={{ color }} />
                </div>
                <div>
                    <h3 style={{ fontSize: 16, fontWeight: 600 }}>{persona.persona}</h3>
                    <span className={`badge badge-${persona.risk_level === 'high' ? 'danger' : persona.risk_level === 'medium' ? 'warning' : 'success'}`}>
                        {persona.risk_level.toUpperCase()} RISK
                    </span>
                </div>
            </div>

            <p style={{ color: 'var(--text-secondary)', marginBottom: 16, lineHeight: 1.7 }}>{persona.response}</p>

            <div style={{ marginBottom: 16 }}>
                <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>KEY POINTS</h4>
                <ul style={{ paddingLeft: 16, color: 'var(--text-secondary)', fontSize: 14 }}>
                    {persona.key_points.map((point, i) => <li key={i} style={{ marginBottom: 4 }}>{point}</li>)}
                </ul>
            </div>

            <div>
                <h4 style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8 }}>RECOMMENDED ACTIONS</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {persona.recommended_actions.map((action, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
                            <Zap size={14} style={{ color }} />
                            {action}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>War Council</h1>
                <p>Multi-persona strategic analysis for complex decisions</p>
            </div>

            {/* Query Input */}
            <div className="card" style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
                    <div style={{
                        width: 56, height: 56, background: 'var(--accent-gradient)', borderRadius: 12,
                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                        <Users size={28} color="white" />
                    </div>
                    <div>
                        <h3 style={{ marginBottom: 4 }}>Convene the Council</h3>
                        <p style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                            Get perspectives from Regulatory, Supply Chain, and Legal experts
                        </p>
                    </div>
                </div>

                <div style={{ marginBottom: 16 }}>
                    <label style={{ display: 'block', marginBottom: 8, color: 'var(--text-secondary)', fontSize: 14 }}>
                        Context: Related Vendors (optional)
                    </label>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {vendors.slice(0, 6).map(v => (
                            <button
                                key={v.id}
                                className={`btn ${selectedVendors.includes(v.id) ? 'btn-primary' : 'btn-secondary'}`}
                                style={{ padding: '6px 12px', fontSize: 13 }}
                                onClick={() => setSelectedVendors(prev =>
                                    prev.includes(v.id) ? prev.filter(id => id !== v.id) : [...prev, v.id]
                                )}
                            >
                                {v.name}
                            </button>
                        ))}
                    </div>
                </div>

                <div style={{ display: 'flex', gap: 12 }}>
                    <textarea
                        placeholder="Describe the situation for strategic analysis..."
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        rows={3}
                        style={{ flex: 1, resize: 'none' }}
                    />
                    <button className="btn btn-primary" onClick={handleSubmit} disabled={loading || !question.trim()} style={{ alignSelf: 'flex-end' }}>
                        {loading ? 'Analyzing...' : <><Send size={18} /> Analyze</>}
                    </button>
                </div>
            </div>

            {/* Results */}
            {result && (
                <div className="fade-in">
                    {/* Synthesis */}
                    <div className="card" style={{ marginBottom: 24, background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <h3 style={{ fontSize: 18, fontWeight: 600 }}>Strategic Synthesis</h3>
                            <span className="badge" style={{ background: getRiskColor(result.overall_risk), color: 'white' }}>
                                Overall: {result.overall_risk.toUpperCase()} RISK
                            </span>
                        </div>
                        <p style={{ lineHeight: 1.8, marginBottom: 20 }}>{result.synthesis}</p>

                        <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Priority Actions</h4>
                        <div className="grid grid-2" style={{ gap: 12 }}>
                            {result.priority_actions.map((action, i) => (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'center', gap: 12, padding: 12,
                                    background: 'var(--bg-card)', borderRadius: 8
                                }}>
                                    <span style={{
                                        width: 24, height: 24, borderRadius: '50%', background: 'var(--accent-gradient)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600
                                    }}>{i + 1}</span>
                                    <span style={{ fontSize: 14 }}>{action}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Persona Responses */}
                    <div className="grid grid-3">
                        <PersonaCard persona={result.regulatory} icon={Scale} color="#6366f1" />
                        <PersonaCard persona={result.supply_chain} icon={Truck} color="#f59e0b" />
                        <PersonaCard persona={result.legal} icon={Gavel} color="#8b5cf6" />
                    </div>
                </div>
            )}
        </div>
    );
}
