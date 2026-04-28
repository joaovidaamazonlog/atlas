/**
 * useRowVirtualization.ts
 * =======================
 * Helper compartilhado para aplicar virtualização de linhas em tabelas
 * grandes, seguindo o padrão já testado em `StationsTable.tsx`.
 *
 * Comportamento
 * -------------
 * - Se `rowCount <= threshold` (default 100), o virtualizador fica
 *   desligado (`enabled=false`) e o caller renderiza todas as linhas
 *   diretamente no DOM.
 * - Se `rowCount > threshold`, o virtualizador é ligado; o caller usa
 *   `virtualizer.getVirtualItems()` para renderizar apenas as linhas
 *   visíveis (+ overscan).
 *
 * O container scrollável deve receber o `parentRef` retornado e usar
 * `containerStyle` para aplicar altura máxima e `overflowY: 'auto'`.
 *
 * Veja `StationsTable.tsx` como implementação de referência.
 */

import { useRef } from 'react';
import { useVirtualizer, type Virtualizer } from '@tanstack/react-virtual';

export interface RowVirtualizationOptions {
  /** Quantidade total de linhas a renderizar. */
  rowCount: number;
  /** Altura estimada (em px) de cada linha. */
  rowHeight: number;
  /** Acima deste valor de linhas, virtualiza. Default: 100. */
  threshold?: number;
  /** Altura máxima (em px) do container scrollável. Default: 400. */
  maxHeight?: number;
  /** Overscan do virtualizador. Default: 10. */
  overscan?: number;
}

export interface RowVirtualizationResult {
  /** Ref a ser conectada ao container scrollável. */
  parentRef: React.RefObject<HTMLDivElement>;
  /** Instância do virtualizer do @tanstack/react-virtual. */
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  /** True quando a virtualização está ligada (rowCount > threshold). */
  enabled: boolean;
  /** Style a ser aplicado no container scrollável (`parentRef`). */
  containerStyle: {
    height: number;
    overflowY: 'auto';
  };
}

export function useRowVirtualization(
  opts: RowVirtualizationOptions,
): RowVirtualizationResult {
  const parentRef = useRef<HTMLDivElement>(null);
  const threshold = opts.threshold ?? 100;
  const maxHeight = opts.maxHeight ?? 400;
  const overscan = opts.overscan ?? 10;
  const enabled = opts.rowCount > threshold;

  const virtualizer = useVirtualizer({
    count: opts.rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => opts.rowHeight,
    enabled,
    overscan,
  });

  return {
    parentRef,
    virtualizer,
    enabled,
    containerStyle: {
      height: Math.min(opts.rowCount * opts.rowHeight, maxHeight),
      overflowY: 'auto',
    },
  };
}
