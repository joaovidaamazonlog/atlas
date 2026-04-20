/**
 * recruitableAreaEvaluator.test.ts
 * =================================
 * Testes de propriedade e unitários para o evaluator de área recrutável.
 *
 * Propriedades testadas:
 *   Property 2 — Filtragem de células por raio (Validates: Requirements 3.1)
 *   Property 3 — Demanda total é soma das células selecionadas (Validates: Requirements 3.2)
 *   Property 4 — Demanda residual é soma das células não cobertas (Validates: Requirements 3.3)
 *   Property 5 — Classificação binária de viabilidade (Validates: Requirements 4.1, 4.2)
 *   Property 6 — Estrutura completa do resultado (Validates: Requirements 4.3, 4.4)
 *
 * Testes unitários:
 *   - MISSING_HEATMAP, MISSING_CENTER, NO_HEATMAP_COVERAGE, residualCells, demand_residual
 *   (Validates: Requirements 3.4, 3.5)
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import * as turf from '@turf/turf';
import {
  evaluateRecruitableArea,
  isEvaluatorError,
  type EvaluatorInput,
} from './recruitableAreaEvaluator';

// ---------------------------------------------------------------------------
// Helpers de construção de features
// ---------------------------------------------------------------------------

/** Cria uma feature GeoJSON Point com propriedades de heatmap. */
function makePointFeature(
  lon: number,
  lat: number,
  demandDaily: number,
  isCovered: boolean,
  demandResidual?: number,
): GeoJSON.Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [lon, lat] },
    properties: {
      demand_daily: demandDaily,
      demand_residual: demandResidual ?? (isCovered ? 0 : demandDaily),
      is_covered: isCovered,
    },
  };
}

/** Cria uma feature GeoJSON Polygon (quadrado simples) com propriedades de heatmap. */
function makePolygonFeature(
  centerLon: number,
  centerLat: number,
  demandDaily: number,
  isCovered: boolean,
  demandResidual?: number,
): GeoJSON.Feature {
  const d = 0.001; // ~111m de lado
  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [centerLon - d, centerLat - d],
        [centerLon + d, centerLat - d],
        [centerLon + d, centerLat + d],
        [centerLon - d, centerLat + d],
        [centerLon - d, centerLat - d],
      ]],
    },
    properties: {
      demand_daily: demandDaily,
      demand_residual: demandResidual ?? (isCovered ? 0 : demandDaily),
      is_covered: isCovered,
    },
  };
}

