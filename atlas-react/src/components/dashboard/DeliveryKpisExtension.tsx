/**
 * DeliveryKpisExtension.tsx
 * =========================
 * Extensão da seção de indicadores do Dashboard Operacional com KPIs
 * derivados de `deliveries_summary.json`:
 *
 * 1. Parceiros ativos na semana passada — hubs (canal IHS_STORE) que
 *    despacharam ao menos 1 pacote nos últimos 7 dias da janela.
 * 2. Variação de volume entre as duas últimas semanas — soma dos
 *    últimos 7 dias vs soma dos 7 anteriores, com cor verde/vermelha.
 *
 * Também renderiza um gráfico de linha com o volume diário por hub
 * delivery (só canal IHS_STORE), agregado e respeitando o recorte de
 * hierarquia aplicado no Dashboard.
 *
 * Todos os cálculos respeitam os filtros de BDM/Base/CTL/ADE/Território
 * via `filterPartnersByHierarchy`, para que qualquer recorte feito no
 * topo reflita nestes indicadores automaticamente.
 *
 * Arquitetura:
 * - `useHubDeliveryMetrics`: hook compartilhado que faz o recorte
 *   hierárquico + filtragem por canal IHS_STORE e retorna métricas
 *   semanais e a série diária. Isolar o cálculo num hook permite que
 *   `DeliveryKpiCards` (renderizados junto com os KPIs gerais) e
 *   `DeliveryHubLineChart` (renderizado abaixo) não dupliquem trabalho
 *   nem precisem compartilhar props.
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartOptions,
  type ChartData,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useStore } from '../../store';
import KpiCard from './KpiCard';
import type { PartnerDeliveryStats } from '../../store/types';
import type { DashboardFilters, ReportData } from '../../lib/reportUtils';
import {
  buildHierarchyIndex,
  filterPartnersByHierarchy,
} from '../../lib/deliveriesHierarchy';

// Registration idempotente — Chart.js ignora duplicatas.
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

interface Props {
  filters: DashboardFilters;
  reportData: ReportData | null;
}

interface WeeklyMetrics {
  activePartnersLastWeek: number;
  variationPct: number | null;
  variationAvailable: boolean;
  dailySeries: { date: string; total: number }[];
  periodTotal: number;
  hasData: boolean;
}

const DAYS_PER_WEEK = 7;

/**
 * Agrega os KPIs semanais a partir dos parceiros hub (IHS_STORE) já
 * filtrados pela hierarquia.
 *
 * Regras:
 * - "Semana passada" = últimos 7 dias da janela de entregas (date_max
 *   inclusive). Não usamos "semana ISO" porque a base de pacotes pode
 *   terminar em qualquer dia — o importante é dar um recorte de 7 dias
 *   corridos e consistente com o backend.
 * - Variação só é calculada se a janela cobrir ≥ 14 dias. Se o período
 *   prior for zero, retorna 100% (todo o volume é "novo").
 */
function computeWeeklyMetrics(
  partners: PartnerDeliveryStats[],
  periodDates: string[],
): WeeklyMetrics {
  if (partners.length === 0 || periodDates.length === 0) {
    return {
      activePartnersLastWeek: 0,
      variationPct: null,
      variationAvailable: false,
      dailySeries: periodDates.map((d) => ({ date: d, total: 0 })),
      periodTotal: 0,
      hasData: false,
    };
  }

  const sortedDates = [...periodDates].sort();
  const lastWeekSet = new Set(sortedDates.slice(-DAYS_PER_WEEK));
  const priorWeekSet = new Set(
    sortedDates.slice(
      Math.max(0, sortedDates.length - 2 * DAYS_PER_WEEK),
      sortedDates.length - DAYS_PER_WEEK,
    ),
  );

  const dailyAgg = new Map<string, number>();
  for (const d of sortedDates) dailyAgg.set(d, 0);

  let lastWeekTotal = 0;
  let priorWeekTotal = 0;
  let activePartners = 0;

  for (const p of partners) {
    let partnerLastWeek = 0;
    for (const entry of p.daily_series) {
      dailyAgg.set(entry.date, (dailyAgg.get(entry.date) ?? 0) + entry.total);
      if (lastWeekSet.has(entry.date)) {
        partnerLastWeek += entry.total;
        lastWeekTotal += entry.total;
      } else if (priorWeekSet.has(entry.date)) {
        priorWeekTotal += entry.total;
      }
    }
    if (partnerLastWeek > 0) activePartners += 1;
  }

  const variationAvailable = priorWeekSet.size === DAYS_PER_WEEK;
  let variationPct: number | null = null;
  if (variationAvailable) {
    if (priorWeekTotal > 0) {
      variationPct = ((lastWeekTotal - priorWeekTotal) / priorWeekTotal) * 100;
    } else if (lastWeekTotal > 0) {
      variationPct = 100;
    } else {
      variationPct = 0;
    }
  }

  const dailySeries = sortedDates.map((d) => ({ date: d, total: dailyAgg.get(d) ?? 0 }));
  const periodTotal = dailySeries.reduce((a, r) => a + r.total, 0);

  return {
    activePartnersLastWeek: activePartners,
    variationPct,
    variationAvailable,
    dailySeries,
    periodTotal,
    hasData: true,
  };
}

// ---------------------------------------------------------------------------
// Hook compartilhado
// ---------------------------------------------------------------------------

