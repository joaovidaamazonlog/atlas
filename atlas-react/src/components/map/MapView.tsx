/**
 * MapView.tsx
 * ===========
 * Componente raiz do mapa. Inicializa o MapContainer do react-leaflet
 * e renderiza todas as camadas como filhos.
 */

import 'leaflet/dist/leaflet.css';
import React, { useEffect } from 'react';
import { MapContainer, TileLayer, useMap, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { MAP_CONFIG } from '../../lib/config';
import { useStore } from '../../store';
import PartnerMarkers from './PartnerMarkers';
import ProspectMarkers from './ProspectMarkers';
import StationMarkers from './StationMarkers';
import PolygonLayer from './PolygonLayer';
import JurisdictionLayer from './JurisdictionLayer';
import HeatmapLayer from './HeatmapLayer';
import RouteLayer from './RouteLayer';
import MapLegend from './MapLegend';
import { MapFlyTo } from './SearchBar';
import GeoIntelligenceLayer from './GeoIntelligenceLayer';
import RecruitableAreaLayer from './RecruitableAreaLayer';
import CapComparisonLayer from './CapComparisonLayer';
import PartnerWhatIfLayer from './PartnerWhatIfLayer';
import MapClickCapture from './MapClickCapture';
import RoutePickPinsLayer from './RoutePickPinsLayer';

function LayerPanesSetup() {
  const map = useMap();
  useEffect(() => {
    const panes: [string, string][] = [
      ['jurisdictionPane', '200'],
      ['polygonsPane', '250'],
      ['optimizationPane', '300'],
      ['recruitableCirclePane', '320'],
      ['recruitablePane', '340'],
      ['markersPane', '400'],
    ];
    for (const [name, zIndex] of panes) {
      if (!map.getPane(name)) {
        const pane = map.createPane(name);
        pane.style.zIndex = zIndex;
        if (name !== 'markersPane') pane.style.pointerEvents = 'none';
      }
    }
  }, [map]);
  return null;
}

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

function GeoIntelligenceLayerConditional() {
  const showGeoIntelligence = useStore((s) => s.styleConfig.showGeoIntelligence);
  if (!showGeoIntelligence) return null;
  return <GeoIntelligenceLayer />;
}

function ProspectMarkersLayer() {
  const companies = useStore((s) => s.prospectState.companies);
  const pinnedKeys = useStore((s) => s.prospectState.pinnedKeys);
  if (companies.length === 0) return null;
  return <ProspectMarkers pinnedKeys={new Set(pinnedKeys)} companies={companies} />;
}

function ManualAnalysisPinLayer() {
  const pin = useStore((s) => s.manualAnalysisPin);
  if (!pin) return null;
  return (
    <Marker position={[pin.lat, pin.lon]}>
      {pin.label && <Popup>{pin.label}</Popup>}
    </Marker>
  );
}

interface MapViewProps {
  className?: string;
  flyToRef?: React.MutableRefObject<((lat: number, lon: number) => void) | null>;
}

export default function MapView({ className, flyToRef }: MapViewProps) {
  const manualAnalysisOpen = useStore((s) => s.manualAnalysisOpen);
  const routeInputFocused = useStore((s) => s.routeInputFocused);
  return (
    <MapContainer
      center={MAP_CONFIG.center}
      zoom={MAP_CONFIG.zoom}
      zoomControl={false}
      className={className ?? 'w-full h-full'}
      style={{ width: '100%', height: '100%' }}
    >
      <TileLayer url={MAP_CONFIG.tileUrl} maxZoom={MAP_CONFIG.maxZoom} subdomains={MAP_CONFIG.subdomains} />
      <LayerPanesSetup />
      <FitBoundsWire />
      {flyToRef && <MapFlyTo flyToRef={flyToRef} />}
      <PartnerMarkers />
      <StationMarkers />
      <PolygonLayer />
      <JurisdictionLayer />
      <HeatmapLayer />
      <RouteLayer />
      <MapLegend />
      <GeoIntelligenceLayerConditional />
      <ProspectMarkersLayer />
      <ManualAnalysisPinLayer />
      <RecruitableAreaLayer />
      <CapComparisonLayer />
      <PartnerWhatIfLayer />
      <RoutePickPinsLayer />
      <MapClickCapture isActive={manualAnalysisOpen || routeInputFocused} />
    </MapContainer>
  );
}
