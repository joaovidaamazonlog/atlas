/**
 * RouteLayer.tsx
 * ==============
 * Camada de rota no mapa usando leaflet-routing-machine.
 * Calcula rota real via OSRM e otimiza paradas intermediárias.
 */

import L from 'leaflet';
import 'leaflet-routing-machine';
import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { useStore } from '../../store';
import { optimizeStops } from '../../lib/routeUtils';

export default function RouteLayer() {
  const map = useMap();
  const route = useStore((s) => s.route);
  const setError = useStore((s) => s.setError);
  const routingControlRef = useRef<L.Routing.Control | null>(null);

  useEffect(() => {
    // Cleanup previous control
    if (routingControlRef.current) {
      map.removeControl(routingControlRef.current);
      routingControlRef.current = null;
    }

    if (route.length < 2) return;

    const [first, last, ...middle] = route;
    const optimized = optimizeStops(first, last, middle);
    const allStops = [first, ...optimized, last];

    const control = L.Routing.control({
      waypoints: allStops.map((s) => L.latLng(s.lat, s.lon)),
      router: L.Routing.osrmv1({ serviceUrl: 'https://router.project-osrm.org/route/v1' }),
      lineOptions: { styles: [{ color: 'blue', opacity: 0.8, weight: 5 }] },
      createMarker: (_i: number, wp: L.Routing.Waypoint) => L.marker(wp.latLng),
      show: true,
    });

    control.on('routingerror', (e: any) => {
      setError(`Erro ao calcular rota: ${e.error?.message ?? 'serviço OSRM indisponível'}`);
    });

    control.addTo(map);
    routingControlRef.current = control;

    return () => {
      map.removeControl(control);
      routingControlRef.current = null;
    };
  }, [route, map, setError]);

  return null;
}
