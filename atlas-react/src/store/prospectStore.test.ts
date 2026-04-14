/**
 * prospectStore.test.ts
 * =====================
 * Testes de propriedade para o slice prospectState do store Zustand.
 *
 * Propriedades testadas:
 *   P4 — Round-trip de armazenamento (Validates: Requirements 2.3, 6.2)
 *   P5 — Limpeza em nova busca       (Validates: Requirements 2.6)
 *   P14 — Limpeza total do prospectState (Validates: Requirements 6.4)
 */

import { describe, it, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { useStore } from './index';
import type { ProspectCompany } from './types';

// ---------------------------------------------------------------------------
// Arbitrary para ProspectCompany
// ---------------------------------------------------------------------------

const prospectCompanyArb: fc.Arbitrary<ProspectCompany> = fc.record({
  nome: fc.string(),
  endereco: fc.string(),
  telefone_1: fc.option(fc.string(), { nil: null }),
  telefone_2: fc.option(fc.string(), { nil: null }),
  telefone: fc.option(fc.string(), { nil: null }),
  site: fc.string(),
  google_maps_link: fc.string(),
  cep: fc.string(),
  tipo: fc.string(),
  _fonte: fc.string(),
  lat: fc.option(fc.float({ noNaN: true }), { nil: null }),
  lon: fc.option(fc.float({ noNaN: true }), { nil: null }),
  isMatch: fc.option(fc.boolean(), { nil: null }),
  contactada: fc.boolean(),
  territory_id: fc.option(fc.string(), { nil: undefined }),
});

const prospectCompanyListArb = fc.array(prospectCompanyArb);

// ---------------------------------------------------------------------------
// Reset do store antes de cada teste
// ---------------------------------------------------------------------------

beforeEach(() => {
  useStore.setState({
    prospectState: {
      companies: [],
      clusters: [],
      isLoading: false,
      error: null,
      selectedStation: null,
      selectedBucket: null,
    },
  });
});

// ---------------------------------------------------------------------------
// P4 — Round-trip de armazenamento
// Validates: Requirements 2.3, 6.2
// ---------------------------------------------------------------------------

describe('P4 — Round-trip de armazenamento', () => {
  it('setCompanies(list) → prospectState.companies deve ser igual a list', () => {
    fc.assert(
      fc.property(prospectCompanyListArb, (list) => {
        useStore.getState().setCompanies(list);
        const stored = useStore.getState().prospectState.companies;
        return JSON.stringify(stored) === JSON.stringify(list);
      }),
    );
  });
});

// ---------------------------------------------------------------------------
// P5 — Limpeza em nova busca
// Validates: Requirements 2.6
// ---------------------------------------------------------------------------

describe('P5 — Limpeza em nova busca', () => {
  it('segunda chamada a setCompanies substitui completamente a primeira', () => {
    fc.assert(
      fc.property(
        prospectCompanyListArb,
        prospectCompanyListArb,
        (list1, list2) => {
          useStore.getState().setCompanies(list1);
          useStore.getState().setCompanies(list2);
          const stored = useStore.getState().prospectState.companies;
          return JSON.stringify(stored) === JSON.stringify(list2);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// P14 — Limpeza total do prospectState
// Validates: Requirements 6.4
// ---------------------------------------------------------------------------

describe('P14 — Limpeza total do prospectState', () => {
  it('clearProspect() zera companies, clusters, selectedStation e selectedBucket', () => {
    fc.assert(
      fc.property(prospectCompanyListArb, (list) => {
        // Popula o estado com dados arbitrários
        useStore.setState((state) => ({
          prospectState: {
            ...state.prospectState,
            companies: list,
            clusters: [],
            selectedStation: 'DSP1',
            selectedBucket: 'bucket-a',
          },
        }));

        useStore.getState().clearProspect();

        const { companies, clusters, selectedStation, selectedBucket } =
          useStore.getState().prospectState;

        return (
          companies.length === 0 &&
          clusters.length === 0 &&
          selectedStation === null &&
          selectedBucket === null
        );
      }),
    );
  });
});
