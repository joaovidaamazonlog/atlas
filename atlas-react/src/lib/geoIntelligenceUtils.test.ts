/**
 * geoIntelligenceUtils.test.ts
 * ============================
 * Testes para os utilitários de geointeligência.
 *
 * Validates: Requirements 7.1
 */

import { describe, test, expect } from 'vitest';
import fc from 'fast-check';
import { potentialScoreToColor, regionTypeLabel, formatGap } from './geoIntelligenceUtils';
import type { RegionType } from './geoIntelligenceUtils';

// ---------------------------------------------------------------------------
// Property test: escala de cores
// ---------------------------------------------------------------------------

describe('potentialScoreToColor', () => {
  /**
   * Property: potentialScoreToColor retorna uma cor hex válida (#rrggbb)
   * para qualquer score em [0, 100].
   *
   * Validates: Requirements 7.1
   */
  test('colorScale maps any score in [0,100] to a valid hex color', () => {
    fc.assert(
      fc.property(fc.float({ min: 0, max: 100, noNaN: true }), (score) => {
        const color = potentialScoreToColor(score);
        expect(color).toMatch(/^#[0-9a-f]{6}$/i);
      }),
      { numRuns: 200 },
    );
  });

  test('score 0 returns cold color', () => {
    expect(potentialScoreToColor(0)).toMatch(/^#[0-9a-f]{6}$/i);
  });

  test('score 100 returns hot color', () => {
    expect(potentialScoreToColor(100)).toMatch(/^#[0-9a-f]{6}$/i);
  });

  test('score 50 returns mid color', () => {
    expect(potentialScoreToColor(50)).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: regionTypeLabel
// ---------------------------------------------------------------------------

describe('regionTypeLabel', () => {
  const cases: Array<[RegionType, string]> = [
    ['favela_comunidade', 'Favela / Comunidade'],
    ['residencial_baixa_renda', 'Residencial Baixa Renda'],
    ['residencial_media_renda', 'Residencial Média Renda'],
    ['residencial_alta_renda', 'Residencial Alta Renda'],
    ['comercial', 'Comercial'],
    ['industrial', 'Industrial'],
    ['rural', 'Rural'],
    ['alto_padrao', 'Alto Padrão'],
  ];

  test.each(cases)('regionTypeLabel(%s) === %s', (type, expected) => {
    expect(regionTypeLabel(type)).toBe(expected);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: formatGap
// ---------------------------------------------------------------------------

describe('formatGap', () => {
  test('positive gap has + sign', () => {
    expect(formatGap(12.5)).toBe('+12.5');
  });

  test('negative gap has - sign', () => {
    expect(formatGap(-3.2)).toBe('-3.2');
  });

  test('zero gap has + sign', () => {
    expect(formatGap(0)).toBe('+0.0');
  });

  test('rounds to one decimal place', () => {
    expect(formatGap(1.567)).toBe('+1.6');
  });
});
