/**
 * RoutesTab.tsx
 * =============
 * Aba de rotas: origem/destino com autocomplete, paradas intermediárias,
 * "Rota a partir daqui" via evento, e sugestão HCP com 3 fases.
 */

import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../store';
import { osrmTableMatrix, osrmResult, getCurrentHcpGroups } from '../../lib/routeUtils';
import { HCP_CONFIG } from '../../lib/config';
import type { RouteStop, Partner, DeliveryStation } from '../../store/types';

// ---------------------------------------------------------------------------
// Autocomplete helpers
// ---------------------------------------------------------------------------

type AutocompleteItem = { id: string; name: string; lat: number; lon: number };

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

function searchItems(query: string, partners: Partner[], stations: DeliveryStation[]): AutocompleteItem[] {
  if (!query.trim()) return [];
  const q = query.toLowerCase();
  const results: AutocompleteItem[] = [];
  for (const p of partners) {
    if (results.length >= 5) break;
    const item = partnerToItem(p);
    if (!item) continue;
    if (item.name.toLowerCase().includes(q) || (p.store_id && p.store_id.toLowerCase().includes(q)))
      results.push(item);
  }
  for (const s of stations) {
    if (results.length >= 5) break;
    if (s.nome.toLowerCase().includes(q)) results.push(stationToItem(s));
  }
  return results.slice(0, 5);
}

// ---------------------------------------------------------------------------
// AutocompleteInput
// ---------------------------------------------------------------------------

interface AutocompleteInputProps {
  id: string; placeholder: string; value: string;
  onChange: (val: string) => void; onSelect: (item: AutocompleteItem) => void;
  partners: Partner[]; stations: DeliveryStation[];
}

