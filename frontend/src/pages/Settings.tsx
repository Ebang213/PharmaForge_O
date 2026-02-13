import { useState, useEffect } from 'react';
import { useAuth } from '../App';
import api from '../lib/api';
import { User, Building2, Key, Bell, Save, Check } from 'lucide-react';

export default function Settings() {
    const { user } = useAuth();
    const [org, setOrg] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [passwordData, setPasswordData] = useState({ current_password: '', new_password: '', confirm_password: '' });
    const [passwordError, setPasswordError] = useState('');

    useEffect(() => {
        loadOrg();
    }, []);

    const loadOrg = async () => {
        try {
            const res = await api.get('/api/orgs/current');
            setOrg(res.data);
        } catch (error) {
            console.error('Failed to load org:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleSaveOrg = async () => {
        setSaving(true);
        try {
            await api.put('/api/orgs/current', { name: org.name, settings: org.settings });
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
        } catch (error) {
            console.error('Save failed:', error);
        } finally {
            setSaving(false);
        }
    };

    const handleChangePassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setPasswordError('');

        if (passwordData.new_password !== passwordData.confirm_password) {
            setPasswordError('Passwords do not match');
            return;
        }

        try {
            await api.post('/api/auth/change-password', {
                current_password: passwordData.current_password,
                new_password: passwordData.new_password
            });
            setPasswordData({ current_password: '', new_password: '', confirm_password: '' });
            alert('Password changed successfully');
        } catch (error: any) {
            setPasswordError(error.response?.data?.detail || 'Failed to change password');
        }
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Settings</h1>
                <p>Manage your account and organization settings</p>
            </div>

            <div className="grid grid-2" style={{ gap: 24 }}>
                {/* Profile Settings */}
                <div className="card">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
                        <div style={{
                            width: 64, height: 64, borderRadius: '50%', background: 'var(--accent-gradient)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 600
                        }}>
                            {user?.full_name?.charAt(0) || 'U'}
                        </div>
                        <div>
                            <h2 style={{ fontSize: 20, fontWeight: 600 }}>{user?.full_name}</h2>
                            <p style={{ color: 'var(--text-secondary)' }}>{user?.email}</p>
                            <span className="badge badge-info" style={{ marginTop: 8 }}>{user?.role?.toUpperCase()}</span>
                        </div>
                    </div>

                    <div style={{ padding: 16, background: 'var(--bg-tertiary)', borderRadius: 8 }}>
                        <h4 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <User size={16} /> Account Info
                        </h4>
                        <div className="grid grid-2" style={{ gap: 12, fontSize: 14 }}>
                            <div><span style={{ color: 'var(--text-muted)' }}>Email:</span> {user?.email}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>Role:</span> {user?.role}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>Org ID:</span> {user?.organization_id}</div>
                            <div><span style={{ color: 'var(--text-muted)' }}>Org:</span> {user?.organization_name}</div>
                        </div>
                    </div>
                </div>

                {/* Organization Settings */}
                <div className="card">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
                        <Building2 size={20} /> Organization Settings
                    </h3>

                    <div className="form-group">
                        <label>Organization Name</label>
                        <input
                            type="text"
                            value={org?.name || ''}
                            onChange={(e) => setOrg({ ...org, name: e.target.value })}
                        />
                    </div>

                    <div className="form-group">
                        <label>Slug</label>
                        <input type="text" value={org?.slug || ''} disabled style={{ opacity: 0.6 }} />
                    </div>

                    <button className="btn btn-primary" onClick={handleSaveOrg} disabled={saving} style={{ width: '100%' }}>
                        {saved ? <><Check size={18} /> Saved!</> : saving ? 'Saving...' : <><Save size={18} /> Save Changes</>}
                    </button>
                </div>

                {/* Change Password */}
                <div className="card">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
                        <Key size={20} /> Change Password
                    </h3>

                    <form onSubmit={handleChangePassword}>
                        {passwordError && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: 'var(--danger)', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
                                {passwordError}
                            </div>
                        )}

                        <div className="form-group">
                            <label>Current Password</label>
                            <input
                                type="password"
                                value={passwordData.current_password}
                                onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })}
                                required
                            />
                        </div>

                        <div className="form-group">
                            <label>New Password</label>
                            <input
                                type="password"
                                value={passwordData.new_password}
                                onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })}
                                required
                            />
                        </div>

                        <div className="form-group">
                            <label>Confirm New Password</label>
                            <input
                                type="password"
                                value={passwordData.confirm_password}
                                onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })}
                                required
                            />
                        </div>

                        <button type="submit" className="btn btn-secondary" style={{ width: '100%' }}>
                            Update Password
                        </button>
                    </form>
                </div>

                {/* Notification Settings */}
                <div className="card">
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
                        <Bell size={20} /> Notification Preferences
                    </h3>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                        {[
                            { label: 'Watchtower Alerts', desc: 'Get notified about supply chain events' },
                            { label: 'RFQ Updates', desc: 'Notifications for quote responses' },
                            { label: 'Compliance Reminders', desc: 'Periodic compliance check reminders' },
                        ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 12, background: 'var(--bg-tertiary)', borderRadius: 8 }}>
                                <div>
                                    <div style={{ fontWeight: 500, fontSize: 14 }}>{item.label}</div>
                                    <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{item.desc}</div>
                                </div>
                                <button
                                    className="btn btn-secondary"
                                    style={{ padding: '6px 16px', background: 'var(--accent-primary)', color: 'white' }}
                                >
                                    Enabled
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
