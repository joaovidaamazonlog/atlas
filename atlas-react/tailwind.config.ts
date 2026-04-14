import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tema ATLAS — usa variáveis CSS para suportar dark/light theme
        // Formato com canal alpha para suportar modificadores de opacidade (bg-atlas-navy/50)
        'atlas-navy':   'rgb(var(--color-navy-rgb) / <alpha-value>)',
        'atlas-dark':   'rgb(var(--color-dark-rgb) / <alpha-value>)',
        'atlas-darker': 'rgb(var(--color-darker-rgb) / <alpha-value>)',
        'atlas-light':  'rgb(var(--color-light-rgb) / <alpha-value>)',
        'atlas-accent': 'rgb(var(--color-accent-rgb) / <alpha-value>)',
        'atlas-muted':  'rgb(var(--color-muted-rgb) / <alpha-value>)',
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
