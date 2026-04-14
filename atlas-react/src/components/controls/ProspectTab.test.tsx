/**
 * ProspectTab.test.tsx
 * ====================
 * Testes de propriedade para o ProspectTab.
 *
 * Propriedades testadas:
 *   P1 — Cascateamento de carteiras por DS   (Validates: Requirements 1.5, 1.6)
 *   P2 — Limpeza de carteira ao trocar DS    (Validates: Requirements 1.7)
 *   P3 — Estado do botão Buscar              (Validates: Requirements 1.8)
 *
 * Estratégia de renderização:
 *   - useBreakpoint é mockado para retornar 'mobile' → renderização inline (sem portal)
 *   - useGeolocation é mockado com objeto estável
 *   - fetch é mockado para retornar [] (sem resultados → ResultPanel não aparece)
 *   - @tanstack/react-virtual é mockado para renderizar todos os itens diretamente
 *   - useStore.setState é usado para popular allMarkersData com dados de teste
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import ProspectTab from './ProspectTab';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

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

global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });

// ---------------------------------------------------------------------------
// Reset do store antes de cada teste
// ---------------------------------------------------------------------------

beforeEach(() => {
  useStore.setState({
    allMarkersData: [],
    prospectState: {
      companies: [],
      clusters: [],
      isLoading: false,
      error: null,
      selectedStation: null,
      selectedBucket: null,
      pinnedKeys: [],
    },
  });
});

// ---------------------------------------------------------------------------
// Arbitrários
// ---------------------------------------------------------------------------

/**
 * Gera uma string não vazia, sem espaços nas extremidades, sem caracteres
 * especiais que possam interferir com seletores CSS ou regex.
 */
const simpleString = (minLength = 2, maxLength = 10) =>
  fc
    .stringOf(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'), {
      minLength,
      maxLength,
    })
    .filter((s) => s.length >= minLength);

/**
 * Cria um Partner mínimo com apenas os campos necessários para os testes.
 * Os demais campos são preenchidos com valores padrão.
 */
function makePartner(delivery_station: string, bucket_ade: string): Partner {
  return {
    salesforce_id: `sf-${delivery_station}-${bucket_ade}`,
    store_id: null,
    name: `Partner ${delivery_station} ${bucket_ade}`,
    status: 'Active',
    lat: -23.5,
    lon: -46.6,
    zip_code: null,
    city: null,
    state: null,
    delivery_station,
    supply_run: null,
    radius: 5,
    capacity: 100,
    bucket: null,
    bucket_ade,
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
  };
}

// ---------------------------------------------------------------------------
// P1 — Cascateamento de carteiras por DS
// Validates: Requirements 1.5, 1.6
// ---------------------------------------------------------------------------

describe('P1 — Cascateamento de carteiras por DS', () => {
  /**
   * **Validates: Requirements 1.5, 1.6**
   *
   * Para qualquer selectedStation, as carteiras exibidas no seletor de Carteira
   * devem ser exatamente os bucket_ade únicos dos parceiros daquela DS.
   */
  it('Feature: prospect-ux-redesign, Property 1: carteiras exibidas são exatamente os bucket_ade únicos da DS selecionada', () => {
    fc.assert(
      fc.property(
        // Gera 2-4 DS distintas
        fc.uniqueArray(simpleString(2, 8), { minLength: 2, maxLength: 4 }),
        // Para cada DS, gera 1-3 buckets distintos
        fc.array(
          fc.uniqueArray(simpleString(2, 8), { minLength: 1, maxLength: 3 }),
          { minLength: 2, maxLength: 4 },
        ),
        (stations, bucketsPerStation) => {
          // Garante que temos pelo menos 2 DS
          if (stations.length < 2) return;

          // Constrói lista de parceiros: cada combinação DS × bucket gera um parceiro
          const partners: Partner[] = [];
          stations.forEach((ds, i) => {
            const buckets = bucketsPerStation[i] ?? ['bucket-default'];
            buckets.forEach((bucket) => {
              partners.push(makePartner(ds, bucket));
            });
          });

          // Popula o store
          useStore.setState({ allMarkersData: partners });

          const { unmount } = render(<ProspectTab />);

          // Seleciona a primeira DS
          const dsSelect = screen.getByLabelText('Delivery Station') as HTMLSelectElement;
          const targetDs = stations[0];
          fireEvent.change(dsSelect, { target: { value: targetDs } });

          // Obtém as opções do seletor de Carteira (excluindo o placeholder)
          const bucketSelect = screen.getByLabelText('Carteira') as HTMLSelectElement;
          const renderedBuckets = Array.from(bucketSelect.options)
            .filter((opt) => opt.value !== '')
            .map((opt) => opt.value)
            .sort();

          // Calcula os buckets esperados para a DS selecionada
          const expectedBuckets = [
            ...new Set(
              partners
                .filter((p) => p.delivery_station === targetDs)
                .map((p) => p.bucket_ade),
            ),
          ].sort();

          expect(renderedBuckets).toEqual(expectedBuckets);

          unmount();
        },
      ),
      { numRuns: 30 },
    );
  });
});

