import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import {
    Shield, FileCheck, Building2,
    ScrollText, Settings, LogOut, Bell, UserCog,
    LayoutDashboard
} from 'lucide-react';
import './Sidebar.css';

const navItems = [
    { path: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    { path: '/transactions', icon: FileCheck, label: 'Transactions' },
    { path: '/trading-partners', icon: Building2, label: 'Trading Partners' },
    { path: '/alerts', icon: Bell, label: 'Alerts' },
    { path: '/audit', icon: ScrollText, label: 'Audit Log' },
    { path: '/settings', icon: Settings, label: 'Settings' },
];

const adminNavItems = [
    { path: '/admin/users', icon: UserCog, label: 'Users' },
];

export default function Sidebar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <aside className="sidebar">
            <div className="sidebar-header">
                <div className="logo">
                    <Shield size={28} />
                    <div className="logo-text">
                        <span className="logo-title">PharmaForge</span>
                        <span className="logo-subtitle">DSCSA</span>
                    </div>
                </div>
            </div>

            <nav className="sidebar-nav">
                {navItems.map(({ path, icon: Icon, label }) => (
                    <NavLink key={path} to={path} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                        <Icon size={20} />
                        <span>{label}</span>
                    </NavLink>
                ))}

                {/* Admin section - only show for admin/owner */}
                {(user?.role === 'admin' || user?.role === 'owner') && (
                    <>
                        <div className="nav-section-label" style={{
                            fontSize: 11,
                            color: 'var(--text-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: 1,
                            padding: '16px 16px 8px',
                            marginTop: 8
                        }}>
                            Admin
                        </div>
                        {adminNavItems.map(({ path, icon: Icon, label }) => (
                            <NavLink key={path} to={path} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                                <Icon size={20} />
                                <span>{label}</span>
                            </NavLink>
                        ))}
                    </>
                )}
            </nav>

            <div className="sidebar-footer">
                <div className="user-info">
                    <div className="user-avatar">
                        {user?.full_name?.charAt(0) || 'U'}
                    </div>
                    <div className="user-details">
                        <span className="user-name">{user?.full_name || 'User'}</span>
                        <span className="user-org">{user?.organization_name}</span>
                    </div>
                </div>
                <button className="logout-btn" onClick={handleLogout}>
                    <LogOut size={18} />
                </button>
            </div>
        </aside>
    );
}
