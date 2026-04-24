/**
 * RouteLayer.tsx
 * ==============
 * Camada de rota no mapa.
 * - LRM com show:false — só calcula rota e desenha linha.
 * - Painel customizado via portal seguindo padrão visual Atlas.
 * - Hover em instrução: marcador temporário no mapa.
 * - GPS animado: seta de navegação percorre a rota automaticamente.
 */

import L from 'leaflet';
import 'leaflet-routing-machine';
import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useMap } from 'react-leaflet';
import { useStore } from '../../store';
import { optimizeStops } from '../../lib/routeUtils';
import type { RouteStop } from '../../store/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDistance(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
}

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}min` : `${m} min`;
}

function ManeuverIcon({ type, modifier }: { type: string; modifier?: string }) {
  const mod = (modifier ?? '').toLowerCase();
  const t   = (type ?? '').toLowerCase();
  let arrow = '↑';
  if (t === 'depart')  arrow = '▶';
  else if (t === 'arrive') arrow = '●';
  else if (t === 'roundabout' || t === 'rotary') arrow = '↻';
  else if (t === 'merge')  arrow = '⤴';
  else if (t === 'fork')   arrow = mod.includes('right') ? '⤷' : '⤶';
  else if (t === 'on ramp' || t === 'off ramp') arrow = mod.includes('right') ? '↱' : '↰';
  else if (t === 'end of road') arrow = mod.includes('right') ? '→' : '←';
  else {
    if (mod === 'uturn')        arrow = '↩';
    else if (mod === 'sharp left')   arrow = '↰';
    else if (mod === 'left')         arrow = '←';
    else if (mod === 'slight left')  arrow = '↖';
    else if (mod === 'straight')     arrow = '↑';
    else if (mod === 'slight right') arrow = '↗';
    else if (mod === 'right')        arrow = '→';
    else if (mod === 'sharp right')  arrow = '↱';
  }
  return <span className="text-sm text-atlas-muted shrink-0 w-5 text-center" style={{ lineHeight: 1 }}>{arrow}</span>;
}

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

interface RouteInstruction {
  text: string;
  distance: number;
  type: string;
  modifier?: string;
  waypointIndex?: number;
  /** coordenada do ponto desta instrução */
  latlng?: [number, number];
}

interface RouteData {
  totalDistance: number;
  totalDuration: number;
  instructions: RouteInstruction[];
  /** geometria completa da rota como array de [lat, lon] */
  coordinates: [number, number][];
}

// ---------------------------------------------------------------------------
// WaypointCard — card do parceiro com distância e tempo acumulados
// ---------------------------------------------------------------------------

function WaypointCard({ stop, distance, duration, arrivalText }: { stop: RouteStop; distance?: number; duration?: number; arrivalText?: string }) {
  return (
    <div className="rounded-lg bg-atlas-navy border border-[var(--border-color)] px-3 py-2.5 flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-pink-400 text-sm shrink-0">📍</span>
        <span className="text-sm font-semibold text-atlas-light truncate">{stop.name}</span>
      </div>
      {(distance != null || duration != null) && (
        <div className="flex items-center gap-3 pl-6">
          {distance != null && (
            <span className="text-xs text-atlas-muted flex items-center gap-1">
              🛣️ {fmtDistance(distance)}
            </span>
          )}
          {duration != null && (
            <span className="text-xs text-atlas-muted flex items-center gap-1">
              ⏱️ {fmtDuration(duration)}
            </span>
          )}
        </div>
      )}
      {arrivalText && (
        <div className="flex items-center gap-2 pl-6 pt-0.5 border-t border-[var(--border-color)] mt-0.5">
          <span className="text-xs text-atlas-muted">←</span>
          <span className="text-xs text-atlas-muted italic">{arrivalText}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoutePanel
// ---------------------------------------------------------------------------

interface RoutePanelProps {
  origin: RouteStop;
  destination: RouteStop;
  stops: RouteStop[];
  isCircular: boolean;
  routeData: RouteData;
  map: L.Map;
  totalDistance: number;
  totalDuration: number;
}

function RoutePanel({ origin, destination, stops, isCircular, routeData, map, totalDistance, totalDuration }: RoutePanelProps) {
  const waypointStops: RouteStop[] = [origin, ...stops, destination];
  const hoverMarkerRef = useRef<L.Marker | null>(null);
  const gpsMarkerRef   = useRef<L.Marker | null>(null);
  const gpsAnimRef     = useRef<number | null>(null);
  const [gpsActive, setGpsActive] = useState(false);
  const gpsIdxRef = useRef(0);

  // Limpa marcador de hover ao desmontar
  useEffect(() => {
    return () => {
      if (hoverMarkerRef.current) { map.removeLayer(hoverMarkerRef.current); hoverMarkerRef.current = null; }
      if (gpsMarkerRef.current)   { map.removeLayer(gpsMarkerRef.current);   gpsMarkerRef.current = null; }
      if (gpsAnimRef.current)     { cancelAnimationFrame(gpsAnimRef.current); gpsAnimRef.current = null; }
    };
  }, [map]);

  // Hover: mostra marcador no ponto da instrução
  const handleInstrEnter = useCallback((latlng: [number, number]) => {
    if (hoverMarkerRef.current) { map.removeLayer(hoverMarkerRef.current); }
    hoverMarkerRef.current = L.circleMarker([latlng[0], latlng[1]], {
      radius: 8, color: '#3b82f6', fillColor: '#93c5fd',
      fillOpacity: 0.9, weight: 2,
    }).addTo(map);
  }, [map]);

  const handleInstrLeave = useCallback(() => {
    if (hoverMarkerRef.current) { map.removeLayer(hoverMarkerRef.current); hoverMarkerRef.current = null; }
  }, [map]);

  // GPS animado: percorre as coordenadas da rota com marcador circular
  const startGps = useCallback(() => {
    if (routeData.coordinates.length < 2) return;
    setGpsActive(true);
    gpsIdxRef.current = 0;

    if (!gpsMarkerRef.current) {
      const [lat, lon] = routeData.coordinates[0];
      gpsMarkerRef.current = L.circleMarker([lat, lon], {
        radius: 10,
        color: '#ffffff',
        fillColor: '#3b82f6',
        fillOpacity: 1,
        weight: 3,
      }).addTo(map);
    }

    const coords = routeData.coordinates;
    const totalPts = coords.length;
    const msPerStep = Math.max(20, (totalDuration * 1000) / totalPts / 50);

    const step = () => {
      const idx = gpsIdxRef.current;
      if (idx >= totalPts - 1) {
        setGpsActive(false);
        return;
      }
      const [lat, lon] = coords[idx];
      (gpsMarkerRef.current as L.CircleMarker)?.setLatLng([lat, lon]);
      gpsIdxRef.current = idx + 1;
      gpsAnimRef.current = window.setTimeout(step, msPerStep) as unknown as number;
    };
    step();
  }, [map, routeData.coordinates, totalDuration]);

  const stopGps = useCallback(() => {
    if (gpsAnimRef.current) { clearTimeout(gpsAnimRef.current); gpsAnimRef.current = null; }
    if (gpsMarkerRef.current) { map.removeLayer(gpsMarkerRef.current); gpsMarkerRef.current = null; }
    setGpsActive(false);
    gpsIdxRef.current = 0;
  }, [map]);

  return createPortal(
    <div
      className="fixed flex flex-col overflow-hidden"
      style={{
        top: '56px', right: '0', bottom: '0',
        width: 'clamp(360px, 28vw, 480px)',
        zIndex: 'var(--z-overlay)' as unknown as number,
        backgroundColor: 'var(--color-navy)',
        borderLeft: '1px solid var(--border-color)',
      }}
    >
      {/* ── Header ── */}
      <div className="px-4 py-3 shrink-0 border-b border-[var(--border-color)]">
        {/* Linha 1: Origem + botão GPS */}
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <div className="flex flex-col gap-1 min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="text-xs text-atlas-muted shrink-0 w-14">Origem:</span>
              <span className="text-sm font-semibold text-atlas-light truncate">➜ {origin.name}</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-xs text-atlas-muted shrink-0 w-14">Destino:</span>
              <span className="text-sm font-semibold text-atlas-light truncate">{isCircular ? '↩ ' : ''}{destination.name}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={gpsActive ? stopGps : startGps}
            title={gpsActive ? 'Parar simulação GPS' : 'Simular percurso GPS'}
            className={`shrink-0 flex items-center gap-1.5 text-xs font-semibold rounded-md px-2.5 py-1.5 border transition-colors ${
              gpsActive
                ? 'bg-blue-500/20 border-blue-500/40 text-blue-400 hover:bg-blue-500/30'
                : 'bg-atlas-dark border-[var(--border-color)] text-atlas-muted hover:text-atlas-light hover:border-atlas-accent'
            }`}
          >
            {gpsActive ? '⏹' : '▶'} GPS
          </button>
        </div>

        {/* Linha 2: Paradas · Distância · Tempo */}
        <div className="flex items-center mt-2 pt-2 border-t border-[var(--border-color)]">
          <div className="flex flex-col items-center gap-0.5 flex-1">
            <span className="text-xs text-atlas-muted">Paradas</span>
            <span className="text-sm font-semibold text-atlas-light">{stops.length}</span>
          </div>
          <div className="w-px h-6 bg-[var(--border-color)]" />
          <div className="flex flex-col items-center gap-0.5 flex-1">
            <span className="text-xs text-atlas-muted">Distância</span>
            <span className="text-sm font-semibold text-atlas-light">{fmtDistance(totalDistance)}</span>
          </div>
          <div className="w-px h-6 bg-[var(--border-color)]" />
          <div className="flex flex-col items-center gap-0.5 flex-1">
            <span className="text-xs text-atlas-muted">Tempo</span>
            <span className="text-sm font-semibold text-atlas-light">{fmtDuration(totalDuration)}</span>
          </div>
        </div>
      </div>

      {/* ── Instruções ── */}
      <div className="flex-1 overflow-y-auto bg-atlas-darker p-3 flex flex-col gap-2">
        {routeData.instructions.map((instr, i) => {
          const isArrival =
            instr.type === 'WaypointReached' ||
            instr.type === 'DestinationReached' ||
            instr.text.toLowerCase().includes('you have arrived');

          const arrivalStop = isArrival && instr.waypointIndex != null
            ? waypointStops[instr.waypointIndex]
            : null;

          // Distância/tempo acumulados até esta parada (aproximação)
          const arrivalDist = arrivalStop && instr.waypointIndex != null
            ? routeData.instructions
                .slice(0, i + 1)
                .reduce((s, ins) => s + (ins.distance ?? 0), 0)
            : undefined;
          const arrivalDur = arrivalDist != null
            ? (arrivalDist / totalDistance) * totalDuration
            : undefined;

          return (
            <div key={i}>
              {arrivalStop && (
                <WaypointCard
                  stop={arrivalStop}
                  distance={arrivalDist}
                  duration={arrivalDur}
                  arrivalText={instr.text}
                />
              )}
              {!arrivalStop && (
                <div
                  className="flex items-start gap-3 px-3 py-2.5 rounded-lg bg-atlas-navy border border-[var(--border-color)] hover:bg-atlas-dark transition-colors cursor-default"
                  onMouseEnter={() => instr.latlng && handleInstrEnter(instr.latlng)}
                  onMouseLeave={handleInstrLeave}
                >
                  <ManeuverIcon type={instr.type} modifier={instr.modifier} />
                  <span className="flex-1 text-xs text-atlas-light leading-snug">{instr.text}</span>
                  {instr.distance > 0 && (
                    <span className="text-xs text-atlas-muted shrink-0 text-right min-w-[40px]">
                      {fmtDistance(instr.distance)}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// RouteLayer
// ---------------------------------------------------------------------------

export default function RouteLayer() {
  const map = useMap();
  const route = useStore((s) => s.route);
  const setError = useStore((s) => s.setError);
  const routingControlRef = useRef<L.Routing.Control | null>(null);
  const [routeData, setRouteData] = useState<RouteData | null>(null);

  useEffect(() => {
    if (routingControlRef.current) {
      map.removeControl(routingControlRef.current);
      routingControlRef.current = null;
    }
    setRouteData(null);

    if (route.length < 2) return;

    const first    = route[0];
    const last     = route[route.length - 1];
    const middle   = route.slice(1, -1);
    const isCircular = first.lat === last.lat && first.lon === last.lon;
    const deduped  = middle.filter((s) => !(s.lat === first.lat && s.lon === first.lon));
    const optimized = deduped.length > 1 ? optimizeStops(first, last, deduped) : deduped;

    const finalWaypoint = isCircular
      ? L.latLng(last.lat + 0.0003, last.lon + 0.0003)
      : L.latLng(last.lat, last.lon);

    const allWaypoints = [
      L.latLng(first.lat, first.lon),
      ...optimized.map((s) => L.latLng(s.lat, s.lon)),
      finalWaypoint,
    ];

    const control = L.Routing.control({
      waypoints: allWaypoints,
      router: L.Routing.osrmv1({
        serviceUrl: 'https://router.project-osrm.org/route/v1',
        requestParameters: { continue_straight: 'false' },
      }),
      lineOptions: {
        styles: [{ color: '#3b82f6', opacity: 0.85, weight: 5 }],
        extendToWaypoints: false,
        missingRouteTolerance: 0,
      },
      show: false,
      addWaypoints: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      createMarker: (_i: number, wp: any) => L.marker(wp.latLng),
    } as L.Routing.RoutingControlOptions);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    control.on('routingerror', (e: any) => {
      setError(`Erro ao calcular rota: ${e.error?.message ?? 'serviço OSRM indisponível'}`);
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    control.on('routesfound', (e: any) => {
      const r = e.routes?.[0];
      if (!r) return;

      // Coordenadas da geometria completa
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const coordinates: [number, number][] = (r.coordinates ?? []).map((c: any) => [c.lat, c.lng]);

      let wpIdx = 0;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const instructions: RouteInstruction[] = (r.instructions ?? []).map((instr: any) => {
        const isArrival =
          instr.type === 'WaypointReached' ||
          instr.type === 'DestinationReached' ||
          (instr.text ?? '').toLowerCase().includes('you have arrived');

        let waypointIndex: number | undefined;
        if (isArrival) { wpIdx += 1; waypointIndex = wpIdx; }

        // Coordenada do ponto desta instrução (índice na geometria)
        let latlng: [number, number] | undefined;
        if (instr.index != null && coordinates[instr.index]) {
          latlng = coordinates[instr.index];
        }

        return {
          text: instr.text ?? '',
          distance: instr.distance ?? 0,
          type: instr.type ?? 'continue',
          modifier: instr.modifier,
          waypointIndex,
          latlng,
        };
      });

      setRouteData({
        totalDistance: r.summary?.totalDistance ?? 0,
        totalDuration: r.summary?.totalTime ?? 0,
        instructions,
        coordinates,
      });
    });

    control.addTo(map);
    routingControlRef.current = control;

    return () => {
      if (routingControlRef.current) {
        map.removeControl(routingControlRef.current);
        routingControlRef.current = null;
      }
      setRouteData(null);
    };
  }, [route, map, setError]);

  if (!routeData || route.length < 2) return null;

  const first    = route[0];
  const last     = route[route.length - 1];
  const middle   = route.slice(1, -1);
  const isCircular = first.lat === last.lat && first.lon === last.lon;
  const deduped  = middle.filter((s) => !(s.lat === first.lat && s.lon === first.lon));
  const optimized = deduped.length > 1 ? optimizeStops(first, last, deduped) : deduped;

  return (
    <RoutePanel
      origin={first}
      destination={last}
      stops={optimized}
      isCircular={isCircular}
      routeData={routeData}
      map={map}
      totalDistance={routeData.totalDistance}
      totalDuration={routeData.totalDuration}
    />
  );
}
