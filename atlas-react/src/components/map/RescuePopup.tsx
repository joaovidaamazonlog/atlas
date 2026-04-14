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
    <div style={{
      position: 'fixed', top: '80px', right: '20px', zIndex: 9999,
      background: 'var(--color-dark)', color: 'var(--color-light)', padding: '20px',
      borderRadius: '8px', boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
      maxWidth: '420px', width: '90vw', maxHeight: '80vh', overflowY: 'auto',
      fontSize: '13px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <strong>Sugestões de Resgate — {state.targetName}</strong>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#ecf0f1', cursor: 'pointer', fontSize: '1.3em' }}>✕</button>
      </div>

      {state.loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#a0aec0' }}>
          <svg style={{ animation: 'spin 1s linear infinite', width: 20, height: 20 }} viewBox="0 0 24 24" fill="none">
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            <circle cx="12" cy="12" r="10" stroke="#4fc3f7" strokeWidth="4" strokeOpacity="0.25"/>
            <path fill="#4fc3f7" d="M4 12a8 8 0 018-8v8z"/>
          </svg>
          Buscando parceiros próximos...
        </div>
      )}

      {!state.loading && state.results.length === 0 && (
        <p style={{ color: '#718096' }}>Nenhum parceiro Ativo encontrado num raio de {RESCUE_RADIUS_KM} km.</p>
      )}

      {!state.loading && state.results.map(({ partner, distanceKm, bonus }) => (
        <div key={partner.store_id} style={{ borderBottom: '1px solid #2d3748', paddingBottom: '10px', marginBottom: '10px' }}>
          <p style={{ margin: '0 0 4px', fontWeight: 600 }}>{partner.name}</p>
          <p style={{ margin: '0 0 4px', color: '#a0aec0', fontSize: '12px' }}>
            Distância: <strong style={{ color: '#ecf0f1' }}>{distanceKm} km</strong>
            &nbsp;·&nbsp;Bônus sugerido: <strong style={{ color: '#f6e05e' }}>R$ {bonus}</strong>
          </p>
          {partner.telefone && (
            <a href={`https://wa.me/${partner.telefone}`} target="_blank" rel="noreferrer"
              style={{ color: '#25d366', display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z"/>
                <path d="M12 0C5.373 0 0 5.373 0 12c0 2.127.558 4.126 1.533 5.858L.057 23.5l5.797-1.52A11.93 11.93 0 0012 24c6.627 0 12-5.373 12-12S18.627 0 12 0zm0 22c-1.885 0-3.65-.52-5.16-1.426l-.37-.22-3.44.902.918-3.352-.24-.386A9.944 9.944 0 012 12C2 6.477 6.477 2 12 2s10 4.477 10 10-4.477 10-10 10z"/>
              </svg>
              WhatsApp
            </a>
          )}
        </div>
      ))}
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
