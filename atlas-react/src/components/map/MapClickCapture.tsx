/**
 * MapClickCapture.tsx
 * ===================
 * Componente interno do mapa que captura cliques e emite um CustomEvent
 * com as coordenadas para que outros componentes (ex: AreaAnalysisTab)
 * possam reagir sem acoplamento direto.
 *
 * Quando `isActive` é false, os cliques são ignorados.
 */

import { useMapEvents } from 'react-leaflet';

interface MapClickCaptureProps {
  isActive: boolean;
}

export default function MapClickCapture({ isActive }: MapClickCaptureProps) {
  useMapEvents({
    click(e) {
      if (!isActive) return;
      const { lat, lng } = e.latlng;
      document.dispatchEvent(
        new CustomEvent('atlas:map-click-coords', { detail: { lat, lng } })
      );
    },
  });

  return null;
}
