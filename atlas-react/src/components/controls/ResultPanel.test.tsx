/**
 * ResultPanel.test.tsx
 * ====================
 * Testes de propriedade para o ResultPanel.
 *
 * Propriedades testadas:
 *   P6  — Contagem de empresas no cabeçalho   (Validates: Requirements 3.2)
 *   P7  — Campos obrigatórios no card          (Validates: Requirements 3.3)
 *   P8  — Botão alfinete sse coordenadas       (Validates: Requirements 3.8)
 *   P11 — Contagem de contactadas atualizada   (Validates: Requirements 3.17)
 *
 * Estratégia de renderização:
 *   - useBreakpoint é mockado para retornar 'mobile' → renderização inline (sem portal)
 *   - useGeolocation é mockado com objeto estável
 *   - fetch é mockado para evitar chamadas reais à API
 *   - @tanstack/react-virtual é mockado para renderizar todos os itens diretamente
 *     (o virtualizer real não renderiza itens sem um container com altura real no jsdom)
 */

import { describe, it, expect, vi, beforeAll } from 'vitest';
import * as fc from 'fast-check';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import ResultPanel from './ResultPanel';
import type { ProspectCompany } from '../../store/types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useBreakpoint', () => ({
  useBreakpoint: () => 'mobile',
}));

vi.mock('../../hooks/useGeolocation', () => ({
  useGeolocation: () => ({
    position: null,
    isTracking: false,
    error: null,
    startTracking: vi.fn(),
    stopTracking: vi.fn(),
  }),
}));

// Mock @tanstack/react-virtual para renderizar todos os itens sem virtualização
vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: (opts: { count: number; estimateSize: () => number }) => ({
    getVirtualItems: () =>
      Array.from({ length: opts.count }, (_, i) => ({
        index: i,
        key: i,
        start: i * opts.estimateSize(),
        size: opts.estimateSize(),
      })),
    getTotalSize: () => opts.count * opts.estimateSize(),
    measureElement: () => undefined,
  }),
}));

beforeAll(() => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true });
});

// ---------------------------------------------------------------------------
// Props padrão
// ---------------------------------------------------------------------------

const defaultProps = {
  selectedStation: 'DSP1',
  selectedBucket: 'bucket-a',
  onClose: vi.fn(),
  pinnedKeys: new Set<string>(),
  onTogglePin: vi.fn(),
};

// ---------------------------------------------------------------------------
// Arbitrários
// ---------------------------------------------------------------------------

/**
 * Gera uma string não vazia e sem espaços em branco nas extremidades,
 * para evitar problemas com a normalização de texto do Testing Library.
 */
const nonBlankString = (minLength = 1, maxLength = 40) =>
  fc
    .string({ minLength, maxLength })
    .map((s) => s.trim())
    .filter((s) => s.length > 0);

/** Gera uma ProspectCompany com campos controlados para os testes. */
const prospectCompanyArb = fc.record<ProspectCompany>({
  nome: nonBlankString(1, 40),
  endereco: nonBlankString(1, 80),
  telefone_1: fc.option(nonBlankString(8, 15), { nil: null }),
  telefone_2: fc.option(nonBlankString(8, 15), { nil: null }),
  telefone: fc.option(nonBlankString(8, 15), { nil: null }),
  site: fc.string({ minLength: 0, maxLength: 40 }),
  // google_maps_link: pode ser 'N/A' ou URL válida (excluímos string vazia pois
  // o componente trata "" como link válido — igual a qualquer string não-nula e não-'N/A')
  google_maps_link: fc.oneof(
    fc.constant('N/A'),
    fc.webUrl(),
  ),
  cep: fc.string({ minLength: 8, maxLength: 9 }),
  tipo: nonBlankString(1, 30),
  _fonte: nonBlankString(1, 20),
  lat: fc.option(fc.float({ min: -90, max: 90, noNaN: true }), { nil: null }),
  lon: fc.option(fc.float({ min: -180, max: 180, noNaN: true }), { nil: null }),
  isMatch: fc.option(fc.boolean(), { nil: null }),
  contactada: fc.boolean(),
  territory_id: fc.option(nonBlankString(1, 20), { nil: undefined }),
});

