/**
 * recruitableAreaEvaluator.ts
 * ===========================
 * Função pura de avaliação de viabilidade de área recrutável.
 *
 * Consome features do heatmap (com campos `demand_residual` e `is_covered`
 * gerados pelo backend) e calcula demanda total, residual e classificação
 * de viabilidade — sem recalcular cobertura no frontend.
 */

import * as turf from '@turf/turf';
import type { EvaluatorResult, EvaluatorError, ReasonCode } from '../store/types';

// ---------------------------------------------------------------------------
// INTERFACE DE ENTRADA
// ---------------------------------------------------------------------------

export interface EvaluatorInput {
  centerLat: number;
  centerLon: number;
  radiusMeters: number;
  minAdv: number;
  heatmapFeatures: GeoJSON.Feature[];
}

// Re-exporta tipos do store para conveniência
export type { EvaluatorResult, EvaluatorError, ReasonCode };

// ---------------------------------------------------------------------------
// TYPE GUARD
// ---------------------------------------------------------------------------

/**
 * Distingue EvaluatorError de EvaluatorResult.
 * EvaluatorError tem campo `type` mas não tem `viable`.
 */
export function isEvaluatorError(
  r: EvaluatorResult | EvaluatorError,
): r is EvaluatorError {
  return 'type' in r && !('viable' in r);
}

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

/**
 * Extrai o centroide de uma feature GeoJSON.
 * - Point: usa coordinates diretamente
 * - Polygon/MultiPolygon: usa turf.centroid
 */
function extractCentroid(feature: GeoJSON.Feature): [number, number] | null {
  const geom = feature.geometry;
  if (!geom) return null;

  if (geom.type === 'Point') {
    const [lon, lat] = geom.coordinates as [number, number];
    return [lon, lat];
  }

  if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') {
    const centroid = turf.centroid(feature as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>);
    const [lon, lat] = centroid.geometry.coordinates as [number, number];
    return [lon, lat];
  }

  return null;
}

// ---------------------------------------------------------------------------
// FUNÇÃO PRINCIPAL
// ---------------------------------------------------------------------------

/**
 * Avalia a viabilidade de recrutamento de uma área geográfica.
 *
 * Retorna EvaluatorError em caso de dados inválidos/ausentes,
 * ou EvaluatorResult com a classificação completa.
 */
export function evaluateRecruitableArea(
  input: EvaluatorInput,
): EvaluatorResult | EvaluatorError {
  const { centerLat, centerLon, radiusMeters, minAdv, heatmapFeatures } = input;

  // --- Validação: heatmap ---
  if (!heatmapFeatures || heatmapFeatures.length === 0) {
    return { type: 'MISSING_HEATMAP' };
  }

  // --- Validação: ponto central ---
  if (
    centerLat === null ||
    centerLat === undefined ||
    centerLon === null ||
    centerLon === undefined ||
    isNaN(centerLat) ||
    isNaN(centerLon)
  ) {
    return { type: 'MISSING_CENTER' };
  }

  // --- Validação: parâmetros numéricos ---
  if (radiusMeters <= 0) {
    return { type: 'INVALID_PARAMS', field: 'radiusMeters' };
  }
  if (minAdv <= 0) {
    return { type: 'INVALID_PARAMS', field: 'minAdv' };
  }

  // --- Filtragem de células por raio ---
  const center = turf.point([centerLon, centerLat]);

  const selectedCells: GeoJSON.Feature[] = [];

  for (const feature of heatmapFeatures) {
    const centroid = extractCentroid(feature);
    if (!centroid) continue;

    const [lon, lat] = centroid;
    const hexCentroid = turf.point([lon, lat]);
    const distanceMeters = turf.distance(center, hexCentroid, { units: 'meters' });

    if (distanceMeters <= radiusMeters) {
      selectedCells.push(feature);
    }
  }

  // --- Cálculo de demanda ---
  let totalDemand = 0;
  let residualDemand = 0;
  const residualCells: GeoJSON.Feature[] = [];

  for (const cell of selectedCells) {
    const props = cell.properties ?? {};
    const demandDaily: number = typeof props.demand_daily === 'number' ? props.demand_daily : 0;
    const demandResidual: number = typeof props.demand_residual === 'number' ? props.demand_residual : demandDaily;
    const isCovered: boolean = props.is_covered === true;

    totalDemand += demandDaily;
    residualDemand += demandResidual;

    if (!isCovered) {
      residualCells.push(cell);
    }
  }

  // --- Classificação de viabilidade ---
  const viable = residualDemand >= minAdv;
  const gap = residualDemand - minAdv;

  let reason: ReasonCode | null = null;
  if (!viable) {
    if (selectedCells.length === 0) {
      reason = 'NO_HEATMAP_COVERAGE';
    } else if (totalDemand < minAdv) {
      reason = 'INSUFFICIENT_TOTAL_DEMAND';
    } else {
      reason = 'INSUFFICIENT_RESIDUAL_DEMAND';
    }
  }

  return {
    totalDemand,
    residualDemand,
    minAdv,
    gap,
    viable,
    reason,
    selectedCells,
    residualCells,
  };
}
