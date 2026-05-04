/**
 * MapClickCapture.tsx
 * ===================
 * Componente interno do mapa que captura cliques e emite um CustomEvent
 * com as coordenadas para que outros componentes (ex: AreaAnalysisTab)
 * possam reagir sem acoplamento direto.
 *
 * Quando `isActive` é false, os cliques são ignorados.
 *
 * Também bloqueamos o evento quando o modo what-if está ativo: nesse modo
 * o usuário está arrastando parceiros no mapa, e um clique acidental não
 * deve alterar a coordenada da análise manual. O what-if gera sua própria
 * coordenada via dragend (atlas:whatif-result).
 */

import { useMapEvents } from 'react-leaflet';
import { useStore } from '../../store';

interface MapClickCaptureProps {
  isActive: boolean;
}

export default function MapClickCapture({ isActive }: MapClickCaptureProps) {
  const whatIfModeActive = useStore((s) => s.whatIfModeActive);

  useMapEvents({
    click(e) {
      if (!isActive) return;
      // What-if tem precedência: não converte cliques em atualização de
      // análise manual enquanto o usuário está simulando reposicionamentos.
      if (whatIfModeActive) return;
      const { lat, lng } = e.latlng;
      document.dispatchEvent(
        new CustomEvent('atlas:map-click-coords', { detail: { lat, lng } })
      );
    },
  });

  return null;
}
