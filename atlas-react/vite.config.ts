import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = fileURLToPath(new URL('.', import.meta.url));

// Caminhos das pastas de dados (relativo à raiz do projeto, um nível acima de atlas-react/)
const DATA_ROOT = resolve(__dirname, '..');

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Plugin inline: serve output_data/ e config/ localmente em dev
    // para não depender do GitHub Pages durante o desenvolvimento.
    {
      name: 'local-data-server',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const LOCAL_PREFIXES: Record<string, string> = {
            '/atlas/output_data/': resolve(DATA_ROOT, 'output_data'),
            '/atlas/config/':      resolve(DATA_ROOT, 'config'),
          };
          for (const [prefix, dir] of Object.entries(LOCAL_PREFIXES)) {
            if (req.url?.startsWith(prefix)) {
              const filePath = resolve(dir, req.url.slice(prefix.length));
              if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
                const ext = filePath.split('.').pop() ?? '';
                const mime: Record<string, string> = {
                  json: 'application/json',
                  geojson: 'application/json',
                  js: 'application/javascript',
                };
                res.setHeader('Content-Type', mime[ext] ?? 'application/octet-stream');
                res.setHeader('Access-Control-Allow-Origin', '*');
                fs.createReadStream(filePath).pipe(res);
                return;
              }
            }
          }
          next();
        });
      },
    },
  ],
  // Ajuste o base para o nome do seu repositório no GitHub Pages
  // Ex: se o repo se chama "atlas", use '/atlas/'
  // Se for o root (usuario.github.io), use '/'
  base: '/atlas/',
  server: {
    // Expõe o servidor em todas as interfaces de rede para acesso via IP local
    // (ex: celular/tablet na mesma Wi-Fi). Equivalente a usar `--host`.
    host: true,
    port: 5173,
    strictPort: false,
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
    // Permite que o Vite acesse arquivos fora de atlas-react/
    fs: {
      allow: ['..'],
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
