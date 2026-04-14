/**
 * kmeansUtils.test.ts
 * ===================
 * Testes de propriedade para kmeansUtils.ts usando fast-check + Vitest.
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { getLeadKey, kmeansCluster } from './kmeansUtils';
import type { ProspectCompany } from '../store/types';

// ---------------------------------------------------------------------------
// ARBITRÁRIOS
// ---------------------------------------------------------------------------

fc.configureGlobal({ numRuns: 100 });

/** Gera uma string não vazia e diferente de 'N/A' para simular um google_maps_link válido. */
const validGoogleMapsLink = (): fc.Arbitrary<string> =>
  fc.string({ minLength: 1, maxLength: 80 }).filter((s) => s !== 'N/A');

/** Gera uma ProspectCompany mínima com campos controláveis. */
const arbitraryCompany = (
  overrides: Partial<{
    google_maps_link: fc.Arbitrary<string>;
    lat: fc.Arbitrary<number | null>;
    lon: fc.Arbitrary<number | null>;
    isMatch: fc.Arbitrary<boolean | null>;
  }> = {}
): fc.Arbitrary<ProspectCompany> =>
  fc.record({
    nome: fc.string({ minLength: 1, maxLength: 40 }),
    endereco: fc.string({ minLength: 1, maxLength: 80 }),
    telefone_1: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    telefone_2: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    telefone: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    site: fc.string({ minLength: 0, maxLength: 40 }),
    google_maps_link: overrides.google_maps_link ?? fc.string({ minLength: 0, maxLength: 80 }),
    cep: fc.string({ minLength: 8, maxLength: 9 }),
    tipo: fc.string({ minLength: 1, maxLength: 20 }),
    _fonte: fc.string({ minLength: 1, maxLength: 20 }),
    lat: overrides.lat ?? fc.option(fc.float({ min: -90, max: 90, noNaN: true }), { nil: null }),
    lon: overrides.lon ?? fc.option(fc.float({ min: -180, max: 180, noNaN: true }), { nil: null }),
    isMatch: overrides.isMatch ?? fc.option(fc.boolean(), { nil: null }),
    contactada: fc.boolean(),
    territory_id: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
  });

/** Gera uma empresa com coordenadas válidas (lat e lon não nulos). */
const arbitraryCompanyWithCoords = (): fc.Arbitrary<ProspectCompany> =>
  arbitraryCompany({
    lat: fc.float({ min: -90, max: 90, noNaN: true }),
    lon: fc.float({ min: -180, max: 180, noNaN: true }),
  });

/** Gera uma empresa sem coordenadas. */
const arbitraryCompanyWithoutCoords = (): fc.Arbitrary<ProspectCompany> =>
  arbitraryCompany({
    lat: fc.constant(null),
    lon: fc.constant(null),
  });

// ---------------------------------------------------------------------------
// PROPERTY 10: lead_key correto
// ---------------------------------------------------------------------------

