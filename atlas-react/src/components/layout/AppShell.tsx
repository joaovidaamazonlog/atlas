import React, { useState, useRef, Suspense, useEffect } from 'react';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { Header } from './Header';
import { Drawer } from './Drawer';
import { FloatingPanel } from './FloatingPanel';
import { DashboardToggle } from '../ui/DashboardToggle';
import { ControlsToggle } from '../ui/ControlsToggle';
import MapView from '../map/MapView';
import ControlPanel from '../controls/ControlPanel';
import { Spinner } from '../ui/Spinner';
import { SearchBar } from '../map/SearchBar';
import { useStore } from '../../store';

const Dashboard = React.lazy(() => import('../dashboard/GeoIntelligenceDashboard'));

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
// Helper: controls drawer header (close button + title)
// ---------------------------------------------------------------------------

const ControlsDrawerHeader: React.FC<{ onClose: () => void }> = ({ onClose }) => (
  <div
    className="flex items-center justify-between px-4 py-3 shrink-0"
    style={{ borderBottom: '1px solid var(--border-color)' }}
  >
    <span className="font-medium text-atlas-light text-sm">Controles</span>
    <button
      onClick={onClose}
      aria-label="Fechar painel de controle"
      className="touch-target text-atlas-muted hover:text-atlas-light transition-colors duration-150"
    >
      <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
      </svg>
    </button>
  </div>
);

// ---------------------------------------------------------------------------
// Layout Mobile
// ---------------------------------------------------------------------------

const MobileLayout: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);
  const manualAnalysisOpen = useStore(s => s.manualAnalysisOpen);

  // Fecha o Dashboard quando alguma view interna dispara atlas:close-dashboard
  // (ex: botão "Ver no mapa" em Maiores Oportunidades).
  useEffect(() => {
    const handler = () => setDashboardOpen(false);
    document.addEventListener('atlas:close-dashboard', handler);
    return () => document.removeEventListener('atlas:close-dashboard', handler);
  }, []);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 overflow-hidden">
        {!manualAnalysisOpen && <SearchBar partners={partners} flyToRef={flyToRef} />}
        <MapView flyToRef={flyToRef} />

        <ControlsToggle isOpen={drawerOpen} onClick={() => setDrawerOpen(o => !o)} />
        {!dashboardOpen && (
          <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen(o => !o)} />
        )}

        {/* Dashboard full-screen em mobile (tela pequena demais p/ split) */}
        {dashboardOpen && (
          <div
            className="fixed inset-0 flex flex-col"
            style={{
              zIndex: 'var(--z-modal)' as unknown as number,
              backgroundColor: 'var(--color-darker)',
            }}
          >
            <div className="flex-1 overflow-y-auto">
              <DashboardWithSuspense />
            </div>
          </div>
        )}
      </div>

      {/* Left Drawer for ControlPanel */}
      <Drawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left" width={320}>
        <ControlsDrawerHeader onClose={() => setDrawerOpen(false)} />
        <div className="flex-1 overflow-y-auto">
          <ControlPanel />
        </div>
      </Drawer>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Layout Tablet — split 50/50 quando Dashboard aberto
// ---------------------------------------------------------------------------

const TabletLayout: React.FC = () => {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [dashboardOpen, setDashboardOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);
  const manualAnalysisOpen = useStore(s => s.manualAnalysisOpen);

  useEffect(() => {
    const handler = () => setDashboardOpen(false);
    document.addEventListener('atlas:close-dashboard', handler);
    return () => document.removeEventListener('atlas:close-dashboard', handler);
  }, []);

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 flex overflow-hidden">
        {/* Coluna do mapa (flex-1 quando dashboard aberto → divide 50/50) */}
        <div className="relative flex-1 min-w-0 overflow-hidden">
          {!manualAnalysisOpen && <SearchBar partners={partners} flyToRef={flyToRef} />}
          <MapView flyToRef={flyToRef} />

          <ControlsToggle isOpen={drawerOpen} onClick={() => setDrawerOpen(o => !o)} />
          {!dashboardOpen && (
            <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen(o => !o)} />
          )}
        </div>

        {/* Coluna do Dashboard — lado a lado, sem sobreposição */}
        {dashboardOpen && (
          <div
            className="flex flex-col shrink-0"
            style={{
              width: '55%',
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
            }}
          >
            <div className="flex-1 min-h-0 overflow-y-auto">
              <DashboardWithSuspense />
            </div>
          </div>
        )}
      </div>

      <Drawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} side="left" width={320}>
        <ControlsDrawerHeader onClose={() => setDrawerOpen(false)} />
        <div className="flex-1 overflow-y-auto">
          <ControlPanel />
        </div>
      </Drawer>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Layout Desktop/Notebook — split side-by-side com ControlPanel flutuante
// quando o Dashboard está fechado, e Drawer lateral quando está aberto.
// ---------------------------------------------------------------------------

