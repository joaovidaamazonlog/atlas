/**
 * hcpUtils.ts
 * ===========
 * Lógica de clusters HCP (Host/Pickup) em 3 fases.
 * Migrado de frontend/js/modules/route-manager.js para TypeScript.
 * Sem dependências de DOM — funções puras assíncronas.
 */

import * as turf from '@turf/turf';
import { HCP_CONFIG } from './config';
import { osrmTableMatrix, osrmResult } from './routeUtils';
import type { Partner, HcpGroups } from '../store/types';

// ---------------------------------------------------------------------------
// TIPOS INTERNOS
// ---------------------------------------------------------------------------

export interface HcpHostWithPickups extends Partner {
  pickups: Partner[];
}

export interface Phase1Result {
  hosts: HcpHostWithPickups[];
  pickups: Partner[];
  moves: HcpMove[];
}

export interface HcpMove {
  pickup: Partner;
  from: string | null;
  to: string;
  type: 'move';
}

export interface Phase2Result {
  hosts: HcpHostWithPickups[];
  assignments: Array<{ hero: Partner; host: HcpHostWithPickups }>;
  remainingHeros: Partner[];
}

export interface NewHostSuggestion {
  hostCandidate: Partner;
  pickups: Partner[];
}

export interface Phase3Result {
  hosts: HcpHostWithPickups[];
  newHostSuggestions: NewHostSuggestion[];
}

// ---------------------------------------------------------------------------
// FASE 1 — Realocar pickups existentes para o host mais próximo
// ---------------------------------------------------------------------------

/**
 * Fase 1: Para cada pickup existente, encontra o host mais próximo dentro dos
 * limites de distância/duração e sugere a realocação se necessário.
 *
 * @param groups  - Grupos HCP atuais
 * @param usedStores - Set de store_ids já utilizados nesta sessão
 */
export async function hcpPhase1(
  groups: HcpGroups,
  usedStores: Set<string>,
): Promise<Phase1Result> {
  const hosts: HcpHostWithPickups[] = groups.hosts.map((h) => ({
    ...h,
    pickups: groups.pickups
      .filter((p) => p.HCP_host_partner === h.name)
      .slice(),
  }));
  const pickups = groups.pickups.slice();
  const moves: HcpMove[] = [];

  if (!pickups.length || !hosts.length) return { hosts, pickups, moves };

  const coords = [
    ...pickups.map((p) => ({ lat: p.lat ?? 0, lon: p.lon ?? 0 })),
    ...hosts.map((h) => ({ lat: h.lat ?? 0, lon: h.lon ?? 0 })),
  ];
  const sources = pickups.map((_, i) => i);
  const destinations = hosts.map((_, j) => pickups.length + j);

  let matrix;
  try {
    matrix = await osrmTableMatrix(coords, sources, destinations);
  } catch {
    return { hosts, pickups, moves };
  }

  for (let i = 0; i < pickups.length; i++) {
    const pickup = pickups[i];
    if (usedStores.has(pickup.store_id ?? '')) continue;

    const candidates = hosts
      .map((host, j) => {
        const r = osrmResult(matrix.distances, matrix.durations, i, j);
        if (!r) return null;
        if (
          r.distance > HCP_CONFIG.maxDistanceM ||
          r.duration > HCP_CONFIG.maxDurationS
        )
          return null;
        const cap = host.pickups?.length ?? 0;
        if (cap >= HCP_CONFIG.maxPickupsPerHost) return null;
        return { host, j, distance: r.distance };
      })
      .filter(Boolean)
      .sort((a, b) => a!.distance - b!.distance) as Array<{
      host: HcpHostWithPickups;
      j: number;
      distance: number;
    }>;

    if (!candidates.length) continue;

    const chosen = candidates[0].host;
    if (pickup.HCP_host_partner !== chosen.name) {
      moves.push({
        pickup,
        from: pickup.HCP_host_partner,
        to: chosen.name,
        type: 'move',
      });
    }

    if (!chosen.pickups) chosen.pickups = [];
    if (
      !chosen.pickups.some((p) => p.store_id === pickup.store_id) &&
      chosen.pickups.length < HCP_CONFIG.maxPickupsPerHost
    ) {
      chosen.pickups.push(pickup);
      usedStores.add(pickup.store_id ?? '');
    }
  }

  return { hosts, pickups, moves };
}

