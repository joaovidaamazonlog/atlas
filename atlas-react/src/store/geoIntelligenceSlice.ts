/**
 * geoIntelligenceSlice.ts
 * =======================
 * Tipos e interfaces do slice de Geointeligência para o store Zustand.
 */

// ---------------------------------------------------------------------------
// ENUMERAÇÃO DE TIPOS DE REGIÃO
// ---------------------------------------------------------------------------

export type RegionType =
  | 'favela_comunidade'
  | 'residencial_baixa_renda'
  | 'residencial_media_renda'
  | 'residencial_alta_renda'
  | 'comercial'
  | 'industrial'
  | 'rural'
  | 'alto_padrao';

// ---------------------------------------------------------------------------
// MODELOS DE DADOS
// ---------------------------------------------------------------------------

export interface TerritoryOutput {
  territory_id: string;
  h3_ids: string[];
  region_type: RegionType;
  potential_score: number;
  current_partners: number;
  ideal_slots: number;
  gap: number;
  model_confidence: number;
  low_confidence: boolean;
  high_opportunity: boolean;
}

export interface GeoIntelligenceFilter {
  regionTypes: RegionType[] | 'all';
  minGap: number;
}

export interface GeoIntelligenceState {
  territories: TerritoryOutput[];
  geojson: GeoJSON.FeatureCollection | null;
  scorecard: Record<string, unknown> | null;
  expansionTargetResult: Record<string, unknown> | null;
  selectedTerritoryId: string | null;
  filter: GeoIntelligenceFilter;
  isLoading: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// INTERFACE DO SLICE
// ---------------------------------------------------------------------------

export interface GeoIntelligenceSlice {
  geoIntelligence: GeoIntelligenceState;
  loadGeoIntelligence: (stationCode: string) => Promise<void>;
  setGeoFilter: (filter: Partial<GeoIntelligenceFilter>) => void;
  setExpansionTarget: (pct: number) => void;
  selectGeoTerritory: (territoryId: string | null) => void;
}

// ---------------------------------------------------------------------------
// ESTADO INICIAL
// ---------------------------------------------------------------------------

export const DEFAULT_GEO_INTELLIGENCE_STATE: GeoIntelligenceState = {
  territories: [],
  geojson: null,
  scorecard: null,
  expansionTargetResult: null,
  selectedTerritoryId: null,
  filter: {
    regionTypes: 'all',
    minGap: 0,
  },
  isLoading: false,
  error: null,
};
