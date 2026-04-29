/**
 * recruitableAreaEvaluator.ts
 * ===========================
 * Função pura de avaliação de viabilidade de área recrutável.
 *
 * Regra de negócio:
 * -----------------
 * Apenas hexágonos cujo centroide está DENTRO de alguma jurisdição são
 * considerados. A DS vencedora é determinada pelos hexes dentro de
 * jurisdição: maior contagem vence; empate → maior soma de demand_residual.
 * A demanda é calculada exclusivamente com os hexes da DS vencedora.
 *
 * Se o ponto central estiver fora de qualquer jurisdição, o resultado
 * inclui `outOfJurisdictionStation` com a DS vencedora como aviso.
 *
 * Se nenhum hex dentro do raio estiver em alguma jurisdição, retorna
 * demanda zero com reason NO_HEATMAP_COVERAGE.
 */

import * as turf from '@turf/turf';
import type { EvaluatorResult, EvaluatorError, ReasonCode } from '../store/types';
import { DS_SATELLITES } from './config';

// Índice reverso: satélite → canônica (construído uma vez).
// Usado APENAS para renderizar o badge "Anexo de …" na UI via
// `canonicalBaseFor`. NÃO é usado para colapsar hexes no cálculo de
// balde dominante — satélites mantêm sua identidade própria.
const SATELLITE_TO_CANONICAL: Record<string, string> = {};
for (const [canonical, satellites] of Object.entries(DS_SATELLITES)) {
  for (const sat of satellites) {
    SATELLITE_TO_CANONICAL[sat] = canonical;
  }
}

/**
 * Retorna a canônica de uma satélite (ex: "XSP7" → "DSP5"). Para canônicas
 * retorna undefined. Usado apenas para renderizar o badge "Anexo de …"
 * na UI — NÃO é usado para colapsar hexes no cálculo de balde dominante.
 */
export function canonicalBaseFor(ds: string): string | undefined {
  return SATELLITE_TO_CANONICAL[ds];
}

// ---------------------------------------------------------------------------
// INTERFACE DE ENTRADA
// ---------------------------------------------------------------------------

export interface EvaluatorInput {
  centerLat: number;
  centerLon: number;
  radiusMeters: number;
  minAdv: number;
  heatmapFeatures: GeoJSON.Feature[];
  /**
   * Polígonos de jurisdição (GeoJSON.Feature[]).
   * Cada feature deve ter `properties.delivery_station` com o código da base.
   * Quando omitido ou vazio, nenhuma filtragem por jurisdição é aplicada
   * (comportamento legado — todos os hexes do raio são considerados).
   */
  jurisdictionFeatures?: GeoJSON.Feature[];
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
    const centroid = turf.centroid(
      feature as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>,
    );
    const [lon, lat] = centroid.geometry.coordinates as [number, number];
    return [lon, lat];
  }

  return null;
}

/**
 * Retorna o delivery_station da jurisdição que contém o centroide do hex.
 *
 * Estratégia com fallback:
 * 1. Se o hex tem `in_jurisdiction: true` e `delivery_station` definidos
 *    (heatmap gerado após o novo setup), usa esses campos diretamente — O(1).
 * 2. Caso contrário, faz booleanPointInPolygon contra os polígonos de
 *    jurisdição (heatmap legado) — O(m) onde m = nº de jurisdições.
 *
 * Retorna null se o hex estiver fora de todas as jurisdições.
 */
function stationForHex(
  lon: number,
  lat: number,
  hexFeature: GeoJSON.Feature,
  jurisdictionFeatures: GeoJSON.Feature[],
): string | null {
  const props = hexFeature.properties ?? {};

  // Fast path: heatmap pós-setup tem in_jurisdiction e delivery_station corretos
  if (typeof props.in_jurisdiction === 'boolean') {
    if (!props.in_jurisdiction) return null;
    const ds = props.delivery_station as string | undefined;
    return ds ?? null;
  }

  // Fallback: heatmap legado — booleanPointInPolygon contra polígonos de jurisdição
  // (in_jurisdiction é null/undefined — heatmap gerado antes do novo setup)
  const pt = turf.point([lon, lat]);
  for (const jf of jurisdictionFeatures) {
    const geom = jf.geometry;
    if (!geom) continue;
    if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') {
      if (
        turf.booleanPointInPolygon(
          pt,
          jf as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>,
        )
      ) {
        const ds = jf.properties?.delivery_station as string | undefined;
        return ds ?? null;
      }
    }
  }
  return null;
}

/**
 * Retorna o delivery_station da primeira jurisdição que contém o ponto,
 * ou null se o ponto estiver fora de todas as jurisdições.
 * Usado para verificar o ponto central (não um hex do heatmap).
 */
function stationForPoint(
  lon: number,
  lat: number,
  jurisdictionFeatures: GeoJSON.Feature[],
): string | null {
  const pt = turf.point([lon, lat]);
  for (const jf of jurisdictionFeatures) {
    const geom = jf.geometry;
    if (!geom) continue;
    if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') {
      if (
        turf.booleanPointInPolygon(
          pt,
          jf as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>,
        )
      ) {
        const ds = jf.properties?.delivery_station as string | undefined;
        return ds ?? null;
      }
    }
  }
  return null;
}

