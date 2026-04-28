/**
 * PolygonLayer.test.ts
 * ====================
 * Testes de equivalência da regra de filtragem de features após o
 * refator que removeu a `key={JSON.stringify(filterState)}` e adotou
 * atualização imperativa da camada Leaflet.
 *
 * A instância `L.GeoJSON` agora é estável: mesmo quando o filtro muda,
 * a camada NÃO é desmontada/recriada. A lógica de quais features
 * aparecem vive em `_filterFeatures`, testada aqui com PBT e casos
 * pontuais.
 *
 * Nota sobre Leaflet + jsdom
 * --------------------------
 * Testes de renderização completa exigiriam um mock extenso do Leaflet
 * (getComputedStyle, panes, etc.). Aqui focamos na propriedade central:
 * o CONJUNTO de features produzido pela regra de filtro não mudou com
 * o refatoramento — a função pura que alimenta a camada imperativa é
 * equivalente à lógica anterior.
 *
 * Referências: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.4
 */

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import type { Feature, FeatureCollection } from 'geojson';
import { _filterFeatures, type FilterStateShape } from '../../components/map/PolygonLayer';

// ---------------------------------------------------------------------------
// Helpers + strategies
// ---------------------------------------------------------------------------

function makeFeature(props: Record<string, unknown>): Feature {
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
    properties: props,
  };
}

const featureArb = (): fc.Arbitrary<Feature> =>
  fc.record({
    territory_id: fc.constantFrom(
      'DSP2_bucket-01', 'DSP2_bucket-02', 'DSP4_bucket-01', 'DBR9_bucket-05',
    ),
    delivery_station: fc.constantFrom('DSP2', 'DSP4', 'DBR9'),
    bucket_ade: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: undefined }),
    bdm_cluster: fc.constantFrom('SP-Capital', 'RJ-Metro', 'NE'),
    attainment: fc.option(fc.float({ min: 0, max: 100, noNaN: true }), { nil: undefined }),
  }).map((props) => makeFeature(props as Record<string, unknown>));

const featureCollectionArb = (): fc.Arbitrary<FeatureCollection> =>
  fc.array(featureArb(), { minLength: 0, maxLength: 30 }).map((features) => ({
    type: 'FeatureCollection' as const,
    features,
  }));

// ---------------------------------------------------------------------------
// Casos explícitos
// ---------------------------------------------------------------------------

