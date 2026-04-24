/**
 * RecruitableAreaLayer.tsx
 * ========================
 * - Círculo de raio: pane recruitableCirclePane (abaixo dos hexágonos)
 * - Hexágonos: pane recruitablePane (acima do círculo)
 * - Coloração dos hexágonos por demanda residual: vermelho → amarelo → verde
 */

import { Circle, GeoJSON } from 'react-leaflet';
import type { PathOptions } from 'leaflet';
import type { Feature } from 'geojson';
import { useStore } from '../../store';
import type { EvaluatorResult } from '../../store/types';

// ---------------------------------------------------------------------------
// HELPERS DE COR
// ---------------------------------------------------------------------------

/**
 * Interpola entre vermelho (#ef4444) → amarelo (#eab308) → verde (#22c55e)
 * com base em t ∈ [0, 1].
 */
function demandColor(t: number): string {
  // 0→0.5: vermelho→amarelo, 0.5→1: amarelo→verde
  const clamp = Math.max(0, Math.min(1, t));
  let r: number, g: number, b: number;
  if (clamp < 0.5) {
    const s = clamp / 0.5;
    r = Math.round(239 + (234 - 239) * s); // 239→234
    g = Math.round(68  + (179 - 68)  * s); // 68→179
    b = Math.round(68  + (8   - 68)  * s); // 68→8
  } else {
    const s = (clamp - 0.5) / 0.5;
    r = Math.round(234 + (34  - 234) * s); // 234→34
    g = Math.round(179 + (197 - 179) * s); // 179→197
    b = Math.round(8   + (94  - 8)   * s); // 8→94
  }
  return `rgb(${r},${g},${b})`;
}

function cellStyle(feature: Feature, result: EvaluatorResult): PathOptions {
  const props = feature.properties ?? {};
  const demandResidual: number = typeof props.demand_residual === 'number'
    ? props.demand_residual
    : (typeof props.demand_daily === 'number' ? props.demand_daily : 0);

  // Normaliza em relação ao minAdv: 0 = sem demanda, 1 = atinge o mínimo
  const t = result.minAdv > 0 ? Math.min(demandResidual / result.minAdv, 1) : 0;
  const color = demandColor(t);

  return {
    color,
    fillColor: color,
    fillOpacity: 0.5,
    weight: 1.5,
    opacity: 0.9,
    pane: 'recruitablePane',
  };
}

/** Estilo do círculo de raio */
const CIRCLE_STYLE: PathOptions = {
  color: '#6366f1',
  fillColor: '#818cf8',
  fillOpacity: 0.06,
  weight: 2,
  opacity: 0.8,
  pane: 'recruitableCirclePane',
};

// ---------------------------------------------------------------------------
// COMPONENTE
// ---------------------------------------------------------------------------

export default function RecruitableAreaLayer() {
  const { params, result } = useStore((s) => s.recruitableAnalysis);
  const whatIfPartnerId = useStore((s) => s.whatIfPartnerId);
  const { centerLat, centerLon, radiusMeters } = params;

  const hasCenter = centerLat !== '' && centerLon !== '';
  const centerLatNum = hasCenter ? parseFloat(centerLat) : null;
  const centerLonNum = hasCenter ? parseFloat(centerLon) : null;
  const validCenter =
    centerLatNum !== null &&
    centerLonNum !== null &&
    !isNaN(centerLatNum) &&
    !isNaN(centerLonNum);

  if (result === null && !validCenter) return null;

  const cellsData: GeoJSON.FeatureCollection | null = result
    ? { type: 'FeatureCollection', features: result.selectedCells }
    : null;

  // Key baseado no primeiro e último hex_id + contagem + base para garantir re-render
  // quando os hexes mudam (evita cache stale do Leaflet GeoJSON)
  const firstHex = result?.selectedCells[0]?.properties?.hex_id ?? '';
  const lastHex = result?.selectedCells[result.selectedCells.length - 1]?.properties?.hex_id ?? '';
  const geoJsonKey = result
    ? `cells-${result.selectedCells.length}-${result.outOfJurisdictionStation ?? 'in'}-${firstHex}-${lastHex}`
    : 'no-result';

  // When a what-if simulation is active, hide the recruitable circle —
  // PartnerWhatIfLayer renders the green/amber circles instead
  const showCircle = validCenter && !whatIfPartnerId;

  return (
    <>
      {/* Círculo de raio — pane abaixo dos hexágonos, oculto durante what-if */}
      {showCircle && (
        <Circle
          center={[centerLatNum!, centerLonNum!]}
          radius={radiusMeters}
          pathOptions={CIRCLE_STYLE}
          pane="recruitableCirclePane"
        />
      )}

      {/* Hexágonos — coloridos por demanda residual */}
      {result && cellsData && (
        <GeoJSON
          key={geoJsonKey}
          data={cellsData}
          style={(feature?: Feature): PathOptions => {
            if (!feature) return { pane: 'recruitablePane' };
            return cellStyle(feature, result);
          }}
          pane="recruitablePane"
        />
      )}
    </>
  );
}
