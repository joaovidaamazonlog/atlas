/**
 * AreaAnalysisTab.test.tsx
 * ========================
 * Testes de propriedade e unitários para a seção "Área Recrutável" do AreaAnalysisTab.
 *
 * Propriedades testadas:
 *   Property 1 — Validação de campos numéricos positivos (Validates: Requirements 1.3, 1.4, 1.5)
 *   Property 7 — Preenchimento automático a partir de lead (Validates: Requirements 6.2, 6.3)
 *
 * Testes unitários:
 *   - Renderização dos campos com valores padrão (ADV=40, raio=1500)
 *   - Botão desabilitado com valores inválidos
 *   - Aviso de lead sem coordenadas
 *   - Motivo No Go do lead
 *   (Validates: Requirements 1.1, 1.2, 1.5, 6.4, 6.5)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fc from 'fast-check';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import AreaAnalysisTab, { isValidPositiveNumber } from './AreaAnalysisTab';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useBreakpoint', () => ({
  useBreakpoint: () => 'mobile',
}));

// Mock react-leaflet to avoid map rendering issues in jsdom
vi.mock('react-leaflet', () => ({
  useMap: vi.fn(),
  useMapEvents: vi.fn(() => null),
  Circle: () => null,
  GeoJSON: () => null,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeProspect(overrides: Partial<Partner> = {}): Partner {
  return {
    salesforce_id: 'sf-001',
    store_id: null,
    name: 'Lead Teste',
    status: 'Prospect',
    lat: -23.5505,
    lon: -46.6333,
    zip_code: null,
    city: 'São Paulo',
    state: 'SP',
    delivery_station: 'SAO1',
    supply_run: null,
    radius: 1500,
    capacity: 100,
    bucket: null,
    bucket_ade: 'bucket-a',
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
    optimization: { radius_suggestion: 2000, cap_suggestion: 60 },
    ceps: [],
    slot_id: '',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Reset do store antes de cada teste
// ---------------------------------------------------------------------------

beforeEach(() => {
  useStore.setState((state) => ({
    allMarkersData: [],
    recruitableAnalysis: {
      ...state.recruitableAnalysis,
      params: {
        minAdv: 40,
        radiusMeters: 1500,
        centerLat: '',
        centerLon: '',
        selectedLeadId: null,
      },
      result: null,
      error: null,
      isStale: false,
    },
  }));
});

// ---------------------------------------------------------------------------
// Property 1 — Validação de campos numéricos positivos
// Feature: recruitable-area-analysis, Property 1: Validação de campos numéricos positivos
// Validates: Requirements 1.3, 1.4, 1.5
// ---------------------------------------------------------------------------

describe('Property 1 — Validação de campos numéricos positivos', () => {
  it('Feature: recruitable-area-analysis, Property 1: valores positivos são aceitos', () => {
    // Feature: recruitable-area-analysis, Property 1: Validação de campos numéricos positivos
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        (value) => {
          return isValidPositiveNumber(value) === true;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('Feature: recruitable-area-analysis, Property 1: valores ≤ 0 são rejeitados', () => {
    // Feature: recruitable-area-analysis, Property 1: Validação de campos numéricos positivos
    fc.assert(
      fc.property(
        fc.integer({ min: -10000, max: 0 }),
        (value) => {
          return isValidPositiveNumber(value) === false;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('Feature: recruitable-area-analysis, Property 1: string vazia é rejeitada', () => {
    expect(isValidPositiveNumber('')).toBe(false);
  });

  it('Feature: recruitable-area-analysis, Property 1: strings não-numéricas são rejeitadas', () => {
    // Feature: recruitable-area-analysis, Property 1: Validação de campos numéricos positivos
    fc.assert(
      fc.property(
        fc.string().filter((s) => isNaN(Number(s)) && s !== ''),
        (value) => {
          return isValidPositiveNumber(value) === false;
        },
      ),
      { numRuns: 50 },
    );
  });

  it('Feature: recruitable-area-analysis, Property 1: valores positivos como string são aceitos', () => {
    // Feature: recruitable-area-analysis, Property 1: Validação de campos numéricos positivos
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        (value) => {
          return isValidPositiveNumber(String(value)) === true;
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 7 — Preenchimento automático a partir de lead
// Feature: recruitable-area-analysis, Property 7: Preenchimento automático a partir de lead
// Validates: Requirements 6.2, 6.3
// ---------------------------------------------------------------------------

describe('Property 7 — Preenchimento automático a partir de lead', () => {
  it('Feature: recruitable-area-analysis, Property 7: campos são preenchidos com valores exatos do lead', () => {
    // Feature: recruitable-area-analysis, Property 7: Preenchimento automático a partir de lead
    fc.assert(
      fc.property(
        // lat/lon válidos
        fc.double({ min: -90, max: 90, noNaN: true }),
        fc.double({ min: -180, max: 180, noNaN: true }),
        // optimization values
        fc.integer({ min: 100, max: 10000 }),
        fc.integer({ min: 1, max: 500 }),
        // salesforce_id único
        fc.string({ minLength: 3, maxLength: 10 }).filter((s) => s.trim().length > 0),
        (lat, lon, radiusSuggestion, capSuggestion, sfId) => {
          const lead = makeProspect({
            salesforce_id: sfId,
            lat,
            lon,
            optimization: { radius_suggestion: radiusSuggestion, cap_suggestion: capSuggestion },
          });

          useStore.setState({ allMarkersData: [lead] });

          const { unmount } = render(<AreaAnalysisTab />);

          // Seleciona o lead
          const leadSelect = screen.getByLabelText('Analisar Lead') as HTMLSelectElement;
          fireEvent.change(leadSelect, { target: { value: sfId } });

          // Verifica que os campos foram preenchidos com os valores do lead
          const { params } = useStore.getState().recruitableAnalysis;

          const result =
            params.centerLat === String(lat) &&
            params.centerLon === String(lon) &&
            params.radiusMeters === radiusSuggestion &&
            params.minAdv === capSuggestion;

          unmount();
          return result;
        },
      ),
      { numRuns: 50 },
    );
  });
});

// ---------------------------------------------------------------------------
// Testes unitários — seção recrutável
// Validates: Requirements 1.1, 1.2, 1.5, 6.4, 6.5
// ---------------------------------------------------------------------------

describe('AreaAnalysisTab — seção recrutável (testes unitários)', () => {
  it('renderiza campos com valores padrão ADV=40 e raio=1500', () => {
    render(<AreaAnalysisTab />);

    const advInput = screen.getByLabelText(/ADV mínimo/i) as HTMLInputElement;
    const radiusInput = screen.getByLabelText(/Raio de entrega/i) as HTMLInputElement;

    expect(advInput.value).toBe('40');
    expect(radiusInput.value).toBe('1500');
  });

  it('botão "Analisar Área Recrutável" está desabilitado quando lat/lon estão vazios', () => {
    render(<AreaAnalysisTab />);

    const button = screen.getByRole('button', { name: /Analisar Área Recrutável/i });
    expect(button).toBeDisabled();
  });

  it('botão fica desabilitado quando ADV é zero', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          minAdv: 0,
          centerLat: '-23.5',
          centerLon: '-46.6',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    const button = screen.getByRole('button', { name: /Analisar Área Recrutável/i });
    expect(button).toBeDisabled();
  });

  it('botão fica desabilitado quando raio é zero', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          radiusMeters: 0,
          centerLat: '-23.5',
          centerLon: '-46.6',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    const button = screen.getByRole('button', { name: /Analisar Área Recrutável/i });
    expect(button).toBeDisabled();
  });

  it('botão fica habilitado quando todos os campos são válidos', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          minAdv: 40,
          radiusMeters: 1500,
          centerLat: '-23.5505',
          centerLon: '-46.6333',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    const button = screen.getByRole('button', { name: /Analisar Área Recrutável/i });
    expect(button).toBeEnabled();
  });

  it('exibe aviso quando lead selecionado não possui coordenadas', () => {
    const leadNoCoords = makeProspect({
      salesforce_id: 'sf-nocoords',
      lat: null,
      lon: null,
    });

    useStore.setState({
      allMarkersData: [leadNoCoords],
    });

    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          selectedLeadId: 'sf-nocoords',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    expect(
      screen.getByText(/Este lead não possui coordenadas e não pode ser analisado/i),
    ).toBeInTheDocument();
  });

  it('botão fica desabilitado quando lead selecionado não possui coordenadas', () => {
    const leadNoCoords = makeProspect({
      salesforce_id: 'sf-nocoords',
      lat: null,
      lon: null,
    });

    useStore.setState({
      allMarkersData: [leadNoCoords],
    });

    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          selectedLeadId: 'sf-nocoords',
          centerLat: '-23.5',
          centerLon: '-46.6',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    const button = screen.getByRole('button', { name: /Analisar Área Recrutável/i });
    expect(button).toBeDisabled();
  });

  it('exibe motivo No Go do lead quando decision === "No Go"', () => {
    const noGoLead = makeProspect({
      salesforce_id: 'sf-nogo',
      decision: 'No Go',
      reason: 'Sem oportunidade próxima',
    });

    useStore.setState({
      allMarkersData: [noGoLead],
    });

    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          selectedLeadId: 'sf-nogo',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    expect(screen.getByText(/Sem oportunidade próxima/i)).toBeInTheDocument();
    expect(screen.getByText(/No Go:/i)).toBeInTheDocument();
  });

  it('não exibe motivo No Go quando lead tem decision === "Go"', () => {
    const goLead = makeProspect({
      salesforce_id: 'sf-go',
      decision: 'Go',
      reason: '',
    });

    useStore.setState({
      allMarkersData: [goLead],
    });

    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          selectedLeadId: 'sf-go',
        },
      },
    }));

    render(<AreaAnalysisTab />);

    expect(screen.queryByText(/No Go:/i)).not.toBeInTheDocument();
  });

  it('preenche lat/lon automaticamente ao receber evento atlas:map-click-coords', () => {
    render(<AreaAnalysisTab />);

    // Simula clique no mapa
    const event = new CustomEvent('atlas:map-click-coords', {
      detail: { lat: -23.5505, lng: -46.6333 },
    });
    document.dispatchEvent(event);

    const { params } = useStore.getState().recruitableAnalysis;
    expect(params.centerLat).toBe('-23.5505');
    expect(params.centerLon).toBe('-46.6333');
  });
});

// ---------------------------------------------------------------------------
// Testes unitários — painel de resultado recrutável
// Validates: Requirements 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.4
// ---------------------------------------------------------------------------

function makeResult(overrides: Partial<import('../../store/types').EvaluatorResult> = {}): import('../../store/types').EvaluatorResult {
  return {
    totalDemand: 100,
    residualDemand: 60,
    minAdv: 40,
    gap: 20,
    viable: true,
    reason: null,
    selectedCells: [],
    residualCells: [],
    ...overrides,
  };
}

describe('AreaAnalysisTab — painel de resultado recrutável', () => {
  it('exibe badge verde "Viável" quando viable === true', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult({ viable: true }),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/✓ Viável/i)).toBeInTheDocument();
  });

  it('exibe badge vermelho "Não Viável" quando viable === false', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult({ viable: false, reason: 'INSUFFICIENT_RESIDUAL_DEMAND', residualDemand: 10, gap: -30 }),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/✗ Não Viável/i)).toBeInTheDocument();
  });

  it('exibe valores numéricos: demanda total, residual, ADV mínimo e gap', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult({ totalDemand: 120, residualDemand: 55, minAdv: 40, gap: 15 }),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/Demanda Total/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Demanda Residual/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/ADV Mínimo/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Gap/i)).toBeInTheDocument();
  });

  it('exibe barra de progresso', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult(),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('exibe motivo quando viable === false', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult({ viable: false, reason: 'INSUFFICIENT_RESIDUAL_DEMAND', residualDemand: 10, gap: -30 }),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/Demanda residual insuficiente/i)).toBeInTheDocument();
  });

  it('não exibe motivo quando viable === true', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult({ viable: true, reason: null }),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.queryByText(/Motivo:/i)).not.toBeInTheDocument();
  });

  it('exibe decisão do lead quando lead está selecionado', () => {
    const lead = makeProspect({ salesforce_id: 'sf-go', decision: 'Go', reason: '' });
    useStore.setState({
      allMarkersData: [lead],
    });
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          centerLat: '-23.5',
          centerLon: '-46.6',
          selectedLeadId: 'sf-go',
        },
        result: makeResult(),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/Decisão do Lead/i)).toBeInTheDocument();
    expect(screen.getAllByText('Go').length).toBeGreaterThan(0);
  });

  it('exibe indicação de resultado desatualizado quando isStale === true', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult(),
        error: null,
        isStale: true,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/Resultado desatualizado/i)).toBeInTheDocument();
  });

  it('exibe mensagem de erro quando recruitableAnalysis.error está definido', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: null,
        error: 'Dados de demanda não carregados',
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByText(/Dados de demanda não carregados/i)).toBeInTheDocument();
  });

  it('não exibe painel de resultado quando result === null', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: null,
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.queryByTestId('recruitable-result-panel')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Testes unitários — botão "Limpar Análise"
// Validates: Requirements 8.1, 8.2, 8.3
// ---------------------------------------------------------------------------

describe('AreaAnalysisTab — botão "Limpar Análise"', () => {
  it('não exibe botão "Limpar Análise" quando result === null', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: null,
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.queryByTestId('clear-analysis-button')).not.toBeInTheDocument();
  });

  it('exibe botão "Limpar Análise" quando result !== null', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult(),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);
    expect(screen.getByTestId('clear-analysis-button')).toBeInTheDocument();
    expect(screen.getByText(/Limpar Análise/i)).toBeInTheDocument();
  });

  it('clicar em "Limpar Análise" chama clearRecruitableAnalysis e result se torna null', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: {
          ...state.recruitableAnalysis.params,
          centerLat: '-23.5',
          centerLon: '-46.6',
          selectedLeadId: 'sf-001',
        },
        result: makeResult(),
        error: null,
        isStale: false,
      },
    }));

    render(<AreaAnalysisTab />);

    const clearButton = screen.getByTestId('clear-analysis-button');
    fireEvent.click(clearButton);

    const { result } = useStore.getState().recruitableAnalysis;
    expect(result).toBeNull();
  });

  it('após limpar, botão "Limpar Análise" desaparece', () => {
    useStore.setState((state) => ({
      recruitableAnalysis: {
        ...state.recruitableAnalysis,
        params: { ...state.recruitableAnalysis.params, centerLat: '-23.5', centerLon: '-46.6' },
        result: makeResult(),
        error: null,
        isStale: false,
      },
    }));

    const { rerender } = render(<AreaAnalysisTab />);
    expect(screen.getByTestId('clear-analysis-button')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('clear-analysis-button'));

    rerender(<AreaAnalysisTab />);
    expect(screen.queryByTestId('clear-analysis-button')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Property 9 — Opportunity list ordering
// Feature: partner-cap-optimization, Property 9: Opportunity list ordering
// Validates: Requirements 5.2
// ---------------------------------------------------------------------------

/**
 * sortOpportunitiesByGain — pure helper that mirrors the sort logic
 * that CapOpportunityPanel will use when rendering the list.
 * Partners with adv_opportunity != null, sorted by estimated_adv_gain DESC.
 */
