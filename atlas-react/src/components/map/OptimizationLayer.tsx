/**
 * OptimizationLayer.tsx
 * =====================
 * Camada de otimização (hexágonos H3 com demanda diária) no mapa.
 * Cor baseada em demand_daily (gradiente vermelho → verde).
 */

import { useMemo } from 'react';
import { GeoJSON } from 'react-leaflet';
import type { StyleFunction, PathOptions } from 'leaflet';
import type { Feature } from 'geojson';
import { useStore } from '../../store';

/**
 * Converte demanda em cor RGB (vermelho → verde).
 */
function demandColor(demand: number, maxDemand: number): string {
  if (maxDemand === 0) return '#e74c3c';
  const t = Math.max(0, Math.min(1, demand / maxDemand));
  const r = Math.round(231 + (46 - 231) * t);
  const g = Math.round(76 + (204 - 76) * t);
  const b = Math.round(60 + (113 - 60) * t);
  return `rgb(${r},${g},${b})`;
}

export default function OptimizationLayer() {
  const heatmapData = useStore((s) => s.heatmapData);
  const filterState = useStore((s) => s.filterState);
  const showOptimizationLayer = useStore((s) => s.styleConfig.showOptimizationLayer);

  const { filteredData, maxDemand } = useMemo(() => {
    if (!heatmapData) return { filteredData: null, maxDemand: 0 };

    const features = heatmapData.features.filter((f) => {
      const props = f.properties ?? {};

      const stationMatch =
        filterState.selectedStations === 'all' ||
        (filterState.selectedStations as string[]).includes(props.delivery_station);

      const bucketMatch =
        filterState.selectedBuckets === 'all' ||
        (filterState.selectedBuckets as string[]).includes(
          props.bucket_ade ?? props.territory_id,
        );

      return stationMatch && bucketMatch;
    });

    const max = Math.max(...features.map((f) => Number(f.properties?.demand_daily ?? 0)));

    return {
      filteredData: { type: 'FeatureCollection' as const, features },
      maxDemand: max,
    };
  }, [heatmapData, filterState]);

  if (!showOptimizationLayer || !filteredData) return null;

  const styleFunc: StyleFunction = (feature?: Feature): PathOptions => {
    const demand = Number(feature?.properties?.demand_daily ?? 0);
    return {
      color: demandColor(demand, maxDemand),
      weight: 1,
      fillOpacity: 0.3,
    };
  };

  return (
    <GeoJSON
      key={JSON.stringify(filterState)}
      data={filteredData}
      style={styleFunc}
      pane="optimizationPane"
    />
  );
}
