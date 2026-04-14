import React from 'react';

interface ControlsToggleProps {
  isOpen: boolean;
  onClick: () => void;
}

export const ControlsToggle: React.FC<ControlsToggleProps> = ({ isOpen, onClick }) => {
  return (
    <button
      onClick={onClick}
      aria-label={isOpen ? 'Fechar controles' : 'Abrir controles'}
      aria-expanded={isOpen}
      style={{
        position: 'fixed',
        left: 0,
        top: '50%',
        transform: 'translateY(-50%)',
        width: '40px',
        height: '80px',
        borderRadius: '0 40px 40px 0',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: isOpen ? 'var(--color-accent)' : 'var(--color-navy)',
        color: isOpen ? 'var(--color-darker)' : 'var(--color-light)',
        border: '1px solid var(--border-color-strong)',
        borderLeft: 'none',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '44px',
        boxShadow: 'var(--shadow-md)',
        transition: 'background-color var(--transition-normal), color var(--transition-normal)',
      }}
    >
      {/* Hamburger icon */}
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        {isOpen ? (
          /* X icon when open */
          <>
            <line x1="4" y1="4" x2="16" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <line x1="16" y1="4" x2="4" y2="16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </>
        ) : (
          /* Hamburger icon when closed */
          <>
            <rect x="3" y="4" width="14" height="2" rx="1" />
            <rect x="3" y="9" width="14" height="2" rx="1" />
            <rect x="3" y="14" width="14" height="2" rx="1" />
          </>
        )}
      </svg>
    </button>
  );
};
