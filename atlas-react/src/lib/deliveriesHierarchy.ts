/**
 * deliveriesHierarchy.ts
 * ======================
 * Índices e filtros hierárquicos (BDM → Base → CTL → ADE → Território)
 * para recortar as análises de entregas (Fase 6) pela visão do gerente.
 *
 * A fonte da hierarquia é o `relatorio_executivo.json` (consumido pelo
 * Dashboard operacional e agora também pelas abas Pacotes & Insights).
 * Reusar essa fonte evita:
 *   - Duplicar a config TEAM em outro artefato.
 *   - Divergências entre o que o Dashboard operacional mostra e o que
 *     as novas abas filtram.
 *
 * O índice resultante permite responder, para qualquer entidade:
 *   "Está dentro do recorte {bdm, base, ctl, ade, territory} ativo?"
 */

import type { ReportData, DashboardFilters } from './reportUtils';
import type {
  PartnerDeliveryStats,
  HexDeliveryBreakdown,
} from '../store/types';

// ---------------------------------------------------------------------------
// ÍNDICE HIERÁRQUICO
// ---------------------------------------------------------------------------

export interface TerritoryMeta {
  territory_id: string;
  base: string;
  bdm: string;
  ctl: string;
  ade?: string;
}

export interface HierarchyIndex {
  /** bucket_ade → meta completa. */
  territoryToMeta: Map<string, TerritoryMeta>;
  /** base → bdm. */
  baseToBdm: Map<string, string>;
  /** BDMs distintos (todos os parceiros de bases desse BDM são elegíveis). */
  allBdms: Set<string>;
  /** Bases por BDM (expandido com satélites). */
  basesByBdm: Map<string, Set<string>>;
}

/**
 * Constrói o índice a partir do reportData. Se reportData vier null,
 * retorna um índice vazio — o consumidor deve tratar como "nenhum
 * filtro hierárquico possível" (comportamento: nada é filtrado).
 */
export function buildHierarchyIndex(reportData: ReportData | null): HierarchyIndex {
  const territoryToMeta = new Map<string, TerritoryMeta>();
  const baseToBdm = new Map<string, string>();
  const allBdms = new Set<string>();
  const basesByBdm = new Map<string, Set<string>>();

  if (!reportData) {
    return { territoryToMeta, baseToBdm, allBdms, basesByBdm };
  }

  for (const base of reportData.bases) {
    baseToBdm.set(base.code, base.bdm);
    allBdms.add(base.bdm);

    if (!basesByBdm.has(base.bdm)) basesByBdm.set(base.bdm, new Set());
    basesByBdm.get(base.bdm)!.add(base.code);
    // Bases satélite absorvidas também contam como pertencentes ao BDM
    for (const sat of base.satelliteAreas ?? []) {
      basesByBdm.get(base.bdm)!.add(sat);
      baseToBdm.set(sat, base.bdm);
    }

    for (const terr of base.territories) {
      territoryToMeta.set(terr.id, {
        territory_id: terr.id,
        base: base.code,
        bdm: base.bdm,
        ctl: terr.ctl,
        ade: terr.ade,
      });
    }
  }

  return { territoryToMeta, baseToBdm, allBdms, basesByBdm };
}

// ---------------------------------------------------------------------------
// MATCHERS
// ---------------------------------------------------------------------------

/**
 * Verifica se um território atende ao recorte de filtros.
 * Filtros 'all' são no-op.
 */
export function territoryMatchesFilters(
  meta: TerritoryMeta,
  filters: DashboardFilters,
): boolean {
  if (filters.bdm !== 'all' && meta.bdm !== filters.bdm) return false;
  if (filters.base !== 'all' && meta.base !== filters.base) return false;
  if (filters.ctl !== 'all' && meta.ctl !== filters.ctl) return false;
  if (filters.ade !== 'all' && meta.ade !== filters.ade) return false;
  if (filters.territory !== 'all' && meta.territory_id !== filters.territory) return false;
  return true;
}

