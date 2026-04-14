/**
 * MapView.test.tsx
 * ================
 * Smoke test: verifica que o MapView renderiza sem controles de zoom.
 *
 * **Validates: Requirements 6.1, 6.3**
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import MapView from './MapView';

// ---------------------------------------------------------------------------
// MOCKS
// ---------------------------------------------------------------------------

// Mock leaflet CSS import
vi.mock('leaflet/dist/leaflet.css', () => ({}));

// Mock react-leaflet — substitui MapContainer por um div simples
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children, className, style }: React.PropsWithChildren<{ className?: string; style?: React.CSSProperties }>) => (
    <div data-testid="map-container" className={className} style={style}>
      {children}
    </div>
  ),
  TileLayer: () => null,
  useMap: () => ({
    getPane: () => null,
    createPane: () => ({ style: {} }),
  }),
}));

// Mock all child layer components to avoid deep dependency chains
vi.mock('./PartnerMarkers', () => ({ default: () => null }));
vi.mock('./StationMarkers', () => ({ default: () => null }));
vi.mock('./PolygonLayer', () => ({ default: () => null }));
vi.mock('./JurisdictionLayer', () => ({ default: () => null }));
vi.mock('./OptimizationLayer', () => ({ default: () => null }));
vi.mock('./HeatmapLayer', () => ({ default: () => null }));
vi.mock('./RouteLayer', () => ({ default: () => null }));
vi.mock('./MapLegend', () => ({ default: () => null }));

// ---------------------------------------------------------------------------
// TESTES
// ---------------------------------------------------------------------------

describe('MapView — smoke test: controles de zoom', () => {
  it('renderiza sem lançar erros', () => {
    expect(() => render(<MapView />)).not.toThrow();
  });

  it('não exibe botões de zoom (+/-) no DOM', () => {
    const { container } = render(<MapView />);
    const zoomControl = container.querySelector('.leaflet-control-zoom');
    expect(zoomControl).toBeNull();
  });

  it('não exibe botão zoom-in no DOM', () => {
    const { container } = render(<MapView />);
    const zoomIn = container.querySelector('.leaflet-control-zoom-in');
    expect(zoomIn).toBeNull();
  });

  it('não exibe botão zoom-out no DOM', () => {
    const { container } = render(<MapView />);
    const zoomOut = container.querySelector('.leaflet-control-zoom-out');
    expect(zoomOut).toBeNull();
  });
});
