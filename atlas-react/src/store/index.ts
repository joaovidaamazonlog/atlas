/**
 * store/index.ts
 * ==============
 * Store Zustand principal da aplicação ATLAS.
 * Substitui o state.js (Proxy reativo) com tipagem estrita e actions.
 */

import { create } from 'zustand';
import { createRef } from 'react';
import type React from 'react';
import type {
  Partner,
  DeliveryStation,
  FilterState,
  StyleConfig,
  RouteStop,
  HcpState,
  ProspectState,
  ProspectCompany,
  ProspectCluster,
  RecruitableAnalysisState,
  RecruitableAnalysisParams,
  EvaluatorResult,
  CapOpportunityState,
  HexSelectionState,
} from './types';
import { Partner as PartnerModel } from '../lib/models';
import { applyFiltersLogic } from './actions/dataActions';
import { defaultStyleConfig } from './actions/mapActions';
import { DATA_URLS, GEO_INTELLIGENCE_API_BASE_URL } from '../lib/config';
import type {
  GeoIntelligenceSlice,
  GeoIntelligenceState,
  GeoIntelligenceFilter,
} from './geoIntelligenceSlice';
import { DEFAULT_GEO_INTELLIGENCE_STATE } from './geoIntelligenceSlice';

// ---------------------------------------------------------------------------
// ESTADO INICIAL
// ---------------------------------------------------------------------------

const DEFAULT_FILTER_STATE: FilterState = {
  selectedStatuses: 'all',
  selectedStations: 'all',
  selectedBuckets: 'all',
  initiativesFilter: 'all',
  jurisdictionFilter: 'all',
};

const DEFAULT_HCP_STATE: HcpState = {
  suggestionCache: {},
  usedStores: {},
  suggestionsActive: false,
};

const DEFAULT_RECRUITABLE_ANALYSIS_STATE: RecruitableAnalysisState = {
  params: {
    minAdv: 40,
    radiusMeters: 1000,
    centerLat: '',
    centerLon: '',
    selectedLeadId: null,
  },
  result: null,
  error: null,
  isStale: false,
};

// ---------------------------------------------------------------------------
// INTERFACE DO STORE
// ---------------------------------------------------------------------------

export interface AtlasStore {
  // --- Dados ---
  allMarkersData: Partner[];
  currentFilteredData: Partner[];
  deliveryStations: DeliveryStation[];
  polygonsData: GeoJSON.FeatureCollection | null;
  jurisdictionData: GeoJSON.FeatureCollection | null;
  optimizationData: GeoJSON.FeatureCollection | null;
  idealSupplyData: GeoJSON.Feature[] | null;
  heatmapData: GeoJSON.FeatureCollection | null;
  period: string | object;

  // --- UI ---
  isLoading: boolean;
  loadingMessage: string;
  error: string | null;
  styleConfig: StyleConfig;
  filterState: FilterState;
  route: RouteStop[];
  hcp: HcpState;
  /** true quando há uma origem de rota definida no RoutesTab */
  routeOriginActive: boolean;
  /** Ref preenchido pelo MapView para executar fitBounds a partir de qualquer componente */
  fitBoundsRef: React.MutableRefObject<((coords: [number, number][]) => void) | null>;

  // --- Prospect ---
  prospectState: ProspectState;

  // --- Actions ---
  loadAll: () => Promise<void>;
  applyFilters: (filters?: Partial<FilterState>) => void;
  resetFilters: () => void;
  setStyleConfig: (config: Partial<StyleConfig>) => void;
  setRoute: (stops: RouteStop[]) => void;
  clearRoute: () => void;
  setError: (msg: string | null) => void;
  setLoading: (loading: boolean, message?: string) => void;
  setAllData: (payload: {
    allMarkersData?: Partner[];
    deliveryStations?: DeliveryStation[];
    polygonsData?: GeoJSON.FeatureCollection | null;
    jurisdictionData?: GeoJSON.FeatureCollection | null;
    optimizationData?: GeoJSON.FeatureCollection | null;
    idealSupplyData?: GeoJSON.Feature[] | null;
    heatmapData?: GeoJSON.FeatureCollection | null;
    period?: string | object;
  }) => void;

