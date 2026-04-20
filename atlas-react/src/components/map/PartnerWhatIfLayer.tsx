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
 *   - If <= 300 m → recalculate suggested_cap / suggested_radius from heatmapData,
 *     dispatch `atlas:whatif-result`
 *
 * Requirements: 6.2, 6.3, 6.4, 6.5, 6.6
 */

import { useRef, useCallback } from 'react';
import { Marker, Circle } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GUARDRAIL_RADIUS = 300; // metres
const INDIGO_COLOR = '#6366F1';
const MAX_CAP = 80;

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
// What-if calculation helpers
// ---------------------------------------------------------------------------

/**
 * Sums demand_residual of heatmap features whose centroid is within
 * `radiusMeters` of (lat, lon).
 */
function sumResidualWithinRadius(
  features: GeoJSON.Feature[],
  lat: number,
  lon: number,
  radiusMeters: number,
): number {
  let total = 0;
  for (const feature of features) {
    if (feature.geometry.type !== 'Point') continue;
    const [fLon, fLat] = (feature.geometry as GeoJSON.Point).coordinates;
    const dist = haversineDistance(lat, lon, fLat, fLon);
    if (dist <= radiusMeters) {
      total += (feature.properties?.demand_residual as number) ?? 0;
    }
  }
  return total;
}

// ---------------------------------------------------------------------------
// Draggable marker for a single partner
// ---------------------------------------------------------------------------

interface WhatIfMarkerProps {
  partner: Partner & { lat: number; lon: number };
  heatmapFeatures: GeoJSON.Feature[];
}

function WhatIfMarker({ partner, heatmapFeatures }: WhatIfMarkerProps) {
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
      window.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: { partnerName: partner.name },
        }),
      );
      return;
    }

    // Recalculate suggested_cap and suggested_radius
    const totalResidual = sumResidualWithinRadius(heatmapFeatures, lat, lng, partner.radius);
    const suggestedCap = Math.min(Math.floor(totalResidual), MAX_CAP);
    const suggestedRadius = partner.radius; // keep same radius for what-if simplicity
    const estimatedAdvGain = suggestedCap - partner.capacity;

    window.dispatchEvent(
      new CustomEvent('atlas:whatif-result', {
        detail: {
          partnerName: partner.name,
          lat,
          lon: lng,
          suggestedCap,
          suggestedRadius,
          estimatedAdvGain,
        },
      }),
    );
  }, [partner, heatmapFeatures]);

  return (
    <>
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
  const allMarkersData = useStore((s) => s.allMarkersData);
  const heatmapData = useStore((s) => s.heatmapData);

  if (!whatIfModeActive) return null;

  const activePartners = allMarkersData.filter(
    (p): p is Partner & { lat: number; lon: number } =>
      p.status === 'Active' &&
      p.lat !== null &&
      p.lat !== 0 &&
      p.lon !== null &&
      p.lon !== 0,
  );

  const heatmapFeatures: GeoJSON.Feature[] = heatmapData?.features ?? [];

  return (
    <>
      {activePartners.map((partner) => (
        <WhatIfMarker
          key={partner.salesforce_id}
          partner={partner}
          heatmapFeatures={heatmapFeatures}
        />
      ))}
    </>
  );
}
