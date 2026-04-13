/**
 * AreaAnalysisTab.tsx
 * ===================
 * Aba de análise de área.
 * Filtra prospects por estado e decisão (Go/No Go/Todos).
 * Filtro fixo: Status = Prospect (não exibido ao usuário).
 */

import { useState, useMemo } from 'react';
import { useStore } from '../../store';
import { getUniqueValues } from '../../store/actions/dataActions';

interface AreaStats {
  total: number;
  go: number;
  noGo: number;
  approvalRate: number;
}

export default function AreaAnalysisTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const applyFilters = useStore((s) => s.applyFilters);

  const [selectedState, setSelectedState] = useState('all');
  const [selectedDecision, setSelectedDecision] = useState('all');
  const [stats, setStats] = useState<AreaStats | null>(null);

  // States from prospects only
  const stateOptions = useMemo(() => {
    const prospects = allMarkersData.filter((p) => p.status === 'Prospect');
    return getUniqueValues(prospects, 'state').sort();
  }, [allMarkersData]);

  const handleAnalyze = () => {
    // Build filters: always status = Prospect
    const filters: Parameters<typeof applyFilters>[0] = {
      selectedStatuses: ['Prospect'],
    };

    // Apply state filter via post-filter (state is not in FilterState, so we filter manually)
    applyFilters(filters);

    // Compute stats from the prospects matching state + decision
    const prospects = allMarkersData.filter((p) => {
      if (p.status !== 'Prospect') return false;
      if (selectedState !== 'all' && p.state !== selectedState) return false;
      if (selectedDecision !== 'all' && p.decision !== selectedDecision) return false;
      return true;
    });

    const go = prospects.filter((p) => p.decision === 'Go').length;
    const noGo = prospects.filter((p) => p.decision === 'No Go').length;
    const total = prospects.length;
    const approvalRate = total > 0 ? Math.round((go / total) * 100) : 0;

    setStats({ total, go, noGo, approvalRate });
  };

  // Count from currently filtered data for live feedback
  const filteredProspects = useMemo(
    () => currentFilteredData.filter((p) => p.status === 'Prospect'),
    [currentFilteredData]
  );

  return (
    <div className="p-3">
      {/* Estado */}
      <div className="mb-3">
        <label
          htmlFor="area-state"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Estado
        </label>
        <select
          id="area-state"
          value={selectedState}
          onChange={(e) => setSelectedState(e.target.value)}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          <option value="all">Todos os estados</option>
          {stateOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {/* Decisão */}
      <div className="mb-4">
        <label
          htmlFor="area-decision"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Decisão
        </label>
        <select
          id="area-decision"
          value={selectedDecision}
          onChange={(e) => setSelectedDecision(e.target.value)}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          <option value="all">Todos</option>
          <option value="Go">Go</option>
          <option value="No Go">No Go</option>
        </select>
      </div>

      {/* Filtro fixo informativo */}
      <div className="mb-4 px-3 py-2 rounded bg-atlas-darker border border-white/10 text-xs text-atlas-muted">
        Filtro fixo: <span className="text-atlas-accent font-medium">Status = Prospect</span>
      </div>

      {/* Botão Analisar */}
      <button
        type="button"
        onClick={handleAnalyze}
        className={[
          'w-full py-3 px-4 rounded bg-atlas-accent text-atlas-darker',
          'text-sm font-semibold transition-colors duration-150',
          'hover:bg-amber-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent',
          'min-h-[44px] mb-4',
        ].join(' ')}
      >
        Analisar Área
      </button>

      {/* Estatísticas */}
      {stats && (
        <div className="rounded border border-white/10 bg-atlas-darker overflow-hidden">
          <div className="px-3 py-2 border-b border-white/10">
            <p className="text-xs font-semibold text-atlas-muted uppercase tracking-wide">
              Estatísticas
            </p>
          </div>
          <div className="grid grid-cols-2 gap-px bg-white/10">
            <StatCell label="Total Prospects" value={String(stats.total)} />
            <StatCell label="Taxa de Aprovação" value={`${stats.approvalRate}%`} accent />
            <StatCell label="Go" value={String(stats.go)} positive />
            <StatCell label="No Go" value={String(stats.noGo)} negative />
          </div>
          {filteredProspects.length > 0 && filteredProspects.length !== stats.total && (
            <div className="px-3 py-2 text-xs text-atlas-muted border-t border-white/10">
              {filteredProspects.length} prospects no mapa atual
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCell({
  label,
  value,
  accent,
  positive,
  negative,
}: {
  label: string;
  value: string;
  accent?: boolean;
  positive?: boolean;
  negative?: boolean;
}) {
  const valueColor = accent
    ? 'text-atlas-accent'
    : positive
      ? 'text-green-400'
      : negative
        ? 'text-red-400'
        : 'text-atlas-light';

  return (
    <div className="bg-atlas-navy px-3 py-3">
      <p className="text-xs text-atlas-muted mb-1">{label}</p>
      <p className={`text-lg font-bold ${valueColor}`}>{value}</p>
    </div>
  );
}
