import { useState, useEffect } from 'react';
import { adminApi } from '../lib/api';
import { Users, UserPlus, Shield, Edit2, Trash2, Key, X, Check, AlertCircle } from 'lucide-react';

interface User {
    id: number;
    email: string;
    full_name: string | null;
    role: string;
    is_active: boolean;
    organization_id: number;
    created_at: string;
    last_login: string | null;
}

export default function AdminUsers() {
    const [users, setUsers] = useState<User[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [showResetPasswordModal, setShowResetPasswordModal] = useState(false);
    const [selectedUser, setSelectedUser] = useState<User | null>(null);

    // Create form state
    const [newUser, setNewUser] = useState({
        email: '',
        password: '',
        full_name: '',
        role: 'viewer'
    });

    // Edit form state
    const [editData, setEditData] = useState({
        full_name: '',
        role: '',
        is_active: true
    });

    // Reset password state
    const [newPassword, setNewPassword] = useState('');

    // Form errors
    const [formError, setFormError] = useState<string | null>(null);

    useEffect(() => {
        loadUsers();
    }, []);

    const loadUsers = async () => {
        try {
            setError(null);
            const response = await adminApi.listUsers();
            setUsers(response.data);
        } catch (err: any) {
            if (err.response?.status === 403) {
                setError('You do not have permission to access user management. Admin role required.');
            } else {
                setError('Failed to load users. Please try again.');
            }
            console.error('Failed to load users:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateUser = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError(null);

        try {
            await adminApi.createUser(newUser);
            setShowCreateModal(false);
            setNewUser({ email: '', password: '', full_name: '', role: 'viewer' });
            loadUsers();
        } catch (err: any) {
            setFormError(err.response?.data?.detail || 'Failed to create user');
        }
    };

    const handleEditUser = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedUser) return;
        setFormError(null);

        try {
            await adminApi.updateUser(selectedUser.id, editData);
            setShowEditModal(false);
            setSelectedUser(null);
            loadUsers();
        } catch (err: any) {
            setFormError(err.response?.data?.detail || 'Failed to update user');
        }
    };

    const handleDeleteUser = async (user: User) => {
        if (!confirm(`Are you sure you want to delete ${user.email}?`)) return;

        try {
            await adminApi.deleteUser(user.id);
            loadUsers();
        } catch (err: any) {
            alert(err.response?.data?.detail || 'Failed to delete user');
        }
    };

    const handleResetPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedUser) return;
        setFormError(null);

        try {
            await adminApi.resetPassword(selectedUser.id, newPassword);
            setShowResetPasswordModal(false);
            setSelectedUser(null);
            setNewPassword('');
            alert('Password reset successfully. User should change password on next login.');
        } catch (err: any) {
            setFormError(err.response?.data?.detail || 'Failed to reset password');
        }
    };

    const openEditModal = (user: User) => {
        setSelectedUser(user);
        setEditData({
            full_name: user.full_name || '',
            role: user.role,
            is_active: user.is_active
        });
        setFormError(null);
        setShowEditModal(true);
    };

    const openResetPasswordModal = (user: User) => {
        setSelectedUser(user);
        setNewPassword('');
        setFormError(null);
        setShowResetPasswordModal(true);
    };

    const getRoleBadge = (role: string) => {
        const classes: Record<string, string> = {
            owner: 'badge badge-danger',
            admin: 'badge badge-warning',
            operator: 'badge badge-info',
            viewer: 'badge badge-success',
        };
        return <span className={classes[role] || 'badge'}>{role.toUpperCase()}</span>;
    };

    if (loading) {
        return <div className="loading-container"><div className="spinner" /></div>;
    }

    if (error) {
        return (
            <div className="fade-in">
                <div className="page-header">
                    <h1>Admin → Users</h1>
                    <p>User management and access control</p>
                </div>
                <div className="card" style={{ textAlign: 'center', padding: 40 }}>
                    <AlertCircle size={48} style={{ marginBottom: 16, color: 'var(--danger)', opacity: 0.7 }} />
                    <p style={{ color: 'var(--text-secondary)' }}>{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div className="fade-in">
            <div className="page-header">
                <h1>Admin → Users</h1>
                <p>Manage user accounts and permissions</p>
            </div>

            {/* Stats */}
            <div className="grid grid-4" style={{ marginBottom: 32 }}>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#6366f1' }}>
                        <Users size={24} />
                    </div>
                    <div className="content">
                        <h3>Total Users</h3>
                        <div className="value">{users.length}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(34, 197, 94, 0.15)', color: '#22c55e' }}>
                        <Check size={24} />
                    </div>
                    <div className="content">
                        <h3>Active Users</h3>
                        <div className="value">{users.filter(u => u.is_active).length}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' }}>
                        <Shield size={24} />
                    </div>
                    <div className="content">
                        <h3>Admins</h3>
                        <div className="value">{users.filter(u => u.role === 'admin' || u.role === 'owner').length}</div>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="icon" style={{ background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' }}>
                        <UserPlus size={24} />
                    </div>
                    <div className="content">
                        <h3>New This Month</h3>
                        <div className="value">
                            {users.filter(u => {
                                const created = new Date(u.created_at);
                                const now = new Date();
                                return created.getMonth() === now.getMonth() && created.getFullYear() === now.getFullYear();
                            }).length}
                        </div>
                    </div>
                </div>
            </div>

            {/* Users Table */}
            <div className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                    <h2 style={{ fontSize: 18, fontWeight: 600 }}>User Accounts</h2>
                    <button className="btn btn-primary" onClick={() => {
                        setFormError(null);
                        setShowCreateModal(true);
                    }}>
                        <UserPlus size={18} /> Add User
                    </button>
                </div>

                {users.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                        <Users size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                        <p>No users found. Add your first user to get started.</p>
                    </div>
                ) : (
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Role</th>
                                <th>Status</th>
                                <th>Last Login</th>
                                <th>Created</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map(user => (
                                <tr key={user.id}>
                                    <td>
                                        <div style={{ fontWeight: 500 }}>{user.full_name || user.email}</div>
                                        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{user.email}</div>
                                    </td>
                                    <td>{getRoleBadge(user.role)}</td>
                                    <td>
                                        {user.is_active ? (
                                            <span className="badge badge-success">Active</span>
                                        ) : (
                                            <span className="badge badge-danger">Disabled</span>
                                        )}
                                    </td>
                                    <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                                        {user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}
                                    </td>
                                    <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                                        {new Date(user.created_at).toLocaleDateString()}
                                    </td>
                                    <td>
                                        <div style={{ display: 'flex', gap: 8 }}>
                                            <button
                                                className="btn btn-secondary"
                                                style={{ padding: '6px 10px' }}
                                                onClick={() => openEditModal(user)}
                                                title="Edit user"
                                            >
                                                <Edit2 size={14} />
                                            </button>
                                            <button
                                                className="btn btn-secondary"
                                                style={{ padding: '6px 10px' }}
                                                onClick={() => openResetPasswordModal(user)}
                                                title="Reset password"
                                            >
                                                <Key size={14} />
                                            </button>
                                            <button
                                                className="btn btn-secondary"
                                                style={{ padding: '6px 10px', color: 'var(--danger)' }}
                                                onClick={() => handleDeleteUser(user)}
                                                title="Delete user"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Create User Modal */}
            {showCreateModal && (
                <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
                    <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <h2 style={{ fontSize: 18, fontWeight: 600 }}>Create New User</h2>
                            <button className="btn btn-secondary" style={{ padding: 8 }} onClick={() => setShowCreateModal(false)}>
                                <X size={16} />
                            </button>
                        </div>

                        {formError && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', borderRadius: 8, padding: 12, marginBottom: 16 }}>
                                <p style={{ color: 'var(--danger)', fontSize: 14 }}>{formError}</p>
                            </div>
                        )}

                        <form onSubmit={handleCreateUser}>
                            <div style={{ marginBottom: 16 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Email</label>
                                <input
                                    type="email"
                                    value={newUser.email}
                                    onChange={e => setNewUser({ ...newUser, email: e.target.value })}
                                    required
                                    placeholder="user@example.com"
                                    style={{ width: '100%' }}
                                />
                            </div>
                            <div style={{ marginBottom: 16 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Full Name</label>
                                <input
                                    type="text"
                                    value={newUser.full_name}
                                    onChange={e => setNewUser({ ...newUser, full_name: e.target.value })}
                                    required
                                    placeholder="John Doe"
                                    style={{ width: '100%' }}
                                />
                            </div>
                            <div style={{ marginBottom: 16 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Password</label>
                                <input
                                    type="password"
                                    value={newUser.password}
                                    onChange={e => setNewUser({ ...newUser, password: e.target.value })}
                                    required
                                    minLength={10}
                                    placeholder="Min 10 chars, 1 letter, 1 number"
                                    style={{ width: '100%' }}
                                />
                                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                                    Password must be at least 10 characters with at least one letter and one number.
                                </p>
                            </div>
                            <div style={{ marginBottom: 24 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Role</label>
                                <select
                                    value={newUser.role}
                                    onChange={e => setNewUser({ ...newUser, role: e.target.value })}
                                    style={{ width: '100%' }}
                                >
                                    <option value="viewer">Viewer - Read-only access</option>
                                    <option value="operator">Operator - Can manage data</option>
                                    <option value="admin">Admin - Full access</option>
                                </select>
                            </div>
                            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    <UserPlus size={16} /> Create User
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Edit User Modal */}
            {showEditModal && selectedUser && (
                <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
                    <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <h2 style={{ fontSize: 18, fontWeight: 600 }}>Edit User</h2>
                            <button className="btn btn-secondary" style={{ padding: 8 }} onClick={() => setShowEditModal(false)}>
                                <X size={16} />
                            </button>
                        </div>

                        <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>{selectedUser.email}</p>

                        {formError && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', borderRadius: 8, padding: 12, marginBottom: 16 }}>
                                <p style={{ color: 'var(--danger)', fontSize: 14 }}>{formError}</p>
                            </div>
                        )}

                        <form onSubmit={handleEditUser}>
                            <div style={{ marginBottom: 16 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Full Name</label>
                                <input
                                    type="text"
                                    value={editData.full_name}
                                    onChange={e => setEditData({ ...editData, full_name: e.target.value })}
                                    placeholder="John Doe"
                                    style={{ width: '100%' }}
                                />
                            </div>
                            <div style={{ marginBottom: 16 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>Role</label>
                                <select
                                    value={editData.role}
                                    onChange={e => setEditData({ ...editData, role: e.target.value })}
                                    style={{ width: '100%' }}
                                >
                                    <option value="viewer">Viewer - Read-only access</option>
                                    <option value="operator">Operator - Can manage data</option>
                                    <option value="admin">Admin - Full access</option>
                                    <option value="owner">Owner - Full access + ownership</option>
                                </select>
                            </div>
                            <div style={{ marginBottom: 24 }}>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                                    <input
                                        type="checkbox"
                                        checked={editData.is_active}
                                        onChange={e => setEditData({ ...editData, is_active: e.target.checked })}
                                    />
                                    <span style={{ fontSize: 14 }}>Account is active</span>
                                </label>
                            </div>
                            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowEditModal(false)}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    <Check size={16} /> Save Changes
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Reset Password Modal */}
            {showResetPasswordModal && selectedUser && (
                <div className="modal-overlay" onClick={() => setShowResetPasswordModal(false)}>
                    <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <h2 style={{ fontSize: 18, fontWeight: 600 }}>Reset Password</h2>
                            <button className="btn btn-secondary" style={{ padding: 8 }} onClick={() => setShowResetPasswordModal(false)}>
                                <X size={16} />
                            </button>
                        </div>

                        <p style={{ color: 'var(--text-secondary)', marginBottom: 16 }}>
                            Set a new temporary password for <strong>{selectedUser.email}</strong>
                        </p>

                        {formError && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--danger)', borderRadius: 8, padding: 12, marginBottom: 16 }}>
                                <p style={{ color: 'var(--danger)', fontSize: 14 }}>{formError}</p>
                            </div>
                        )}

                        <form onSubmit={handleResetPassword}>
                            <div style={{ marginBottom: 24 }}>
                                <label style={{ display: 'block', marginBottom: 6, fontSize: 14, fontWeight: 500 }}>New Password</label>
                                <input
                                    type="password"
                                    value={newPassword}
                                    onChange={e => setNewPassword(e.target.value)}
                                    required
                                    minLength={10}
                                    placeholder="Min 10 chars, 1 letter, 1 number"
                                    style={{ width: '100%' }}
                                />
                                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                                    The user should change this password after logging in.
                                </p>
                            </div>
                            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setShowResetPasswordModal(false)}>
                                    Cancel
                                </button>
                                <button type="submit" className="btn btn-primary">
                                    <Key size={16} /> Reset Password
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
