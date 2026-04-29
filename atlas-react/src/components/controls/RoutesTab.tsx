/**
 * RoutesTab.tsx
 * =============
 * Aba de rotas: origem/destino/paradas com autocomplete + geocodificação Nominatim,
 * painel lateral com header de rota e cards de destino, sugestão HCP com 3 fases.
 */

import { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';
import { osrmTableMatrix, osrmResult, getCurrentHcpGroups } from '../../lib/routeUtils';
import { HCP_CONFIG } from '../../lib/config';
import type { RouteStop, Partner, DeliveryStation } from '../../store/types';
import type { RoutePickPin } from '../../store';

// ---------------------------------------------------------------------------
// Autocomplete + Geocodificação
// ---------------------------------------------------------------------------

type AutocompleteItem = { id: string; name: string; lat: number; lon: number; isAddress?: boolean };

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

async function geocodeAddress(query: string): Promise<AutocompleteItem | null> {
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'pt-BR,pt;q=0.9' } });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.length) return null;
    const r = data[0];
    return {
      id: `addr:${r.place_id}`,
      name: r.display_name,
      lat: parseFloat(r.lat),
      lon: parseFloat(r.lon),
      isAddress: true,
    };
  } catch {
    return null;
  }
}

/** Reverse geocode de uma coordenada clicada no mapa. Sempre retorna um item usável. */
async function reverseGeocode(lat: number, lon: number): Promise<AutocompleteItem> {
  const fallback: AutocompleteItem = {
    id: `pin:${lat.toFixed(6)},${lon.toFixed(6)}`,
    name: `${lat.toFixed(5)}, ${lon.toFixed(5)}`,
    lat,
    lon,
    isAddress: true,
  };
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'pt-BR,pt;q=0.9' } });
    if (!res.ok) return fallback;
    const data = await res.json();
    if (!data || !data.display_name) return fallback;
    return {
      id: `addr:${data.place_id ?? `${lat},${lon}`}`,
      name: data.display_name,
      lat,
      lon,
      isAddress: true,
    };
  } catch {
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// RouteSearchInput — autocomplete + geocodificação Nominatim
// ---------------------------------------------------------------------------

interface RouteSearchInputProps {
  id: string;
  placeholder: string;
  value: string;
  onChange: (val: string) => void;
  onSelect: (item: AutocompleteItem) => void;
  partners: Partner[];
  stations: DeliveryStation[];
  onFocus?: () => void;
  onBlur?: () => void;
}

function RouteSearchInput({ id, placeholder, value, onChange, onSelect, partners, stations, onFocus, onBlur }: RouteSearchInputProps) {
  const { t } = useTranslation();
  const [suggestions, setSuggestions] = useState<AutocompleteItem[]>([]);
  const [open, setOpen] = useState(false);
  const [isGeocoding, setIsGeocoding] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sugestões de parceiros/estações em tempo real
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

  const handleKeyDown = useCallback(async (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (suggestions.length > 0) {
      // Seleciona primeiro resultado de parceiro/estação
      onChange(suggestions[0].name);
      setOpen(false);
      onSelect(suggestions[0]);
      return;
    }
    // Nenhum parceiro encontrado — tenta geocodificar
    if (value.trim().length < 3) return;
    setIsGeocoding(true);
    setOpen(false);
    const result = await geocodeAddress(value.trim());
    setIsGeocoding(false);
    if (result) {
      onChange(result.name);
      onSelect(result);
    }
  }, [suggestions, value, onChange, onSelect]);

  const noPartnerMatch = value.trim().length >= 3 && suggestions.length === 0;

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center rounded bg-atlas-darker border border-[var(--border-color)] overflow-hidden focus-within:border-atlas-accent transition-colors">
        <span className="px-2 text-sm shrink-0 text-atlas-muted">
          {isGeocoding ? '⏳' : noPartnerMatch ? '📍' : '🔍'}
        </span>
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={onFocus}
          onBlur={onBlur}
          placeholder={placeholder}
          autoComplete="off"
          className="flex-1 bg-transparent border-none outline-none text-sm text-atlas-light py-2 pr-2 placeholder:text-atlas-muted/60 min-h-[44px]"
        />
        {isGeocoding && (
          <span className="px-2 text-xs text-atlas-muted animate-pulse">…</span>
        )}
      </div>

      {/* Dropdown de sugestões */}
      {open && (
        <ul className="absolute z-50 left-0 right-0 mt-1 rounded border border-[var(--border-color)] bg-atlas-navy shadow-lg overflow-hidden" role="listbox">
          {suggestions.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onMouseDown={() => { onChange(item.name); setOpen(false); onSelect(item); }}
                className="w-full text-left px-3 py-2 text-sm text-atlas-light hover:bg-atlas-dark transition-colors min-h-[44px] flex items-center"
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

      {/* Hint de geocodificação quando não há parceiro */}
      {noPartnerMatch && !open && !isGeocoding && (
        <p className="text-xs text-atlas-muted mt-1 px-1">
          {t('routes.geocode_hint')}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HCP logic
// ---------------------------------------------------------------------------

interface HcpMove { pickup: Partner; from: string | null; to: string }
interface HcpAssignment { hero: Partner; host: Partner }
interface HcpSuggestion { hostCandidate: Partner; pickups: Partner[] }
interface HcpResult { moves: HcpMove[]; assignments: HcpAssignment[]; suggestions: HcpSuggestion[] }

function _phase3Greedy(remainingHeros: Partner[], usedStores: Set<string>, suggestions: HcpSuggestion[]): void {
  for (const candidate of remainingHeros) {
    if (usedStores.has(candidate.store_id ?? '')) continue;
    const nearby = remainingHeros.filter((h) => {
      if (usedStores.has(h.store_id ?? '') || h.store_id === candidate.store_id) return false;
      const dlat = (h.lat! - candidate.lat!) * 111000;
      const dlon = (h.lon! - candidate.lon!) * 111000 * Math.cos((candidate.lat! * Math.PI) / 180);
      return Math.sqrt(dlat * dlat + dlon * dlon) <= HCP_CONFIG.maxDistanceM;
    }).slice(0, HCP_CONFIG.maxPickupsPerHost);
    if (nearby.length < HCP_CONFIG.minPickupsForNewHost) continue;
    suggestions.push({ hostCandidate: candidate, pickups: nearby });
    usedStores.add(candidate.store_id ?? '');
    nearby.forEach((h) => usedStores.add(h.store_id ?? ''));
  }
}

async function runHcpPhases(currentFilteredData: Partner[]): Promise<HcpResult> {
  const groups = getCurrentHcpGroups(currentFilteredData);
  const usedStores = new Set<string>();
  const moves: HcpMove[] = [];
  const assignments: HcpAssignment[] = [];
  const suggestions: HcpSuggestion[] = [];

  // Phase 1
  if (groups.hosts.length > 0 && groups.pickups.length > 0) {
    const coords = [...groups.pickups.map((p) => ({ lat: p.lat!, lon: p.lon! })), ...groups.hosts.map((h) => ({ lat: h.lat!, lon: h.lon! }))];
    try {
      const matrix = await osrmTableMatrix(coords, groups.pickups.map((_, i) => i), groups.hosts.map((_, j) => groups.pickups.length + j));
      const hostCapacity = new Map(groups.hosts.map((h) => [h.store_id, 0]));
      for (let i = 0; i < groups.pickups.length; i++) {
        const pickup = groups.pickups[i];
        if (usedStores.has(pickup.store_id ?? '')) continue;
        const candidates = groups.hosts.map((host, j) => {
          const r = osrmResult(matrix.distances, matrix.durations, i, j);
          if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
          if ((hostCapacity.get(host.store_id ?? '') ?? 0) >= HCP_CONFIG.maxPickupsPerHost) return null;
          return { host, distance: r.distance };
        }).filter(Boolean).sort((a, b) => a!.distance - b!.distance);
        if (!candidates.length) continue;
        const chosen = candidates[0]!.host;
        if (pickup.HCP_host_partner !== chosen.name) moves.push({ pickup, from: pickup.HCP_host_partner, to: chosen.name });
        hostCapacity.set(chosen.store_id ?? '', (hostCapacity.get(chosen.store_id ?? '') ?? 0) + 1);
        usedStores.add(pickup.store_id ?? '');
      }
    } catch (err) { console.error('[HCP] Fase 1 erro:', err); }
  }

  // Phase 2
  if (groups.hosts.length > 0 && groups.heros.length > 0) {
    const coords = [...groups.heros.map((h) => ({ lat: h.lat!, lon: h.lon! })), ...groups.hosts.map((h) => ({ lat: h.lat!, lon: h.lon! }))];
    try {
      const matrix = await osrmTableMatrix(coords, groups.heros.map((_, i) => i), groups.hosts.map((_, j) => groups.heros.length + j));
      const hostCapacity = new Map(groups.hosts.map((h) => [h.store_id, 0]));
      for (let i = 0; i < groups.heros.length; i++) {
        const hero = groups.heros[i];
        if (usedStores.has(hero.store_id ?? '')) continue;
        const candidates = groups.hosts.map((host, j) => {
          if ((hostCapacity.get(host.store_id ?? '') ?? 0) >= HCP_CONFIG.maxPickupsPerHost) return null;
          const r = osrmResult(matrix.distances, matrix.durations, i, j);
          if (!r || r.distance > HCP_CONFIG.maxDistanceM || r.duration > HCP_CONFIG.maxDurationS) return null;
          return { host, distance: r.distance };
        }).filter(Boolean).sort((a, b) => a!.distance - b!.distance);
        if (!candidates.length) continue;
        const chosen = candidates[0]!.host;
        assignments.push({ hero, host: chosen });
        hostCapacity.set(chosen.store_id ?? '', (hostCapacity.get(chosen.store_id ?? '') ?? 0) + 1);
        usedStores.add(hero.store_id ?? '');
      }
    } catch (err) { console.error('[HCP] Fase 2 erro:', err); }
  }

  // Phase 3 — k-means via turf, fallback greedy
  const remainingHeros = groups.heros.filter((h) => !usedStores.has(h.store_id ?? ''));
  if (remainingHeros.length >= HCP_CONFIG.minClusterMembers) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const turf = (window as any).turf;
    if (turf) {
      const k = Math.max(1, Math.ceil(remainingHeros.length / 5));
      const fc = turf.featureCollection(remainingHeros.map((h: Partner) => turf.point([h.lon!, h.lat!], { store_id: h.store_id })));
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let clustered: any = null;
      try { clustered = turf.clustersKmeans(fc, { numberOfClusters: k }); } catch { clustered = null; }
      if (clustered) {
        const clusterMap = new Map<number, Partner[]>();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        clustered.features.forEach((f: any) => {
          const cid: number = f.properties.cluster;
          const hero = remainingHeros.find((h) => h.store_id === f.properties.store_id);
          if (!hero) return;
          if (!clusterMap.has(cid)) clusterMap.set(cid, []);
          clusterMap.get(cid)!.push(hero);
        });
        for (const members of clusterMap.values()) {
          let cm = members;
          if (cm.length > HCP_CONFIG.maxClusterMembers) {
            const fcTmp = turf.featureCollection(cm.map((m: Partner) => turf.point([m.lon!, m.lat!])));
            const cTmp = turf.centroid(fcTmp);
            cm = [...cm].sort((a, b) => turf.distance(cTmp, turf.point([a.lon!, a.lat!])) - turf.distance(cTmp, turf.point([b.lon!, b.lat!]))).slice(0, HCP_CONFIG.maxClusterMembers);
          }
          const fc2 = turf.featureCollection(cm.map((m: Partner) => turf.point([m.lon!, m.lat!])));
          const centroid = turf.centroid(fc2);
          const maxDist = Math.max(...cm.map((m: Partner) => turf.distance(centroid, turf.point([m.lon!, m.lat!]), { units: 'kilometers' })));
          if (maxDist > HCP_CONFIG.clusterDensityKm || cm.length < HCP_CONFIG.minClusterMembers) continue;
          let hostCandidate: Partner | null = null; let hostDist = Infinity;
          for (const m of cm) { const d = turf.distance(centroid, turf.point([m.lon!, m.lat!]), { units: 'kilometers' }); if (d < hostDist) { hostDist = d; hostCandidate = m; } }
          if (!hostCandidate || usedStores.has(hostCandidate.store_id ?? '')) continue;
          const pickupCandidates = cm.filter((m: Partner) => m.store_id !== hostCandidate!.store_id);
          if (!pickupCandidates.length) continue;
          try {
            const coords = [...pickupCandidates.map((p: Partner) => ({ lat: p.lat!, lon: p.lon! })), { lat: hostCandidate.lat!, lon: hostCandidate.lon! }];
            const matrix = await osrmTableMatrix(coords, pickupCandidates.map((_: Partner, i: number) => i), [pickupCandidates.length]);
            const valid = pickupCandidates.filter((p: Partner, r: number) => {
              if (usedStores.has(p.store_id ?? '')) return false;
              const res = osrmResult(matrix.distances, matrix.durations, r, 0);
              return res && res.distance <= HCP_CONFIG.maxDistanceM && res.duration <= HCP_CONFIG.maxDurationS;
            }).slice(0, HCP_CONFIG.maxPickupsPerHost);
            if (valid.length < HCP_CONFIG.minPickupsForNewHost) continue;
            usedStores.add(hostCandidate.store_id ?? '');
            valid.forEach((p: Partner) => usedStores.add(p.store_id ?? ''));
            suggestions.push({ hostCandidate, pickups: valid });
          } catch { /* pula cluster */ }
        }
      } else { _phase3Greedy(remainingHeros, usedStores, suggestions); }
    } else { _phase3Greedy(remainingHeros, usedStores, suggestions); }
  }

  return { moves, assignments, suggestions };
}

// ---------------------------------------------------------------------------
// HCP Result Popup
// ---------------------------------------------------------------------------

function HcpPopup({ result, onClose }: { result: HcpResult; onClose: () => void }) {
  const { t } = useTranslation();
  const totalActions = result.moves.length + result.assignments.length + result.suggestions.length;
  return createPortal(
    <div style={{ position: 'fixed', top: '56px', right: '0', bottom: '0', width: 'clamp(360px, 28vw, 480px)', zIndex: 9000, backgroundColor: 'var(--color-navy)', borderLeft: '1px solid var(--border-color)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div className="flex items-start justify-between px-4 py-3 shrink-0 border-b border-[var(--border-color)]">
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-atlas-light text-sm">{t('routes.hcp_popup_title')}</span>
          <span className="text-xs text-atlas-muted">{t('routes.hcp_suggestions_other', { count: totalActions })}</span>
        </div>
        <button onClick={onClose} className="ml-2 text-atlas-muted hover:text-atlas-light transition-colors" aria-label={t('routes.hcp_popup_close')}>
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">{t('routes.hcp_phase1_title')}</p>
          {result.moves.length === 0 ? <p className="text-xs text-atlas-muted px-1">{t('routes.hcp_phase1_empty')}</p>
            : <div className="flex flex-col gap-2">{result.moves.map((m, i) => (
              <div key={i} className="rounded-lg bg-atlas-dark border border-[var(--border-color)] p-3 flex flex-col gap-1">
                <span className="text-sm font-semibold text-atlas-light leading-tight">{m.pickup.name}</span>
                <div className="flex items-center gap-1 text-xs text-atlas-muted flex-wrap"><span className="text-red-400">{m.from ?? 'N/A'}</span><span>→</span><span className="text-green-400">{m.to}</span></div>
                {m.pickup.store_id && <span className="text-xs text-atlas-muted">ID: {m.pickup.store_id}</span>}
              </div>))}</div>}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">{t('routes.hcp_phase2_title')}</p>
          {result.assignments.length === 0 ? <p className="text-xs text-atlas-muted px-1">{t('routes.hcp_phase2_empty')}</p>
            : <div className="flex flex-col gap-2">{result.assignments.map((a, i) => (
              <div key={i} className="rounded-lg bg-atlas-dark border border-[var(--border-color)] p-3 flex flex-col gap-1">
                <span className="text-sm font-semibold text-atlas-light leading-tight">{a.hero.name}</span>
                <div className="flex items-center gap-1 text-xs"><span className="text-atlas-muted">{t('routes.hcp_host_label')}</span><span className="text-atlas-accent font-medium">{a.host.name}</span></div>
                {a.hero.store_id && <span className="text-xs text-atlas-muted">ID: {a.hero.store_id}</span>}
              </div>))}</div>}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-atlas-muted mb-2 px-1">{t('routes.hcp_phase3_title')}</p>
          {result.suggestions.length === 0 ? <p className="text-xs text-atlas-muted px-1">{t('routes.hcp_phase3_empty')}</p>
            : <div className="flex flex-col gap-2">{result.suggestions.map((s, i) => (
              <div key={i} className="rounded-lg bg-atlas-dark border border-[var(--border-color)] p-3 flex flex-col gap-2">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-semibold text-atlas-light leading-tight">{s.hostCandidate.name}</span>
                  <span className="text-xs bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded px-1.5 py-0.5 shrink-0">{t('routes.hcp_host_badge')}</span>
                </div>
                {s.hostCandidate.store_id && <span className="text-xs text-atlas-muted">ID: {s.hostCandidate.store_id}</span>}
                <div className="border-t border-[var(--border-color)] pt-2">
                  <p className="text-xs text-atlas-muted mb-1">{t('routes.hcp_pickups_label', { count: s.pickups.length })}</p>
                  <div className="flex flex-col gap-1">{s.pickups.map((p) => (
                    <div key={p.store_id} className="flex items-center justify-between text-xs">
                      <span className="text-atlas-light">{p.name}</span>
                      {p.store_id && <span className="text-atlas-muted">{p.store_id}</span>}
                    </div>))}</div>
                </div>
              </div>))}</div>}
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
  const { t } = useTranslation();
  const allMarkersData = useStore((s) => s.allMarkersData);
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const deliveryStations = useStore((s) => s.deliveryStations);
  const filterState = useStore((s) => s.filterState);
  const setRoute = useStore((s) => s.setRoute);
  const clearRoute = useStore((s) => s.clearRoute);
  const setRouteOriginActive = useCallback((v: boolean) => useStore.setState({ routeOriginActive: v }), []);
  const setRouteInputFocused = useCallback((v: boolean) => useStore.setState({ routeInputFocused: v }), []);

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

  // Campo de rota atualmente focado — controla para onde vai uma coordenada clicada no mapa.
  // Usamos ref em vez de state para não re-registrar listeners a cada mudança de foco.
  const focusedFieldRef = useRef<'origin' | 'dest' | string | null>(null);
  const [pinFillingField, setPinFillingField] = useState<string | null>(null);

  useEffect(() => { setRouteOriginActive(originItem != null); }, [originItem, setRouteOriginActive]);
  // Libera a flag global ao desmontar o tab
  useEffect(() => () => { setRouteInputFocused(false); }, [setRouteInputFocused]);

  // Listeners de eventos do mapa (popup "Rota a partir daqui" etc.)
  useEffect(() => {
    const handleOrigin = (e: Event) => { const item = (e as CustomEvent<AutocompleteItem>).detail; setOriginText(item.name); setOriginItem(item); };
    const handleDest   = (e: Event) => { const item = (e as CustomEvent<AutocompleteItem>).detail; setDestText(item.name);   setDestItem(item); };
    const handleAddStop = (e: Event) => { const item = (e as CustomEvent<AutocompleteItem>).detail; setStops((prev) => [...prev, { key: newStopKey(), text: item.name, resolved: item }]); };
    window.addEventListener('atlas:set-route-origin', handleOrigin);
    window.addEventListener('atlas:set-route-dest',   handleDest);
    window.addEventListener('atlas:add-route-stop',   handleAddStop);
    return () => {
      window.removeEventListener('atlas:set-route-origin', handleOrigin);
      window.removeEventListener('atlas:set-route-dest',   handleDest);
      window.removeEventListener('atlas:add-route-stop',   handleAddStop);
    };
  }, []);

  // Clique no mapa enquanto um campo de rota está focado → preenche o campo com a coordenada (reverse geocode)
  useEffect(() => {
    const handleClick = async (e: Event) => {
      const target = focusedFieldRef.current;
      if (!target) return;
      const detail = (e as CustomEvent<{ lat: number; lng: number }>).detail;
      if (!detail) return;
      setPinFillingField(target);
      const item = await reverseGeocode(detail.lat, detail.lng);
      if (target === 'origin') {
        setOriginText(item.name);
        setOriginItem(item);
      } else if (target === 'dest') {
        setDestText(item.name);
        setDestItem(item);
      } else {
        const stopKey = target;
        setStops((prev) => prev.map((s) => s.key === stopKey ? { ...s, text: item.name, resolved: item } : s));
      }
      setPinFillingField(null);
    };
    document.addEventListener('atlas:map-click-coords', handleClick);
    return () => document.removeEventListener('atlas:map-click-coords', handleClick);
  }, []);

  // Sincroniza os pins draggable no mapa a partir dos itens resolvidos
  useEffect(() => {
    const pins: RoutePickPin[] = [];
    if (originItem) pins.push({ field: 'origin', lat: originItem.lat, lon: originItem.lon, label: originItem.name });
    for (const s of stops) {
      if (s.resolved) pins.push({ field: s.key, lat: s.resolved.lat, lon: s.resolved.lon, label: s.resolved.name });
    }
    if (destItem) pins.push({ field: 'dest', lat: destItem.lat, lon: destItem.lon, label: destItem.name });
    useStore.setState({ routePickPins: pins });
  }, [originItem, destItem, stops]);

  // Limpa os pins ao desmontar o tab
  useEffect(() => () => { useStore.setState({ routePickPins: [] }); }, []);

  // Drag de pin no mapa → atualiza o campo com a nova coordenada (reverse geocode)
  useEffect(() => {
    const handleDrag = async (e: Event) => {
      const detail = (e as CustomEvent<{ field: string; lat: number; lng: number }>).detail;
      if (!detail) return;
      const { field, lat, lng } = detail;
      setPinFillingField(field);
      const item = await reverseGeocode(lat, lng);
      if (field === 'origin') {
        setOriginText(item.name);
        setOriginItem(item);
      } else if (field === 'dest') {
        setDestText(item.name);
        setDestItem(item);
      } else {
        setStops((prev) => prev.map((s) => s.key === field ? { ...s, text: item.name, resolved: item } : s));
      }
      setPinFillingField(null);
    };
    document.addEventListener('atlas:route-pin-dragged', handleDrag);
    return () => document.removeEventListener('atlas:route-pin-dragged', handleDrag);
  }, []);

  const handleFieldFocus = useCallback((field: 'origin' | 'dest' | string) => {
    focusedFieldRef.current = field;
    setRouteInputFocused(true);
  }, [setRouteInputFocused]);

  const handleFieldBlur = useCallback(() => {
    // Pequeno atraso para permitir que um clique no mapa ocorra antes do blur desativar o estado
    setTimeout(() => {
      focusedFieldRef.current = null;
      setRouteInputFocused(false);
    }, 150);
  }, [setRouteInputFocused]);

  const handleAddStop    = useCallback(() => { setStops((prev) => [...prev, { key: newStopKey(), text: '', resolved: null }]); }, []);
  const handleRemoveStop = useCallback((key: string) => { setStops((prev) => prev.filter((s) => s.key !== key)); }, []);
  const handleMoveUp     = useCallback((index: number) => { if (index === 0) return; setStops((prev) => { const n = [...prev]; [n[index-1], n[index]] = [n[index], n[index-1]]; return n; }); }, []);
  const handleMoveDown   = useCallback((index: number) => { setStops((prev) => { if (index >= prev.length-1) return prev; const n = [...prev]; [n[index], n[index+1]] = [n[index+1], n[index]]; return n; }); }, []);

  const handleFindRoute = useCallback(() => {
    const routeStops: RouteStop[] = [];
    if (originItem) routeStops.push(toRouteStop(originItem));
    for (const s of stops) { if (s.resolved) routeStops.push(toRouteStop(s.resolved)); }
    if (destItem) routeStops.push(toRouteStop(destItem));
    setRoute(routeStops);
  }, [originItem, stops, destItem, setRoute]);

  const handleClear = useCallback(() => {
    setOriginText(''); setOriginItem(null);
    setDestText('');   setDestItem(null);
    setStops([]); setHcpResult(null);
    setRouteOriginActive(false);
    clearRoute();
  }, [clearRoute, setRouteOriginActive]);

  const handleSuggestHcp = useCallback(async () => {
    setHcpLoading(true); setHcpResult(null);
    try { const result = await runHcpPhases(currentFilteredData); setHcpResult(result); }
    catch (err) { console.error('[HCP] Erro:', err); }
    finally { setHcpLoading(false); }
  }, [currentFilteredData]);

  const isCircularRoute  = originItem != null && destItem != null && originItem.id === destItem.id;
  const hasResolvedStops = stops.some((s) => s.resolved != null);
  const canFindRoute     = originItem != null && destItem != null && (!isCircularRoute || hasResolvedStops);

  return (
    <div className="p-3 flex flex-col gap-3">

      {/* ── Origem ── */}
      <div>
        <label htmlFor="route-origin" className="block text-xs font-medium text-atlas-muted mb-1">
          {t('routes.origin_label')}
        </label>
        <RouteSearchInput
          id="route-origin"
          placeholder={t('routes.origin_placeholder')}
          value={originText}
          onChange={(val) => { setOriginText(val); setOriginItem(null); }}
          onSelect={(item) => { setOriginText(item.name); setOriginItem(item); }}
          partners={allMarkersData}
          stations={deliveryStations}
          onFocus={() => handleFieldFocus('origin')}
          onBlur={handleFieldBlur}
        />
        {pinFillingField === 'origin' && (
          <p className="text-xs text-atlas-muted mt-1 px-1 animate-pulse">📍 {t('routes.map_pick_filling', { defaultValue: 'Obtendo endereço do ponto clicado…' })}</p>
        )}
        {originItem && (
          <p className="text-xs text-atlas-accent mt-1 flex items-center gap-1">
            <span>{originItem.isAddress ? '📍' : '✓'}</span>
            <span className="truncate">{originItem.name}</span>
          </p>
        )}
      </div>

      {/* ── Destino ── */}
      <div>
        <label htmlFor="route-dest" className="block text-xs font-medium text-atlas-muted mb-1">
          {t('routes.dest_label')}
        </label>
        <RouteSearchInput
          id="route-dest"
          placeholder={t('routes.dest_placeholder')}
          value={destText}
          onChange={(val) => { setDestText(val); setDestItem(null); }}
          onSelect={(item) => { setDestText(item.name); setDestItem(item); }}
          partners={allMarkersData}
          stations={deliveryStations}
          onFocus={() => handleFieldFocus('dest')}
          onBlur={handleFieldBlur}
        />
        {pinFillingField === 'dest' && (
          <p className="text-xs text-atlas-muted mt-1 px-1 animate-pulse">📍 {t('routes.map_pick_filling', { defaultValue: 'Obtendo endereço do ponto clicado…' })}</p>
        )}
        {destItem && (
          <p className="text-xs text-atlas-accent mt-1 flex items-center gap-1">
            <span>{destItem.isAddress ? '📍' : '✓'}</span>
            <span className="truncate">{destItem.name}</span>
          </p>
        )}
      </div>

      {/* ── Paradas intermediárias + botão adicionar ── */}
      {/* O botão só aparece quando origem e destino estão preenchidos */}
      {originItem && destItem && (
        <div className="flex flex-col gap-2">
          {stops.length > 0 && (
            <>
              <p className="text-xs font-medium text-atlas-muted">{t('routes.stops_label')}</p>
              {stops.map((stop, index) => (
                <div key={stop.key} className="flex items-start gap-1">
                  <div className="flex flex-col gap-0.5 pt-1">
                    <button type="button" onClick={() => handleMoveUp(index)} disabled={index === 0} aria-label={t('routes.stop_move_up')}
                      className="w-6 h-5 flex items-center justify-center rounded text-xs bg-atlas-dark hover:bg-atlas-dark disabled:opacity-30 disabled:cursor-not-allowed">▲</button>
                    <button type="button" onClick={() => handleMoveDown(index)} disabled={index === stops.length - 1} aria-label={t('routes.stop_move_down')}
                      className="w-6 h-5 flex items-center justify-center rounded text-xs bg-atlas-dark hover:bg-atlas-dark disabled:opacity-30 disabled:cursor-not-allowed">▼</button>
                  </div>
                  <div className="flex-1">
                    <RouteSearchInput
                      id={`stop-${stop.key}`}
                      placeholder={t('routes.stop_placeholder')}
                      value={stop.text}
                      onChange={(val) => setStops((prev) => prev.map((s) => s.key === stop.key ? { ...s, text: val, resolved: null } : s))}
                      onSelect={(item) => setStops((prev) => prev.map((s) => s.key === stop.key ? { ...s, text: item.name, resolved: item } : s))}
                      partners={allMarkersData}
                      stations={deliveryStations}
                      onFocus={() => handleFieldFocus(stop.key)}
                      onBlur={handleFieldBlur}
                    />
                    {pinFillingField === stop.key && (
                      <p className="text-xs text-atlas-muted mt-0.5 px-1 animate-pulse">📍 {t('routes.map_pick_filling', { defaultValue: 'Obtendo endereço do ponto clicado…' })}</p>
                    )}
                    {stop.resolved && (
                      <p className="text-xs text-atlas-accent mt-0.5 flex items-center gap-1">
                        <span>{stop.resolved.isAddress ? '📍' : '✓'}</span>
                        <span className="truncate">{stop.resolved.name}</span>
                      </p>
                    )}
                  </div>
                  <button type="button" onClick={() => handleRemoveStop(stop.key)} aria-label={t('routes.stop_remove')}
                    className="w-8 h-8 flex items-center justify-center rounded bg-red-500/20 hover:bg-red-500/40 text-red-400 shrink-0 mt-0.5">✕</button>
                </div>
              ))}
            </>
          )}

          {/* Botão adicionar parada — sempre abaixo da última parada */}
          <button type="button" onClick={handleAddStop}
            className="w-full py-2 px-4 rounded border border-[var(--border-color)] text-atlas-muted text-sm hover:border-atlas-accent hover:text-atlas-accent focus:outline-none min-h-[44px] transition-colors">
            {t('routes.add_stop')}
          </button>
        </div>
      )}

      {/* ── Avisos de rota circular ── */}
      {isCircularRoute && !hasResolvedStops && (
        <p className="text-xs text-yellow-400 px-1">⚠️ {t('routes.circular_needs_stops')}</p>
      )}
      {isCircularRoute && hasResolvedStops && (
        <p className="text-xs text-atlas-accent px-1">🔄 {t('routes.circular_route')}</p>
      )}

      {/* ── Botões de ação ── */}
      <button type="button" onClick={handleFindRoute} disabled={!canFindRoute}
        className="w-full py-3 px-4 rounded bg-atlas-accent text-white text-sm font-semibold hover:opacity-90 focus:outline-none disabled:opacity-40 disabled:cursor-not-allowed min-h-[44px] transition-colors">
        {t('routes.find_route')}
      </button>

      <button type="button" onClick={handleClear}
        className="w-full py-3 px-4 rounded bg-atlas-dark text-atlas-light text-sm font-medium hover:bg-atlas-dark focus:outline-none min-h-[44px] transition-colors">
        {t('routes.clear_route')}
      </button>

      {showHcpButton && (
        <button type="button" onClick={handleSuggestHcp} disabled={hcpLoading}
          className="w-full py-3 px-4 rounded bg-purple-600 text-white text-sm font-semibold hover:bg-purple-500 active:bg-purple-700 focus:outline-none disabled:opacity-50 min-h-[44px] transition-colors shadow-md">
          {t('routes.suggest_hcp')}
        </button>
      )}

      {/* HCP loading overlay */}
      {hcpLoading && createPortal(
        <div style={{ position: 'fixed', inset: 0, zIndex: 99999, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'var(--color-dark)', color: 'var(--color-light)', padding: '28px 36px', borderRadius: '10px', boxShadow: '0 4px 24px rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', gap: '16px', fontSize: '15px' }}>
            <svg style={{ animation: 'spin 1s linear infinite', width: 28, height: 28 }} viewBox="0 0 24 24" fill="none">
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              <circle cx="12" cy="12" r="10" stroke="#a78bfa" strokeWidth="4" strokeOpacity="0.25"/>
              <path fill="#a78bfa" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            {t('routes.hcp_loading')}
          </div>
        </div>,
        document.body
      )}

      {hcpResult && <HcpPopup result={hcpResult} onClose={() => setHcpResult(null)} />}
    </div>
  );
}
