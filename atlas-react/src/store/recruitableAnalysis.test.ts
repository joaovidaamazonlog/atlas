/**
 * recruitableAnalysis.test.ts
 * ===========================
 * Testes de propriedade para o slice recruitableAnalysis do store Zustand.
 *
 * Propriedades testadas:
 *   Property 8 — Limpeza preserva configuração (Validates: Requirements 8.2, 8.3)
 *   Property 9 — Alteração de parâmetro invalida resultado (Validates: Requirements 8.4)
 */

import { describe, it, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { useStore } from './index';
import type { EvaluatorResult, RecruitableAnalysisParams } from './types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Cria um EvaluatorResult mínimo válido para popular o store. */
function makeResult(overrides: Partial<EvaluatorResult> = {}): EvaluatorResult {
  return {
    totalDemand: 100,
    residualDemand: 50,
    minAdv: 40,
    gap: 10,
    viable: true,
    reason: null,
    selectedCells: [],
    residualCells: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Reset do store antes de cada teste
// ---------------------------------------------------------------------------

beforeEach(() => {
  useStore.setState((state) => ({
    recruitableAnalysis: {
      ...state.recruitableAnalysis,
      params: {
        minAdv: 40,
        radiusMeters: 1500,
        centerLat: '',
        centerLon: '',
        selectedLeadId: null,
      },
      result: null,
      error: null,
      isStale: false,
    },
  }));
});

// ---------------------------------------------------------------------------
// Property 8 — Limpeza preserva configuração
// Validates: Requirements 8.2, 8.3
// ---------------------------------------------------------------------------

describe('Property 8 — Limpeza preserva configuração', () => {
  it('clearRecruitableAnalysis preserva minAdv e radiusMeters, limpa o restante', () => {
    // Feature: recruitable-area-analysis, Property 8: Limpeza preserva configuração
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 500 }),    // minAdv
        fc.integer({ min: 100, max: 10000 }), // radiusMeters
        fc.string(),                           // centerLat arbitrário
        fc.string(),                           // centerLon arbitrário
        fc.option(fc.string(), { nil: null }), // selectedLeadId
        (minAdv, radiusMeters, centerLat, centerLon, selectedLeadId) => {
          // Configura estado com valores arbitrários e um resultado existente
          useStore.setState((state) => ({
            recruitableAnalysis: {
              ...state.recruitableAnalysis,
              params: { minAdv, radiusMeters, centerLat, centerLon, selectedLeadId },
              result: makeResult({ minAdv }),
              error: 'algum erro',
              isStale: true,
            },
          }));

          useStore.getState().clearRecruitableAnalysis();

          const { params, result, error, isStale } =
            useStore.getState().recruitableAnalysis;

          return (
            params.minAdv === minAdv &&
            params.radiusMeters === radiusMeters &&
            params.centerLat === '' &&
            params.centerLon === '' &&
            params.selectedLeadId === null &&
            result === null &&
            error === null &&
            isStale === false
          );
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 9 — Alteração de parâmetro invalida resultado
// Validates: Requirements 8.4
// ---------------------------------------------------------------------------

describe('Property 9 — Alteração de parâmetro invalida resultado', () => {
  it('setRecruitableParams com resultado existente marca isStale: true', () => {
    // Feature: recruitable-area-analysis, Property 9: Alteração de parâmetro invalida resultado
    fc.assert(
      fc.property(
        fc.record({
          minAdv: fc.option(fc.integer({ min: 1, max: 500 }), { nil: undefined }),
          radiusMeters: fc.option(fc.integer({ min: 100, max: 10000 }), { nil: undefined }),
          centerLat: fc.option(fc.string(), { nil: undefined }),
          centerLon: fc.option(fc.string(), { nil: undefined }),
          selectedLeadId: fc.option(fc.option(fc.string(), { nil: null }), { nil: undefined }),
        }),
        (paramUpdate) => {
          // Garante que há pelo menos um campo no update
          const hasAnyField = Object.values(paramUpdate).some((v) => v !== undefined);
          if (!hasAnyField) return true; // skip trivial case

          // Popula o store com um resultado existente
          useStore.setState((state) => ({
            recruitableAnalysis: {
              ...state.recruitableAnalysis,
              result: makeResult(),
              isStale: false,
            },
          }));

          useStore.getState().setRecruitableParams(
            paramUpdate as Partial<RecruitableAnalysisParams>,
          );

          return useStore.getState().recruitableAnalysis.isStale === true;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('setRecruitableParams sem resultado existente não altera isStale', () => {
    // Feature: recruitable-area-analysis, Property 9 (complemento): sem resultado, isStale permanece false
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 500 }),
        (minAdv) => {
          // Garante que não há resultado
          useStore.setState((state) => ({
            recruitableAnalysis: {
              ...state.recruitableAnalysis,
              result: null,
              isStale: false,
            },
          }));

          useStore.getState().setRecruitableParams({ minAdv });

          return useStore.getState().recruitableAnalysis.isStale === false;
        },
      ),
      { numRuns: 100 },
    );
  });
});