function AutocompleteInput({ id, placeholder, value, onChange, onSelect, partners, stations }: AutocompleteInputProps) {
  const [suggestions, setSuggestions] = useState<AutocompleteItem[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const results = searchItems(value, partners, stations);
    setSuggestions(results);
    setOpen(results.length > 0 && value.trim().length > 0);
  }, [value, partners, stations]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={containerRef} className="relative">
      <input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder} autoComplete="off"
        className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light placeholder-atlas-muted focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
      />
      {open && (
        <ul className="absolute z-50 left-0 right-0 mt-1 rounded border border-white/10 bg-atlas-navy shadow-lg overflow-hidden" role="listbox">
          {suggestions.map((item) => (
            <li key={item.id}>
              <button type="button" onMouseDown={() => { onChange(item.name); setOpen(false); onSelect(item); }}
                className="w-full text-left px-3 py-2 text-sm text-atlas-light hover:bg-white/10 transition-colors min-h-[44px] flex items-center" role="option" aria-selected={false}>
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
// HCP logic (ported from route-manager.js phases 1-2, simplified phase 3)
// ---------------------------------------------------------------------------

interface HcpMove { pickup: Partner; from: string | null; to: string }
interface HcpAssignment { hero: Partner; host: Partner }
interface HcpSuggestion { hostCandidate: Partner; pickups: Partner[] }
interface HcpResult {
  moves: HcpMove[];
  assignments: HcpAssignment[];
  suggestions: HcpSuggestion[];
}

async function runHcpPhases(currentFilteredData: Partner[]): Promise<HcpResult> {
  const groups = getCurrentHcpGroups(currentFilteredData);
  console.info('[HCP] Grupos:', { hosts: groups.hosts.length, pickups: groups.pickups.length, heros: groups.heros.length });

  const usedStores = new Set<string>();
  const moves: HcpMove[] = [];
  const assignments: HcpAssignment[] = [];
  const suggestions: HcpSuggestion[] = [];

  // Phase 1: reallocate existing pickups to nearest host within range
  if (groups.hosts.length > 0 && groups.pickups.length > 0) {
    const coords = [
      ...groups.pickups.map((p) => ({ lat: p.lat!, lon: p.lon! })),
      ...groups.hosts.map((h) => ({ lat: h.lat!, lon: h.lon! })),
    ];
    const sources = groups.pickups.map((_, i) => i);
    const destinations = groups.hosts.map((_, j) => groups.pickups.length + j);
    try {
      const matrix = await osrmTableMatrix(coords, sources, destinations);
      const hostCapacity = new Map(groups.hosts.map((h) => [h.store_id, 0]));
      for (let i = 0; i < groups.pickups.length; i++) {
        const pickup = groups.pickups[i];
        if (usedStores.has(pickup.store_id ?? '')) continue;
        const candidates = groups.hosts
          .map((host, j) => {
            const r = osrmResult(matrix.distances, matrix.durations, i, j);
            if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
            if ((hostCapacity.get(host.store_id ?? '') ?? 0) >= HCP_CONFIG.maxPickupsPerHost) return null;
            return { host, distance: r.distance };
          })
          .filter(Boolean)
          .sort((a, b) => a!.distance - b!.distance);
        if (!candidates.length) continue;
        const chosen = candidates[0]!.host;
        if (pickup.HCP_host_partner !== chosen.name)
          moves.push({ pickup, from: pickup.HCP_host_partner, to: chosen.name });
        hostCapacity.set(chosen.store_id ?? '', (hostCapacity.get(chosen.store_id ?? '') ?? 0) + 1);
        usedStores.add(pickup.store_id ?? '');
      }
      console.info('[HCP] Fase 1 concluída:', moves.length, 'movimentos');
    } catch (err) {
      console.error('[HCP] Fase 1 erro:', err);
    }
  }

  // Phase 2: assign Hub Heroes to existing hosts
  if (groups.hosts.length > 0 && groups.heros.length > 0) {
    const coords = [
      ...groups.heros.map((h) => ({ lat: h.lat!, lon: h.lon! })),
      ...groups.hosts.map((h) => ({ lat: h.lat!, lon: h.lon! })),
    ];
    const sources = groups.heros.map((_, i) => i);
    const destinations = groups.hosts.map((_, j) => groups.heros.length + j);
    try {
      const matrix = await osrmTableMatrix(coords, sources, destinations);
      const hostCapacity = new Map(groups.hosts.map((h) => [h.store_id, 0]));
      for (let i = 0; i < groups.heros.length; i++) {
        const hero = groups.heros[i];
        if (usedStores.has(hero.store_id ?? '')) continue;
        const candidates = groups.hosts
          .map((host, j) => {
            if ((hostCapacity.get(host.store_id ?? '') ?? 0) >= HCP_CONFIG.maxPickupsPerHost) return null;
            const r = osrmResult(matrix.distances, matrix.durations, i, j);
            if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
            return { host, distance: r.distance };
          })
          .filter(Boolean)
          .sort((a, b) => a!.distance - b!.distance);
        if (!candidates.length) continue;
        const chosen = candidates[0]!.host;
        assignments.push({ hero, host: chosen });
        hostCapacity.set(chosen.store_id ?? '', (hostCapacity.get(chosen.store_id ?? '') ?? 0) + 1);
        usedStores.add(hero.store_id ?? '');
      }
      console.info('[HCP] Fase 2 concluída:', assignments.length, 'alocações');
    } catch (err) {
      console.error('[HCP] Fase 2 erro:', err);
    }
  }

  // Phase 3: suggest new host clusters from remaining heros (simplified — no turf.js)
  const remainingHeros = groups.heros.filter((h) => !usedStores.has(h.store_id ?? ''));
  if (remainingHeros.length >= HCP_CONFIG.minClusterMembers) {
    // Simple greedy clustering: group by proximity
    const used3 = new Set<string>();
    for (const candidate of remainingHeros) {
      if (used3.has(candidate.store_id ?? '')) continue;
      const nearby = remainingHeros.filter((h) => {
        if (used3.has(h.store_id ?? '') || h.store_id === candidate.store_id) return false;
        const dlat = (h.lat! - candidate.lat!) * 111000;
        const dlon = (h.lon! - candidate.lon!) * 111000 * Math.cos((candidate.lat! * Math.PI) / 180);
        return Math.sqrt(dlat * dlat + dlon * dlon) <= HCP_CONFIG.maxDistanceM;
      }).slice(0, HCP_CONFIG.maxPickupsPerHost);
      if (nearby.length < HCP_CONFIG.minPickupsForNewHost) continue;
      suggestions.push({ hostCandidate: candidate, pickups: nearby });
      used3.add(candidate.store_id ?? '');
      nearby.forEach((h) => used3.add(h.store_id ?? ''));
    }
    console.info('[HCP] Fase 3 concluída:', suggestions.length, 'novos hosts sugeridos');
  }

  return { moves, assignments, suggestions };
}

// ---------------------------------------------------------------------------
// HCP Result Popup
// ---------------------------------------------------------------------------

function HcpPopup({ result, onClose }: { result: HcpResult; onClose: () => void }) {
  const totalActions = result.moves.length + result.assignments.length + result.suggestions.length;

  return createPortal(
    <div style={{
      position: 'fixed', top: '56px', right: '0', bottom: '0', width: 'clamp(360px, 28vw, 480px)',
      zIndex: 9000, backgroundColor: 'var(--color-navy)',
      borderLeft: '1px solid var(--border-color)',
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-3 shrink-0 border-b border-white/10">
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-atlas-light text-sm">HCP Initiatives</span>
          <span className="text-xs text-atlas-muted">{totalActions} sugestão{totalActions !== 1 ? 'ões' : ''}</span>
        </div>
        <button onClick={onClose} className="ml-2 text-atlas-muted hover:text-atlas-light transition-colors" aria-label="Fechar">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-4">

        {/* Fase 1 — Movimentos */}
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">
            📦 Fase 1 — Movimentos de Pickup
          </p>
          {result.moves.length === 0
            ? <p className="text-xs text-atlas-muted px-1">Nenhum movimento sugerido.</p>
            : <div className="flex flex-col gap-2">
                {result.moves.map((m, i) => (
                  <div key={i} className="rounded-lg bg-white/5 border border-white/5 p-3 flex flex-col gap-1">
                    <span className="text-sm font-semibold text-atlas-light leading-tight">{m.pickup.name}</span>
                    <div className="flex items-center gap-1 text-xs text-atlas-muted flex-wrap">
                      <span className="text-red-400">{m.from ?? 'N/A'}</span>
                      <span>→</span>
                      <span className="text-green-400">{m.to}</span>
                    </div>
                    {m.pickup.store_id && (
                      <span className="text-xs text-atlas-muted">ID: {m.pickup.store_id}</span>
                    )}
                  </div>
                ))}
              </div>
          }
        </div>

        {/* Fase 2 — Alocações */}
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">
            🏠 Fase 2 — Alocações em Hosts
          </p>
          {result.assignments.length === 0
            ? <p className="text-xs text-atlas-muted px-1">Nenhuma alocação sugerida.</p>
            : <div className="flex flex-col gap-2">
                {result.assignments.map((a, i) => (
                  <div key={i} className="rounded-lg bg-white/5 border border-white/5 p-3 flex flex-col gap-1">
                    <span className="text-sm font-semibold text-atlas-light leading-tight">{a.hero.name}</span>
                    <div className="flex items-center gap-1 text-xs">
                      <span className="text-atlas-muted">Host:</span>
                      <span className="text-atlas-accent font-medium">{a.host.name}</span>
                    </div>
                    {a.hero.store_id && (
                      <span className="text-xs text-atlas-muted">ID: {a.hero.store_id}</span>
                    )}
                  </div>
                ))}
              </div>
          }
        </div>

        {/* Fase 3 — Novos Hosts */}
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">
            ✨ Fase 3 — Novos Hosts Sugeridos
          </p>
          {result.suggestions.length === 0
            ? <p className="text-xs text-atlas-muted px-1">Nenhum novo host sugerido.</p>
            : <div className="flex flex-col gap-2">
                {result.suggestions.map((s, i) => (
                  <div key={i} className="rounded-lg bg-white/5 border border-white/5 p-3 flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-semibold text-atlas-light leading-tight">{s.hostCandidate.name}</span>
                      <span className="text-xs bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded px-1.5 py-0.5 shrink-0">
                        Host
                      </span>
                    </div>
                    {s.hostCandidate.store_id && (
                      <span className="text-xs text-atlas-muted">ID: {s.hostCandidate.store_id}</span>
                    )}
                    <div className="border-t border-white/10 pt-2">
                      <p className="text-xs text-atlas-muted mb-1">Pickups ({s.pickups.length}):</p>
                      <div className="flex flex-col gap-1">
                        {s.pickups.map((p) => (
                          <div key={p.store_id} className="flex items-center justify-between text-xs">
                            <span className="text-atlas-light">{p.name}</span>
                            {p.store_id && <span className="text-atlas-muted">{p.store_id}</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>

      </div>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// RoutesTab
// ---------------------------------------------------------------------------

interface StopEntry { key: string; text: string; resolved: AutocompleteItem | null }
let stopKeyCounter = 0;
function newStopKey() { return `stop-${++stopKeyCounter}`; }

export default function RoutesTab() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const deliveryStations = useStore((s) => s.deliveryStations);
  const filterState = useStore((s) => s.filterState);
  const setRoute = useStore((s) => s.setRoute);
  const clearRoute = useStore((s) => s.clearRoute);
  const setRouteOriginActive = useCallback(
    (v: boolean) => useStore.setState({ routeOriginActive: v }),
    []
  );

  const showHcpButton = useMemo(() => {
    const stations = filterState.selectedStations;
    return Array.isArray(stations) && stations.length === 1;
  }, [filterState.selectedStations]);

  const [originText, setOriginText] = useState('');
  const [originItem, setOriginItem] = useState<AutocompleteItem | null>(null);
  const [destText, setDestText] = useState('');
  const [destItem, setDestItem] = useState<AutocompleteItem | null>(null);
  const [stops, setStops] = useState<StopEntry[]>([]);
  const [hcpLoading, setHcpLoading] = useState(false);
  const [hcpResult, setHcpResult] = useState<HcpResult | null>(null);

  // Sync origin state to store so PartnerMarkers can show conditional buttons
  useEffect(() => {
    setRouteOriginActive(originItem != null);
  }, [originItem, setRouteOriginActive]);

  // Listen for popup route actions
  useEffect(() => {
    const handleOrigin = (e: Event) => {
      const item = (e as CustomEvent<AutocompleteItem>).detail;
      setOriginText(item.name);
      setOriginItem(item);
    };
    const handleDest = (e: Event) => {
      const item = (e as CustomEvent<AutocompleteItem>).detail;
      setDestText(item.name);
      setDestItem(item);
    };
    const handleAddStop = (e: Event) => {
      const item = (e as CustomEvent<AutocompleteItem>).detail;
      setStops((prev) => [...prev, { key: newStopKey(), text: item.name, resolved: item }]);
    };
    window.addEventListener('atlas:set-route-origin', handleOrigin);
    window.addEventListener('atlas:set-route-dest', handleDest);
    window.addEventListener('atlas:add-route-stop', handleAddStop);
    return () => {
      window.removeEventListener('atlas:set-route-origin', handleOrigin);
      window.removeEventListener('atlas:set-route-dest', handleDest);
      window.removeEventListener('atlas:add-route-stop', handleAddStop);
    };
  }, []);

  const handleAddStop = useCallback(() => {
    setStops((prev) => [...prev, { key: newStopKey(), text: '', resolved: null }]);
  }, []);

  const handleRemoveStop = useCallback((key: string) => {
    setStops((prev) => prev.filter((s) => s.key !== key));
  }, []);

  const handleMoveUp = useCallback((index: number) => {
    if (index === 0) return;
    setStops((prev) => { const n = [...prev]; [n[index - 1], n[index]] = [n[index], n[index - 1]]; return n; });
  }, []);

  const handleMoveDown = useCallback((index: number) => {
    setStops((prev) => {
      if (index >= prev.length - 1) return prev;
      const n = [...prev]; [n[index], n[index + 1]] = [n[index + 1], n[index]]; return n;
    });
  }, []);

  const handleFindRoute = useCallback(() => {
    const routeStops: RouteStop[] = [];
    if (originItem) routeStops.push(toRouteStop(originItem));
    for (const s of stops) { if (s.resolved) routeStops.push(toRouteStop(s.resolved)); }
    if (destItem) routeStops.push(toRouteStop(destItem));
    setRoute(routeStops);
  }, [originItem, stops, destItem, setRoute]);

  const handleClear = useCallback(() => {
    setOriginText(''); setOriginItem(null);
    setDestText(''); setDestItem(null);
    setStops([]); setHcpResult(null);
    setRouteOriginActive(false);
    clearRoute();
  }, [clearRoute, setRouteOriginActive]);

  const handleSuggestHcp = useCallback(async () => {
    setHcpLoading(true);
    setHcpResult(null);
    console.info('[HCP] Iniciando otimização de malha HCP...');
    try {
      const result = await runHcpPhases(currentFilteredData);
      console.info('[HCP] Otimização concluída:', result);
      setHcpResult(result);
    } catch (err) {
      console.error('[HCP] Erro na otimização:', err);
    } finally {
      setHcpLoading(false);
    }
  }, [currentFilteredData]);

  const canFindRoute = originItem != null && destItem != null;

  return (
    <div className="p-3">
      {/* Origem */}
      <div className="mb-3">
        <label htmlFor="route-origin" className="block text-xs font-medium text-atlas-muted mb-1">Origem</label>
        <AutocompleteInput id="route-origin" placeholder="Buscar parceiro ou estação..."
          value={originText} onChange={setOriginText} onSelect={setOriginItem}
          partners={allMarkersData} stations={deliveryStations} />
        {originItem && <p className="text-xs text-atlas-accent mt-1">✓ {originItem.name}</p>}
      </div>

      {/* Paradas */}
      {stops.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-atlas-muted mb-1">Paradas</p>
          <div className="flex flex-col gap-2">
            {stops.map((stop, index) => (
              <div key={stop.key} className="flex items-center gap-1">
                <div className="flex flex-col gap-0.5">
                  <button type="button" onClick={() => handleMoveUp(index)} disabled={index === 0} aria-label="Mover para cima"
                    className="w-6 h-5 flex items-center justify-center rounded text-xs bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed">▲</button>
                  <button type="button" onClick={() => handleMoveDown(index)} disabled={index === stops.length - 1} aria-label="Mover para baixo"
                    className="w-6 h-5 flex items-center justify-center rounded text-xs bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:cursor-not-allowed">▼</button>
                </div>
                <div className="flex-1">
                  <AutocompleteInput id={`stop-${stop.key}`} placeholder="Parada..."
                    value={stop.text}
                    onChange={(val) => setStops((prev) => prev.map((s) => s.key === stop.key ? { ...s, text: val, resolved: null } : s))}
                    onSelect={(item) => setStops((prev) => prev.map((s) => s.key === stop.key ? { ...s, text: item.name, resolved: item } : s))}
                    partners={allMarkersData} stations={deliveryStations} />
                </div>
                <button type="button" onClick={() => handleRemoveStop(stop.key)} aria-label="Remover parada"
                  className="w-8 h-8 flex items-center justify-center rounded bg-red-500/20 hover:bg-red-500/40 text-red-400 shrink-0">✕</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Destino */}
      <div className="mb-3">
        <label htmlFor="route-dest" className="block text-xs font-medium text-atlas-muted mb-1">Destino</label>
        <AutocompleteInput id="route-dest" placeholder="Buscar parceiro ou estação..."
          value={destText} onChange={setDestText} onSelect={setDestItem}
          partners={allMarkersData} stations={deliveryStations} />
        {destItem && <p className="text-xs text-atlas-accent mt-1">✓ {destItem.name}</p>}
      </div>

      <button type="button" onClick={handleAddStop}
        className="w-full py-2 px-4 rounded border border-white/20 text-atlas-muted text-sm hover:bg-white/5 hover:text-atlas-light focus:outline-none min-h-[44px] mb-3 transition-colors">
        + Adicionar Parada
      </button>

      <button type="button" onClick={handleFindRoute} disabled={!canFindRoute}
        className="w-full py-3 px-4 rounded bg-atlas-accent text-white text-sm font-semibold hover:opacity-90 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed min-h-[44px] mb-2 transition-colors">
        Buscar Melhor Rota
      </button>

      <button type="button" onClick={handleClear}
        className="w-full py-3 px-4 rounded bg-white/10 text-atlas-light text-sm font-medium hover:bg-white/20 focus:outline-none min-h-[44px] mb-2 transition-colors">
        Limpar Rota
      </button>

      {showHcpButton && (
        <button type="button" onClick={handleSuggestHcp} disabled={hcpLoading}
          className="w-full py-3 px-4 rounded bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 active:bg-purple-700 focus:outline-none disabled:opacity-50 min-h-[44px] transition-colors shadow-md">
          Sugerir HCP Initiatives
        </button>
      )}

      {/* HCP loading overlay — centro da tela via portal */}
      {hcpLoading && createPortal(
        <div style={{
          position: 'fixed', inset: 0, zIndex: 99999,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            background: 'var(--color-dark)', color: 'var(--color-light)', padding: '28px 36px',
            borderRadius: '10px', boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', gap: '16px', fontSize: '15px',
          }}>
            <svg style={{ animation: 'spin 1s linear infinite', width: 28, height: 28 }} viewBox="0 0 24 24" fill="none">
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              <circle cx="12" cy="12" r="10" stroke="#a78bfa" strokeWidth="4" strokeOpacity="0.25"/>
              <path fill="#a78bfa" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            Otimizando malha com HCP...
          </div>
        </div>,
        document.body
      )}

      {hcpResult && <HcpPopup result={hcpResult} onClose={() => setHcpResult(null)} />}
    </div>
  );
}
