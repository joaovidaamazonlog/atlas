/**
 * ProspectMarkers.tsx
 * ===================
 * Gerencia marcadores Leaflet imperativos (alfinetes) para empresas prospectadas.
 * Usa useMap() do react-leaflet e mantém um Map<string, L.Marker> em ref
 * para controle de ciclo de vida — sem JSX de react-leaflet para os marcadores.
 */

import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import type { ProspectCompany } from '../../store/types';
import { getLeadKey } from '../../lib/kmeansUtils';

interface ProspectMarkersProps {
  pinnedKeys: Set<string>;
  companies: ProspectCompany[];
}

export default function ProspectMarkers({ pinnedKeys, companies }: ProspectMarkersProps): null {
  const map = useMap();
  const markersRef = useRef<Map<string, L.Marker>>(new Map());

  useEffect(() => {
    const markers = markersRef.current;

    // Add markers for newly pinned keys
    for (const key of pinnedKeys) {
      if (!markers.has(key)) {
        const company = companies.find((c) => getLeadKey(c) === key);
        if (!company || company.lat == null || company.lon == null) continue;

        const popupContent = `<div>
  <b>${company.nome}</b><br/>
  ${company.endereco}<br/>
  ${company.telefone_1 ? `Tel: ${company.telefone_1}` : ''}
</div>`;

        const marker = L.marker([company.lat, company.lon])
          .bindPopup(popupContent)
          .addTo(map);

        markers.set(key, marker);
        map.setView([company.lat, company.lon], Math.max(map.getZoom(), 15));
      }
    }

    // Remove markers for keys no longer pinned
    for (const [key, marker] of markers) {
      if (!pinnedKeys.has(key)) {
        marker.remove();
        markers.delete(key);
      }
    }
  }, [map, pinnedKeys, companies]);

  // Cleanup all markers on unmount
  useEffect(() => {
    const markers = markersRef.current;
    return () => {
      for (const marker of markers.values()) {
        marker.remove();
      }
      markers.clear();
    };
  }, []);

  return null;
}
