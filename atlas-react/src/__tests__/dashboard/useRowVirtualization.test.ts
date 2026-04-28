/**
 * useRowVirtualization.test.ts
 * ============================
 * Testes unitários do hook compartilhado de virtualização de linhas.
 *
 * Valida:
 * - `enabled=false` quando `rowCount <= threshold`.
 * - `enabled=true` quando `rowCount > threshold`.
 * - `containerStyle.height` respeita o menor entre
 *   `rowCount * rowHeight` e `maxHeight`.
 * - Valores default aplicados quando argumentos opcionais omitidos.
 *
 * Referências: Requirements 2.1, 2.2, 2.3, 3.1, 3.2, 3.3
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useRowVirtualization } from '../../components/dashboard/useRowVirtualization';

describe('useRowVirtualization', () => {
  it('desliga a virtualização quando rowCount <= threshold (default 100)', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 50, rowHeight: 36 }),
    );
    expect(result.current.enabled).toBe(false);
  });

  it('desliga no limite exato (rowCount === threshold)', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 100, rowHeight: 36 }),
    );
    expect(result.current.enabled).toBe(false);
  });

  it('liga a virtualização quando rowCount > threshold', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 101, rowHeight: 36 }),
    );
    expect(result.current.enabled).toBe(true);
  });

  it('respeita threshold customizado', () => {
    const small = renderHook(() =>
      useRowVirtualization({ rowCount: 10, rowHeight: 36, threshold: 5 }),
    );
    expect(small.result.current.enabled).toBe(true);

    const big = renderHook(() =>
      useRowVirtualization({ rowCount: 10, rowHeight: 36, threshold: 50 }),
    );
    expect(big.result.current.enabled).toBe(false);
  });

  it('containerStyle.height respeita o menor entre rowCount*rowHeight e maxHeight', () => {
    // 50 linhas × 36px = 1800, maxHeight default = 400 → 400
    const many = renderHook(() =>
      useRowVirtualization({ rowCount: 50, rowHeight: 36 }),
    );
    expect(many.result.current.containerStyle.height).toBe(400);

    // 5 linhas × 36px = 180, maxHeight default = 400 → 180
    const few = renderHook(() =>
      useRowVirtualization({ rowCount: 5, rowHeight: 36 }),
    );
    expect(few.result.current.containerStyle.height).toBe(180);

    // maxHeight customizado
    const custom = renderHook(() =>
      useRowVirtualization({ rowCount: 50, rowHeight: 36, maxHeight: 200 }),
    );
    expect(custom.result.current.containerStyle.height).toBe(200);
  });

  it('containerStyle sempre tem overflowY=auto', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 5, rowHeight: 36 }),
    );
    expect(result.current.containerStyle.overflowY).toBe('auto');
  });

  it('retorna parentRef como React ref object', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 5, rowHeight: 36 }),
    );
    expect(result.current.parentRef).toHaveProperty('current');
    // ref começa null até ser conectada a um DOM node
    expect(result.current.parentRef.current).toBeNull();
  });

  it('lida com rowCount=0 sem erro (tabela vazia)', () => {
    const { result } = renderHook(() =>
      useRowVirtualization({ rowCount: 0, rowHeight: 36 }),
    );
    expect(result.current.enabled).toBe(false);
    expect(result.current.containerStyle.height).toBe(0);
  });
});
