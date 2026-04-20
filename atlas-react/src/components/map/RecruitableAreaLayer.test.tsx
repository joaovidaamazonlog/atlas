/**
 * RecruitableAreaLayer.test.tsx
 * ==============================
 * Testes unitários para RecruitableAreaLayer:
 * - Renderização condicional: sem resultado e sem centro → sem camadas
 * - Circle aparece quando ponto central está definido
 * - Células residuais e cobertas recebem estilos diferentes
 *
 * **Validates: Requirements 7.1, 7.2, 7.3**
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { act } from 'react';
import { useStore } from '../../store';
import type { EvaluatorResult } from '../../store/types';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

vi.mock('leaflet/dist/leaflet.css', () => ({}));

// Captura as props passadas para Circle e GeoJSON para inspeção nos testes
const circleProps: Record<string, unknown>[] = [];
const geoJsonProps: Record<string, unknown>[] = [];

vi.mock('react-leaflet', () => ({
  Circle: (props: Record<string, unknown>) => {
    circleProps.push(props);
    return <div data-testid="circle" data-radius={props.radius as number} />;
  },
  GeoJSON: (props: Record<string, unknown>) => {
    geoJsonProps.push(props);
    return <div data-testid="geojson" />;
  },
}));

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function makeFeature(demandDaily: number, isCovered: boolean): GeoJSON.Feature {
  return {
    type: 'Feature',
    geometry: {
      type: 'Point',
      coordinates: [-46.6, -23.5],
    },
    properties: {
      demand_daily: demandDaily,
      demand_residual: isCovered ? 0 : demandDaily,
      is_covered: isCovered,
    },
  };
}

function makeResult(overrides: Partial<EvaluatorResult> = {}): EvaluatorResult {
  const coveredCell = makeFeature(50, true);
  const residualCell = makeFeature(30, false);
  return {
    totalDemand: 80,
    residualDemand: 30,
    minAdv: 40,
    gap: -10,
    viable: false,
    reason: 'INSUFFICIENT_RESIDUAL_DEMAND',
    selectedCells: [coveredCell, residualCell],
    residualCells: [residualCell],
    ...overrides,
  };
}

function setAnalysisState(
  params: Partial<{ centerLat: string; centerLon: string; radiusMeters: number }> = {},
  result: EvaluatorResult | null = null,
) {
  act(() => {
    useStore.getState().setRecruitableParams({
      centerLat: '',
      centerLon: '',
      radiusMeters: 1500,
      ...params,
    });
    useStore.getState().setRecruitableResult(result);
  });
}

function resetState() {
  act(() => {
    useStore.getState().clearRecruitableAnalysis();
  });
}

// ---------------------------------------------------------------------------
// IMPORT AFTER MOCKS
// ---------------------------------------------------------------------------

import RecruitableAreaLayer from './RecruitableAreaLayer';

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

describe('RecruitableAreaLayer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    circleProps.length = 0;
    geoJsonProps.length = 0;
    resetState();
  });

  // -------------------------------------------------------------------------
  // 1. Renderização condicional: sem resultado e sem centro → sem camadas
  // -------------------------------------------------------------------------

  describe('renderização condicional', () => {
    it('retorna null quando não há resultado e não há ponto central', () => {
      // Estado padrão: centerLat='', centerLon='', result=null
      const { container } = render(<RecruitableAreaLayer />);
      expect(container.firstChild).toBeNull();
    });

    it('não renderiza GeoJSON quando result é null (mesmo com centro definido)', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, null);
      render(<RecruitableAreaLayer />);
      expect(geoJsonProps).toHaveLength(0);
    });

    it('não renderiza Circle quando centerLat e centerLon estão vazios', () => {
      setAnalysisState({ centerLat: '', centerLon: '' }, null);
      render(<RecruitableAreaLayer />);
      expect(circleProps).toHaveLength(0);
    });
  });

  // -------------------------------------------------------------------------
  // 2. Circle aparece quando ponto central está definido
  // -------------------------------------------------------------------------

  describe('Circle com ponto central definido', () => {
    it('renderiza Circle quando centerLat e centerLon são strings numéricas válidas', () => {
      setAnalysisState({ centerLat: '-23.5505', centerLon: '-46.6333' }, null);
      render(<RecruitableAreaLayer />);
      expect(circleProps).toHaveLength(1);
    });

    it('Circle usa as coordenadas corretas do ponto central', () => {
      setAnalysisState({ centerLat: '-23.5505', centerLon: '-46.6333' }, null);
      render(<RecruitableAreaLayer />);
      const props = circleProps[0];
      expect(props.center).toEqual([-23.5505, -46.6333]);
    });

    it('Circle usa o radiusMeters configurado', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6', radiusMeters: 2000 }, null);
      render(<RecruitableAreaLayer />);
      expect(circleProps[0].radius).toBe(2000);
    });

    it('renderiza Circle mesmo sem resultado quando centro está definido', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, null);
      const { container } = render(<RecruitableAreaLayer />);
      // Deve renderizar algo (não null)
      expect(container.firstChild).not.toBeNull();
      expect(circleProps).toHaveLength(1);
    });

    it('não renderiza Circle quando centerLat é string vazia', () => {
      setAnalysisState({ centerLat: '', centerLon: '-46.6' }, null);
      render(<RecruitableAreaLayer />);
      expect(circleProps).toHaveLength(0);
    });

    it('não renderiza Circle quando centerLon é string vazia', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '' }, null);
      render(<RecruitableAreaLayer />);
      expect(circleProps).toHaveLength(0);
    });
  });

  // -------------------------------------------------------------------------
  // 3. Células residuais e cobertas recebem estilos diferentes
  // -------------------------------------------------------------------------

  describe('estilos diferenciados para células residuais e cobertas', () => {
    it('renderiza GeoJSON quando há resultado com células selecionadas', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, makeResult());
      render(<RecruitableAreaLayer />);
      expect(geoJsonProps).toHaveLength(1);
    });

    it('a função style retorna estilos diferentes para células residuais vs cobertas', () => {
      const result = makeResult();
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, result);
      render(<RecruitableAreaLayer />);

      const styleFn = geoJsonProps[0].style as (feature?: GeoJSON.Feature) => Record<string, unknown>;
      expect(typeof styleFn).toBe('function');

      // Célula coberta (índice 0 em selectedCells, não está em residualCells)
      const coveredStyle = styleFn(result.selectedCells[0]);
      // Célula residual (índice 1 em selectedCells, está em residualCells)
      const residualStyle = styleFn(result.selectedCells[1]);

      // As cores de preenchimento devem ser diferentes
      expect(coveredStyle.fillColor).not.toBe(residualStyle.fillColor);
      // As cores de borda devem ser diferentes
      expect(coveredStyle.color).not.toBe(residualStyle.color);
    });

    it('células residuais recebem cor de destaque (vermelho/laranja)', () => {
      const result = makeResult();
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, result);
      render(<RecruitableAreaLayer />);

      const styleFn = geoJsonProps[0].style as (feature?: GeoJSON.Feature) => Record<string, unknown>;
      const residualCell = result.residualCells[0];
      const residualStyle = styleFn(residualCell);

      // Cor de preenchimento deve ser laranja/vermelho (não azul/teal)
      const fillColor = residualStyle.fillColor as string;
      expect(fillColor).toMatch(/^#(f97316|ef4444|ff|e[0-9a-f])/i);
    });

    it('células cobertas recebem cor azul/teal', () => {
      const result = makeResult();
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, result);
      render(<RecruitableAreaLayer />);

      const styleFn = geoJsonProps[0].style as (feature?: GeoJSON.Feature) => Record<string, unknown>;
      // Célula coberta: selectedCells[0] não está em residualCells
      const coveredCell = result.selectedCells[0];
      const coveredStyle = styleFn(coveredCell);

      // Cor de preenchimento deve ser azul/teal
      const fillColor = coveredStyle.fillColor as string;
      expect(fillColor).toMatch(/^#(06b6d4|0891b2|0[0-9a-f])/i);
    });

    it('renderiza Circle e GeoJSON juntos quando há resultado e centro definido', () => {
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, makeResult());
      render(<RecruitableAreaLayer />);
      expect(circleProps).toHaveLength(1);
      expect(geoJsonProps).toHaveLength(1);
    });

    it('GeoJSON recebe FeatureCollection com todas as selectedCells', () => {
      const result = makeResult();
      setAnalysisState({ centerLat: '-23.5', centerLon: '-46.6' }, result);
      render(<RecruitableAreaLayer />);

      const data = geoJsonProps[0].data as GeoJSON.FeatureCollection;
      expect(data.type).toBe('FeatureCollection');
      expect(data.features).toHaveLength(result.selectedCells.length);
    });
  });
});
