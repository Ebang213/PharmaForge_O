import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import { authApi } from '../lib/api';
import { Shield, Mail, Lock, ArrowRight } from 'lucide-react';
import './Login.css';

export default function Login() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const [formData, setFormData] = useState({
        email: '',
        password: '',
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await authApi.login(formData.email, formData.password);
            login(response.data.access_token, response.data.user);
            // Redirect to Risk Intelligence Loop (Mission Control) after successful auth
            navigate('/mission-control', { replace: true });
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            if (typeof detail === 'string') {
                setError(detail);
            } else {
                setError('Authentication failed. Please check your credentials.');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-bg" />
            <div className="login-container">
                <div className="login-header">
                    <div className="login-logo">
                        <Shield size={40} />
                    </div>
                    <h1>PharmaForge OS</h1>
                    <p>Operating System for Virtual Pharma</p>
                </div>

                <form className="login-form" onSubmit={handleSubmit}>
                    <h2>Welcome Back</h2>

                    {error && <div className="error-message">{error}</div>}

                    <div className="form-group">
                        <label><Mail size={16} /> Email</label>
                        <input
                            type="email"
                            placeholder="you@company.com"
                            value={formData.email}
                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                            required
                            autoComplete="email"
                        />
                    </div>

                    <div className="form-group">
                        <label><Lock size={16} /> Password</label>
                        <input
                            type="password"
                            placeholder="••••••••"
                            value={formData.password}
                            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                            required
                            autoComplete="current-password"
                        />
                    </div>

                    <button type="submit" className="btn btn-primary login-btn" disabled={loading}>
                        {loading ? 'Signing in...' : 'Sign In'}
                        <ArrowRight size={18} />
                    </button>
                </form>

                <div className="login-footer">
                    <p className="contact-admin">
                        Need an account? Contact your system administrator.
                    </p>
                </div>
            </div>
        </div>
    );
}
