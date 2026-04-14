/**
 * AreaAnalysisTab.tsx
 * ===================
 * Aba de análise de área — porta fiel da versão vanilla (ui-manager.js).
 *
 * Desktop/Tablet: painel lateral com overview global, motivos de No Go,
 *   resultado filtrado e botão "Ver detalhamento por Estado" (tabela expansível).
 * Mobile: resultado inline no painel de controles (sem painel lateral).
 */

import { useState, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../store';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { getUniqueValues } from '../../store/actions/dataActions';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const NO_GO_REASONS = [
  'Sem oportunidade próxima',
  'Fora de jurisdição',
  'Não avaliado por falta de coordenadas',
];

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

interface NoGoReasonCount {
  reason: string;
  count: number;
  pct: string;
}

interface Overview {
  total: number;
  go: number;
  nogo: number;
  rate: string;
  noCoords: number;
  nogoReasonCounts: Record<string, number>;
}

interface FilteredStats {
  total: number;
  go: number;
  nogo: number;
  rate: string;
  nogoReasonRows: NoGoReasonCount[];
}

interface StateRow {
  uf: string;
  total: number;
  go: number;
  nogo: number;
  rate: string;
}

// ---------------------------------------------------------------------------
// Funções puras (portadas de ui-manager.js)
// ---------------------------------------------------------------------------

function getGlobalOverview(allMarkersData: Partner[]): Overview {
  const allProspects = allMarkersData.filter((m) => m.status === 'Prospect');
  const noCoords = allProspects.filter((m) => !m.lat || !m.lon).length;
  const evaluated = allProspects.filter((m) => m.decision);
  const go = evaluated.filter((p) => p.decision === 'Go').length;
  const nogo = evaluated.filter((p) => p.decision === 'No Go').length;
  const rate = evaluated.length > 0 ? ((go / evaluated.length) * 100).toFixed(1) : '0.0';
  const nogoReasonCounts: Record<string, number> = {};
  NO_GO_REASONS.forEach((r) => {
    nogoReasonCounts[r] = evaluated.filter((p) => p.decision === 'No Go' && p.reason === r).length;
  });
  return { total: evaluated.length, go, nogo, rate, noCoords, nogoReasonCounts };
}

function getFilteredStats(prospects: Partner[], nogo: number): FilteredStats {
  const total = prospects.length;
  const go = prospects.filter((p) => p.decision === 'Go').length;
  const fNogo = prospects.filter((p) => p.decision === 'No Go').length;
  const rate = total > 0 ? ((go / total) * 100).toFixed(1) : '0.0';
  const nogoReasonRows = NO_GO_REASONS.map((r) => {
    const count = prospects.filter((p) => p.decision === 'No Go' && p.reason === r).length;
    const pct = fNogo > 0 ? ((count / fNogo) * 100).toFixed(1) : '0.0';
    return { reason: r, count, pct };
  });
  return { total, go, nogo: fNogo, rate, nogoReasonRows };
}

function getStatsByState(prospects: Partner[]): StateRow[] {
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
      return { uf, total, go: s.go, nogo: s.nogo, rate: total > 0 ? ((s.go / total) * 100).toFixed(0) : '0' };
    });
}

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function StatBox({ value, label, color }: { value: string | number; label: string; color?: string }) {
  return (
    <div className="text-center flex-1">
      <div className={`text-xl font-bold ${color ?? 'text-atlas-light'}`}>{value}</div>
      <div className="text-xs text-atlas-muted">{label}</div>
    </div>
  );
}

