/**
 * PackagesTab.tsx
 * ===============
 * Aba "Pacotes & Canais" do Dashboard Operacional.
 * Consome `deliveries_summary.json` (Fase 6) e mostra:
 *
 * - Card de %share IHS vs DSP (com seletor de DS).
 * - Tabela de parceiros hub ordenada por volume, com filtros e
 *   linha expansível para drill-down (PartnerDrillDown).
 *
 * Estados visuais:
 * - Loading: Spinner enquanto `deliveries.isLoadingSummary`.
 * - Empty: mensagem amigável quando summary ainda não foi gerado pelo backend.
 * - Error: warning com botão para retentar.
 */

import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import { Spinner } from '../ui/Spinner';
import ShareIhsDspCard from './ShareIhsDspCard';
import PartnerDrillDown from './PartnerDrillDown';
import MisconfiguredHubsCard from './MisconfiguredHubsCard';
import type { PartnerDeliveryStats } from '../../store/types';
import type { DashboardFilters, ReportData } from '../../lib/reportUtils';
import {
  buildHierarchyIndex,
  filterPartnersByHierarchy,
  stationsInScope,
} from '../../lib/deliveriesHierarchy';

type SortKey =
  | 'name'
  | 'delivery_station'
  | 'total'
  | 'daily_avg'
  | 'cap_utilization_pct'
  | 'share_ds_pct'
  | 'share_ds_ihs_pct'
  | 'trend_7d_pct';

interface PackagesTabProps {
  filters: DashboardFilters;
  reportData: ReportData | null;
}

