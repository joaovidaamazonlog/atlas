import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
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

const KpiGrid: React.FC = React.memo(() => {
  const { t } = useTranslation();
  const currentFilteredData = useStore((s) => s.currentFilteredData);

  const kpis = useMemo((): KpiData[] => {
    const data: Partner[] = currentFilteredData;
    const total = data.length;

    // Active partners
    const activeCount = data.filter((p) => p.status === 'Active').length;

    // HCP Host Ratio: partners with HCP_host_partner not null / active
    const hostCount = data.filter(
      (p) => p.status === 'Active' && p.HCP_host_partner && p.HCP_host_partner.trim() !== ''
    ).length;
    const hcpHostRatio =
      activeCount > 0 ? parseFloat(((hostCount / activeCount) * 100).toFixed(1)) : 0;

    return [
      {
        label: t('dashboard.kpi_active_partners'),
        value: activeCount,
        goal: PERFORMANCE_GOALS.activePartners,
      },
      {
        label: t('dashboard.kpi_adv_overall'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.advOverall,
      },
      {
        label: t('dashboard.kpi_dea'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.dea,
      },
      {
        label: t('dashboard.kpi_ead'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.ead,
      },
      {
        label: t('dashboard.kpi_dcr'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.dcr,
      },
      {
        label: t('dashboard.kpi_fdds'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.fdds,
      },
      {
        label: t('dashboard.kpi_ftds'),
        value: 'N/A',
        unit: '%',
        goal: PERFORMANCE_GOALS.ftds,
      },
      {
        label: t('dashboard.kpi_hcp_host_ratio'),
        value: activeCount > 0 ? hcpHostRatio : 'N/A',
        unit: '%',
        goal: parseFloat((PERFORMANCE_GOALS.hcpHostRatio * 100).toFixed(1)),
      },
      {
        label: t('dashboard.kpi_spr_medio'),
        value: 'N/A',
        unit: 'R$',
        goal: PERFORMANCE_GOALS.sprMedio,
      },
      {
        label: 'Total',
        value: total,
      },
    ];
  }, [currentFilteredData, t]);

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
