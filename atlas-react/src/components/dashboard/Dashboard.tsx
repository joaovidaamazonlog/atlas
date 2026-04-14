import React, { useEffect, useMemo, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Bar } from 'react-chartjs-2';
import { DATA_URLS } from '../../lib/config';
import {
  ReportData,
  DashboardFilters,
  TerritoryRow,
  filterBases,
  computeKPIs,
  sortTerritories,
  getStatusClass,
  getChartDataForBase,
} from '../../lib/reportUtils';
import { Spinner } from '../ui/Spinner';
import FilterCascade from './FilterCascade';
import KpiCard from './KpiCard';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortState = { column: string | null; direction: 'asc' | 'desc' };

// ---------------------------------------------------------------------------
// Territory table columns
// ---------------------------------------------------------------------------

const TERRITORY_COLUMNS: { key: string; label: string }[] = [
  { key: 'id', label: 'Território' },
  { key: 'baseCode', label: 'Base' },
  { key: 'ctl', label: 'CTL' },
  { key: 'dailyDemand', label: 'Demanda/dia' },
  { key: 'totalSlots', label: 'Vagas' },
  { key: 'openSlots', label: 'Em aberto' },
  { key: 'active', label: 'Ativos' },
  { key: 'onboarding', label: 'Onboarding' },
  { key: 'attainment', label: 'Attainment' },
  { key: 'accuracy', label: 'Acuracidade' },
];

// ---------------------------------------------------------------------------
// Chart options
// ---------------------------------------------------------------------------

const darkColor = '#ecf0f1';
const gridColor = '#1e2a38';

const barOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    title: {
      display: true,
      color: darkColor,
      font: { size: 13 },
    },
  },
  scales: {
    x: {
      ticks: { color: darkColor, maxRotation: 45, font: { size: 11 } },
      grid: { color: gridColor },
    },
    y: {
      ticks: { color: darkColor, font: { size: 11 } },
      grid: { color: gridColor },
    },
  },
};

// ---------------------------------------------------------------------------
// Dashboard component
// ---------------------------------------------------------------------------

