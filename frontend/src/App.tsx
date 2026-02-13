import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Pages
import Login from './pages/Login';
import MissionControl from './pages/MissionControl';
import Workflow from './pages/Workflow';
import Watchtower from './pages/Watchtower';
import DSCSA from './pages/DSCSA';
import Copilot from './pages/Copilot';
import WarCouncil from './pages/WarCouncil';
import AdminUsers from './pages/AdminUsers';

// Components
import Sidebar from './components/Sidebar';

// Types
interface User {
    id: string;
    email: string;
    full_name: string;
    organization_id: string;
    organization_name: string;
    role: string;
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    login: (token: string, user: User) => void;
    logout: () => void;
    isAuthenticated: boolean;
}

// Auth Context
export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth(): AuthContextType {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}

// Auth Provider Component
function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check for existing auth on mount
        const storedToken = localStorage.getItem('pharmaforge_token');
        const storedUser = localStorage.getItem('pharmaforge_user');

        if (storedToken && storedUser) {
            setToken(storedToken);
            setUser(JSON.parse(storedUser));
        }
        setLoading(false);
    }, []);

    const login = (newToken: string, newUser: User) => {
        setToken(newToken);
        setUser(newUser);
        localStorage.setItem('pharmaforge_token', newToken);
        localStorage.setItem('pharmaforge_user', JSON.stringify(newUser));
    };

    const logout = () => {
        setToken(null);
        setUser(null);
        localStorage.removeItem('pharmaforge_token');
        localStorage.removeItem('pharmaforge_user');
    };

    if (loading) {
        return (
            <div className="loading-screen">
                <div className="loading-spinner"></div>
                <p>Loading PharmaForge OS...</p>
            </div>
        );
    }

    return (
        <AuthContext.Provider value={{ user, token, login, logout, isAuthenticated: !!token }}>
            {children}
        </AuthContext.Provider>
    );
}

// Protected Route Component
function ProtectedRoute({ children }: { children: ReactNode }) {
    const { isAuthenticated } = useAuth();

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return <>{children}</>;
}

// Main Layout with Sidebar
function MainLayout({ children }: { children: ReactNode }) {
    return (
        <div className="app-layout">
            <Sidebar />
            <main className="main-content">
                {children}
            </main>
        </div>
    );
}

// Placeholder pages for routes not yet implemented
function PlaceholderPage({ title }: { title: string }) {
    return (
        <div className="page-container">
            <h1>{title}</h1>
            <p className="text-muted">This module is coming soon.</p>
        </div>
    );
}

// Main App Component
export default function App() {
    return (
        <BrowserRouter>
            <AuthProvider>
                <Routes>
                    {/* Public Route */}
                    <Route path="/login" element={<Login />} />

                    {/* Protected Routes */}
                    <Route path="/" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <Navigate to="/mission-control" replace />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/mission-control" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <MissionControl />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/workflow" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <Workflow />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/watchtower" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <Watchtower />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/dscsa" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <DSCSA />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/copilot" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <Copilot />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/war-council" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <WarCouncil />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/vendors" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <PlaceholderPage title="Vendors" />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/sourcing" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <PlaceholderPage title="Sourcing" />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/audit" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <PlaceholderPage title="Audit Log" />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/settings" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <PlaceholderPage title="Settings" />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    <Route path="/admin/users" element={
                        <ProtectedRoute>
                            <MainLayout>
                                <AdminUsers />
                            </MainLayout>
                        </ProtectedRoute>
                    } />

                    {/* Catch-all redirect */}
                    <Route path="*" element={<Navigate to="/mission-control" replace />} />
                </Routes>
            </AuthProvider>
        </BrowserRouter>
    );
}
