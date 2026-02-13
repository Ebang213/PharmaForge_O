import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../App';
import {
    Shield, FileCheck, MessageSquare, Users, Building2,
    ScrollText, Settings, LogOut, ShoppingCart, AlertTriangle, UserCog,
    Target, GitBranch
} from 'lucide-react';
import './Sidebar.css';

const navItems = [
    { path: '/mission-control', icon: Target, label: 'Risk Intelligence Loop' },
    { path: '/workflow', icon: GitBranch, label: 'Golden Workflow' },
    { path: '/watchtower', icon: AlertTriangle, label: 'Supply Chain Risk Radar' },
    { path: '/dscsa', icon: FileCheck, label: 'DSCSA / EPCIS' },
    { path: '/copilot', icon: MessageSquare, label: 'Compliance Copilot' },
    { path: '/war-council', icon: Users, label: 'Decision Council' },
    { path: '/vendors', icon: Building2, label: 'Vendors' },
    { path: '/sourcing', icon: ShoppingCart, label: 'Sourcing' },
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
                        <span className="logo-subtitle">OS</span>
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
