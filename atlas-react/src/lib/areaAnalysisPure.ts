/**
 * areaAnalysisPure.ts
 * ===================
 * Funções puras extraídas de `AreaAnalysisTab.tsx` para viabilizar:
 * 1. Memoização com `useMemo` no componente (dependências explícitas).
 * 2. Property-based testing isolado (fast-check) sem depender do React.
 *
 * Nenhuma lógica nova — apenas reorganização mecânica.
 */

import type { Partner } from '../store/types';

export const NO_GO_REASONS = [
  'Sem oportunidade próxima',
  'Fora de jurisdição',
  'Não avaliado por falta de coordenadas',
] as const;

export interface NoGoReasonCount {
  reason: string;
  count: number;
  pct: string;
}

export interface Overview {
  total: number;
  go: number;
  nogo: number;
  rate: string;
  noCoords: number;
  nogoReasonCounts: Record<string, number>;
}

export interface FilteredStats {
  total: number;
  go: number;
  nogo: number;
  rate: string;
  nogoReasonRows: NoGoReasonCount[];
}

export interface StateRow {
  uf: string;
  total: number;
  go: number;
  nogo: number;
  rate: string;
}

export function getGlobalOverview(allMarkersData: Partner[]): Overview {
  const allProspects = allMarkersData.filter((m) => m.status === 'Prospect');
  const noCoords = allProspects.filter((m) => !m.lat || !m.lon).length;
  const evaluated = allProspects.filter((m) => m.decision);
  const go = evaluated.filter((p) => p.decision === 'Go').length;
  const nogo = evaluated.filter((p) => p.decision === 'No Go').length;
  const rate = evaluated.length > 0 ? ((go / evaluated.length) * 100).toFixed(1) : '0.0';
  const nogoReasonCounts: Record<string, number> = {};
  NO_GO_REASONS.forEach((r) => {
    nogoReasonCounts[r] = evaluated.filter(
      (p) => p.decision === 'No Go' && p.reason === r,
    ).length;
  });
  return { total: evaluated.length, go, nogo, rate, noCoords, nogoReasonCounts };
}

export function getFilteredStats(prospects: Partner[]): FilteredStats {
  const total = prospects.length;
  const go = prospects.filter((p) => p.decision === 'Go').length;
  const fNogo = prospects.filter((p) => p.decision === 'No Go').length;
  const rate = total > 0 ? ((go / total) * 100).toFixed(1) : '0.0';
  const nogoReasonRows: NoGoReasonCount[] = NO_GO_REASONS.map((r) => {
    const count = prospects.filter((p) => p.decision === 'No Go' && p.reason === r).length;
    const pct = fNogo > 0 ? ((count / fNogo) * 100).toFixed(1) : '0.0';
    return { reason: r, count, pct };
  });
  return { total, go, nogo: fNogo, rate, nogoReasonRows };
}

export function getStatsByState(prospects: Partner[]): StateRow[] {
  const byState: Record<string, { go: number; nogo: number }> = {};
  prospects.forEach((p) => {
    const uf = p.state || 'N/A';
    if (!byState[uf]) byState[uf] = { go: 0, nogo: 0 };
    if (p.decision === 'Go') byState[uf].go++;
    else byState[uf].nogo++;
  });
  return Object.entries(byState)
    .sort((a, b) => (b[1].go + b[1].nogo) - (a[1].go + a[1].nogo))
    .map(([uf, s]) => {
      const total = s.go + s.nogo;
      return {
        uf,
        total,
        go: s.go,
        nogo: s.nogo,
        rate: total > 0 ? ((s.go / total) * 100).toFixed(0) : '0',
      };
    });
}
