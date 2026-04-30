/**
 * DSPShareLayer.tsx
 * =================
 * Layer opcional do mapa que colore cada hex pelo % DSP dentro dele,
 * usando o artefato `deliveries_by_hex.json` (Fase 6).
 *
 * Gradiente: verde (0% DSP — hub domina) → amarelo (50%) → vermelho (100% DSP).
 * Ajuda gerentes a identificar de relance onde prospectar novos hubs.
 *
 * Popup on hover: mostra IHS, DSP, total e %DSP do hex clicado.
 *
 * Usa o mesmo heatmapData já carregado no store para obter a geometria
 * dos hexes (a `deliveries_by_hex.json` tem apenas hex_id, não polígono).
 */

import React, { useEffect, useMemo } from 'react';
import { GeoJSON } from 'react-leaflet';
import { useStore } from '../../store';
import type { HexDeliveryBreakdown } from '../../store/types';

/** Gradiente verde → amarelo → vermelho em função de DSP share [0-100]. */
function dspShareColor(pct: number): string {
  const p = Math.max(0, Math.min(100, pct)) / 100;
  // 0 → verde (#2ecc71), 0.5 → amarelo (#f1c40f), 1 → vermelho (#e74c3c)
  if (p < 0.5) {
    // verde → amarelo
    const t = p * 2;
    const r = Math.round(46 + (241 - 46) * t);
    const g = Math.round(204 + (196 - 204) * t);
    const b = Math.round(113 + (15 - 113) * t);
    return `rgb(${r},${g},${b})`;
  } else {
    // amarelo → vermelho
    const t = (p - 0.5) * 2;
    const r = Math.round(241 + (231 - 241) * t);
    const g = Math.round(196 + (76 - 196) * t);
    const b = Math.round(15 + (60 - 15) * t);
    return `rgb(${r},${g},${b})`;
  }
}

const DSPShareLayer: React.FC = () => {
  const showLayer = useStore((s) => s.styleConfig.showDspShareLayer);
  const byHex = useStore((s) => s.deliveries.byHex);
  const isLoadingByHex = useStore((s) => s.deliveries.isLoadingByHex);
  const loadByHex = useStore((s) => s.loadDeliveriesByHex);
  const heatmapData = useStore((s) => s.heatmapData);

  // Lazy-load do byHex quando o layer for ativado pela primeira vez.
  useEffect(() => {
    if (showLayer && !byHex && !isLoadingByHex) {
      loadByHex();
    }
  }, [showLayer, byHex, isLoadingByHex, loadByHex]);

  // Merge: feature do heatmap (com polígono H3) + dados do deliveries_by_hex.
  const mergedFeatures = useMemo<GeoJSON.Feature[]>(() => {
    if (!showLayer || !byHex || !heatmapData?.features) return [];
    const byHexMap = new Map<string, HexDeliveryBreakdown>();
    for (const h of byHex.hexes) byHexMap.set(h.hex_id, h);

    const out: GeoJSON.Feature[] = [];
    for (const f of heatmapData.features) {
      const hexId = f.properties?.hex_id;
      if (!hexId) continue;
      const dr = byHexMap.get(String(hexId));
      if (!dr) continue;
      out.push({
        ...f,
        properties: {
          ...f.properties,
          __dsp_share_pct: dr.dsp_share_pct,
          __ihs: dr.ihs,
          __dsp: dr.dsp,
          __total: dr.total,
        },
      } as GeoJSON.Feature);
    }
    return out;
  }, [showLayer, byHex, heatmapData]);

  if (!showLayer || mergedFeatures.length === 0) return null;

  const fc: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: mergedFeatures,
  };

  return (
    <GeoJSON
      key={`dsp-share-${mergedFeatures.length}`}
      data={fc}
      style={(f) => ({
        color: '#222',
        weight: 0.3,
        fillColor: dspShareColor((f?.properties?.__dsp_share_pct as number) || 0),
        fillOpacity: 0.55,
      })}
      onEachFeature={(feature, layer) => {
        const p = feature.properties || {};
        const html = `
          <div style="font-size:12px">
            <div style="font-weight:600;margin-bottom:4px;">Share DSP no hex</div>
            <div>IHS: <b>${p.__ihs ?? 0}</b></div>
            <div>DSP: <b>${p.__dsp ?? 0}</b></div>
            <div>Total: <b>${p.__total ?? 0}</b></div>
            <div>% DSP: <b>${(p.__dsp_share_pct ?? 0).toFixed(1)}%</b></div>
          </div>`;
        layer.bindPopup(html);
      }}
    />
  );
};

export default DSPShareLayer;
