/**
 * PolygonLayer.tsx
 * ================
 * Camada de polígonos de território no mapa.
 * Filtra features por delivery_station e bucket_ade baseado em filterState.
 */

import { useMemo } from 'react';
import { GeoJSON } from 'react-leaflet';
import type { StyleFunction, PathOptions } from 'leaflet';
import type { Feature } from 'geojson';
import { useStore } from '../../store';

export default function PolygonLayer() {
  const polygonsData = useStore((s) => s.polygonsData);
  const filterState = useStore((s) => s.filterState);
  const showPolygons = useStore((s) => s.styleConfig.showPolygons);

  const filteredData = useMemo(() => {
    if (!polygonsData) return null;

    const features = polygonsData.features.filter((f) => {
      const props = f.properties ?? {};

      const stationMatch =
        filterState.selectedStations === 'all' ||
        filterState.selectedStations.includes(props.delivery_station);

      const bucketMatch =
        filterState.selectedBuckets === 'all' ||
        filterState.selectedBuckets.includes(props.bucket_ade ?? props.territory_id);

      return stationMatch && bucketMatch;
    });

    return { type: 'FeatureCollection' as const, features };
  }, [polygonsData, filterState]);

  if (!showPolygons || !filteredData) return null;

  const styleFunc: StyleFunction = (feature?: Feature): PathOptions => ({
    color: (feature?.properties?.cor as string) ?? '#3388ff',
    weight: 2,
    opacity: 0.8,
    fillOpacity: 0.2,
    pane: 'polygonsPane',
  });

  return (
    <GeoJSON
      key={JSON.stringify(filterState)}
      data={filteredData}
      style={styleFunc}
      pane="polygonsPane"
      onEachFeature={(feature, layer) => {
        const p = feature.properties ?? {};
        layer.bindPopup(`
          <div style="min-width:200px;font-size:12px;">
            <h6><b>${p.territory_id ?? ''}</b></h6>
            <p><b>Parceiros Esperados:</b> ${p.n_slots ?? 'N/A'}</p>
            <p><b>Attainment:</b> ${p.attainment != null ? Number(p.attainment).toFixed(1) + '%' : 'N/A'}</p>
            <p><b>Acuracidade:</b> ${p.accuracy != null ? Number(p.accuracy).toFixed(1) + '%' : 'N/A'}</p>
          </div>
        `);
      }}
    />
  );
}
