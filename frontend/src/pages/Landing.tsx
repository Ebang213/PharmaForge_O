import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../App';
import { Shield, FileCheck, Building2, Package, ArrowRight } from 'lucide-react';
import './Login.css';

const featureCards = [
    { icon: FileCheck, title: 'Receive & validate EPCIS files' },
    { icon: Building2, title: 'Track trading partner licenses' },
    { icon: Package, title: 'One-click audit packets' },
];

export default function Landing() {
    const { isAuthenticated } = useAuth();

    if (isAuthenticated) {
        return <Navigate to="/dashboard" replace />;
    }

    return (
        <div className="login-page" style={{ alignItems: 'flex-start', paddingTop: 64 }}>
            <div className="login-bg" />
            <div style={{ width: '100%', maxWidth: 880, margin: '0 auto', animation: 'fadeIn 0.4s ease' }}>
                {/* Header / hero */}
                <div className="login-header">
                    <div className="login-logo">
                        <Shield size={40} />
                    </div>
                    <h1 style={{ fontSize: 36, lineHeight: 1.25 }}>
                        DSCSA compliance for independent pharmacies. Ready before November 27.
                    </h1>
                    <p style={{ maxWidth: 640, margin: '0 auto' }}>
                        Your small-dispenser exemption ends November 27, 2026. PharmaForge receives,
                        validates, and stores your EPCIS data so you can prove compliance.
                    </p>
                </div>

                {/* Feature cards */}
                <div className="grid grid-3" style={{ marginBottom: 32 }}>
                    {featureCards.map(({ icon: Icon, title }) => (
                        <div key={title} className="card" style={{ textAlign: 'center', padding: 28 }}>
                            <div style={{
                                width: 48, height: 48, margin: '0 auto 16px',
                                background: 'rgba(99, 102, 241, 0.15)', borderRadius: 12,
                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                            }}>
                                <Icon size={24} style={{ color: 'var(--accent-primary)' }} />
                            </div>
                            <h3 style={{ fontSize: 16, fontWeight: 600 }}>{title}</h3>
                        </div>
                    ))}
                </div>

                {/* Pricing */}
                <div className="card" style={{ textAlign: 'center', padding: 32, marginBottom: 32 }}>
                    <div style={{ fontSize: 40, fontWeight: 700 }}>
                        $149<span style={{ fontSize: 18, fontWeight: 500, color: 'var(--text-secondary)' }}>/month</span>
                    </div>
                    <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
                        No setup fee. Cancel anytime. Free 60-day pilot.
                    </p>
                </div>

                {/* CTAs */}
                <div style={{ display: 'flex', gap: 16, justifyContent: 'center', paddingBottom: 64 }}>
                    <Link to="/register" className="btn btn-primary" style={{ padding: '14px 28px', fontSize: 15, textDecoration: 'none' }}>
                        Register <ArrowRight size={18} />
                    </Link>
                    <Link to="/login" className="btn btn-secondary" style={{ padding: '14px 28px', fontSize: 15, textDecoration: 'none' }}>
                        Login
                    </Link>
                </div>
            </div>
        </div>
    );
}
