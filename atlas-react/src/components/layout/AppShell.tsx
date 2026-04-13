import React, { useState, Suspense } from 'react';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { Header } from './Header';
import { BottomSheet } from './BottomSheet';
import { Drawer } from './Drawer';
import { FloatingPanel } from './FloatingPanel';
import { FAB } from '../ui/FAB';
import MapView from '../map/MapView';
import ControlPanel from '../controls/ControlPanel';
import { Spinner } from '../ui/Spinner';

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
  const [controlPanelOpen, setControlPanelOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      {/* Map fills remaining space */}
      <div className="relative flex-1 overflow-hidden">
        <MapView />

        {/* FABs */}
        <div className="absolute bottom-6 right-4 flex flex-col gap-3" style={{ zIndex: 'var(--z-overlay)' as unknown as number }}>
          <FAB
            label="Abrir painel de controle"
            onClick={() => setControlPanelOpen(true)}
            icon={
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            }
          />
          <FAB
            label="Abrir dashboard"
            onClick={() => setDashboardOpen(true)}
            icon={
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            }
          />
        </div>
      </div>

      {/* BottomSheet for ControlPanel */}
      <BottomSheet isOpen={controlPanelOpen} onClose={() => setControlPanelOpen(false)}>
        <ControlPanel />
      </BottomSheet>

      {/* Dashboard as full-screen modal */}
      {dashboardOpen && (
        <div
          className="fixed inset-0 flex flex-col"
          style={{
            zIndex: 'var(--z-modal)' as unknown as number,
            backgroundColor: 'var(--color-darker)',
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
  );
};

// ---------------------------------------------------------------------------
// Layout Tablet
// ---------------------------------------------------------------------------

const TabletLayout: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        <MapView />

        {/* Toggle drawer FAB */}
        <div className="absolute top-4 left-4" style={{ zIndex: 'var(--z-overlay)' as unknown as number }}>
          <FAB
            label="Abrir painel de controle"
            onClick={() => setDrawerOpen(true)}
            icon={
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
            }
          />
        </div>

        {/* Dashboard FAB */}
        <div className="absolute bottom-6 right-4" style={{ zIndex: 'var(--z-overlay)' as unknown as number }}>
          <FAB
            label="Abrir dashboard"
            onClick={() => setDashboardOpen((o) => !o)}
            icon={
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            }
          />
        </div>

        {/* Dashboard right panel */}
        {dashboardOpen && (
          <div
            className="absolute top-0 right-0 bottom-0 overflow-y-auto"
            style={{
              width: '85vw',
              zIndex: 'var(--z-overlay)' as unknown as number,
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
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

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        <MapView />

        {/* Floating ControlPanel — top left */}
        <div
          className="absolute top-4 left-4"
          style={{ zIndex: 'var(--z-overlay)' as unknown as number }}
        >
          <FloatingPanel title="Controles" width={controlPanelWidth}>
            <ControlPanel />
          </FloatingPanel>
        </div>

        {/* Dashboard toggle FAB */}
        <div className="absolute bottom-6 right-4" style={{ zIndex: 'var(--z-overlay)' as unknown as number }}>
          <FAB
            label="Abrir dashboard"
            onClick={() => setDashboardOpen((o) => !o)}
            icon={
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            }
          />
        </div>

        {/* Dashboard right panel */}
        {dashboardOpen && (
          <div
            className="absolute top-0 right-0 bottom-0 overflow-y-auto"
            style={{
              width: `${dashboardWidth}px`,
              zIndex: 'var(--z-overlay)' as unknown as number,
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
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
