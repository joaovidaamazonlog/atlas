import React from 'react';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  side?: 'left' | 'right';
  width?: number;
  children: React.ReactNode;
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  side = 'left',
  width = 320,
  children,
}) => {
  const translateX = isOpen ? '0' : side === 'left' ? '-100%' : '100%';

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity duration-300"
        style={{
          zIndex: 'var(--z-drawer)' as unknown as number,
          opacity: isOpen ? 1 : 0,
          pointerEvents: isOpen ? 'auto' : 'none',
        }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="true"
        className="fixed top-0 bottom-0 flex flex-col overflow-hidden"
        style={{
          [side]: 0,
          width: `${width}px`,
          zIndex: 'var(--z-drawer)' as unknown as number,
          backgroundColor: 'var(--color-navy)',
          borderRight: side === 'left' ? '1px solid var(--border-color)' : undefined,
          borderLeft: side === 'right' ? '1px solid var(--border-color)' : undefined,
          transform: `translateX(${translateX})`,
          transition: 'transform 300ms ease',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        {children}
      </div>
    </>
  );
};
