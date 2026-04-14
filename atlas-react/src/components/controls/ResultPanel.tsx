/**
 * ResultPanel.tsx
 * ===============
 * Painel lateral de resultados da prospecção.
 *
 * Desktop/Tablet: renderizado via createPortal no document.body como painel
 *   fixo no lado ESQUERDO da tela (similar ao AreaAnalysisTab, mas à esquerda).
 * Mobile: renderizado inline dentro do ProspectTab.
 *
 * Features:
 * - Cabeçalho com DS, Carteira, total de empresas e contagem de contactadas
 * - Card por ProspectCompany: nome, endereço, tipo, telefone, link Google Maps,
 *   botão alfinete (quando lat/lon disponíveis), toggle "Marcar como contactada"
 * - Virtualização via @tanstack/react-virtual para listas longas
 * - Botão "Minha localização" em mobile via useGeolocation
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { ProspectCompany } from '../../store/types';
import { getLeadKey } from '../../lib/kmeansUtils';
import { API_BASE_URL } from '../../lib/config';
import { useBreakpoint } from '../../hooks/useBreakpoint';
import { useGeolocation } from '../../hooks/useGeolocation';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ResultPanelProps {
  companies: ProspectCompany[];
  selectedStation: string;
  selectedBucket: string;
  onClose: () => void;
  pinnedKeys: Set<string>;
  onTogglePin: (key: string) => void;
}

// ---------------------------------------------------------------------------
// CompanyCard
// ---------------------------------------------------------------------------

interface CompanyCardProps {
  company: ProspectCompany;
  contactada: boolean;
  onToggleContactada: () => void;
  isPinned: boolean;
  onTogglePin: () => void;
}

function CompanyCard({
  company,
  contactada,
  onToggleContactada,
  isPinned,
  onTogglePin,
}: CompanyCardProps) {
  const hasCoords = company.lat != null && company.lon != null;
  const hasPhone = company.telefone_1 != null;
  const hasGoogleMaps =
    company.google_maps_link != null && company.google_maps_link !== 'N/A';

  // Badge de fonte: "Google Maps 🗺️" ou "Receita Federal 🏛️"
  const fonteBadge = company._fonte
    ? company._fonte.includes('Google') ? '🗺️ Google Maps' : '🏛️ Receita Federal'
    : null;

  return (
    <div
      className={`rounded-lg bg-white/5 p-3 flex flex-col gap-1 border border-white/5 transition-opacity ${
        contactada ? 'opacity-50' : 'opacity-100'
      }`}
    >
      {/* Nome + pin */}
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-semibold text-atlas-light leading-tight flex-1">
          {company.nome}
        </span>

        {/* Botão alfinete — só quando tem coordenadas */}
        {hasCoords && (
          <button
            type="button"
            onClick={onTogglePin}
            aria-label={isPinned ? 'Remover alfinete' : 'Fixar no mapa'}
            title={isPinned ? 'Remover alfinete' : 'Fixar no mapa'}
            className={`shrink-0 text-lg leading-none transition-opacity hover:opacity-100 ${
              isPinned ? 'opacity-100' : 'opacity-30'
            }`}
          >
            📌
          </button>
        )}
      </div>

      {/* Fonte + Tipo */}
      <div className="flex items-center gap-2 flex-wrap">
        {fonteBadge && (
          <span className="text-xs text-atlas-accent">{fonteBadge}</span>
        )}
        <span className="text-xs text-atlas-muted">{company.tipo}</span>
      </div>

      {/* Endereço */}
      <span className="text-xs text-atlas-muted leading-snug">{company.endereco}</span>

      {/* Telefone */}
      {hasPhone && (
        <span className="text-xs text-atlas-light">📞 {company.telefone_1}</span>
      )}

      {/* Google Maps link */}
      {hasGoogleMaps && (
        <a
          href={company.google_maps_link}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-400 hover:text-blue-300 underline transition-colors"
        >
          Ver no Google Maps
        </a>
      )}

      {/* Toggle contactada */}
      <button
        type="button"
        onClick={onToggleContactada}
        className={`mt-1 w-full py-1.5 px-3 rounded text-xs font-medium transition-colors ${
          contactada
            ? 'bg-green-600/30 text-green-400 border border-green-500/40 hover:bg-green-600/20'
            : 'bg-white/5 text-atlas-muted border border-white/10 hover:bg-white/10 hover:text-atlas-light'
        }`}
      >
        {contactada ? '✓ Contactada' : 'Marcar como contactada'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PanelContent — conteúdo do painel (usado tanto no portal quanto inline)
// ---------------------------------------------------------------------------

interface PanelContentProps extends ResultPanelProps {
  contactadaStates: boolean[];
  onToggleContactada: (idx: number) => void;
  isMobile: boolean;
}

function PanelContent({
  companies,
  selectedStation,
  selectedBucket,
  onClose,
  pinnedKeys,
  onTogglePin,
  contactadaStates,
  onToggleContactada,
  isMobile,
}: PanelContentProps) {
  const { position, isTracking, error: geoError, startTracking, stopTracking } =
    useGeolocation();

  const contactadaCount = contactadaStates.filter(Boolean).length;
  const mapsCount = companies.filter((c) => c._fonte === 'Google Maps').length;
  const receitaCount = companies.filter((c) => c._fonte === 'Receita Federal').length;

  // Virtualizer
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: companies.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 140,
    overscan: 5,
  });

  const items = virtualizer.getVirtualItems();

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start justify-between px-4 py-3 shrink-0 border-b border-white/10">
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          <span className="font-semibold text-atlas-light text-sm truncate">
            {selectedStation} — {selectedBucket}
          </span>
          {/* Total + fontes */}
          <div className="flex items-center gap-2 text-xs flex-wrap">
            <span className="text-atlas-light font-medium">{companies.length} empresa{companies.length !== 1 ? 's' : ''}</span>
            {mapsCount > 0 && (
              <span className="text-atlas-muted">🗺️ {mapsCount} Maps</span>
            )}
            {receitaCount > 0 && (
              <span className="text-atlas-muted">🏛️ {receitaCount} Receita</span>
            )}
          </div>
          {/* Contactadas */}
          {contactadaCount > 0 && (
            <span className="text-xs text-green-400">
              ✓ {contactadaCount} contactada{contactadaCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Fechar painel"
          className="ml-2 shrink-0 text-atlas-muted hover:text-atlas-light transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>

      {/* Mobile: botão "Minha localização" */}
      {isMobile && (
        <div className="px-4 py-2 shrink-0 border-b border-white/10">
          <button
            type="button"
            onClick={isTracking ? stopTracking : startTracking}
            className={`w-full py-2 px-3 rounded text-xs font-medium flex items-center justify-center gap-2 transition-colors ${
              isTracking
                ? 'bg-blue-600/30 text-blue-300 border border-blue-500/40 hover:bg-blue-600/20'
                : 'bg-white/5 text-atlas-muted border border-white/10 hover:bg-white/10 hover:text-atlas-light'
            }`}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="currentColor"
            >
              <path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0013 3.06V1h-2v2.06A8.994 8.994 0 003.06 11H1v2h2.06A8.994 8.994 0 0011 20.94V23h2v-2.06A8.994 8.994 0 0020.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z" />
            </svg>
            {isTracking ? 'Parar rastreamento' : 'Minha localização'}
          </button>
          {position && (
            <p className="text-xs text-atlas-muted mt-1 text-center">
              {position[0].toFixed(5)}, {position[1].toFixed(5)}
            </p>
          )}
          {geoError && (
            <p className="text-xs text-red-400 mt-1">{geoError}</p>
          )}
        </div>
      )}

      {/* Lista virtualizada */}
      {companies.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-sm text-atlas-muted text-center">
            Nenhuma empresa encontrada para esta carteira.
          </p>
        </div>
      ) : (
        <div ref={parentRef} className="flex-1 overflow-y-auto p-3">
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {items.map((virtualItem) => {
              const company = companies[virtualItem.index];
              const leadKey = getLeadKey(company);
              return (
                <div
                  key={virtualItem.key}
                  data-index={virtualItem.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualItem.start}px)`,
                    paddingBottom: '8px',
                  }}
                >
                  <CompanyCard
                    company={company}
                    contactada={contactadaStates[virtualItem.index]}
                    onToggleContactada={() => onToggleContactada(virtualItem.index)}
                    isPinned={pinnedKeys.has(leadKey)}
                    onTogglePin={() => onTogglePin(leadKey)}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResultPanel — componente principal
// ---------------------------------------------------------------------------

export default function ResultPanel(props: ResultPanelProps) {
  const { companies, selectedBucket } = props;
  const bp = useBreakpoint();
  const isMobile = bp === 'mobile';

  // Contactada state — inicializado a partir de companies.contactada
  const [contactadaStates, setContactadaStates] = useState<boolean[]>(() =>
    companies.map((c) => c.contactada)
  );

  // Sync when companies list changes (new search)
  useEffect(() => {
    setContactadaStates(companies.map((c) => c.contactada));
  }, [companies]);

  const handleToggleContactada = useCallback(
    async (idx: number) => {
      const company = companies[idx];
      const prevState = contactadaStates[idx];
      const nextState = !prevState;

      // Optimistic update
      setContactadaStates((prev) => {
        const next = [...prev];
        next[idx] = nextState;
        return next;
      });

      const leadKey = getLeadKey(company);

      try {
        const res = await fetch(`${API_BASE_URL}/api/empresas/contactada`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lead_key: leadKey,
            lead_nome: company.nome,
            territorio: selectedBucket,
            fonte: company._fonte,
            action: nextState ? 'add' : 'remove',
          }),
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
      } catch (err) {
        console.warn('[ResultPanel] Falha ao atualizar contactada:', err);
        // Revert on failure
        setContactadaStates((prev) => {
          const next = [...prev];
          next[idx] = prevState;
          return next;
        });
      }
    },
    [companies, contactadaStates, selectedBucket]
  );

  const contentProps: PanelContentProps = {
    ...props,
    contactadaStates,
    onToggleContactada: handleToggleContactada,
    isMobile,
  };

  // Mobile: render inline
  if (isMobile) {
    return (
      <div className="flex flex-col" style={{ minHeight: '300px' }}>
        <PanelContent {...contentProps} />
      </div>
    );
  }

  // Desktop/Tablet: render via portal as fixed RIGHT panel
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
      <PanelContent {...contentProps} />
    </div>,
    document.body
  );
}
