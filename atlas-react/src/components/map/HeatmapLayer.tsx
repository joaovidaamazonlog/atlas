/**
 * HeatmapLayer.tsx
 * ================
 * Renderiza um heatmap via leaflet.heat com os clusters de prospecção.
 */

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { useStore } from '../../store';
import { createHeatLayer, type HeatLayerInstance, type HeatLatLngTuple } from '../../lib/leafletHeat';

const supportsWebGL = (): boolean => {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch {
    return false;
  }
};

export default function HeatmapLayer(): null {
  const map = useMap();
  const clusters = useStore((s) => s.prospectState.clusters);
  const layerRef = useRef<HeatLayerInstance | null>(null);

  useEffect(() => {
    // Remove camada anterior sempre que clusters mudar
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
