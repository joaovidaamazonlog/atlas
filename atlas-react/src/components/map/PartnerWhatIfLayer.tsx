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
 * Visual after drag:
 *   - Green circle = original position + radius
 *   - Amber circle = simulated position + radius (dashed)
 *   - All other partners hidden from PartnerMarkers
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
 */

import { useRef, useCallback, useMemo } from 'react';
import { Circle, CircleMarker, Tooltip, Marker } from 'react-leaflet';
import * as turf from '@turf/turf';
import L from 'leaflet';
import { useStore } from '../../store';
import type { Partner } from '../../store/types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GUARDRAIL_RADIUS = 300; // metres
const INDIGO_COLOR = '#6366F1';
const ACTIVE_COLOR = '#22C55E';
const AMBER_COLOR  = '#F59E0B';
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
 * of the given (lat, lon) position, optionally restricted to hexagons inside
 * the provided jurisdiction polygons.
 */
export function getHexesWithinRadius(
  features: GeoJSON.Feature[],
  lat: number,
  lon: number,
  radiusMeters: number,
  jurisdictionFeatures: GeoJSON.Feature[] = [],
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
    if (dist > radiusMeters) continue;

    // Filtra hexágonos fora da jurisdição quando jurisdictionFeatures está disponível
    if (jurisdictionFeatures.length > 0) {
      const pt = turf.point([fLon, fLat]);
      const insideJurisdiction = jurisdictionFeatures.some((jf) => {
        const jGeom = jf.geometry;
        if (!jGeom) return false;
        if (jGeom.type === 'Polygon' || jGeom.type === 'MultiPolygon') {
          return turf.booleanPointInPolygon(
            pt,
            jf as GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon>,
          );
        }
        return false;
      });
      if (!insideJurisdiction) continue;
    }

    result.add(hexId);
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
  jurisdictionFeatures: GeoJSON.Feature[];
  isActive: boolean; // true = this partner is the one being simulated
  anySimulated: boolean; // true = some partner has already been dragged
  onDragStart: (id: string) => void;
  simulatedPos: [number, number] | null;
  simulatedRadius: number | null;
  onSimulatedPos: (id: string, pos: [number, number], radius: number) => void;
}