describe('kmeansUtils — Property 10: lead_key calculado corretamente', () => {
  /**
   * **Validates: Requirements 3.14, 3.16**
   *
   * Para qualquer ProspectCompany, getLeadKey deve retornar google_maps_link
   * quando esse campo é não nulo e diferente de 'N/A', e "${nome}|${endereco}"
   * caso contrário.
   */
  it('Feature: prospect-ux-redesign, Property 10: retorna google_maps_link quando válido', () => {
    fc.assert(
      fc.property(
        arbitraryCompany({ google_maps_link: validGoogleMapsLink() }),
        (company) => {
          const key = getLeadKey(company);
          expect(key).toBe(company.google_maps_link);
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 10: retorna "nome|endereco" quando google_maps_link é N/A', () => {
    fc.assert(
      fc.property(
        arbitraryCompany({ google_maps_link: fc.constant('N/A') }),
        (company) => {
          const key = getLeadKey(company);
          expect(key).toBe(`${company.nome}|${company.endereco}`);
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 10: retorna "nome|endereco" quando google_maps_link é string vazia', () => {
    fc.assert(
      fc.property(
        arbitraryCompany({ google_maps_link: fc.constant('') }),
        (company) => {
          const key = getLeadKey(company);
          expect(key).toBe(`${company.nome}|${company.endereco}`);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPERTY 12: K-means produz min(n, 4) clusters
// ---------------------------------------------------------------------------

describe('kmeansUtils — Property 12: K-means produz exatamente min(n, 4) clusters', () => {
  /**
   * **Validates: Requirements 4.1, 4.2**
   *
   * Para qualquer lista com n empresas com coordenadas válidas,
   * kmeansCluster deve retornar exatamente min(n, 4) clusters,
   * cada um com count > 0.
   */
  it('Feature: prospect-ux-redesign, Property 12: n=0 retorna []', () => {
    const result = kmeansCluster([]);
    expect(result).toEqual([]);
  });

  it('Feature: prospect-ux-redesign, Property 12: lista sem coordenadas retorna []', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithoutCoords(), { minLength: 1, maxLength: 20 }),
        (companies) => {
          const result = kmeansCluster(companies);
          expect(result).toEqual([]);
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 12: produz min(n, 4) clusters com count > 0', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 1, maxLength: 30 }),
        (companies) => {
          const n = companies.length;
          const expectedK = Math.min(n, 4);
          const result = kmeansCluster(companies, 4);

          expect(result.length).toBe(expectedK);
          for (const cluster of result) {
            expect(cluster.count).toBeGreaterThan(0);
          }
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 12: empresas sem coordenadas não afetam o número de clusters', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 1, maxLength: 20 }),
        fc.array(arbitraryCompanyWithoutCoords(), { minLength: 0, maxLength: 10 }),
        (withCoords, withoutCoords) => {
          const companies = [...withCoords, ...withoutCoords];
          const n = withCoords.length;
          const expectedK = Math.min(n, 4);
          const result = kmeansCluster(companies, 4);

          expect(result.length).toBe(expectedK);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// PROPERTY 13: Invariantes dos clusters K-means
// ---------------------------------------------------------------------------

describe('kmeansUtils — Property 13: Invariantes dos clusters K-means', () => {
  /**
   * **Validates: Requirements 4.3, 4.4, 4.5**
   *
   * Para qualquer resultado de kmeansCluster:
   * - Soma de count == número de empresas com coordenadas válidas
   * - match_count <= count para cada cluster
   * - Cluster com priority === 1 tem intensity === 1.0
   * - Intensidades são não-crescentes por ordem de prioridade
   */
  it('Feature: prospect-ux-redesign, Property 13: soma de count == n empresas com coordenadas', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompany(), { minLength: 0, maxLength: 30 }),
        (companies) => {
          const validCount = companies.filter(
            (c) => c.lat != null && c.lon != null,
          ).length;
          const result = kmeansCluster(companies, 4);
          const totalCount = result.reduce((sum, cl) => sum + cl.count, 0);
          expect(totalCount).toBe(validCount);
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 13: match_count <= count para cada cluster', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 1, maxLength: 30 }),
        (companies) => {
          const result = kmeansCluster(companies, 4);
          for (const cluster of result) {
            expect(cluster.match_count).toBeLessThanOrEqual(cluster.count);
          }
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 13: cluster com priority === 1 tem intensity === 1.0', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 1, maxLength: 30 }),
        (companies) => {
          const result = kmeansCluster(companies, 4);
          const top = result.find((cl) => cl.priority === 1);
          if (top) {
            expect(top.intensity).toBe(1.0);
          }
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 13: intensidades são não-crescentes por prioridade', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 2, maxLength: 30 }),
        (companies) => {
          const result = kmeansCluster(companies, 4);
          // Ordenar por prioridade para garantir a ordem correta
          const sorted = [...result].sort((a, b) => a.priority - b.priority);
          for (let i = 0; i < sorted.length - 1; i++) {
            expect(sorted[i].intensity).toBeGreaterThanOrEqual(sorted[i + 1].intensity);
          }
        },
      ),
    );
  });

  it('Feature: prospect-ux-redesign, Property 13: todas as invariantes simultaneamente', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompany(), { minLength: 0, maxLength: 30 }),
        (companies) => {
          const validCount = companies.filter(
            (c) => c.lat != null && c.lon != null,
          ).length;
          const result = kmeansCluster(companies, 4);

          // Invariante 1: soma de count
          const totalCount = result.reduce((sum, cl) => sum + cl.count, 0);
          expect(totalCount).toBe(validCount);

          // Invariante 2: match_count <= count
          for (const cluster of result) {
            expect(cluster.match_count).toBeLessThanOrEqual(cluster.count);
          }

          if (result.length > 0) {
            // Invariante 3: priority 1 → intensity 1.0
            const top = result.find((cl) => cl.priority === 1)!;
            expect(top.intensity).toBe(1.0);

            // Invariante 4: intensidades não-crescentes
            const sorted = [...result].sort((a, b) => a.priority - b.priority);
            for (let i = 0; i < sorted.length - 1; i++) {
              expect(sorted[i].intensity).toBeGreaterThanOrEqual(sorted[i + 1].intensity);
            }
          }
        },
      ),
    );
  });
});