/**
 * Verifica se uma base está no recorte. Usada para parceiros cujo
 * bucket_ade não bate com nenhum território conhecido (ex: parceiros
 * em onboarding sem bucket_ade definido) — nesse caso só BDM/Base
 * podem filtrar.
 */
export function baseMatchesFilters(
  base: string,
  filters: DashboardFilters,
  index: HierarchyIndex,
): boolean {
  if (filters.base !== 'all' && base !== filters.base) return false;
  if (filters.bdm !== 'all') {
    const bdm = index.baseToBdm.get(base);
    if (bdm !== filters.bdm) return false;
  }
  // Se CTL/ADE/Território estão filtrados mas só temos a base,
  // a linha fica fora do recorte (não conseguimos garantir que pertence).
  if (filters.ctl !== 'all') return false;
  if (filters.ade !== 'all') return false;
  if (filters.territory !== 'all') return false;
  return true;
}

// ---------------------------------------------------------------------------
// FILTROS APLICADOS A DATAFRAMES DA FASE 6
// ---------------------------------------------------------------------------

/**
 * Filtra a lista de parceiros da Fase 6 pelo recorte hierárquico.
 * A lógica:
 *   1. Se o parceiro tem bucket_ade e o bucket está no índice, usa a meta
 *      completa do território para checar BDM/Base/CTL/ADE/Territory.
 *   2. Sem bucket_ade (ex: unknown ou onboarding), cai no fallback por base.
 */
export function filterPartnersByHierarchy(
  partners: PartnerDeliveryStats[],
  filters: DashboardFilters,
  index: HierarchyIndex,
): PartnerDeliveryStats[] {
  // Sem filtros ativos → retorna tudo (rápido).
  if (
    filters.bdm === 'all' &&
    filters.base === 'all' &&
    filters.ctl === 'all' &&
    filters.ade === 'all' &&
    filters.territory === 'all'
  ) {
    return partners;
  }

  return partners.filter((p) => {
    if (p.bucket_ade) {
      const meta = index.territoryToMeta.get(p.bucket_ade);
      if (meta) return territoryMatchesFilters(meta, filters);
    }
    return baseMatchesFilters(p.delivery_station, filters, index);
  });
}

/**
 * Filtra os hexes pelo recorte — usa `station_code` e `territory_id`
 * do próprio payload (Fase 6 enriquecida). Hexes sem essas chaves
 * caem fora de qualquer recorte mais específico que `all`.
 */
export function filterHexesByHierarchy(
  hexes: HexDeliveryBreakdown[],
  filters: DashboardFilters,
  index: HierarchyIndex,
): HexDeliveryBreakdown[] {
  if (
    filters.bdm === 'all' &&
    filters.base === 'all' &&
    filters.ctl === 'all' &&
    filters.ade === 'all' &&
    filters.territory === 'all'
  ) {
    return hexes;
  }

  return hexes.filter((h) => {
    if (h.territory_id) {
      const meta = index.territoryToMeta.get(h.territory_id);
      if (meta) return territoryMatchesFilters(meta, filters);
    }
    if (h.station_code) {
      return baseMatchesFilters(h.station_code, filters, index);
    }
    return false;
  });
}

/**
 * Stations que estão dentro do recorte atual (para os dropdowns
 * locais — ex: card de share IHS/DSP). Quando nenhum filtro ativo,
 * retorna todas as stations presentes no índice + as presentes no
 * universo `availableStations`.
 */
export function stationsInScope(
  availableStations: string[],
  filters: DashboardFilters,
  index: HierarchyIndex,
): string[] {
  if (filters.bdm === 'all' && filters.base === 'all') return availableStations;

  const allowed = new Set<string>();
  if (filters.base !== 'all') {
    allowed.add(filters.base);
  } else if (filters.bdm !== 'all') {
    for (const b of index.basesByBdm.get(filters.bdm) ?? []) allowed.add(b);
  }
  return availableStations.filter((ds) => allowed.has(ds));
}