// ---------------------------------------------------------------------------
// P2 — Limpeza de carteira ao trocar DS
// Validates: Requirements 1.7
// ---------------------------------------------------------------------------

describe('P2 — Limpeza de carteira ao trocar DS', () => {
  /**
   * **Validates: Requirements 1.7**
   *
   * Ao trocar de DS1 para DS2, a carteira selecionada deve ser "" (vazia/placeholder)
   * independentemente de qual carteira estava selecionada antes.
   */
  it('Feature: prospect-ux-redesign, Property 2: ao trocar DS, a carteira selecionada é resetada para vazia', () => {
    fc.assert(
      fc.property(
        // DS1 e DS2 distintas
        fc.tuple(simpleString(2, 8), simpleString(2, 8)).filter(([a, b]) => a !== b),
        // Bucket para DS1
        simpleString(2, 8),
        // Bucket para DS2
        simpleString(2, 8),
        ([ds1, ds2], bucket1, bucket2) => {
          // Cria parceiros para DS1 e DS2 com buckets distintos
          const partners: Partner[] = [
            makePartner(ds1, bucket1),
            makePartner(ds2, bucket2),
          ];

          useStore.setState({ allMarkersData: partners });

          const { unmount } = render(<ProspectTab />);

          const dsSelect = screen.getByLabelText('Delivery Station') as HTMLSelectElement;
          const bucketSelect = screen.getByLabelText('Carteira') as HTMLSelectElement;

          // Seleciona DS1
          fireEvent.change(dsSelect, { target: { value: ds1 } });

          // Seleciona um bucket de DS1
          fireEvent.change(bucketSelect, { target: { value: bucket1 } });
          expect(bucketSelect.value).toBe(bucket1);

          // Troca para DS2
          fireEvent.change(dsSelect, { target: { value: ds2 } });

          // A carteira deve ter sido resetada para "" (placeholder)
          expect(bucketSelect.value).toBe('');

          unmount();
        },
      ),
      { numRuns: 30 },
    );
  });
});

// ---------------------------------------------------------------------------
// P3 — Estado do botão Buscar
// Validates: Requirements 1.8
// ---------------------------------------------------------------------------

describe('P3 — Estado do botão Buscar', () => {
  /**
   * **Validates: Requirements 1.8**
   *
   * O botão "Buscar Empresas" está habilitado se e somente se
   * selectedStation != '' && selectedBucket != ''.
   */
  it('Feature: prospect-ux-redesign, Property 3: botão desabilitado quando DS ou carteira estão vazios', () => {
    fc.assert(
      fc.property(
        simpleString(2, 8), // DS
        simpleString(2, 8), // bucket
        (ds, bucket) => {
          const partners: Partner[] = [makePartner(ds, bucket)];
          useStore.setState({ allMarkersData: partners });

          const { unmount } = render(<ProspectTab />);

          const button = screen.getByRole('button', { name: /Buscar Empresas/i });
          const dsSelect = screen.getByLabelText('Delivery Station') as HTMLSelectElement;
          const bucketSelect = screen.getByLabelText('Carteira') as HTMLSelectElement;

          // Estado inicial: DS vazia, bucket vazio → botão desabilitado
          expect(button).toBeDisabled();

          // Seleciona DS, mas não bucket → ainda desabilitado
          fireEvent.change(dsSelect, { target: { value: ds } });
          expect(button).toBeDisabled();

          // Seleciona bucket → botão habilitado
          fireEvent.change(bucketSelect, { target: { value: bucket } });
          expect(button).toBeEnabled();

          // Limpa DS → botão desabilitado novamente
          fireEvent.change(dsSelect, { target: { value: '' } });
          expect(button).toBeDisabled();

          unmount();
        },
      ),
      { numRuns: 30 },
    );
  });

  it('Feature: prospect-ux-redesign, Property 3: botão habilitado quando DS e carteira estão selecionados', () => {
    fc.assert(
      fc.property(
        simpleString(2, 8),
        simpleString(2, 8),
        (ds, bucket) => {
          const partners: Partner[] = [makePartner(ds, bucket)];
          useStore.setState({ allMarkersData: partners });

          const { unmount } = render(<ProspectTab />);

          const button = screen.getByRole('button', { name: /Buscar Empresas/i });
          const dsSelect = screen.getByLabelText('Delivery Station');
          const bucketSelect = screen.getByLabelText('Carteira');

          fireEvent.change(dsSelect, { target: { value: ds } });
          fireEvent.change(bucketSelect, { target: { value: bucket } });

          expect(button).toBeEnabled();

          unmount();
        },
      ),
      { numRuns: 30 },
    );
  });
});
