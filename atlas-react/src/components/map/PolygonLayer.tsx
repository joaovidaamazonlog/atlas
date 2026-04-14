/**
 * PolygonLayer.tsx
 * ================
 * Camada de polígonos de território no mapa.
 * Filtra features por delivery_station e bucket_ade baseado em filterState.
 * Quando o heatmap de prospecção está ativo (clusters.length > 0), exibe apenas
 * o polígono da carteira selecionada (selectedBucket).
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
  const prospectClusters = useStore((s) => s.prospectState.clusters);
  const selectedBucket = useStore((s) => s.prospectState.selectedBucket);

  const filteredData = useMemo(() => {
    if (!polygonsData) return null;

    const heatmapActive = prospectClusters.length > 0;

    const features = polygonsData.features.filter((f) => {
      const props = f.properties ?? {};

      // When heatmap is active, show only the polygon matching selectedBucket
      if (heatmapActive) {
        if (!selectedBucket) return false;
        return (
          props.bucket_ade === selectedBucket ||
          props.territory_id === selectedBucket
        );
      }

      // Default behavior: filter by filterState
      const stationMatch =
        filterState.selectedStations === 'all' ||
        filterState.selectedStations.includes(props.delivery_station);

      const bucketMatch =
        filterState.selectedBuckets === 'all' ||
        filterState.selectedBuckets.includes(props.bucket_ade ?? props.territory_id);

      return stationMatch && bucketMatch;
    });

    return { type: 'FeatureCollection' as const, features };
  }, [polygonsData, filterState, prospectClusters, selectedBucket]);

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
      key={JSON.stringify(filterState) + selectedBucket + prospectClusters.length}
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
