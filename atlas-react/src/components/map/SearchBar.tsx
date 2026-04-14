import { useState, useRef, useEffect, useCallback } from 'react';
import { useMap } from 'react-leaflet';
import type { Partner } from '../../store/types';
import { useDebounce } from '../../hooks/useDebounce';
import { useBreakpoint, type Breakpoint } from '../../hooks/useBreakpoint';

interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
}

interface MapFlyToProps {
  flyToRef: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
}

function MapFlyTo({ flyToRef }: MapFlyToProps) {
  const map = useMap();
  useEffect(() => {
    flyToRef.current = (lat: number, lon: number) => map.flyTo([lat, lon], 15);
    return () => { flyToRef.current = null; };
  }, [map, flyToRef]);
  return null;
}

export interface SearchBarProps {
  partners: Partner[];
  flyToRef: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
  breakpoint?: Breakpoint;
  /** Largura do FloatingPanel de controles — usado no desktop para posicionar a barra ao lado */
  controlPanelWidth?: number;
}

function getContainerStyle(bp: Breakpoint, controlPanelWidth: number): React.CSSProperties {
  if (bp === 'mobile' || bp === 'tablet') {
    return {
      position: 'absolute',
      top: '16px',
      left: '50%',
      transform: 'translateX(-50%)',
      width: '90vw',
      maxWidth: '90vw',
      zIndex: 'var(--z-overlay)' as unknown as number,
    };
  }
  return {
    position: 'absolute',
    top: '16px',
    left: `${controlPanelWidth + 24}px`,
    width: 'clamp(280px, 30vw, 480px)',
    zIndex: 'var(--z-overlay)' as unknown as number,
  };
}