/**
 * Dado um mapa de { station → hexes dentro da jurisdição dessa station },
 * retorna a station dominante:
 *   1. Maior número de hexes
 *   2. Empate → maior soma de demand_residual
 * Retorna null se o mapa estiver vazio.
 */
function resolveDominantStation(
  hexesByStation: Map<string, GeoJSON.Feature[]>,
): string | null {
  let winner: string | null = null;
  let maxCount = -1;
  let maxResidual = -1;

  for (const [station, cells] of hexesByStation) {
    const count = cells.length;
    const residual = cells.reduce((sum, cell) => {
      const props = cell.properties ?? {};
      const r =
        typeof props.demand_residual === 'number'
          ? props.demand_residual
          : typeof props.demand_daily === 'number'
            ? props.demand_daily
            : 0;
      return sum + r;
    }, 0);

    if (
      count > maxCount ||
      (count === maxCount && residual > maxResidual)
    ) {
      winner = station;
      maxCount = count;
      maxResidual = residual;
    }
  }

  return winner;
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
  const {
    centerLat,
    centerLon,
    radiusMeters,
    minAdv,
    heatmapFeatures,
    jurisdictionFeatures = [],
  } = input;

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

  // --- Verificar se o ponto central está dentro de alguma jurisdição ---
  // (usado apenas para decidir se exibe o warning — não muda a lógica de filtragem)
  const centerStation =
    jurisdictionFeatures.length > 0
      ? stationForPoint(centerLon, centerLat, jurisdictionFeatures)
      : null;
  const centerInsideJurisdiction = jurisdictionFeatures.length === 0 || centerStation !== null;

  // --- Coletar células dentro do raio ---
  const center = turf.point([centerLon, centerLat]);
  const cellsInRadius: GeoJSON.Feature[] = [];

  for (const feature of heatmapFeatures) {
    const centroid = extractCentroid(feature);
    if (!centroid) continue;

    const [lon, lat] = centroid;
    const distanceMeters = turf.distance(
      center,
      turf.point([lon, lat]),
      { units: 'meters' },
    );

    if (distanceMeters <= radiusMeters) {
      cellsInRadius.push(feature);
    }
  }

  // --- Filtrar hexes por jurisdição e agrupar por DS ---
  let selectedCells: GeoJSON.Feature[];
  let outOfJurisdictionStation: string | undefined;
  let dominantStation: string | null = null;

  if (jurisdictionFeatures.length === 0) {
    // Sem dados de jurisdição: comportamento legado (todos os hexes do raio)
    selectedCells = cellsInRadius;
  } else {
    // Agrupar hexes do raio pela jurisdição que os contém
    const hexesByStation = new Map<string, GeoJSON.Feature[]>();

    for (const feature of cellsInRadius) {
      const centroid = extractCentroid(feature);
      if (!centroid) continue;
      const [lon, lat] = centroid;
      const station = stationForHex(lon, lat, feature, jurisdictionFeatures);
      if (station === null) continue; // hex fora de qualquer jurisdição — descartado

      if (!hexesByStation.has(station)) hexesByStation.set(station, []);
      hexesByStation.get(station)!.push(feature);
    }

    if (hexesByStation.size === 0) {
      // Nenhum hex dentro de qualquer jurisdição no raio
      selectedCells = [];
    } else {
      dominantStation = resolveDominantStation(hexesByStation)!;
      selectedCells = hexesByStation.get(dominantStation)!;

      // Warning quando o ponto central está fora de jurisdição
      if (!centerInsideJurisdiction) {
        outOfJurisdictionStation = dominantStation;
      }
    }
  }

  // --- Cálculo de demanda ---
  let totalDemand = 0;
  let residualDemand = 0;
  const residualCells: GeoJSON.Feature[] = [];

  for (const cell of selectedCells) {
    const props = cell.properties ?? {};
    const demandDaily: number =
      typeof props.demand_daily === 'number' ? props.demand_daily : 0;
    const demandResidual: number =
      typeof props.demand_residual === 'number' ? props.demand_residual : demandDaily;
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
    } else if (totalDemand === 0 && selectedCells.every(c => c.properties?.in_jurisdiction === true)) {
      // Todos os hexes são de área satélite sem histórico de pacotes
      reason = 'NO_HISTORICAL_DATA';
    } else if (totalDemand < minAdv) {
      reason = 'INSUFFICIENT_TOTAL_DEMAND';
    } else {
      reason = 'INSUFFICIENT_RESIDUAL_DEMAND';
    }
  }

  // --- DEBUG TEMPORÁRIO (satellite-areas-daily-integration) ---
  // Remover após validação em produção.
  // eslint-disable-next-line no-console
  console.log('[evaluator:debug]', {
    jurisdictionFeaturesLen: jurisdictionFeatures.length,
    cellsInRadius: cellsInRadius.length,
    dominantStation,
    recommendedStation: dominantStation ?? undefined,
    canonicalBase: dominantStation ? canonicalBaseFor(dominantStation) : undefined,
    sampleCell: selectedCells[0]?.properties,
  });

  return {
    totalDemand,
    residualDemand,
    minAdv,
    gap,
    viable,
    reason,
    selectedCells,
    residualCells,
    outOfJurisdictionStation,
    recommendedStation: dominantStation ?? undefined,
    canonicalBase: dominantStation ? canonicalBaseFor(dominantStation) : undefined,
  };
}