  // --- Prospect Actions ---
  setCompanies: (companies: ProspectCompany[]) => void;
  setClusters: (clusters: ProspectCluster[]) => void;
  setProspectLoading: (isLoading: boolean) => void;
  setProspectError: (error: string | null) => void;
  setProspectStation: (station: string | null) => void;
  setProspectBucket: (bucket: string | null) => void;
  togglePin: (key: string) => void;
  clearProspect: () => void;

  // --- Geo Intelligence (GeoIntelligenceSlice) ---
  geoIntelligence: GeoIntelligenceState;
  loadGeoIntelligence: (stationCode: string) => Promise<void>;
  setGeoFilter: (filter: Partial<GeoIntelligenceFilter>) => void;
  setExpansionTarget: (pct: number) => void;
  selectGeoTerritory: (territoryId: string | null) => void;

  // --- Active Tab ---
  activeTab: string;
  setActiveTab: (tab: string) => void;

  // --- Manual Analysis Panel ---
  manualAnalysisOpen: boolean;
  setManualAnalysisOpen: (open: boolean) => void;
  /** Pin temporário no mapa para análise manual (endereço geocodificado) */
  manualAnalysisPin: { lat: number; lon: number; label: string } | null;
  setManualAnalysisPin: (pin: { lat: number; lon: number; label: string } | null) => void;

  // --- Recruitable Area Analysis ---
  recruitableAnalysis: RecruitableAnalysisState;
  setRecruitableParams: (params: Partial<RecruitableAnalysisParams>) => void;
  setRecruitableResult: (result: EvaluatorResult | null, error?: string | null) => void;
  clearRecruitableAnalysis: () => void;

  // --- Cap Opportunity ---
  capOpportunityState: CapOpportunityState;
  setSelectedCapOpportunity: (partnerId: string | null) => void;

  // --- Hex Selection ---
  hexSelectionState: HexSelectionState;
  toggleHexSelection: (hexId: string, demandDaily: number, demandResidual: number) => void;
  clearHexSelection: () => void;

  // --- What-If Mode ---
  whatIfModeActive: boolean;
  setWhatIfModeActive: (active: boolean) => void;
}

// ---------------------------------------------------------------------------
// CRIAÇÃO DO STORE
// ---------------------------------------------------------------------------