// ---------------------------------------------------------------------------
// FASE 2 — Alocar Hub Heros em hosts existentes
// ---------------------------------------------------------------------------

/**
 * Fase 2: Para cada Hub Hero, tenta alocá-lo no host existente mais próximo
 * que ainda tenha capacidade.
 *
 * @param groups       - Grupos HCP (com heros já filtrados pelos restantes da fase 1)
 * @param currentHosts - Hosts com pickups atualizados pela fase 1
 * @param usedStores   - Set de store_ids já utilizados
 */
export async function hcpPhase2(
  groups: HcpGroups,
  currentHosts: HcpHostWithPickups[],
  usedStores: Set<string>,
): Promise<Phase2Result> {
  const hosts: HcpHostWithPickups[] = currentHosts.map((h) => ({
    ...h,
    pickups: (h.pickups ?? []).slice(),
  }));
  const heros = groups.heros.slice();
  const assignments: Array<{ hero: Partner; host: HcpHostWithPickups }> = [];

  if (!heros.length || !hosts.length)
    return { hosts, assignments, remainingHeros: heros };

  const coords = [
    ...heros.map((h) => ({ lat: h.lat ?? 0, lon: h.lon ?? 0 })),
    ...hosts.map((h) => ({ lat: h.lat ?? 0, lon: h.lon ?? 0 })),
  ];
  const sources = heros.map((_, i) => i);
  const destinations = hosts.map((_, j) => heros.length + j);

  let matrix;
  try {
    matrix = await osrmTableMatrix(coords, sources, destinations);
  } catch {
    return { hosts, assignments, remainingHeros: heros };
  }

  const remaining: Partner[] = [];

  for (let i = 0; i < heros.length; i++) {
    const hero = heros[i];
    if (usedStores.has(hero.store_id ?? '')) continue;

    const candidates = hosts
      .map((host, j) => {
        if ((host.pickups?.length ?? 0) >= HCP_CONFIG.maxPickupsPerHost)
          return null;
        const r = osrmResult(matrix.distances, matrix.durations, i, j);
        if (!r) return null;
        if (
          r.distance > HCP_CONFIG.maxDistanceM ||
          r.duration > HCP_CONFIG.maxDurationS
        )
          return null;
        return { host, distance: r.distance };
      })
      .filter(Boolean)
      .sort((a, b) => a!.distance - b!.distance) as Array<{
      host: HcpHostWithPickups;
      distance: number;
    }>;

    if (!candidates.length) {
      remaining.push(hero);
      continue;
    }

    let assigned = false;
    for (const { host } of candidates) {
      if (!host.pickups) host.pickups = [];
      if (host.pickups.length < HCP_CONFIG.maxPickupsPerHost) {
        host.pickups.push(hero);
        assignments.push({ hero, host });
        usedStores.add(hero.store_id ?? '');
        assigned = true;
        break;
      }
    }
    if (!assigned) remaining.push(hero);
  }

  return { hosts, assignments, remainingHeros: remaining };
}

// ---------------------------------------------------------------------------
// FASE 3 — Sugerir novos clusters de hosts para heros restantes
// ---------------------------------------------------------------------------

/**
 * Fase 3: Agrupa os heros restantes em clusters via k-means (turf.js) e
 * sugere novos hosts para cada cluster denso o suficiente.
 *
 * @param groups       - Grupos HCP (com heros restantes da fase 2)
 * @param currentHosts - Hosts atualizados pelas fases anteriores
 * @param usedStores   - Set de store_ids já utilizados
 */
