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
        let expanded = false;

        const render = () => {
          div.style.cssText = [
            'background:var(--color-dark)',
            'color:var(--color-light)',
            'border-radius:6px',
            'font-size:11px',
            'box-shadow:0 2px 8px rgba(0,0,0,0.4)',
            'min-width:120px',
            'max-width:160px',
            'overflow:hidden',
            'cursor:pointer',
            'user-select:none',
          ].join(';');

          if (!expanded) {
            div.innerHTML = `<div style="padding:6px 10px;display:flex;align-items:center;gap:6px;font-weight:600;">
              <span>▶</span> Legenda
            </div>`;
          } else {
            let html = `<div style="padding:6px 10px;display:flex;align-items:center;gap:6px;font-weight:600;border-bottom:1px solid var(--border-color);">
              <span>▼</span> Legenda
            </div>`;
            html += `<div style="padding:6px 10px;max-height:200px;overflow-y:auto;">`;
            html += `<b style="display:block;margin-bottom:4px;font-size:10px;">Borda (${styleConfig.primaryField}):</b>`;
            for (const [key, color] of Object.entries(colorMaps.border)) {
              html += `<div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
                <span style="display:inline-block;width:12px;height:12px;flex-shrink:0;background:#fff;border:2px solid ${color};border-radius:2px;"></span>
                <span style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${key}</span>
              </div>`;
            }
            if (Object.keys(colorMaps.fill).length > 0) {
              html += `<b style="display:block;margin:4px 0 2px;font-size:10px;">Preenchimento (${styleConfig.secondaryField}):</b>`;
              for (const [key, color] of Object.entries(colorMaps.fill)) {
                html += `<div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;">
                  <span style="display:inline-block;width:12px;height:12px;flex-shrink:0;background:${color};border:1px solid #222;border-radius:2px;"></span>
                  <span style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${key}</span>
                </div>`;
              }
            }
            if (showGeoIntelligence) {
              const stops = [0, 25, 50, 75, 100].map((s) => `${potentialScoreToColor(s)} ${s}%`).join(', ');
              html += `<b style="display:block;margin:4px 0 2px;font-size:10px;">Potencial:</b>`;
              html += `<div style="width:100%;height:10px;background:linear-gradient(to right,${stops});border-radius:2px;margin-bottom:2px;"></div>`;
              html += `<div style="display:flex;justify-content:space-between;font-size:9px;color:#94a3b8;"><span>0</span><span>100</span></div>`;
            }
            html += `</div>`;
            div.innerHTML = html;
          }

          div.onclick = () => {
            expanded = !expanded;
            render();
          };
        };

        render();
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
