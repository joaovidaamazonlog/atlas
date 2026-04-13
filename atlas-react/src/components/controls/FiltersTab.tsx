/**
 * FiltersTab.tsx
 * ==============
 * Aba de filtros do ControlPanel.
 * Campos: busca por nome (debounce 300ms), Status, Delivery Station,
 * Carteira ADE, Delivery Initiatives, Jurisdiction Type.
 */

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useStore } from '../../store';
import { getUniqueValues } from '../../store/actions/dataActions';
import { useDebounce } from '../../hooks/useDebounce';

const STATUS_OPTIONS = [
  'Active',
  'Inactive',
  'Onboarding',
  'BG Checks',
  'Prospect',
  'Exited',
  'New',
];

const INITIATIVES_OPTIONS = [
  { value: 'all', label: 'Todos' },
  { value: 'HCP Host Partner', label: 'HCP Host Partner' },
  { value: 'HCP Pick Up Partner', label: 'HCP Pick Up Partner' },
  { value: 'Hub Hero', label: 'Hub Hero' },
  { value: 'null', label: '(Sem iniciativa)' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const toggle = (val: string) => {
    if (selected.includes(val)) {
      onChange(selected.filter((v) => v !== val));
    } else {
      onChange([...selected, val]);
    }
  };

  return (
    <div className="mb-3">
      <label className="block text-xs font-medium text-atlas-muted mb-1">{label}</label>
      <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto p-1 bg-atlas-darker rounded border border-white/10">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={[
              'px-2 py-1 rounded text-xs transition-colors duration-150',
              'min-h-[28px] focus:outline-none focus-visible:ring-1 focus-visible:ring-atlas-accent',
              selected.includes(opt)
                ? 'bg-atlas-accent text-atlas-darker font-semibold'
                : 'bg-white/10 text-atlas-light hover:bg-white/20',
            ].join(' ')}
          >
            {opt}
          </button>
        ))}
        {options.length === 0 && (
          <span className="text-xs text-atlas-muted px-1 py-1">Carregando...</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FiltersTab
// ---------------------------------------------------------------------------

export default function FiltersTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const applyFilters = useStore((s) => s.applyFilters);
  const resetFilters = useStore((s) => s.resetFilters);

  // Local state
  const [nameSearch, setNameSearch] = useState('');
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [selectedStations, setSelectedStations] = useState<string[]>([]);
  const [selectedBuckets, setSelectedBuckets] = useState<string[]>([]);
  const [initiativesFilter, setInitiativesFilter] = useState('all');
  const [jurisdictionFilter, setJurisdictionFilter] = useState('all');

  const debouncedName = useDebounce(nameSearch, 300);

  // Populate selects from data
  const stationOptions = useMemo(
    () => getUniqueValues(allMarkersData, 'delivery_station').sort(),
    [allMarkersData]
  );
  const bucketOptions = useMemo(
    () => getUniqueValues(allMarkersData, 'bucket_ade').sort(),
    [allMarkersData]
  );
  const jurisdictionOptions = useMemo(
    () => getUniqueValues(allMarkersData, 'jurisdiction_type').sort(),
    [allMarkersData]
  );

  // Apply name search via debounce automatically
  useEffect(() => {
    if (debouncedName.trim()) {
      applyFilters({
        selectedStatuses: selectedStatuses.length ? selectedStatuses : 'all',
        selectedStations: selectedStations.length ? selectedStations : 'all',
        selectedBuckets: selectedBuckets.length ? selectedBuckets : 'all',
        initiativesFilter,
        jurisdictionFilter,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedName]);

  const handleApply = useCallback(() => {
    applyFilters({
      selectedStatuses: selectedStatuses.length ? selectedStatuses : 'all',
      selectedStations: selectedStations.length ? selectedStations : 'all',
      selectedBuckets: selectedBuckets.length ? selectedBuckets : 'all',
      initiativesFilter,
      jurisdictionFilter,
    });
  }, [applyFilters, selectedStatuses, selectedStations, selectedBuckets, initiativesFilter, jurisdictionFilter]);

  const handleClear = useCallback(() => {
    setNameSearch('');
    setSelectedStatuses([]);
    setSelectedStations([]);
    setSelectedBuckets([]);
    setInitiativesFilter('all');
    setJurisdictionFilter('all');
    resetFilters();
  }, [resetFilters]);

  return (
    <div className="p-3">
      {/* Busca por nome */}
      <div className="mb-3">
        <label htmlFor="filter-name" className="block text-xs font-medium text-atlas-muted mb-1">
          Busca por nome
        </label>
        <input
          id="filter-name"
          type="text"
          value={nameSearch}
          onChange={(e) => setNameSearch(e.target.value)}
          placeholder="Nome do parceiro..."
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light placeholder-atlas-muted',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        />
      </div>

      {/* Status */}
      <MultiSelect
        label="Status"
        options={STATUS_OPTIONS}
        selected={selectedStatuses}
        onChange={setSelectedStatuses}
      />

      {/* Delivery Station */}
      <MultiSelect
        label="Delivery Station"
        options={stationOptions}
        selected={selectedStations}
        onChange={setSelectedStations}
      />

      {/* Carteira ADE */}
      <MultiSelect
        label="Carteira ADE"
        options={bucketOptions}
        selected={selectedBuckets}
        onChange={setSelectedBuckets}
      />

      {/* Delivery Initiatives */}
      <div className="mb-3">
        <label
          htmlFor="filter-initiatives"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Delivery Initiatives
        </label>
        <select
          id="filter-initiatives"
          value={initiativesFilter}
          onChange={(e) => setInitiativesFilter(e.target.value)}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          {INITIATIVES_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Jurisdiction Type */}
      <div className="mb-4">
        <label
          htmlFor="filter-jurisdiction"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Jurisdiction Type
        </label>
        <select
          id="filter-jurisdiction"
          value={jurisdictionFilter}
          onChange={(e) => setJurisdictionFilter(e.target.value)}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          <option value="all">Todos</option>
          {jurisdictionOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleApply}
          className={[
            'flex-1 py-3 px-4 rounded bg-atlas-accent text-atlas-darker',
            'text-sm font-semibold transition-colors duration-150',
            'hover:bg-amber-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent',
            'min-h-[44px]',
          ].join(' ')}
        >
          Aplicar Filtros
        </button>
        <button
          type="button"
          onClick={handleClear}
          className={[
            'flex-1 py-3 px-4 rounded bg-white/10 text-atlas-light',
            'text-sm font-medium transition-colors duration-150',
            'hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30',
            'min-h-[44px]',
          ].join(' ')}
        >
          Limpar Filtros
        </button>
      </div>
    </div>
  );
}
