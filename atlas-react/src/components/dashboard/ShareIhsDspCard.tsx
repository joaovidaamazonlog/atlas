/**
 * ShareIhsDspCard.tsx
 * ===================
 * Card de %share IHS vs DSP ao longo do tempo, com seletor de DS.
 *
 * Formato: linha dupla (azul = IHS, laranja = DSP) com threshold pontilhado
 * em 50% para marcar a meta. Quando a DS é "all", agrega todas as DSs do
 * recorte hierárquico atual.
 *
 * A fonte dos dados é `summary.daily_by_station` — já zero-filled pelo
 * backend para cobrir todos os dias da janela, então não há descontinuidade
 * visual quando um DS não teve entregas em um dia.
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
  type ChartOptions,
  type ChartData,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import type { DeliveryStationTotals, DailyByStation } from '../../store/types';

// Registramos localmente os elementos necessários para o Line chart.
// Idempotente — Chart.js ignora re-registros de mesmo componente.
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

// Cores consistentes com o resto do app (donut e pin de oportunidades).
const COLOR_IHS = '#00a8e1';
const COLOR_DSP = '#ff8c42';
const COLOR_THRESHOLD = '#7b8fa3';
const COLOR_GRID = '#1e2a38';
const COLOR_MUTED = '#7b8fa3';
const TARGET_SHARE_PCT = 50;

interface Props {
  /** Totais por DS já recortados pela hierarquia aplicada. */
  stationTotals: Record<string, DeliveryStationTotals>;
  /** Série temporal diária por DS (zero-filled pelo backend). */
  dailyByStation: DailyByStation;
  /** Nº de dias da janela (fonte de verdade: summary.period.days). */
  periodDays: number;
  selectedDs: string;
  onChangeDs: (ds: string) => void;
}

/**
 * Agrega séries diárias de múltiplas DSs em uma série única.
 * Soma ihs / dsp / total por data; retorna array ordenado por data ASC.
 */
function aggregateDaily(
  dailyByStation: DailyByStation,
  stationFilter: string[] | null,
): { date: string; ihs: number; dsp: number; total: number }[] {
  const acc: Record<string, { ihs: number; dsp: number; total: number }> = {};
  const stations = stationFilter ?? Object.keys(dailyByStation);
  for (const ds of stations) {
    const series = dailyByStation[ds];
    if (!series) continue;
    for (const entry of series) {
      if (!acc[entry.date]) {
        acc[entry.date] = { ihs: 0, dsp: 0, total: 0 };
      }
      acc[entry.date].ihs += entry.ihs;
      acc[entry.date].dsp += entry.dsp;
      acc[entry.date].total += entry.total;
    }
  }
  return Object.keys(acc)
    .sort()
    .map((date) => ({ date, ...acc[date] }));
}

