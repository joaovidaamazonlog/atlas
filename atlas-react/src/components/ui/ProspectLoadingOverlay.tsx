/**
 * ProspectLoadingOverlay.tsx
 * ==========================
 * Overlay fullscreen de loading para a busca de empresas.
 * Visual idêntico ao loading do HCP em RoutesTab.
 */

import { createPortal } from 'react-dom';
import { useStore } from '../../store';

export default function ProspectLoadingOverlay() {
  const isLoading = useStore((s) => s.prospectState.isLoading);

  if (!isLoading) return null;

  return createPortal(
    <div style={{
      position: 'fixed', inset: 0, zIndex: 99999,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--color-dark)', color: 'var(--color-light)', padding: '28px 36px',
        borderRadius: '10px', boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', gap: '16px', fontSize: '15px',
      }}>
        <svg style={{ animation: 'spin 1s linear infinite', width: 28, height: 28 }} viewBox="0 0 24 24" fill="none">
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <circle cx="12" cy="12" r="10" stroke="#00a8e1" strokeWidth="4" strokeOpacity="0.25"/>
          <path fill="#00a8e1" d="M4 12a8 8 0 018-8v8z"/>
        </svg>
        Carregando empresas...
      </div>
    </div>,
    document.body
  );
}