function NoGoTable({ rows, title }: { rows: NoGoReasonCount[]; title: string }) {
  return (
    <div className="mt-2">
      <p className="text-xs font-semibold text-atlas-muted mb-1">{title}</p>
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-white/5">
            <th className="text-left px-2 py-1 text-atlas-muted font-medium">Motivo</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">#</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">% No Go</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.reason} className="border-t border-white/5">
              <td className="px-2 py-1 text-atlas-light">{r.reason}</td>
              <td className="px-2 py-1 text-center text-atlas-light">{r.count}</td>
              <td className="px-2 py-1 text-center text-atlas-muted">{r.pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StateTable({ rows }: { rows: StateRow[] }) {
  return (
    <div className="mt-3 max-h-56 overflow-y-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-atlas-darker">
          <tr>
            <th className="text-left px-2 py-1 text-atlas-muted font-medium">UF</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">Total</th>
            <th className="text-center px-2 py-1 text-green-400 font-medium">Go</th>
            <th className="text-center px-2 py-1 text-red-400 font-medium">No Go</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">Aprov.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.uf} className="border-t border-white/5">
              <td className="px-2 py-1 font-semibold text-atlas-light">{r.uf}</td>
              <td className="px-2 py-1 text-center text-atlas-light">{r.total}</td>
              <td className="px-2 py-1 text-center text-green-400">{r.go}</td>
              <td className="px-2 py-1 text-center text-red-400">{r.nogo}</td>
              <td className="px-2 py-1 text-center text-atlas-muted">{r.rate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Painel de resultados (desktop/tablet) — painel lateral fixo
// ---------------------------------------------------------------------------

interface ResultPanelProps {
  overview: Overview;
  filtered: FilteredStats | null;
  stateFilter: string;
  decisionFilter: string;
  stateRows: StateRow[];
  showStateTable: boolean;
  onToggleStateTable: () => void;
  onClose: () => void;
}

function ResultPanel({
  overview,
  filtered,
  stateFilter,
  decisionFilter,
  stateRows,
  showStateTable,
  onToggleStateTable,
  onClose,
}: ResultPanelProps) {
  const hasStateFilter = stateFilter !== 'all';
  const hasFilter = stateFilter !== 'all' || decisionFilter !== 'all';

  const overviewNoGoRows: NoGoReasonCount[] = NO_GO_REASONS.map((r) => ({
    reason: r,
    count: overview.nogoReasonCounts[r] ?? 0,
    pct: overview.nogo > 0 ? (((overview.nogoReasonCounts[r] ?? 0) / overview.nogo) * 100).toFixed(1) : '0.0',
  }));

  return (
    <div
      className="fixed overflow-y-auto flex flex-col"
      style={{
        top: '56px',
        right: '0',
        bottom: '0',
        width: 'clamp(360px, 28vw, 480px)',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: 'var(--color-navy)',
        borderLeft: '1px solid var(--border-color)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-white/10">
        <span className="font-semibold text-atlas-light text-sm">Análise de Área — Prospects</span>
        <button onClick={onClose} aria-label="Fechar painel" className="text-atlas-muted hover:text-atlas-light transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* Overview global */}
        <div className="rounded-lg bg-white/5 p-3">
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-3">Overview Geral</p>
          <div className="flex gap-2">
            <StatBox value={overview.total} label="Avaliados" />
            <StatBox value={overview.go} label="Go" color="text-green-400" />
            <StatBox value={overview.nogo} label="No Go" color="text-red-400" />
            <StatBox value={`${overview.rate}%`} label="Aprovação" color="text-blue-400" />
          </div>

          {overview.noCoords > 0 && (
            <div className="mt-3 px-3 py-2 rounded bg-yellow-500/10 border-l-2 border-yellow-400 text-xs text-atlas-muted">
              ⚠️ <strong>{overview.noCoords}</strong> lead(s) sem lat/lon — não avaliados
            </div>
          )}

          {/* Motivos de No Go globais — só quando não há filtro de estado */}
          {!hasStateFilter && overview.nogo > 0 && (
            <NoGoTable rows={overviewNoGoRows} title="Detalhamento de No Go:" />
          )}
        </div>

        {/* Resultado filtrado */}
        {hasFilter && filtered && (
          <div className="rounded-lg bg-white/5 p-3">
            <p className="text-xs uppercase tracking-wide text-atlas-muted mb-1">
              {hasStateFilter && <span>Estado: <strong className="text-atlas-light">{stateFilter}</strong></span>}
              {decisionFilter !== 'all' && <span> | Decisão: <strong className="text-atlas-light">{decisionFilter}</strong></span>}
            </p>
            {filtered.total === 0 ? (
              <p className="text-xs text-atlas-muted">Nenhum prospect encontrado.</p>
            ) : (
              <>
                <div className="flex gap-2 mt-2">
                  <StatBox value={filtered.total} label="Total" />
                  <StatBox value={filtered.go} label="Go" color="text-green-400" />
                  <StatBox value={filtered.nogo} label="No Go" color="text-red-400" />
                  <StatBox value={`${filtered.rate}%`} label="Aprovação" color="text-blue-400" />
                </div>
                {hasStateFilter && filtered.nogo > 0 && (
                  <NoGoTable rows={filtered.nogoReasonRows} title={`Detalhamento de No Go — ${stateFilter}:`} />
                )}
              </>
            )}
          </div>
        )}

        {/* Botão detalhamento por estado — só sem filtro de estado */}
        {!hasStateFilter && (
          <button
            type="button"
            onClick={onToggleStateTable}
            className="w-full py-2 px-3 rounded border border-blue-500/50 text-blue-400 text-xs hover:bg-blue-500/10 transition-colors"
          >
            {showStateTable ? '▲ Ocultar detalhamento por Estado' : '▼ Ver detalhamento por Estado'}
          </button>
        )}

        {showStateTable && !hasStateFilter && stateRows.length > 0 && (
          <div className="rounded-lg bg-white/5 p-3">
            <p className="text-xs font-semibold text-atlas-muted mb-1">Detalhamento por Estado</p>
            <StateTable rows={stateRows} />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AreaAnalysisTab principal
// ---------------------------------------------------------------------------

export default function AreaAnalysisTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const applyFilters = useStore((s) => s.applyFilters);
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';

  const [selectedState, setSelectedState] = useState('all');
  const [selectedDecision, setSelectedDecision] = useState('all');

  // Resultado da análise
  const [analysisResult, setAnalysisResult] = useState<{
    overview: Overview;
    filtered: FilteredStats;
    stateRows: StateRow[];
    stateFilter: string;
    decisionFilter: string;
  } | null>(null);

  const [showPanel, setShowPanel] = useState(false);
  const [showStateTable, setShowStateTable] = useState(false);

  const stateOptions = useMemo(() => {
    const prospects = allMarkersData.filter((p) => p.status === 'Prospect');
    return getUniqueValues(prospects, 'state').sort();
  }, [allMarkersData]);

  const handleAnalyze = useCallback(() => {
    applyFilters({ selectedStatuses: ['Prospect'] });

    const allProspects = allMarkersData.filter((p) => p.status === 'Prospect');
    const filteredProspects = allProspects.filter((p) => {
      if (!p.decision) return false;
      if (selectedState !== 'all' && p.state !== selectedState) return false;
      if (selectedDecision !== 'all' && p.decision !== selectedDecision) return false;
      return true;
    });

    const overview = getGlobalOverview(allMarkersData);
    const filtered = getFilteredStats(filteredProspects, overview.nogo);
    const stateRows = getStatsByState(allProspects.filter((p) => !!p.decision));

    setAnalysisResult({
      overview,
      filtered,
      stateRows,
      stateFilter: selectedState,
      decisionFilter: selectedDecision,
    });
    setShowPanel(true);
    setShowStateTable(false);
  }, [allMarkersData, applyFilters, selectedState, selectedDecision]);

  const handleClose = useCallback(() => {
    setShowPanel(false);
    setShowStateTable(false);
  }, []);

  return (
    <>
      {/* Painel lateral de resultados — desktop e tablet */}
      {!isMobile && showPanel && analysisResult && (
        createPortal(
          <ResultPanel
            overview={analysisResult.overview}
            filtered={analysisResult.filtered}
            stateFilter={analysisResult.stateFilter}
            decisionFilter={analysisResult.decisionFilter}
            stateRows={analysisResult.stateRows}
            showStateTable={showStateTable}
            onToggleStateTable={() => setShowStateTable((v) => !v)}
            onClose={handleClose}
          />,
          document.body
        )
      )}

      {/* Formulário de filtros */}
      <div className="p-3">
        {/* Estado */}
        <div className="mb-3">
          <label htmlFor="area-state" className="block text-xs font-medium text-atlas-muted mb-1">
            Estado
          </label>
          <select
            id="area-state"
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          >
            <option value="all">Todos os estados</option>
            {stateOptions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        {/* Decisão */}
        <div className="mb-4">
          <label htmlFor="area-decision" className="block text-xs font-medium text-atlas-muted mb-1">
            Decisão
          </label>
          <select
            id="area-decision"
            value={selectedDecision}
            onChange={(e) => setSelectedDecision(e.target.value)}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          >
            <option value="all">Todos</option>
            <option value="Go">Go</option>
            <option value="No Go">No Go</option>
          </select>
        </div>

        <div className="mb-4 px-3 py-2 rounded bg-atlas-darker border border-white/10 text-xs text-atlas-muted">
          Filtro fixo: <span className="text-atlas-accent font-medium">Status = Prospect</span>
        </div>

        <button
          type="button"
          onClick={handleAnalyze}
          className="w-full py-3 px-4 rounded bg-atlas-accent text-white text-sm font-semibold hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent min-h-[44px] mb-4 transition-colors"
        >
          Analisar Área
        </button>

        {/* Mobile: resultado inline */}
        {isMobile && analysisResult && (
          <div className="flex flex-col gap-3">
            {/* Overview */}
            <div className="rounded-lg bg-white/5 p-3">
              <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2">Overview Geral</p>
              <div className="flex gap-2">
                <StatBox value={analysisResult.overview.total} label="Avaliados" />
                <StatBox value={analysisResult.overview.go} label="Go" color="text-green-400" />
                <StatBox value={analysisResult.overview.nogo} label="No Go" color="text-red-400" />
                <StatBox value={`${analysisResult.overview.rate}%`} label="Aprov." color="text-blue-400" />
              </div>
              {/* Motivos de No Go — mobile sempre mostra */}
              {analysisResult.overview.nogo > 0 && (
                <NoGoTable
                  rows={NO_GO_REASONS.map((r) => ({
                    reason: r,
                    count: analysisResult.overview.nogoReasonCounts[r] ?? 0,
                    pct: analysisResult.overview.nogo > 0
                      ? (((analysisResult.overview.nogoReasonCounts[r] ?? 0) / analysisResult.overview.nogo) * 100).toFixed(1)
                      : '0.0',
                  }))}
                  title="Detalhamento de No Go:"
                />
              )}
            </div>

            {/* Filtrado (se houver filtro) */}
            {(analysisResult.stateFilter !== 'all' || analysisResult.decisionFilter !== 'all') && (
              <div className="rounded-lg bg-white/5 p-3">
                <p className="text-xs text-atlas-muted mb-2">
                  {analysisResult.stateFilter !== 'all' && <span>Estado: <strong className="text-atlas-light">{analysisResult.stateFilter}</strong></span>}
                  {analysisResult.decisionFilter !== 'all' && <span> | Decisão: <strong className="text-atlas-light">{analysisResult.decisionFilter}</strong></span>}
                </p>
                <div className="flex gap-2">
                  <StatBox value={analysisResult.filtered.total} label="Total" />
                  <StatBox value={analysisResult.filtered.go} label="Go" color="text-green-400" />
                  <StatBox value={analysisResult.filtered.nogo} label="No Go" color="text-red-400" />
                  <StatBox value={`${analysisResult.filtered.rate}%`} label="Aprov." color="text-blue-400" />
                </div>
                {analysisResult.filtered.nogo > 0 && (
                  <NoGoTable rows={analysisResult.filtered.nogoReasonRows} title="Detalhamento de No Go:" />
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