/** Gera uma empresa com coordenadas garantidamente válidas. */
const companyWithCoordsArb = prospectCompanyArb.filter(
  (c) => c.lat != null && c.lon != null,
);

/** Gera uma empresa sem coordenadas (lat ou lon nulos). */
const companyWithoutCoordsArb = fc.oneof(
  prospectCompanyArb.map((c) => ({ ...c, lat: null, lon: null })),
  prospectCompanyArb.map((c) => ({ ...c, lat: null })),
  prospectCompanyArb.map((c) => ({ ...c, lon: null })),
);

// ---------------------------------------------------------------------------
// P6 — Contagem de empresas no cabeçalho
// Validates: Requirements 3.2
// ---------------------------------------------------------------------------

describe('P6 — Contagem de empresas no cabeçalho', () => {
  /**
   * **Validates: Requirements 3.2**
   *
   * Para qualquer lista de ProspectCompany, o total exibido no cabeçalho
   * do ResultPanel deve ser igual a companies.length.
   */
  it('Feature: prospect-ux-redesign, Property 6: total no cabeçalho igual a companies.length', () => {
    fc.assert(
      fc.property(
        fc.array(prospectCompanyArb, { minLength: 0, maxLength: 10 }),
        (companies) => {
          const { unmount } = render(
            <ResultPanel {...defaultProps} companies={companies} />,
          );

          const count = companies.length;
          const expectedText = count === 1 ? '1 empresa' : `${count} empresa`;
          // O cabeçalho exibe "N empresa(s)"
          const header = screen.getByText(new RegExp(`${count}\\s+empresa`));
          expect(header).toBeInTheDocument();

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });
});

// ---------------------------------------------------------------------------
// P7 — Campos obrigatórios no card
// Validates: Requirements 3.3
// ---------------------------------------------------------------------------

describe('P7 — Campos obrigatórios no card', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * Para qualquer ProspectCompany, o card renderizado deve conter:
   *   - nome (sempre)
   *   - endereço (sempre)
   *   - tipo (sempre)
   *   - telefone_1 quando não nulo
   *   - link Google Maps quando não nulo e diferente de 'N/A'
   */
  it('Feature: prospect-ux-redesign, Property 7: nome, endereço e tipo sempre presentes no card', () => {
    fc.assert(
      fc.property(prospectCompanyArb, (company) => {
        const { container, unmount } = render(
          <ResultPanel {...defaultProps} companies={[company]} />,
        );

        // O card é o div com classe rounded-lg
        const card = container.querySelector('.rounded-lg');
        expect(card).not.toBeNull();

        // nome — primeiro span font-semibold dentro do card
        const nomeEl = card!.querySelector('.font-semibold');
        expect(nomeEl?.textContent?.trim()).toBe(company.nome);

        // tipo — primeiro span text-atlas-muted dentro do card (antes do endereço)
        const muted = card!.querySelectorAll('.text-xs.text-atlas-muted');
        // muted[0] = tipo, muted[1] = endereço (leading-snug)
        expect(muted[0]?.textContent?.trim()).toBe(company.tipo);

        // endereço — span com classe leading-snug
        const enderecoEl = card!.querySelector('.leading-snug');
        expect(enderecoEl?.textContent?.trim()).toBe(company.endereco);

        unmount();
      }),
      { numRuns: 50 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 7: telefone_1 presente no card quando não nulo', () => {
    fc.assert(
      fc.property(
        prospectCompanyArb.filter((c) => c.telefone_1 != null),
        (company) => {
          const { container, unmount } = render(
            <ResultPanel {...defaultProps} companies={[company]} />,
          );

          // O card exibe "📞 <telefone>" em um span
          const phoneEl = container.querySelector('.text-xs.text-atlas-light');
          expect(phoneEl).not.toBeNull();
          expect(phoneEl?.textContent).toContain(company.telefone_1!);

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 7: link Google Maps presente quando não nulo e diferente de N/A', () => {
    fc.assert(
      fc.property(
        prospectCompanyArb.filter(
          (c) => c.google_maps_link != null && c.google_maps_link !== 'N/A',
        ),
        (company) => {
          const { container, unmount } = render(
            <ResultPanel {...defaultProps} companies={[company]} />,
          );

          const link = container.querySelector('a[href]');
          expect(link).not.toBeNull();
          expect(link?.textContent).toBe('Ver no Google Maps');

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 7: link Google Maps ausente quando N/A', () => {
    fc.assert(
      fc.property(
        prospectCompanyArb.filter((c) => c.google_maps_link === 'N/A'),
        (company) => {
          const { container, unmount } = render(
            <ResultPanel {...defaultProps} companies={[company]} />,
          );

          const link = container.querySelector('a[href]');
          expect(link).toBeNull();

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });
});

// ---------------------------------------------------------------------------
// P8 — Botão alfinete sse coordenadas válidas
// Validates: Requirements 3.8
// ---------------------------------------------------------------------------

describe('P8 — Botão alfinete sse coordenadas válidas', () => {
  /**
   * **Validates: Requirements 3.8**
   *
   * O botão de alfinete deve aparecer no card se e somente se
   * lat != null && lon != null.
   */
  it('Feature: prospect-ux-redesign, Property 8: botão alfinete presente quando lat e lon não nulos', () => {
    fc.assert(
      fc.property(companyWithCoordsArb, (company) => {
        const { unmount } = render(
          <ResultPanel {...defaultProps} companies={[company]} />,
        );

        // O botão tem aria-label "Fixar no mapa" ou "Remover alfinete"
        const pinButton =
          screen.queryByRole('button', { name: 'Fixar no mapa' }) ??
          screen.queryByRole('button', { name: 'Remover alfinete' });

        expect(pinButton).toBeInTheDocument();

        unmount();
      }),
      { numRuns: 50 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 8: botão alfinete ausente quando lat ou lon nulos', () => {
    fc.assert(
      fc.property(companyWithoutCoordsArb, (company) => {
        const { unmount } = render(
          <ResultPanel {...defaultProps} companies={[company]} />,
        );

        const pinButton =
          screen.queryByRole('button', { name: 'Fixar no mapa' }) ??
          screen.queryByRole('button', { name: 'Remover alfinete' });

        expect(pinButton).not.toBeInTheDocument();

        unmount();
      }),
      { numRuns: 50 },
    );
  });
});

// ---------------------------------------------------------------------------
// P11 — Contagem de contactadas atualizada
// Validates: Requirements 3.17
// ---------------------------------------------------------------------------

describe('P11 — Contagem de contactadas atualizada', () => {
  /**
   * **Validates: Requirements 3.17**
   *
   * Para qualquer lista de empresas com qualquer combinação de
   * contactada: true/false, a contagem exibida no cabeçalho deve ser
   * igual ao número de empresas com contactada === true.
   */
  it('Feature: prospect-ux-redesign, Property 11: contagem de contactadas no cabeçalho igual ao número de empresas com contactada === true', () => {
    fc.assert(
      fc.property(
        fc.array(prospectCompanyArb, { minLength: 0, maxLength: 10 }),
        (companies) => {
          const { unmount } = render(
            <ResultPanel {...defaultProps} companies={companies} />,
          );

          const contactadaCount = companies.filter((c) => c.contactada).length;
          const expectedText =
            contactadaCount === 1 ? '1 contactada' : `${contactadaCount} contactada`;

          const header = screen.getByText(new RegExp(`${contactadaCount}\\s+contactada`));
          expect(header).toBeInTheDocument();

          unmount();
        },
      ),
      { numRuns: 50 },
    );
  });
});
