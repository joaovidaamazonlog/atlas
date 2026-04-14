/**
 * ProspectTab.tsx
 * ===============
 * Aba "Prospectar" do ControlPanel.
 *
 * Sem props — lê tudo do store Zustand.
 *
 * Features:
 * - Seletor de Delivery Station (todas as únicas de allMarkersData)
 * - Seletor de Carteira cascateado pela DS selecionada
 * - Ao trocar DS: limpa seleção de Carteira
 * - Botão "Buscar Empresas": habilitado apenas com DS + Carteira selecionados
 * - Chamada POST /api/empresas → setCompanies + kmeansCluster + setClusters
 * - Tratamento de erros HTTP e de rede
 * - Renderiza ResultPanel quando há resultados ou erro
 * - pinnedKeys gerenciado no store (togglePin action)
 */

import { useState, useMemo, useCallback } from 'react';
import { useStore } from '../../store';
import { getUniqueValues } from '../../store/actions/dataActions';
import { kmeansCluster } from '../../lib/kmeansUtils';
import { API_BASE_URL } from '../../lib/config';
import ResultPanel from './ResultPanel';

export default function ProspectTab(): JSX.Element {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const prospectState = useStore((s) => s.prospectState);
  const setCompanies = useStore((s) => s.setCompanies);
  const setClusters = useStore((s) => s.setClusters);
  const setProspectLoading = useStore((s) => s.setProspectLoading);
  const setProspectError = useStore((s) => s.setProspectError);
  const setProspectStation = useStore((s) => s.setProspectStation);
  const setProspectBucket = useStore((s) => s.setProspectBucket);
  const togglePin = useStore((s) => s.togglePin);
  const clearProspect = useStore((s) => s.clearProspect);

  // Local selectors (not persisted to store until search)
  const [selectedStation, setSelectedStation] = useState<string>('');
  const [selectedBucket, setSelectedBucket] = useState<string>('');

  // DS options — all unique delivery_station values
  const stationOptions = useMemo(
    () => getUniqueValues(allMarkersData, 'delivery_station').sort(),
    [allMarkersData]
  );

  // Carteira options — cascaded by selected DS
  const bucketOptions = useMemo(() => {
    const base = selectedStation
      ? allMarkersData.filter((p) => p.delivery_station === selectedStation)
      : allMarkersData;
    return getUniqueValues(base, 'bucket_ade').sort();
  }, [allMarkersData, selectedStation]);

  const handleStationChange = useCallback((value: string) => {
    setSelectedStation(value);
    setSelectedBucket(''); // clear carteira when DS changes
  }, []);

  const canSearch = selectedStation !== '' && selectedBucket !== '';

  const handleSearch = useCallback(async () => {
    if (!canSearch) return;

    setProspectLoading(true);
    setProspectError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/empresas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          delivery_station: selectedStation,
          bucket_ade: selectedBucket,
        }),
      });

      if (!res.ok) {
        throw new Error(`Erro ao buscar empresas: ${res.status} ${res.statusText}`);
      }

      const data = await res.json();
      const companies = Array.isArray(data) ? data : [];

      setCompanies(companies);
      setProspectStation(selectedStation);
      setProspectBucket(selectedBucket);

      try {
        const clusters = kmeansCluster(companies, 4);
        setClusters(clusters);
      } catch (clusterErr) {
        console.warn('[ProspectTab] kmeansCluster falhou:', clusterErr);
        setClusters([]);
      }
    } catch (err) {
      const isNetworkError =
        err instanceof TypeError && err.message.toLowerCase().includes('fetch');
      const message = isNetworkError
        ? 'Erro de conexão. Verifique sua internet e tente novamente.'
        : err instanceof Error
          ? err.message
          : 'Erro desconhecido ao buscar empresas.';
      setProspectError(message);
    } finally {
      setProspectLoading(false);
    }
  }, [
    canSearch,
    selectedStation,
    selectedBucket,
    setCompanies,
    setClusters,
    setProspectLoading,
    setProspectError,
    setProspectStation,
    setProspectBucket,
  ]);

  const handleClose = useCallback(() => {
    clearProspect();
  }, [clearProspect]);

  const showResultPanel =
    prospectState.companies.length > 0 ||
    prospectState.error !== null;

  const pinnedKeys = useMemo(
    () => new Set(prospectState.pinnedKeys),
    [prospectState.pinnedKeys]
  );

  return (
    <div className="p-3 flex flex-col gap-3">
      {/* Delivery Station selector */}
      <div>
        <label
          htmlFor="prospect-station"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Delivery Station
        </label>
        <select
          id="prospect-station"
          value={selectedStation}
          onChange={(e) => handleStationChange(e.target.value)}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
        >
          <option value="">Selecione uma DS...</option>
          {stationOptions.map((ds) => (
            <option key={ds} value={ds}>
              {ds}
            </option>
          ))}
        </select>
      </div>

      {/* Carteira selector — cascaded */}
      <div>
        <label
          htmlFor="prospect-bucket"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Carteira
        </label>
        <select
          id="prospect-bucket"
          value={selectedBucket}
          onChange={(e) => setSelectedBucket(e.target.value)}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
        >
          <option value="">Selecione uma carteira...</option>
          {bucketOptions.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
      </div>

      {/* Search button */}
      <button
        type="button"
        onClick={handleSearch}
        disabled={!canSearch || prospectState.isLoading}
        className="w-full py-3 px-4 rounded bg-atlas-accent text-atlas-darker text-sm font-semibold hover:opacity-90 focus:outline-none min-h-[44px] transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {prospectState.isLoading ? 'Buscando...' : 'Buscar Empresas'}
      </button>

      {/* Error message (when no ResultPanel is shown) */}
      {prospectState.error && !showResultPanel && (
        <p className="text-xs text-red-400 mt-1">{prospectState.error}</p>
      )}

      {/* ResultPanel — inline on mobile, portal on desktop/tablet */}
      {showResultPanel && prospectState.selectedStation && prospectState.selectedBucket && (
        <ResultPanel
          companies={prospectState.companies}
          selectedStation={prospectState.selectedStation}
          selectedBucket={prospectState.selectedBucket}
          onClose={handleClose}
          pinnedKeys={pinnedKeys}
          onTogglePin={togglePin}
        />
      )}
    </div>
  );
}
