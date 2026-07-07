// Feature flags driven by Vite env vars (build-time).
// VITE_ENTERPRISE_FEATURES gates the enterprise surface (Mission Control,
// Copilot, War Council, Sourcing, Watchtower). Defaults to false — the
// pharmacy MVP hides these pages entirely unless explicitly enabled.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const env = (import.meta as any).env;

export const ENTERPRISE_FEATURES: boolean = env?.VITE_ENTERPRISE_FEATURES === 'true';
