/**
 * JurisdictionLayer.tsx
 * =====================
 * Camada de jurisdições no mapa.
 * Filtra por delivery_station baseado em filterState.
 */

import { useMemo } from 'react';
import { GeoJSON } from 'react-leaflet';
import type { StyleFunction, PathOptions } from 'leaflet';
import type { Feature } from 'geojson';
import { useStore } from '../../store';
import { expandWithSatellites } from '../../lib/config';

export default function JurisdictionLayer() {
  const jurisdictionData = useStore((s) => s.jurisdictionData);
  const filterState = useStore((s) => s.filterState);
  const showJurisdictions = useStore((s) => s.styleConfig.showJurisdictions);

  const filteredData = useMemo(() => {
    if (!jurisdictionData) return null;

    const features =
      filterState.selectedStations === 'all'
        ? jurisdictionData.features
        : jurisdictionData.features.filter((f) => {
            // Expande as stations selecionadas para incluir satélites
            const expanded = expandWithSatellites(filterState.selectedStations as string[]);
            return expanded.includes(f.properties?.delivery_station);
          });

    return { type: 'FeatureCollection' as const, features };
  }, [jurisdictionData, filterState]);

  if (!showJurisdictions || !filteredData) return null;

  const styleFunc: StyleFunction = (_feature?: Feature): PathOptions => ({
    color: '#6E00B3',
    weight: 2,
    opacity: 0.8,
    fillOpacity: 0.2,
  });

  return (
    <GeoJSON
      key={JSON.stringify(filterState)}
      data={filteredData}
      style={styleFunc}
      pane="jurisdictionPane"
      onEachFeature={(feature, layer) => {
        const station = feature.properties?.delivery_station ?? '';
        layer.bindPopup(`<b>${station}</b>`);
      }}
    />
  );
}
