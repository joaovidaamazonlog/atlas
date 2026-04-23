/**
 * PolygonLayer.tsx
 * ================
 * Modos de colorização (polygonColorField):
 * - 'attainment' : escala por attainment relativo ao range visível por DS
 * - 'territory'  : cor distinta por territory_id
 * - 'ds'         : cor distinta por delivery_station
 * - 'ctl'        : cor distinta por CTL (derivado do territory_id)
 * - 'bdm'        : cor distinta por BDM cluster
 */

import { useMemo } from 'react';
import { GeoJSON } from 'react-leaflet';
import type { StyleFunction, PathOptions } from 'leaflet';
import type { Feature } from 'geojson';
import { useStore } from '../../store';

// Paleta viva para modos de grupo (DS, CTL, BDM, territory)
const GROUP_PALETTE = [
  '#FF3B30','#007AFF','#34C759','#AF52DE','#FF9500',
  '#00C7BE','#FF2D55','#5AC8FA','#FFCC00','#30D158',
  '#BF5AF2','#FF6B35','#0A84FF','#32D74B','#FF375F',
  '#64D2FF','#FFD60A','#FF453A','#30B0C7','#AC8E68',
];

// Cor base por DS para o modo attainment multi-DS
const DS_BASE_COLORS: Record<string, [number, number, number]> = {
  DBR9: [255, 59,  48 ], DSP2: [0,   122, 255], DSP4: [52,  199, 89 ],
  DSP5: [175, 82,  222], DPR2: [255, 149, 0  ], DRJ3: [255, 107, 53 ],
  DRS5: [255, 45,  85 ], DBS5: [0,   199, 190], DBH5: [100, 210, 255],
  DMG2: [191, 90,  242], DCE3: [255, 55,  95 ], DES2: [48,  209, 88 ],
  DGO2: [255, 214, 10 ], DPE4: [255, 159, 10 ], DPB3: [142, 142, 147],
  DSA8: [10,  132, 255], DAM1: [50,  215, 75 ],
};

/** Extrai o CTL de um territory_id (ex: DSP2_bucket-06 → CTL-B, seq 6 → grupo 5) */
function ctlFromTerritoryId(tid: string): string {
  for (const sep of ['_bucket-', '_T']) {
    if (tid.includes(sep)) {
      const seq = parseInt(tid.split(sep)[1], 10);
      if (!isNaN(seq)) return `CTL-${String.fromCharCode(65 + Math.floor((seq - 1) / 5))}`;
    }
  }
  return 'CTL-A';
}

/** Interpola entre duas cores RGB com t ∈ [0,1] */
function lerpColor(from: [number, number, number], to: [number, number, number], t: number): string {
  const r = Math.round(from[0] + (to[0] - from[0]) * t);
  const g = Math.round(from[1] + (to[1] - from[1]) * t);
  const b = Math.round(from[2] + (to[2] - from[2]) * t);
  return `rgb(${r},${g},${b})`;
}

/** Constrói um mapa {chave → cor} a partir de uma lista de chaves únicas */
function buildGroupColorMap(keys: string[]): Record<string, string> {
  const unique = [...new Set(keys)].sort();
  const map: Record<string, string> = {};
  unique.forEach((k, i) => { map[k] = GROUP_PALETTE[i % GROUP_PALETTE.length]; });
  return map;
}

