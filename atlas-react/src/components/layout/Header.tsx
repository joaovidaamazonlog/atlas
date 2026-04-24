import React from 'react';
import { useStore } from '../../store';
import { LoadingIndicator } from '../ui/LoadingIndicator';
import { useTheme } from '../../hooks/useTheme';
import LanguageSelector from '../ui/LanguageSelector';

export const Header: React.FC = () => {
  const period = useStore((s) => s.period);
  const periodText = typeof period === 'string' ? period : JSON.stringify(period);
  const base = import.meta.env.BASE_URL;
  const { theme, toggleTheme } = useTheme();

  return (
    <header
      className="flex items-center justify-between shrink-0"
      style={{
        height: '56px',
        backgroundColor: 'var(--header-bg)',
        borderBottom: '1px solid var(--header-border)',
        padding: '6px 20px',
        fontFamily: 'Arial, sans-serif',
      }}
    >
      {/* Esquerda — logo */}
      <div style={{ width: '130px', flexShrink: 0 }}>
        <img
          src={`${base}icons/AmazonHub.ico`}
          alt="Amazon Hub"
          onError={(e) => { (e.target as HTMLImageElement).src = `${base}icons/hub.png`; }}
          style={{ width: '130px', height: '34px', objectFit: 'contain' }}
        />
      </div>

      {/* Centro — título */}
      <div className="flex flex-col items-center text-center flex-1 px-4">
        <p style={{ margin: 0, color: 'var(--header-text)', fontSize: '13px', fontWeight: 700, letterSpacing: '0.01em', lineHeight: 1.3 }}>
          ATLAS - Analytical Tracking for Location and Store performance
        </p>
        <p style={{ margin: 0, color: 'var(--color-accent)', fontSize: '11px', lineHeight: 1.3 }}>
          Created by: joaovida@
        </p>
        {periodText && (
          <p style={{ margin: 0, color: 'rgba(255,255,255,0.55)', fontSize: '11px', lineHeight: 1.3 }}>
            {periodText}
          </p>
        )}
      </div>

      {/* Direita — language selector + theme toggle + loading */}
      <div className="flex items-center justify-end gap-2" style={{ width: '180px', flexShrink: 0 }}>
        <LanguageSelector />
        <button
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '4px',
            color: 'rgba(255,255,255,0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderRadius: '4px',
            transition: 'color 150ms ease',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = '#00a8e1')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(255,255,255,0.7)')}
        >
          {theme === 'dark' ? (
            // Sun icon
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          ) : (
            // Moon icon
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          )}
        </button>
        <LoadingIndicator className="text-white/70" />
      </div>
    </header>
  );
};
