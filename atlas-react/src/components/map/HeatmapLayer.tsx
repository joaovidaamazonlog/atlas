/**
 * HeatmapLayer.tsx
 * ================
 * Renderiza um heatmap via leaflet.heat com os clusters de prospecção.
 * Lê prospectState.clusters do store Zustand e usa useMap() do react-leaflet.
 *
 * Requisitos: 5.1, 5.3, 5.5, 5.6, 6.3
 */

import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet.heat';
import { useStore } from '../../store';

// ---------------------------------------------------------------------------
// WebGL detection
// ---------------------------------------------------------------------------

const supportsWebGL = (): boolean => {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch {
    return false;
  }
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function HeatmapLayer(): null {
  const map = useMap();
  const clusters = useStore((s) => s.prospectState.clusters);

  useEffect(() => {
    // Req 6.3: não renderizar quando clusters está vazio
    if (!clusters || clusters.length === 0) return;

    // Req 5.5 / 5.6: detectar suporte a WebGL para ajustar radius/blur
    const webgl = supportsWebGL();
    const radius = webgl ? 40 : 25;
    const blur = webgl ? 25 : 15;

    // Req 5.1 / 5.3: construir pontos [lat, lon, intensity] para cada cluster
    const points: [number, number, number][] = clusters.map((cluster) => [
      cluster.centroid.lat,
      cluster.centroid.lon,
      cluster.intensity,
    ]);

    // Criar e adicionar a camada ao mapa
    const heatLayer = L.heatLayer(points, { radius, blur });
    heatLayer.addTo(map);

    // Cleanup: remover a camada ao desmontar ou quando clusters mudar
    return () => {
      map.removeLayer(heatLayer);
    };
  }, [map, clusters]);

  return null;
}
