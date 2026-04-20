/**
 * HeatmapLayer.tsx
 * ================
 * - When `activeTab === 'area'`: renders heatmap hexes as interactive GeoJSON polygons.
 *   Clicking a hex dispatches `toggleHexSelection`; selected hexes get a white border.
 * - Otherwise: renders a heat-point layer via leaflet.heat (existing behavior).
 */

import { useEffect, useRef } from 'react';
import { useMap, GeoJSON } from 'react-leaflet';
import type L from 'leaflet';
import type { PathOptions, LeafletMouseEvent } from 'leaflet';
import type { Feature } from 'geojson';
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
  const heatmapData = useStore((s) => s.heatmapData);
  const hexSelectionState = useStore((s) => s.hexSelectionState);
  const toggleHexSelection = useStore((s) => s.toggleHexSelection);
  const clearHexSelection = useStore((s) => s.clearHexSelection);

  // Clear hex selection when leaving the 'area' tab
  useEffect(() => {
    if (activeTab !== 'area') {
      clearHexSelection();
    }
  }, [activeTab, clearHexSelection]);

  if (activeTab === 'area' && heatmapData) {
    // Pre-compute max demand for color normalization
    const maxDemand = heatmapData.features.reduce((max, f) => {
      const d = (f.properties?.demand_daily as number | undefined) ?? 0;
      return d > max ? d : max;
    }, 0);

    const selectedIds = hexSelectionState.selectedHexIds;

    const hexStyle = (feature?: Feature): PathOptions => {
      if (!feature) return { fillOpacity: 0.5, weight: 1 };
      const props = feature.properties ?? {};
      const demandDaily: number = typeof props.demand_daily === 'number' ? props.demand_daily : 0;
      const hexId: string = props.hex_id ?? '';
      const isSelected = selectedIds.includes(hexId);
      const fillColor = heatmapHexColor(demandDaily, maxDemand);
      return {
        fillColor,
        color: isSelected ? 'white' : fillColor,
        weight: isSelected ? 2 : 0.5,
        fillOpacity: 0.6,
        opacity: isSelected ? 1 : 0.7,
      };
    };

    const onEachFeature = (feature: Feature, layer: L.Layer) => {
      layer.on('click', (_e: LeafletMouseEvent) => {
        const props = feature.properties ?? {};
        const hexId: string = props.hex_id ?? '';
        const demandDaily: number = typeof props.demand_daily === 'number' ? props.demand_daily : 0;
        const demandResidual: number = typeof props.demand_residual === 'number' ? props.demand_residual : 0;
        if (hexId) {
          toggleHexSelection(hexId, demandDaily, demandResidual);
        }
      });
    };

    // Key includes selectedHexIds.length so GeoJSON re-renders when selection changes
    const geoJsonKey = `area-hexes-${selectedIds.length}`;

    return (
      <GeoJSON
        key={geoJsonKey}
        data={heatmapData}
        style={hexStyle}
        onEachFeature={onEachFeature}
      />
    );
  }

  // Default: heat-point behavior
  return <HeatPoints />;
}
