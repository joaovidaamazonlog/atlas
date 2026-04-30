/**
 * useDashboardFilters.ts
 * ======================
 * Hook + singleton de filtros do Dashboard compartilhado entre abas.
 *
 * Por que não usar o store principal (Zustand) diretamente
 * --------------------------------------------------------
 * O store já está grande e cruza responsabilidades (mapa, prospect,
 * geo intelligence, what-if). Um hook focado — com estado e cache do
 * reportData — deixa a surface de API enxuta e não acopla o Dashboard
 * a evoluções futuras do store principal.
 *
 * Comportamento
 * -------------
 * - `filters`: DashboardFilters (mesma forma usada pelo FilterCascade).
 * - `reportData`: carregado on-demand e cacheado; todas as abas
 *   compartilham o mesmo objeto.
 * - `retry()`: força novo fetch quando o usuário clica em "Tentar de novo".
 *
 * Estado externo a React (módulo-level) porque é global à aplicação.
 * Usamos `useSyncExternalStore` para componentes que consomem sem
 * re-renderizar desnecessariamente.
 */

import { useSyncExternalStore, useCallback } from 'react';
import { DATA_URLS } from '../lib/config';
import type { ReportData, DashboardFilters } from '../lib/reportUtils';

// ---------------------------------------------------------------------------
// ESTADO MODULE-LEVEL
// ---------------------------------------------------------------------------

interface DashboardFiltersState {
  filters: DashboardFilters;
  reportData: ReportData | null;
  isLoadingReport: boolean;
  reportError: string | null;
}

const DEFAULT_FILTERS: DashboardFilters = {
  bdm: 'all',
  base: 'all',
  ctl: 'all',
  ade: 'all',
  territory: 'all',
};

let state: DashboardFiltersState = {
  filters: { ...DEFAULT_FILTERS },
  reportData: null,
  isLoadingReport: false,
  reportError: null,
};

const listeners = new Set<() => void>();

function notify() {
  for (const l of listeners) l();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): DashboardFiltersState {
  return state;
}

// ---------------------------------------------------------------------------
// ACTIONS
// ---------------------------------------------------------------------------

function setFilters(next: DashboardFilters | ((prev: DashboardFilters) => DashboardFilters)) {
  const nextFilters = typeof next === 'function' ? next(state.filters) : next;
  state = { ...state, filters: nextFilters };
  notify();
}

let _inflight = false;

async function loadReport(force = false) {
  if (state.reportData && !force) return;
  if (_inflight) return;
  _inflight = true;
  state = { ...state, isLoadingReport: true, reportError: null };
  notify();
  try {
    const res = await fetch(DATA_URLS.executiveReport);
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const json = (await res.json()) as ReportData;
    state = { ...state, reportData: json, isLoadingReport: false };
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Erro ao carregar relatório.';
    state = { ...state, isLoadingReport: false, reportError: msg };
  } finally {
    _inflight = false;
    notify();
  }
}

function resetReport() {
  state = { ...state, reportData: null, reportError: null };
  notify();
}

// ---------------------------------------------------------------------------
// HOOK
// ---------------------------------------------------------------------------

export interface UseDashboardFiltersResult extends DashboardFiltersState {
  setFilters: typeof setFilters;
  loadReport: () => Promise<void>;
  retry: () => void;
}

export function useDashboardFilters(): UseDashboardFiltersResult {
  const snap = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const retry = useCallback(() => {
    resetReport();
    loadReport();
  }, []);

  return {
    ...snap,
    setFilters,
    loadReport,
    retry,
  };
}