export async function hcpPhase3(
  groups: HcpGroups,
  currentHosts: HcpHostWithPickups[],
  usedStores: Set<string>,
): Promise<Phase3Result> {
  const hosts: HcpHostWithPickups[] = currentHosts.map((h) => ({
    ...h,
    pickups: (h.pickups ?? []).slice(),
  }));
  const heros = groups.heros.slice();
  const newHostSuggestions: NewHostSuggestion[] = [];

  if (heros.length < HCP_CONFIG.minClusterMembers)
    return { hosts, newHostSuggestions };

  const k = Math.max(1, Math.ceil(heros.length / 5));
  const fc = turf.featureCollection(
    heros.map((h) =>
      turf.point([h.lon ?? 0, h.lat ?? 0], { store_id: h.store_id }),
    ),
  );

  let clustered: ReturnType<typeof turf.clustersKmeans>;
  try {
    clustered = turf.clustersKmeans(fc, { numberOfClusters: k });
  } catch {
    return { hosts, newHostSuggestions };
  }

  // Agrupar features por cluster
  const clusterMap = new Map<number, typeof clustered.features>();
  clustered.features.forEach((f) => {
    const cid = f.properties?.cluster as number;
    if (!clusterMap.has(cid)) clusterMap.set(cid, []);
    clusterMap.get(cid)!.push(f);
  });

  for (const [, features] of clusterMap.entries()) {
    let members = features
      .map((f) =>
        heros.find((h) => h.store_id === (f.properties?.store_id as string)),
      )
      .filter(Boolean) as Partner[];

    if (!members.length) continue;

    // Limitar ao máximo de membros por cluster
    if (members.length > HCP_CONFIG.maxClusterMembers) {
      const fcTmp = turf.featureCollection(
        members.map((m) => turf.point([m.lon ?? 0, m.lat ?? 0])),
      );
      const cTmp = turf.centroid(fcTmp);
      members.sort(
        (a, b) =>
          turf.distance(cTmp, turf.point([b.lon ?? 0, b.lat ?? 0])) -
          turf.distance(cTmp, turf.point([a.lon ?? 0, a.lat ?? 0])),
      );
      members = members.slice(0, HCP_CONFIG.maxClusterMembers);
    }

    const fc2 = turf.featureCollection(
      members.map((m) => turf.point([m.lon ?? 0, m.lat ?? 0])),
    );
    const centroid = turf.centroid(fc2);

    const maxDist = Math.max(
      ...members.map((m) =>
        turf.distance(centroid, turf.point([m.lon ?? 0, m.lat ?? 0]), {
          units: 'kilometers',
        }),
      ),
    );

    if (
      maxDist > HCP_CONFIG.clusterDensityKm ||
      members.length < HCP_CONFIG.minClusterMembers
    )
      continue;

    // Escolher o membro mais próximo do centróide como host candidato
    let hostCandidate: Partner | null = null;
    let hostDist = Infinity;
    members.forEach((m) => {
      const d = turf.distance(
        centroid,
        turf.point([m.lon ?? 0, m.lat ?? 0]),
        { units: 'kilometers' },
      );
      if (d < hostDist) {
        hostDist = d;
        hostCandidate = m;
      }
    });

    if (!hostCandidate || usedStores.has((hostCandidate as Partner).store_id ?? ''))
      continue;

    const pickupCandidates = members.filter(
      (m) => m.store_id !== (hostCandidate as Partner).store_id,
    );
    if (!pickupCandidates.length) continue;

    // Verificar distância OSRM dos pickups ao host candidato
    const coords = [
      ...pickupCandidates.map((p) => ({ lat: p.lat ?? 0, lon: p.lon ?? 0 })),
      { lat: (hostCandidate as Partner).lat ?? 0, lon: (hostCandidate as Partner).lon ?? 0 },
    ];

    let matrix;
    try {
      matrix = await osrmTableMatrix(
        coords,
        pickupCandidates.map((_, i) => i),
        [pickupCandidates.length],
      );
    } catch {
      continue;
    }

    const valid = pickupCandidates
      .filter((p, r) => {
        if (usedStores.has(p.store_id ?? '')) return false;
        const res = osrmResult(matrix.distances, matrix.durations, r, 0);
        return (
          res &&
          res.distance <= HCP_CONFIG.maxDistanceM &&
          res.duration <= HCP_CONFIG.maxDurationS
        );
      })
      .slice(0, HCP_CONFIG.maxPickupsPerHost);

    if (valid.length < HCP_CONFIG.minPickupsForNewHost) continue;

    // Marcar como usados
    usedStores.add((hostCandidate as Partner).store_id ?? '');
    valid.forEach((fp) => usedStores.add(fp.store_id ?? ''));

    newHostSuggestions.push({
      hostCandidate: hostCandidate as Partner,
      pickups: valid,
    });

    hosts.push({
      ...(hostCandidate as Partner),
      pickups: valid.slice(),
    });
  }

  return { hosts, newHostSuggestions };
}
