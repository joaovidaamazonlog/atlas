import React from 'react';
import { useStore } from '../../store';
import { Spinner } from './Spinner';

export const LoadingIndicator: React.FC = () => {
  const isLoading = useStore((s) => s.isLoading);
  const loadingMessage = useStore((s) => s.loadingMessage);

  if (!isLoading) return null;

  return (
    <div className="flex items-center gap-2 text-atlas-muted text-sm">
      <Spinner size="sm" />
      <span>{loadingMessage || 'Carregando...'}</span>
    </div>
  );
};
