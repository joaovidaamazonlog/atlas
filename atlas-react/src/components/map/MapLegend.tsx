/**
 * MapLegend.tsx
 * =============
 * Legenda do mapa no canto inferior direito.
 * Mostra colorMap de borda (primaryField) e preenchimento (secondaryField).
 */

import { useMemo } from 'react';
import { useMap } from 'react-leaflet';
import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useStore } from '../../store';
import { buildColorMaps } from '../../lib/colorUtils';

export default function MapLegend() {
  const map = useMap();
  const data = useStore((s) => s.currentFilteredData);
  const styleConfig = useStore((s) => s.styleConfig);
  const prospectActive = useStore((s) => s.prospectState.companies.length > 0);
  const controlRef = useRef<L.Control | null>(null);

  const colorMaps = useMemo(
    () => buildColorMaps(data, styleConfig),
    [data, styleConfig],
  );

  useEffect(() => {
    // Remove controle anterior
    if (controlRef.current) {
      map.removeControl(controlRef.current);
      controlRef.current = null;
    }

    // Não exibir legenda quando prospect está ativo
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

        // Borda (primaryField)
        html += `<b>Borda (${styleConfig.primaryField}):</b><br>`;
        for (const [key, color] of Object.entries(colorMaps.border)) {
          html += `<span style="display:inline-block;width:14px;height:14px;background:#fff;border:3px solid ${color};margin-right:5px;vertical-align:middle;"></span>${key}<br>`;
        }

        // Preenchimento (secondaryField) — só quando diferente do primário
        if (Object.keys(colorMaps.fill).length > 0) {
          html += `<hr style="border-color:#4a5568;margin:6px 0;"><b>Preenchimento (${styleConfig.secondaryField}):</b><br>`;
          for (const [key, color] of Object.entries(colorMaps.fill)) {
            html += `<span style="display:inline-block;width:14px;height:14px;background:${color};border:1.5px solid #222;margin-right:5px;vertical-align:middle;"></span>${key}<br>`;
          }
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
  }, [map, colorMaps, styleConfig, prospectActive]);

  return null;
}
