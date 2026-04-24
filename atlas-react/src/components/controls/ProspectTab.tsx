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
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import { getUniqueValues } from '../../store/actions/dataActions';
import { kmeansCluster } from '../../lib/kmeansUtils';
import { API_BASE_URL } from '../../lib/config';
import ResultPanel from './ResultPanel';
import type { ProspectCompany } from '../../store/types';
import type { Polygon, MultiPolygon } from 'geojson';

// ---------------------------------------------------------------------------
// Normaliza a resposta bruta da API para ProspectCompany
// ---------------------------------------------------------------------------

function normalizeCompany(raw: Record<string, unknown>): ProspectCompany {
  const fonte = (raw.fonte as string) ?? '';
  const isReceita = fonte === 'Receita Federal';

  const endereco = isReceita
    ? [raw.logradouro, raw.numero, raw.bairro, raw.municipio, raw.uf, raw.cep]
        .filter(Boolean)
        .join(', ')
    : (raw.endereco as string) ?? '';

  const nome = isReceita
    ? ((raw.razao_social as string) || (raw.nome_fantasia as string) || 'N/A')
    : (raw.nome as string) ?? 'N/A';

  return {
    nome,
    endereco,
    telefone_1: (raw.telefone_1 as string | null) ?? (raw.ddd_telefone_1 as string | null) ?? null,
    telefone_2: (raw.telefone_2 as string | null) ?? (raw.ddd_telefone_2 as string | null) ?? null,
    telefone: (raw.telefone as string | null) ?? null,
    site: (raw.site as string) ?? '',
    google_maps_link: (raw.google_maps_link as string) ?? 'N/A',
    cep: (raw.cep as string) ?? '',
    tipo: (raw.tipo as string) ?? (raw.cnae_fiscal_descricao as string) ?? '',
    _fonte: fonte,
    lat: (raw.lat as number | null) ?? null,
    lon: (raw.lon as number | null) ?? null,
    // API já filtra pelo match — todos os retornados são candidatos válidos
    isMatch: null,
    gridDisk: null,
    matched_slot: null,
    contactada: (raw.contactada as boolean) ?? false,
    territory_id: (raw.territory_id as string | undefined),
  };
}

// ---------------------------------------------------------------------------
// Extrai todos os slots vagos de um bucket para passar à API
// ---------------------------------------------------------------------------

interface SlotRef {
  slot_id:  string;
  h3_r9_id: string | null;
  h3_r8_id: string | null;
  lat:      number;
  lon:      number;
}

function getAllOpenSlots(
  idealSupplyData: GeoJSON.Feature[] | null,
  bucketAde: string
): SlotRef[] {
  if (!idealSupplyData) return [];
  return idealSupplyData
    .filter((f) => {
      const p = f.properties ?? {};
      return (
        p.type === 'IDEAL_SLOT' &&
        (p.territory_id === bucketAde || p.bucket_ade === bucketAde) &&
        !p.matched_partner_id
      );
    })
    .map((f) => {
      const p = f.properties ?? {};
      const coords = (f.geometry as GeoJSON.Point).coordinates;
      return {
        slot_id:  (p.slot_id as string) ?? '',
        h3_r9_id: (p.h3_r9_id as string | null) ?? null,
        h3_r8_id: (p.h3_r8_id as string | null) ?? null,
        lat:      coords[1],
        lon:      coords[0],
      };
    });
}

export default function ProspectTab(): JSX.Element {
  const { t } = useTranslation();
  const allMarkersData = useStore((s) => s.allMarkersData);
  const polygonsData = useStore((s) => s.polygonsData);
  const idealSupplyData = useStore((s) => s.idealSupplyData);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);
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

  // DS options — all unique non-empty delivery_station values
  const stationOptions = useMemo(
    () => getUniqueValues(allMarkersData, 'delivery_station').filter(Boolean).sort(),
    [allMarkersData]
  );

  // Carteira options — cascaded by selected DS
  const bucketOptions = useMemo(() => {
    if (!selectedStation) return [];
    return getUniqueValues(
      allMarkersData.filter((p) => p.delivery_station === selectedStation),
      'bucket_ade'
    ).filter(Boolean).sort();
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
      const openSlots = getAllOpenSlots(idealSupplyData, selectedBucket);

      const res = await fetch(`${API_BASE_URL}/api/empresas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          territory_id: selectedBucket,
          slots:        openSlots,
        }),
      });

      if (!res.ok) {
        throw new Error(`Erro ao buscar empresas: ${res.status} ${res.statusText}`);
      }

      const data = await res.json();
      const companies = (Array.isArray(data) ? data : (data.empresas ?? []))
        .map((raw: Record<string, unknown>) => normalizeCompany(raw));

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

      // Centralizar mapa no polígono do bucket selecionado
      if (fitBoundsRef.current && polygonsData) {
        const bucketFeature = polygonsData.features.find((f) => {
          const p = f.properties ?? {};
          return p.bucket_ade === selectedBucket || p.territory_id === selectedBucket;
        });
        if (bucketFeature?.geometry) {
          // Extrair todas as coordenadas do polígono
          const geom = bucketFeature.geometry as Polygon | MultiPolygon;
          const coords: [number, number][] = [];
          const extractCoords = (rings: number[][][]) => {
            rings.forEach((ring) => ring.forEach(([lon, lat]) => coords.push([lat, lon])));
          };
          if (geom.type === 'Polygon') extractCoords(geom.coordinates);
          else if (geom.type === 'MultiPolygon') geom.coordinates.forEach(extractCoords);
          if (coords.length > 0) fitBoundsRef.current(coords);
        }
      }
    } catch (err) {
      const isNetworkError =
        err instanceof TypeError && err.message.toLowerCase().includes('fetch');
      const message = isNetworkError
        ? t('prospect.error_connection')
        : err instanceof Error
          ? err.message
          : t('prospect.error_unknown');
      setProspectError(message);
      // Também dispara o toast global de erro
      useStore.getState().setError(message);
    } finally {
      setProspectLoading(false);
    }
  }, [
    canSearch,
    selectedStation,
    selectedBucket,
    allMarkersData,
    polygonsData,
    idealSupplyData,
    fitBoundsRef,
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
          {t('prospect.station_label')}
        </label>
        <select
          id="prospect-station"
          value={selectedStation}
          onChange={(e) => handleStationChange(e.target.value)}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
        >
          <option value="">{t('prospect.station_placeholder')}</option>
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
          {t('prospect.bucket_label')}
        </label>
        <select
          id="prospect-bucket"
          value={selectedBucket}
          onChange={(e) => setSelectedBucket(e.target.value)}
          disabled={!selectedStation}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <option value="">{selectedStation ? t('prospect.bucket_placeholder') : t('prospect.bucket_disabled')}</option>
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
        className="w-full py-3 px-4 rounded bg-atlas-accent text-white text-sm font-semibold hover:opacity-90 focus:outline-none min-h-[44px] transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {prospectState.isLoading ? t('prospect.search_loading') : t('prospect.search_button')}
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
