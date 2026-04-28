/**
 * areaAnalysis.pure.test.ts
 * =========================
 * Property-based tests (fast-check) sobre as funções puras extraídas
 * de `AreaAnalysisTab.tsx`.
 *
 * Valida:
 * - `getGlobalOverview: go + nogo === total` (soma das decisões cobertas).
 * - `getFilteredStats: go + nogo === total` e `∑ nogoReasonRows.count ≤ nogo`.
 * - `getStatsByState: ∑(go + nogo) por UF === número de prospects com
 *    decision definida`.
 * - Invariantes de formato: `rate` é string com ponto decimal (toFixed);
 *    nenhum campo fica NaN ou undefined.
 *
 * Referências: Requirements 6.1, 6.7, 6.9
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { Partner } from '../../store/types';
import {
  getGlobalOverview,
  getFilteredStats,
  getStatsByState,
  NO_GO_REASONS,
} from '../../lib/areaAnalysisPure';

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------

const partnerArb = (): fc.Arbitrary<Partner> =>
  fc.record({
    salesforce_id: fc.string({ minLength: 1, maxLength: 15 }),
    store_id: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    name: fc.string({ minLength: 1, maxLength: 30 }),
    status: fc.constantFrom('Active', 'Prospect', 'Inactive', 'Onboarding', 'BG Checks', 'Exited', 'New'),
    lead_source: fc.option(fc.string(), { nil: null }),
    lat: fc.option(fc.float({ min: -33, max: 5, noNaN: true }), { nil: null }),
    lon: fc.option(fc.float({ min: -73, max: -34, noNaN: true }), { nil: null }),
    zip_code: fc.option(fc.string(), { nil: null }),
    city: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    state: fc.option(fc.string({ minLength: 2, maxLength: 2 }), { nil: null }),
    delivery_station: fc.string({ minLength: 1, maxLength: 10 }),
    supply_run: fc.option(fc.string(), { nil: null }),
    radius: fc.integer({ min: 100, max: 5000 }),
    capacity: fc.integer({ min: 1, max: 200 }),
    bucket: fc.option(fc.string(), { nil: null }),
    jurisdiction_type: fc.option(fc.string(), { nil: null }),
    hub_delivey_initiatives: fc.option(fc.string(), { nil: null }),
    HCP_rate_card: fc.option(fc.string(), { nil: null }),
    HCP_host_partner: fc.option(fc.string(), { nil: null }),
    launch_date: fc.option(fc.string(), { nil: null }),
    exited_date: fc.option(fc.string(), { nil: null }),
    decision: fc.option(
      fc.constantFrom('Go', 'No Go'),
      { nil: undefined },
    ),
    reason: fc.option(
      fc.constantFrom(
        'Sem oportunidade próxima',
        'Fora de jurisdição',
        'Não avaliado por falta de coordenadas',
        'Seguir cadastro',
      ),
      { nil: undefined },
    ),
    bucket_ade: fc.option(fc.string(), { nil: null }),
    tooltip: fc.string(),
    decision_status: fc.option(fc.string(), { nil: null }),
    decision_reason_code: fc.option(fc.string(), { nil: null }),
    telefone: fc.option(fc.string(), { nil: null }),
    owner_id: fc.option(fc.string(), { nil: null }),
    adv_opportunity: fc.option(fc.anything(), { nil: null }),
  }) as unknown as fc.Arbitrary<Partner>;

// ---------------------------------------------------------------------------
// getGlobalOverview
// ---------------------------------------------------------------------------

describe('getGlobalOverview', () => {
  it('go + nogo === total evaluated', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const o = getGlobalOverview(data);
        expect(o.go + o.nogo).toBe(o.total);
      }),
    );
  });

  it('noCoords é contado entre prospects sem lat/lon', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const o = getGlobalOverview(data);
        const expected = data.filter(
          (p) => p.status === 'Prospect' && (!p.lat || !p.lon),
        ).length;
        expect(o.noCoords).toBe(expected);
      }),
    );
  });

  it('nogoReasonCounts tem todas as chaves NO_GO_REASONS', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 50 }), (data) => {
        const o = getGlobalOverview(data);
        for (const reason of NO_GO_REASONS) {
          expect(o.nogoReasonCounts).toHaveProperty(reason);
          expect(typeof o.nogoReasonCounts[reason]).toBe('number');
        }
      }),
    );
  });

  it('rate é string no formato "NN.N" quando há evaluated', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 50 }), (data) => {
        const o = getGlobalOverview(data);
        expect(typeof o.rate).toBe('string');
        expect(o.rate).toMatch(/^\d+\.\d$/);
      }),
    );
  });

  it('lista vazia → total=0, go=0, nogo=0, rate="0.0"', () => {
    const o = getGlobalOverview([]);
    expect(o.total).toBe(0);
    expect(o.go).toBe(0);
    expect(o.nogo).toBe(0);
    expect(o.rate).toBe('0.0');
  });
});

// ---------------------------------------------------------------------------
// getFilteredStats
// ---------------------------------------------------------------------------

describe('getFilteredStats', () => {
  it('go + nogo === total', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const s = getFilteredStats(prospects);
        expect(s.go + s.nogo).toBe(s.total);
      }),
    );
  });

  it('soma de nogoReasonRows.count ≤ nogo', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const s = getFilteredStats(prospects);
        const sum = s.nogoReasonRows.reduce((a, r) => a + r.count, 0);
        expect(sum).toBeLessThanOrEqual(s.nogo);
      }),
    );
  });

  it('nogoReasonRows tem exatamente NO_GO_REASONS.length entradas, na ordem', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 50 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const s = getFilteredStats(prospects);
        expect(s.nogoReasonRows.length).toBe(NO_GO_REASONS.length);
        s.nogoReasonRows.forEach((row, i) => {
          expect(row.reason).toBe(NO_GO_REASONS[i]);
        });
      }),
    );
  });

  it('lista vazia → zeros e rate "0.0"', () => {
    const s = getFilteredStats([]);
    expect(s.total).toBe(0);
    expect(s.go).toBe(0);
    expect(s.nogo).toBe(0);
    expect(s.rate).toBe('0.0');
  });
});

// ---------------------------------------------------------------------------
// getStatsByState
// ---------------------------------------------------------------------------

describe('getStatsByState', () => {
  it('soma de (go + nogo) por UF === len(prospects com decision)', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const rows = getStatsByState(prospects);
        const sum = rows.reduce((a, r) => a + r.go + r.nogo, 0);
        expect(sum).toBe(prospects.length);
      }),
    );
  });

  it('sempre ordenado por total desc', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 100 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const rows = getStatsByState(prospects);
        for (let i = 0; i < rows.length - 1; i++) {
          expect(rows[i].total).toBeGreaterThanOrEqual(rows[i + 1].total);
        }
      }),
    );
  });

  it('prospects sem state usam "N/A"', () => {
    const prospects: Partner[] = [
      { status: 'Prospect', decision: 'Go', state: null } as unknown as Partner,
      { status: 'Prospect', decision: 'No Go', state: null } as unknown as Partner,
      { status: 'Prospect', decision: 'Go', state: 'SP' } as unknown as Partner,
    ];
    const rows = getStatsByState(prospects);
    const byUf = new Map(rows.map((r) => [r.uf, r]));
    expect(byUf.get('N/A')?.total).toBe(2);
    expect(byUf.get('SP')?.total).toBe(1);
  });

  it('rate é calculado por UF como string inteira', () => {
    fc.assert(
      fc.property(fc.array(partnerArb(), { maxLength: 50 }), (data) => {
        const prospects = data.filter((p) => p.status === 'Prospect' && p.decision);
        const rows = getStatsByState(prospects);
        for (const r of rows) {
          expect(typeof r.rate).toBe('string');
          // rate é formatado com toFixed(0) → "NN"
          expect(r.rate).toMatch(/^\d+$/);
        }
      }),
    );
  });

  it('lista vazia → []', () => {
    expect(getStatsByState([])).toEqual([]);
  });
});
