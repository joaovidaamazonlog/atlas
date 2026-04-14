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
