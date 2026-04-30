/**
 * GeoIntelligenceDashboard.tsx
 * ============================
 * Dashboard principal do Atlas — substitui Dashboard.tsx.
 * Exibe KPIs de geointeligência (DS e BDM), tabela ranqueada de territórios,
 * rankings, gráfico de distribuição de RegionType, input de expansion target
 * e exportação CSV. Preserva o dashboard operacional original via aba.
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 10.4
 */

import React, { useMemo, useState, useCallback, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar, Pie } from 'react-chartjs-2';
import { useStore } from '../../store';
import type { TerritoryOutput } from '../../store/geoIntelligenceSlice';
import { regionTypeLabel, formatGap, potentialScoreToColor } from '../../lib/geoIntelligenceUtils';
import { Spinner } from '../ui/Spinner';
import KpiCard from './KpiCard';
import FilterCascade from './FilterCascade';
import { useDashboardFilters } from '../../hooks/useDashboardFilters';

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend);

const OriginalDashboard = lazy(() => import('./Dashboard'));
const PackagesTab = lazy(() => import('./PackagesTab'));
const InsightsTab = lazy(() => import('./InsightsTab'));

type SortDir = 'asc' | 'desc';
type SortCol = keyof TerritoryOutput | null;
type ActiveTab = 'geo' | 'operacional' | 'packages' | 'insights';

