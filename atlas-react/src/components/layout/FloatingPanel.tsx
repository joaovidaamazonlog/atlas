import React, { useState } from 'react';

interface FloatingPanelProps {
  title: string;
  defaultCollapsed?: boolean;
  width?: number;
  children: React.ReactNode;
  className?: string;
}

export const FloatingPanel: React.FC<FloatingPanelProps> = ({
  title,
  defaultCollapsed = false,
  width = 320,
  children,
  className = '',
}) => {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div
      className={`flex flex-col rounded-lg overflow-hidden ${className}`}
      style={{
        width: `${width}px`,
        backgroundColor: 'var(--color-navy)',
        border: '1px solid var(--border-color)',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="flex items-center justify-between px-4 py-3 w-full text-left hover:bg-white/5 transition-colors duration-150 shrink-0"
        aria-expanded={!collapsed}
        aria-controls="floating-panel-content"
      >
        <span className="font-medium text-atlas-light text-sm">{title}</span>
        {/* Chevron icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4 text-atlas-muted transition-transform duration-300"
          style={{ transform: collapsed ? 'rotate(0deg)' : 'rotate(180deg)' }}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Collapsible content */}
      <div
        id="floating-panel-content"
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: collapsed ? '0px' : '600px' }}
      >
        <div
          className="overflow-y-auto"
          style={{ borderTop: '1px solid var(--border-color)' }}
        >
          {children}
        </div>
      </div>
    </div>
  );
};
