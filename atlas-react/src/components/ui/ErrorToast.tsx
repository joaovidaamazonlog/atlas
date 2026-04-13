import React, { useEffect, useState } from 'react';
import { useStore } from '../../store';

export const ErrorToast: React.FC = () => {
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (error) {
      setVisible(true);
    } else {
      setVisible(false);
    }
  }, [error]);

  const handleClose = () => {
    setVisible(false);
    // Delay clearing the error to allow exit animation
    setTimeout(() => setError(null), 300);
  };

  if (!error) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{ zIndex: 'var(--z-toast)' as unknown as number }}
      className={`fixed top-4 right-4 max-w-sm w-full bg-red-900/90 border border-red-700 text-atlas-light rounded-lg shadow-lg p-4 flex items-start gap-3 transition-all duration-300 ${
        visible ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2 pointer-events-none'
      }`}
    >
      <div className="flex-1 text-sm leading-snug">{error}</div>
      <button
        onClick={handleClose}
        aria-label="Fechar mensagem de erro"
        className="touch-target shrink-0 text-atlas-muted hover:text-atlas-light transition-colors duration-150 -mt-1 -mr-1"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    </div>
  );
};
