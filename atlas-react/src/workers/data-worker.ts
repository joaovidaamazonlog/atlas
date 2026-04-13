/**
 * data-worker.ts
 * ==============
 * Web Worker para processamento off-thread de dados.
 * Compatível com Vite (type: 'module').
 * Migração fiel de frontend/data-worker.js para TypeScript.
 */

import type { Partner, FilterState } from '../store/types';
import type { DataUrls } from '../lib/config';

// ---------------------------------------------------------------------------
// PROTOCOLO DE MENSAGENS
// ---------------------------------------------------------------------------

export type WorkerInMessage =
  | { action: 'filter'; filters: FilterState & { allMarkersData: Partner[] } }
  | { action: 'loadData'; urls: DataUrls };

export interface LoadedDataPayload {
  allMarkersData: Partner[];
  deliveryStations: { nome: string; lat: number; lon: number }[];
  polygonsData: GeoJSON.FeatureCollection | null;
  jurisdictionData: GeoJSON.FeatureCollection | null;
  optimizationData: GeoJSON.FeatureCollection | null;
  idealSupplyData: GeoJSON.Feature[] | null;
  heatmapData: GeoJSON.FeatureCollection | null;
  period: string | object;
}

export type WorkerOutMessage =
  | { action: 'filterResult'; filtered: Partner[] }
  | { action: 'dataLoaded'; payload: LoadedDataPayload }
  | { action: 'error'; message: string };

// ---------------------------------------------------------------------------
// LÓGICA DE FILTRAGEM (migrada de frontend/data-worker.js)
// ---------------------------------------------------------------------------

function filterPartners(
  allMarkersData: Partner[],
  filters: FilterState
): Partner[] {
  const {
    selectedStatuses,
    selectedStations,
    selectedBuckets,
    initiativesFilter,
    jurisdictionFilter,
  } = filters;

  const statusAllSelected = selectedStatuses === 'all';
  const stationAllSelected = selectedStations === 'all';
  const bucketsAllSelected = selectedBuckets === 'all';

  return allMarkersData.filter((marker) => {
    const statusMatch =
      statusAllSelected ||
      (Array.isArray(selectedStatuses) && selectedStatuses.includes(marker.status));

    const stationMatch =
      stationAllSelected ||
      (Array.isArray(selectedStations) && selectedStations.includes(marker.delivery_station));

    const bucketMatch =
      bucketsAllSelected ||
      (Array.isArray(selectedBuckets) && selectedBuckets.includes(marker.bucket_ade));

    let initiativesMatch = true;
    if (initiativesFilter !== 'all') {
      if (initiativesFilter === 'null') {
        initiativesMatch =
          marker.hub_delivey_initiatives === null ||
          marker.hub_delivey_initiatives === undefined ||
          marker.hub_delivey_initiatives === '' ||
          marker.hub_delivey_initiatives === 'N/A';
      } else {
        initiativesMatch = marker.hub_delivey_initiatives === initiativesFilter;
      }
    }

    const jurisdictionMatch =
      jurisdictionFilter === 'all' || marker.jurisdiction_type === jurisdictionFilter;

    return statusMatch && stationMatch && initiativesMatch && jurisdictionMatch && bucketMatch;
  });
}

// ---------------------------------------------------------------------------
// LÓGICA DE CARREGAMENTO DE DADOS
// ---------------------------------------------------------------------------

async function loadData(urls: DataUrls): Promise<void> {
  try {
    const partnersRes = await fetch(urls.partners);
    if (!partnersRes.ok) {
      throw new Error(`Falha ao carregar parceiros: ${partnersRes.status}`);
    }
    const partnersJson = await partnersRes.json();

    const allMarkersData: Partner[] = Array.isArray(partnersJson.allMarkerData)
      ? partnersJson.allMarkerData
      : Array.isArray(partnersJson.partners)
        ? partnersJson.partners
        : Array.isArray(partnersJson)
          ? partnersJson
          : [];
    const deliveryStations = partnersJson.deliveryStations ?? partnersJson.delivery_stations ?? [];
    const period: string | object = partnersJson.period ?? '';

    const [territoriesResult, jurisdictionResult, optimizationResult, heatmapResult] =
      await Promise.allSettled([
        fetch(urls.territories).then((r) => (r.ok ? r.json() : null)),
        fetch(urls.jurisdiction).then((r) => (r.ok ? r.json() : null)),
        fetch(urls.optimization).then((r) => (r.ok ? r.json() : null)),
        fetch(urls.heatmap).then((r) => (r.ok ? r.json() : null)),
      ]);

    const polygonsData =
      territoriesResult.status === 'fulfilled' ? territoriesResult.value : null;
    const jurisdictionData =
      jurisdictionResult.status === 'fulfilled' ? jurisdictionResult.value : null;
    const optimizationData =
      optimizationResult.status === 'fulfilled' ? optimizationResult.value : null;
    const heatmapData =
      heatmapResult.status === 'fulfilled' ? heatmapResult.value : null;

    const idealSupplyData =
      ((optimizationData as GeoJSON.FeatureCollection | null)
        ?.features?.filter((f) => f.properties?.['type'] === 'IDEAL_SLOT') ?? null) as GeoJSON.Feature[] | null;

    const payload: LoadedDataPayload = {
      allMarkersData,
      deliveryStations,
      polygonsData,
      jurisdictionData,
      optimizationData,
      idealSupplyData,
      heatmapData,
      period,
    };

    self.postMessage({ action: 'dataLoaded', payload } satisfies WorkerOutMessage);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Erro desconhecido no worker';
    self.postMessage({ action: 'error', message } satisfies WorkerOutMessage);
  }
}

// ---------------------------------------------------------------------------
// HANDLER DE MENSAGENS
// ---------------------------------------------------------------------------

self.onmessage = function (e: MessageEvent<WorkerInMessage>) {
  const msg = e.data;

  if (msg.action === 'filter') {
    try {
      const { allMarkersData, ...filters } = msg.filters;
      const filtered = filterPartners(allMarkersData, filters as FilterState);
      self.postMessage({ action: 'filterResult', filtered } satisfies WorkerOutMessage);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erro ao filtrar dados';
      self.postMessage({ action: 'error', message } satisfies WorkerOutMessage);
    }
  } else if (msg.action === 'loadData') {
    loadData(msg.urls);
  }
};