export default function PolygonLayer() {
  const polygonsData = useStore((s) => s.polygonsData);
  const filterState = useStore((s) => s.filterState);
  const showPolygons = useStore((s) => s.styleConfig.showPolygons);
  const polygonColorField = useStore((s) => s.styleConfig.polygonColorField);
  const prospectClusters = useStore((s) => s.prospectState.clusters);
  const selectedBucket = useStore((s) => s.prospectState.selectedBucket);

  const filteredData = useMemo(() => {
    if (!polygonsData) return null;
    const heatmapActive = prospectClusters.length > 0;
    const features = polygonsData.features.filter((f) => {
      const props = f.properties ?? {};
      if (heatmapActive) {
        if (!selectedBucket) return false;
        return props.bucket_ade === selectedBucket || props.territory_id === selectedBucket;
      }
      const stationMatch =
        filterState.selectedStations === 'all' ||
        filterState.selectedStations.includes(props.delivery_station);
      const bucketMatch =
        filterState.selectedBuckets === 'all' ||
        filterState.selectedBuckets.includes(props.bucket_ade ?? props.territory_id);
      return stationMatch && bucketMatch;
    });
    return { type: 'FeatureCollection' as const, features };
  }, [polygonsData, filterState, prospectClusters, selectedBucket]);

  // Pré-computar todos os mapas de cor a partir dos dados filtrados
  const colorMap = useMemo(() => {
    if (!filteredData) return null;
    const features = filteredData.features;

    // Mapas de grupo
    const byTerritory = buildGroupColorMap(
      features.map((f) => (f.properties?.territory_id as string) ?? '')
    );
    const byDS = buildGroupColorMap(
      features.map((f) => (f.properties?.delivery_station as string) ?? '')
    );
    const byCTL = buildGroupColorMap(
      features.map((f) => ctlFromTerritoryId((f.properties?.territory_id as string) ?? ''))
    );
    const byBDM = buildGroupColorMap(
      features.map((f) => (f.properties?.bdm_cluster as string) ?? '')
    );

    // Attainment: min/max por DS entre os territórios visíveis
    const stationAttainments: Record<string, number[]> = {};
    features.forEach((f) => {
      const props = f.properties ?? {};
      const ds = (props.delivery_station as string) ?? 'unknown';
      const att = props.attainment != null ? Number(props.attainment) : null;
      if (att != null) {
        if (!stationAttainments[ds]) stationAttainments[ds] = [];
        stationAttainments[ds].push(att);
      }
    });
    const stationRanges: Record<string, { min: number; max: number }> = {};
    for (const [ds, vals] of Object.entries(stationAttainments)) {
      stationRanges[ds] = { min: Math.min(...vals), max: Math.max(...vals) };
    }
    const multipleStations = Object.keys(stationRanges).length > 1;

    return { byTerritory, byDS, byCTL, byBDM, stationRanges, multipleStations };
  }, [filteredData]);

  const heatmapActive = prospectClusters.length > 0;
  if (!showPolygons && !heatmapActive) return null;
  if (!filteredData || !colorMap) return null;

  const styleFunc: StyleFunction = (feature?: Feature): PathOptions => {
    const props = feature?.properties ?? {};
    const tid = (props.territory_id as string) ?? '';
    const ds  = (props.delivery_station as string) ?? '';
    let color = '#3388ff';

    switch (polygonColorField) {
      case 'territory':
        color = colorMap.byTerritory[tid] ?? '#3388ff';
        break;
      case 'ds':
        color = colorMap.byDS[ds] ?? '#3388ff';
        break;
      case 'ctl':
        color = colorMap.byCTL[ctlFromTerritoryId(tid)] ?? '#3388ff';
        break;
      case 'bdm':
        color = colorMap.byBDM[(props.bdm_cluster as string) ?? ''] ?? '#3388ff';
        break;
      case 'attainment': {
        const att = props.attainment != null ? Number(props.attainment) : null;
        const range = colorMap.stationRanges[ds];
        if (att == null || !range) {
          color = '#94a3b8';
        } else {
          const t = range.max > range.min ? (att - range.min) / (range.max - range.min) : 0.5;
          if (colorMap.multipleStations) {
            const base = DS_BASE_COLORS[ds] ?? [0, 122, 255];
            const light: [number, number, number] = [
              Math.round(base[0] + (255 - base[0]) * 0.65),
              Math.round(base[1] + (255 - base[1]) * 0.65),
              Math.round(base[2] + (255 - base[2]) * 0.65),
            ];
            color = lerpColor(light, base, t);
          } else {
            color = lerpColor([86, 204, 242], [10, 47, 255], t);
          }
        }
        break;
      }
    }

    return { color, weight: 2, opacity: 0.85, fillColor: color, fillOpacity: 0.3, pane: 'polygonsPane' };
  };

  return (
    <GeoJSON
      key={JSON.stringify(filterState) + selectedBucket + prospectClusters.length + polygonColorField + String(showPolygons)}
      data={filteredData}
      style={styleFunc}
      pane="polygonsPane"
      onEachFeature={(feature, layer) => {
        const p = feature.properties ?? {};
        const ctl = ctlFromTerritoryId((p.territory_id as string) ?? '');
        layer.bindPopup(`
          <div style="min-width:200px;font-size:12px;">
            <b style="display:block;margin-bottom:4px">${p.territory_id ?? ''}</b>
            <p style="margin:2px 0"><b>DS:</b> ${p.delivery_station ?? 'N/A'}</p>
            <p style="margin:2px 0"><b>BDM:</b> ${p.bdm_cluster ?? 'N/A'}</p>
            <p style="margin:2px 0"><b>CTL:</b> ${ctl}</p>
            <p style="margin:2px 0"><b>Parceiros Esperados:</b> ${p.n_slots ?? 'N/A'}</p>
            <p style="margin:2px 0"><b>Attainment:</b> ${p.attainment != null ? Number(p.attainment).toFixed(1) + '%' : 'N/A'}</p>
            <p style="margin:2px 0"><b>Acuracidade:</b> ${p.accuracy != null ? Number(p.accuracy).toFixed(1) + '%' : 'N/A'}</p>
          </div>
        `);
      }}
    />
  );
}
