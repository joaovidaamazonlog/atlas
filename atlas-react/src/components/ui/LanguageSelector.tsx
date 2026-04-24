/**
 * LanguageSelector.tsx
 * ====================
 * Seletor de idioma com bandeiras SVG inline.
 */

import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

// SVG flags inline — evita dependência de emoji (inconsistente entre plataformas)
const FlagBR = () => (
  <svg width="20" height="14" viewBox="0 0 20 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="20" height="14" rx="2" fill="#009C3B"/>
    <polygon points="10,1.5 18.5,7 10,12.5 1.5,7" fill="#FEDF00"/>
    <circle cx="10" cy="7" r="3" fill="#002776"/>
    <path d="M7.2 6.2 Q10 5 12.8 6.2" stroke="white" strokeWidth="0.7" fill="none"/>
  </svg>
);

const FlagUS = () => (
  <svg width="20" height="14" viewBox="0 0 20 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="20" height="14" rx="2" fill="#B22234"/>
    <rect y="1.08" width="20" height="1.08" fill="white"/>
    <rect y="3.23" width="20" height="1.08" fill="white"/>
    <rect y="5.38" width="20" height="1.08" fill="white"/>
    <rect y="7.54" width="20" height="1.08" fill="white"/>
    <rect y="9.69" width="20" height="1.08" fill="white"/>
    <rect y="11.85" width="20" height="1.08" fill="white"/>
    <rect width="8" height="7.54" rx="0" fill="#3C3B6E"/>
  </svg>
);

const FlagES = () => (
  <svg width="20" height="14" viewBox="0 0 20 14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="20" height="14" rx="2" fill="#AA151B"/>
    <rect y="3.5" width="20" height="7" fill="#F1BF00"/>
  </svg>
);

const LANGUAGES = [
  { code: 'pt', label: 'Português', Flag: FlagBR },
  { code: 'en', label: 'English',   Flag: FlagUS },
  { code: 'es', label: 'Español',   Flag: FlagES },
];

export default function LanguageSelector() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = LANGUAGES.find((l) => i18n.language.startsWith(l.code)) ?? LANGUAGES[0];

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Select language"
        title="Select language"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 8px',
          background: 'none',
          border: '1px solid rgba(255,255,255,0.25)',
          borderRadius: '6px',
          cursor: 'pointer',
          color: 'rgba(255,255,255,0.85)',
          fontSize: '12px',
          fontWeight: 600,
          transition: 'border-color 150ms, color 150ms',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = '#00a8e1';
          e.currentTarget.style.color = '#00a8e1';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.25)';
          e.currentTarget.style.color = 'rgba(255,255,255,0.85)';
        }}
      >
        <current.Flag />
        <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>{current.code}</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <ul
          style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 6px)',
            zIndex: 99999,
            minWidth: '140px',
            background: 'var(--color-navy)',
            border: '1px solid var(--border-color-strong)',
            borderRadius: '8px',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
            overflow: 'hidden',
            listStyle: 'none',
            margin: 0,
            padding: 0,
          }}
        >
          {LANGUAGES.map((lang) => {
            const isActive = current.code === lang.code;
            return (
              <li key={lang.code}>
                <button
                  type="button"
                  onClick={() => { i18n.changeLanguage(lang.code); setOpen(false); }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '9px 14px',
                    background: isActive ? 'rgba(0,168,225,0.12)' : 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: isActive ? '#00a8e1' : 'var(--color-light)',
                    fontSize: '13px',
                    fontWeight: isActive ? 600 : 400,
                    textAlign: 'left',
                    transition: 'background 150ms, color 150ms',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
                      e.currentTarget.style.color = '#00a8e1';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = 'none';
                      e.currentTarget.style.color = 'var(--color-light)';
                    }
                  }}
                >
                  <lang.Flag />
                  <span>{lang.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
