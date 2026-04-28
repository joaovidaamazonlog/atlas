/**
 * AreaAnalysisTab.memo.test.tsx
 * =============================
 * Testes de estabilidade referencial dos memos aplicados em
 * `AreaAnalysisTab`.
 *
 * Valida via `renderHook` + `useMemo` diretamente:
 * - Dependências não mudam entre renders consecutivos → mesma
 *   referência retornada (`===`).
 * - Dependências mudam → valor estruturalmente igual ao produzido pela
 *   função pura aplicada aos novos argumentos.
 *
 * Essa abordagem isola a invariante de memoização (Requirement 4.9 e 6.6)
 * sem depender do componente inteiro montado.
 *
 * Referências: Requirements 4.8, 4.9, 6.6, 6.7
 */

import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useMemo } from 'react';
import type { Partner } from '../../store/types';
import {
  getGlobalOverview,
  getFilteredStats,
  getStatsByState,
} from '../../lib/areaAnalysisPure';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const FIXTURE_A: Partner[] = [
  {
    salesforce_id: 'sf1', store_id: null, name: 'P1', status: 'Prospect',
    lead_source: null, lat: -23.5, lon: -46.6, zip_code: null, city: null,
    state: 'SP', delivery_station: 'DSP2', supply_run: null,
    radius: 1000, capacity: 50, bucket: null, jurisdiction_type: null,
    hub_delivey_initiatives: null, HCP_rate_card: null, HCP_host_partner: null,
    launch_date: null, exited_date: null, decision: 'Go',
    reason: 'Seguir cadastro', bucket_ade: null, tooltip: '',
    decision_status: null, decision_reason_code: null, telefone: null,
    owner_id: null, adv_opportunity: null,
  } as unknown as Partner,
  {
    salesforce_id: 'sf2', store_id: null, name: 'P2', status: 'Prospect',
    lead_source: null, lat: -23.6, lon: -46.7, zip_code: null, city: null,
    state: 'RJ', delivery_station: 'DSP2', supply_run: null,
    radius: 1000, capacity: 50, bucket: null, jurisdiction_type: null,
    hub_delivey_initiatives: null, HCP_rate_card: null, HCP_host_partner: null,
    launch_date: null, exited_date: null, decision: 'No Go',
    reason: 'Fora de jurisdição', bucket_ade: null, tooltip: '',
    decision_status: null, decision_reason_code: null, telefone: null,
    owner_id: null, adv_opportunity: null,
  } as unknown as Partner,
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AreaAnalysisTab memoização — estabilidade referencial', () => {
  it('useMemo de overview retorna mesma referência quando deps não mudam', () => {
    const { result, rerender } = renderHook(
      ({ data }: { data: Partner[] }) =>
        useMemo(() => getGlobalOverview(data), [data]),
      { initialProps: { data: FIXTURE_A } },
    );
    const first = result.current;
    rerender({ data: FIXTURE_A }); // MESMA referência
    expect(result.current).toBe(first);
  });

  it('useMemo de overview retorna nova referência quando deps mudam', () => {
    const { result, rerender } = renderHook(
      ({ data }: { data: Partner[] }) =>
        useMemo(() => getGlobalOverview(data), [data]),
      { initialProps: { data: FIXTURE_A } },
    );
    const first = result.current;
    const FIXTURE_B = [...FIXTURE_A]; // nova referência de array
    rerender({ data: FIXTURE_B });
    expect(result.current).not.toBe(first);
    // Mas estruturalmente equivalente (mesmos números)
    expect(result.current).toEqual(first);
  });

  it('useMemo de filteredProspects é estável com (data, state, decision) iguais', () => {
    const { result, rerender } = renderHook(
      ({ data, state, decision }: {
        data: Partner[];
        state: string;
        decision: string;
      }) =>
        useMemo(() => {
          return data.filter((p) => {
            if (p.status !== 'Prospect') return false;
            if (!p.decision) return false;
            if (state !== 'all' && p.state !== state) return false;
            if (decision !== 'all' && p.decision !== decision) return false;
            return true;
          });
        }, [data, state, decision]),
      { initialProps: { data: FIXTURE_A, state: 'all', decision: 'all' } },
    );
    const first = result.current;
    rerender({ data: FIXTURE_A, state: 'all', decision: 'all' });
    expect(result.current).toBe(first);

    // Mudança em `state` → nova referência
    rerender({ data: FIXTURE_A, state: 'SP', decision: 'all' });
    expect(result.current).not.toBe(first);
    // Mas consistente com função pura aplicada diretamente
    expect(result.current).toEqual(
      FIXTURE_A.filter((p) => p.status === 'Prospect' && p.decision && p.state === 'SP'),
    );
  });

  it('useMemo encadeado: filteredStats depende de filteredProspects', () => {
    const { result, rerender } = renderHook(
      ({ data }: { data: Partner[] }) => {
        const filtered = useMemo(
          () => data.filter((p) => p.status === 'Prospect' && p.decision),
          [data],
        );
        const stats = useMemo(() => getFilteredStats(filtered), [filtered]);
        return { filtered, stats };
      },
      { initialProps: { data: FIXTURE_A } },
    );
    const firstFiltered = result.current.filtered;
    const firstStats = result.current.stats;

    // Re-render com mesma data: ambos preservam referência
    rerender({ data: FIXTURE_A });
    expect(result.current.filtered).toBe(firstFiltered);
    expect(result.current.stats).toBe(firstStats);
  });

  it('stateRows é estável com allEvaluatedProspects estável', () => {
    const { result, rerender } = renderHook(
      ({ data }: { data: Partner[] }) => {
        const evaluated = useMemo(
          () => data.filter((p) => p.status === 'Prospect' && !!p.decision),
          [data],
        );
        return useMemo(() => getStatsByState(evaluated), [evaluated]);
      },
      { initialProps: { data: FIXTURE_A } },
    );
    const first = result.current;
    rerender({ data: FIXTURE_A });
    expect(result.current).toBe(first);
  });
});