function WhatIfMarker({
  partner,
  heatmapFeatures,
  heatmapIndex,
  jurisdictionFeatures,
  isActive,
  anySimulated,
  onDragStart,
  simulatedPos,
  simulatedRadius,
  onSimulatedPos,
}: WhatIfMarkerProps) {
  const markerRef = useRef<L.Marker | null>(null);

  const handleDragStart = useCallback(() => {
    onDragStart(partner.salesforce_id);
  }, [partner.salesforce_id, onDragStart]);

  const handleDragEnd = useCallback(() => {
    const marker = markerRef.current;
    if (!marker) return;

    const { lat, lng } = marker.getLatLng();
    const origLat = partner.lat;
    const origLon = partner.lon;

    const dist = haversineDistance(origLat, origLon, lat, lng);

    if (dist > GUARDRAIL_RADIUS) {
      marker.setLatLng([origLat, origLon]);
      document.dispatchEvent(
        new CustomEvent('atlas:whatif-warning', {
          detail: { message: `${partner.name}: posição fora do raio de 300 m. Marcador reposicionado.` },
        }),
      );
      return;
    }

    const { radiusMeters: currentRadius } = useStore.getState().recruitableAnalysis.params;

    const hexesOriginal = getHexesWithinRadius(heatmapFeatures, origLat, origLon, currentRadius, jurisdictionFeatures);
    const hexesSimulated = getHexesWithinRadius(heatmapFeatures, lat, lng, currentRadius, jurisdictionFeatures);

    const hexesLost    = new Set([...hexesOriginal].filter(h => !hexesSimulated.has(h)));
    const hexesGained  = new Set([...hexesSimulated].filter(h => !hexesOriginal.has(h)));

    const hexCoverageMap = new Map<string, number>(
      (partner.hex_coverage ?? []).map(e => [e.hex_id, e.packages_allocated])
    );

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

    onSimulatedPos(partner.salesforce_id, [lat, lng], currentRadius);

    document.dispatchEvent(
      new CustomEvent('atlas:whatif-result', {
        detail: {
          partnerName: partner.name,
          simulatedLat: lat,
          simulatedLon: lng,
          advSimulated,
          simulatedRadius: currentRadius,
          advGain,
          originalCap: partner.capacity,
        },
      }),
    );
  }, [partner, heatmapFeatures, heatmapIndex, jurisdictionFeatures, onSimulatedPos]);

  const origPos: [number, number] = [partner.lat, partner.lon];
  const simPos = simulatedPos ?? origPos;
  const hasMoved = simulatedPos !== null &&
    (simulatedPos[0] !== origPos[0] || simulatedPos[1] !== origPos[1]);

  // Another partner is being simulated — hide this one entirely
  if (!isActive && anySimulated) return null;

  // No simulation yet — show guardrail + draggable marker for all partners
  if (!isActive) {
    return (
      <>
        <CircleMarker
          center={origPos}
          radius={7}
          pane="markersPane"
          pathOptions={{ color: INDIGO_COLOR, fillColor: INDIGO_COLOR, weight: 2, fillOpacity: 0.25 }}
        />
        <Marker
          position={origPos}
          draggable
          ref={markerRef}
          eventHandlers={{ dragstart: handleDragStart, dragend: handleDragEnd }}
        />
        <Circle
          center={origPos}
          radius={GUARDRAIL_RADIUS}
          pathOptions={{ color: INDIGO_COLOR, fillOpacity: 0.04, weight: 2, dashArray: '6 4', interactive: false }}
        />
      </>
    );
  }

  // This partner is active — show full comparison visual
  return (
    <>
      {/* ── Original position — green, using partner's real radius ── */}
      <CircleMarker
        center={origPos}
        radius={10}
        pane="markersPane"
        pathOptions={{ color: ACTIVE_COLOR, fillColor: ACTIVE_COLOR, fillOpacity: 0.85, weight: 2 }}
      >
        <Tooltip direction="top" permanent={false}>
          {partner.name} — atual (cap {partner.capacity}, raio {partner.radius} m)
        </Tooltip>
      </CircleMarker>
      <Circle
        center={origPos}
        radius={partner.radius}
        pathOptions={{ color: ACTIVE_COLOR, fillColor: ACTIVE_COLOR, fillOpacity: 0.06, weight: 2 }}
      />

      {/* ── Simulated position — amber, using analysis radius ── */}
      {hasMoved && (
        <>
          <CircleMarker
            center={simPos}
            radius={10}
            pane="markersPane"
            pathOptions={{ color: AMBER_COLOR, fillColor: AMBER_COLOR, fillOpacity: 0.85, weight: 3 }}
          >
            <Tooltip direction="top" permanent={false}>
              {partner.name} — simulado (raio {simulatedRadius} m)
            </Tooltip>
          </CircleMarker>
          <Circle
            center={simPos}
            radius={simulatedRadius ?? partner.radius}
            pathOptions={{ color: AMBER_COLOR, fillColor: AMBER_COLOR, fillOpacity: 0.06, weight: 2, dashArray: '6 4' }}
          />
        </>
      )}

      {/* ── Draggable marker (hidden after drag, always draggable for re-simulation) ── */}
      <Marker
        position={origPos}
        draggable
        ref={markerRef}
        eventHandlers={{ dragstart: handleDragStart, dragend: handleDragEnd }}
        icon={hasMoved
          ? L.divIcon({ className: '', iconSize: [0, 0], iconAnchor: [0, 0] })
          : new L.Icon.Default()
        }
      />

      {/* ── 300 m guardrail ── */}
      <Circle
        center={origPos}
        radius={GUARDRAIL_RADIUS}
        pathOptions={{ color: INDIGO_COLOR, fillOpacity: 0.04, weight: 1.5, dashArray: '6 4', interactive: false }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main layer component
// ---------------------------------------------------------------------------

export default function PartnerWhatIfLayer() {
  const whatIfModeActive      = useStore((s) => s.whatIfModeActive);
  const whatIfPartnerId       = useStore((s) => s.whatIfPartnerId);
  const setWhatIfPartnerId    = useStore((s) => s.setWhatIfPartnerId);
  const whatIfSimulatedData   = useStore((s) => s.whatIfSimulatedData);
  const setWhatIfSimulatedData = useStore((s) => s.setWhatIfSimulatedData);
  const currentFilteredData   = useStore((s) => s.currentFilteredData);
  const heatmapData           = useStore((s) => s.heatmapData);
  const jurisdictionData      = useStore((s) => s.jurisdictionData);

  const heatmapFeatures: GeoJSON.Feature[] = heatmapData?.features ?? [];
  const jurisdictionFeatures: GeoJSON.Feature[] = jurisdictionData?.features ?? [];

  const heatmapIndex = useMemo(
    () => new Map(
      heatmapFeatures
        .filter(f => f.properties?.hex_id)
        .map(f => [f.properties!.hex_id as string, f])
    ),
    [heatmapFeatures]
  );

  const handleDragStart = useCallback((id: string) => {
    setWhatIfPartnerId(id);
    setWhatIfSimulatedData(null); // clear previous simulation on new drag
  }, [setWhatIfPartnerId, setWhatIfSimulatedData]);

  const handleSimulatedPos = useCallback((id: string, pos: [number, number], radius: number) => {
    setWhatIfSimulatedData({ id, pos, radius });
  }, [setWhatIfSimulatedData]);

  if (!whatIfModeActive) return null;

  const anySimulated = whatIfPartnerId !== null;

  const activePartners = currentFilteredData.filter(
    (p): p is Partner & { lat: number; lon: number } =>
      p.status === 'Active' &&
      p.lat !== null && p.lat !== 0 &&
      p.lon !== null && p.lon !== 0,
  );

  return (
    <>
      {activePartners.map((partner) => {
        const isActive = whatIfPartnerId === partner.salesforce_id;
        const simPos = (whatIfSimulatedData?.id === partner.salesforce_id) ? whatIfSimulatedData.pos : null;
        const simRadius = (whatIfSimulatedData?.id === partner.salesforce_id) ? whatIfSimulatedData.radius : null;
        return (
          <WhatIfMarker
            key={partner.salesforce_id}
            partner={partner}
            heatmapFeatures={heatmapFeatures}
            heatmapIndex={heatmapIndex}
            jurisdictionFeatures={jurisdictionFeatures}
            isActive={isActive}
            anySimulated={anySimulated}
            onDragStart={handleDragStart}
            simulatedPos={simPos}
            simulatedRadius={simRadius}
            onSimulatedPos={handleSimulatedPos}
          />
        );
      })}
    </>
  );
}
