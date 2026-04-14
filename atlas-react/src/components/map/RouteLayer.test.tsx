/**
 * RouteLayer.test.tsx
 * ===================
 * Testes unitários do ciclo de vida do RouteLayer:
 * - addTo(map) chamado quando route.length >= 2
 * - map.removeControl() chamado no cleanup e quando route é esvaziado
 * - routingerror chama store.setError com mensagem descritiva
 *
 * **Validates: Requirements 7.2, 7.6, 7.7, 7.9**
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { useStore } from '../../store';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

// Mock leaflet-routing-machine CSS (se importado)
vi.mock('leaflet/dist/leaflet.css', () => ({}));
vi.mock('leaflet-routing-machine/dist/leaflet-routing-machine.css', () => ({}));

// Controle mock retornado por L.Routing.control
const mockControl = {
  addTo: vi.fn().mockReturnThis(),
  on: vi.fn().mockReturnThis(),
  remove: vi.fn(),
};

// Mock leaflet + leaflet-routing-machine
vi.mock('leaflet', () => {
  const latLng = (lat: number, lng: number) => ({ lat, lng });
  const marker = vi.fn(() => ({}));

  const Routing = {
    control: vi.fn(() => mockControl),
    osrmv1: vi.fn(() => ({})),
  };

  return {
    default: { latLng, marker, Routing },
    latLng,
    marker,
    Routing,
  };
});

vi.mock('leaflet-routing-machine', () => ({}));

// Mock map retornado por useMap()
const mockMap = {
  addControl: vi.fn(),
  removeControl: vi.fn(),
};

vi.mock('react-leaflet', () => ({
  useMap: () => mockMap,
}));

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

const stop1 = { store_id: 'A', name: 'Stop A', lat: -23.5, lon: -46.6 };
const stop2 = { store_id: 'B', name: 'Stop B', lat: -23.6, lon: -46.7 };
const stop3 = { store_id: 'C', name: 'Stop C', lat: -23.7, lon: -46.8 };

function setRoute(stops: typeof stop1[]) {
  act(() => {
    useStore.getState().setRoute(stops as any);
  });
}

function clearRoute() {
  act(() => {
    useStore.getState().clearRoute();
  });
}

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

// Import after mocks are set up
import RouteLayer from './RouteLayer';
import L from 'leaflet';

describe('RouteLayer — ciclo de vida', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store state
    act(() => {
      useStore.getState().clearRoute();
      useStore.getState().setError(null);
    });
  });

  // -------------------------------------------------------------------------
  // 1. addTo(map) chamado quando route.length >= 2
  // -------------------------------------------------------------------------

  it('chama addTo(map) quando route tem 2 paradas', () => {
    setRoute([stop1, stop2]);
    render(<RouteLayer />);

    expect(L.Routing.control).toHaveBeenCalledTimes(1);
    expect(mockControl.addTo).toHaveBeenCalledWith(mockMap);
  });

  it('chama addTo(map) quando route tem 3 paradas', () => {
    setRoute([stop1, stop2, stop3]);
    render(<RouteLayer />);

    expect(L.Routing.control).toHaveBeenCalledTimes(1);
    expect(mockControl.addTo).toHaveBeenCalledWith(mockMap);
  });

  it('NÃO cria controle de rota quando route tem menos de 2 paradas', () => {
    setRoute([stop1]);
    render(<RouteLayer />);

    expect(L.Routing.control).not.toHaveBeenCalled();
    expect(mockControl.addTo).not.toHaveBeenCalled();
  });

  it('NÃO cria controle de rota quando route está vazia', () => {
    // route já está vazia pelo beforeEach
    render(<RouteLayer />);

    expect(L.Routing.control).not.toHaveBeenCalled();
    expect(mockControl.addTo).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 2. map.removeControl() chamado no cleanup (unmount)
  // -------------------------------------------------------------------------

  it('chama map.removeControl() quando o componente é desmontado', () => {
    setRoute([stop1, stop2]);
    const { unmount } = render(<RouteLayer />);

    expect(mockControl.addTo).toHaveBeenCalledTimes(1);

    unmount();

    expect(mockMap.removeControl).toHaveBeenCalledWith(mockControl);
  });

  // -------------------------------------------------------------------------
  // 3. map.removeControl() chamado quando route é esvaziada
  // -------------------------------------------------------------------------

  it('chama map.removeControl() quando route é esvaziada após ter paradas', () => {
    setRoute([stop1, stop2]);
    render(<RouteLayer />);

    expect(mockControl.addTo).toHaveBeenCalledTimes(1);

    // Esvaziar a rota dispara o useEffect novamente (cleanup + re-run)
    clearRoute();

    expect(mockMap.removeControl).toHaveBeenCalledWith(mockControl);
  });

  // -------------------------------------------------------------------------
  // 4. routingerror chama store.setError com mensagem descritiva
  // -------------------------------------------------------------------------

  it('registra handler de routingerror no controle criado', () => {
    setRoute([stop1, stop2]);
    render(<RouteLayer />);

    expect(mockControl.on).toHaveBeenCalledWith('routingerror', expect.any(Function));
  });

  it('chama store.setError com mensagem descritiva quando routingerror é disparado', () => {
    setRoute([stop1, stop2]);
    render(<RouteLayer />);

    // Captura o handler registrado
    const onCall = (mockControl.on as ReturnType<typeof vi.fn>).mock.calls.find(
      ([event]) => event === 'routingerror',
    );
    expect(onCall).toBeDefined();
    const errorHandler = onCall![1];

    // Simula o evento com mensagem de erro
    act(() => {
      errorHandler({ error: { message: 'Network timeout' } });
    });

    const error = useStore.getState().error;
    expect(error).toBeTruthy();
    expect(error).toContain('Erro ao calcular rota');
    expect(error).toContain('Network timeout');
  });

  it('chama store.setError com fallback quando routingerror não tem mensagem', () => {
    setRoute([stop1, stop2]);
    render(<RouteLayer />);

    const onCall = (mockControl.on as ReturnType<typeof vi.fn>).mock.calls.find(
      ([event]) => event === 'routingerror',
    );
    const errorHandler = onCall![1];

    // Simula o evento sem mensagem de erro
    act(() => {
      errorHandler({ error: null });
    });

    const error = useStore.getState().error;
    expect(error).toBeTruthy();
    expect(error).toContain('serviço OSRM indisponível');
  });
});
