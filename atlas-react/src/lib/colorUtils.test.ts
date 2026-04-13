/**
 * colorUtils.test.ts
 * ==================
 * Testes de propriedade e exemplo para colorUtils.ts.
 *
 * **Validates: Requirements 10.2**
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { generateColorMap, getMarkerStyle, buildColorMaps } from './colorUtils';
import { COLOR_PALETTES } from './config';
import type { Partner } from '../store/types';

// ---------------------------------------------------------------------------
// ARBITRÁRIOS
// ---------------------------------------------------------------------------

const arbitraryPartnerStatus = () =>
  fc.constantFrom(
    'Active',
    'Inactive',
    'Onboarding',
    'BG Checks',
    'Prospect',
    'Exited',
    'New',
  ) as fc.Arbitrary<Partner['status']>;

const arbitraryPartner = (): fc.Arbitrary<Partner> =>
  fc.record({
    salesforce_id: fc.string({ minLength: 1, maxLength: 20 }),
    store_id: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    name: fc.string({ minLength: 1, maxLength: 50 }),
    status: arbitraryPartnerStatus(),
    lat: fc.option(fc.float({ min: -33, max: 5, noNaN: true }), { nil: null }),
    lon: fc.option(fc.float({ min: -73, max: -34, noNaN: true }), { nil: null }),
    zip_code: fc.option(fc.string({ minLength: 8, maxLength: 9 }), { nil: null }),
    city: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: null }),
    state: fc.option(fc.string({ minLength: 2, maxLength: 2 }), { nil: null }),
    delivery_station: fc.constantFrom('DSP2', 'DSP3', 'DRJ3', 'DGO2'),
    supply_run: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    radius: fc.integer({ min: 0, max: 5000 }),
    capacity: fc.integer({ min: 0, max: 200 }),
    bucket: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    bucket_ade: fc.string({ minLength: 1, maxLength: 20 }),
    jurisdiction_type: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    hub_delivey_initiatives: fc.option(
      fc.constantFrom('HCP Host Partner', 'HCP Pick Up Partner', 'Hub Hero'),
      { nil: null },
    ),
    HCP_rate_card: fc.option(fc.constantFrom('Tier 1', 'Tier 2'), { nil: null }),
    HCP_host_partner: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: null }),
    launch_date: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    exited_date: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    telefone: fc.option(fc.string({ minLength: 10, maxLength: 15 }), { nil: null }),
    owner_id: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    decision_status: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    lead_source: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
    tooltip: fc.string({ minLength: 0, maxLength: 50 }),
    regiao: fc.string({ minLength: 0, maxLength: 20 }),
    decision: fc.string({ minLength: 0, maxLength: 20 }),
    reason: fc.string({ minLength: 0, maxLength: 50 }),
    optimization: fc.record({
      radius_suggestion: fc.integer({ min: 0, max: 5000 }),
      cap_suggestion: fc.integer({ min: 0, max: 200 }),
    }),
    ceps: fc.array(fc.string({ minLength: 8, maxLength: 9 }), { maxLength: 5 }),
    slot_id: fc.string({ minLength: 0, maxLength: 20 }),
  });

// ---------------------------------------------------------------------------
// TESTES DE PROPRIEDADE
// ---------------------------------------------------------------------------

fc.configureGlobal({ numRuns: 100 });

describe('colorUtils — Propriedade 9: Cores dos marcadores correspondem à estilização selecionada', () => {
  /**
   * **Validates: Requirements 10.2**
   *
   * Para qualquer campo de estilização e currentFilteredData, cada marcador
   * deve ter a cor correspondente ao valor do campo no colorMap gerado.
   */
  it('Feature: react-responsive-frontend, Property 9: cada marcador recebe a cor do colorMap para o campo selecionado', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryPartner(), { minLength: 1, maxLength: 30 }),
        fc.constantFrom(
          'status',
          'delivery_station',
          'bucket_ade',
          'hub_delivey_initiatives',
        ) as fc.Arbitrary<keyof Partner>,
        (partners, field) => {
          const colorMap = generateColorMap(partners, field, true);

          // Cada parceiro deve ter uma cor no mapa
          for (const partner of partners) {
            const key = String(partner[field] ?? 'N/A');
            const color = colorMap[key];
            expect(color).toBeDefined();
            expect(typeof color).toBe('string');
            expect(color.startsWith('#')).toBe(true);
          }

          // O mapa deve conter apenas cores da paleta de borda
          for (const color of Object.values(colorMap)) {
            expect(COLOR_PALETTES.border).toContain(color);
          }
        },
      ),
    );
  });

  it('Feature: react-responsive-frontend, Property 9: getMarkerStyle retorna cor consistente com o colorMap', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryPartner(), { minLength: 1, maxLength: 30 }),
        (partners) => {
          const primaryField: keyof Partner = 'delivery_station';
          const secondaryField: keyof Partner = 'status';

          const borderMap = generateColorMap(partners, primaryField, true);
          const fillMap = generateColorMap(partners, secondaryField, false);

          for (const partner of partners) {
            const style = getMarkerStyle(partner, primaryField, secondaryField, {
              border: borderMap,
              fill: fillMap,
            });

            const expectedBorderKey = String(partner[primaryField] ?? 'N/A');
            const expectedBorderColor =
              borderMap[expectedBorderKey] ?? COLOR_PALETTES.border[0];

            expect(style.color).toBe(expectedBorderColor);
            expect(style.fillOpacity).toBe(0.9);
            expect(style.weight).toBe(3);
          }
        },
      ),
    );
  });

  it('Feature: react-responsive-frontend, Property 9: colorMap não tem duplicatas de chave', () => {
    fc.assert(
      fc.property(
        fc.array(arbitraryPartner(), { minLength: 1, maxLength: 50 }),
        (partners) => {
          const colorMap = generateColorMap(partners, 'status', false);
          const keys = Object.keys(colorMap);
          const uniqueKeys = new Set(keys);
          expect(keys.length).toBe(uniqueKeys.size);
        },
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// TESTES DE EXEMPLO
// ---------------------------------------------------------------------------

describe('colorUtils — testes de exemplo', () => {
  const samplePartners: Partner[] = [
    {
      salesforce_id: 'A1',
      store_id: 'S1',
      name: 'Parceiro A',
      status: 'Active',
      lat: -23.5,
      lon: -46.6,
      zip_code: null,
      city: null,
      state: null,
      delivery_station: 'DSP2',
      supply_run: null,
      radius: 1500,
      capacity: 42,
      bucket: null,
      bucket_ade: 'BKT1',
      jurisdiction_type: null,
      hub_delivey_initiatives: 'HCP Host Partner',
      HCP_rate_card: 'Tier 1',
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
      optimization: { radius_suggestion: 1500, cap_suggestion: 42 },
      ceps: [],
      slot_id: '',
    },
    {
      salesforce_id: 'A2',
      store_id: 'S2',
      name: 'Parceiro B',
      status: 'Inactive',
      lat: -23.6,
      lon: -46.7,
      zip_code: null,
      city: null,
      state: null,
      delivery_station: 'DSP3',
      supply_run: null,
      radius: 1000,
      capacity: 30,
      bucket: null,
      bucket_ade: 'BKT2',
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
      optimization: { radius_suggestion: 1000, cap_suggestion: 30 },
      ceps: [],
      slot_id: '',
    },
  ];

  it('generateColorMap retorna cores distintas para valores distintos', () => {
    const map = generateColorMap(samplePartners, 'delivery_station', true);
    expect(map['DSP2']).toBeDefined();
    expect(map['DSP3']).toBeDefined();
    expect(map['DSP2']).not.toBe(map['DSP3']);
  });

  it('generateColorMap usa paleta de borda quando isBorder=true', () => {
    const map = generateColorMap(samplePartners, 'status', true);
    for (const color of Object.values(map)) {
      expect(COLOR_PALETTES.border).toContain(color);
    }
  });

  it('generateColorMap usa paleta de preenchimento quando isBorder=false', () => {
    const map = generateColorMap(samplePartners, 'status', false);
    for (const color of Object.values(map)) {
      expect(COLOR_PALETTES.fill).toContain(color);
    }
  });

  it('getMarkerStyle retorna fillColor branco quando primary === secondary', () => {
    const map = generateColorMap(samplePartners, 'status', true);
    const style = getMarkerStyle(samplePartners[0], 'status', 'status', {
      border: map,
      fill: {},
    });
    expect(style.fillColor).toBe('#fff');
  });

  it('buildColorMaps retorna fill vazio quando primary === secondary', () => {
    const maps = buildColorMaps(samplePartners, {
      primaryField: 'status',
      secondaryField: 'status',
    });
    expect(Object.keys(maps.fill).length).toBe(0);
    expect(Object.keys(maps.border).length).toBeGreaterThan(0);
  });

  it('buildColorMaps retorna ambos os mapas quando campos são diferentes', () => {
    const maps = buildColorMaps(samplePartners, {
      primaryField: 'delivery_station',
      secondaryField: 'status',
    });
    expect(Object.keys(maps.border).length).toBeGreaterThan(0);
    expect(Object.keys(maps.fill).length).toBeGreaterThan(0);
  });
});
