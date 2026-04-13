import React from 'react';

interface FABProps {
  icon: React.ReactNode;
  onClick: () => void;
  label: string;
  className?: string;
}

export const FAB: React.FC<FABProps> = ({ icon, onClick, label, className = '' }) => {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={`touch-target rounded-full bg-atlas-accent text-atlas-darker shadow-lg hover:brightness-110 active:scale-95 transition-all duration-150 ${className}`}
    >
      {icon}
    </button>
  );
};
