/**
 * Dashboard.test.tsx
 * ==================
 * Testes unitários para o componente Dashboard.
 * Cobre estados de loading, erro e sucesso do fetch.
 *
 * **Validates: Requirements 2.1, 2.2, 2.7, 2.13**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import Dashboard from './Dashboard';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

vi.mock('react-chartjs-2', () => ({
  Bar: () => <canvas data-testid="chart" />,
}));

vi.mock('../../lib/config', () => ({
  DATA_URLS: {
    executiveReport: 'http://test.local/relatorio.json',
  },
}));

vi.mock('../ui/Spinner', () => ({
  Spinner: () => <div data-testid="spinner" />,
}));

vi.mock('./FilterCascade', () => ({
  default: () => <div data-testid="filter-cascade" />,
}));

// ---------------------------------------------------------------------------
// TEST DATA
// ---------------------------------------------------------------------------

const mockReportData = {
  generatedAt: '2024-01-15 10:00:00',
  bases: [
    {
      code: 'DSP2',
      bdm: 'João Silva',
      numTerritories: 2,
      dailyDemand: 1500,
      idealSlots: 20,
      matchedSlots: 18,
      openSlots: 2,
      coverage: 0.9,
      partners: {
        active: 15,
        onboarding: 3,
        bgChecks: 1,
        prospects: 2,
        inactive: 0,
      },
      attainment: 0.75,
      territories: [
        {
          id: 'DSP2_bucket-1',
          ctl: 'CTL-A',
          dailyDemand: 750,
          totalSlots: 10,
          openSlots: 1,
          active: 8,
          onboarding: 2,
          bg: 0,
          prospects: 1,
          inactive: 0,
          attainment: 0.8,
          accuracy: 0.85,
        },
        {
          id: 'DSP2_bucket-2',
          ctl: 'CTL-B',
          dailyDemand: 750,
          totalSlots: 10,
          openSlots: 1,
          active: 7,
          onboarding: 1,
          bg: 1,
          prospects: 1,
          inactive: 0,
          attainment: 0.7,
          accuracy: 0.75,
        },
      ],
    },
    {
      code: 'DRJ3',
      bdm: 'Maria Santos',
      numTerritories: 1,
      dailyDemand: 800,
      idealSlots: 12,
      matchedSlots: 10,
      openSlots: 2,
      coverage: 0.83,
      partners: {
        active: 9,
        onboarding: 1,
        bgChecks: 0,
        prospects: 0,
        inactive: 1,
      },
      attainment: 0.65,
      territories: [
        {
          id: 'DRJ3_bucket-1',
          ctl: 'CTL-C',
          dailyDemand: 800,
          totalSlots: 12,
          openSlots: 2,
          active: 9,
          onboarding: 1,
          bg: 0,
          prospects: 0,
          inactive: 1,
          attainment: 0.65,
          accuracy: 0.72,
        },
      ],
    },
  ],
};

// ---------------------------------------------------------------------------
// SETUP — stub fetch globally for all tests
// ---------------------------------------------------------------------------

const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);

beforeEach(() => {
  fetchMock.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

describe('Dashboard — estado de loading', () => {
  it('exibe spinner enquanto o fetch está pendente', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}));

    await act(async () => {
      render(<Dashboard />);
    });

    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  it('não exibe KPI cards durante o carregamento', async () => {
    fetchMock.mockReturnValue(new Promise(() => {}));

    await act(async () => {
      render(<Dashboard />);
    });

    expect(screen.queryByText('Bases')).not.toBeInTheDocument();
    expect(screen.queryByText('Territórios')).not.toBeInTheDocument();
  });
});

describe('Dashboard — estado de erro', () => {
  it('exibe mensagem de erro quando o fetch falha com erro de rede', async () => {
    fetchMock.mockRejectedValue(new Error('Network error'));

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });
  });

  it('exibe mensagem de erro quando o fetch retorna status não-ok', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    } as Response);

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/HTTP 500/i)).toBeInTheDocument();
    });
  });

  it('exibe botão "Tentar novamente" quando o fetch falha', async () => {
    fetchMock.mockRejectedValue(new Error('Falha na conexão'));

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
    });
  });

  it('clicar em "Tentar novamente" dispara um novo fetch', async () => {
    fetchMock
      .mockRejectedValueOnce(new Error('Falha na conexão'))
      .mockReturnValue(new Promise(() => {}));

    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /tentar novamente/i })).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /tentar novamente/i }));
    });

    // After retry, the useEffect fires and calls fetch again
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    }, { timeout: 3000 });
  });
});

describe('Dashboard — estado de sucesso', () => {
  beforeEach(() => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockReportData),
    } as unknown as Response);
  });

  it('exibe KPI card "Bases" após fetch bem-sucedido', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Bases')).toBeInTheDocument();
    });
  });

  it('exibe KPI card "Territórios" após fetch bem-sucedido', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Territórios')).toBeInTheDocument();
    });
  });

  it('exibe o valor correto de bases (2)', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Bases')).toBeInTheDocument();
    });

    // computeKPIs retorna totalBases = 2 para os dados de teste
    // Use getAllByText since "2" may appear multiple times in the table
    const allTwos = screen.getAllByText('2');
    expect(allTwos.length).toBeGreaterThan(0);
    // The KPI card value for "Bases" should be 2
    const basesLabel = screen.getByText('Bases');
    const basesCard = basesLabel.closest('div');
    expect(basesCard).toBeTruthy();
    expect(basesCard!.textContent).toContain('2');
  });

  it('exibe o FilterCascade após fetch bem-sucedido', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByTestId('filter-cascade')).toBeInTheDocument();
    });
  });

  it('não exibe spinner após fetch bem-sucedido', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Bases')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('spinner')).not.toBeInTheDocument();
  });

  it('não exibe botão "Tentar novamente" após fetch bem-sucedido', async () => {
    render(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Bases')).toBeInTheDocument();
    });

    expect(
      screen.queryByRole('button', { name: /tentar novamente/i }),
    ).not.toBeInTheDocument();
  });
});
