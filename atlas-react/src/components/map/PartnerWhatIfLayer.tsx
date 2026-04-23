/**
 * PartnerWhatIfLayer.tsx
 * ======================
 * What-if repositioning layer for Active partners.
 *
 * Active only when `whatIfModeActive === true` in the store.
 * For each Active partner with valid coords:
 *   - Renders a draggable Leaflet Marker
 *   - Renders a 300 m guardrail Circle at the original centroid (indigo, dashed)
 *
 * On dragend:
 *   - If new position is > 300 m from original → snap back, dispatch `atlas:whatif-warning`
 *   - If <= 300 m → compute hex-diff (hexesLost / hexesGained), derive loss/gain from
 *     partner.hex_coverage and heatmap demand_residual, dispatch `atlas:whatif-result`
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
 */

import { useRef, useCallback, useMemo } from 'react';
import { Marker, Circle, CircleMarker } from 'react-leaflet';
import * as turf from '@turf/turf';
import L from 'leaflet';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GUARDRAIL_RADIUS = 300; // metres
const INDIGO_COLOR = '#6366F1';
export const MAX_CAP = 80;

// ---------------------------------------------------------------------------
// Haversine distance (metres)
// ---------------------------------------------------------------------------

function haversineDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// Hex-diff engine helpers
// ---------------------------------------------------------------------------

/**
 * Returns the set of hex_ids whose feature centroids are within `radiusMeters`
 * of the given (lat, lon) position.
 */
export function getHexesWithinRadius(
  features: GeoJSON.Feature[],
  lat: number,
  lon: number,
  radiusMeters: number,
): Set<string> {
  const center = turf.point([lon, lat]);
  const result = new Set<string>();
  for (const feature of features) {
    const hexId = feature.properties?.hex_id as string | undefined;
    if (!hexId) continue;
    const geom = feature.geometry;
    if (!geom) continue;
    let fLon: number, fLat: number;
    if (geom.type === 'Point') {
      [fLon, fLat] = (geom as GeoJSON.Point).coordinates as [number, number];
    } else if (geom.type === 'Polygon' || geom.type === 'MultiPolygon') {
      const c = turf.centroid(feature as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>);
      [fLon, fLat] = c.geometry.coordinates as [number, number];
    } else {
      continue;
    }
    const dist = turf.distance(center, turf.point([fLon, fLat]), { units: 'meters' });
    if (dist <= radiusMeters) result.add(hexId);
  }
  return result;
}

/**
 * Computes the simulated ADV after repositioning.
 * adv_simulated = min(max(capacity - loss + gain, 0), MAX_CAP)
 */
export function computeAdvSimulated(capacity: number, loss: number, gain: number): number {
  return Math.min(Math.max(capacity - loss + gain, 0), MAX_CAP);
}

// ---------------------------------------------------------------------------
// Draggable marker for a single partner
// ---------------------------------------------------------------------------

interface WhatIfMarkerProps {
  partner: Partner & { lat: number; lon: number };
  heatmapFeatures: GeoJSON.Feature[];
  heatmapIndex: Map<string, GeoJSON.Feature>;
}

