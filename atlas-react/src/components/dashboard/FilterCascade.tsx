import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ReportData, DashboardFilters } from '../../lib/reportUtils';

interface FilterCascadeProps {
  reportData: ReportData | null;
  filters: DashboardFilters;
  onFilterChange: (filters: DashboardFilters) => void;
  isLoading?: boolean;
}

function unique(arr: string[]): string[] {
  return [...new Set(arr)].sort();
}

const FilterCascade: React.FC<FilterCascadeProps> = ({
  reportData,
  filters,
  onFilterChange,
  isLoading = false,
}) => {
  const { t } = useTranslation();
  const bases = reportData?.bases ?? [];

  // Available BDMs: all BDMs from reportData
  const bdmOptions = useMemo(() => unique(bases.map((b) => b.bdm)), [bases]);

  // Available Bases: filtered by selected BDM
  const baseOptions = useMemo(() => {
    const visible = filters.bdm !== 'all' ? bases.filter((b) => b.bdm === filters.bdm) : bases;
    return unique(visible.map((b) => b.code));
  }, [bases, filters.bdm]);

  // Available CTLs: from bases visible after BDM + Base filter
  const ctlOptions = useMemo(() => {
    let visible = filters.bdm !== 'all' ? bases.filter((b) => b.bdm === filters.bdm) : bases;
    if (filters.base !== 'all') visible = visible.filter((b) => b.code === filters.base);
    return unique(visible.flatMap((b) => b.territories.map((t) => t.ctl)));
  }, [bases, filters.bdm, filters.base]);

  // Available Territories: filtered by CTL (and base/bdm)
  const territoryOptions = useMemo(() => {
    let visible = filters.bdm !== 'all' ? bases.filter((b) => b.bdm === filters.bdm) : bases;
    if (filters.base !== 'all') visible = visible.filter((b) => b.code === filters.base);
    const terrs = visible.flatMap((b) =>
      filters.ctl !== 'all' ? b.territories.filter((t) => t.ctl === filters.ctl) : b.territories,
    );
    return unique(terrs.map((t) => t.id));
  }, [bases, filters.bdm, filters.base, filters.ctl]);

  const handleBdmChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ bdm: e.target.value, base: 'all', ctl: 'all', territory: 'all' });
  };

  const handleBaseChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ ...filters, base: e.target.value, ctl: 'all', territory: 'all' });
  };

  const handleCtlChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ ...filters, ctl: e.target.value, territory: 'all' });
  };

  const handleTerritoryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onFilterChange({ ...filters, territory: e.target.value });
  };

  const selectClass =
    'bg-atlas-darker border border-atlas-navy text-atlas-light text-sm rounded px-2 py-1 focus:outline-none focus:border-atlas-accent disabled:opacity-50 disabled:cursor-not-allowed';

  const filterDefs = [
    { label: t('dashboard.filter_bdm'), value: filters.bdm, options: bdmOptions, onChange: handleBdmChange },
    { label: t('dashboard.filter_base'), value: filters.base, options: baseOptions, onChange: handleBaseChange },
    { label: t('dashboard.filter_ctl'), value: filters.ctl, options: ctlOptions, onChange: handleCtlChange },
    {
      label: t('dashboard.filter_territory'),
      value: filters.territory,
      options: territoryOptions,
      onChange: handleTerritoryChange,
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 bg-atlas-dark border border-atlas-navy rounded-lg p-3">
      {filterDefs.map(({ label, value, options, onChange }) => (
        <div key={label} className="flex items-center gap-2">
          <label className="text-atlas-muted text-sm whitespace-nowrap">{label}:</label>
          <select
            value={value}
            onChange={onChange}
            disabled={isLoading}
            className={selectClass}
          >
            <option value="all">{t('dashboard.filter_all')}</option>
            {options.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  );
};

export default FilterCascade;
