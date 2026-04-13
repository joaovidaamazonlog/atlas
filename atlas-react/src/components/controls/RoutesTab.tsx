/**
 * RoutesTab.tsx
 * =============
 * Aba de rotas com autocomplete de origem/destino,
 * paradas intermediárias e sugestão HCP.
 */

import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { useStore } from '../../store';
import type { RouteStop, Partner, DeliveryStation, HcpState } from '../../store/types';

// ---------------------------------------------------------------------------
// Autocomplete helpers
// ---------------------------------------------------------------------------

type AutocompleteItem = {
  id: string;
  name: string;
  lat: number;
  lon: number;
};

function toRouteStop(item: AutocompleteItem): RouteStop {
  return { store_id: item.id, name: item.name, lat: item.lat, lon: item.lon };
}

function partnerToItem(p: Partner): AutocompleteItem | null {
  if (p.lat == null || p.lon == null) return null;
  return { id: p.store_id ?? p.salesforce_id, name: p.name, lat: p.lat, lon: p.lon };
}

function stationToItem(s: DeliveryStation): AutocompleteItem {
  return { id: s.nome, name: s.nome, lat: s.lat, lon: s.lon };
}

function searchItems(
  query: string,
  partners: Partner[],
  stations: DeliveryStation[]
): AutocompleteItem[] {
  if (!query.trim()) return [];
  const q = query.toLowerCase();
  const results: AutocompleteItem[] = [];

  for (const p of partners) {
    if (results.length >= 5) break;
    const item = partnerToItem(p);
    if (!item) continue;
    if (
      item.name.toLowerCase().includes(q) ||
      (p.store_id && p.store_id.toLowerCase().includes(q))
    ) {
      results.push(item);
    }
  }

  for (const s of stations) {
    if (results.length >= 5) break;
    if (s.nome.toLowerCase().includes(q)) {
      results.push(stationToItem(s));
    }
  }

  return results.slice(0, 5);
}

// ---------------------------------------------------------------------------
// AutocompleteInput component
// ---------------------------------------------------------------------------

interface AutocompleteInputProps {
  id: string;
  placeholder: string;
  value: string;
  onChange: (val: string) => void;
  onSelect: (item: AutocompleteItem) => void;
  partners: Partner[];
  stations: DeliveryStation[];
}

