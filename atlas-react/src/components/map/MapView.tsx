/**
 * MapView.tsx
 * ===========
 * Componente raiz do mapa. Inicializa o MapContainer do react-leaflet
 * e renderiza todas as camadas como filhos.
 */

import 'leaflet/dist/leaflet.css';
import { useEffect } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import { MAP_CONFIG } from '../../lib/config';
import PartnerMarkers from './PartnerMarkers';
import StationMarkers from './StationMarkers';
import PolygonLayer from './PolygonLayer';
import JurisdictionLayer from './JurisdictionLayer';
import OptimizationLayer from './OptimizationLayer';
import HeatmapLayer from './HeatmapLayer';
import RouteLayer from './RouteLayer';
import MapLegend from './MapLegend';

// ---------------------------------------------------------------------------
// PANE SETUP
// ---------------------------------------------------------------------------

/**
 * Componente interno que cria o pane 'polygonsPane' via useMap().
 * Deve ser filho do MapContainer para ter acesso à instância do mapa.
 */
function PolygonsPaneSetup() {
  const map = useMap();

  useEffect(() => {
    if (!map.getPane('polygonsPane')) {
      const pane = map.createPane('polygonsPane');
      pane.style.zIndex = '200';
      pane.style.pointerEvents = 'none';
    }
  }, [map]);

  return null;
}

// ---------------------------------------------------------------------------
// MAPVIEW
// ---------------------------------------------------------------------------

interface MapViewProps {
  className?: string;
}

export default function MapView({ className }: MapViewProps) {
  return (
    <MapContainer
      center={MAP_CONFIG.center}
      zoom={MAP_CONFIG.zoom}
      className={className ?? 'w-full h-full'}
      style={{ width: '100%', height: '100%' }}
    >
      <TileLayer
        url={MAP_CONFIG.tileUrl}
        maxZoom={MAP_CONFIG.maxZoom}
        subdomains={MAP_CONFIG.subdomains}
      />
      <PolygonsPaneSetup />
      <PartnerMarkers />
      <StationMarkers />
      <PolygonLayer />
      <JurisdictionLayer />
      <OptimizationLayer />
      <HeatmapLayer />
      <RouteLayer />
      <MapLegend />
    </MapContainer>
  );
}
