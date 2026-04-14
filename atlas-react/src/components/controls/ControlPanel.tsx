/**
 * ControlPanel.tsx
 * ================
 * Container principal com navegação por abas:
 * Filtros | Estilo | Área | Rotas
 */

import { useState, useEffect, useRef } from 'react';
import FiltersTab from './FiltersTab';
import StyleTab from './StyleTab';
import AreaAnalysisTab from './AreaAnalysisTab';
import RoutesTab from './RoutesTab';
import ProspectTab from './ProspectTab';
import { useStore } from '../../store';

type TabId = 'filters' | 'style' | 'area' | 'routes' | 'prospect';

interface Tab {
  id: TabId;
  label: string;
}

const TABS: Tab[] = [
  { id: 'filters', label: 'Filtros' },
  { id: 'style', label: 'Estilo' },
  { id: 'area', label: 'Área' },
  { id: 'routes', label: 'Rotas' },
  { id: 'prospect', label: 'Prospectar' },
];

export default function ControlPanel() {
  const [activeTab, setActiveTab] = useState<TabId>('filters');
  const [prospectKey, setProspectKey] = useState(0);
  const clearProspect = useStore((s) => s.clearProspect);
  const prevTabRef = useRef<TabId>('filters');

  // Limpar estado de prospecção ao sair da aba "Prospectar"
  const handleTabChange = (tab: TabId) => {
    if (prevTabRef.current === 'prospect' && tab !== 'prospect') {
      clearProspect();
      setProspectKey((k) => k + 1); // força remount do ProspectTab, resetando selects locais
    }
    prevTabRef.current = tab;
    setActiveTab(tab);
  };

  // Listen for external tab-switch requests (e.g. "Rota a partir daqui" popup button)
  useEffect(() => {
    const handler = (e: Event) => {
      const tab = (e as CustomEvent<string>).detail as TabId;
      if (TABS.some((t) => t.id === tab)) handleTabChange(tab);
    };
    window.addEventListener('atlas:open-tab', handler);
    return () => window.removeEventListener('atlas:open-tab', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full bg-atlas-navy text-atlas-light overflow-hidden">
      {/* Tab navigation */}
      <div
        className="flex border-b border-white/10 bg-atlas-darker shrink-0"
        role="tablist"
        aria-label="Abas de controle"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => handleTabChange(tab.id)}
            className={[
              'flex-1 py-3 px-2 text-xs font-medium transition-colors duration-150',
              'min-h-[44px] focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent',
              activeTab === tab.id
                ? 'text-atlas-accent border-b-2 border-atlas-accent bg-atlas-navy/50'
                : 'text-atlas-muted hover:text-atlas-light hover:bg-white/5',
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content — todos sempre montados para preservar estado */}
      <div className="flex-1 overflow-y-auto">
        <div role="tabpanel" id="tabpanel-filters" aria-labelledby="tab-filters" hidden={activeTab !== 'filters'}>
          <FiltersTab />
        </div>
        <div role="tabpanel" id="tabpanel-style" aria-labelledby="tab-style" hidden={activeTab !== 'style'}>
          <StyleTab />
        </div>
        <div role="tabpanel" id="tabpanel-area" aria-labelledby="tab-area" hidden={activeTab !== 'area'}>
          <AreaAnalysisTab />
        </div>
        <div role="tabpanel" id="tabpanel-routes" aria-labelledby="tab-routes" hidden={activeTab !== 'routes'}>
          <RoutesTab />
        </div>
        <div role="tabpanel" id="tabpanel-prospect" aria-labelledby="tab-prospect" hidden={activeTab !== 'prospect'}>
          <ProspectTab key={prospectKey} />
        </div>
      </div>
    </div>
  );
}
