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
import * as turf from '@turf/turf';
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

  // Endereço: Receita Federal vem fragmentado
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
    isMatch: (raw.isMatch as boolean | null) ?? null,
    contactada: (raw.contactada as boolean) ?? false,
    territory_id: (raw.territory_id as string | undefined),
  };
}

// ---------------------------------------------------------------------------
// Validação isMatch — replica a lógica do vanilla gmaps-scraper.js
// ---------------------------------------------------------------------------

interface SlotGeo {
  lat: number;
  lon: number;
  radius_s: number;
  ceps: string[];
}

/**
 * Extrai os slots IDEAL_SLOT do idealSupplyData para um dado bucket_ade.
 */
function getSlotsForBucket(
  idealSupplyData: GeoJSON.Feature[] | null,
  bucketAde: string
): SlotGeo[] {
  if (!idealSupplyData) return [];
  return idealSupplyData
    .filter((f) => {
      const p = f.properties ?? {};
      return (
        p.type === 'IDEAL_SLOT' &&
        (p.territory_id === bucketAde || p.bucket_ade === bucketAde)
      );
    })
    .map((f) => {
      const p = f.properties ?? {};
      // Centróide do slot: geometry é um Point ou Polygon
      let lat = p.lat as number | undefined;
      let lon = p.lon as number | undefined;
      if ((lat == null || lon == null) && f.geometry?.type === 'Point') {
        const coords = (f.geometry as GeoJSON.Point).coordinates;
        lon = coords[0];
        lat = coords[1];
      }
      return {
        lat: lat ?? 0,
        lon: lon ?? 0,
        radius_s: (p.radius_s as number) ?? 500,
        ceps: (p.ceps as string[]) ?? [],
      };
    })
    .filter((s) => s.lat !== 0 || s.lon !== 0);
}

const MAX_DISTANCE_M = 1000;

/**
 * Valida e filtra empresas conforme a lógica do vanilla:
 * - Google Maps (tem lat/lon): dentro do raio de algum slot E <= 1000m
 * - Receita Federal (sem lat/lon): CEP pertence ao cepSet de algum slot
 * Retorna apenas as empresas que passam na validação, com isMatch setado.
 */
function validateAndFilter(
  companies: ProspectCompany[],
  slots: SlotGeo[],
  cepSet: Set<string>
): ProspectCompany[] {
  if (slots.length === 0 && cepSet.size === 0) return companies;

  return companies
    .map((company) => {
      const isGoogleMaps = company._fonte === 'Google Maps';

      if (isGoogleMaps && company.lat != null && company.lon != null) {
        // Calcular distância ao slot mais próximo
        let minDist = Infinity;
        let matchRadius = false;
        for (const slot of slots) {
          const distM = Math.round(
            turf.distance(
              turf.point([slot.lon, slot.lat]),
              turf.point([company.lon, company.lat]),
              { units: 'meters' }
            )
          );
          if (distM < minDist) minDist = distM;
          if (distM <= slot.radius_s) { matchRadius = true; break; }
        }
        // Filtrar: deve estar dentro do raio de algum slot E <= MAX_DISTANCE_M
        if (minDist > MAX_DISTANCE_M) return null;
        return { ...company, isMatch: matchRadius };
      } else {
        // Receita Federal — validar por CEP
        const cleanCep = (company.cep ?? '').replace(/\D/g, '');
        const isMatch = cepSet.size > 0 ? cepSet.has(cleanCep) : null;
        if (isMatch === false) return null; // fora dos CEPs da carteira
        return { ...company, isMatch };
      }
    })
    .filter((c): c is ProspectCompany => c !== null);
}

export default function ProspectTab(): JSX.Element {
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
      // Coleta os CEPs únicos dos parceiros da carteira selecionada
      const partnerCeps = allMarkersData
        .filter((p) => p.delivery_station === selectedStation && p.bucket_ade === selectedBucket)
        .flatMap((p) => p.ceps ?? [])
        .filter(Boolean);
      const uniqueCeps = [...new Set(partnerCeps)];

      const res = await fetch(`${API_BASE_URL}/api/empresas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ceps: uniqueCeps,
          territory_id: selectedBucket,
        }),
      });

      if (!res.ok) {
        throw new Error(`Erro ao buscar empresas: ${res.status} ${res.statusText}`);
      }

      const data = await res.json();
      // API retorna { total, empresas: [...] } ou array direto
      const rawCompanies = (Array.isArray(data) ? data : (data.empresas ?? []))
        .map((raw: Record<string, unknown>) => normalizeCompany(raw));

      // Validar: manter apenas empresas dentro do raio de algum slot (Google Maps)
      // ou com CEP pertencente à carteira (Receita Federal)
      const slots = getSlotsForBucket(idealSupplyData, selectedBucket);
      const companies = validateAndFilter(rawCompanies, slots, new Set(uniqueCeps));

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
        ? 'Erro de conexão. Verifique sua internet e tente novamente.'
        : err instanceof Error
          ? err.message
          : 'Erro desconhecido ao buscar empresas.';
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
          disabled={!selectedStation}
          className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <option value="">{selectedStation ? 'Selecione uma carteira...' : 'Selecione uma DS primeiro'}</option>
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