function getCSSVar(name: string): string {
  if (typeof document === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function chartTheme() {
  return {
    text: getCSSVar('--color-light') || '#ecf0f1',
    grid: getCSSVar('--color-dark') || '#1e2a38',
  };
}

function exportCSV(rows: TerritoryOutput[], filename = 'territorios.csv') {
  if (rows.length === 0) return;
  const cols: (keyof TerritoryOutput)[] = [
    'territory_id', 'region_type', 'potential_score', 'current_partners',
    'ideal_slots', 'gap', 'model_confidence', 'low_confidence', 'high_opportunity',
  ];
  const header = cols.join(',');
  const body = rows.map((r) =>
    cols.map((c) => { const v = r[c]; const s = String(v ?? ''); return s.includes(',') ? `"${s}"` : s; }).join(',')
  ).join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

const GeoIntelligenceDashboard: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<ActiveTab>('geo');
  const [stationInput, setStationInput] = useState('');
  const [loadedStation, setLoadedStation] = useState<string | null>(null);
  const [expansionTarget, setExpansionTarget] = useState<number>(50);
  const [sortCol, setSortCol] = useState<SortCol>('gap');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Filtros globais do Dashboard (compartilhados entre todas as abas).
  // O FilterCascade fica fora das abas porque o gerente escolhe a
  // visão uma vez (ex: "minha região SP/SUL") e navega pelas análises
  // sem perder o recorte.
  const {
    filters,
    setFilters,
    reportData,
    isLoadingReport,
    reportError,
    loadReport,
    retry: retryReport,
  } = useDashboardFilters();

  React.useEffect(() => {
    if (!reportData && !isLoadingReport && !reportError) {
      void loadReport();
    }
  }, [reportData, isLoadingReport, reportError, loadReport]);

  const loadGeoIntelligence = useStore((s) => s.loadGeoIntelligence);
  const selectGeoTerritory = useStore((s) => s.selectGeoTerritory);
  const territories = useStore((s) => s.geoIntelligence.territories);
  const scorecard = useStore((s) => s.geoIntelligence.scorecard);
  const isLoading = useStore((s) => s.geoIntelligence.isLoading);
  const error = useStore((s) => s.geoIntelligence.error);

  const handleLoadStation = useCallback(() => {
    const code = stationInput.trim().toUpperCase();
    if (!code) return;
    setLoadedStation(code);
    void loadGeoIntelligence(code);
  }, [stationInput, loadGeoIntelligence]);

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortCol(col); setSortDir('desc'); }
  };

  const sortedTerritories = useMemo(() => {
    if (!sortCol) return territories;
    return [...territories].sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      if (av === undefined || bv === undefined) return 0;
      if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [territories, sortCol, sortDir]);

  const dsKpis = useMemo(() => {
    const total = territories.length;
    const highOpp = territories.filter((t) => t.high_opportunity).length;
    const avgGap = total > 0 ? territories.reduce((s, t) => s + t.gap, 0) / total : 0;
    const totalPotential = territories.reduce((s, t) => s + t.potential_score, 0);
    const covered = territories.filter((t) => t.current_partners > 0).length;
    return { total, highOpp, avgGap, totalPotential, coveragePct: total > 0 ? (covered / total) * 100 : 0 };
  }, [territories]);

  const bdmKpis = useMemo(() => {
    if (!scorecard) return null;
    const sc = scorecard as Record<string, unknown>;
    const bdm = (Array.isArray(sc.bdm) && sc.bdm.length > 0 ? sc.bdm[0] : sc) as Record<string, unknown>;
    return {
      nDs: (bdm.n_ds ?? bdm.n_territories ?? '—') as string | number,
      avgPotential: typeof bdm.potential_score === 'number' ? bdm.potential_score.toFixed(1) : '—',
      totalHighOpp: (bdm.n_high_opportunity ?? '—') as string | number,
      avgGap: typeof bdm.avg_gap === 'number' ? bdm.avg_gap.toFixed(1) : '—',
    };
  }, [scorecard]);

  const regionDist = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of territories) counts[t.region_type] = (counts[t.region_type] ?? 0) + 1;
    return counts;
  }, [territories]);

  const expansionRecommended = useMemo(() => {
    if (territories.length === 0) return [];
    const sorted = [...territories].sort((a, b) => b.gap - a.gap);
    const totalPotential = territories.reduce((s, t) => s + t.potential_score, 0);
    const targetPotential = (expansionTarget / 100) * totalPotential;
    let acc = 0;
    const result: TerritoryOutput[] = [];
    for (const t of sorted) {
      if (acc >= targetPotential) break;
      result.push(t);
      acc += t.potential_score;
    }
    return result;
  }, [territories, expansionTarget]);

  const accumulatedPotential = useMemo(
    () => expansionRecommended.reduce((s, t) => s + t.potential_score, 0),
    [expansionRecommended],
  );

  return (
    <div className="flex flex-col h-full bg-atlas-darker">
      <div className="flex shrink-0 border-b border-atlas-navy">
        <TabButton active={activeTab === 'geo'} onClick={() => setActiveTab('geo')}>{t('dashboard.tab_geo')}</TabButton>
        <TabButton active={activeTab === 'operacional'} onClick={() => setActiveTab('operacional')}>{t('dashboard.tab_operational')}</TabButton>
        <TabButton active={activeTab === 'packages'} onClick={() => setActiveTab('packages')}>{t('dashboard.tab_packages')}</TabButton>
        <TabButton active={activeTab === 'insights'} onClick={() => setActiveTab('insights')}>{t('dashboard.tab_insights')}</TabButton>
      </div>

      {/* Filtros globais — aplicam-se a TODAS as abas exceto Geo (que tem seu próprio fluxo) */}
      {activeTab !== 'geo' && (
        <div className="shrink-0 border-b border-atlas-navy bg-atlas-darker">
          <FilterCascade
            reportData={reportData}
            filters={filters}
            onFilterChange={setFilters}
            isLoading={isLoadingReport}
          />
        </div>
      )}

      {activeTab === 'operacional' && (
        <div className="flex-1 overflow-y-auto">
          <Suspense fallback={<div className="flex items-center justify-center h-full p-8"><Spinner /></div>}>
            <OriginalDashboard />
          </Suspense>
        </div>
      )}

      {activeTab === 'packages' && (
        <div className="flex-1 overflow-y-auto">
          <Suspense fallback={<div className="flex items-center justify-center h-full p-8"><Spinner /></div>}>
            <PackagesTab filters={filters} reportData={reportData} />
          </Suspense>
        </div>
      )}

      {activeTab === 'insights' && (
        <div className="flex-1 overflow-y-auto">
          <Suspense fallback={<div className="flex items-center justify-center h-full p-8"><Spinner /></div>}>
            <InsightsTab filters={filters} reportData={reportData} />
          </Suspense>
        </div>
      )}

      {activeTab === 'geo' && (
        <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
          <section className="flex gap-2 items-center">
            <input type="text" value={stationInput} onChange={(e) => setStationInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLoadStation()}
              placeholder={t('dashboard.geo_ds_input_placeholder')}
              className="flex-1 bg-atlas-dark border border-atlas-navy rounded px-3 py-2 text-atlas-light text-sm placeholder-atlas-muted focus:outline-none focus:border-atlas-accent" />
            <button onClick={handleLoadStation} disabled={isLoading || !stationInput.trim()}
              className="px-4 py-2 bg-atlas-accent text-white text-sm font-semibold rounded hover:opacity-90 transition-opacity disabled:opacity-50">
              {isLoading ? <Spinner size="sm" /> : t('dashboard.geo_load_button')}
            </button>
          </section>

          {error && <div className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded px-3 py-2">{error}</div>}

          {loadedStation && !isLoading && !error && (
            <>
              <section>
                <SectionTitle>KPIs — DS {loadedStation}</SectionTitle>
                <div className="grid grid-cols-2 tablet:grid-cols-5 gap-3">
                  <KpiCard label={t('dashboard.geo_kpi_territories')} value={dsKpis.total} />
                  <KpiCard label={t('dashboard.geo_kpi_high_opportunity')} value={dsKpis.highOpp} />
                  <KpiCard label={t('dashboard.geo_kpi_avg_gap')} value={formatGap(dsKpis.avgGap)} />
                  <KpiCard label={t('dashboard.geo_kpi_total_potential')} value={dsKpis.totalPotential.toFixed(1)} />
                  <KpiCard label={t('dashboard.geo_kpi_coverage')} value={`${dsKpis.coveragePct.toFixed(1)}%`} />
                </div>
              </section>

              {bdmKpis && (
                <section>
                  <SectionTitle>KPIs — BDM</SectionTitle>
                  <div className="grid grid-cols-2 tablet:grid-cols-4 gap-3">
                    <KpiCard label={t('dashboard.geo_kpi_ds_count')} value={bdmKpis.nDs} />
                    <KpiCard label={t('dashboard.geo_kpi_avg_potential')} value={bdmKpis.avgPotential} />
                    <KpiCard label={t('dashboard.geo_kpi_total_high_opp')} value={bdmKpis.totalHighOpp} />
                    <KpiCard label={t('dashboard.geo_kpi_avg_gap')} value={bdmKpis.avgGap} />
                  </div>
                </section>
              )}

              {Object.keys(regionDist).length > 0 && (
                <section>
                  <SectionTitle>{t('dashboard.geo_region_dist_title')}</SectionTitle>
                  <RegionTypeChart distribution={regionDist} />
                </section>
              )}

              <section>
                <div className="flex items-center justify-between mb-2">
                  <SectionTitle>{t('dashboard.geo_top_gap')} ({sortedTerritories.length})</SectionTitle>
                  <button onClick={() => exportCSV(sortedTerritories)}
                    className="text-xs px-3 py-1 bg-atlas-navy border border-atlas-accent text-atlas-accent rounded hover:bg-atlas-accent hover:text-white transition-colors">
                    {t('dashboard.geo_export_csv')}
                  </button>
                </div>
                <TerritoryTable rows={sortedTerritories} sortCol={sortCol} sortDir={sortDir}
                  onSort={handleSort} onSelectTerritory={(id) => selectGeoTerritory(id)} />
              </section>

              <RankingsSection territories={territories} />

              <section>
                <SectionTitle>{t('dashboard.geo_expansion_title')}</SectionTitle>
                <ExpansionTargetPanel value={expansionTarget} onChange={setExpansionTarget}
                  recommended={expansionRecommended} accumulatedPotential={accumulatedPotential} />
              </section>
            </>
          )}

          {!loadedStation && !isLoading && (
            <div className="flex flex-col items-center justify-center flex-1 text-atlas-muted text-sm gap-2 py-12">
              <span className="text-3xl">🗺️</span>
              <p>{t('dashboard.geo_no_data')}</p>
            </div>
          )}

          {isLoading && (
            <div className="flex flex-col items-center justify-center flex-1 gap-3 py-12 text-atlas-muted">
              <Spinner size="lg" />
              <span className="text-sm">{t('dashboard.geo_loading')}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const TabButton: React.FC<{ active: boolean; onClick: () => void; children: React.ReactNode }> = ({ active, onClick, children }) => (
  <button onClick={onClick}
    className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${active ? 'border-atlas-accent text-atlas-accent' : 'border-transparent text-atlas-muted hover:text-atlas-light'}`}>
    {children}
  </button>
);

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">{children}</h2>
);

const REGION_COLORS = ['#00a8e1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

const RegionTypeChart: React.FC<{ distribution: Record<string, number> }> = ({ distribution }) => {
  const { text } = chartTheme();
  const labels = Object.keys(distribution).map((k) => regionTypeLabel(k as Parameters<typeof regionTypeLabel>[0]));
  const data = Object.values(distribution);
  const chartData = { labels, datasets: [{ data, backgroundColor: REGION_COLORS.slice(0, data.length), borderWidth: 1, borderColor: '#1e2a38' }] };
  const options = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true, position: 'right' as const, labels: { color: text, boxWidth: 12, padding: 8, font: { size: 11 } } }, title: { display: false } } };
  return <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4" style={{ height: 220 }}><Pie data={chartData} options={options} /></div>;
};

interface TerritoryTableProps {
  rows: TerritoryOutput[];
  sortCol: SortCol;
  sortDir: SortDir;
  onSort: (col: SortCol) => void;
  onSelectTerritory: (id: string) => void;
}

const TerritoryTable: React.FC<TerritoryTableProps> = ({ rows, sortCol, sortDir, onSort, onSelectTerritory }) => {
  const { t } = useTranslation();

  const GEO_COLUMNS: { key: keyof TerritoryOutput; label: string }[] = [
    { key: 'territory_id', label: t('dashboard.geo_col_territory') },
    { key: 'region_type', label: t('dashboard.geo_col_type') },
    { key: 'potential_score', label: t('dashboard.geo_col_potential') },
    { key: 'current_partners', label: t('dashboard.geo_col_partners') },
    { key: 'gap', label: t('dashboard.geo_col_gap') },
    { key: 'model_confidence', label: t('dashboard.geo_col_confidence') },
  ];

  if (rows.length === 0) return <div className="bg-atlas-dark border border-atlas-navy rounded-lg text-atlas-muted text-center py-6 text-sm">{t('dashboard.no_data')}</div>;
  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
      <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-atlas-darker sticky top-0 z-10">
            <tr>
              {GEO_COLUMNS.map((col) => (
                <th key={col.key} onClick={() => onSort(col.key)}
                  className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide cursor-pointer select-none hover:text-atlas-light transition-colors whitespace-nowrap">
                  {col.label}
                  {sortCol === col.key ? <span className="text-atlas-accent ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span> : <span className="text-atlas-muted ml-1 opacity-50">↕</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.territory_id} onClick={() => onSelectTerritory(row.territory_id)}
                className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors cursor-pointer">
                <td className="px-3 py-2 text-atlas-light font-medium whitespace-nowrap">
                  {row.territory_id}
                  {row.high_opportunity && <span className="ml-1 text-yellow-400 text-xs" title="Alta oportunidade">★</span>}
                  {row.low_confidence && <span className="ml-1 text-red-400 text-xs" title="Baixa confiança">⚠</span>}
                </td>
                <td className="px-3 py-2 text-atlas-muted whitespace-nowrap">{regionTypeLabel(row.region_type)}</td>
                <td className="px-3 py-2 text-right font-medium" style={{ color: potentialScoreToColor(row.potential_score) }}>{row.potential_score.toFixed(1)}</td>
                <td className="px-3 py-2 text-atlas-light text-right">{row.current_partners}</td>
                <td className={`px-3 py-2 text-right font-medium ${row.gap >= 0 ? 'text-green-400' : 'text-red-400'}`}>{formatGap(row.gap)}</td>
                <td className="px-3 py-2 text-atlas-muted text-right">{(row.model_confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const RankingsSection: React.FC<{ territories: TerritoryOutput[] }> = ({ territories }) => {
  const { t } = useTranslation();
  if (territories.length === 0) return null;
  const byPotential = [...territories].sort((a, b) => b.potential_score - a.potential_score).slice(0, 5);
  return (
    <section>
      <SectionTitle>{t('dashboard.geo_top_territories')}</SectionTitle>
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
        {byPotential.map((t, i) => (
          <div key={t.territory_id} className="flex items-center gap-3 px-3 py-2 border-b border-atlas-navy last:border-0 hover:bg-atlas-navy transition-colors">
            <span className="text-atlas-muted text-xs w-5 text-right shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <p className="text-atlas-light text-sm truncate">{t.territory_id}</p>
              <p className="text-atlas-muted text-xs truncate">{regionTypeLabel(t.region_type)}</p>
            </div>
            <span className="text-sm font-semibold shrink-0" style={{ color: potentialScoreToColor(t.potential_score) }}>{t.potential_score.toFixed(1)}</span>
          </div>
        ))}
      </div>
    </section>
  );
};

interface ExpansionTargetPanelProps {
  value: number;
  onChange: (v: number) => void;
  recommended: TerritoryOutput[];
  accumulatedPotential: number;
}

const ExpansionTargetPanel: React.FC<ExpansionTargetPanelProps> = ({ value, onChange, recommended, accumulatedPotential }) => {
  const { t } = useTranslation();
  const { text, grid } = chartTheme();
  const barData = {
    labels: recommended.map((t) => t.territory_id),
    datasets: [{ label: 'Potencial', data: recommended.map((t) => t.potential_score), backgroundColor: recommended.map((t) => potentialScoreToColor(t.potential_score)), borderWidth: 0 }],
  };
  const barOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: false } }, scales: { x: { ticks: { color: text, maxRotation: 45, font: { size: 10 } }, grid: { color: grid } }, y: { ticks: { color: text, font: { size: 10 } }, grid: { color: grid } } } };
  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <label className="text-atlas-muted text-sm shrink-0">{t('dashboard.geo_expansion_label')}:</label>
        <input type="range" min={5} max={100} step={5} value={value} onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-atlas-accent" />
        <span className="text-atlas-light text-sm font-semibold w-10 text-right shrink-0">{value}%</span>
      </div>
      {recommended.length > 0 ? (
        <>
          <p className="text-atlas-muted text-xs">{recommended.length} {t('dashboard.geo_expansion_territories')} — {t('dashboard.geo_expansion_potential')}: <span className="text-atlas-light font-medium">{accumulatedPotential.toFixed(1)}</span></p>
          <div style={{ height: 180 }}><Bar data={barData} options={barOptions} /></div>
        </>
      ) : (
        <p className="text-atlas-muted text-xs">Nenhum território disponível para a meta selecionada.</p>
      )}
    </div>
  );
};

export default GeoIntelligenceDashboard;
