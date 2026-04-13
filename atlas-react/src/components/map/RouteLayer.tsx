/**
 * RouteLayer.tsx
 * ==============
 * Camada de rota no mapa.
 * Renderiza uma Polyline conectando as paradas quando há 2 ou mais.
 *
 * Nota: leaflet-routing-machine será integrado via useEffect com
 * L.Routing.control em uma iteração futura para roteamento real.
 * Por ora, usa Polyline simples conectando os pontos em ordem.
 */

import { Polyline } from 'react-leaflet';
import { useStore } from '../../store';

export default function RouteLayer() {
  const route = useStore((s) => s.route);

  if (route.length < 2) return null;

  const positions = route.map((stop) => [stop.lat, stop.lon] as [number, number]);

  return (
    <Polyline
      positions={positions}
      pathOptions={{
        color: '#3b82f6',
        opacity: 0.8,
        weight: 5,
      }}
    />
  );
}