const PackagesTab: React.FC<PackagesTabProps> = ({ filters, reportData }) => {
  const { t } = useTranslation();
  const summary = useStore((s) => s.deliveries.summary);
  const isLoading = useStore((s) => s.deliveries.isLoadingSummary);
  const error = useStore((s) => s.deliveries.errorSummary);
  const loadSummary = useStore((s) => s.loadDeliveriesSummary);

  const [selectedDs, setSelectedDs] = useState<string>('all');
  const [filterDs, setFilterDs] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [onlyKnown, setOnlyKnown] = useState(false);
  const [onlyIhs, setOnlyIhs] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('total');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [expandedStoreId, setExpandedStoreId] = useState<string | null>(null);

  // Índice hierárquico derivado do reportData.
  const hierarchyIndex = useMemo(() => buildHierarchyIndex(reportData), [reportData]);

  // Parceiros filtrados pela hierarquia global (BDM/Base/CTL/ADE/Território).
  const partnersInScope = useMemo<PartnerDeliveryStats[]>(() => {
    if (!summary) return [];
    return filterPartnersByHierarchy(summary.partners, filters, hierarchyIndex);
  }, [summary, filters, hierarchyIndex]);

  // Station totals dentro do recorte: quando nenhum filtro ativo, usa os
  // totais crus do summary (são os da DS inteira). Com filtro ativo,
  // precisamos recalcular IHS/DSP/total a partir dos parceiros filtrados
  // — o total do DS cru incluiria entregas fora do CTL/ADE selecionado.
  const scopedStationTotals = useMemo(() => {
    if (!summary) return {};
    const hasHierarchyFilter =
      filters.bdm !== 'all' ||
      filters.ctl !== 'all' ||
      filters.ade !== 'all' ||
      filters.territory !== 'all';

    if (!hasHierarchyFilter) {
      // Sem recorte hierárquico fino, usa os totais originais do backend
      // (incluem as entregas DSP sem store_id, que não aparecem em partnersInScope).
      const keys = filters.base === 'all'
        ? Object.keys(summary.station_totals)
        : [filters.base];
      const out: Record<string, typeof summary.station_totals[string]> = {};
      for (const k of keys) {
        if (summary.station_totals[k]) out[k] = summary.station_totals[k];
      }
      return out;
    }

    // Com recorte fino, recalcula a partir dos parceiros filtrados.
    const acc: Record<string, { total: number; ihs: number; dsp: number; other: number }> = {};
    for (const p of partnersInScope) {
      const ds = p.delivery_station || 'UNKNOWN';
      if (!acc[ds]) acc[ds] = { total: 0, ihs: 0, dsp: 0, other: 0 };
      acc[ds].total += p.total;
      if (p.canal_dominante === 'IHS_STORE') acc[ds].ihs += p.total;
      else if (p.canal_dominante === 'DSP') acc[ds].dsp += p.total;
      else acc[ds].other += p.total;
    }
    const out: Record<string, typeof summary.station_totals[string]> = {};
    for (const [ds, v] of Object.entries(acc)) {
      const total = v.total;
      out[ds] = {
        total,
        ihs: v.ihs,
        dsp: v.dsp,
        other: v.other,
        ihs_share_pct: total > 0 ? Math.round((v.ihs / total) * 10000) / 100 : 0,
        dsp_share_pct: total > 0 ? Math.round((v.dsp / total) * 10000) / 100 : 0,
      };
    }
    return out;
  }, [summary, filters, partnersInScope]);

  // Stations disponíveis dentro do recorte — alimenta dropdowns locais.
  const scopedStations = useMemo(() => {
    if (!summary) return [];
    return stationsInScope(Object.keys(summary.station_totals), filters, hierarchyIndex);
  }, [summary, filters, hierarchyIndex]);

  // Reset do dropdown local de DS quando o recorte muda e o DS
  // previamente selecionado não está mais disponível.
  React.useEffect(() => {
    if (selectedDs !== 'all' && !scopedStations.includes(selectedDs)) {
      setSelectedDs('all');
    }
    if (filterDs !== 'all' && !scopedStations.includes(filterDs)) {
      setFilterDs('all');
    }
  }, [scopedStations, selectedDs, filterDs]);

  const rows = useMemo<PartnerDeliveryStats[]>(() => {
    let arr = partnersInScope;
    if (filterDs !== 'all') arr = arr.filter((p) => p.delivery_station === filterDs);
    if (onlyKnown) arr = arr.filter((p) => !p.is_unknown);
    if (onlyIhs) arr = arr.filter((p) => p.canal_dominante === 'IHS_STORE');
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      arr = arr.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.store_id.toLowerCase().includes(q) ||
          (p.nome_empresa || '').toLowerCase().includes(q),
      );
    }
    const sorted = [...arr].sort((a, b) => {
      const va = a[sortKey] ?? 0;
      const vb = b[sortKey] ?? 0;
      if (typeof va === 'string' || typeof vb === 'string') {
        return sortDir === 'asc'
          ? String(va).localeCompare(String(vb))
          : String(vb).localeCompare(String(va));
      }
      return sortDir === 'asc' ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
    return sorted;
  }, [partnersInScope, filterDs, onlyKnown, onlyIhs, searchQuery, sortKey, sortDir]);

  const onSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  // ---------- Loading / error / empty ----------

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-atlas-muted">
        <Spinner size="lg" />
        <span className="text-sm">{t('packages.loading')}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3">
        <span className="text-3xl">⚠️</span>
        <p className="text-yellow-400 text-sm text-center max-w-md">
          {t('packages.load_error')}
          <span className="block text-atlas-muted text-xs mt-1">({error})</span>
        </p>
        <button
          onClick={() => loadSummary()}
          className="px-4 py-2 bg-atlas-accent text-white text-sm rounded hover:opacity-90"
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center p-12 gap-3 text-atlas-muted">
        <span className="text-3xl">📦</span>
        <p className="text-sm text-center max-w-md">
          {t('packages.empty_state')}
        </p>
      </div>
    );
  }

  // ---------- Main render ----------

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex flex-col">
          <h2 className="text-atlas-light font-semibold text-base">
            {t('packages.title')}
          </h2>
          <span className="text-atlas-muted text-xs">
            {t('packages.period_label')}: {summary.period.date_min} → {summary.period.date_max} ({summary.period.days}d)
          </span>
        </div>
      </div>

      {/* Share card */}
      <ShareIhsDspCard
        stationTotals={scopedStationTotals}
        periodDays={summary.period.days}
        selectedDs={selectedDs}
        onChangeDs={setSelectedDs}
      />

      {/* Warning de hubs com cap/radius=0 no Salesforce — respeita o recorte. */}
      <MisconfiguredHubsCard partners={partnersInScope} />

      {/* Filters */}
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-3 flex flex-wrap gap-3 items-center">
        <input
          type="search"
          placeholder={t('packages.search_placeholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 min-w-[200px] bg-atlas-darker border border-atlas-navy rounded px-3 py-1.5 text-sm text-atlas-light placeholder-atlas-muted focus:outline-none focus:border-atlas-accent"
        />
        <select
          value={filterDs}
          onChange={(e) => setFilterDs(e.target.value)}
          className="bg-atlas-darker border border-atlas-navy rounded px-2 py-1.5 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent"
        >
          <option value="all">{t('packages.all_stations')}</option>
          {scopedStations.sort().map((ds) => (
            <option key={ds} value={ds}>{ds}</option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-atlas-light">
          <input
            type="checkbox"
            checked={onlyIhs}
            onChange={(e) => setOnlyIhs(e.target.checked)}
            className="accent-atlas-accent"
          />
          {t('packages.filter_only_ihs')}
        </label>
        <label className="flex items-center gap-1.5 text-xs text-atlas-light">
          <input
            type="checkbox"
            checked={onlyKnown}
            onChange={(e) => setOnlyKnown(e.target.checked)}
            className="accent-atlas-accent"
          />
          {t('packages.filter_only_known')}
        </label>
      </div>

      {/* Tabela de parceiros */}
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
        <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-atlas-darker sticky top-0 z-10">
              <tr>
                <HeaderCell label={t('packages.col_partner')} k="name" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <HeaderCell label={t('packages.col_ds')} k="delivery_station" sortKey={sortKey} sortDir={sortDir} onSort={onSort} />
                <HeaderCell label={t('packages.col_total')} k="total" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <HeaderCell label={t('packages.col_daily_avg')} k="daily_avg" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <HeaderCell label={t('packages.col_cap_util')} k="cap_utilization_pct" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <HeaderCell label={t('packages.col_share_ds')} k="share_ds_pct" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <HeaderCell label={t('packages.col_share_ihs')} k="share_ds_ihs_pct" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <HeaderCell label={t('packages.col_trend')} k="trend_7d_pct" sortKey={sortKey} sortDir={sortDir} onSort={onSort} align="right" />
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-atlas-muted text-center py-6 text-sm">
                    {t('packages.no_results')}
                  </td>
                </tr>
              ) : (
                rows.map((p) => (
                  <React.Fragment key={p.store_id}>
                    <tr
                      className={`border-t border-atlas-navy hover:bg-atlas-navy transition-colors cursor-pointer ${
                        expandedStoreId === p.store_id ? 'bg-atlas-navy' : ''
                      }`}
                      onClick={() =>
                        setExpandedStoreId((id) => (id === p.store_id ? null : p.store_id))
                      }
                    >
                      <td className="px-3 py-2 text-atlas-light">
                        {p.name}
                        {p.is_unknown && (
                          <span className="ml-2 px-1.5 py-0.5 text-[10px] rounded bg-yellow-500/20 border border-yellow-500/40 text-yellow-300">
                            unknown
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-atlas-muted">{p.delivery_station}</td>
                      <td className="px-3 py-2 text-atlas-light text-right">
                        {p.total.toLocaleString('pt-BR')}
                      </td>
                      <td className="px-3 py-2 text-atlas-light text-right">
                        {p.daily_avg.toFixed(1)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <CapUtilBadge pct={p.cap_utilization_pct} misconfigured={p.cap_misconfigured} />
                      </td>
                      <td className="px-3 py-2 text-atlas-light text-right">
                        {p.share_ds_pct.toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-atlas-light text-right">
                        {p.share_ds_ihs_pct.toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-right">
                        <TrendBadge pct={p.trend_7d_pct} />
                      </td>
                      <td className="px-3 py-2 text-right text-atlas-muted">
                        {expandedStoreId === p.store_id ? '▾' : '▸'}
                      </td>
                    </tr>
                    {expandedStoreId === p.store_id && (
                      <tr>
                        <td colSpan={9} className="px-3 pb-3 bg-atlas-darker">
                          <PartnerDrillDown
                            partner={p}
                            onRequestClose={() => setExpandedStoreId(null)}
                          />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Helpers inline
// ---------------------------------------------------------------------------

const HeaderCell: React.FC<{
  label: string;
  k: SortKey;
  sortKey: SortKey;
  sortDir: 'asc' | 'desc';
  onSort: (k: SortKey) => void;
  align?: 'left' | 'right';
}> = ({ label, k, sortKey, sortDir, onSort, align = 'left' }) => (
  <th
    onClick={() => onSort(k)}
    className={`px-3 py-2 uppercase text-xs text-atlas-muted tracking-wide cursor-pointer select-none hover:text-atlas-light transition-colors whitespace-nowrap ${
      align === 'right' ? 'text-right' : 'text-left'
    }`}
  >
    {label}
    {sortKey === k ? (
      <span className="text-atlas-accent ml-1">
        {sortDir === 'asc' ? '↑' : '↓'}
      </span>
    ) : (
      <span className="text-atlas-muted ml-1 opacity-50">↕</span>
    )}
  </th>
);

const CapUtilBadge: React.FC<{ pct: number; misconfigured?: boolean }> = ({
  pct,
  misconfigured,
}) => {
  // Cap/radius zerados no Salesforce vira warning dedicado em vez de
  // alerta de performance — evita confundir "parceiro sem cap configurado"
  // com "parceiro performando abaixo do cap".
  if (misconfigured) {
    return (
      <span
        className="px-1.5 py-0.5 rounded bg-yellow-500/20 border border-yellow-500/40 text-yellow-300 text-[10px] font-semibold uppercase tracking-wide"
        title="Hub sem cap ou raio configurado no Salesforce"
      >
        ⚠ sem cap
      </span>
    );
  }
  let cls = 'text-atlas-muted';
  if (pct >= 80) cls = 'text-green-400';
  else if (pct >= 50) cls = 'text-yellow-400';
  else if (pct > 0) cls = 'text-red-400';
  return <span className={`${cls} font-medium`}>{pct.toFixed(1)}%</span>;
};

const TrendBadge: React.FC<{ pct: number }> = ({ pct }) => {
  if (pct === 0) return <span className="text-atlas-muted">—</span>;
  const cls = pct > 0 ? 'text-green-400' : 'text-red-400';
  const arrow = pct > 0 ? '↑' : '↓';
  return (
    <span className={`${cls} font-medium`}>
      {arrow} {Math.abs(pct).toFixed(1)}%
    </span>
  );
};

export default PackagesTab;
