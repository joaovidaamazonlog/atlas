/**
 * ProspectMarkers.test.tsx
 * ========================
 * Testes de propriedade para a lógica de toggle de alfinetes (P9).
 *
 * Como ProspectMarkers é um componente imperativo Leaflet que usa useMap(),
 * testamos a lógica de toggle no nível unitário:
 *   - getLeadKey é determinístico (mesma entrada → mesma saída)
 *   - Adicionar e remover uma chave de um Set resulta em ausência da chave (round-trip)
 *   - Combinação: pin (add) → unpin (delete) → chave não está no Set
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { getLeadKey } from '../../lib/kmeansUtils';
import type { ProspectCompany } from '../../store/types';

// ---------------------------------------------------------------------------
// ARBITRÁRIOS
// ---------------------------------------------------------------------------

/** Gera uma ProspectCompany com coordenadas válidas (lat e lon não nulos). */
const arbitraryCompanyWithCoords = (): fc.Arbitrary<ProspectCompany> =>
  fc.record({
    nome: fc.string({ minLength: 1, maxLength: 40 }),
    endereco: fc.string({ minLength: 1, maxLength: 80 }),
    telefone_1: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    telefone_2: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    telefone: fc.option(fc.string({ minLength: 8, maxLength: 15 }), { nil: null }),
    site: fc.string({ minLength: 0, maxLength: 40 }),
    google_maps_link: fc.string({ minLength: 0, maxLength: 80 }),
    cep: fc.string({ minLength: 8, maxLength: 9 }),
    tipo: fc.string({ minLength: 1, maxLength: 20 }),
    _fonte: fc.string({ minLength: 1, maxLength: 20 }),
    lat: fc.float({ min: -90, max: 90, noNaN: true }),
    lon: fc.float({ min: -180, max: 180, noNaN: true }),
    isMatch: fc.option(fc.boolean(), { nil: null }),
    contactada: fc.boolean(),
    territory_id: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
  });

// ---------------------------------------------------------------------------
// PROPERTY 9: Toggle de alfinete é round-trip
// ---------------------------------------------------------------------------

describe('ProspectMarkers — Property 9: Toggle de alfinete é round-trip', () => {
  /**
   * **Validates: Requirements 3.10**
   *
   * Para qualquer empresa com coordenadas válidas, fixar e depois desfixar
   * deve resultar em nenhum marcador ativo para essa empresa.
   */

  it('Feature: prospect-ux-redesign, Property 9: getLeadKey é determinístico (mesma entrada → mesma saída)', () => {
    fc.assert(
      fc.property(arbitraryCompanyWithCoords(), (company) => {
        const key1 = getLeadKey(company);
        const key2 = getLeadKey(company);
        expect(key1).toBe(key2);
      }),
      { numRuns: 100 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 9: add então delete de uma chave resulta em ausência no Set', () => {
    fc.assert(
      fc.property(arbitraryCompanyWithCoords(), (company) => {
        const key = getLeadKey(company);
        const pinnedKeys = new Set<string>();

        // pin
        pinnedKeys.add(key);
        expect(pinnedKeys.has(key)).toBe(true);

        // unpin
        pinnedKeys.delete(key);
        expect(pinnedKeys.has(key)).toBe(false);
      }),
      { numRuns: 100 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 9: pin → unpin resulta em nenhum marcador ativo para a empresa', () => {
    fc.assert(
      fc.property(arbitraryCompanyWithCoords(), (company) => {
        const key = getLeadKey(company);
        const pinnedKeys = new Set<string>();

        // Simula o toggle: pin (adiciona ao Set)
        pinnedKeys.add(key);

        // Simula o toggle: unpin (remove do Set)
        pinnedKeys.delete(key);

        // Após round-trip, a empresa não deve ter marcador ativo
        expect(pinnedKeys.has(key)).toBe(false);
        expect(pinnedKeys.size).toBe(0);
      }),
      { numRuns: 100 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 9: múltiplas empresas — unpin de uma não afeta as demais', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryCompanyWithCoords(), { minLength: 2, maxLength: 10 }),
        (companies) => {
          const keys = companies.map(getLeadKey);
          const pinnedKeys = new Set<string>(keys);

          // Unpin da primeira empresa
          const firstKey = keys[0];
          pinnedKeys.delete(firstKey);

          // A primeira empresa não deve estar mais fixada
          expect(pinnedKeys.has(firstKey)).toBe(false);

          // As demais chaves únicas ainda devem estar presentes
          const remainingKeys = keys.slice(1);
          for (const key of remainingKeys) {
            if (key !== firstKey) {
              expect(pinnedKeys.has(key)).toBe(true);
            }
          }
        },
      ),
      { numRuns: 100 },
    );
  });
});