function AutocompleteInput({
  id,
  placeholder,
  value,
  onChange,
  onSelect,
  partners,
  stations,
}: AutocompleteInputProps) {
  const [suggestions, setSuggestions] = useState<AutocompleteItem[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const results = searchItems(value, partners, stations);
    setSuggestions(results);
    setOpen(results.length > 0 && value.trim().length > 0);
  }, [value, partners, stations]);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSelect = (item: AutocompleteItem) => {
    onChange(item.name);
    setOpen(false);
    onSelect(item);
  };

  return (
    <div ref={containerRef} className="relative">
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className={[
          'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
          'text-sm text-atlas-light placeholder-atlas-muted',
          'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
          'min-h-[44px]',
        ].join(' ')}
      />
      {open && (
        <ul
          className={[
            'absolute z-50 left-0 right-0 mt-1 rounded border border-white/10',
            'bg-atlas-navy shadow-lg overflow-hidden',
          ].join(' ')}
          role="listbox"
        >
          {suggestions.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onMouseDown={() => handleSelect(item)}
                className={[
                  'w-full text-left px-3 py-2 text-sm text-atlas-light',
                  'hover:bg-white/10 transition-colors duration-100',
                  'min-h-[44px] flex items-center',
                ].join(' ')}
                role="option"
                aria-selected={false}
              >
                <span className="truncate">{item.name}</span>
                <span className="ml-auto text-xs text-atlas-muted shrink-0 pl-2">{item.id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoutesTab
// ---------------------------------------------------------------------------

interface StopEntry {
  key: string;
  text: string;
  resolved: AutocompleteItem | null;
}

let stopKeyCounter = 0;
function newStopKey() {
  return `stop-${++stopKeyCounter}`;
}

export default function RoutesTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const deliveryStations = useStore((s) => s.deliveryStations);
  const setRoute = useStore((s) => s.setRoute);
  const clearRoute = useStore((s) => s.clearRoute);
  const hcp = useStore((s) => s.hcp);

  const [originText, setOriginText] = useState('');
  const [originItem, setOriginItem] = useState<AutocompleteItem | null>(null);

  const [destText, setDestText] = useState('');
  const [destItem, setDestItem] = useState<AutocompleteItem | null>(null);

  const [stops, setStops] = useState<StopEntry[]>([]);

  // Show HCP button when suggestionsActive or any station with HCP active
  const showHcpButton = useMemo_hcp(hcp, allMarkersData);

  const handleAddStop = useCallback(() => {
    setStops((prev) => [...prev, { key: newStopKey(), text: '', resolved: null }]);
  }, []);

  const handleRemoveStop = useCallback((key: string) => {
    setStops((prev) => prev.filter((s) => s.key !== key));
  }, []);

  const handleMoveUp = useCallback((index: number) => {
    if (index === 0) return;
    setStops((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next;
    });
  }, []);

  const handleMoveDown = useCallback((index: number) => {
    setStops((prev) => {
      if (index >= prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next;
    });
  }, []);

  const handleStopTextChange = useCallback((key: string, text: string) => {
    setStops((prev) =>
      prev.map((s) => (s.key === key ? { ...s, text, resolved: null } : s))
    );
  }, []);

  const handleStopSelect = useCallback((key: string, item: AutocompleteItem) => {
    setStops((prev) =>
      prev.map((s) => (s.key === key ? { ...s, text: item.name, resolved: item } : s))
    );
  }, []);

  const handleFindRoute = useCallback(() => {
    const routeStops: RouteStop[] = [];
    if (originItem) routeStops.push(toRouteStop(originItem));
    for (const s of stops) {
      if (s.resolved) routeStops.push(toRouteStop(s.resolved));
    }
    if (destItem) routeStops.push(toRouteStop(destItem));
    setRoute(routeStops);
  }, [originItem, stops, destItem, setRoute]);

  const handleClear = useCallback(() => {
    setOriginText('');
    setOriginItem(null);
    setDestText('');
    setDestItem(null);
    setStops([]);
    clearRoute();
  }, [clearRoute]);

  const handleSuggestHcp = useCallback(() => {
    console.info('[RoutesTab] Sugerir HCP Initiatives acionado');
  }, []);

  const canFindRoute = originItem != null && destItem != null;

  return (
    <div className="p-3">
      {/* Origem */}
      <div className="mb-3">
        <label htmlFor="route-origin" className="block text-xs font-medium text-atlas-muted mb-1">
          Origem
        </label>
        <AutocompleteInput
          id="route-origin"
          placeholder="Buscar parceiro ou estação..."
          value={originText}
          onChange={setOriginText}
          onSelect={(item) => setOriginItem(item)}
          partners={allMarkersData}
          stations={deliveryStations}
        />
      </div>

      {/* Paradas intermediárias */}
      {stops.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-atlas-muted mb-1">Paradas</p>
          <div className="flex flex-col gap-2">
            {stops.map((stop, index) => (
              <div key={stop.key} className="flex items-center gap-1">
                <div className="flex flex-col gap-0.5">
                  <button
                    type="button"
                    onClick={() => handleMoveUp(index)}
                    disabled={index === 0}
                    aria-label="Mover para cima"
                    className={[
                      'w-6 h-5 flex items-center justify-center rounded text-xs',
                      'bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed',
                      'transition-colors duration-100',
                    ].join(' ')}
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    onClick={() => handleMoveDown(index)}
                    disabled={index === stops.length - 1}
                    aria-label="Mover para baixo"
                    className={[
                      'w-6 h-5 flex items-center justify-center rounded text-xs',
                      'bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed',
                      'transition-colors duration-100',
                    ].join(' ')}
                  >
                    ▼
                  </button>
                </div>
                <div className="flex-1">
                  <AutocompleteInput
                    id={`stop-${stop.key}`}
                    placeholder="Parada..."
                    value={stop.text}
                    onChange={(val) => handleStopTextChange(stop.key, val)}
                    onSelect={(item) => handleStopSelect(stop.key, item)}
                    partners={allMarkersData}
                    stations={deliveryStations}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => handleRemoveStop(stop.key)}
                  aria-label="Remover parada"
                  className={[
                    'w-8 h-8 flex items-center justify-center rounded',
                    'bg-red-500/20 hover:bg-red-500/40 text-red-400',
                    'transition-colors duration-100 shrink-0',
                  ].join(' ')}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Destino */}
      <div className="mb-3">
        <label htmlFor="route-dest" className="block text-xs font-medium text-atlas-muted mb-1">
          Destino
        </label>
        <AutocompleteInput
          id="route-dest"
          placeholder="Buscar parceiro ou estação..."
          value={destText}
          onChange={setDestText}
          onSelect={(item) => setDestItem(item)}
          partners={allMarkersData}
          stations={deliveryStations}
        />
      </div>

      {/* Adicionar parada */}
      <button
        type="button"
        onClick={handleAddStop}
        className={[
          'w-full py-2 px-4 rounded border border-white/20 text-atlas-muted',
          'text-sm transition-colors duration-150 hover:bg-white/5 hover:text-atlas-light',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30',
          'min-h-[44px] mb-3',
        ].join(' ')}
      >
        + Adicionar Parada
      </button>

      {/* Buscar rota */}
      <button
        type="button"
        onClick={handleFindRoute}
        disabled={!canFindRoute}
        className={[
          'w-full py-3 px-4 rounded bg-atlas-accent text-atlas-darker',
          'text-sm font-semibold transition-colors duration-150',
          'hover:bg-amber-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-atlas-accent',
          'disabled:opacity-40 disabled:cursor-not-allowed',
          'min-h-[44px] mb-2',
        ].join(' ')}
      >
        Buscar Melhor Rota
      </button>

      {/* Limpar rota */}
      <button
        type="button"
        onClick={handleClear}
        className={[
          'w-full py-3 px-4 rounded bg-white/10 text-atlas-light',
          'text-sm font-medium transition-colors duration-150',
          'hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/30',
          'min-h-[44px] mb-2',
        ].join(' ')}
      >
        Limpar Rota
      </button>

      {/* Sugerir HCP (condicional) */}
      {showHcpButton && (
        <button
          type="button"
          onClick={handleSuggestHcp}
          className={[
            'w-full py-3 px-4 rounded border border-purple-500/50 text-purple-300',
            'text-sm font-medium transition-colors duration-150',
            'hover:bg-purple-500/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-400',
            'min-h-[44px]',
          ].join(' ')}
        >
          Sugerir HCP Initiatives
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper hook
// ---------------------------------------------------------------------------

function useMemo_hcp(hcp: HcpState, partners: Partner[]): boolean {
  return useMemo(() => {
    if (hcp.suggestionsActive) return true;
    return partners.some(
      (p) =>
        p.hub_delivey_initiatives === 'HCP Host Partner' ||
        p.hub_delivey_initiatives === 'HCP Pick Up Partner'
    );
  }, [hcp.suggestionsActive, partners]);
}
