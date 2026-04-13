import React from 'react';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { useStore } from '../../store';
import { LoadingIndicator } from '../ui/LoadingIndicator';

export const Header: React.FC = () => {
  const breakpoint = useBreakpoint();
  const period = useStore((s) => s.period);
  const isMobile = breakpoint === 'mobile';

  const periodText = typeof period === 'string' ? period : JSON.stringify(period);

  return (
    <header
      className="flex items-center justify-between px-3 shrink-0 border-b"
      style={{
        height: isMobile ? '48px' : '56px',
        backgroundColor: 'var(--color-navy)',
        borderBottomColor: 'var(--border-color)',
      }}
    >
      {/* Logo + título */}
      <div className="flex items-center gap-2">
        {/* Logo icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-6 h-6 text-atlas-accent shrink-0"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" />
        </svg>

        <div className="flex flex-col leading-tight">
          <span className="font-semibold text-atlas-light text-sm tracking-wide">
            {isMobile ? 'ATLAS' : 'ATLAS - Analytical Tracking'}
          </span>
          {!isMobile && periodText && (
            <span className="text-atlas-muted text-xs">{periodText}</span>
          )}
        </div>
      </div>

      {/* Loading indicator */}
      <LoadingIndicator />
    </header>
  );
};