interface DesktopLayoutProps {
  controlPanelWidth: number;
  dashboardWidth: number;
}

const DesktopLayout: React.FC<DesktopLayoutProps> = ({ controlPanelWidth }) => {
  const [dashboardOpen, setDashboardOpen] = useState(false);
  // Quando o dashboard abre, o painel flutuante de Controles atrapalharia
  // (ficaria sobre o mapa já comprimido). Movemos para um Drawer — mesmo
  // padrão usado em tablet/mobile. `controlsDrawerOpen` é o estado desse
  // drawer auxiliar (só relevante com o dashboard aberto).
  const [controlsDrawerOpen, setControlsDrawerOpen] = useState(false);
  const flyToRef = useRef<((lat: number, lon: number) => void) | null>(null);
  const partners = useStore(s => s.currentFilteredData);
  const manualAnalysisOpen = useStore(s => s.manualAnalysisOpen);

  useEffect(() => {
    const handler = () => setDashboardOpen(false);
    document.addEventListener('atlas:close-dashboard', handler);
    return () => document.removeEventListener('atlas:close-dashboard', handler);
  }, []);

  const [vw, setVw] = useState(() => typeof window !== 'undefined' ? window.innerWidth : 1440);
  useEffect(() => {
    const handler = () => setVw(window.innerWidth);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);

  const effectivePanelWidth = Math.round(
    vw < 1100 ? Math.max(260, vw * 0.25) :
    vw < 1280 ? Math.max(270, vw * 0.23) :
    controlPanelWidth,
  );

  // Proporção do split map/dashboard. Dashboard ocupa 65% e o mapa 35%
  // em qualquer tamanho desktop — prioriza espaço para as tabelas e o
  // gráfico diário, que são o foco do usuário quando o Dashboard está
  // aberto. O mapa continua visível para referência geográfica.
  const dashboardColumnWidth = '65%';

  return (
    <div className="relative w-full h-full flex flex-col">
      <Header />

      <div className="relative flex-1 flex overflow-hidden">
        {/* Coluna do mapa (ocupa o restante do espaço) */}
        <div className="relative flex-1 min-w-0 overflow-hidden">
          {!manualAnalysisOpen && (
            <SearchBar
              partners={partners}
              flyToRef={flyToRef}
              controlPanelWidth={dashboardOpen ? 0 : effectivePanelWidth}
            />
          )}
          <MapView flyToRef={flyToRef} />

          {/* Painel de Controles flutuante — apenas com o Dashboard fechado.
              Quando o Dashboard abre, a tela de mapa fica apertada e o
              painel flutuante vira drawer (igual tablet/mobile). */}
          {!dashboardOpen && (
            <div
              className="absolute top-4 left-4"
              style={{ zIndex: 'var(--z-overlay)' as unknown as number }}
            >
              <FloatingPanel title="Controles" width={effectivePanelWidth}>
                <div className={vw < 1280 ? 'control-panel-scaled' : ''}>
                  <ControlPanel />
                </div>
              </FloatingPanel>
            </div>
          )}

          {/* Toggle dos Controles — só aparece com Dashboard aberto, para
              não competir com o painel flutuante. */}
          {dashboardOpen && (
            <ControlsToggle
              isOpen={controlsDrawerOpen}
              onClick={() => setControlsDrawerOpen((o) => !o)}
            />
          )}

          {!dashboardOpen && (
            <DashboardToggle isOpen={dashboardOpen} onClick={() => setDashboardOpen((o) => !o)} />
          )}
        </div>

        {/* Coluna do Dashboard — lado a lado, sem sobreposição no mapa */}
        {dashboardOpen && (
          <div
            className="flex flex-col shrink-0"
            style={{
              width: dashboardColumnWidth,
              backgroundColor: 'var(--color-navy)',
              borderLeft: '1px solid var(--border-color)',
            }}
          >
            <div className="flex-1 min-h-0 overflow-y-auto">
              <DashboardWithSuspense />
            </div>
          </div>
        )}
      </div>

      {/* Drawer de Controles — ativo apenas com o Dashboard aberto. */}
      <Drawer
        isOpen={dashboardOpen && controlsDrawerOpen}
        onClose={() => setControlsDrawerOpen(false)}
        side="left"
        width={320}
      >
        <ControlsDrawerHeader onClose={() => setControlsDrawerOpen(false)} />
        <div className="flex-1 overflow-y-auto">
          <ControlPanel />
        </div>
      </Drawer>
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
  if (breakpoint === 'laptop') return <DesktopLayout controlPanelWidth={240} dashboardWidth={380} />;
  if (breakpoint === 'notebook') return <DesktopLayout controlPanelWidth={280} dashboardWidth={440} />;
  // desktop
  return <DesktopLayout controlPanelWidth={360} dashboardWidth={560} />;
};
