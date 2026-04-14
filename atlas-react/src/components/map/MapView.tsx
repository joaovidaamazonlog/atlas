/**
 * MapView.tsx
 * ===========
 * Componente raiz do mapa. Inicializa o MapContainer do react-leaflet
 * e renderiza todas as camadas como filhos.
 */

import 'leaflet/dist/leaflet.css';
import React, { useEffect } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { MAP_CONFIG } from '../../lib/config';
import { useStore } from '../../store';
import PartnerMarkers from './PartnerMarkers';
import ProspectMarkers from './ProspectMarkers';
import StationMarkers from './StationMarkers';
import PolygonLayer from './PolygonLayer';
import JurisdictionLayer from './JurisdictionLayer';
import OptimizationLayer from './OptimizationLayer';
import HeatmapLayer from './HeatmapLayer';
import RouteLayer from './RouteLayer';
import MapLegend from './MapLegend';
import { MapFlyTo } from './SearchBar';

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

// Wires store.fitBoundsRef to the Leaflet map instance
function FitBoundsWire() {
  const map = useMap();
  const fitBoundsRef = useStore((s) => s.fitBoundsRef);
  useEffect(() => {
    fitBoundsRef.current = (coords: [number, number][]) => {
      if (coords.length === 0) return;
      if (coords.length === 1) { map.setView(coords[0], 13); return; }
      map.fitBounds(L.latLngBounds(coords), { padding: [40, 40] });
    };
    return () => { fitBoundsRef.current = null; };
  }, [map, fitBoundsRef]);
  return null;
}

// ---------------------------------------------------------------------------
// PROSPECT MARKERS LAYER
// ---------------------------------------------------------------------------

function ProspectMarkersLayer() {
  const companies = useStore((s) => s.prospectState.companies);
  const pinnedKeys = useStore((s) => s.prospectState.pinnedKeys);

  if (companies.length === 0) return null;

  return (
    <ProspectMarkers
      pinnedKeys={new Set(pinnedKeys)}
      companies={companies}
    />
  );
}

// ---------------------------------------------------------------------------
// MAPVIEW
// ---------------------------------------------------------------------------

interface MapViewProps {
  className?: string;
  flyToRef?: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
}

export default function MapView({ className, flyToRef }: MapViewProps) {
  return (
    <MapContainer
      center={MAP_CONFIG.center}
      zoom={MAP_CONFIG.zoom}
      zoomControl={false}
      className={className ?? 'w-full h-full'}
      style={{ width: '100%', height: '100%' }}
    >
      <TileLayer
        url={MAP_CONFIG.tileUrl}
        maxZoom={MAP_CONFIG.maxZoom}
        subdomains={MAP_CONFIG.subdomains}
      />
      <PolygonsPaneSetup />
      <FitBoundsWire />
      {flyToRef && <MapFlyTo flyToRef={flyToRef} />}
      <PartnerMarkers />
      <StationMarkers />
      <PolygonLayer />
      <JurisdictionLayer />
      <OptimizationLayer />
      <HeatmapLayer />
      <RouteLayer />
      <MapLegend />
      <ProspectMarkersLayer />
    </MapContainer>
  );
}
