/**
 * store/index.ts
 * ==============
 * Store Zustand principal da aplicação ATLAS.
 * Substitui o state.js (Proxy reativo) com tipagem estrita e actions.
 */

import { create } from 'zustand';
import type {
  Partner,
  DeliveryStation,
  FilterState,
  StyleConfig,
  RouteStop,
  HcpState,
} from './types';
import { applyFiltersLogic } from './actions/dataActions';
import { defaultStyleConfig } from './actions/mapActions';
import { DATA_URLS } from '../lib/config';

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

      const allMarkersData: Partner[] = partnersJson.partners ?? partnersJson;
      const deliveryStations: DeliveryStation[] = partnersJson.delivery_stations ?? [];
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
}));

// ---------------------------------------------------------------------------
// ACESSO FORA DE COMPONENTES REACT
// ---------------------------------------------------------------------------

/**
 * Acessa o estado atual do store fora de componentes React.
 * Útil para workers, utilitários e testes.
 */
export const getStore = () => useStore.getState();