describe('_filterFeatures', () => {
  it('retorna [] quando polygonsData é null', () => {
    expect(_filterFeatures(null, { selectedStations: 'all', selectedBuckets: 'all' }, [], null)).toEqual([]);
  });

  it('selectedStations="all" + selectedBuckets="all" retorna todas as features', () => {
    const data: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        makeFeature({ delivery_station: 'DSP2', bucket_ade: 'A', territory_id: 't1' }),
        makeFeature({ delivery_station: 'DSP4', bucket_ade: 'B', territory_id: 't2' }),
      ],
    };
    const out = _filterFeatures(data, { selectedStations: 'all', selectedBuckets: 'all' }, [], null);
    expect(out.length).toBe(2);
  });

  it('filtra por station específica', () => {
    const data: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        makeFeature({ delivery_station: 'DSP2', bucket_ade: 'A', territory_id: 't1' }),
        makeFeature({ delivery_station: 'DSP4', bucket_ade: 'B', territory_id: 't2' }),
      ],
    };
    const out = _filterFeatures(
      data,
      { selectedStations: ['DSP2'], selectedBuckets: 'all' },
      [],
      null,
    );
    expect(out.length).toBe(1);
    expect(out[0].properties?.delivery_station).toBe('DSP2');
  });

  it('filtra por bucket específico (usa bucket_ade se houver, senão territory_id)', () => {
    const data: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        makeFeature({ delivery_station: 'DSP2', bucket_ade: 'X', territory_id: 't1' }),
        makeFeature({ delivery_station: 'DSP2', territory_id: 't2' }),
      ],
    };
    const out = _filterFeatures(
      data,
      { selectedStations: 'all', selectedBuckets: ['X'] },
      [],
      null,
    );
    expect(out.length).toBe(1);
    expect(out[0].properties?.bucket_ade).toBe('X');

    const outByTid = _filterFeatures(
      data,
      { selectedStations: 'all', selectedBuckets: ['t2'] },
      [],
      null,
    );
    expect(outByTid.length).toBe(1);
    expect(outByTid[0].properties?.territory_id).toBe('t2');
  });

  it('heatmapActive (prospectClusters não vazio) filtra apenas pelo selectedBucket', () => {
    const data: FeatureCollection = {
      type: 'FeatureCollection',
      features: [
        makeFeature({ delivery_station: 'DSP2', bucket_ade: 'A', territory_id: 't1' }),
        makeFeature({ delivery_station: 'DSP2', bucket_ade: 'B', territory_id: 't2' }),
      ],
    };
    const out = _filterFeatures(
      data,
      { selectedStations: ['DSP4'], selectedBuckets: [] }, // filtros normais seriam []
      [{ some: 'cluster' }],
      'A',
    );
    // heatmap ignora selectedStations/selectedBuckets; só olha selectedBucket
    expect(out.length).toBe(1);
    expect(out[0].properties?.bucket_ade).toBe('A');
  });

  it('heatmapActive sem selectedBucket retorna []', () => {
    const data: FeatureCollection = {
      type: 'FeatureCollection',
      features: [makeFeature({ delivery_station: 'DSP2', bucket_ade: 'A', territory_id: 't1' })],
    };
    const out = _filterFeatures(
      data,
      { selectedStations: 'all', selectedBuckets: 'all' },
      [{ x: 1 }],
      null,
    );
    expect(out.length).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Property-based tests
// ---------------------------------------------------------------------------

describe('_filterFeatures — propriedades', () => {
  it('é idempotente: chamar duas vezes com mesmo input produz mesmo output', () => {
    fc.assert(
      fc.property(featureCollectionArb(), (data) => {
        const s: FilterStateShape = { selectedStations: 'all', selectedBuckets: 'all' };
        const a = _filterFeatures(data, s, [], null);
        const b = _filterFeatures(data, s, [], null);
        expect(a).toEqual(b);
      }),
    );
  });

  it('conjunto resultado ⊆ features originais (filtro nunca adiciona)', () => {
    fc.assert(
      fc.property(
        featureCollectionArb(),
        fc.oneof(fc.constant<'all'>('all'), fc.array(fc.constantFrom('DSP2', 'DSP4'), { maxLength: 2 })),
        fc.oneof(fc.constant<'all'>('all'), fc.array(fc.string(), { maxLength: 3 })),
        (data, selectedStations, selectedBuckets) => {
          const out = _filterFeatures(
            data,
            { selectedStations, selectedBuckets },
            [],
            null,
          );
          expect(out.length).toBeLessThanOrEqual(data.features.length);
          for (const f of out) {
            expect(data.features).toContain(f);
          }
        },
      ),
    );
  });

  it('`all` + `all` é o identity filter (retorna todas features)', () => {
    fc.assert(
      fc.property(featureCollectionArb(), (data) => {
        const out = _filterFeatures(
          data,
          { selectedStations: 'all', selectedBuckets: 'all' },
          [],
          null,
        );
        expect(out.length).toBe(data.features.length);
      }),
    );
  });

  it('estabilidade sob mudanças de filtro: duas mutações consecutivas produzem conjuntos determinísticos', () => {
    // Propriedade que justifica o refator: a camada Leaflet não precisa
    // ser recriada ao mudar filtros. O conjunto filtrado depende só do
    // input atual (sem estado oculto).
    fc.assert(
      fc.property(
        featureCollectionArb(),
        fc.array(fc.constantFrom('DSP2', 'DSP4'), { minLength: 1, maxLength: 2 }),
        fc.array(fc.constantFrom('DSP2', 'DSP4'), { minLength: 1, maxLength: 2 }),
        (data, filter1, filter2) => {
          const a = _filterFeatures(
            data,
            { selectedStations: filter1, selectedBuckets: 'all' },
            [],
            null,
          );
          const b = _filterFeatures(
            data,
            { selectedStations: filter2, selectedBuckets: 'all' },
            [],
            null,
          );
          // Cada chamada depende SÓ dos argumentos — sem memoization escondida
          const aAgain = _filterFeatures(
            data,
            { selectedStations: filter1, selectedBuckets: 'all' },
            [],
            null,
          );
          expect(a).toEqual(aAgain);
          // b pode ou não ser igual a a; o importante é que ambos são puros
          expect(b).toBeDefined();
        },
      ),
    );
  });
});
