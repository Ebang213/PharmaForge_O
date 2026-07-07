import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import { authApi } from '../lib/api';
import { Shield, Mail, Lock, User, Building2, ArrowRight } from 'lucide-react';
import './Login.css';

export default function Register() {
    const { login } = useAuth();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const [formData, setFormData] = useState({
        full_name: '',
        pharmacy_name: '',
        email: '',
        password: '',
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError('');

        try {
            const response = await authApi.register({
                email: formData.email,
                password: formData.password,
                full_name: formData.full_name,
                organization_name: formData.pharmacy_name,
            });
            login(response.data.access_token, response.data.user, response.data.refresh_token);
            navigate('/dashboard', { replace: true });
        } catch (err: any) {
            const detail = err.response?.data?.detail;
            if (typeof detail === 'string') {
                setError(detail);
            } else if (Array.isArray(detail) && detail[0]?.msg) {
                setError(detail[0].msg);
            } else {
                setError('Registration failed. Please try again.');
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
                    <h1>PharmaForge DSCSA</h1>
                    <p>Register your pharmacy to start validating EPCIS data.</p>
                </div>

                <form className="login-form" onSubmit={handleSubmit}>
                    <h2>Create Your Account</h2>

                    {error && <div className="error-message">{error}</div>}

                    <div className="form-group">
                        <label><User size={16} /> Full Name</label>
                        <input
                            type="text"
                            placeholder="Jane Doe"
                            value={formData.full_name}
                            onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                            required
                            autoComplete="name"
                        />
                    </div>

                    <div className="form-group">
                        <label><Building2 size={16} /> Pharmacy Name</label>
                        <input
                            type="text"
                            placeholder="Main Street Pharmacy"
                            value={formData.pharmacy_name}
                            onChange={(e) => setFormData({ ...formData, pharmacy_name: e.target.value })}
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label><Mail size={16} /> Email</label>
                        <input
                            type="email"
                            placeholder="you@yourpharmacy.com"
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
                            placeholder="At least 10 characters, with a letter and a number"
                            value={formData.password}
                            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                            required
                            minLength={10}
                            autoComplete="new-password"
                        />
                    </div>

                    <button type="submit" className="btn btn-primary login-btn" disabled={loading}>
                        {loading ? 'Creating account...' : 'Register'}
                        <ArrowRight size={18} />
                    </button>
                </form>

                <div className="login-footer">
                    <p>
                        Already have an account? <Link to="/login" style={{ color: 'var(--accent-primary)' }}>Sign in</Link>
                    </p>
                </div>
            </div>
        </div>
    );
}
