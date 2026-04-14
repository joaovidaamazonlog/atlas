import React from 'react';
import { useStore } from '../../store';
import { Spinner } from './Spinner';

export const LoadingIndicator: React.FC<{ className?: string }> = ({ className }) => {
  const isLoading = useStore((s) => s.isLoading);
  const loadingMessage = useStore((s) => s.loadingMessage);

  if (!isLoading) return null;

  return (
    <div className={`flex items-center gap-2 text-sm ${className ?? 'text-atlas-muted'}`}>
      <Spinner size="sm" />
      <span>{loadingMessage || 'Carregando...'}</span>
    </div>
  );
};
