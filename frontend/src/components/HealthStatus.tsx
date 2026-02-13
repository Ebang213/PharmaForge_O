/**
 * HealthStatus Component
 * Displays real-time API health check status with HTTP codes and response details.
 * This component DOES NOT use mock data or fake success states.
 */
import { useState, useEffect } from 'react';
import { healthApi } from '../lib/api';
import { Activity, CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';

interface HealthResult {
    endpoint: string;
    status: 'loading' | 'healthy' | 'unhealthy' | 'error';
    httpCode?: number | string;
    responseSnippet?: string;
    latencyMs?: number;
}

export default function HealthStatus() {
    const [results, setResults] = useState<HealthResult[]>([]);
    const [checking, setChecking] = useState(false);
    const [lastChecked, setLastChecked] = useState<Date | null>(null);

    const checkHealth = async () => {
        setChecking(true);
        const endpoints: { name: string; fn: () => Promise<any> }[] = [
            { name: '/api/health', fn: healthApi.check },
            { name: '/api/risk/health', fn: healthApi.risk },
            { name: '/api/watchtower/health', fn: healthApi.watchtower },
            { name: '/api/dscsa/health', fn: healthApi.dscsa },
            { name: '/api/copilot/health', fn: healthApi.copilot },
        ];

        const newResults: HealthResult[] = [];

        for (const ep of endpoints) {
            const startTime = performance.now();
            try {
                const response = await ep.fn();
                const latency = Math.round(performance.now() - startTime);
                const snippet = JSON.stringify(response.data).slice(0, 100);
                newResults.push({
                    endpoint: ep.name,
                    status: 'healthy',
                    httpCode: response.status || 200,
                    responseSnippet: snippet,
                    latencyMs: latency,
                });
            } catch (err: any) {
                const latency = Math.round(performance.now() - startTime);
                const httpCode = err.response?.status || 'NETWORK_ERROR';
                const snippet = err.response?.data
                    ? JSON.stringify(err.response.data).slice(0, 100)
                    : err.message || 'Unknown error';
                newResults.push({
                    endpoint: ep.name,
                    status: httpCode === 401 ? 'unhealthy' : 'error',
                    httpCode,
                    responseSnippet: snippet,
                    latencyMs: latency,
                });
            }
        }

        setResults(newResults);
        setLastChecked(new Date());
        setChecking(false);
    };

    useEffect(() => {
        checkHealth();
    }, []);

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'healthy':
                return <CheckCircle size={16} style={{ color: 'var(--success)' }} />;
            case 'unhealthy':
                return <AlertTriangle size={16} style={{ color: 'var(--warning)' }} />;
            case 'error':
                return <XCircle size={16} style={{ color: 'var(--danger)' }} />;
            default:
                return <Activity size={16} style={{ color: 'var(--text-muted)' }} />;
        }
    };

    const getStatusBadge = (status: string) => {
        const classes: Record<string, string> = {
            healthy: 'badge badge-success',
            unhealthy: 'badge badge-warning',
            error: 'badge badge-danger',
            loading: 'badge',
        };
        return classes[status] || 'badge';
    };

    return (
        <div className="card" style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ fontSize: 16, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Activity size={18} /> API Health Status
                </h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    {lastChecked && (
                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                            Last checked: {lastChecked.toLocaleTimeString()}
                        </span>
                    )}
                    <button
                        className="btn btn-secondary"
                        style={{ padding: '6px 12px' }}
                        onClick={checkHealth}
                        disabled={checking}
                    >
                        <RefreshCw size={14} className={checking ? 'spin' : ''} />
                        {checking ? 'Checking...' : 'Refresh'}
                    </button>
                </div>
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
                Live health checks showing real HTTP status codes and response data. No mock data.
            </p>

            <table className="data-table smaller">
                <thead>
                    <tr>
                        <th>Endpoint</th>
                        <th>Status</th>
                        <th>HTTP Code</th>
                        <th>Latency</th>
                        <th>Response</th>
                    </tr>
                </thead>
                <tbody>
                    {results.length === 0 && !checking ? (
                        <tr>
                            <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                                Click "Refresh" to check health status
                            </td>
                        </tr>
                    ) : (
                        results.map((r, idx) => (
                            <tr key={idx}>
                                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>{r.endpoint}</td>
                                <td>
                                    <span className={getStatusBadge(r.status)} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                        {getStatusIcon(r.status)}
                                        {r.status.toUpperCase()}
                                    </span>
                                </td>
                                <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                                    {r.httpCode}
                                </td>
                                <td style={{ fontSize: 12 }}>
                                    {r.latencyMs}ms
                                </td>
                                <td style={{ fontFamily: 'monospace', fontSize: 11, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {r.responseSnippet}
                                </td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}
