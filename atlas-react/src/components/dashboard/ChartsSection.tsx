import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
} from 'chart.js';
import { Doughnut, Bar } from 'react-chartjs-2';
import type { Partner } from '../../store/types';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title);

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const CHART_COLORS = [
  '#00a8e1',
  '#4daf4a',
  '#377eb8',
  '#e41a1c',
  '#984ea3',
  '#ff7f00',
  '#a65628',
  '#f781bf',
  '#999999',
  '#66c2a5',
];

interface ChartsSectionProps {
  data: Partner[];
}

const ChartsSection: React.FC<ChartsSectionProps> = ({ data }) => {
  const { t } = useTranslation();
  const textColor = getCSSVar('--color-light') || '#ecf0f1';
  const gridColor = getCSSVar('--color-dark') || '#1e2a38';
  const bgColor = getCSSVar('--color-darker') || '#16202c';
  // Distribuição por Status (Doughnut)
  const statusChartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of data) {
      counts[p.status] = (counts[p.status] ?? 0) + 1;
    }
    const labels = Object.keys(counts);
    return {
      labels,
      datasets: [
        {
          data: labels.map((l) => counts[l]),
          backgroundColor: labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
          borderColor: bgColor,
          borderWidth: 2,
        },
      ],
    };
  }, [data]);

  // Parceiros por Delivery Station (Bar)
  const stationChartData = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const p of data) {
      const station = p.delivery_station || 'N/A';
      counts[station] = (counts[station] ?? 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
    return {
      labels: sorted.map(([s]) => s),
      datasets: [
        {
          label: t('dashboard.chart_partners_label'),
          data: sorted.map(([, c]) => c),
          backgroundColor: '#00a8e1cc',
          borderColor: '#00a8e1',
          borderWidth: 1,
        },
      ],
    };
  }, [data]);

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: { color: textColor, boxWidth: 12, padding: 8 },
      },
      title: {
        display: true,
        text: t('dashboard.chart_status_title'),
        color: textColor,
        font: { size: 14 },
      },
    },
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text: t('dashboard.chart_station_title'),
        color: textColor,
        font: { size: 14 },
      },
    },
    scales: {
      x: {
        ticks: { color: textColor, maxRotation: 45 },
        grid: { color: gridColor },
      },
      y: {
        ticks: { color: textColor },
        grid: { color: gridColor },
      },
    },
  };

  if (data.length === 0) {
    return (
      <div className="text-atlas-muted text-center py-8">
        Sem dados para exibir gráficos.
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 tablet:grid-cols-2 gap-4">
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4" style={{ height: 300 }}>
        <Doughnut data={statusChartData} options={doughnutOptions} />
      </div>
      <div className="bg-atlas-dark border border-atlas-navy rounded-lg p-4" style={{ height: 300 }}>
        <Bar data={stationChartData} options={barOptions} />
      </div>
    </div>
  );
};

export default ChartsSection;