export const useStore = create<AtlasStore>((set, get) => ({
  // --- Estado inicial: dados ---
  allMarkersData: [],
  currentFilteredData: [],
  deliveryStations: [],
  polygonsData: null,
  jurisdictionData: null,
  optimizationData: null,
  idealSupplyData: null,
  heatmapData: null,
  period: '',

  // --- Estado inicial: UI ---
  isLoading: false,
  loadingMessage: '',
  error: null,
  styleConfig: defaultStyleConfig(),
  filterState: { ...DEFAULT_FILTER_STATE },
  route: [],
  hcp: { ...DEFAULT_HCP_STATE },
  routeOriginActive: false,
  fitBoundsRef: createRef<((coords: [number, number][]) => void) | null>() as React.MutableRefObject<((coords: [number, number][]) => void) | null>,

  // --- Estado inicial: prospect ---
  prospectState: {
    companies: [],
    clusters: [],
    isLoading: false,
    error: null,
    selectedStation: null,
    selectedBucket: null,
    pinnedKeys: [],
  },

  // --- Estado inicial: geo intelligence ---
  geoIntelligence: { ...DEFAULT_GEO_INTELLIGENCE_STATE },

  // --- Estado inicial: active tab ---
  activeTab: 'filters',

  // --- Estado inicial: manual analysis panel ---
  manualAnalysisOpen: false,
  manualAnalysisPin: null,

  // --- Estado inicial: recruitable area analysis ---
  recruitableAnalysis: { ...DEFAULT_RECRUITABLE_ANALYSIS_STATE, params: { ...DEFAULT_RECRUITABLE_ANALYSIS_STATE.params } },

  // --- Estado inicial: cap opportunity ---
  capOpportunityState: { selectedPartnerId: null },

  // --- Estado inicial: hex selection ---
  hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 },

  // --- Estado inicial: what-if mode ---
  whatIfModeActive: false,

  // ---------------------------------------------------------------------------
  // ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Carrega todos os dados da aplicação a partir das URLs configuradas.
   * Preserva o estado anterior em caso de falha.
   */
  loadAll: async () => {
    const prevState = {
      allMarkersData: get().allMarkersData,
      currentFilteredData: get().currentFilteredData,
      deliveryStations: get().deliveryStations,
      polygonsData: get().polygonsData,
      jurisdictionData: get().jurisdictionData,
      optimizationData: get().optimizationData,
      idealSupplyData: get().idealSupplyData,
      heatmapData: get().heatmapData,
      period: get().period,
    };

    set({ isLoading: true, loadingMessage: 'Carregando dados...', error: null });

    try {
      console.log('[AtlasStore] Iniciando loadAll, URL:', DATA_URLS.partners);
      // Carrega dados principais dos parceiros
      const partnersRes = await fetch(DATA_URLS.partners);
      console.log('[AtlasStore] Resposta parceiros:', partnersRes.status, partnersRes.ok);
      if (!partnersRes.ok) throw new Error(`Falha ao carregar parceiros: ${partnersRes.status} ${partnersRes.statusText}`);
      const partnersJson = await partnersRes.json();

      const allMarkersData: Partner[] = (Array.isArray(partnersJson.allMarkerData)
        ? partnersJson.allMarkerData
        : Array.isArray(partnersJson.partners)
          ? partnersJson.partners
          : Array.isArray(partnersJson)
            ? partnersJson
            : []).map((raw: unknown) => new PartnerModel(raw as Record<string, unknown>));
      const deliveryStations: DeliveryStation[] = partnersJson.deliveryStations ?? partnersJson.delivery_stations ?? [];
      const period: string | object = partnersJson.period ?? '';
      console.log('[AtlasStore] Parceiros carregados:', allMarkersData.length);

      // Carrega camadas GeoJSON em paralelo (falhas individuais não bloqueiam)
      const [territoriesResult, jurisdictionResult, optimizationResult, heatmapResult] =
        await Promise.allSettled([
          fetch(DATA_URLS.territories).then((r) => (r.ok ? r.json() : null)),
          fetch(DATA_URLS.jurisdiction).then((r) => (r.ok ? r.json() : null)),
          fetch(DATA_URLS.optimization).then((r) => (r.ok ? r.json() : null)),
          fetch(DATA_URLS.heatmap).then((r) => (r.ok ? r.json() : null)),
        ]);

      const polygonsData =
        territoriesResult.status === 'fulfilled' ? territoriesResult.value : null;
      const jurisdictionData =
        jurisdictionResult.status === 'fulfilled' ? jurisdictionResult.value : null;
      const optimizationData =
        optimizationResult.status === 'fulfilled' ? optimizationResult.value : null;
      const heatmapData =
        heatmapResult.status === 'fulfilled' ? heatmapResult.value : null;

      // Extrai idealSupplyData do GeoJSON de otimização (features IDEAL_SLOT)
      const idealSupplyData =
        optimizationData?.features?.filter(
          (f: GeoJSON.Feature) => f.properties?.type === 'IDEAL_SLOT'
        ) ?? null;

      set({
        allMarkersData,
        currentFilteredData: allMarkersData,
        deliveryStations,
        polygonsData,
        jurisdictionData,
        optimizationData,
        idealSupplyData,
        heatmapData,
        period,
        isLoading: false,
        loadingMessage: '',
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro desconhecido ao carregar dados';
      console.error('[AtlasStore] loadAll falhou:', message, err);
      set({
        ...prevState,
        isLoading: false,
        loadingMessage: '',
        error: message,
      });
    }
  },

  /**
   * Aplica filtros sobre allMarkersData e atualiza currentFilteredData.
   * Mescla filtros parciais com o estado atual de filterState.
   */
  applyFilters: (filters?: Partial<FilterState>) => {
    const prevFilterState = get().filterState;
    const prevCurrentFilteredData = get().currentFilteredData;

    try {
      const newFilterState: FilterState = filters
        ? { ...prevFilterState, ...filters }
        : prevFilterState;

      const filtered = applyFiltersLogic(get().allMarkersData, newFilterState);

      set({ filterState: newFilterState, currentFilteredData: filtered });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao aplicar filtros';
      console.error('[AtlasStore] applyFilters falhou:', message);
      set({
        filterState: prevFilterState,
        currentFilteredData: prevCurrentFilteredData,
        error: message,
      });
    }
  },

  /**
   * Reseta todos os filtros para o estado padrão e restaura currentFilteredData
   * para allMarkersData completo.
   */
  resetFilters: () => {
    try {
      set({
        filterState: { ...DEFAULT_FILTER_STATE },
        currentFilteredData: get().allMarkersData,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao resetar filtros';
      console.error('[AtlasStore] resetFilters falhou:', message);
      set({ error: message });
    }
  },

  /**
   * Atualiza parcialmente o StyleConfig.
   */
  setStyleConfig: (config: Partial<StyleConfig>) => {
    const prevStyleConfig = get().styleConfig;
    try {
      set({ styleConfig: { ...prevStyleConfig, ...config } });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao atualizar estilo';
      console.error('[AtlasStore] setStyleConfig falhou:', message);
      set({ styleConfig: prevStyleConfig, error: message });
    }
  },

  /**
   * Define as paradas da rota atual.
   */
  setRoute: (stops: RouteStop[]) => {
    const prevRoute = get().route;
    try {
      set({ route: stops });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao definir rota';
      console.error('[AtlasStore] setRoute falhou:', message);
      set({ route: prevRoute, error: message });
    }
  },

  /**
   * Limpa a rota atual.
   */
  clearRoute: () => {
    try {
      set({ route: [] });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao limpar rota';
      console.error('[AtlasStore] clearRoute falhou:', message);
      set({ error: message });
    }
  },

  /**
   * Define a mensagem de erro (null para limpar).
   */
  setError: (msg: string | null) => {
    set({ error: msg });
  },

  /**
   * Define o estado de carregamento com mensagem opcional.
   */
  setLoading: (loading: boolean, message = '') => {
    set({ isLoading: loading, loadingMessage: message });
  },

  /**
   * Atualiza múltiplos slices de dados de uma vez (usado pelo DataWorker).
   */
  setAllData: (payload) => {
    const prevState = {
      allMarkersData: get().allMarkersData,
      currentFilteredData: get().currentFilteredData,
      deliveryStations: get().deliveryStations,
      polygonsData: get().polygonsData,
      jurisdictionData: get().jurisdictionData,
      optimizationData: get().optimizationData,
      idealSupplyData: get().idealSupplyData,
      heatmapData: get().heatmapData,
      period: get().period,
    };

    try {
      const updates: Partial<AtlasStore> = {};

      if (payload.allMarkersData !== undefined) {
        updates.allMarkersData = payload.allMarkersData;
        // Ao receber novos dados, currentFilteredData é resetado para o total
        updates.currentFilteredData = payload.allMarkersData;
      }
      if (payload.deliveryStations !== undefined) updates.deliveryStations = payload.deliveryStations;
      if (payload.polygonsData !== undefined) updates.polygonsData = payload.polygonsData;
      if (payload.jurisdictionData !== undefined) updates.jurisdictionData = payload.jurisdictionData;
      if (payload.optimizationData !== undefined) updates.optimizationData = payload.optimizationData;
      if (payload.idealSupplyData !== undefined) updates.idealSupplyData = payload.idealSupplyData;
      if (payload.heatmapData !== undefined) updates.heatmapData = payload.heatmapData;
      if (payload.period !== undefined) updates.period = payload.period;

      set(updates);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao atualizar dados';
      console.error('[AtlasStore] setAllData falhou:', message);
      set({ ...prevState, error: message });
    }
  },

  // ---------------------------------------------------------------------------
  // PROSPECT ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Atualiza a lista de empresas prospectadas.
   * Também reseta pinnedKeys (nova busca limpa alfinetes).
   */
  setCompanies: (companies: ProspectCompany[]) => {
    set((state) => ({ prospectState: { ...state.prospectState, companies, pinnedKeys: [] } }));
  },

  /**
   * Atualiza os clusters K-means calculados.
   */
  setClusters: (clusters: ProspectCluster[]) => {
    set((state) => ({ prospectState: { ...state.prospectState, clusters } }));
  },

  /**
   * Atualiza o estado de carregamento da prospecção.
   */
  setProspectLoading: (isLoading: boolean) => {
    set((state) => ({ prospectState: { ...state.prospectState, isLoading } }));
  },

  /**
   * Define a mensagem de erro da prospecção (null para limpar).
   */
  setProspectError: (error: string | null) => {
    set((state) => ({ prospectState: { ...state.prospectState, error } }));
  },

  /**
   * Define a Delivery Station selecionada na prospecção.
   */
  setProspectStation: (selectedStation: string | null) => {
    set((state) => ({ prospectState: { ...state.prospectState, selectedStation } }));
  },

  /**
   * Define a Carteira selecionada na prospecção.
   */
  setProspectBucket: (selectedBucket: string | null) => {
    set((state) => ({ prospectState: { ...state.prospectState, selectedBucket } }));
  },

  /**
   * Alterna o estado de alfinete de uma empresa (adiciona se ausente, remove se presente).
   */
  togglePin: (key: string) => {
    set((state) => {
      const prev = state.prospectState.pinnedKeys;
      const pinnedKeys = prev.includes(key)
        ? prev.filter((k) => k !== key)
        : [...prev, key];
      return { prospectState: { ...state.prospectState, pinnedKeys } };
    });
  },

  /**
   * Reseta o estado de prospecção para o estado inicial.
   */
  clearProspect: () => {
    set((state) => ({
      prospectState: {
        ...state.prospectState,
        companies: [],
        clusters: [],
        selectedStation: null,
        selectedBucket: null,
        isLoading: false,
        error: null,
        pinnedKeys: [],
      },
    }));
  },

  // ---------------------------------------------------------------------------
  // GEO INTELLIGENCE ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Carrega dados de geointeligência para uma Delivery Station.
   * Busca territories, geojson e scorecard em paralelo.
   */
  loadGeoIntelligence: async (stationCode: string) => {
    set((state) => ({
      geoIntelligence: { ...state.geoIntelligence, isLoading: true, error: null },
    }));

    try {
      const base = GEO_INTELLIGENCE_API_BASE_URL;
      const [territoriesRes, geojsonRes, scorecardRes] = await Promise.allSettled([
        fetch(`${base}/geo-intelligence/${stationCode}/territories`).then((r) =>
          r.ok ? r.json() : Promise.reject(new Error(`territories: ${r.status}`))
        ),
        fetch(`${base}/geo-intelligence/${stationCode}/geojson`).then((r) =>
          r.ok ? r.json() : Promise.reject(new Error(`geojson: ${r.status}`))
        ),
        fetch(`${base}/geo-intelligence/${stationCode}/scorecard`).then((r) =>
          r.ok ? r.json() : Promise.reject(new Error(`scorecard: ${r.status}`))
        ),
      ]);

      const territories =
        territoriesRes.status === 'fulfilled' ? territoriesRes.value : [];
      const geojson =
        geojsonRes.status === 'fulfilled' ? geojsonRes.value : null;
      const scorecard =
        scorecardRes.status === 'fulfilled' ? scorecardRes.value : null;

      set((state) => ({
        geoIntelligence: {
          ...state.geoIntelligence,
          territories,
          geojson,
          scorecard,
          isLoading: false,
        },
      }));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Erro ao carregar geointeligência';
      console.error('[AtlasStore] loadGeoIntelligence falhou:', message);
      set((state) => ({
        geoIntelligence: {
          ...state.geoIntelligence,
          isLoading: false,
          error: message,
        },
      }));
    }
  },

  /**
   * Atualiza parcialmente o filtro de geointeligência.
   */
  setGeoFilter: (filter: Partial<GeoIntelligenceFilter>) => {
    set((state) => ({
      geoIntelligence: {
        ...state.geoIntelligence,
        filter: { ...state.geoIntelligence.filter, ...filter },
      },
    }));
  },

  /**
   * Calcula e armazena o resultado do expansion target para um percentual dado.
   */
  setExpansionTarget: async (pct: number) => {
    const stationCode = null; // expansion target requer stationCode — chamadores devem usar loadGeoIntelligence primeiro
    void stationCode; // suprime warning de unused
    set((state) => ({
      geoIntelligence: {
        ...state.geoIntelligence,
        expansionTargetResult: { expansion_target_pct: pct },
      },
    }));
  },

  /**
   * Seleciona (ou deseleciona) um território pelo ID.
   */
  selectGeoTerritory: (territoryId: string | null) => {
    set((state) => ({
      geoIntelligence: {
        ...state.geoIntelligence,
        selectedTerritoryId: territoryId,
      },
    }));
  },

  // ---------------------------------------------------------------------------
  // ACTIVE TAB ACTION
  // ---------------------------------------------------------------------------

  setActiveTab: (tab: string) => {
    set({ activeTab: tab });
  },

  // ---------------------------------------------------------------------------
  // MANUAL ANALYSIS PANEL ACTION
  // ---------------------------------------------------------------------------

  setManualAnalysisOpen: (open: boolean) => {
    set({ manualAnalysisOpen: open });
    if (!open) {
      // Limpa análise e pin ao fechar o painel
      set((state) => ({
        manualAnalysisPin: null,
        recruitableAnalysis: {
          ...state.recruitableAnalysis,
          params: {
            ...state.recruitableAnalysis.params,
            centerLat: '',
            centerLon: '',
            selectedLeadId: null,
            radiusMeters: 1000,
          },
          result: null,
          error: null,
          isStale: false,
        },
      }));
    }
  },

  setManualAnalysisPin: (pin) => {
    set({ manualAnalysisPin: pin });
  },

  // ---------------------------------------------------------------------------
  // RECRUITABLE AREA ANALYSIS ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Atualiza parcialmente os parâmetros de análise recrutável.
   * Marca isStale: true quando há resultado existente.
   */
  setRecruitableParams: (params: Partial<RecruitableAnalysisParams>) => {
    set((state) => {
      const hasResult = state.recruitableAnalysis.result !== null;
      return {
        recruitableAnalysis: {
          ...state.recruitableAnalysis,
          params: { ...state.recruitableAnalysis.params, ...params },
          isStale: hasResult ? true : state.recruitableAnalysis.isStale,
        },
      };
    });
  },

  /**
   * Armazena o resultado da análise recrutável (e erro opcional).
   */
  setRecruitableResult: (result: EvaluatorResult | null, error: string | null = null) => {
    set((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        result,
        error,
        isStale: false,
      },
    }));
  },

  /**
   * Limpa resultado, erro, ponto central e lead selecionado.
   * Preserva minAdv e radiusMeters.
   */
  clearRecruitableAnalysis: () => {
    set((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          centerLat: '',
          centerLon: '',
          selectedLeadId: null,
        },
        result: null,
        error: null,
        isStale: false,
      },
    }));
  },

  // ---------------------------------------------------------------------------
  // CAP OPPORTUNITY ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Seleciona (ou deseleciona) um parceiro para visualização de oportunidade de cap.
   * Toggle: se o mesmo partnerId já estiver selecionado, deseleciona (null).
   */
  setSelectedCapOpportunity: (partnerId: string | null) => {
    set((state) => ({
      capOpportunityState: {
        selectedPartnerId:
          state.capOpportunityState.selectedPartnerId === partnerId ? null : partnerId,
      },
    }));
  },

  // ---------------------------------------------------------------------------
  // HEX SELECTION ACTIONS
  // ---------------------------------------------------------------------------

  /**
   * Alterna a seleção de um hex H3.
   * Se já selecionado, remove e subtrai os valores de demanda.
   * Se não selecionado, adiciona e acumula os valores de demanda.
   */
  toggleHexSelection: (hexId: string, demandDaily: number, demandResidual: number) => {
    set((state) => {
      const { selectedHexIds, totalDemandDaily, totalDemandResidual } = state.hexSelectionState;
      const isSelected = selectedHexIds.includes(hexId);
      if (isSelected) {
        return {
          hexSelectionState: {
            selectedHexIds: selectedHexIds.filter((id) => id !== hexId),
            totalDemandDaily: totalDemandDaily - demandDaily,
            totalDemandResidual: totalDemandResidual - demandResidual,
          },
        };
      }
      return {
        hexSelectionState: {
          selectedHexIds: [...selectedHexIds, hexId],
          totalDemandDaily: totalDemandDaily + demandDaily,
          totalDemandResidual: totalDemandResidual + demandResidual,
        },
      };
    });
  },

  /**
   * Limpa toda a seleção de hexes e reseta os acumuladores de demanda.
   */
  clearHexSelection: () => {
    set({ hexSelectionState: { selectedHexIds: [], totalDemandDaily: 0, totalDemandResidual: 0 } });
  },

  // ---------------------------------------------------------------------------
  // WHAT-IF MODE ACTION
  // ---------------------------------------------------------------------------

  /**
   * Ativa ou desativa o modo what-if de reposicionamento de parceiros.
   */
  setWhatIfModeActive: (active: boolean) => {
    set({ whatIfModeActive: active });
  },
}));

/**
 * Acessa o estado atual do store fora de componentes React.
 * Útil para workers, utilitários e testes.
 */
export const getStore = () => useStore.getState();
