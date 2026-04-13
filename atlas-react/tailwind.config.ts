import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tema escuro ATLAS
        'atlas-navy': '#232f3e',
        'atlas-dark': '#1e2a38',
        'atlas-darker': '#16202c',
        'atlas-light': '#ecf0f1',
        'atlas-accent': '#ff9900',
        'atlas-muted': '#8899aa',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      screens: {
        // Breakpoints ATLAS
        // mobile: < 768px (default)
        tablet: '768px',   // 768px–1023px
        notebook: '1024px', // 1024px–1439px
        desktop: '1440px',  // ≥ 1440px
      },
      transitionDuration: {
        '150': '150ms',
        '300': '300ms',
      },
    },
  },
  plugins: [],
};

export default config;
