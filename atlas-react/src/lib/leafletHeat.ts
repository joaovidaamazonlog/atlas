/**
 * leafletHeat.ts
 * ==============
 * Importa leaflet.heat como side-effect síncrono para garantir que
 * L.heatLayer esteja disponível antes de qualquer componente usar.
 */
import L from 'leaflet';
import 'leaflet.heat';

export type HeatLatLngTuple = [number, number, number?];

export interface HeatLayerInstance extends L.Layer {
  setLatLngs(latlngs: HeatLatLngTuple[]): this;
}

declare module 'leaflet' {
  function heatLayer(
    latlngs: HeatLatLngTuple[],
    options?: { radius?: number; blur?: number; max?: number; minOpacity?: number }
  ): HeatLayerInstance;
}

export function createHeatLayer(
  points: HeatLatLngTuple[],
  options: { radius: number; blur: number }
): HeatLayerInstance {
  return L.heatLayer(points, { ...options, max: 1.0, minOpacity: 0.4 });
}