export function useHubDeliveryMetrics(
  filters: DashboardFilters,
  reportData: ReportData | null,
): WeeklyMetrics {
  const summary = useStore((s) => s.deliveries.summary);
  const hierarchyIndex = useMemo(() => buildHierarchyIndex(reportData), [reportData]);

  const hubPartners = useMemo<PartnerDeliveryStats[]>(() => {
    if (!summary) return [];
    const scoped = filterPartnersByHierarchy(summary.partners, filters, hierarchyIndex);
    return scoped.filter((p) => p.canal_dominante === 'IHS_STORE');
  }, [summary, filters, hierarchyIndex]);

  const periodDates = useMemo<string[]>(() => {
    if (!summary) return [];
    const any = Object.values(summary.daily_by_station)[0];
    if (any && any.length > 0) return any.map((e) => e.date);
    const fromPartner = summary.partners[0]?.daily_series.map((e) => e.date) ?? [];
    return fromPartner;
  }, [summary]);

  return useMemo(
    () => computeWeeklyMetrics(hubPartners, periodDates),
    [hubPartners, periodDates],
  );
}

// ---------------------------------------------------------------------------
// DeliveryKpiCards — renderiza só os 2 cards (Hubs ativos + Δ 7d)
// ---------------------------------------------------------------------------

export const DeliveryKpiCards: React.FC<Props> = ({ filters, reportData }) => {
  const { t } = useTranslation();
  const isLoadingSummary = useStore((s) => s.deliveries.isLoadingSummary);
  const summary = useStore((s) => s.deliveries.summary);
  const metrics = useHubDeliveryMetrics(filters, reportData);

  // Enquanto o summary carrega, não renderizamos para evitar cards
  // "piscando" com zeros. Quando falha de carregar, também ficamos
  // silenciosos — a aba Operacional não é o lugar de mostrar erro de
  // deliveries (Pacotes e Insights cuidam disso).
  if (isLoadingSummary || !summary) return null;

  const variationLabel =
    metrics.variationAvailable && metrics.variationPct !== null
      ? `${metrics.variationPct > 0 ? '+' : ''}${metrics.variationPct.toFixed(1)}%`
      : 'N/A';

  const variationColorClass =
    !metrics.variationAvailable || metrics.variationPct === null
      ? 'text-atlas-light'
      : metrics.variationPct > 0
        ? 'text-green-400'
        : metrics.variationPct < 0
          ? 'text-red-400'
          : 'text-atlas-muted';

  const variationTrend: 'up' | 'down' | 'neutral' | undefined =
    !metrics.variationAvailable || metrics.variationPct === null
      ? undefined
      : metrics.variationPct > 0
        ? 'up'
        : metrics.variationPct < 0
          ? 'down'
          : 'neutral';

  return (
    <>
      <KpiCard
        label={t('dashboard.kpi_active_hubs_last_week')}
        value={metrics.activePartnersLastWeek.toLocaleString('pt-BR')}
      />
      <KpiCard
        label={t('dashboard.kpi_hub_weekly_variation')}
        value={variationLabel}
        valueClassName={variationColorClass}
        trend={variationTrend}
      />
    </>
  );
};

// ---------------------------------------------------------------------------
// DeliveryHubLineChart — gráfico de volume diário por hub delivery
// ---------------------------------------------------------------------------

const COLOR_HUB = '#00a8e1';
const COLOR_GRID = '#1e2a38';
const COLOR_MUTED = '#7b8fa3';

export const DeliveryHubLineChart: React.FC<Props> = ({ filters, reportData }) => {
  const { t } = useTranslation();
  const isLoadingSummary = useStore((s) => s.deliveries.isLoadingSummary);
  const summary = useStore((s) => s.deliveries.summary);
  const metrics = useHubDeliveryMetrics(filters, reportData);

  const chartData = useMemo<ChartData<'line'>>(
    () => ({
      labels: metrics.dailySeries.map((d) => d.date.slice(5)), // MM-DD
      datasets: [
        {
          label: t('dashboard.hub_delivery_daily_label'),
          data: metrics.dailySeries.map((d) => d.total),
          borderColor: COLOR_HUB,
          backgroundColor: `${COLOR_HUB}33`,
          fill: true,
          tension: 0.25,
          pointRadius: 2,
          pointHoverRadius: 4,
          borderWidth: 2,
        },
      ],
    }),
    [metrics.dailySeries, t],
  );

  const chartOptions = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) =>
              `${t('dashboard.hub_delivery_daily_label')}: ${Number(ctx.parsed.y).toLocaleString('pt-BR')}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: COLOR_MUTED, font: { size: 10 }, maxRotation: 0, autoSkip: true },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: COLOR_MUTED,
            font: { size: 10 },
            callback: (v) => Number(v).toLocaleString('pt-BR'),
          },
          grid: { color: COLOR_GRID },
        },
      },
    }),
    [t],
  );

  if (isLoadingSummary || !summary) return null;
  if (metrics.dailySeries.length === 0) return null;

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <div className="flex flex-col">
          <h3 className="text-atlas-light font-semibold text-sm">
            {t('dashboard.hub_delivery_chart_title')}
          </h3>
          <span className="text-atlas-muted text-xs">
            {t('dashboard.hub_delivery_chart_subtitle')}
          </span>
        </div>
        <div className="text-right">
          <span className="text-atlas-muted text-[10px] uppercase tracking-widest block">
            {t('dashboard.hub_delivery_total_label')}
          </span>
          <span className="text-atlas-light font-semibold text-base">
            {metrics.periodTotal.toLocaleString('pt-BR')}
          </span>
        </div>
      </div>
      <div style={{ height: 240 }}>
        <Line data={chartData} options={chartOptions} />
      </div>
    </div>
  );
};
