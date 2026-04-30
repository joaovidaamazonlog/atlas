/**
 * mapActions.ts
 * =============
 * Helpers de mapa: StyleConfig padrão e funções auxiliares de mapa.
 */

import type { StyleConfig } from '../types';

/**
 * Retorna o StyleConfig padrão da aplicação.
 */
export function defaultStyleConfig(): StyleConfig {
  return {
    primaryField: 'delivery_station',
    secondaryField: 'status',
    showRadii: false,
    showPolygons: false,
    showJurisdictions: false,
    showOptimizationLayer: false,
    showHeatmap: false,
    showGeoIntelligence: false,
    showDspShareLayer: false,
    polygonColorField: 'territory',
  };
}
