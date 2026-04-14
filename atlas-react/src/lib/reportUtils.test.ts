/**
 * reportUtils.test.ts
 * ===================
 * Testes de propriedade para reportUtils.ts.
 *
 * **Validates: Requirements 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.11, 2.12**
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import {
  filterBases,
  computeKPIs,
  getChartDataForBase,
  sortTerritories,
  getStatusClass,
} from './reportUtils';
import type {
  BaseData,
  TerritoryData,
  TerritoryRow,
  ReportData,
  DashboardFilters,
} from './reportUtils';

// ---------------------------------------------------------------------------
// ARBITRÁRIOS
// ---------------------------------------------------------------------------

fc.configureGlobal({ numRuns: 100 });

const arbitraryTerritoryData = (): fc.Arbitrary<TerritoryData> =>
  fc.record({
    id: fc.string({ minLength: 1, maxLength: 20 }),
    ctl: fc.string({ minLength: 1, maxLength: 20 }),
    dailyDemand: fc.float({ min: 0, max: 10000, noNaN: true }),
    totalSlots: fc.float({ min: 0, max: 500, noNaN: true }),
    openSlots: fc.float({ min: 0, max: 500, noNaN: true }),
    active: fc.float({ min: 0, max: 500, noNaN: true }),
    onboarding: fc.float({ min: 0, max: 500, noNaN: true }),
    bg: fc.float({ min: 0, max: 500, noNaN: true }),
    prospects: fc.float({ min: 0, max: 500, noNaN: true }),
    inactive: fc.float({ min: 0, max: 500, noNaN: true }),
    attainment: fc.float({ min: 0, max: 1, noNaN: true }),
    accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
  });

const arbitraryBaseData = (): fc.Arbitrary<BaseData> =>
  fc.record({
    code: fc.string({ minLength: 1, maxLength: 10 }),
    bdm: fc.string({ minLength: 1, maxLength: 30 }),
    numTerritories: fc.float({ min: 0, max: 100, noNaN: true }),
    dailyDemand: fc.float({ min: 0, max: 100000, noNaN: true }),
    idealSlots: fc.float({ min: 0, max: 1000, noNaN: true }),
    matchedSlots: fc.float({ min: 0, max: 1000, noNaN: true }),
    openSlots: fc.float({ min: 0, max: 1000, noNaN: true }),
    coverage: fc.float({ min: 0, max: 1, noNaN: true }),
    partners: fc.record({
      active: fc.float({ min: 0, max: 500, noNaN: true }),
      onboarding: fc.float({ min: 0, max: 500, noNaN: true }),
      bgChecks: fc.float({ min: 0, max: 500, noNaN: true }),
      prospects: fc.float({ min: 0, max: 500, noNaN: true }),
      inactive: fc.float({ min: 0, max: 500, noNaN: true }),
    }),
    attainment: fc.float({ min: 0, max: 1, noNaN: true }),
    territories: fc.array(arbitraryTerritoryData(), { minLength: 0, maxLength: 10 }),
  });

const arbitraryReportData = (): fc.Arbitrary<ReportData> =>
  fc.record({
    generatedAt: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: null }),
    bases: fc.array(arbitraryBaseData(), { minLength: 0, maxLength: 10 }),
  });

const arbitraryFilters = (): fc.Arbitrary<DashboardFilters> =>
  fc.record({
    bdm: fc.oneof(fc.constant('all'), fc.string({ minLength: 1, maxLength: 20 })),
    base: fc.oneof(fc.constant('all'), fc.string({ minLength: 1, maxLength: 10 })),
    ctl: fc.oneof(fc.constant('all'), fc.string({ minLength: 1, maxLength: 20 })),
    territory: fc.oneof(fc.constant('all'), fc.string({ minLength: 1, maxLength: 20 })),
  });

const arbitraryTerritoryRow = (): fc.Arbitrary<TerritoryRow> =>
  fc.record({
    id: fc.string({ minLength: 1, maxLength: 20 }),
    ctl: fc.string({ minLength: 1, maxLength: 20 }),
    dailyDemand: fc.float({ min: 0, max: 10000, noNaN: true }),
    totalSlots: fc.float({ min: 0, max: 500, noNaN: true }),
    openSlots: fc.float({ min: 0, max: 500, noNaN: true }),
    active: fc.float({ min: 0, max: 500, noNaN: true }),
    onboarding: fc.float({ min: 0, max: 500, noNaN: true }),
    bg: fc.float({ min: 0, max: 500, noNaN: true }),
    prospects: fc.float({ min: 0, max: 500, noNaN: true }),
    inactive: fc.float({ min: 0, max: 500, noNaN: true }),
    attainment: fc.float({ min: 0, max: 1, noNaN: true }),
    accuracy: fc.float({ min: 0, max: 1, noNaN: true }),
    baseCode: fc.string({ minLength: 1, maxLength: 10 }),
  });

// ---------------------------------------------------------------------------
// PROPRIEDADE 1: filterBases preserva consistência de cascata
// ---------------------------------------------------------------------------

// Feature: atlas-ux-improvements, Propriedade 1: filterBases preserva consistência de cascata
describe('reportUtils — Propriedade 1: filterBases preserva consistência de cascata', () => {
  /**
   * **Validates: Requirements 2.4, 2.5, 2.6**
   *
   * Para qualquer ReportData e combinação de filtros, filterBases retorna
   * apenas bases/territórios que satisfazem todos os filtros ativos.
   */
  it('Feature: atlas-ux-improvements, Propriedade 1: todas as bases retornadas satisfazem os filtros ativos', () => {
    fc.assert(
      fc.property(
        arbitraryReportData(),
        arbitraryFilters(),
        (reportData, filters) => {
          const result = filterBases(reportData, filters);

          // Filtro de BDM: todas as bases retornadas devem ter o BDM correto
          if (filters.bdm && filters.bdm !== 'all') {
            for (const base of result) {
              expect(base.bdm).toBe(filters.bdm);
            }
          }

          // Filtro de base: todas as bases retornadas devem ter o código correto
          if (filters.base && filters.base !== 'all') {
            for (const base of result) {
              expect(base.code).toBe(filters.base);
            }
          }

          // Filtro de CTL: todos os territórios retornados devem ter o CTL correto
          if (filters.ctl && filters.ctl !== 'all') {
            for (const base of result) {
              for (const territory of base.territories) {
                expect(territory.ctl).toBe(filters.ctl);
              }
            }
          }

          // Filtro de território: todos os territórios retornados devem ter o ID correto
          if (filters.territory && filters.territory !== 'all') {
            for (const base of result) {
              for (const territory of base.territories) {
                expect(territory.id).toBe(filters.territory);
              }
            }
          }

          // Bases com filtros de CTL/território ativos não devem ter territórios vazios
          if (
            (filters.ctl && filters.ctl !== 'all') ||
            (filters.territory && filters.territory !== 'all')
          ) {
            for (const base of result) {
              expect(base.territories.length).toBeGreaterThan(0);
            }
          }
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPRIEDADE 2: computeKPIs é consistente com os dados de entrada
// ---------------------------------------------------------------------------

// Feature: atlas-ux-improvements, Propriedade 2: computeKPIs é consistente com os dados de entrada
describe('reportUtils — Propriedade 2: computeKPIs é consistente com os dados de entrada', () => {
  /**
   * **Validates: Requirements 2.7, 2.8**
   *
   * Para qualquer array não-vazio de BaseData:
   * - totalBases === bases.length
   * - totalTerritories === soma dos territories.length
   * - totalDailyDemand === soma dos dailyDemand
   * - avgAttainment ∈ [0, 1]
   */
  it('Feature: atlas-ux-improvements, Propriedade 2: KPIs são consistentes com os dados de entrada', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryBaseData(), { minLength: 1, maxLength: 20 }),
        (bases) => {
          const kpis = computeKPIs(bases);

          // totalBases deve ser igual ao comprimento do array
          expect(kpis.totalBases).toBe(bases.length);

          // totalTerritories deve ser a soma dos territories.length
          const expectedTotalTerritories = bases.reduce(
            (sum, b) => sum + (b.territories ? b.territories.length : 0),
            0,
          );
          expect(kpis.totalTerritories).toBe(expectedTotalTerritories);

          // totalDailyDemand deve ser a soma dos dailyDemand
          const expectedTotalDailyDemand = bases.reduce(
            (sum, b) => sum + (b.dailyDemand || 0),
            0,
          );
          expect(kpis.totalDailyDemand).toBeCloseTo(expectedTotalDailyDemand, 5);

          // avgAttainment deve estar no intervalo [0, 1]
          expect(kpis.avgAttainment).toBeGreaterThanOrEqual(0);
          expect(kpis.avgAttainment).toBeLessThanOrEqual(1);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPRIEDADE 3: getChartDataForBase ordena attainment de forma decrescente
// ---------------------------------------------------------------------------

// Feature: atlas-ux-improvements, Propriedade 3: getChartDataForBase ordena attainment de forma decrescente
describe('reportUtils — Propriedade 3: getChartDataForBase ordena attainment de forma decrescente', () => {
  /**
   * **Validates: Requisito 2.9**
   *
   * Para qualquer array de BaseData, getChartDataForBase(bases, 'all').attainmentByBase.data
   * deve ser não-crescente.
   */
  it('Feature: atlas-ux-improvements, Propriedade 3: attainmentByBase.data é não-crescente', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryBaseData(), { minLength: 0, maxLength: 20 }),
        (bases) => {
          const chartData = getChartDataForBase(bases, 'all');
          const data = chartData.attainmentByBase.data;

          // Verificar que o array é não-crescente
          for (let i = 0; i < data.length - 1; i++) {
            expect(data[i]).toBeGreaterThanOrEqual(data[i + 1]);
          }
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPRIEDADE 4: sortTerritories produz array ordenado
// ---------------------------------------------------------------------------

// Feature: atlas-ux-improvements, Propriedade 4: sortTerritories produz array ordenado
describe('reportUtils — Propriedade 4: sortTerritories produz array ordenado', () => {
  /**
   * **Validates: Requisito 2.11**
   *
   * Para qualquer array de TerritoryRow e coluna numérica válida:
   * - sortTerritories(rows, col, 'asc') produz array não-decrescente
   * - sortTerritories(rows, col, 'desc') produz array não-crescente
   */
  const numericColumns = [
    'dailyDemand',
    'totalSlots',
    'openSlots',
    'active',
    'attainment',
    'accuracy',
  ] as const;

  it('Feature: atlas-ux-improvements, Propriedade 4: sortTerritories asc produz array não-decrescente', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryTerritoryRow(), { minLength: 0, maxLength: 30 }),
        fc.constantFrom(...numericColumns),
        (rows, col) => {
          const sorted = sortTerritories(rows, col, 'asc');

          // Verificar que o array é não-decrescente
          for (let i = 0; i < sorted.length - 1; i++) {
            const va = (sorted[i] as unknown as Record<string, unknown>)[col] as number;
            const vb = (sorted[i + 1] as unknown as Record<string, unknown>)[col] as number;
            expect(va).toBeLessThanOrEqual(vb);
          }
        },
      ),
    );
  });

  it('Feature: atlas-ux-improvements, Propriedade 4: sortTerritories desc produz array não-crescente', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryTerritoryRow(), { minLength: 0, maxLength: 30 }),
        fc.constantFrom(...numericColumns),
        (rows, col) => {
          const sorted = sortTerritories(rows, col, 'desc');

          // Verificar que o array é não-crescente
          for (let i = 0; i < sorted.length - 1; i++) {
            const va = (sorted[i] as unknown as Record<string, unknown>)[col] as number;
            const vb = (sorted[i + 1] as unknown as Record<string, unknown>)[col] as number;
            expect(va).toBeGreaterThanOrEqual(vb);
          }
        },
      ),
    );
  });

  it('Feature: atlas-ux-improvements, Propriedade 4: sortTerritories não muta o array original', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryTerritoryRow(), { minLength: 1, maxLength: 20 }),
        fc.constantFrom(...numericColumns),
        (rows, col) => {
          const original = [...rows];
          sortTerritories(rows, col, 'asc');
          // O array original não deve ser mutado
          expect(rows).toEqual(original);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPRIEDADE 5: getStatusClass respeita os thresholds
// ---------------------------------------------------------------------------

// Feature: atlas-ux-improvements, Propriedade 5: getStatusClass respeita os thresholds
describe('reportUtils — Propriedade 5: getStatusClass respeita os thresholds', () => {
  /**
   * **Validates: Requisito 2.12**
   *
   * Para qualquer v ∈ [0, 1] e thresholds { green, yellow } com green > yellow >= 0:
   * - v >= green → 'status-green'
   * - yellow <= v < green → 'status-yellow'
   * - v < yellow → 'status-red'
   */
  it('Feature: atlas-ux-improvements, Propriedade 5: getStatusClass retorna status correto para cada faixa', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1, noNaN: true }),
        fc
          .tuple(
            fc.float({ min: Math.fround(0.01), max: 1, noNaN: true }),
            fc.float({ min: 0, max: Math.fround(0.99), noNaN: true }),
          )
          .filter(([green, yellow]) => green > yellow),
        (v, [green, yellow]) => {
          const result = getStatusClass(v, { green, yellow });

          if (v >= green) {
            expect(result).toBe('status-green');
          } else if (v >= yellow) {
            expect(result).toBe('status-yellow');
          } else {
            expect(result).toBe('status-red');
          }
        },
      ),
    );
  });
});
