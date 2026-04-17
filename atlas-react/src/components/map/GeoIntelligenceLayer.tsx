/**
 * GeoIntelligenceLayer.tsx
 * ========================
 * Camada de Geointeligência no mapa react-leaflet.
 * Renderiza territórios como polígonos coloridos e pontos de supply ideal.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 10.3, 10.5, 11.9
 */

import React, { useMemo } from 'react';
import { Polygon, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../store';
import { potentialScoreToColor, regionTypeLabel, formatGap } from '../../lib/geoIntelligenceUtils';
import type { TerritoryOutput } from '../../store/geoIntelligenceSlice';

function extractPositions(geometry: GeoJSON.Geometry): [number, number][][] {
  if (geometry.type === 'Polygon') {
    return [geometry.coordinates[0].map(([lng, lat]) => [lat, lng] as [number, number])];
  }
  if (geometry.type === 'MultiPolygon') {
    return geometry.coordinates.map((poly) =>
      poly[0].map(([lng, lat]) => [lat, lng] as [number, number]),
    );
  }
  return [];
}

const idealSupplyIcon = L.divIcon({
  className: '',
  html: `<div style="width:14px;height:14px;background:#f97316;border:2px solid #fff;border-radius:50%;box-shadow:0 0 4px rgba(0,0,0,0.5);"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function TerritoryPolygon({ territory, geojsonFeature }: { territory: TerritoryOutput; geojsonFeature: GeoJSON.Feature }) {
  const selectGeoTerritory = useStore((s) => s.selectGeoTerritory);
  const selectedTerritoryId = useStore((s) => s.geoIntelligence.selectedTerritoryId);
  const fillColor = potentialScoreToColor(territory.potential_score);
  const isSelected = selectedTerritoryId === territory.territory_id;
  const pathOptions: L.PathOptions = {
    color: territory.high_opportunity ? '#f97316' : '#334155',
    weight: territory.high_opportunity ? 3 : 1.5,
    opacity: isSelected ? 1 : 0.85,
    fillColor,
    fillOpacity: isSelected ? 0.65 : 0.45,
  };
  const positionSets = extractPositions(geojsonFeature.geometry);
  if (positionSets.length === 0) return null;
  return (
    <>
      {positionSets.map((positions, idx) => (
        <Polygon key={`${territory.territory_id}-${idx}`} positions={positions} pathOptions={pathOptions}
          eventHandlers={{ click: () => selectGeoTerritory(territory.territory_id) }}>
          <Popup>
            <div style={{ minWidth: 200, fontSize: 12 }}>
              <b style={{ display: 'block', marginBottom: 4 }}>{territory.territory_id}</b>
              <p style={{ margin: '2px 0' }}><b>Tipo:</b> {regionTypeLabel(territory.region_type)}</p>
              <p style={{ margin: '2px 0' }}><b>Potencial:</b> {territory.potential_score.toFixed(1)}</p>
              <p style={{ margin: '2px 0' }}><b>Parceiros atuais:</b> {territory.current_partners}</p>
              <p style={{ margin: '2px 0' }}><b>Gap:</b> {formatGap(territory.gap)}</p>
              <p style={{ margin: '2px 0' }}>
                <b>Confiança:</b> {(territory.model_confidence * 100).toFixed(0)}%
                {territory.low_confidence && <span style={{ color: '#f97316', marginLeft: 4 }}>⚠ baixa</span>}
              </p>
              {territory.high_opportunity && <p style={{ margin: '4px 0 0', color: '#f97316', fontWeight: 'bold' }}>★ Alta oportunidade</p>}
            </div>
          </Popup>
        </Polygon>
      ))}
    </>
  );
}

function GeoLoadingOverlay() {
  const map = useMap();
  const center = map.getCenter();
  return (
    <Marker position={[center.lat, center.lng]} interactive={false}
      icon={L.divIcon({
        className: '',
        html: `<div style="background:rgba(15,23,42,0.85);color:#e2e8f0;padding:8px 14px;border-radius:6px;font-size:13px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,0.4);">Carregando geointeligência...</div>`,
        iconAnchor: [80, 20],
      })} />
  );
}

export default function GeoIntelligenceLayer() {
  const territories = useStore((s) => s.geoIntelligence.territories);
  const geojson = useStore((s) => s.geoIntelligence.geojson);
  const isLoading = useStore((s) => s.geoIntelligence.isLoading);
  const filter = useStore((s) => s.geoIntelligence.filter);

  const featureMap = useMemo(() => {
    const map = new Map<string, GeoJSON.Feature>();
    if (!geojson) return map;
    for (const feature of geojson.features) {
      const id = feature.properties?.territory_id as string | undefined;
      if (id) map.set(id, feature);
    }
    return map;
  }, [geojson]);

  const visibleTerritories = useMemo(() => {
    if (filter.regionTypes === 'all') return territories;
    return territories.filter((t) => (filter.regionTypes as string[]).includes(t.region_type));
  }, [territories, filter.regionTypes]);

  if (!isLoading && territories.length === 0) return null;
  if (isLoading) return <GeoLoadingOverlay />;

  const supplyFeatures = geojson?.features.filter((f) => f.properties?.supply_id || f.properties?.type === 'IDEAL_SLOT') ?? [];

  return (
    <>
      {visibleTerritories.map((territory) => {
        const feature = featureMap.get(territory.territory_id);
        if (!feature) return null;
        return <TerritoryPolygon key={territory.territory_id} territory={territory} geojsonFeature={feature} />;
      })}
      {supplyFeatures.map((f, i) => {
        const coords = (f.geometry as GeoJSON.Point)?.coordinates;
        if (!coords) return null;
        const [lng, lat] = coords;
        const p = f.properties ?? {};
        return (
          <Marker key={p.supply_id ?? `supply-${i}`} position={[lat, lng]} icon={idealSupplyIcon}>
            <Popup>
              <div style={{ fontSize: 12 }}>
                <b>Ponto de Supply Ideal</b>
                {p.capacity_day != null && <p style={{ margin: '2px 0' }}><b>Capacidade/dia:</b> {p.capacity_day}</p>}
                {p.radius_km != null && <p style={{ margin: '2px 0' }}><b>Raio:</b> {p.radius_km} km</p>}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </>
  );
}
