/**
 * AppShell.test.tsx
 * =================
 * Teste unitário: FloatingPanel permanece montado após transição isLoading.
 *
 * Simula a transição `isLoading: true → false` no DesktopLayout e verifica
 * que o FloatingPanel com ControlPanel permanece no DOM após a transição.
 *
 * **Validates: Requirements 5.1, 5.3**
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { AppShell } from './AppShell';
import { useStore } from '../../store';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

// Mock useBreakpoint to return desktop breakpoint
vi.mock('../../hooks/useBreakpoint', () => ({
  useBreakpoint: () => 'notebook',
}));

// Mock leaflet CSS
vi.mock('leaflet/dist/leaflet.css', () => ({}));

// Mock react-leaflet
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children, className }: React.PropsWithChildren<{ className?: string }>) => (
    <div data-testid="map-container" className={className}>
      {children}
    </div>
  ),
  TileLayer: () => null,
  useMap: () => ({
    getPane: () => null,
    createPane: () => ({ style: {} }),
  }),
}));

// Mock all map layer components
vi.mock('../map/MapView', () => ({
  default: () => <div data-testid="map-view" />,
}));

// Mock SearchBar
vi.mock('../map/SearchBar', () => ({
  SearchBar: () => <div data-testid="search-bar" />,
}));

// Mock Dashboard (lazy loaded)
vi.mock('../dashboard/Dashboard', () => ({
  default: () => <div data-testid="dashboard" />,
}));

// Mock ControlPanel sub-tabs to avoid deep dependency chains
vi.mock('../controls/FiltersTab', () => ({ default: () => <div data-testid="filters-tab" /> }));
vi.mock('../controls/StyleTab', () => ({ default: () => <div data-testid="style-tab" /> }));
vi.mock('../controls/AreaAnalysisTab', () => ({ default: () => <div data-testid="area-tab" /> }));
vi.mock('../controls/RoutesTab', () => ({ default: () => <div data-testid="routes-tab" /> }));

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

/**
 * Sets the store's isLoading state directly.
 */
function setStoreLoading(loading: boolean) {
  useStore.setState({ isLoading: loading });
}

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

describe('DesktopLayout — FloatingPanel permanece montado após transição isLoading', () => {
  beforeEach(() => {
    // Reset store to clean state before each test
    useStore.setState({ isLoading: false });
  });

  it('renderiza o FloatingPanel com título "Controles" quando isLoading é false', () => {
    setStoreLoading(false);
    const { getByText } = render(<AppShell />);
    expect(getByText('Controles')).toBeTruthy();
  });

  it('FloatingPanel está presente no DOM quando isLoading é true', () => {
    setStoreLoading(true);
    const { getByText } = render(<AppShell />);
    expect(getByText('Controles')).toBeTruthy();
  });

  it('FloatingPanel permanece no DOM após transição isLoading: true → false', () => {
    setStoreLoading(true);
    const { getByText } = render(<AppShell />);

    // Verify FloatingPanel is present while loading
    expect(getByText('Controles')).toBeTruthy();

    // Simulate transition: isLoading true → false
    act(() => {
      setStoreLoading(false);
    });

    // FloatingPanel must still be in the DOM after loading completes
    expect(getByText('Controles')).toBeTruthy();
  });

  it('ControlPanel (tab navigation) permanece no DOM após transição isLoading', () => {
    setStoreLoading(true);
    const { getByRole } = render(<AppShell />);

    // ControlPanel tab list should be present
    expect(getByRole('tablist')).toBeTruthy();

    act(() => {
      setStoreLoading(false);
    });

    // Tab list must still be present after loading completes
    expect(getByRole('tablist')).toBeTruthy();
  });

  it('FloatingPanel não é desmontado em múltiplas transições de isLoading', () => {
    setStoreLoading(false);
    const { getByText } = render(<AppShell />);

    // Cycle through multiple loading state transitions
    act(() => { setStoreLoading(true); });
    expect(getByText('Controles')).toBeTruthy();

    act(() => { setStoreLoading(false); });
    expect(getByText('Controles')).toBeTruthy();

    act(() => { setStoreLoading(true); });
    expect(getByText('Controles')).toBeTruthy();

    act(() => { setStoreLoading(false); });
    expect(getByText('Controles')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Testes de visibilidade por breakpoint (Requirements 3.4, 4.4)
// ---------------------------------------------------------------------------

describe('AppShell — visibilidade dos toggles por breakpoint', () => {
  it('ControlsToggle NÃO está presente no DOM no breakpoint notebook', () => {
    // useBreakpoint já está mockado para retornar 'notebook' neste arquivo
    const { queryByRole } = render(<AppShell />);
    // No DesktopLayout não há ControlsToggle — apenas DashboardToggle
    // ControlsToggle usa aria-label "Abrir controles" ou "Fechar controles"
    const controlsToggle = queryByRole('button', { name: /^(Abrir|Fechar) controles$/i });
    expect(controlsToggle).toBeNull();
  });

  it('DashboardToggle está presente no DOM no breakpoint notebook', () => {
    const { getByRole } = render(<AppShell />);
    const dashboardToggle = getByRole('button', { name: /dashboard/i });
    expect(dashboardToggle).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Smoke tests: estrutura do DOM (Requirements 1.1, 3.1, 4.1, 6.1)
// ---------------------------------------------------------------------------

describe('AppShell — smoke tests de estrutura', () => {
  it('SearchBar é renderizado fora do MapContainer (irmão, não filho)', () => {
    const { getByTestId } = render(<AppShell />);
    const searchBar = getByTestId('search-bar');
    const mapView = getByTestId('map-view');

    // SearchBar and MapView must share the same parent (siblings)
    expect(searchBar.parentElement).toBe(mapView.parentElement);
    // SearchBar must NOT be inside MapView
    expect(mapView.contains(searchBar)).toBe(false);
  });

  it('DashboardToggle está presente no DOM no breakpoint notebook', () => {
    const { getByRole } = render(<AppShell />);
    expect(getByRole('button', { name: /dashboard/i })).toBeTruthy();
  });
});