const Dashboard: React.FC = () => {
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);
  const [filters, setFilters] = useState<DashboardFilters>({
    bdm: 'all',
    base: 'all',
    ctl: 'all',
    territory: 'all',
  });
  const [sortState, setSortState] = useState<SortState>({ column: null, direction: 'asc' });

  // Fetch on first mount or on retry (when reportData is null)
  useEffect(() => {
    if (reportData !== null) return;

    let cancelled = false;

    const fetchReport = async () => {
      setIsLoadingReport(true);
      setReportError(null);
      try {
        const res = await fetch(DATA_URLS.executiveReport);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
        const json = await res.json();
        if (!cancelled) {
          setReportData(json as ReportData);
        }
      } catch (err) {
        if (!cancelled) {
          setReportError(
            err instanceof Error ? err.message : 'Erro desconhecido ao carregar relatório.',
          );
        }
      } finally {
        if (!cancelled) {
          setIsLoadingReport(false);
        }
      }
    };

    fetchReport();

    return () => {
      cancelled = true;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportData, retryCount]);

  // Retry handler
  const handleRetry = () => {
    setReportData(null);
    setReportError(null);
    setIsLoadingReport(false);
    setRetryCount((c) => c + 1);
  };

  // Derived data via useMemo
  const filteredBases = useMemo(() => filterBases(reportData, filters), [reportData, filters]);
  const kpis = useMemo(() => computeKPIs(filteredBases), [filteredBases]);

  // Territory rows (flat list)
  const territoryRows = useMemo<TerritoryRow[]>(
    () =>
      filteredBases.flatMap((b) =>
        b.territories.map((t) => ({ ...t, baseCode: b.code })),
      ),
    [filteredBases],
  );

  // Sorted territory rows
  const sortedTerritories = useMemo(() => {
    if (!sortState.column) return territoryRows;
    return sortTerritories(territoryRows, sortState.column, sortState.direction);
  }, [territoryRows, sortState]);

  // Chart data
  const chartData = useMemo(
    () => getChartDataForBase(filteredBases, filters.base),
    [filteredBases, filters.base],
  );

  // Column sort handler
  const handleColumnSort = (column: string) => {
    setSortState((prev) => ({
      column,
      direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  // ---------------------------------------------------------------------------
  // Render: loading
  // ---------------------------------------------------------------------------

  if (isLoadingReport) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-3 text-atlas-muted">
        <Spinner size="lg" />
        <span className="text-sm">Carregando relatório executivo...</span>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: error
  // ---------------------------------------------------------------------------

  if (reportError) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-3 p-6">
        <span className="text-3xl">⚠️</span>
        <p className="text-red-400 text-center text-sm">{reportError}</p>
        <button
          onClick={handleRetry}
          className="mt-2 px-4 py-2 bg-atlas-accent text-atlas-darker text-sm font-semibold rounded hover:opacity-90 transition-opacity"
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: main dashboard
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col gap-4 p-4 bg-atlas-darker min-h-full overflow-y-auto">
      {/* Header */}
      {reportData?.generatedAt && (
        <p className="text-atlas-muted text-xs">
          Relatório gerado em: <span className="text-atlas-light">{reportData.generatedAt}</span>
        </p>
      )}

      {/* Filters */}
      <FilterCascade
        reportData={reportData}
        filters={filters}
        onFilterChange={setFilters}
        isLoading={isLoadingReport}
      />

      {/* KPI Cards */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">Indicadores</h2>
        <KpiSummaryGrid kpis={kpis} />
      </section>

      {/* Charts */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">Gráficos</h2>
        <DashboardCharts chartData={chartData} />
      </section>

      {/* Territory Table */}
      <section>
        <h2 className="text-atlas-muted text-xs uppercase tracking-widest mb-2">
          Territórios ({sortedTerritories.length})
        </h2>
        <TerritoryTable
          rows={sortedTerritories}
          sortState={sortState}
          onSort={handleColumnSort}
        />
      </section>
    </div>
  );
};

// ---------------------------------------------------------------------------
// KPI Summary Grid (8 cards)
// ---------------------------------------------------------------------------

interface KpiSummaryGridProps {
  kpis: ReturnType<typeof computeKPIs>;
}

const KpiSummaryGrid: React.FC<KpiSummaryGridProps> = ({ kpis }) => {
  const cards = [
    { label: 'Bases', value: kpis.totalBases },
    { label: 'Territórios', value: kpis.totalTerritories },
    {
      label: 'Demanda/dia',
      value: kpis.totalDailyDemand.toLocaleString('pt-BR', { maximumFractionDigits: 0 }),
    },
    { label: 'Vagas Ideais', value: kpis.totalIdealSlots },
    { label: 'Vagas em Aberto', value: kpis.totalOpenSlots },
    { label: 'Parceiros Ativos', value: kpis.totalActivePartners },
    {
      label: 'Attainment Médio',
      value: `${(kpis.avgAttainment * 100).toFixed(1)}%`,
    },
    {
      label: 'Cobertura Média',
      value: `${(kpis.avgCoverage * 100).toFixed(1)}%`,
    },
  ];

  return (
    <div className="grid grid-cols-2 tablet:grid-cols-4 gap-3">
      {cards.map((card) => (
        <KpiCard key={card.label} label={card.label} value={card.value} />
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Dashboard Charts
// ---------------------------------------------------------------------------

interface DashboardChartsProps {
  chartData: ReturnType<typeof getChartDataForBase>;
}

const DashboardCharts: React.FC<DashboardChartsProps> = ({ chartData }) => {
  if (chartData.attainmentByBase.labels.length === 0) {
    return (
      <div className="text-atlas-muted text-center py-6 text-sm">
        Sem dados para exibir gráficos.
      </div>
    );
  }

  const attainmentData = {
    labels: chartData.attainmentByBase.labels,
    datasets: [
      {
        label: 'Attainment (%)',
        data: chartData.attainmentByBase.data,
        backgroundColor: '#ff9900cc',
        borderColor: '#ff9900',
        borderWidth: 1,
      },
    ],
  };

  const partnersData = {
    labels: chartData.partnersByBase.labels,
    datasets: chartData.partnersByBase.datasets,
  };

  const attainmentOptions = {
    ...barOptions,
    plugins: {
      ...barOptions.plugins,
      legend: { display: false },
      title: { ...barOptions.plugins.title, display: true, text: 'Attainment por Base (%)' },
    },
  };

  const partnersOptions = {
    ...barOptions,
    plugins: {
      ...barOptions.plugins,
      legend: {
        display: true,
        labels: { color: darkColor, boxWidth: 12, padding: 8 },
      },
      title: { ...barOptions.plugins.title, display: true, text: 'Composição de Parceiros por Base' },
    },
  };

  return (
    <div className="grid grid-cols-1 tablet:grid-cols-2 gap-4">
      <div
        className="bg-atlas-dark border border-atlas-navy rounded-lg p-4"
        style={{ height: 280 }}
      >
        <Bar data={attainmentData} options={attainmentOptions} />
      </div>
      <div
        className="bg-atlas-dark border border-atlas-navy rounded-lg p-4"
        style={{ height: 280 }}
      >
        <Bar data={partnersData} options={partnersOptions} />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Territory Table
// ---------------------------------------------------------------------------

interface TerritoryTableProps {
  rows: TerritoryRow[];
  sortState: SortState;
  onSort: (column: string) => void;
}

const ATTAINMENT_THRESHOLDS = { green: 0.15, yellow: 0.05 };
const ACCURACY_THRESHOLDS = { green: 0.70, yellow: 0.40 };

const STATUS_CLASS_MAP: Record<string, string> = {
  'status-green': 'text-green-400',
  'status-yellow': 'text-yellow-400',
  'status-red': 'text-red-400',
};

const TerritoryTable: React.FC<TerritoryTableProps> = ({ rows, sortState, onSort }) => {
  if (rows.length === 0) {
    return (
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg text-atlas-muted text-center py-6 text-sm">
        Nenhum território encontrado.
      </div>
    );
  }

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg overflow-hidden">
      <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-atlas-darker sticky top-0 z-10">
            <tr>
              {TERRITORY_COLUMNS.map((col) => (
                <th
                  key={col.key}
                  onClick={() => onSort(col.key)}
                  className="px-3 py-3 text-left text-atlas-muted uppercase text-xs tracking-wide cursor-pointer select-none hover:text-atlas-light transition-colors whitespace-nowrap"
                >
                  {col.label}
                  <SortIndicator column={col.key} sortState={sortState} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const attClass =
                STATUS_CLASS_MAP[getStatusClass(row.attainment, ATTAINMENT_THRESHOLDS)];
              const accClass =
                STATUS_CLASS_MAP[getStatusClass(row.accuracy, ACCURACY_THRESHOLDS)];

              return (
                <tr
                  key={`${row.baseCode}-${row.id}`}
                  className="border-b border-atlas-navy hover:bg-atlas-navy transition-colors"
                >
                  <td className="px-3 py-2 text-atlas-light font-medium whitespace-nowrap">
                    {row.id}
                  </td>
                  <td className="px-3 py-2 text-atlas-muted whitespace-nowrap">{row.baseCode}</td>
                  <td className="px-3 py-2 text-atlas-muted whitespace-nowrap">{row.ctl}</td>
                  <td className="px-3 py-2 text-atlas-light text-right">
                    {row.dailyDemand.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}
                  </td>
                  <td className="px-3 py-2 text-atlas-light text-right">{row.totalSlots}</td>
                  <td className="px-3 py-2 text-atlas-light text-right">{row.openSlots}</td>
                  <td className="px-3 py-2 text-green-400 text-right">{row.active}</td>
                  <td className="px-3 py-2 text-yellow-400 text-right">{row.onboarding}</td>
                  <td className={`px-3 py-2 text-right font-medium ${attClass}`}>
                    {(row.attainment * 100).toFixed(1)}%
                  </td>
                  <td className={`px-3 py-2 text-right font-medium ${accClass}`}>
                    {(row.accuracy * 100).toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Sort indicator
// ---------------------------------------------------------------------------

const SortIndicator: React.FC<{ column: string; sortState: SortState }> = ({
  column,
  sortState,
}) => {
  if (sortState.column !== column) {
    return <span className="text-atlas-muted ml-1 opacity-50">↕</span>;
  }
  return (
    <span className="text-atlas-accent ml-1">
      {sortState.direction === 'asc' ? '↑' : '↓'}
    </span>
  );
};

export default Dashboard;
