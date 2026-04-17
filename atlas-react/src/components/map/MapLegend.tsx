/**
 * MapLegend.tsx
 * =============
 * Legenda do mapa no canto inferior direito.
 * Mostra colorMap de borda (primaryField) e preenchimento (secondaryField).
 * Quando a camada de Geointeligência está ativa, exibe a escala de potencial.
 */

import { useMemo, useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { useStore } from '../../store';
import { buildColorMaps } from '../../lib/colorUtils';
import { potentialScoreToColor } from '../../lib/geoIntelligenceUtils';

export default function MapLegend() {
  const map = useMap();
  const data = useStore((s) => s.currentFilteredData);
  const styleConfig = useStore((s) => s.styleConfig);
  const prospectActive = useStore((s) => s.prospectState.companies.length > 0);
  const showGeoIntelligence = useStore((s) => s.styleConfig.showGeoIntelligence);
  const controlRef = useRef<L.Control | null>(null);

  const colorMaps = useMemo(
    () => buildColorMaps(data, styleConfig),
    [data, styleConfig],
  );

  useEffect(() => {
    if (controlRef.current) {
      map.removeControl(controlRef.current);
      controlRef.current = null;
    }

    if (prospectActive) return;

    const LegendControl = L.Control.extend({
      onAdd() {
        const div = L.DomUtil.create('div');
        div.style.cssText = [
          'background:var(--color-dark)',
          'color:var(--color-light)',
          'padding:10px 14px',
          'border-radius:6px',
          'font-size:12px',
          'max-height:300px',
          'overflow-y:auto',
          'box-shadow:0 2px 8px rgba(0,0,0,0.4)',
          'min-width:160px',
        ].join(';');

        let html = '<b style="display:block;margin-bottom:6px;">Legenda</b>';

        html += `<b>Borda (${styleConfig.primaryField}):</b><br>`;
        for (const [key, color] of Object.entries(colorMaps.border)) {
          html += `<span style="display:inline-block;width:14px;height:14px;background:#fff;border:3px solid ${color};margin-right:5px;vertical-align:middle;"></span>${key}<br>`;
        }

        if (Object.keys(colorMaps.fill).length > 0) {
          html += `<hr style="border-color:#4a5568;margin:6px 0;"><b>Preenchimento (${styleConfig.secondaryField}):</b><br>`;
          for (const [key, color] of Object.entries(colorMaps.fill)) {
            html += `<span style="display:inline-block;width:14px;height:14px;background:${color};border:1.5px solid #222;margin-right:5px;vertical-align:middle;"></span>${key}<br>`;
          }
        }

        if (showGeoIntelligence) {
          const stops = [0, 25, 50, 75, 100].map((s) => `${potentialScoreToColor(s)} ${s}%`).join(', ');
          html += `<hr style="border-color:#4a5568;margin:6px 0;"><b>Potencial (Geointeligência):</b><br>`;
          html += `<div style="width:100%;height:14px;background:linear-gradient(to right,${stops});border-radius:3px;margin:4px 0 2px;border:1px solid #334155;"></div>`;
          html += `<div style="display:flex;justify-content:space-between;font-size:10px;color:#94a3b8;"><span>0</span><span>100</span></div>`;
        }

        div.innerHTML = html;
        return div;
      },
    });

    const control = new LegendControl({ position: 'bottomright' });
    control.addTo(map);
    controlRef.current = control;

    return () => {
      if (controlRef.current) {
        map.removeControl(controlRef.current);
        controlRef.current = null;
      }
    };
  }, [map, colorMaps, styleConfig, prospectActive, showGeoIntelligence]);

  return null;
}
