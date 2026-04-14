import React, { useState, useRef, Suspense } from 'react';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { Header } from './Header';
import { BottomSheet } from './BottomSheet';
import { Drawer } from './Drawer';import { FloatingPanel } from './FloatingPanel';
import { DashboardToggle } from '../ui/DashboardToggle';
import { ControlsToggle } from '../ui/ControlsToggle';
import MapView from '../map/MapView';
import ControlPanel from '../controls/ControlPanel';
import { Spinner } from '../ui/Spinner';
import { SearchBar } from '../map/SearchBar';
import { useStore } from '../../store';

const Dashboard = React.lazy(() => import('../dashboard/Dashboard'));

const DashboardWithSuspense: React.FC = () => (
  <Suspense
    fallback={
      <div className="flex items-center justify-center h-full p-8">
        <Spinner />
      </div>
    }
  >
    <Dashboard />
  </Suspense>
);

// ---------------------------------------------------------------------------
// Layout Mobile
// ---------------------------------------------------------------------------

const MobileLayout: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        <SearchBar partners={partners} flyToRef={flyToRef} />
        <MapView flyToRef={flyToRef} />

        <ControlsToggle isOpen={drawerOpen} onClick={() => setDrawerOpen(o => !o)} />
        <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen(o => !o)} />

        {/* Dashboard full-screen */}
        {dashboardOpen && (
          <div
            className="fixed inset-0 flex flex-col"
            style={{
              zIndex: 'var(--z-modal)' as unknown as number,
              backgroundColor: 'var(--color-darker)',
              transform: 'translateX(0)',
              transition: 'transform 300ms ease-in-out',
            }}
          >
            <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--border-color)' }}>
              <span className="font-medium text-atlas-light text-sm">Dashboard</span>
              <button
                onClick={() => setDashboardOpen(false)}
                aria-label="Fechar dashboard"
                className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <DashboardWithSuspense />
            </div>
          </div>
        )}
      </div>

      {/* Left Drawer for ControlPanel — igual tablet */}
      <Drawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left" width={320}>
        <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <span className="font-medium text-atlas-light text-sm">Controles</span>
          <button
            onClick={() => setDrawerOpen(false)}
            aria-label="Fechar painel de controle"
            className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ControlPanel />
        </div>
      </Drawer>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Layout Tablet
// ---------------------------------------------------------------------------

const TabletLayout: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        <SearchBar partners={partners} flyToRef={flyToRef} />
        <MapView flyToRef={flyToRef} />

        <ControlsToggle isOpen={drawerOpen} onClick={() => setDrawerOpen(o => !o)} />
        <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen(o => !o)} />

        {/* Dashboard right panel */}
        {dashboardOpen && (
          <div
            className="absolute top-0 right-0 bottom-0 overflow-y-auto"
            style={{
              width: '85vw',
              zIndex: 'var(--z-overlay)' as unknown as number,
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
              transform: dashboardOpen ? 'translateX(0)' : 'translateX(100%)',
              transition: 'transform 300ms ease-in-out',
            }}
          >
            <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--border-color)' }}>
              <span className="font-medium text-atlas-light text-sm">Dashboard</span>
              <button
                onClick={() => setDashboardOpen(false)}
                aria-label="Fechar dashboard"
                className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <DashboardWithSuspense />
          </div>
        )}
      </div>

      {/* Left Drawer for ControlPanel */}
      <Drawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left" width={320}>
        <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <span className="font-medium text-atlas-light text-sm">Controles</span>
          <button
            onClick={() => setDrawerOpen(false)}
            aria-label="Fechar painel de controle"
            className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ControlPanel />
        </div>
      </Drawer>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Layout Desktop/Notebook
// ---------------------------------------------------------------------------

interface DesktopLayoutProps {
  controlPanelWidth: number;
  dashboardWidth: number;
}

const DesktopLayout: React.FC<DesktopLayoutProps> = ({ controlPanelWidth, dashboardWidth }) => {
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        <SearchBar partners={partners} flyToRef={flyToRef} controlPanelWidth={controlPanelWidth} />
        <MapView flyToRef={flyToRef} />
        <div
          className="absolute top-4 left-4"
          style={{ zIndex: 'var(--z-overlay)' as unknown as number }}
        >
          <FloatingPanel title="Controles" width={controlPanelWidth}>
            <ControlPanel />
          </FloatingPanel>
        </div>

        {/* Dashboard toggle */}
        <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen((o) => !o)} />

        {/* Dashboard right panel */}
        {dashboardOpen && (
          <div
            className="absolute top-0 right-0 bottom-0 overflow-y-auto"
            style={{
              width: '60vw',
              zIndex: 'var(--z-overlay)' as unknown as number,
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
              transform: dashboardOpen ? 'translateX(0)' : 'translateX(100%)',
              transition: 'transform 300ms ease-in-out',
            }}
          >
            <div className="flex items-center justify-between px-4 py-3 shrink-0" style={{ borderBottom: '1px solid var(--border-color)' }}>
              <span className="font-medium text-atlas-light text-sm">Dashboard</span>
              <button
                onClick={() => setDashboardOpen(false)}
                aria-label="Fechar dashboard"
                className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
            <DashboardWithSuspense />
          </div>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// AppShell — entry point
// ---------------------------------------------------------------------------

export const AppShell: React.FC = () => {
  const breakpoint = useBreakpoint();

  if (breakpoint === 'mobile') return <MobileLayout />;
  if (breakpoint === 'tablet') return <TabletLayout />;
  if (breakpoint === 'notebook') return <DesktopLayout controlPanelWidth={320} dashboardWidth={480} />;
  // desktop
  return <DesktopLayout controlPanelWidth={360} dashboardWidth={560} />;
};