export function SearchBar({ partners, flyToRef, breakpoint: breakpointProp, controlPanelWidth = 0 }: SearchBarProps) {
  const detectedBreakpoint = useBreakpoint();
  const bp = breakpointProp ?? detectedBreakpoint;

  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Partner[]>([]);
  // true quando não há match de parceiro e o campo vira modo endereço (igual vanilla)
  const [addressMode, setAddressMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebounce(query, 300);

  // Filtra parceiros; quando não há match ativa modo endereço
  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      setAddressMode(false);
      return;
    }
    const lower = debouncedQuery.toLowerCase();
    const filtered = partners.filter(
      (p) => p.name.toLowerCase().includes(lower) && p.lat != null && p.lon != null
    );
    setSuggestions(filtered.slice(0, 8));
    if (filtered.length > 0) {
      setAddressMode(false);
      setIsOpen(true);
    } else {
      // Sem match de parceiro — modo endereço, igual ao comportamento vanilla
      setAddressMode(true);
      setIsOpen(true);
    }
    setActiveIndex(-1);
    setError(null);
  }, [debouncedQuery, partners]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectPartner = useCallback((partner: Partner) => {
    if (partner.lat != null && partner.lon != null) {
      flyToRef.current?.(partner.lat, partner.lon);
    }
    setQuery(partner.name);
    setIsOpen(false);
    setSuggestions([]);
    setAddressMode(false);
    setError(null);
  }, [flyToRef]);

  const geocodeAddress = useCallback(async (q: string) => {
    setError(null);
    setIsOpen(false);
    setAddressMode(false);
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`;
      const res = await fetch(url, { headers: { 'Accept-Language': 'pt-BR,pt;q=0.9' } });
      if (!res.ok) throw new Error('Falha na geocodificação');
      const data: NominatimResult[] = await res.json();
      if (data.length === 0) { setError('Endereço não encontrado'); return; }
      flyToRef.current?.(parseFloat(data[0].lat), parseFloat(data[0].lon));
    } catch {
      setError('Erro ao buscar endereço');
    }
  }, [flyToRef]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setIsOpen(false);
      setActiveIndex(-1);
      inputRef.current?.blur();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, suggestions.length - 1));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, -1));
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (activeIndex >= 0 && suggestions[activeIndex]) {
        selectPartner(suggestions[activeIndex]);
        return;
      }
      if (query.trim().length >= 2) {
        geocodeAddress(query.trim());
      }
    }
  }, [activeIndex, suggestions, query, selectPartner, geocodeAddress]);

  const placeholder = addressMode
    ? `Buscar endereço: "${query}"`
    : 'Buscar parceiro ou endereço…';

  return (
    <div ref={containerRef} style={getContainerStyle(bp, controlPanelWidth)}>
      <div style={styles.inputWrapper}>
        <span style={styles.icon} aria-hidden="true">{addressMode ? '📍' : '🔍'}</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setError(null); }}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (isOpen || suggestions.length > 0 || addressMode) setIsOpen(true); }}
          placeholder={placeholder}
          aria-label="Buscar parceiro ou endereço"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="searchbar-suggestions"
          aria-activedescendant={activeIndex >= 0 ? `suggestion-${activeIndex}` : undefined}
          style={{
            ...styles.input,
          }}
          autoComplete="off"
        />
        {query && (
          <button
            onClick={() => {
              setQuery('');
              setSuggestions([]);
              setIsOpen(false);
              setAddressMode(false);
              setError(null);
              inputRef.current?.focus();
            }}
            style={styles.clearBtn}
            aria-label="Limpar busca"
            type="button"
          >
            ✕
          </button>
        )}
      </div>

      {error && <div style={styles.error} role="alert">{error}</div>}

      {isOpen && (
        <ul id="searchbar-suggestions" role="listbox" style={styles.dropdown}>
          {/* Modo endereço: mostra opção de geocodificar (igual vanilla) */}
          {addressMode && query.trim().length >= 2 && (
            <li
              role="option"
              aria-selected={false}
              onMouseDown={(e) => { e.preventDefault(); geocodeAddress(query.trim()); }}
              style={{ ...styles.suggestion, ...styles.addressOption }}
            >
              <span style={styles.suggestionName}>📍 Buscar endereço: <em>{query}</em></span>
              <span style={styles.suggestionMeta}>Pressione Enter ou clique para geocodificar</span>
            </li>
          )}
          {/* Sugestões de parceiros */}
          {suggestions.map((partner, idx) => (
            <li
              key={partner.salesforce_id}
              id={`suggestion-${idx}`}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseDown={(e) => { e.preventDefault(); selectPartner(partner); }}
              onMouseEnter={() => setActiveIndex(idx)}
              style={{
                ...styles.suggestion,
                ...(idx === activeIndex ? styles.suggestionActive : {}),
              }}
            >
              <span style={styles.suggestionName}>{partner.name}</span>
              {partner.city && (
                <span style={styles.suggestionMeta}>
                  {partner.city}{partner.state ? `, ${partner.state}` : ''}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  inputWrapper: {
    display: 'flex',
    alignItems: 'center',
    background: 'var(--surface-primary)',
    border: '1px solid var(--border-color-strong)',
    borderRadius: '8px',
    boxShadow: 'var(--shadow-md)',
    overflow: 'hidden',
  },
  icon: { padding: '0 8px 0 12px', fontSize: '14px', flexShrink: 0 },
  input: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    outline: 'none',
    color: 'var(--text-primary)',
    fontSize: 'var(--font-size-sm)',
    padding: '12px 4px',
    fontFamily: 'inherit',
  },
  clearBtn: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    padding: '0 12px',
    fontSize: '12px',
    lineHeight: 1,
    flexShrink: 0,
  },
  error: {
    marginTop: '4px',
    padding: '6px 12px',
    background: 'var(--surface-secondary)',
    border: '1px solid rgba(255,80,80,0.4)',
    borderRadius: '6px',
    color: '#ff6b6b',
    fontSize: 'var(--font-size-xs)',
  },
  dropdown: {
    marginTop: '4px',
    background: 'var(--surface-primary)',
    border: '1px solid var(--border-color-strong)',
    borderRadius: '8px',
    boxShadow: 'var(--shadow-lg)',
    listStyle: 'none',
    overflow: 'hidden',
    maxHeight: '320px',
    overflowY: 'auto',
  },
  suggestion: {
    display: 'flex',
    flexDirection: 'column',
    padding: '8px 14px',
    cursor: 'pointer',
    borderBottom: '1px solid var(--border-color)',
    transition: 'background var(--transition-fast)',
  },
  addressOption: {
    background: 'rgba(255, 153, 0, 0.08)',
  },
  suggestionActive: { background: 'var(--surface-secondary)' },
  suggestionName: {
    color: 'var(--text-primary)',
    fontSize: 'var(--font-size-sm)',
    fontWeight: 500,
  },
  suggestionMeta: {
    color: 'var(--text-secondary)',
    fontSize: 'var(--font-size-xs)',
    marginTop: '2px',
  },
};

export { MapFlyTo };
