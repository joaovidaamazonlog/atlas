import React, { useMemo } from 'react';
import { useStore } from '../../store';
import { PERFORMANCE_GOALS } from '../../lib/config';
import KpiCard from './KpiCard';
import type { Partner } from '../../store/types';

interface KpiData {
  label: string;
  value: string | number;
  unit?: string;
  goal?: number;
}

function computeKpis(data: Partner[]): KpiData[] {
  const total = data.length;

  // Parceiros Ativos
  const activeCount = data.filter((p) => p.status === 'Active').length;

  // HCP Host Ratio: parceiros com HCP_host_partner não nulo / ativos
  const hostCount = data.filter(
    (p) => p.status === 'Active' && p.HCP_host_partner && p.HCP_host_partner.trim() !== ''
  ).length;
  const hcpHostRatio =
    activeCount > 0 ? parseFloat(((hostCount / activeCount) * 100).toFixed(1)) : 0;

  return [
    {
      label: 'Parceiros Ativos',
      value: activeCount,
      goal: PERFORMANCE_GOALS.activePartners,
    },
    {
      label: 'ADV Overall',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.advOverall,
    },
    {
      label: 'DEA',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.dea,
    },
    {
      label: 'EAD',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.ead,
    },
    {
      label: 'DCR',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.dcr,
    },
    {
      label: 'FDDS',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.fdds,
    },
    {
      label: 'FTDS',
      value: 'N/A',
      unit: '%',
      goal: PERFORMANCE_GOALS.ftds,
    },
    {
      label: 'HCP Host Ratio',
      value: activeCount > 0 ? hcpHostRatio : 'N/A',
      unit: '%',
      goal: parseFloat((PERFORMANCE_GOALS.hcpHostRatio * 100).toFixed(1)),
    },
    {
      label: 'SPR Médio',
      value: 'N/A',
      unit: 'R$',
      goal: PERFORMANCE_GOALS.sprMedio,
    },
    {
      label: 'Total Parceiros',
      value: total,
    },
  ];
}

const KpiGrid: React.FC = React.memo(() => {
  const currentFilteredData = useStore((s) => s.currentFilteredData);

  const kpis = useMemo(() => computeKpis(currentFilteredData), [currentFilteredData]);

  return (
    <div className="grid grid-cols-2 tablet:grid-cols-3 notebook:grid-cols-5 gap-3">
      {kpis.map((kpi) => (
        <KpiCard
          key={kpi.label}
          label={kpi.label}
          value={kpi.value}
          unit={kpi.unit}
          goal={kpi.goal}
        />
      ))}
    </div>
  );
});

KpiGrid.displayName = 'KpiGrid';

export default KpiGrid;
