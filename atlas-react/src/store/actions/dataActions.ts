/**
 * dataActions.ts
 * ==============
 * Funções puras de filtragem e utilitários de dados.
 * Sem efeitos colaterais — facilita testes unitários e de propriedade.
 */

import type { Partner, FilterState } from '../types';

/**
 * Aplica os filtros ativos sobre um array de parceiros.
 * Quando um filtro é 'all', aquele campo não é filtrado.
 *
 * @param partners - Array completo de parceiros
 * @param filters  - Estado atual dos filtros
 * @returns Subconjunto de parceiros que satisfaz todos os critérios ativos
 */
export function applyFiltersLogic(partners: Partner[], filters: FilterState): Partner[] {
  return partners.filter((p) => {
    // Sempre ocultar Exited e New
    if (p.status === 'Exited' || p.status === 'New') return false;

    // Filtro por status
    if (filters.selectedStatuses !== 'all') {
      if (!filters.selectedStatuses.includes(p.status)) return false;
    }

    // Filtro por delivery station
    if (filters.selectedStations !== 'all') {
      if (!filters.selectedStations.includes(p.delivery_station)) return false;
    }

    // Filtro por bucket (carteira ADE)
    if (filters.selectedBuckets !== 'all') {
      if (!filters.selectedBuckets.includes(p.bucket_ade)) return false;
    }

    // Filtro por iniciativas (hub_delivey_initiatives)
    if (filters.initiativesFilter && filters.initiativesFilter !== 'all') {
      if (p.hub_delivey_initiatives !== filters.initiativesFilter) return false;
    }

    // Filtro por tipo de jurisdição
    if (filters.jurisdictionFilter && filters.jurisdictionFilter !== 'all') {
      if (p.jurisdiction_type !== filters.jurisdictionFilter) return false;
    }

    return true;
  });
}

/**
 * Retorna os valores únicos de um campo específico de um array de parceiros.
 * Valores nulos/undefined são excluídos.
 *
 * @param partners - Array de parceiros
 * @param field    - Campo a extrair valores únicos
 * @returns Array de strings únicas, sem duplicatas
 */
export function getUniqueValues(partners: Partner[], field: keyof Partner): string[] {
  const seen = new Set<string>();
  for (const p of partners) {
    const val = p[field];
    if (val !== null && val !== undefined) {
      seen.add(String(val));
    }
  }
  return Array.from(seen);
}
