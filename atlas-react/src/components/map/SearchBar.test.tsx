/**
 * SearchBar.test.tsx
 * ==================
 * Testes unitários para o componente SearchBar.
 *
 * **Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.10**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent, waitFor, act } from '@testing-library/react';
import { SearchBar } from './SearchBar';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

vi.mock('react-leaflet', () => ({
  useMap: () => ({ flyTo: vi.fn() }),
  MapContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

vi.mock('../../hooks/useDebounce', () => ({
  useDebounce: <T,>(value: T) => value,
}));

vi.mock('../../hooks/useBreakpoint', () => ({
  useBreakpoint: () => 'desktop',
}));

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function makePartner(overrides: Partial<Partner> = {}): Partner {
  return {
    salesforce_id: 'sf-1',
    store_id: null,
    name: 'Parceiro Teste',
    status: 'Active',
    lat: -23.5,
    lon: -46.6,
    zip_code: null,
    city: 'São Paulo',
    state: 'SP',
    delivery_station: 'GRU1',
    supply_run: null,
    radius: 5,
    capacity: 100,
    bucket: null,
    bucket_ade: '',
    jurisdiction_type: null,
    hub_delivey_initiatives: null,
    HCP_rate_card: null,
    HCP_host_partner: null,
    launch_date: null,
    exited_date: null,
    telefone: null,
    owner_id: null,
    decision_status: null,
    lead_source: null,
    tooltip: '',
    regiao: '',
    decision: '',
    reason: '',
    optimization: { radius_suggestion: 0, cap_suggestion: 0 },
    ceps: [],
    slot_id: '',
    ...overrides,
  };
}

const PARTNERS: Partner[] = [
  makePartner({ salesforce_id: 'sf-1', name: 'Alpha Logística', lat: -23.5, lon: -46.6 }),
  makePartner({ salesforce_id: 'sf-2', name: 'Beta Transportes', lat: -22.9, lon: -43.1 }),
  makePartner({ salesforce_id: 'sf-3', name: 'Gamma Express', lat: -19.9, lon: -43.9 }),
];

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

describe('SearchBar', () => {
  let flyToRef: React.MutableRefObject<((lat: number, lon: number) => void) | null>;

  beforeEach(() => {
    flyToRef = { current: vi.fn() };
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // 1. Renderiza o input de busca
  it('renderiza o input de busca', () => {
    const { getByRole } = render(<SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />);
    const input = getByRole('textbox', { name: /buscar parceiro/i });
    expect(input).toBeTruthy();
  });

  // 2. Exibe sugestões quando query >= 2 chars e há matches
  it('exibe sugestões de autocomplete quando query tem >= 2 caracteres e há correspondências', async () => {
    const { getByRole, getByText } = render(
      <SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Al' } });
    });

    await waitFor(() => {
      expect(getByText('Alpha Logística')).toBeTruthy();
    });
  });

  // 3. Filtra apenas parceiros cujo nome contém a query (case-insensitive)
  it('exibe apenas parceiros cujo nome contém a query (case-insensitive)', async () => {
    const { getByRole, queryByText } = render(
      <SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'beta' } });
    });

    await waitFor(() => {
      expect(queryByText('Beta Transportes')).toBeTruthy();
      expect(queryByText('Alpha Logística')).toBeNull();
      expect(queryByText('Gamma Express')).toBeNull();
    });
  });

  // 4. Chama flyToRef.current com coordenadas corretas ao selecionar sugestão
  it('chama flyToRef.current com coordenadas corretas ao clicar em sugestão', async () => {
    const { getByRole, getByText } = render(
      <SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Alpha' } });
    });

    await waitFor(() => expect(getByText('Alpha Logística')).toBeTruthy());

    await act(async () => {
      fireEvent.mouseDown(getByText('Alpha Logística'));
    });

    expect(flyToRef.current).toHaveBeenCalledWith(-23.5, -46.6);
  });

  // 5. Exibe mensagem de erro quando geocodificação retorna array vazio
  it('exibe mensagem de erro quando geocodificação retorna vazio', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    const { getByRole, findByRole } = render(
      <SearchBar partners={[]} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'endereço inexistente' } });
      fireEvent.keyDown(input, { key: 'Enter' });
    });

    const alert = await findByRole('alert');
    expect(alert.textContent).toContain('não encontrado');
  });

  // 6. Fecha o autocomplete ao pressionar Escape
  it('fecha o autocomplete ao pressionar Escape', async () => {
    const { getByRole, queryByRole } = render(
      <SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'Alpha' } });
    });

    await waitFor(() => expect(queryByRole('listbox')).toBeTruthy());

    await act(async () => {
      fireEvent.keyDown(input, { key: 'Escape' });
    });

    expect(queryByRole('listbox')).toBeNull();
  });

  // 7. NÃO exibe sugestões quando query < 2 chars
  it('não exibe sugestões quando query tem menos de 2 caracteres', async () => {
    const { getByRole, queryByRole } = render(
      <SearchBar partners={PARTNERS} flyToRef={flyToRef} breakpoint="desktop" />
    );
    const input = getByRole('textbox');

    await act(async () => {
      fireEvent.change(input, { target: { value: 'A' } });
    });

    expect(queryByRole('listbox')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// LÓGICA PURA DE FILTRAGEM (extraída do componente para testes de propriedade)
// ---------------------------------------------------------------------------

/**
 * Replica exatamente a lógica de filtragem do SearchBar:
 *   partners.filter(p => p.name.toLowerCase().includes(lower) && p.lat != null && p.lon != null)
 */
