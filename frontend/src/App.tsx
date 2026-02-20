import { createContext, useContext, useState, useEffect, ReactNode, lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

// Components (loaded eagerly — small, always needed)
import Sidebar from './components/Sidebar';
import ErrorBoundary from './components/ErrorBoundary';

// Lazy-loaded pages (code-split at route level)
const Login = lazy(() => import('./pages/Login'));
const MissionControl = lazy(() => import('./pages/MissionControl'));
const Workflow = lazy(() => import('./pages/Workflow'));
const Watchtower = lazy(() => import('./pages/Watchtower'));
const DSCSA = lazy(() => import('./pages/DSCSA'));
const Copilot = lazy(() => import('./pages/Copilot'));
const WarCouncil = lazy(() => import('./pages/WarCouncil'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));

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
        // Check for existing auth on mount (sessionStorage — cleared on browser close)
        const storedToken = sessionStorage.getItem('pharmaforge_token');
        const storedUser = sessionStorage.getItem('pharmaforge_user');

        if (storedToken && storedUser) {
            setToken(storedToken);
            setUser(JSON.parse(storedUser));
        }
        setLoading(false);
    }, []);

    const login = (newToken: string, newUser: User) => {
        setToken(newToken);
        setUser(newUser);
        sessionStorage.setItem('pharmaforge_token', newToken);
        sessionStorage.setItem('pharmaforge_user', JSON.stringify(newUser));
    };

    const logout = () => {
        setToken(null);
        setUser(null);
        sessionStorage.removeItem('pharmaforge_token');
        sessionStorage.removeItem('pharmaforge_user');
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

// Suspense fallback for lazy-loaded routes
function PageLoader() {
    return (
        <div className="loading-screen">
            <div className="loading-spinner"></div>
        </div>
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
        <ErrorBoundary>
            <BrowserRouter>
                <AuthProvider>
                    <Suspense fallback={<PageLoader />}>
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
                    </Suspense>
                </AuthProvider>
            </BrowserRouter>
        </ErrorBoundary>
    );
}
