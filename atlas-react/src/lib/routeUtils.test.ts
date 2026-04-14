/**
 * routeUtils.test.ts
 * ==================
 * Testes de propriedade para routeUtils.ts.
 *
 * // Feature: atlas-ux-improvements, Propriedade 7: optimizeStops produz rota de distância mínima
 *
 * **Validates: Requirements 7.3**
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { optimizeStops } from './routeUtils';
import type { RouteStop } from '../store/types';

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

const R = 6371000; // raio da Terra em metros

function haversineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function totalDistance(from: RouteStop, to: RouteStop, order: RouteStop[]): number {
  let d = 0;
  let prev = from;
  for (const stop of order) {
    d += haversineDistance(prev.lat, prev.lon, stop.lat, stop.lon);
    prev = stop;
  }
  d += haversineDistance(prev.lat, prev.lon, to.lat, to.lon);
  return d;
}

/** Gera todas as permutações de um array. */
function permute<T>(arr: T[]): T[][] {
  if (arr.length <= 1) return [arr];
  return arr.flatMap((v, i) =>
    permute([...arr.slice(0, i), ...arr.slice(i + 1)]).map((r) => [v, ...r]),
  );
}

// ---------------------------------------------------------------------------
// ARBITRÁRIOS
// ---------------------------------------------------------------------------

const arbitraryRouteStop = (): fc.Arbitrary<RouteStop> =>
  fc.record({
    store_id: fc.string({ minLength: 1, maxLength: 10 }),
    name: fc.string({ minLength: 1, maxLength: 30 }),
    lat: fc.float({ min: -90, max: 90, noNaN: true }),
    lon: fc.float({ min: -180, max: 180, noNaN: true }),
  });

// ---------------------------------------------------------------------------
// TESTES DE PROPRIEDADE
// ---------------------------------------------------------------------------

fc.configureGlobal({ numRuns: 100 });

describe('routeUtils — Propriedade 7: optimizeStops produz rota de distância mínima', () => {
  /**
   * **Validates: Requirements 7.3**
   *
   * Para qualquer origem, destino e até 8 paradas intermediárias,
   * a distância total da rota retornada por optimizeStops deve ser ≤
   * à distância de qualquer outra permutação das mesmas paradas.
   */
  it('Feature: atlas-ux-improvements, Propriedade 7: optimizeStops retorna a permutação de distância mínima', () => {
    fc.assert(
      fc.property(
        arbitraryRouteStop(),
        arbitraryRouteStop(),
        fc.array(arbitraryRouteStop(), { minLength: 0, maxLength: 8 }),
        (from, to, stops) => {
          const optimized = optimizeStops(from, to, stops);

          // A distância da rota otimizada
          const optimizedDist = totalDistance(from, to, optimized);

          // Verificar contra todas as permutações possíveis
          const allPerms = permute(stops);
          for (const perm of allPerms) {
            const permDist = totalDistance(from, to, perm);
            // A rota otimizada deve ser ≤ qualquer permutação
            expect(optimizedDist).toBeLessThanOrEqual(permDist + 1e-9); // tolerância numérica
          }
        },
      ),
    );
  });

  it('Feature: atlas-ux-improvements, Propriedade 7: optimizeStops com 0 paradas retorna array vazio', () => {
    fc.assert(
      fc.property(
        arbitraryRouteStop(),
        arbitraryRouteStop(),
        (from, to) => {
          const result = optimizeStops(from, to, []);
          expect(result).toHaveLength(0);
        },
      ),
    );
  });

  it('Feature: atlas-ux-improvements, Propriedade 7: optimizeStops com 1 parada retorna a mesma parada', () => {
    fc.assert(
      fc.property(
        arbitraryRouteStop(),
        arbitraryRouteStop(),
        arbitraryRouteStop(),
        (from, to, stop) => {
          const result = optimizeStops(from, to, [stop]);
          expect(result).toHaveLength(1);
          expect(result[0]).toEqual(stop);
        },
      ),
    );
  });

  it('Feature: atlas-ux-improvements, Propriedade 7: optimizeStops retorna todas as paradas originais (sem perder nem duplicar)', () => {
    fc.assert(
      fc.property(
        arbitraryRouteStop(),
        arbitraryRouteStop(),
        fc.array(arbitraryRouteStop(), { minLength: 2, maxLength: 8 }),
        (from, to, stops) => {
          const result = optimizeStops(from, to, stops);
          expect(result).toHaveLength(stops.length);
          // Cada parada original deve aparecer exatamente uma vez no resultado
          for (const stop of stops) {
            const count = result.filter((r) => r === stop).length;
            expect(count).toBe(1);
          }
        },
      ),
    );
  });
});
