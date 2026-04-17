import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Ajuste o base para o nome do seu repositório no GitHub Pages
  // Ex: se o repo se chama "atlas", use '/atlas/'
  // Se for o root (usuario.github.io), use '/'
  base: '/atlas/',
  server: {
    proxy: {
      // Proxy para contornar CORS em desenvolvimento local.
      // Chamadas para /api-proxy/* são redirecionadas para a API real.
      '/api-proxy': {
        target: 'https://api-cnpj-br.vercel.app',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api-proxy/, ''),
      },
      // Proxy para a API GeoIntelligence local (backend Python)
      '/geo-intelligence': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
  worker: {
    format: 'es',
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'leaflet-vendor': ['leaflet', 'react-leaflet'],
          'chart-vendor': ['chart.js', 'react-chartjs-2'],
          'zustand-vendor': ['zustand'],
        },
      },
    },
  },
});
