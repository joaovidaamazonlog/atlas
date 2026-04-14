import React from 'react';

interface DashboardToggleProps {
  isOpen: boolean;
  onClick: () => void;
}

export const DashboardToggle: React.FC<DashboardToggleProps> = ({ isOpen, onClick }) => {
  return (
    <button
      onClick={onClick}
      aria-label={isOpen ? 'Fechar dashboard' : 'Abrir dashboard'}
      aria-expanded={isOpen}
      style={{
        position: 'fixed',
        right: 0,
        top: '50%',
        transform: 'translateY(-50%)',
        width: '40px',
        height: '80px',
        borderRadius: '40px 0 0 40px',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: isOpen ? 'var(--color-accent)' : 'var(--color-navy)',
        color: isOpen ? 'var(--color-darker)' : 'var(--color-light)',
        border: '1px solid var(--border-color-strong)',
        borderRight: 'none',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: 'var(--shadow-md)',
        transition: 'background-color var(--transition-normal), color var(--transition-normal)',
      }}
    >
      {/* Bar chart icon */}
      <svg
        width="20"
        height="20"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <rect x="2" y="10" width="4" height="8" rx="1" />
        <rect x="8" y="6" width="4" height="12" rx="1" />
        <rect x="14" y="2" width="4" height="16" rx="1" />
      </svg>
    </button>
  );
};
