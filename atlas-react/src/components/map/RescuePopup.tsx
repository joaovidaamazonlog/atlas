/**
 * RescuePopup.tsx
 * ===============
 * Popup de sugestões de resgate — porta fiel de requestAssistence() do vanilla.
 * Encontra parceiros Ativos dentro de um raio (padrão 5 km) usando haversine,
 * consulta OSRM para distâncias reais e exibe os 10 mais próximos com bônus sugerido.
 */

import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

const RESCUE_RADIUS_KM = 5;

// Haversine distance in km
function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function bonusFor(distKm: number): number {
  if (distKm <= 2) return 30;
  if (distKm <= 5) return 40;
  return 50;
}

interface RescueSuggestion {
  partner: Partner;
  distanceKm: string;
  bonus: number;
}

interface RescueState {
  loading: boolean;
  results: RescueSuggestion[];
  targetName: string;
}

// ---------------------------------------------------------------------------
// Popup UI
// ---------------------------------------------------------------------------

function RescuePopupUI({ state, onClose }: { state: RescueState; onClose: () => void }) {
  return createPortal(
    <div
      className="fixed overflow-hidden flex flex-col text-atlas-light"
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
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0 border-b border-white/10">
        <div>
          <p className="text-xs font-semibold text-atlas-muted uppercase tracking-wide">
            Sugestões de Resgate
          </p>
          <p className="text-sm font-semibold text-atlas-light mt-0.5 leading-snug">
            {state.targetName}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fechar painel"
          className="text-atlas-muted hover:text-atlas-light transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-2 p-3">
        {state.loading && (
          <div className="flex items-center gap-2 text-xs text-atlas-muted py-2">
            <svg className="w-4 h-4 animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#4fc3f7" strokeWidth="4" strokeOpacity="0.25"/>
              <path fill="#4fc3f7" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            Buscando parceiros próximos…
          </div>
        )}

        {!state.loading && state.results.length === 0 && (
          <p className="text-xs text-atlas-muted text-center py-4">
            Nenhum parceiro Ativo encontrado num raio de {RESCUE_RADIUS_KM} km.
          </p>
        )}

        {!state.loading && state.results.map(({ partner, distanceKm, bonus }) => (
          <div key={partner.store_id} className="rounded-lg bg-white/5 p-3 flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-atlas-light leading-tight">
              {partner.name}
            </span>
            <p className="text-xs text-atlas-muted">
              Distância:{' '}
              <span className="text-atlas-light font-medium">{distanceKm} km</span>
              {' · '}
              Bônus sugerido:{' '}
              <span className="text-yellow-400 font-semibold">R$ {bonus}</span>
            </p>
            {partner.telefone && (
              <a
                href={`https://wa.me/${partner.telefone}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs text-[#25d366] hover:opacity-80 transition-opacity"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
                  <path d="M12 0C5.373 0 0 5.373 0 12c0 2.127.558 4.126 1.533 5.858L.057 23.5l5.797-1.52A11.93 11.93 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.885 0-3.65-.52-5.16-1.426l-.37-.22-3.44.902.918-3.352-.24-.386A9.944 9.944 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/>
                </svg>
                WhatsApp
              </a>
            )}
          </div>
        ))}
      </div>
    </div>,
    document.body
  );
}

// ---------------------------------------------------------------------------
// Hook — monta no PartnerMarkers e escuta o evento atlas:request-rescue
// ---------------------------------------------------------------------------

export function useRescuePopup() {
  const allMarkersData = useStore((s) => s.allMarkersData);
  const [rescueState, setRescueState] = useState<RescueState | null>(null);

  const handleRescue = useCallback(async (storeId: string) => {
    const target = allMarkersData.find((p) => p.store_id === storeId);
    if (!target || target.lat == null || target.lon == null) return;

    setRescueState({ loading: true, results: [], targetName: target.name });

    // Find Active partners within radius using haversine
    const nearby = allMarkersData.filter((p) => {
      if (p.status !== 'Active' || p.store_id === storeId) return false;
      if (p.lat == null || p.lon == null) return false;
      return haversineKm(target.lat!, target.lon!, p.lat, p.lon) <= RESCUE_RADIUS_KM;
    });

    if (nearby.length === 0) {
      setRescueState({ loading: false, results: [], targetName: target.name });
      return;
    }

    // Query OSRM table for real road distances
    try {
      const coords = [
        ...nearby.map((p) => `${p.lon},${p.lat}`),
        `${target.lon},${target.lat}`,
      ].join(';');
      const res = await fetch(
        `https://router.project-osrm.org/table/v1/driving/${coords}?annotations=distance`
      );
      if (!res.ok) throw new Error(`OSRM ${res.status}`);
      const osrm = await res.json();
      const destIdx = nearby.length; // last coord is the target

      const results: RescueSuggestion[] = nearby
        .map((p, i) => {
          const distM = osrm.distances?.[i]?.[destIdx] ?? null;
          const distKm = distM != null ? (distM / 1000).toFixed(2) : haversineKm(p.lat!, p.lon!, target.lat!, target.lon!).toFixed(2);
          return { partner: p, distanceKm: distKm, bonus: bonusFor(parseFloat(distKm)) };
        })
        .sort((a, b) => parseFloat(a.distanceKm) - parseFloat(b.distanceKm))
        .slice(0, 10);

      setRescueState({ loading: false, results, targetName: target.name });
    } catch (err) {
      console.error('[Resgate] Erro OSRM:', err);
      // Fallback: use haversine distances
      const results: RescueSuggestion[] = nearby
        .map((p) => {
          const distKm = haversineKm(p.lat!, p.lon!, target.lat!, target.lon!).toFixed(2);
          return { partner: p, distanceKm: distKm, bonus: bonusFor(parseFloat(distKm)) };
        })
        .sort((a, b) => parseFloat(a.distanceKm) - parseFloat(b.distanceKm))
        .slice(0, 10);
      setRescueState({ loading: false, results, targetName: target.name });
    }
  }, [allMarkersData]);

  // Listen for rescue events from popup buttons
  useEffect(() => {
    const handler = (e: Event) => {
      const storeId = (e as CustomEvent<string>).detail;
      handleRescue(storeId);
    };
    window.addEventListener('atlas:request-rescue', handler);
    return () => window.removeEventListener('atlas:request-rescue', handler);
  }, [handleRescue]);

  const popup = rescueState
    ? <RescuePopupUI state={rescueState} onClose={() => setRescueState(null)} />
    : null;

  return popup;
}
