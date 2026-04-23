/**
 * HeatmapLayer.tsx
 * ================
 * - When `activeTab === 'area'`: renders heatmap hexes as interactive GeoJSON polygons.
 *   Clicking a hex dispatches `toggleHexSelection`; selected hexes get a white border.
 * - Otherwise: renders a heat-point layer via leaflet.heat (existing behavior).
 */

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { useStore } from '../../store';
import { createHeatLayer, type HeatLayerInstance, type HeatLatLngTuple } from '../../lib/leafletHeat';

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

const supportsWebGL = (): boolean => {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch {
    return false;
  }
};

/**
 * Maps a demand_daily value to a fill color using a simple gradient:
 * low demand → blue, high demand → red (matching typical heatmap palettes).
 */
function heatmapHexColor(demandDaily: number, maxDemand: number): string {
  const t = maxDemand > 0 ? Math.min(demandDaily / maxDemand, 1) : 0;
  // blue (#3b82f6) → orange (#f97316) → red (#ef4444)
  let r: number, g: number, b: number;
  if (t < 0.5) {
    const s = t / 0.5;
    r = Math.round(59  + (249 - 59)  * s);
    g = Math.round(130 + (115 - 130) * s);
    b = Math.round(246 + (22  - 246) * s);
  } else {
    const s = (t - 0.5) / 0.5;
    r = Math.round(249 + (239 - 249) * s);
    g = Math.round(115 + (68  - 115) * s);
    b = Math.round(22  + (68  - 22)  * s);
  }
  return `rgb(${r},${g},${b})`;
}

// ---------------------------------------------------------------------------
// HEAT-POINT SUB-COMPONENT (existing behavior)
// ---------------------------------------------------------------------------

function HeatPoints(): null {
  const map = useMap();
  const clusters = useStore((s) => s.prospectState.clusters);
  const layerRef = useRef<HeatLayerInstance | null>(null);

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    if (!clusters || clusters.length === 0) return;

    const webgl = supportsWebGL();
    const radius = webgl ? 40 : 25;
    const blur = webgl ? 25 : 15;

    const points: HeatLatLngTuple[] = clusters.map((c) => [
      c.centroid.lat,
      c.centroid.lon,
      c.intensity,
    ]);

    const layer = createHeatLayer(points, { radius, blur });
    layer.addTo(map);
    layerRef.current = layer;

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [map, clusters]);

  return null;
}

// ---------------------------------------------------------------------------
// MAIN COMPONENT
// ---------------------------------------------------------------------------

export default function HeatmapLayer() {
  const activeTab = useStore((s) => s.activeTab);

  // Na aba 'area' não renderiza nada — os hexes não devem aparecer
  if (activeTab === 'area') return null;

  // Default: heat-point behavior
  return <HeatPoints />;
}
