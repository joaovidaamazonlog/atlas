/**
 * AreaAnalysisTab.tsx
 */

import { useState, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { getUniqueValues } from '../../store/actions/dataActions';
import type { Partner } from '../../store/types';

const NO_GO_REASONS = [
  'Sem oportunidade próxima',
  'Fora de jurisdição',
  'Não avaliado por falta de coordenadas',
];

interface NoGoReasonCount { reason: string; count: number; pct: string; }
interface Overview { total: number; go: number; nogo: number; rate: string; noCoords: number; nogoReasonCounts: Record<string, number>; }
interface FilteredStats { total: number; go: number; nogo: number; rate: string; nogoReasonRows: NoGoReasonCount[]; }
interface StateRow { uf: string; total: number; go: number; nogo: number; rate: string; }

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

function getFilteredStats(prospects: Partner[]): FilteredStats {
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

function StatBox({ value, label, color }: { value: string | number; label: string; color?: string }) {
  return (
    <div className="text-center flex-1">
      <div className={`text-xl font-bold ${color ?? 'text-atlas-light'}`}>{value}</div>
      <div className="text-xs text-atlas-muted">{label}</div>
    </div>
  );
}

function NoGoTable({ rows, title }: { rows: NoGoReasonCount[]; title: string }) {
  const { t } = useTranslation();
  return (
    <div className="mt-2">
      <p className="text-xs font-semibold text-atlas-muted mb-1">{title}</p>
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-atlas-dark">
            <th className="text-left px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.table_reason')}</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.table_count')}</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.table_pct_no_go')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.reason} className="border-t border-[var(--border-color)]">
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
  const { t } = useTranslation();
  return (
    <div className="mt-3 max-h-56 overflow-y-auto">
      <table className="w-full text-xs border-collapse">
        <thead className="sticky top-0 bg-atlas-darker">
          <tr>
            <th className="text-left px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.state_table_uf')}</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.state_table_total')}</th>
            <th className="text-center px-2 py-1 text-green-400 font-medium">{t('common.go')}</th>
            <th className="text-center px-2 py-1 text-red-400 font-medium">{t('common.no_go')}</th>
            <th className="text-center px-2 py-1 text-atlas-muted font-medium">{t('area_analysis.state_table_approval')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.uf} className="border-t border-[var(--border-color)]">
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
// LeadCard — card individual de lead avaliado
// ---------------------------------------------------------------------------

function LeadCard({ lead, onSearch }: { lead: Partner; onSearch: (lead: Partner) => void }) {
  const { t } = useTranslation();
  const isGo = lead.decision === 'Go';
  const hasCoords = lead.lat != null && lead.lon != null;
  return (
    <div className="rounded-lg bg-atlas-darker p-3 flex flex-col gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-atlas-light leading-tight flex-1">{lead.name}</span>
        <span
          className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-semibold ${
            isGo ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
          }`}
        >
          {lead.decision}
        </span>
      </div>

      {lead.reason && (
        <p className="text-xs text-atlas-muted leading-snug">{lead.reason}</p>
      )}

      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="text-xs text-atlas-muted/60">
          {lead.city ? `${lead.city}${lead.state ? `, ${lead.state}` : ''}` : lead.state ?? ''}
        </span>
        {hasCoords && (
          <button
            type="button"
            onClick={() => onSearch(lead)}
            title={t('common.visualize_on_map')}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-semibold text-atlas-accent border border-atlas-accent/30 hover:bg-atlas-accent/10 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            {t('common.visualize')}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// LeadsPanel — lista de leads avaliados com busca
// ---------------------------------------------------------------------------

function LeadsPanel({ leads }: { leads: Partner[] }) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    const sorted = [...leads].sort((a, b) => {
      if (a.decision === 'Go' && b.decision !== 'Go') return -1;
      if (a.decision !== 'Go' && b.decision === 'Go') return 1;
      return a.name.localeCompare(b.name);
    });
    if (!search.trim()) return sorted;
    const q = search.toLowerCase();
    return sorted.filter(
      (l) => l.name.toLowerCase().includes(q) || (l.city ?? '').toLowerCase().includes(q) || (l.state ?? '').toLowerCase().includes(q)
    );
  }, [leads, search]);

  const handleSearch = useCallback((lead: Partner) => {
    if (lead.lat != null && lead.lon != null) {
      window.dispatchEvent(new CustomEvent('atlas:open-partner-popup', {
        detail: { salesforceId: lead.salesforce_id, lat: lead.lat, lon: lead.lon },
      }));
    }
  }, []);

  return (
    <div className="flex flex-col gap-2">
      {/* Título + busca — card próprio */}
      <div className="rounded-lg bg-atlas-darker p-3 flex flex-col gap-2">
        <p className="text-xs font-semibold text-atlas-muted uppercase tracking-wide">
          {t('area_analysis.leads_title')} <span className="text-atlas-light font-bold ml-1">{leads.length}</span>
        </p>
        <div className="flex items-center rounded bg-atlas-darker border border-[var(--border-color)] overflow-hidden focus-within:border-atlas-accent transition-colors">
          <span className="px-2 text-xs text-atlas-muted">🔍</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('area_analysis.leads_search_placeholder')}
            className="flex-1 bg-transparent border-none outline-none text-xs text-atlas-light py-2 pr-2 placeholder:text-atlas-muted/50"
          />
          {search && (
            <button type="button" onClick={() => setSearch('')} className="px-2 text-xs text-atlas-muted hover:text-atlas-light">✕</button>
          )}
        </div>
      </div>

      {/* Cards individuais */}
      <div className="flex flex-col gap-2 max-h-96 overflow-y-auto pr-0.5">
        {filtered.length === 0 ? (
          <p className="text-xs text-atlas-muted text-center py-4">{t('area_analysis.leads_not_found')}</p>
        ) : (
          filtered.map((lead) => (
            <LeadCard key={lead.salesforce_id} lead={lead} onSearch={handleSearch} />
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResultPanel — painel lateral fixo (desktop/tablet)
// ---------------------------------------------------------------------------

interface ResultPanelProps {
  overview: Overview;
  filtered: FilteredStats | null;
  stateFilter: string;
  decisionFilter: string;
  stateRows: StateRow[];
  leads: Partner[];
  showStateTable: boolean;
  onToggleStateTable: () => void;
  onClose: () => void;
}

function ResultPanel({
  overview, filtered, stateFilter, decisionFilter, stateRows, leads,
  showStateTable, onToggleStateTable, onClose,
}: ResultPanelProps) {
  const { t } = useTranslation();
  const hasStateFilter = stateFilter !== 'all';
  const hasFilter = stateFilter !== 'all' || decisionFilter !== 'all';

  const overviewNoGoRows: NoGoReasonCount[] = NO_GO_REASONS.map((r) => ({
    reason: r,
    count: overview.nogoReasonCounts[r] ?? 0,
    pct: overview.nogo > 0 ? (((overview.nogoReasonCounts[r] ?? 0) / overview.nogo) * 100).toFixed(1) : '0.0',
  }));

  return (
    <div
      className="fixed overflow-hidden flex flex-col"
      style={{
        top: '56px', right: '0', bottom: '0',
        width: 'clamp(360px, 28vw, 480px)',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: 'var(--color-navy)',
        borderLeft: '1px solid var(--border-color)',
      }}
    >
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-[var(--border-color)]">
        <span className="font-semibold text-atlas-light text-sm">{t('area_analysis.result_panel_title')}</span>
        <button onClick={onClose} aria-label={t('common.close')} className="text-atlas-muted hover:text-atlas-light transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* Overview */}
        <div className="rounded-lg bg-atlas-darker p-3">
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-3">{t('area_analysis.overview_label')}</p>
          <div className="flex gap-2">
            <StatBox value={overview.total} label={t('area_analysis.stat_evaluated')} />
            <StatBox value={overview.go} label={t('common.go')} color="text-green-400" />
            <StatBox value={overview.nogo} label={t('common.no_go')} color="text-red-400" />
            <StatBox value={`${overview.rate}%`} label={t('area_analysis.stat_approval')} color="text-blue-400" />
          </div>
          {overview.noCoords > 0 && (
            <div className="mt-3 px-3 py-2 rounded bg-yellow-500/10 border-l-2 border-yellow-400 text-xs text-atlas-muted">
              ⚠️ <strong>{overview.noCoords}</strong> {t('area_analysis.warning_no_coords', { count: overview.noCoords })}
            </div>
          )}
          {!hasStateFilter && overview.nogo > 0 && (
            <NoGoTable rows={overviewNoGoRows} title={t('area_analysis.no_go_detail_title')} />
          )}
        </div>

        {/* Filtrado */}
        {hasFilter && filtered && (
          <div className="rounded-lg bg-atlas-darker p-3">
            <p className="text-xs uppercase tracking-wide text-atlas-muted mb-1">
              {hasStateFilter && <span>Estado: <strong className="text-atlas-light">{stateFilter}</strong></span>}
              {decisionFilter !== 'all' && <span> | Decisão: <strong className="text-atlas-light">{decisionFilter}</strong></span>}
            </p>
            {filtered.total === 0 ? (
              <p className="text-xs text-atlas-muted">{t('area_analysis.no_prospect_found')}</p>
            ) : (
              <>
                <div className="flex gap-2 mt-2">
                  <StatBox value={filtered.total} label={t('area_analysis.stat_total')} />
                  <StatBox value={filtered.go} label={t('common.go')} color="text-green-400" />
                  <StatBox value={filtered.nogo} label={t('common.no_go')} color="text-red-400" />
                  <StatBox value={`${filtered.rate}%`} label={t('area_analysis.stat_approval')} color="text-blue-400" />
                </div>
                {hasStateFilter && filtered.nogo > 0 && (
                  <NoGoTable rows={filtered.nogoReasonRows} title={t('area_analysis.no_go_detail_state', { state: stateFilter })} />
                )}
              </>
            )}
          </div>
        )}

        {/* Toggle tabela por estado */}
        {!hasStateFilter && (
          <button
            type="button"
            onClick={onToggleStateTable}
            className="w-full py-2 px-3 rounded border border-atlas-accent/50 text-atlas-accent text-xs font-semibold hover:bg-atlas-accent/10 transition-colors flex items-center justify-center gap-1.5"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className={`w-3 h-3 transition-transform duration-200 ${showStateTable ? 'rotate-90' : ''}`} viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M7.293 4.293a1 1 0 011.414 0l5 5a1 1 0 010 1.414l-5 5a1 1 0 01-1.414-1.414L11.586 10 7.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          {showStateTable ? t('area_analysis.state_table_hide') : t('area_analysis.state_table_show')}
          </button>
        )}

        {showStateTable && !hasStateFilter && stateRows.length > 0 && (
          <div className="rounded-lg bg-atlas-darker p-3">
            <p className="text-xs font-semibold text-atlas-muted mb-1">{t('area_analysis.state_table_title')}</p>
            <StateTable rows={stateRows} />
          </div>
        )}

        {/* Cards de leads avaliados */}
        {leads.length > 0 && (
          <LeadsPanel leads={leads} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// HexSelectionSummary — resumo de hexes selecionados na aba Área
// ---------------------------------------------------------------------------

function HexSelectionSummary() {
  const { t } = useTranslation();
  const hexSelectionState = useStore((s) => s.hexSelectionState);
  const activeTab = useStore((s) => s.activeTab);
  const minAdv = useStore((s) => s.recruitableAnalysis.params.minAdv);
  const clearHexSelection = useStore((s) => s.clearHexSelection);

  if (activeTab !== 'area' || hexSelectionState.selectedHexIds.length === 0) {
    return null;
  }

  const { selectedHexIds, totalDemandDaily, totalDemandResidual } = hexSelectionState;
  const hasMinAdv = minAdv > 0;
  const pct = hasMinAdv ? ((totalDemandResidual / minAdv) * 100).toFixed(1) : null;

  return (
    <div className="mt-4 rounded-lg bg-atlas-accent/10 border border-atlas-accent/30 p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-atlas-accent uppercase tracking-wide">
          {t('area_analysis.hex_selection_title')}
        </p>
        <button
          type="button"
          onClick={clearHexSelection}
          className="text-xs text-atlas-muted hover:text-atlas-light transition-colors"
          aria-label="Limpar seleção de hexes"
        >
          {t('area_analysis.hex_selection_clear')}
        </button>
      </div>

      <div className="flex gap-2">
        <div className="text-center flex-1">
          <div className="text-lg font-bold text-atlas-accent">{selectedHexIds.length}</div>
          <div className="text-xs text-atlas-muted">{t('area_analysis.hex_selection_hexes')}</div>
        </div>
        <div className="text-center flex-1">
          <div className="text-lg font-bold text-atlas-light">{totalDemandDaily.toFixed(1)}</div>
          <div className="text-xs text-atlas-muted">{t('area_analysis.hex_selection_daily_demand')}</div>
        </div>
        <div className="text-center flex-1">
          <div className="text-lg font-bold text-green-400">{totalDemandResidual.toFixed(1)}</div>
          <div className="text-xs text-atlas-muted">{t('area_analysis.hex_selection_residual_demand')}</div>
        </div>
      </div>

      {hasMinAdv && pct !== null && (
        <div className="mt-1 px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-xs text-atlas-muted">
          {t('area_analysis.hex_selection_vs_adv')}{' '}
          <span className="text-atlas-light font-semibold">
            {totalDemandResidual.toFixed(1)} / {minAdv}
          </span>{' '}
          <span className={parseFloat(pct) >= 100 ? 'text-green-400 font-semibold' : 'text-yellow-400 font-semibold'}>
            ({pct}%)
          </span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CapOpportunityPanel — painel lateral de oportunidades de aumento de ADV
// ---------------------------------------------------------------------------

function CapOpportunityPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const allMarkersData = useStore((s) => s.allMarkersData);
  const selectedPartnerId = useStore((s) => s.capOpportunityState.selectedPartnerId);
  const setSelectedCapOpportunity = useStore((s) => s.setSelectedCapOpportunity);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);

  const opportunities = useMemo(() => {
    return allMarkersData
      .filter((p) => p.status === 'Active' && p.adv_opportunity != null)
      .sort((a, b) => (b.adv_opportunity!.estimated_adv_gain) - (a.adv_opportunity!.estimated_adv_gain));
  }, [allMarkersData]);

  return (
    <div
      className="fixed overflow-hidden flex flex-col"
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
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-[var(--border-color)]">
        <span className="font-semibold text-atlas-light text-sm">{t('area_analysis.cap_opportunity_title')}</span>
        <button
          onClick={onClose}
          aria-label={t('common.close')}
          className="text-atlas-muted hover:text-atlas-light transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
        {opportunities.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-4">
            <p className="text-sm text-atlas-muted text-center">
              {t('area_analysis.cap_opportunity_no_results')}
            </p>
          </div>
        ) : (
          opportunities.map((partner) => {
            const opp = partner.adv_opportunity!;
            const isSelected = selectedPartnerId === partner.salesforce_id;
            // Verde se ganho > 50% do cap atual, amarelo se ≤ 50%
            const gainPct = partner.capacity > 0 ? opp.estimated_adv_gain / partner.capacity : 1;
            const isHighGain = gainPct > 0.5;
            const badgeClass = isHighGain
              ? 'bg-green-500/20 text-green-400'
              : 'bg-amber-500/20 text-amber-400';
            const valueClass = isHighGain ? 'text-green-400' : 'text-amber-400';
            return (
              <div
                key={partner.salesforce_id}
                className={[
                  'rounded-lg p-3 flex flex-col gap-1.5 transition-colors',
                  isSelected
                    ? 'bg-amber-500/15'
                    : 'bg-atlas-darker',
                ].join(' ')}
              >
                {/* Partner name + gain badge */}
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-atlas-light leading-tight flex-1">
                    {partner.name}
                  </span>
                  <span className={`shrink-0 px-2 py-0.5 rounded-full text-xs font-semibold ${badgeClass}`}>
                    +{opp.estimated_adv_gain} ADV
                  </span>
                </div>

                {/* Cap: atual → sugerido */}
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-atlas-muted">{t('area_analysis.cap_opportunity_cap')}</span>
                  <span className="text-atlas-light font-medium">{partner.capacity}</span>
                  <span className="text-atlas-muted">→</span>
                  <span className={`font-semibold ${valueClass}`}>{opp.suggested_cap}</span>
                </div>

                {/* Raio: atual → sugerido */}
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-atlas-muted">{t('area_analysis.cap_opportunity_radius')}</span>
                  <span className="text-atlas-light font-medium">{partner.radius} m</span>
                  <span className="text-atlas-muted">→</span>
                  <span className={`font-semibold ${valueClass}`}>{opp.suggested_radius} m</span>
                </div>

                {/* Ganho estimado */}
                <div className="text-xs text-atlas-muted">
                  {t('area_analysis.cap_opportunity_estimated_gain')} <span className={`font-semibold ${valueClass}`}>{opp.estimated_adv_gain} {t('area_analysis.cap_opportunity_adv_per_day')}</span>
                </div>

                {/* Ações */}
                <div className="flex gap-2 mt-1">
                  <button
                    type="button"
                    onClick={() => setSelectedCapOpportunity(partner.salesforce_id)}
                    className={[
                      'flex-1 py-1.5 px-3 rounded text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400',
                      isSelected
                        ? 'bg-amber-500 text-white hover:bg-amber-400'
                        : 'bg-atlas-dark text-atlas-light border border-[var(--border-color)] hover:border-atlas-accent hover:text-atlas-accent',
                    ].join(' ')}
                  >
                    {isSelected ? t('area_analysis.cap_opportunity_selected') : t('area_analysis.cap_opportunity_view_change')}
                  </button>
                  {partner.lat != null && partner.lon != null && (
                    <button
                      type="button"
                      aria-label={`Ir até ${partner.name}`}
                      onClick={() => fitBoundsRef.current?.([[partner.lat!, partner.lon!]])}
                      className="py-1.5 px-2.5 rounded text-xs font-semibold text-atlas-accent border border-atlas-accent/30 hover:bg-atlas-accent/10 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent flex items-center gap-1"
                      title={t('common.visualize_on_map')}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
                      </svg>
                      {t('common.visualize')}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AreaAnalysisTab principal
// ---------------------------------------------------------------------------

export default function AreaAnalysisTab() {
  const { t } = useTranslation();
  const allMarkersData = useStore((s) => s.allMarkersData);
  const applyFilters = useStore((s) => s.applyFilters);
  const resetFilters = useStore((s) => s.resetFilters);
  const setManualAnalysisOpen = useStore((s) => s.setManualAnalysisOpen);
  const manualAnalysisOpen = useStore((s) => s.manualAnalysisOpen);
  const setSelectedCapOpportunity = useStore((s) => s.setSelectedCapOpportunity);
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';
  const [selectedState, setSelectedState] = useState('all');
  const [selectedDecision, setSelectedDecision] = useState('all');

  const [analysisResult, setAnalysisResult] = useState<{
    overview: Overview;
    filtered: FilteredStats;
    stateRows: StateRow[];
    leads: Partner[];
    stateFilter: string;
    decisionFilter: string;
  } | null>(null);

  const [showPanel, setShowPanel] = useState(false);
  const [showStateTable, setShowStateTable] = useState(false);
  const [showCapOpportunityPanel, setShowCapOpportunityPanel] = useState(false);

  const stateOptions = useMemo(() => {
    const prospects = allMarkersData.filter((p) => p.status === 'Prospect');
    return getUniqueValues(prospects, 'state').sort();
  }, [allMarkersData]);

  const handleAnalyze = useCallback(() => {
    // Fecha as outras análises antes de abrir esta
    if (manualAnalysisOpen) setManualAnalysisOpen(false);
    if (showCapOpportunityPanel) {
      setShowCapOpportunityPanel(false);
      setSelectedCapOpportunity(null);
    }

    applyFilters({ selectedStatuses: ['Prospect'] });

    const allProspects = allMarkersData.filter((p) => p.status === 'Prospect');
    const filteredProspects = allProspects.filter((p) => {
      if (!p.decision) return false;
      if (selectedState !== 'all' && p.state !== selectedState) return false;
      if (selectedDecision !== 'all' && p.decision !== selectedDecision) return false;
      return true;
    });

    const overview = getGlobalOverview(allMarkersData);
    const filtered = getFilteredStats(filteredProspects);
    const stateRows = getStatsByState(allProspects.filter((p) => !!p.decision));
    const leads = filteredProspects;

    setAnalysisResult({ overview, filtered, stateRows, leads, stateFilter: selectedState, decisionFilter: selectedDecision });
    setShowPanel(true);
    setShowStateTable(false);
  }, [allMarkersData, applyFilters, selectedState, selectedDecision, manualAnalysisOpen, setManualAnalysisOpen, showCapOpportunityPanel, setSelectedCapOpportunity]);

  const handleClose = useCallback(() => {
    setShowPanel(false);
    setShowStateTable(false);
  }, []);

  const handleOpenCapOpportunity = useCallback(() => {
    // Fecha as outras análises antes de abrir esta
    if (manualAnalysisOpen) setManualAnalysisOpen(false);
    if (showPanel) {
      setShowPanel(false);
      setShowStateTable(false);
    }
    setShowCapOpportunityPanel(true);
    applyFilters({ selectedStatuses: ['Active'] });
  }, [applyFilters, manualAnalysisOpen, setManualAnalysisOpen, showPanel]);

  const handleCloseCapOpportunity = useCallback(() => {
    setShowCapOpportunityPanel(false);
    setSelectedCapOpportunity(null);
    resetFilters();
  }, [resetFilters, setSelectedCapOpportunity]);

  const handleToggleManualAnalysis = useCallback(() => {
    if (!manualAnalysisOpen) {
      // Vai abrir — fecha as outras
      if (showPanel) {
        setShowPanel(false);
        setShowStateTable(false);
      }
      if (showCapOpportunityPanel) {
        setShowCapOpportunityPanel(false);
        setSelectedCapOpportunity(null);
        resetFilters();
      }
    }
    setManualAnalysisOpen(!manualAnalysisOpen);
  }, [manualAnalysisOpen, setManualAnalysisOpen, showPanel, showCapOpportunityPanel, setSelectedCapOpportunity, resetFilters]);

  return (
    <>
      {!isMobile && showPanel && analysisResult && (
        createPortal(
          <ResultPanel
            overview={analysisResult.overview}
            filtered={analysisResult.filtered}
            stateFilter={analysisResult.stateFilter}
            decisionFilter={analysisResult.decisionFilter}
            stateRows={analysisResult.stateRows}
            leads={analysisResult.leads}
            showStateTable={showStateTable}
            onToggleStateTable={() => setShowStateTable((v) => !v)}
            onClose={handleClose}
          />,
          document.body
        )
      )}

      {!isMobile && showCapOpportunityPanel && (
        createPortal(
          <CapOpportunityPanel onClose={handleCloseCapOpportunity} />,
          document.body
        )
      )}

      <div className="p-3">
        {/* Botão Análise Manual — sólido e vivo */}
        <div className="mb-5">
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-3 font-semibold border-b border-[var(--border-color)] pb-1">
            {t('area_analysis.section_areas')}
          </p>
          <button
            type="button"
            onClick={() => handleToggleManualAnalysis()}
            className={[
              'w-full py-3 px-4 rounded text-sm font-semibold min-h-[44px] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent shadow-lg',
              manualAnalysisOpen
                ? 'bg-atlas-accent text-white hover:opacity-90 shadow-atlas-accent/30'
                : 'bg-atlas-accent text-white hover:opacity-90 shadow-atlas-accent/40',
            ].join(' ')}
          >
            {manualAnalysisOpen ? t('area_analysis.manual_analysis_close') : t('area_analysis.manual_analysis_button')}
          </button>
          {manualAnalysisOpen && (
            <p className="mt-2 text-xs text-atlas-accent text-center">
              {t('area_analysis.manual_analysis_hint')}
            </p>
          )}
        </div>

        <div className="border-t border-[var(--border-color)] mb-4" />

        {/* Oportunidades de ADV */}
        <div className="mb-5">
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-3 font-semibold">
            {t('area_analysis.section_opportunities')}
          </p>
          <button
            type="button"
            onClick={showCapOpportunityPanel ? handleCloseCapOpportunity : handleOpenCapOpportunity}
            className={[
              'w-full py-3 px-4 rounded text-sm font-semibold min-h-[44px] transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 shadow-lg',
              showCapOpportunityPanel
                ? 'bg-amber-500 text-white hover:bg-amber-400 shadow-amber-500/30'
                : 'bg-amber-600 text-white hover:bg-amber-500 shadow-amber-600/40',
            ].join(' ')}
          >
            {showCapOpportunityPanel ? t('area_analysis.opportunities_close') : t('area_analysis.opportunities_button')}
          </button>
        </div>

        <div className="border-t border-[var(--border-color)] mb-4" />

        {/* Análise de Prospects */}
        <p className="text-xs uppercase tracking-wide text-atlas-muted mb-3 font-semibold">
          {t('area_analysis.section_prospects')}
        </p>

        <div className="mb-3">
          <label htmlFor="area-state" className="block text-xs font-medium text-atlas-muted mb-1">{t('area_analysis.state_label')}</label>
          <select
            id="area-state"
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          >
            <option value="all">{t('area_analysis.state_all')}</option>
            {stateOptions.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="mb-4">
          <label htmlFor="area-decision" className="block text-xs font-medium text-atlas-muted mb-1">{t('area_analysis.decision_label')}</label>
          <select
            id="area-decision"
            value={selectedDecision}
            onChange={(e) => setSelectedDecision(e.target.value)}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          >
            <option value="all">{t('area_analysis.decision_all')}</option>
            <option value="Go">{t('common.go')}</option>
            <option value="No Go">{t('common.no_go')}</option>
          </select>
        </div>

        <div className="mb-4 px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-xs text-atlas-muted">
          {t('area_analysis.fixed_filter_note')} <span className="text-atlas-accent font-medium">{t('area_analysis.fixed_filter_status')}</span>
        </div>

        <button
          type="button"
          onClick={handleAnalyze}
          className="w-full py-3 px-4 rounded bg-atlas-accent text-white text-sm font-semibold hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent min-h-[44px] mb-4 transition-colors shadow-lg shadow-atlas-accent/40"
        >
          {t('area_analysis.analyze_button')}
        </button>

        {/* Resumo de seleção de hexes — visível apenas na aba Área com hexes selecionados */}
        <HexSelectionSummary />

        {/* Mobile: resultado inline */}
        {isMobile && analysisResult && (
          <div className="flex flex-col gap-3">
            <div className="rounded-lg bg-atlas-darker p-3">
              <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2">{t('area_analysis.overview_label')}</p>
              <div className="flex gap-2">
                <StatBox value={analysisResult.overview.total} label={t('area_analysis.stat_evaluated')} />
                <StatBox value={analysisResult.overview.go} label={t('common.go')} color="text-green-400" />
                <StatBox value={analysisResult.overview.nogo} label={t('common.no_go')} color="text-red-400" />
                <StatBox value={`${analysisResult.overview.rate}%`} label={t('area_analysis.stat_approval_short')} color="text-blue-400" />
              </div>
              {analysisResult.overview.nogo > 0 && (
                <NoGoTable
                  rows={NO_GO_REASONS.map((r) => ({
                    reason: r,
                    count: analysisResult.overview.nogoReasonCounts[r] ?? 0,
                    pct: analysisResult.overview.nogo > 0
                      ? (((analysisResult.overview.nogoReasonCounts[r] ?? 0) / analysisResult.overview.nogo) * 100).toFixed(1)
                      : '0.0',
                  }))}
                  title={t('area_analysis.no_go_detail_title')}
                />
              )}
            </div>
            {(analysisResult.stateFilter !== 'all' || analysisResult.decisionFilter !== 'all') && (
              <div className="rounded-lg bg-atlas-darker p-3">
                <p className="text-xs text-atlas-muted mb-2">
                  {analysisResult.stateFilter !== 'all' && <span>{t('area_analysis.state_filter_label')}<strong className="text-atlas-light">{analysisResult.stateFilter}</strong></span>}
                  {analysisResult.decisionFilter !== 'all' && <span> | {t('area_analysis.decision_filter_label')}<strong className="text-atlas-light">{analysisResult.decisionFilter}</strong></span>}
                </p>
                <div className="flex gap-2">
                  <StatBox value={analysisResult.filtered.total} label={t('area_analysis.stat_total')} />
                  <StatBox value={analysisResult.filtered.go} label={t('common.go')} color="text-green-400" />
                  <StatBox value={analysisResult.filtered.nogo} label={t('common.no_go')} color="text-red-400" />
                  <StatBox value={`${analysisResult.filtered.rate}%`} label={t('area_analysis.stat_approval_short')} color="text-blue-400" />
                </div>
                {analysisResult.filtered.nogo > 0 && (
                  <NoGoTable rows={analysisResult.filtered.nogoReasonRows} title={t('area_analysis.no_go_detail_title')} />
                )}
              </div>
            )}
            {analysisResult.leads.length > 0 && (
              <LeadsPanel leads={analysisResult.leads} />
            )}
          </div>
        )}
      </div>
    </>
  );
}