function filterPartners(partners: Partner[], query: string): Partner[] {
  if (query.length < 2) return [];
  const lower = query.toLowerCase();
  return partners.filter(
    (p) => p.name.toLowerCase().includes(lower) && p.lat != null && p.lon != null
  );
}

// ---------------------------------------------------------------------------
// TESTES DE PROPRIEDADE — Propriedade 6: Autocomplete retorna subconjunto válido
// Feature: atlas-ux-improvements, Propriedade 6: Autocomplete retorna subconjunto válido
// Valida: Requisito 1.4
// ---------------------------------------------------------------------------

import * as fc from 'fast-check';

describe('SearchBar — Propriedade 6: Autocomplete retorna subconjunto válido (PBT)', () => {
  // Gerador de Partner arbitrário
  const arbPartner = fc.record({
    salesforce_id: fc.string({ minLength: 1, maxLength: 20 }),
    store_id: fc.constant(null),
    name: fc.string({ minLength: 1, maxLength: 60 }),
    status: fc.constant('Active' as const),
    lat: fc.oneof(fc.double({ min: -90, max: 90, noNaN: true }), fc.constant(null)),
    lon: fc.oneof(fc.double({ min: -180, max: 180, noNaN: true }), fc.constant(null)),
    zip_code: fc.constant(null),
    city: fc.constant(null),
    state: fc.constant(null),
    delivery_station: fc.constant('GRU1'),
    supply_run: fc.constant(null),
    radius: fc.constant(5),
    capacity: fc.constant(100),
    bucket: fc.constant(null),
    bucket_ade: fc.constant(''),
    jurisdiction_type: fc.constant(null),
    hub_delivey_initiatives: fc.constant(null),
    HCP_rate_card: fc.constant(null),
    HCP_host_partner: fc.constant(null),
    launch_date: fc.constant(null),
    exited_date: fc.constant(null),
    telefone: fc.constant(null),
    owner_id: fc.constant(null),
    decision_status: fc.constant(null),
    lead_source: fc.constant(null),
    tooltip: fc.constant(''),
    regiao: fc.constant(''),
    decision: fc.constant(''),
    reason: fc.constant(''),
    optimization: fc.constant({ radius_suggestion: 0, cap_suggestion: 0 }),
    ceps: fc.constant([]),
    slot_id: fc.constant(''),
  });

  // Gerador de query com >= 2 caracteres
  const arbQuery = fc.string({ minLength: 2, maxLength: 20 });

  /**
   * Propriedade 6a: Todos os resultados contêm a query no nome (case-insensitive)
   * **Validates: Requisito 1.4**
   */
  it('Prop 6a: todos os resultados contêm a query no nome (case-insensitive)', () => {
    fc.assert(
      fc.property(fc.array(arbPartner, { maxLength: 50 }), arbQuery, (partners, query) => {
        const results = filterPartners(partners, query);
        const lower = query.toLowerCase();
        return results.every((p) => p.name.toLowerCase().includes(lower));
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Propriedade 6b: Nenhum parceiro que não satisfaça o critério aparece nos resultados
   * **Validates: Requisito 1.4**
   */
  it('Prop 6b: nenhum parceiro que não satisfaça o critério aparece nos resultados', () => {
    fc.assert(
      fc.property(fc.array(arbPartner, { maxLength: 50 }), arbQuery, (partners, query) => {
        const results = filterPartners(partners, query);
        const lower = query.toLowerCase();
        // Parceiros que NÃO deveriam aparecer
        const nonMatching = partners.filter(
          (p) => !p.name.toLowerCase().includes(lower) || p.lat == null || p.lon == null
        );
        return nonMatching.every((nm) => !results.some((r) => r.salesforce_id === nm.salesforce_id));
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Propriedade 6c: Os resultados são um subconjunto dos parceiros de entrada
   * **Validates: Requisito 1.4**
   */
  it('Prop 6c: resultados são subconjunto dos parceiros de entrada', () => {
    fc.assert(
      fc.property(fc.array(arbPartner, { maxLength: 50 }), arbQuery, (partners, query) => {
        const results = filterPartners(partners, query);
        const inputIds = new Set(partners.map((p) => p.salesforce_id));
        return results.every((r) => inputIds.has(r.salesforce_id));
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Propriedade 6d: Quando query < 2 chars, resultados são sempre vazios
   * **Validates: Requisito 1.4**
   */
  it('Prop 6d: quando query < 2 chars, resultados são sempre vazios', () => {
    fc.assert(
      fc.property(
        fc.array(arbPartner, { maxLength: 50 }),
        fc.string({ maxLength: 1 }),
        (partners, query) => {
          const results = filterPartners(partners, query);
          return results.length === 0;
        }
      ),
      { numRuns: 100 }
    );
  });
});
