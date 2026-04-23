/**
 * ManualAnalysisPanel.tsx
 * =======================
 * Painel lateral direito de Análise Manual de Área Recrutável.
 *
 * Quando aberto:
 * - A SearchBar padrão some do mapa
 * - Este painel incorpora a busca (parceiros + geocodificação Nominatim)
 * - Selecionar um parceiro: voa até ele e preenche lat/lon
 * - Buscar um endereço: geocodifica, coloca pin no mapa e preenche lat/lon
 * - Clique no mapa também preenche lat/lon
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../store';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { useDebounce } from '../../hooks/useDebounce';
import type { Partner, ReasonCode } from '../../store/types';
import { evaluateRecruitableArea, isEvaluatorError } from '../../lib/recruitableAreaEvaluator';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isValidPositiveNumber(value: string | number): boolean {
  if (value === '' || value === null || value === undefined) return false;
  const num = typeof value === 'string' ? Number(value) : value;
  return !isNaN(num) && num > 0;
}

const REASON_LABELS: Record<ReasonCode, string> = {
  INSUFFICIENT_RESIDUAL_DEMAND: 'Demanda residual insuficiente',
  NO_HEATMAP_COVERAGE: 'Área sem cobertura de heatmap',
  INSUFFICIENT_TOTAL_DEMAND: 'Demanda total insuficiente',
};

interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
}

// ---------------------------------------------------------------------------
// RecruitableResultPanel
// ---------------------------------------------------------------------------

function RecruitableResultPanel({
  result,
  isStale,
}: {
  result: import('../../store/types').EvaluatorResult;
  isStale: boolean;
}) {
  const { totalDemand, residualDemand, minAdv, gap, viable, reason } = result;
  const barWidth = minAdv > 0 ? Math.min((residualDemand / minAdv) * 100, 100) : 0;
  const displayPct = minAdv > 0 ? ((residualDemand / minAdv) * 100).toFixed(0) : '0';

  return (
    <div
      className={`rounded-lg border p-3 flex flex-col gap-3 ${isStale ? 'border-yellow-500/50 bg-yellow-500/5' : 'border-white/10 bg-white/5'}`}
      data-testid="recruitable-result-panel"
    >
      {isStale && (
        <div className="flex items-center gap-2 px-2 py-1 rounded bg-yellow-500/10 border border-yellow-500/30 text-xs text-yellow-400" role="alert">
          ⚠️ Resultado desatualizado — parâmetros foram alterados
        </div>
      )}

      <div className="flex items-center gap-2">
        {viable ? (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-green-500/20 border border-green-500/40 text-green-400 text-sm font-semibold">
            ✓ Viável
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 text-sm font-semibold">
            ✗ Não Viável
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded bg-white/5 px-2 py-2">
          <div className="text-atlas-muted mb-0.5">Demanda Total</div>
          <div className="text-atlas-light font-semibold">{Math.round(totalDemand)} pct/dia</div>
        </div>
        <div className="rounded bg-white/5 px-2 py-2">
          <div className="text-atlas-muted mb-0.5">Demanda Residual</div>
          <div className="text-atlas-light font-semibold">{Math.round(residualDemand)} pct/dia</div>
        </div>
        <div className="rounded bg-white/5 px-2 py-2">
          <div className="text-atlas-muted mb-0.5">ADV Mínimo</div>
          <div className="text-atlas-light font-semibold">{minAdv} pct/dia</div>
        </div>
        <div className="rounded bg-white/5 px-2 py-2">
          <div className="text-atlas-muted mb-0.5">Gap</div>
          <div className={`font-semibold ${gap >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {gap >= 0 ? '+' : ''}{Math.round(gap)} pct/dia
          </div>
        </div>
      </div>

      <div>
        <div className="flex justify-between text-xs text-atlas-muted mb-1">
          <span>Cobertura de demanda residual</span>
          <span className={viable ? 'text-green-400' : 'text-red-400'}>{displayPct}%</span>
        </div>
        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${viable ? 'bg-green-500' : 'bg-red-500'}`}
            style={{ width: `${barWidth}%` }}
            role="progressbar"
            aria-valuenow={Number(displayPct)}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <div className="flex justify-between text-xs text-atlas-muted mt-0.5">
          <span>0%</span>
          <span>100%+</span>
        </div>
      </div>

      {!viable && reason && (
        <div className="px-3 py-2 rounded bg-red-500/10 border-l-2 border-red-400 text-xs text-atlas-muted">
          <span className="text-red-400 font-semibold">Motivo:</span>{' '}
          <span className="text-atlas-light">{REASON_LABELS[reason]}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PanelContent
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// WhatIfResult type (mirrors atlas:whatif-result event detail)
// ---------------------------------------------------------------------------

interface WhatIfResult {
  partnerName: string;
  simulatedLat: number;
  simulatedLon: number;
  advSimulated: number;
  simulatedRadius: number;
  advGain: number;
  originalCap: number;
}

// ---------------------------------------------------------------------------
// PanelContent
// ---------------------------------------------------------------------------

function PanelContent({ onClose }: { onClose: () => void }) {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const recruitableAnalysis = useStore((s) => s.recruitableAnalysis);
  const setRecruitableParams = useStore((s) => s.setRecruitableParams);
  const setRecruitableResult = useStore((s) => s.setRecruitableResult);
  const clearRecruitableAnalysis = useStore((s) => s.clearRecruitableAnalysis);
  const heatmapData = useStore((s) => s.heatmapData);
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);
  const setManualAnalysisPin = useStore((s) => s.setManualAnalysisPin);
  const whatIfModeActive = useStore((s) => s.whatIfModeActive);
  const setWhatIfModeActive = useStore((s) => s.setWhatIfModeActive);

  // --- What-if state ---
  const [whatIfResult, setWhatIfResult] = useState<WhatIfResult | null>(null);
  const [whatIfWarning, setWhatIfWarning] = useState<string | null>(null);

  // --- Search state ---
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Partner[]>([]);
  const [addressMode, setAddressMode] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [isGeocoding, setIsGeocoding] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebounce(query, 300);

  const { params } = recruitableAnalysis;
  const advStr = String(params.minAdv);
  const radiusStr = String(params.radiusMeters);
  const advValid = isValidPositiveNumber(params.minAdv);
  const radiusValid = isValidPositiveNumber(params.radiusMeters);
  const latValid = params.centerLat !== '' && !isNaN(Number(params.centerLat));
  const lonValid = params.centerLon !== '' && !isNaN(Number(params.centerLon));
  const canAnalyze = advValid && radiusValid && latValid && lonValid;

  const partners = useMemo(
    () => allMarkersData.filter((p) => p.lat != null && p.lon != null),
    [allMarkersData],
  );

  // Filter partners on debounced query
  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setSuggestions([]);
      setDropdownOpen(false);
      setAddressMode(false);
      return;
    }
    const lower = debouncedQuery.toLowerCase();
    const filtered = partners.filter((p) => p.name.toLowerCase().includes(lower));
    setSuggestions(filtered.slice(0, 8));
    setAddressMode(filtered.length === 0);
    setDropdownOpen(true);
    setActiveIndex(-1);
    setSearchError(null);
  }, [debouncedQuery, partners]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Map click listener
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ lat: number; lng: number }>).detail;
      if (detail) {
        setRecruitableParams({ centerLat: String(detail.lat), centerLon: String(detail.lng) });
        setManualAnalysisPin(null); // remove pin ao clicar no mapa (coordenada manual)
      }
    };
    document.addEventListener('atlas:map-click-coords', handler);
    return () => document.removeEventListener('atlas:map-click-coords', handler);
  }, [setRecruitableParams, setManualAnalysisPin]);

  // What-if result listener — atualiza coords e roda análise automaticamente
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<WhatIfResult>).detail;
      if (!detail) return;

      setWhatIfResult(detail);
      setWhatIfWarning(null);

      // Lê os parâmetros atuais do store (minAdv, radiusMeters)
      const store = useStore.getState();
      const { minAdv, radiusMeters } = store.recruitableAnalysis.params;

      // Atualiza as coordenadas do painel com a posição simulada
      store.setRecruitableParams({
        centerLat: String(detail.simulatedLat),
        centerLon: String(detail.simulatedLon),
      });

      // Roda análise automaticamente se os parâmetros forem válidos
      if (!isValidPositiveNumber(minAdv) || !isValidPositiveNumber(radiusMeters)) return;

      const features = store.heatmapData?.features ?? [];
      const result = evaluateRecruitableArea({
        centerLat: detail.simulatedLat,
        centerLon: detail.simulatedLon,
        radiusMeters,
        minAdv,
        heatmapFeatures: features,
      });

      if (isEvaluatorError(result)) {
        const msgs: Record<string, string> = {
          MISSING_HEATMAP: 'Dados de demanda não carregados',
          MISSING_CENTER: 'Ponto central obrigatório',
          INVALID_PARAMS: 'Parâmetros inválidos',
        };
        store.setRecruitableResult(null, msgs[result.type] ?? 'Erro desconhecido');
      } else {
        store.setRecruitableResult(result);
      }
    };
    document.addEventListener('atlas:whatif-result', handler);
    return () => document.removeEventListener('atlas:whatif-result', handler);
  }, []);

  // What-if warning listener
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ message: string }>).detail;
      if (detail?.message) {
        setWhatIfWarning(detail.message);
      }
    };
    document.addEventListener('atlas:whatif-warning', handler);
    return () => document.removeEventListener('atlas:whatif-warning', handler);
  }, []);

  // Reset what-if state when mode is deactivated
  useEffect(() => {
    if (!whatIfModeActive) {
      setWhatIfResult(null);
      setWhatIfWarning(null);
    }
  }, [whatIfModeActive]);

  const flyTo = useCallback((lat: number, lon: number) => {
    fitBoundsRef.current?.([[lat, lon]]);
  }, [fitBoundsRef]);

  const selectPartner = useCallback((partner: Partner) => {
    if (partner.lat != null && partner.lon != null) {
      flyTo(partner.lat, partner.lon);
      setRecruitableParams({ centerLat: String(partner.lat), centerLon: String(partner.lon) });
      setManualAnalysisPin(null);
    }
    setQuery(partner.name);
    setDropdownOpen(false);
    setSuggestions([]);
    setAddressMode(false);
    setSearchError(null);
  }, [flyTo, setRecruitableParams, setManualAnalysisPin]);

  const geocodeAddress = useCallback(async (q: string) => {
    setSearchError(null);
    setDropdownOpen(false);
    setAddressMode(false);
    setIsGeocoding(true);
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`;
      const res = await fetch(url, { headers: { 'Accept-Language': 'pt-BR,pt;q=0.9' } });
      if (!res.ok) throw new Error('Falha na geocodificação');
      const data: NominatimResult[] = await res.json();
      if (data.length === 0) { setSearchError('Endereço não encontrado'); return; }
      const lat = parseFloat(data[0].lat);
      const lon = parseFloat(data[0].lon);
      flyTo(lat, lon);
      setRecruitableParams({ centerLat: String(lat), centerLon: String(lon) });
      setManualAnalysisPin({ lat, lon, label: data[0].display_name });
      setQuery(data[0].display_name);
    } catch {
      setSearchError('Erro ao buscar endereço');
    } finally {
      setIsGeocoding(false);
    }
  }, [flyTo, setRecruitableParams, setManualAnalysisPin]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') { setDropdownOpen(false); setActiveIndex(-1); inputRef.current?.blur(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1)); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex((i) => Math.max(i - 1, -1)); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && suggestions[activeIndex]) { selectPartner(suggestions[activeIndex]); return; }
      if (query.trim().length >= 2) geocodeAddress(query.trim());
    }
  }, [activeIndex, suggestions, query, selectPartner, geocodeAddress]);

  const handleAnalyze = useCallback(() => {
    const features = heatmapData?.features ?? [];
    const result = evaluateRecruitableArea({
      centerLat: Number(params.centerLat),
      centerLon: Number(params.centerLon),
      radiusMeters: params.radiusMeters,
      minAdv: params.minAdv,
      heatmapFeatures: features,
    });
    if (isEvaluatorError(result)) {
      const msgs: Record<string, string> = {
        MISSING_HEATMAP: 'Dados de demanda não carregados',
        MISSING_CENTER: 'Ponto central obrigatório',
        INVALID_PARAMS: 'Parâmetros inválidos',
      };
      setRecruitableResult(null, msgs[result.type] ?? 'Erro desconhecido');
    } else {
      setRecruitableResult(result);
    }
  }, [params, heatmapData, setRecruitableResult]);

  return (
    <div className="flex flex-col h-full bg-atlas-navy text-atlas-light">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-white/10">
        <span className="font-semibold text-atlas-light text-sm">Análise Manual</span>
        <button onClick={onClose} aria-label="Fechar painel" className="text-atlas-muted hover:text-atlas-light transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Map click hint */}
      <div className="px-4 py-2 shrink-0 bg-indigo-500/10 border-b border-indigo-500/20 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" />
        <span className="text-xs text-indigo-300">Clique no mapa para definir o ponto central</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

        {/* ---- Busca integrada ---- */}
        <div ref={containerRef} className="relative">
          <label className="block text-xs font-medium text-atlas-muted mb-1">
            Buscar parceiro ou endereço
          </label>
          <div className="flex items-center rounded bg-atlas-darker border border-white/10 overflow-hidden focus-within:border-atlas-accent transition-colors">
            <span className="px-3 text-sm shrink-0">{addressMode ? '📍' : '🔍'}</span>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setSearchError(null); }}
              onKeyDown={handleKeyDown}
              onFocus={() => { if (dropdownOpen || suggestions.length > 0 || addressMode) setDropdownOpen(true); }}
              placeholder="Nome do parceiro ou endereço…"
              aria-label="Buscar parceiro ou endereço"
              aria-autocomplete="list"
              aria-expanded={dropdownOpen}
              className="flex-1 bg-transparent border-none outline-none text-sm text-atlas-light py-3 pr-2 placeholder:text-atlas-muted/60"
              autoComplete="off"
            />
            {isGeocoding && <span className="px-3 text-xs text-atlas-muted animate-pulse">…</span>}
            {query && !isGeocoding && (
              <button
                type="button"
                onClick={() => { setQuery(''); setSuggestions([]); setDropdownOpen(false); setAddressMode(false); setSearchError(null); inputRef.current?.focus(); }}
                aria-label="Limpar busca"
                className="px-3 text-xs text-atlas-muted hover:text-atlas-light transition-colors"
              >
                ✕
              </button>
            )}
          </div>

          {searchError && (
            <p className="mt-1 text-xs text-red-400" role="alert">{searchError}</p>
          )}

          {/* Dropdown */}
          {dropdownOpen && (
            <ul
              role="listbox"
              className="absolute left-0 right-0 mt-1 rounded-lg bg-atlas-darker border border-white/10 shadow-lg overflow-hidden max-h-64 overflow-y-auto z-50"
            >
              {/* Geocode option */}
              {addressMode && query.trim().length >= 2 && (
                <li
                  role="option"
                  aria-selected={false}
                  onMouseDown={(e) => { e.preventDefault(); geocodeAddress(query.trim()); }}
                  className="flex flex-col px-3 py-2 cursor-pointer hover:bg-white/5 border-b border-white/5 bg-orange-500/5"
                >
                  <span className="text-sm text-atlas-light font-medium">📍 Buscar endereço: <em className="not-italic text-atlas-accent">{query}</em></span>
                  <span className="text-xs text-atlas-muted mt-0.5">Pressione Enter ou clique para geocodificar</span>
                </li>
              )}
              {/* Partner suggestions */}
              {suggestions.map((partner, idx) => (
                <li
                  key={partner.salesforce_id}
                  role="option"
                  aria-selected={idx === activeIndex}
                  onMouseDown={(e) => { e.preventDefault(); selectPartner(partner); }}
                  onMouseEnter={() => setActiveIndex(idx)}
                  className={`flex flex-col px-3 py-2 cursor-pointer border-b border-white/5 transition-colors ${idx === activeIndex ? 'bg-white/10' : 'hover:bg-white/5'}`}
                >
                  <span className="text-sm text-atlas-light font-medium">{partner.name}</span>
                  {partner.city && (
                    <span className="text-xs text-atlas-muted mt-0.5">
                      {partner.city}{partner.state ? `, ${partner.state}` : ''} · {partner.status}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* ---- ADV mínimo ---- */}
        <div>
          <label htmlFor="manual-adv" className="block text-xs font-medium text-atlas-muted mb-1">
            ADV mínimo <span className="font-normal">(pacotes/dia)</span>
          </label>
          <input
            id="manual-adv"
            type="number"
            min={1}
            value={advStr}
            onChange={(e) => setRecruitableParams({ minAdv: e.target.value === '' ? 0 : Number(e.target.value) })}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          />
          {!advValid && <p className="mt-1 text-xs text-red-400" role="alert">Informe um valor positivo maior que zero.</p>}
        </div>

        {/* ---- Raio ---- */}
        <div>
          <label htmlFor="manual-radius" className="block text-xs font-medium text-atlas-muted mb-1">
            Raio de entrega <span className="font-normal">(metros)</span>
          </label>
          <input
            id="manual-radius"
            type="number"
            min={1}
            value={radiusStr}
            onChange={(e) => setRecruitableParams({ radiusMeters: e.target.value === '' ? 0 : Number(e.target.value) })}
            className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
          />
          {!radiusValid && <p className="mt-1 text-xs text-red-400" role="alert">Informe um valor positivo maior que zero.</p>}
        </div>

        {/* ---- Lat / Lon ---- */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="manual-lat" className="block text-xs font-medium text-atlas-muted mb-1">Latitude</label>
            <input
              id="manual-lat"
              type="text"
              placeholder="-23.5505"
              value={params.centerLat}
              onChange={(e) => { setRecruitableParams({ centerLat: e.target.value }); setManualAnalysisPin(null); }}
              className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
            />
            {params.centerLat !== '' && !latValid && <p className="mt-1 text-xs text-red-400" role="alert">Inválida.</p>}
          </div>
          <div>
            <label htmlFor="manual-lon" className="block text-xs font-medium text-atlas-muted mb-1">Longitude</label>
            <input
              id="manual-lon"
              type="text"
              placeholder="-46.6333"
              value={params.centerLon}
              onChange={(e) => { setRecruitableParams({ centerLon: e.target.value }); setManualAnalysisPin(null); }}
              className="w-full px-3 py-2 rounded bg-atlas-darker border border-white/10 text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
            />
            {params.centerLon !== '' && !lonValid && <p className="mt-1 text-xs text-red-400" role="alert">Inválida.</p>}
          </div>
        </div>

        {/* ---- Botão analisar + limpar ponto ---- */}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!canAnalyze}
            className="flex-1 py-3 px-4 rounded bg-blue-600 text-white text-sm font-semibold hover:opacity-90 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 min-h-[44px] transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            Analisar
          </button>
          {/* X só aparece quando há ponto definido mas nenhum painel de resultado está ativo */}
          {(params.centerLat !== '' || params.centerLon !== '') &&
           !recruitableAnalysis.result &&
           !whatIfResult && (
            <button
              type="button"
              onClick={() => { clearRecruitableAnalysis(); setManualAnalysisPin(null); }}
              aria-label="Limpar ponto central"
              className="py-3 px-3 rounded border border-white/20 text-atlas-muted hover:text-atlas-light hover:border-white/40 min-h-[44px] transition-colors flex items-center justify-center"
              title="Limpar ponto central"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          )}
        </div>

        {recruitableAnalysis.error && (
          <div className="px-3 py-2 rounded bg-red-500/10 border-l-2 border-red-400 text-xs text-red-400" role="alert">
            ⚠️ {recruitableAnalysis.error}
          </div>
        )}

        {/* Resultado de viabilidade — oculto quando what-if está ativo */}
        {!whatIfModeActive && recruitableAnalysis.result && (
          <RecruitableResultPanel
            result={recruitableAnalysis.result}
            isStale={recruitableAnalysis.isStale}
          />
        )}

        {!whatIfModeActive && recruitableAnalysis.result !== null && (
          <button
            type="button"
            onClick={() => { clearRecruitableAnalysis(); setManualAnalysisPin(null); }}
            className="w-full py-2 px-4 rounded border border-red-500/50 text-red-400 text-sm hover:bg-red-500/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 min-h-[44px] transition-colors flex items-center justify-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            Limpar Análise
          </button>
        )}

        {/* ---- Separador ---- */}
        <div className="border-t border-white/10 pt-2" />

        {/* ---- What-if toggle ---- */}
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-3 cursor-pointer select-none">
            <div className="relative">
              <input
                type="checkbox"
                className="sr-only"
                checked={whatIfModeActive}
                onChange={(e) => {
                  setWhatIfModeActive(e.target.checked);
                }}
                aria-label="Simular reposicionamento de parceiro"
              />
              <div
                className={`w-10 h-6 rounded-full transition-colors ${whatIfModeActive ? 'bg-indigo-500' : 'bg-white/20'}`}
              />
              <div
                className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${whatIfModeActive ? 'translate-x-4' : 'translate-x-0'}`}
              />
            </div>
            <span className="text-sm text-atlas-light">Simular reposicionamento de parceiro</span>
          </label>

          {/* Error: heatmap not loaded */}
          {whatIfModeActive && heatmapData === null && (
            <div className="px-3 py-2 rounded bg-red-500/10 border-l-2 border-red-400 text-xs text-red-400" role="alert">
              Dados de demanda não disponíveis. Carregue o heatmap para usar o modo what-if.
            </div>
          )}

          {/* Warning from drag outside guardrail */}
          {whatIfModeActive && whatIfWarning && (
            <div className="px-3 py-2 rounded bg-yellow-500/10 border-l-2 border-yellow-400 text-xs text-yellow-400" role="alert">
              ⚠️ {whatIfWarning}
            </div>
          )}

          {/* What-if result — substitui o painel de viabilidade quando ativo */}
          {whatIfModeActive && whatIfResult && (
            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3 flex flex-col gap-2" data-testid="whatif-result-panel">
              <div className="text-xs font-semibold text-indigo-300 mb-1">Resultado da simulação</div>
              <div className="text-sm text-atlas-light font-medium">{whatIfResult.partnerName}</div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="rounded bg-white/5 px-2 py-2">
                  <div className="text-atlas-muted mb-0.5">Lat simulada</div>
                  <div className="text-atlas-light font-semibold">{whatIfResult.simulatedLat.toFixed(5)}</div>
                </div>
                <div className="rounded bg-white/5 px-2 py-2">
                  <div className="text-atlas-muted mb-0.5">Lon simulada</div>
                  <div className="text-atlas-light font-semibold">{whatIfResult.simulatedLon.toFixed(5)}</div>
                </div>
                <div className="rounded bg-white/5 px-2 py-2">
                  <div className="text-atlas-muted mb-0.5">Cap atual</div>
                  <div className="text-atlas-light font-semibold">{whatIfResult.originalCap} pct/dia</div>
                </div>
                <div className="rounded bg-white/5 px-2 py-2">
                  <div className="text-atlas-muted mb-0.5">ADV simulado</div>
                  <div className="text-atlas-light font-semibold">{Math.round(whatIfResult.advSimulated)} pct/dia</div>
                </div>
              </div>
              <div className={`rounded px-2 py-2 text-xs ${whatIfResult.advGain >= 0 ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                <div className="text-atlas-muted mb-0.5">Ganho ADV</div>
                <div className={`font-semibold text-sm ${whatIfResult.advGain >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {whatIfResult.advGain >= 0 ? '+' : ''}{Math.round(whatIfResult.advGain)} pct/dia
                </div>
              </div>
            </div>
          )}

          {/* Limpar simulação — aparece após resultado what-if, igual ao Limpar Análise */}
          {whatIfModeActive && whatIfResult && (
            <button
              type="button"
              onClick={() => { setWhatIfResult(null); setWhatIfWarning(null); clearRecruitableAnalysis(); setManualAnalysisPin(null); }}
              className="w-full py-2 px-4 rounded border border-red-500/50 text-red-400 text-sm hover:bg-red-500/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 min-h-[44px] transition-colors flex items-center justify-center gap-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              Limpar Simulação
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ManualAnalysisPanel — portal no desktop/tablet, inline no mobile
// ---------------------------------------------------------------------------

export default function ManualAnalysisPanel() {
  const manualAnalysisOpen = useStore((s) => s.manualAnalysisOpen);
  const setManualAnalysisOpen = useStore((s) => s.setManualAnalysisOpen);
  const setWhatIfModeActive = useStore((s) => s.setWhatIfModeActive);
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';

  if (!manualAnalysisOpen) return null;

  const handleClose = () => {
    setWhatIfModeActive(false);
    setManualAnalysisOpen(false);
  };

  if (isMobile) {
    return <PanelContent onClose={handleClose} />;
  }

  return createPortal(
    <div
      className="fixed overflow-hidden flex flex-col"
      style={{
        top: '56px',
        right: '0',
        bottom: '0',
        width: 'clamp(360px, 28vw, 480px)',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: 'var(--color-navy)',
        borderLeft: '1px solid var(--border-color)',
      }}
    >
      <PanelContent onClose={handleClose} />
    </div>,
    document.body,
  );
}