/** Input mínimo válido para o evaluator. */
function makeInput(overrides: Partial<EvaluatorInput> = {}): EvaluatorInput {
  return {
    centerLat: -23.5,
    centerLon: -46.6,
    radiusMeters: 1000,
    minAdv: 40,
    heatmapFeatures: [makePointFeature(-46.6, -23.5, 50, false)],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Property 2 — Filtragem de células por raio
// Feature: recruitable-area-analysis, Property 2: Filtragem de células por raio
// Validates: Requirements 3.1
// ---------------------------------------------------------------------------

describe('Property 2 — Filtragem de células por raio', () => {
  it('selectedCells contém exatamente as células com distância ≤ raio', () => {
    // Feature: recruitable-area-analysis, Property 2: Filtragem de células por raio
    fc.assert(
      fc.property(
        // Centro da análise: coordenadas em São Paulo (usando double para evitar restrição 32-bit)
        fc.double({ min: -23.6, max: -23.4, noNaN: true }),
        fc.double({ min: -46.7, max: -46.5, noNaN: true }),
        // Raio entre 200m e 3000m
        fc.integer({ min: 200, max: 3000 }),
        // Lista de células com offsets em graus (~0.001° ≈ 111m)
        fc.array(
          fc.record({
            dLon: fc.double({ min: -0.05, max: 0.05, noNaN: true }),
            dLat: fc.double({ min: -0.05, max: 0.05, noNaN: true }),
            demand: fc.integer({ min: 1, max: 100 }),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (centerLat, centerLon, radiusMeters, cells) => {
          const heatmapFeatures = cells.map((c) =>
            makePointFeature(centerLon + c.dLon, centerLat + c.dLat, c.demand, false),
          );

          const result = evaluateRecruitableArea({
            centerLat,
            centerLon,
            radiusMeters,
            minAdv: 1,
            heatmapFeatures,
          });

          if (isEvaluatorError(result)) return false;

          // Calcula quais células deveriam estar selecionadas
          const center = turf.point([centerLon, centerLat]);
          const expectedSelected = heatmapFeatures.filter((f) => {
            const geom = f.geometry as GeoJSON.Point;
            const [lon, lat] = geom.coordinates;
            const dist = turf.distance(center, turf.point([lon, lat]), { units: 'meters' });
            return dist <= radiusMeters;
          });

          return result.selectedCells.length === expectedSelected.length;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3 — Demanda total é soma das células selecionadas
// Feature: recruitable-area-analysis, Property 3: Demanda total é soma das células selecionadas
// Validates: Requirements 3.2
// ---------------------------------------------------------------------------

describe('Property 3 — Demanda total é soma das células selecionadas', () => {
  it('totalDemand === sum(selectedCells.demand_daily)', () => {
    // Feature: recruitable-area-analysis, Property 3: Demanda total é soma das células selecionadas
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            demand: fc.integer({ min: 0, max: 200 }),
            isCovered: fc.boolean(),
          }),
          { minLength: 1, maxLength: 30 },
        ),
        (cells) => {
          // Todas as células no mesmo ponto central → todas selecionadas
          const heatmapFeatures = cells.map((c) =>
            makePointFeature(-46.6, -23.5, c.demand, c.isCovered),
          );

          const result = evaluateRecruitableArea(
            makeInput({ heatmapFeatures, radiusMeters: 10 }),
          );

          if (isEvaluatorError(result)) return false;

          const expectedTotal = result.selectedCells.reduce(
            (sum, f) => sum + ((f.properties?.demand_daily as number) ?? 0),
            0,
          );

          return result.totalDemand === expectedTotal;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4 — Demanda residual é soma das células não cobertas
// Feature: recruitable-area-analysis, Property 4: Demanda residual é soma das células não cobertas
// Validates: Requirements 3.3
// ---------------------------------------------------------------------------

describe('Property 4 — Demanda residual é soma das células não cobertas', () => {
  it('residualDemand === sum(demand_residual das células selecionadas) e residualCells ⊆ selectedCells', () => {
    // Feature: recruitable-area-analysis, Property 4: Demanda residual é soma das células não cobertas
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            demand: fc.integer({ min: 0, max: 200 }),
            isCovered: fc.boolean(),
          }),
          { minLength: 1, maxLength: 30 },
        ),
        (cells) => {
          const heatmapFeatures = cells.map((c) =>
            makePointFeature(-46.6, -23.5, c.demand, c.isCovered),
          );

          const result = evaluateRecruitableArea(
            makeInput({ heatmapFeatures, radiusMeters: 10 }),
          );

          if (isEvaluatorError(result)) return false;

          // residualCells deve ser subconjunto de selectedCells
          const selectedSet = new Set(result.selectedCells);
          const allResidualInSelected = result.residualCells.every((c) => selectedSet.has(c));

          // residualDemand deve ser soma de demand_residual das células selecionadas
          const expectedResidual = result.selectedCells.reduce(
            (sum, f) => sum + ((f.properties?.demand_residual as number) ?? 0),
            0,
          );

          return allResidualInSelected && result.residualDemand === expectedResidual;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 5 — Classificação binária de viabilidade
// Feature: recruitable-area-analysis, Property 5: Classificação binária de viabilidade
// Validates: Requirements 4.1, 4.2
// ---------------------------------------------------------------------------

describe('Property 5 — Classificação binária de viabilidade', () => {
  it('viable === (residualDemand >= minAdv)', () => {
    // Feature: recruitable-area-analysis, Property 5: Classificação binária de viabilidade
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }),  // demanda residual
        fc.integer({ min: 1, max: 500 }),   // minAdv
        (residualDemand, minAdv) => {
          // Constrói uma célula com demand_residual exato e is_covered=false
          const heatmapFeatures: GeoJSON.Feature[] = [
            makePointFeature(-46.6, -23.5, residualDemand, false, residualDemand),
          ];

          const result = evaluateRecruitableArea(
            makeInput({ heatmapFeatures, minAdv, radiusMeters: 10 }),
          );

          if (isEvaluatorError(result)) return false;

          return result.viable === (result.residualDemand >= minAdv);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6 — Estrutura completa do resultado
// Feature: recruitable-area-analysis, Property 6: Estrutura completa do resultado
// Validates: Requirements 4.3, 4.4
// ---------------------------------------------------------------------------

describe('Property 6 — Estrutura completa do resultado', () => {
  it('toda execução válida retorna objeto com todos os campos obrigatórios', () => {
    // Feature: recruitable-area-analysis, Property 6: Estrutura completa do resultado
    fc.assert(
      fc.property(
        fc.double({ min: -90, max: 90, noNaN: true }),
        fc.double({ min: -180, max: 180, noNaN: true }),
        fc.integer({ min: 100, max: 5000 }),
        fc.integer({ min: 1, max: 500 }),
        fc.array(
          fc.record({
            demand: fc.integer({ min: 0, max: 200 }),
            isCovered: fc.boolean(),
          }),
          { minLength: 1, maxLength: 10 },
        ),
        (centerLat, centerLon, radiusMeters, minAdv, cells) => {
          const heatmapFeatures = cells.map((c) =>
            makePointFeature(centerLon, centerLat, c.demand, c.isCovered),
          );

          const result = evaluateRecruitableArea({
            centerLat,
            centerLon,
            radiusMeters,
            minAdv,
            heatmapFeatures,
          });

          if (isEvaluatorError(result)) return false;

          // Verifica presença de todos os campos obrigatórios
          return (
            typeof result.totalDemand === 'number' &&
            typeof result.residualDemand === 'number' &&
            typeof result.minAdv === 'number' &&
            typeof result.gap === 'number' &&
            typeof result.viable === 'boolean' &&
            (result.reason === null || typeof result.reason === 'string') &&
            Array.isArray(result.selectedCells) &&
            Array.isArray(result.residualCells) &&
            // reason é null quando viável, ReasonCode quando não viável
            (result.viable ? result.reason === null : result.reason !== null)
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Testes unitários
// Validates: Requirements 3.4, 3.5
// ---------------------------------------------------------------------------

describe('evaluateRecruitableArea — testes unitários', () => {
  // --- MISSING_HEATMAP ---

  it('retorna MISSING_HEATMAP quando heatmapFeatures é array vazio', () => {
    const result = evaluateRecruitableArea(makeInput({ heatmapFeatures: [] }));
    expect(isEvaluatorError(result)).toBe(true);
    if (isEvaluatorError(result)) {
      expect(result.type).toBe('MISSING_HEATMAP');
    }
  });

  it('retorna MISSING_HEATMAP quando heatmapFeatures é null', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = evaluateRecruitableArea(makeInput({ heatmapFeatures: null as any }));
    expect(isEvaluatorError(result)).toBe(true);
    if (isEvaluatorError(result)) {
      expect(result.type).toBe('MISSING_HEATMAP');
    }
  });

  // --- MISSING_CENTER ---

  it('retorna MISSING_CENTER quando centerLat é NaN', () => {
    const result = evaluateRecruitableArea(makeInput({ centerLat: NaN }));
    expect(isEvaluatorError(result)).toBe(true);
    if (isEvaluatorError(result)) {
      expect(result.type).toBe('MISSING_CENTER');
    }
  });

  it('retorna MISSING_CENTER quando centerLon é NaN', () => {
    const result = evaluateRecruitableArea(makeInput({ centerLon: NaN }));
    expect(isEvaluatorError(result)).toBe(true);
    if (isEvaluatorError(result)) {
      expect(result.type).toBe('MISSING_CENTER');
    }
  });

  // --- NO_HEATMAP_COVERAGE ---

  it('retorna totalDemand: 0 e reason: NO_HEATMAP_COVERAGE quando nenhuma célula está no raio', () => {
    // Célula muito distante do centro
    const farCell = makePointFeature(-40.0, -20.0, 100, false);
    const result = evaluateRecruitableArea(
      makeInput({
        centerLat: -23.5,
        centerLon: -46.6,
        radiusMeters: 500,
        minAdv: 40,
        heatmapFeatures: [farCell],
      }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.totalDemand).toBe(0);
      expect(result.residualDemand).toBe(0);
      expect(result.viable).toBe(false);
      expect(result.reason).toBe('NO_HEATMAP_COVERAGE');
      expect(result.selectedCells).toHaveLength(0);
    }
  });

  // --- residualCells não inclui células cobertas ---

  it('células com is_covered=true não entram em residualCells', () => {
    const coveredCell = makePointFeature(-46.6, -23.5, 80, true, 0);
    const uncoveredCell = makePointFeature(-46.601, -23.5, 50, false, 50);

    const result = evaluateRecruitableArea(
      makeInput({
        heatmapFeatures: [coveredCell, uncoveredCell],
        radiusMeters: 500,
        minAdv: 10,
      }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.selectedCells).toHaveLength(2);
      expect(result.residualCells).toHaveLength(1);
      // A célula residual deve ser a não coberta
      expect(result.residualCells[0].properties?.is_covered).toBe(false);
    }
  });

  // --- demand_residual do heatmap é usado diretamente ---

  it('usa demand_residual do heatmap diretamente, sem recalcular cobertura', () => {
    // Célula marcada como coberta mas com demand_residual parcial (cenário real do backend)
    const partialResidualCell = makePointFeature(-46.6, -23.5, 100, true, 30);

    const result = evaluateRecruitableArea(
      makeInput({
        heatmapFeatures: [partialResidualCell],
        radiusMeters: 500,
        minAdv: 10,
      }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      // demand_residual deve ser 30 (valor do heatmap), não 0 nem 100
      expect(result.residualDemand).toBe(30);
      expect(result.totalDemand).toBe(100);
    }
  });

  // --- Polygon feature ---

  it('extrai centroide de feature Polygon corretamente', () => {
    const polygonCell = makePolygonFeature(-46.6, -23.5, 60, false);

    const result = evaluateRecruitableArea(
      makeInput({
        heatmapFeatures: [polygonCell],
        radiusMeters: 500,
        minAdv: 10,
      }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.selectedCells).toHaveLength(1);
      expect(result.totalDemand).toBe(60);
    }
  });

  // --- gap calculation ---

  it('gap = residualDemand - minAdv', () => {
    const cell = makePointFeature(-46.6, -23.5, 100, false, 70);
    const result = evaluateRecruitableArea(
      makeInput({ heatmapFeatures: [cell], minAdv: 40, radiusMeters: 10 }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.gap).toBe(70 - 40); // 30
      expect(result.viable).toBe(true);
      expect(result.reason).toBeNull();
    }
  });

  // --- INSUFFICIENT_TOTAL_DEMAND ---

  it('reason é INSUFFICIENT_TOTAL_DEMAND quando totalDemand < minAdv', () => {
    // Célula coberta: demand_daily=10, demand_residual=0
    const coveredCell = makePointFeature(-46.6, -23.5, 10, true, 0);
    const result = evaluateRecruitableArea(
      makeInput({ heatmapFeatures: [coveredCell], minAdv: 50, radiusMeters: 10 }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.viable).toBe(false);
      expect(result.reason).toBe('INSUFFICIENT_TOTAL_DEMAND');
    }
  });

  // --- INSUFFICIENT_RESIDUAL_DEMAND ---

  it('reason é INSUFFICIENT_RESIDUAL_DEMAND quando totalDemand >= minAdv mas residualDemand < minAdv', () => {
    // Célula com demand_daily=100 mas demand_residual=10 (maioria coberta)
    const cell = makePointFeature(-46.6, -23.5, 100, false, 10);
    const result = evaluateRecruitableArea(
      makeInput({ heatmapFeatures: [cell], minAdv: 50, radiusMeters: 10 }),
    );

    expect(isEvaluatorError(result)).toBe(false);
    if (!isEvaluatorError(result)) {
      expect(result.viable).toBe(false);
      expect(result.reason).toBe('INSUFFICIENT_RESIDUAL_DEMAND');
    }
  });
});
