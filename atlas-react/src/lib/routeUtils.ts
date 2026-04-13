/**
 * routeUtils.ts
 * =============
 * Utilitários de rota e otimização de paradas.
 * Migrado de frontend/js/modules/route-manager.js para TypeScript.
 * Funções puras sem dependências de DOM.
 */

import type { Partner, RouteStop, HcpGroups } from '../store/types';

// ---------------------------------------------------------------------------
// TIPOS
// ---------------------------------------------------------------------------

interface OsrmTableResult {
  distances: number[][] | null;
  durations: number[][] | null;
}

// ---------------------------------------------------------------------------
// DISTÂNCIA HAVERSINE (substitui L.latLng.distanceTo sem Leaflet)
// ---------------------------------------------------------------------------

/**
 * Calcula a distância em metros entre dois pontos usando a fórmula de Haversine.
 */
function haversineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371000; // raio da Terra em metros
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// OTIMIZAÇÃO DE PARADAS (permutação para N pequeno)
// ---------------------------------------------------------------------------

/**
 * Gera todas as permutações de um array.
 */
function permute<T>(arr: T[]): T[][] {
  if (arr.length <= 1) return [arr];
  return arr.flatMap((v, i) =>
    permute([...arr.slice(0, i), ...arr.slice(i + 1)]).map((r) => [v, ...r]),
  );
}

/**
 * Calcula a distância total de uma ordem de paradas.
 */
function totalDistance(
  from: RouteStop,
  to: RouteStop,
  order: RouteStop[],
): number {
  let d = 0;
  let prev = from;
  for (const stop of order) {
    d += haversineDistance(prev.lat, prev.lon, stop.lat, stop.lon);
    prev = stop;
  }
  d += haversineDistance(prev.lat, prev.lon, to.lat, to.lon);
  return d;
}

/**
 * Encontra a ordem ótima de paradas intermediárias por força bruta (permutação).
 * Adequado para N ≤ 8 paradas. Migrado de `_optimizeStops` em route-manager.js.
 *
 * @param from  - Ponto de origem
 * @param to    - Ponto de destino
 * @param stops - Paradas intermediárias a ordenar
 */
export function optimizeStops(
  from: RouteStop,
  to: RouteStop,
  stops: RouteStop[],
): RouteStop[] {
  if (stops.length <= 1) return stops;
  const perms = permute(stops);
  return perms.reduce(
    (best, order) =>
      totalDistance(from, to, order) < totalDistance(from, to, best)
        ? order
        : best,
    stops,
  );
}

// ---------------------------------------------------------------------------
// OSRM TABLE MATRIX
// ---------------------------------------------------------------------------

/**
 * Consulta a API OSRM Table para obter matriz de distâncias e durações.
 * Migrado de `_osrmTableMatrix` em route-manager.js.
 *
 * @param coords       - Array de coordenadas {lat, lon}
 * @param sources      - Índices das origens (null = todos)
 * @param destinations - Índices dos destinos (null = todos)
 */
export async function osrmTableMatrix(
  coords: Array<{ lat: number; lon: number }>,
  sources: number[] | null = null,
  destinations: number[] | null = null,
): Promise<OsrmTableResult> {
  if (!coords || coords.length === 0) throw new Error('coords empty');

  const coordStr = coords.map((c) => `${c.lon},${c.lat}`).join(';');
  const params = new URLSearchParams();
  params.set('annotations', 'distance,duration');
  if (sources?.length) params.set('sources', sources.join(';'));
  if (destinations?.length) params.set('destinations', destinations.join(';'));

  const res = await fetch(
    `https://router.project-osrm.org/table/v1/driving/${coordStr}?${params}`,
  );
  if (!res.ok) throw new Error(`OSRM table error ${res.status}`);

  const j = await res.json();
  return {
    distances: j.distances ?? null,
    durations: j.durations ?? null,
  };
}

/**
 * Extrai um resultado individual da matriz OSRM.
 */
export function osrmResult(
  distances: number[][] | null,
  durations: number[][] | null,
  row: number,
  col: number,
): { distance: number; duration: number } | null {
  if (!distances || !durations) return null;
  const d = distances[row]?.[col];
  const t = durations[row]?.[col];
  if (d == null || t == null) return null;
  return { distance: d, duration: t };
}

// ---------------------------------------------------------------------------
// HCP GROUPS
// ---------------------------------------------------------------------------

/**
 * Filtra e agrupa parceiros por iniciativa HCP.
 * Migrado de `getCurrentHcpGroups` em route-manager.js.
 *
 * @param partners - Lista de parceiros (já filtrados, sem Exited)
 */
export function getCurrentHcpGroups(partners: Partner[]): HcpGroups {
  const all = partners.filter((p) => p.status !== 'Exited');
  const hosts = all.filter(
    (p) => p.hub_delivey_initiatives === 'HCP Host Partner',
  );
  const pickups = all.filter(
    (p) => p.hub_delivey_initiatives === 'HCP Pick Up Partner',
  );
  const heros = all.filter(
    (p) => p.hub_delivey_initiatives === 'Hub Hero',
  );
  return { hosts, pickups, heros, all };
}