function WhatIfMarker({ partner, heatmapFeatures, heatmapIndex }: WhatIfMarkerProps) {
  const markerRef = useRef<L.Marker | null>(null);

  const handleDragEnd = useCallback(() => {
    const marker = markerRef.current;
    if (!marker) return;

    const { lat, lng } = marker.getLatLng();
    const origLat = partner.lat;
    const origLon = partner.lon;

    const dist = haversineDistance(origLat, origLon, lat, lng);

    if (dist > GUARDRAIL_RADIUS) {
      // Snap back to original position
      marker.setLatLng([origLat, origLon]);
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: { message: `${partner.name}: posição fora do raio de 300 m. Marcador reposicionado.` },
        }),
      );
      return;
    }

    // Usa o raio configurado no painel de análise (params.radiusMeters)
    const { radiusMeters } = useStore.getState().recruitableAnalysis.params;

    // Compute hex sets for original and simulated positions
    const hexesOriginal = getHexesWithinRadius(heatmapFeatures, origLat, origLon, radiusMeters);
    const hexesSimulated = getHexesWithinRadius(heatmapFeatures, lat, lng, radiusMeters);

    const hexesLost = new Set([...hexesOriginal].filter(h => !hexesSimulated.has(h)));
    const hexesGained = new Set([...hexesSimulated].filter(h => !hexesOriginal.has(h)));

    // Build hex_coverage lookup from partner data
    const hexCoverageMap = new Map<string, number>(
      (partner.hex_coverage ?? []).map(e => [e.hex_id, e.packages_allocated])
    );

    // Guard: if hex_coverage is absent/empty AND hexes are lost → warning, no result
    if ((!partner.hex_coverage || partner.hex_coverage.length === 0) && hexesLost.size > 0) {
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: { message: `${partner.name}: dados de cobertura hex indisponíveis. Reposicione após recarregar os dados.` },
        }),
      );
      return;
    }

    const loss = [...hexesLost].reduce((sum, h) => sum + (hexCoverageMap.get(h) ?? 0), 0);
    const gain = [...hexesGained].reduce((sum, h) => {
      const feature = heatmapIndex.get(h);
      return sum + ((feature?.properties?.demand_residual as number) ?? 0);
    }, 0);

    const advSimulated = computeAdvSimulated(partner.capacity, loss, gain);
    const advGain = advSimulated - partner.capacity;

    document.dispatchEvent(
      new CustomEvent('atlas:whatif-result', {
        detail: {
          partnerName: partner.name,
          simulatedLat: lat,
          simulatedLon: lng,
          advSimulated,
          simulatedRadius: radiusMeters,
          advGain,
          originalCap: partner.capacity,
        },
      }),
    );
  }, [partner, heatmapFeatures, heatmapIndex]);

  return (
    <>
      {/* Marcador original fixo — posição de referência */}
      <CircleMarker
        center={[partner.lat, partner.lon]}
        radius={7}
        pane="markersPane"
        pathOptions={{
          color: INDIGO_COLOR,
          fillColor: INDIGO_COLOR,
          weight: 2,
          fillOpacity: 0.25,
        }}
      />
      {/* Marcador arrastável — posição simulada */}
      <Marker
        position={[partner.lat, partner.lon]}
        draggable
        ref={markerRef}
        eventHandlers={{ dragend: handleDragEnd }}
      />
      {/* 300 m guardrail circle at original centroid */}
      <Circle
        center={[partner.lat, partner.lon]}
        radius={GUARDRAIL_RADIUS}
        pathOptions={{
          color: INDIGO_COLOR,
          fillOpacity: 0.04,
          weight: 2,
          dashArray: '6 4',
          interactive: false,
        }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main layer component
// ---------------------------------------------------------------------------

export default function PartnerWhatIfLayer() {
  const whatIfModeActive = useStore((s) => s.whatIfModeActive);
  const currentFilteredData = useStore((s) => s.currentFilteredData);
  const heatmapData = useStore((s) => s.heatmapData);

  const heatmapFeatures: GeoJSON.Feature[] = heatmapData?.features ?? [];

  const heatmapIndex = useMemo(
    () => new Map(
      heatmapFeatures
        .filter(f => f.properties?.hex_id)
        .map(f => [f.properties!.hex_id as string, f])
    ),
    [heatmapFeatures]
  );

  if (!whatIfModeActive) return null;

  // Respeita o filtro ativo (ex: Delivery Station) e mostra só os ativos
  const activePartners = currentFilteredData.filter(
    (p): p is Partner & { lat: number; lon: number } =>
      p.status === 'Active' &&
      p.lat !== null &&
      p.lat !== 0 &&
      p.lon !== null &&
      p.lon !== 0,
  );

  return (
    <>
      {activePartners.map((partner) => (
        <WhatIfMarker
          key={partner.salesforce_id}
          partner={partner}
          heatmapFeatures={heatmapFeatures}
          heatmapIndex={heatmapIndex}
        />
      ))}
    </>
  );
}
