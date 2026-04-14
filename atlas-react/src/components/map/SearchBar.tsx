/**
 * SearchBar.tsx
 * =============
 * Componente overlay de busca flutuante sobre o mapa.
 * Renderizado FORA do MapContainer — não é filho do Leaflet.
 *
 * Sub-componente interno `MapFlyTo` é filho do MapContainer e
 * usa useMap().flyTo() para navegar o mapa.
 *
 * Requirements: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 1.10
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useMap } from 'react-leaflet';
import type { Partner } from '../../store/types';
import { useDebounce } from '../../hooks/useDebounce';
import { useBreakpoint, type Breakpoint } from '../../hooks/useBreakpoint';

// ---------------------------------------------------------------------------
// TIPOS
// ---------------------------------------------------------------------------

interface NominatimResult {
  lat: string;
  lon: string;
  display_name: string;
}

// ---------------------------------------------------------------------------
// MapFlyTo — filho do MapContainer
// ---------------------------------------------------------------------------

interface MapFlyToProps {
  flyToRef: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
}

function MapFlyTo({ flyToRef }: MapFlyToProps) {
  const map = useMap();

  useEffect(() => {
    flyToRef.current = (lat: number, lon: number) => {
      map.flyTo([lat, lon], 15);
    };
    return () => {
      flyToRef.current = null;
    };
  }, [map, flyToRef]);

  return null;
}

// ---------------------------------------------------------------------------
// SearchBar — overlay fora do MapContainer
// ---------------------------------------------------------------------------

export interface SearchBarProps {
  partners: Partner[];
  /** Ref para o sub-componente MapFlyTo ser injetado no MapContainer pelo pai */
  flyToRef: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
  /** Breakpoint opcional; se omitido, usa o hook useBreakpoint internamente */
  breakpoint?: Breakpoint;
}

function getContainerStyle(bp: Breakpoint): React.CSSProperties {
  const isMobileOrTablet = bp === 'mobile' || bp === 'tablet';
  return isMobileOrTablet
    ? {
        position: 'absolute',
        top: '16px',
        left: '50%',
        transform: 'translateX(-50%)',
        width: '90vw',
        maxWidth: '90vw',
        zIndex: 'var(--z-overlay)' as unknown as number,
        fontFamily: 'var(--font-family)',
      }
    : {
        position: 'absolute',
        top: '16px',
        left: '16px',
        width: 'clamp(280px, 30vw, 480px)',
        zIndex: 'var(--z-overlay)' as unknown as number,
        fontFamily: 'var(--font-family)',
      };
}

export function SearchBar({ partners, flyToRef, breakpoint: breakpointProp }: SearchBarProps) {
  const detectedBreakpoint = useBreakpoint();
  const bp = breakpointProp ?? detectedBreakpoint;
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<Partner[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const debouncedQuery = useDebounce(query, 300);

  // Filtra parceiros por nome (mínimo 2 caracteres)
  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setSuggestions([]);
      setIsOpen(false);
      return;
    }

    const lower = debouncedQuery.toLowerCase();
    const filtered = partners.filter(
      (p) => p.name.toLowerCase().includes(lower) && p.lat != null && p.lon != null
    );
    setSuggestions(filtered.slice(0, 8));
    setIsOpen(filtered.length > 0);
    setActiveIndex(-1);
    setError(null);
  }, [debouncedQuery, partners]);

  // Fecha ao clicar fora
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectPartner = useCallback(
    (partner: Partner) => {
      if (partner.lat != null && partner.lon != null) {
        flyToRef.current?.(partner.lat, partner.lon);
      }
      setQuery(partner.name);
      setIsOpen(false);
      setSuggestions([]);
      setError(null);
    },
    [flyToRef]
  );

  const geocodeAddress = useCallback(async (q: string) => {
    setError(null);
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`;
      const res = await fetch(url, {
        headers: { 'Accept-Language': 'pt-BR,pt;q=0.9' },
      });
      if (!res.ok) throw new Error('Falha na geocodificação');
      const data: NominatimResult[] = await res.json();
      if (data.length === 0) {
        setError('Endereço não encontrado');
        return;
      }
      const { lat, lon } = data[0];
      flyToRef.current?.(parseFloat(lat), parseFloat(lon));
      setIsOpen(false);
    } catch {
      setError('Erro ao buscar endereço');
    }
  }, [flyToRef]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
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
        // Sem match de parceiro selecionado — geocodifica
        if (query.trim().length >= 2) {
          setIsOpen(false);
          geocodeAddress(query.trim());
        }
      }
    },
    [activeIndex, suggestions, query, selectPartner, geocodeAddress]
  );

  return (
    <div ref={containerRef} style={getContainerStyle(bp)}>
      <div style={styles.inputWrapper}>
        <span style={styles.icon} aria-hidden="true">🔍</span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (suggestions.length > 0) setIsOpen(true);
          }}
          placeholder="Buscar parceiro ou endereço…"
          aria-label="Buscar parceiro ou endereço"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="searchbar-suggestions"
          aria-activedescendant={activeIndex >= 0 ? `suggestion-${activeIndex}` : undefined}
          style={styles.input}
          autoComplete="off"
        />
        {query && (
          <button
            onClick={() => {
              setQuery('');
              setSuggestions([]);
              setIsOpen(false);
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

      {error && (
        <div style={styles.error} role="alert">
          {error}
        </div>
      )}

      {isOpen && suggestions.length > 0 && (
        <ul
          id="searchbar-suggestions"
          role="listbox"
          style={styles.dropdown}
        >
          {suggestions.map((partner, idx) => (
            <li
              key={partner.salesforce_id}
              id={`suggestion-${idx}`}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseDown={(e) => {
                e.preventDefault();
                selectPartner(partner);
              }}
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

// ---------------------------------------------------------------------------
// ESTILOS INLINE (usa variáveis CSS do projeto)
// ---------------------------------------------------------------------------

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
  icon: {
    padding: '0 8px 0 12px',
    fontSize: '14px',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    outline: 'none',
    color: 'var(--text-primary)',
    fontSize: 'var(--font-size-sm)',
    padding: '10px 4px',
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
    boxShadow: 'var(--shadow-sm)',
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
  suggestionActive: {
    background: 'var(--surface-secondary)',
  },
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

// ---------------------------------------------------------------------------
// EXPORT do sub-componente MapFlyTo para uso no MapContainer
// ---------------------------------------------------------------------------

export { MapFlyTo };
