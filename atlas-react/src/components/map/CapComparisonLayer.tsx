/**
 * CapComparisonLayer.tsx
 * ======================
 * Renders a visual comparison between a partner's current position/radius
 * and the suggested position/radius from `adv_opportunity`.
 *
 * Controlled by `capOpportunityState.selectedPartnerId` in the store.
 * Returns null when no partner is selected or the partner is not found.
 */

import { Circle, CircleMarker, Tooltip } from 'react-leaflet';
import { useStore } from '../../store';

/** Green used for Active partner markers (matches Tailwind green-500) */
const ACTIVE_COLOR = '#22C55E';

/** Amber used for the suggested position/radius */
const AMBER_COLOR = '#F59E0B';

export default function CapComparisonLayer() {
  const selectedPartnerId = useStore((s) => s.capOpportunityState.selectedPartnerId);
  const allMarkersData = useStore((s) => s.allMarkersData);

  if (!selectedPartnerId) return null;

  const partner = allMarkersData.find((p) => p.salesforce_id === selectedPartnerId);

  if (!partner || partner.lat === null || partner.lon === null) return null;
  if (!partner.adv_opportunity) return null;

  const { suggested_lat, suggested_lon, suggested_radius, suggested_cap } =
    partner.adv_opportunity;

  const currentPos: [number, number] = [partner.lat, partner.lon];
  const suggestedPos: [number, number] = [suggested_lat, suggested_lon];

  return (
    <>
      {/* Current position marker — Active color */}
      <CircleMarker
        center={currentPos}
        radius={10}
        pathOptions={{
          color: ACTIVE_COLOR,
          fillColor: ACTIVE_COLOR,
          fillOpacity: 0.85,
          weight: 2,
        }}
      >
        <Tooltip direction="top" permanent={false}>
          {partner.name} — atual (cap {partner.capacity})
        </Tooltip>
      </CircleMarker>

      {/* Suggested position marker — amber, heavier weight */}
      <CircleMarker
        center={suggestedPos}
        radius={10}
        pathOptions={{
          color: AMBER_COLOR,
          fillColor: AMBER_COLOR,
          fillOpacity: 0.85,
          weight: 3,
        }}
      >
        <Tooltip direction="top" permanent={false}>
          {partner.name} — sugerido (cap {suggested_cap})
        </Tooltip>
      </CircleMarker>

      {/* Current radius circle — Active color */}
      <Circle
        center={currentPos}
        radius={partner.radius}
        pathOptions={{
          color: ACTIVE_COLOR,
          fillColor: ACTIVE_COLOR,
          fillOpacity: 0.06,
          weight: 2,
        }}
      />

      {/* Suggested radius circle — amber, dashed */}
      <Circle
        center={suggestedPos}
        radius={suggested_radius}
        pathOptions={{
          color: AMBER_COLOR,
          fillColor: AMBER_COLOR,
          fillOpacity: 0.06,
          weight: 2,
          dashArray: '6 4',
        }}
      />
    </>
  );
}
