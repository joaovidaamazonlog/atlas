/**
 * FiltersTab.tsx
 * ==============
 * - Carteiras cascateadas pela Delivery Station selecionada
 * - fitBounds automático ao filtrar (via store.fitBoundsRef)
 * - Sem campo de busca por nome (agora é a SearchBar no mapa)
 */

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useStore } from '../../store';
import { getUniqueValues } from '../../store/actions/dataActions';

const STATUS_OPTIONS = ['Active', 'Inactive', 'Onboarding', 'BG Checks', 'Prospect', 'Exited', 'New'];

const INITIATIVES_OPTIONS = [
  { value: 'all', label: 'Todos' },
  { value: 'HCP Host Partner', label: 'HCP Host Partner' },
  { value: 'HCP Pick Up Partner', label: 'HCP Pick Up Partner' },
  { value: 'Hub Hero', label: 'Hub Hero' },
  { value: 'null', label: '(Sem iniciativa)' },
];

function MultiSelect({ label, options, selected, onChange }: {
  label: string; options: string[]; selected: string[]; onChange: (v: string[]) => void;
}) {
  const toggle = (val: string) =>
    onChange(selected.includes(val) ? selected.filter((v) => v !== val) : [...selected, val]);

  return (
    <div className="mb-3">
      <label className="block text-xs font-medium text-atlas-muted mb-1">{label}</label>
      <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto p-1 bg-atlas-darker rounded border border-white/10">
        {options.map((opt) => (
          <button key={opt} type="button" onClick={() => toggle(opt)}
            className={['px-2 py-1 rounded text-xs transition-colors min-h-[28px] focus:outline-none',
              selected.includes(opt) ? 'bg-atlas-accent text-atlas-darker font-semibold' : 'bg-white/10 text-atlas-light hover:bg-white/20',
            ].join(' ')}>
            {opt}
          </button>
        ))}
        {options.length === 0 && <span className="text-xs text-atlas-muted px-1 py-1">Carregando...</span>}
      </div>
    </div>
  );
}

export default function FiltersTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const applyFilters = useStore((s) => s.applyFilters);
  const resetFilters = useStore((s) => s.resetFilters);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);

  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([]);
  const [selectedStations, setSelectedStations] = useState<string[]>([]);
  const [selectedBuckets, setSelectedBuckets] = useState<string[]>([]);
  const [initiativesFilter, setInitiativesFilter] = useState('all');
  const [jurisdictionFilter, setJurisdictionFilter] = useState('all');

  const stationOptions = useMemo(() => getUniqueValues(allMarkersData, 'delivery_station').sort(), [allMarkersData]);

  // Carteiras cascateadas pelas stations selecionadas
  const bucketOptions = useMemo(() => {
    const base = selectedStations.length > 0
      ? allMarkersData.filter((p) => selectedStations.includes(p.delivery_station))
      : allMarkersData;
    return getUniqueValues(base, 'bucket_ade').sort();
  }, [allMarkersData, selectedStations]);

  // Limpa carteiras inválidas quando stations mudam
  useEffect(() => {
    setSelectedBuckets((prev) => prev.filter((b) => bucketOptions.includes(b)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bucketOptions]);

  const jurisdictionOptions = useMemo(() => getUniqueValues(allMarkersData, 'jurisdiction_type').sort(), [allMarkersData]);

  // Aplica filtros automaticamente
  useEffect(() => {
    applyFilters({
      selectedStatuses: selectedStatuses.length ? selectedStatuses : 'all',
      selectedStations: selectedStations.length ? selectedStations : 'all',
      selectedBuckets: selectedBuckets.length ? selectedBuckets : 'all',
      initiativesFilter,
      jurisdictionFilter,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStatuses, selectedStations, selectedBuckets, initiativesFilter, jurisdictionFilter]);

  // fitBounds quando station ou carteira está selecionada e dados mudam
  useEffect(() => {
    if (selectedStations.length === 0 && selectedBuckets.length === 0) return;
    const coords = currentFilteredData
      .filter((p) => p.lat != null && p.lon != null && p.lat !== 0 && p.lon !== 0)
      .map((p) => [p.lat!, p.lon!] as [number, number]);
    fitBoundsRef.current?.(coords);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentFilteredData]);

  const handleClear = useCallback(() => {
    setSelectedStatuses([]);
    setSelectedStations([]);
    setSelectedBuckets([]);
    setInitiativesFilter('all');
    setJurisdictionFilter('all');
    resetFilters();
  }, [resetFilters]);

  return (
    <div className="p-3">
      <MultiSelect label="Status" options={STATUS_OPTIONS} selected={selectedStatuses} onChange={setSelectedStatuses} />
      <MultiSelect label="Delivery Station" options={stationOptions} selected={selectedStations} onChange={setSelectedStations} />
      <MultiSelect label="Carteira ADE" options={bucketOptions} selected={selectedBuckets} onChange={setSelectedBuckets} />

      <div className="mb-3">
        <label htmlFor="filter-initiatives" className="block text-xs font-medium text-atlas-muted mb-1">Delivery Initiatives</label>
        <select id="filter-initiatives" value={initiativesFilter} onChange={(e) => setInitiativesFilter(e.target.value)}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]">
          {INITIATIVES_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
        </select>
      </div>

      <div className="mb-4">
        <label htmlFor="filter-jurisdiction" className="block text-xs font-medium text-atlas-muted mb-1">Jurisdiction Type</label>
        <select id="filter-jurisdiction" value={jurisdictionFilter} onChange={(e) => setJurisdictionFilter(e.target.value)}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]">
          <option value="all">Todos</option>
          {jurisdictionOptions.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      </div>

      <button type="button" onClick={handleClear}
        className="w-full py-3 px-4 rounded bg-white/10 text-atlas-light text-sm font-medium hover:bg-white/20 focus:outline-none min-h-[44px] transition-colors">
        Limpar Filtros
      </button>
    </div>
  );
}