function sortOpportunitiesByGain(partners: Partner[]): Partner[] {
  return partners
    .filter((p) => p.adv_opportunity !== null)
    .sort((a, b) => {
      const gainA = a.adv_opportunity!.estimated_adv_gain;
      const gainB = b.adv_opportunity!.estimated_adv_gain;
      return gainB - gainA;
    });
}

function makeActivePartnerWithOpportunity(
  sfId: string,
  estimatedAdvGain: number,
): Partner {
  return {
    ...makeProspect({ salesforce_id: sfId, status: 'Active' }),
    adv_opportunity: {
      suggested_lat: -23.5,
      suggested_lon: -46.6,
      suggested_cap: 60,
      suggested_radius: 1200,
      estimated_adv_gain: estimatedAdvGain,
      distance_from_current: 100,
    },
  };
}

describe('Property 9 — Opportunity list ordering', () => {
  it(
    'Feature: partner-cap-optimization, Property 9: lista ordenada por estimated_adv_gain decrescente',
    () => {
      // Feature: partner-cap-optimization, Property 9: Opportunity list ordering
      // Validates: Requirements 5.2
      fc.assert(
        fc.property(
          // Generate a list of 1–20 partners, each with a random estimated_adv_gain
          fc.array(
            fc.record({
              sfId: fc.string({ minLength: 3, maxLength: 12 }).filter((s) => s.trim().length > 0),
              gain: fc.integer({ min: 1, max: 79 }),
            }),
            { minLength: 1, maxLength: 20 },
          ),
          (items) => {
            // Deduplicate sfIds to avoid duplicate key issues
            const seen = new Set<string>();
            const unique = items.filter(({ sfId }) => {
              if (seen.has(sfId)) return false;
              seen.add(sfId);
              return true;
            });

            const partners = unique.map(({ sfId, gain }) =>
              makeActivePartnerWithOpportunity(sfId, gain),
            );

            const sorted = sortOpportunitiesByGain(partners);

            // All partners with adv_opportunity are included
            if (sorted.length !== partners.length) return false;

            // Verify descending order
            for (let i = 0; i < sorted.length - 1; i++) {
              const gainA = sorted[i].adv_opportunity!.estimated_adv_gain;
              const gainB = sorted[i + 1].adv_opportunity!.estimated_adv_gain;
              if (gainA < gainB) return false;
            }

            return true;
          },
        ),
        { numRuns: 100 },
      );
    },
  );

  it(
    'Feature: partner-cap-optimization, Property 9: parceiros sem adv_opportunity são excluídos da lista',
    () => {
      // Feature: partner-cap-optimization, Property 9: Opportunity list ordering
      // Validates: Requirements 5.2
      fc.assert(
        fc.property(
          fc.array(fc.integer({ min: 1, max: 79 }), { minLength: 1, maxLength: 10 }),
          fc.array(fc.integer({ min: 0, max: 5 }), { minLength: 0, maxLength: 5 }),
          (gains, _nullCounts) => {
            const withOpportunity = gains.map((gain, i) =>
              makeActivePartnerWithOpportunity(`sf-opp-${i}`, gain),
            );
            const withoutOpportunity = _nullCounts.map((_, i) => ({
              ...makeProspect({ salesforce_id: `sf-null-${i}`, status: 'Active' }),
              adv_opportunity: null,
            }));

            const all = [...withOpportunity, ...withoutOpportunity];
            const sorted = sortOpportunitiesByGain(all);

            // Only partners with adv_opportunity should appear
            return sorted.every((p) => p.adv_opportunity !== null) &&
              sorted.length === withOpportunity.length;
          },
        ),
        { numRuns: 100 },
      );
    },
  );
});