const ShareIhsDspCard: React.FC<Props> = ({
  stationTotals,
  dailyByStation,
  periodDays,
  selectedDs,
  onChangeDs,
}) => {
  const { t } = useTranslation();

  const stations = useMemo(
    () => Object.keys(stationTotals).sort(),
    [stationTotals],
  );

  // Totais agregados (para o painel da direita: IHS/DSP/Outros/Total)
  const totals = useMemo(() => {
    if (selectedDs === 'all') {
      let ihs = 0;
      let dsp = 0;
      let other = 0;
      for (const ds of Object.keys(stationTotals)) {
        const st = stationTotals[ds];
        ihs += st.ihs;
        dsp += st.dsp;
        other += st.other;
      }
      const total = ihs + dsp + other;
      return {
        ihs,
        dsp,
        other,
        total,
        ihs_pct: total ? (ihs / total) * 100 : 0,
        dsp_pct: total ? (dsp / total) * 100 : 0,
      };
    }
    const st = stationTotals[selectedDs];
    if (!st) return null;
    return {
      ihs: st.ihs,
      dsp: st.dsp,
      other: st.other,
      total: st.total,
      ihs_pct: st.ihs_share_pct,
      dsp_pct: st.dsp_share_pct,
    };
  }, [stationTotals, selectedDs]);

  // Série diária (array de pontos {date, ihs, dsp, total})
  const series = useMemo(() => {
    const filter =
      selectedDs === 'all'
        ? Object.keys(stationTotals) // respeita o recorte hierárquico
        : [selectedDs];
    return aggregateDaily(dailyByStation, filter);
  }, [dailyByStation, stationTotals, selectedDs]);

  // Dados do Chart.js: duas linhas (IHS, DSP) + uma linha pontilhada em 50%.
  const chartData = useMemo<ChartData<'line'>>(() => {
    const labels = series.map((p) => {
      // Mostra MM-DD (labels completos em 15+ dias ficam ilegíveis).
      const parts = p.date.split('-');
      return `${parts[1]}-${parts[2]}`;
    });

    const ihsPct = series.map((p) => (p.total > 0 ? (p.ihs / p.total) * 100 : 0));
    const dspPct = series.map((p) => (p.total > 0 ? (p.dsp / p.total) * 100 : 0));
    const threshold = series.map(() => TARGET_SHARE_PCT);

    return {
      labels,
      datasets: [
        {
          label: 'Hub Delivery',
          data: ihsPct,
          borderColor: COLOR_IHS,
          backgroundColor: COLOR_IHS,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.2,
        },
        {
          label: 'DSP',
          data: dspPct,
          borderColor: COLOR_DSP,
          backgroundColor: COLOR_DSP,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.2,
        },
        {
          // Threshold de 50% — dataset sintético: mesma constante em cada ponto,
          // estilizado como linha pontilhada cinza. Não interativa.
          label: `${t('packages.share_target')} ${TARGET_SHARE_PCT}%`,
          data: threshold,
          borderColor: COLOR_THRESHOLD,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          borderDash: [6, 4],
          pointRadius: 0,
          pointHoverRadius: 0,
          tension: 0,
        },
      ],
    };
  }, [series, t]);

  const chartOptions = useMemo<ChartOptions<'line'>>(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: COLOR_MUTED,
            boxWidth: 10,
            boxHeight: 10,
            padding: 10,
            font: { size: 11 },
            usePointStyle: true,
          },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: COLOR_MUTED, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 8 },
          grid: { display: false },
        },
        y: {
          min: 0,
          max: 100,
          ticks: {
            color: COLOR_MUTED,
            font: { size: 10 },
            callback: (v) => `${v}%`,
            stepSize: 25,
          },
          grid: { color: COLOR_GRID },
        },
      },
    }),
    [],
  );

  if (!totals) {
    return (
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4 text-atlas-muted text-sm">
        {t('packages.no_data_for_station')}
      </div>
    );
  }

  return (
    <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-atlas-muted text-xs uppercase tracking-widest">
          {t('packages.share_title')}
        </h3>
        <select
          value={selectedDs}
          onChange={(e) => onChangeDs(e.target.value)}
          className="bg-atlas-darker border border-atlas-navy rounded px-2 py-1 text-atlas-light text-xs focus:outline-none focus:border-atlas-accent"
        >
          <option value="all">{t('packages.all_stations')}</option>
          {stations.map((ds) => (
            <option key={ds} value={ds}>
              {ds}
            </option>
          ))}
        </select>
      </div>

      {/* Chart de linhas: %share dia a dia */}
      <div style={{ height: 220 }}>
        {series.length > 0 ? (
          <Line data={chartData} options={chartOptions} />
        ) : (
          <div className="flex items-center justify-center h-full text-atlas-muted text-sm">
            {t('packages.no_data_for_station')}
          </div>
        )}
      </div>

      {/* Totais agregados — resumo do período */}
      <div className="mt-4 pt-3 border-t border-atlas-navy grid grid-cols-2 tablet:grid-cols-4 gap-3 text-xs">
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ background: COLOR_IHS }} />
          <div className="flex flex-col">
            <span className="text-atlas-light font-semibold">Hub Delivery</span>
            <span className="text-atlas-muted">
              {totals.ihs.toLocaleString('pt-BR')} ({totals.ihs_pct.toFixed(1)}%)
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-3 h-3 rounded-sm" style={{ background: COLOR_DSP }} />
          <div className="flex flex-col">
            <span className="text-atlas-light font-semibold">DSP</span>
            <span className="text-atlas-muted">
              {totals.dsp.toLocaleString('pt-BR')} ({totals.dsp_pct.toFixed(1)}%)
            </span>
          </div>
        </div>
        {totals.other > 0 && (
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-3 h-3 rounded-sm"
              style={{ background: COLOR_THRESHOLD }}
            />
            <div className="flex flex-col">
              <span className="text-atlas-light">{t('packages.other_label')}</span>
              <span className="text-atlas-muted">{totals.other.toLocaleString('pt-BR')}</span>
            </div>
          </div>
        )}
        <div className="flex flex-col">
          <span className="text-atlas-muted text-[10px] uppercase tracking-wider">
            {t('packages.total_label')}
          </span>
          <span className="text-atlas-light font-semibold">
            {totals.total.toLocaleString('pt-BR')}
            <span className="text-atlas-muted text-[10px] ml-1">({periodDays}d)</span>
          </span>
        </div>
      </div>
    </div>
  );
};

export default ShareIhsDspCard;
