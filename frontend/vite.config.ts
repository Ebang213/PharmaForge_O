import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), '');

    return {
        plugins: [react()],
        resolve: {
            alias: {
                '@': path.resolve(__dirname, './src'),
            },
        },
        build: {
            outDir: 'dist',
            sourcemap: mode !== 'production',
            // Use esbuild for minification (built-in, faster, no extra deps)
            minify: 'esbuild',
            rollupOptions: {
                output: {
                    manualChunks: {
                        'react-vendor': ['react', 'react-dom', 'react-router-dom'],
                        'ui-vendor': ['lucide-react', 'recharts'],
                    },
                },
            },
            chunkSizeWarningLimit: 1000,
        },
        server: {
            port: 5173,
            host: true,
            proxy: {
                '/api': {
                    // Use VITE_PROXY_TARGET in Docker, or fallback to localhost for local dev
                    target: env.VITE_PROXY_TARGET || env.VITE_API_URL || 'http://localhost:8001',
                    changeOrigin: true,
                },
            },
        },
        preview: {
            port: 5173,
            host: true,
        },
    };
});
