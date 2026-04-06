/**
 * polygon-manager.js
 * ==================
 * Gerencia todas as camadas de polígonos no mapa:
 * territórios, jurisdições e heatmap de demanda.
 *
 * Responsabilidades
 * -----------------
 * - Renderização e filtragem de polígonos de território
 * - Renderização e filtragem de jurisdições
 * - Renderização do heatmap de demanda (hexágonos H3)
 * - Seleção interativa de hexágonos com tooltip de demanda
 * - Cálculo de prioridade de território
 */

import { state } from '../state.js';

// ---------------------------------------------------------------------------
// TERRITÓRIOS
// ---------------------------------------------------------------------------

/**
 * Atualiza a camada de polígonos de território com base nos filtros ativos.
 */
export function updateFilteredPolygons() {
    if (state.polygonLayer) {
        state.map.removeLayer(state.polygonLayer);
        state.polygonLayer = null;
    }
    if (!state.polygonsData) return;

    const selectedStations = _getMultiSelect('stationFilter');
    const selectedBuckets  = _getMultiSelect('bucket_ade');

    const features = state.polygonsData.features.filter(f => {
        const stationMatch = selectedStations.includes('all') ||
            selectedStations.includes(f.properties.delivery_station);
        const bucketMatch  = selectedBuckets.includes('all')  ||
            selectedBuckets.includes(f.properties.territory_id);
        return stationMatch && bucketMatch;
    });

    state.polygonLayer = L.geoJSON(
        { type: 'FeatureCollection', features },
        {
            pane:  'polygonsPane',
            style: f => ({ color: f.properties.cor || '#3388ff', weight: 2, opacity: 0.8, fillOpacity: 0.2 }),
        }
    );

    _updatePolygonPopups();

    if (document.getElementById('showPolygons')?.checked) {
        state.polygonLayer.addTo(state.map);
    }
}

export function togglePolygons() {
    updateFilteredPolygons();
}

// ---------------------------------------------------------------------------
// JURISDIÇÕES
// ---------------------------------------------------------------------------

/**
 * Atualiza a camada de jurisdições com base nos filtros ativos.
 */
export function updateFilteredJurisdiction() {
    if (state.jurisdictionLayer) {
        state.map.removeLayer(state.jurisdictionLayer);
        state.jurisdictionLayer = null;
    }
    if (!state.jurisdictionData) return;

    const selectedStations = _getMultiSelect('stationFilter');
    const features = selectedStations.includes('all')
        ? state.jurisdictionData.features
        : state.jurisdictionData.features.filter(f =>
            selectedStations.includes(f.properties.delivery_station)
          );

    state.jurisdictionLayer = L.geoJSON(
        { type: 'FeatureCollection', features },
        {
            pane:  'polygonsPane',
            style: f => ({ color: f.properties.cor || '#6E00B3', weight: 2, opacity: 0.8, fillOpacity: 0.2 }),
            onEachFeature: (feat, layer) => layer.bindPopup(feat.properties.delivery_station),
        }
    );

    if (document.getElementById('showJurisdictions')?.checked) {
        state.jurisdictionLayer.addTo(state.map);
    }
}

export function toggleJurisdictions() {
    updateFilteredJurisdiction();
}

// ---------------------------------------------------------------------------
// HEATMAP (camada de otimização)
// ---------------------------------------------------------------------------

/**
 * Renderiza o heatmap de demanda diária por hexágono H3.
 */
export function renderOptimizationLayer() {
    if (state.optimizationLayer) {
        state.map.removeLayer(state.optimizationLayer);
        state.optimizationLayer = null;
    }
    if (!state.heatmapData) {
        console.error('[PolygonManager] heatmapData não encontrado.');
        return;
    }

    const selectedStations = _getMultiSelect('stationFilter');
    const selectedBuckets  = _getMultiSelect('bucket_ade');

    const features = state.heatmapData.features.filter(f => {
        const stationMatch = selectedStations.includes('all') ||
            selectedStations.includes(f.properties.delivery_station);
        const bucketMatch  = selectedBuckets.includes('all')  ||
            selectedBuckets.includes(f.properties.territory_id);
        return stationMatch && bucketMatch;
    });

    const maxDemanda = Math.max(...features.map(f => f.properties.demand_daily || 0));

    state.optimizationLayer = L.geoJSON(
        { type: 'FeatureCollection', features },
        {
            pane:  'polygonsPane',
            style: f => ({
                color:       _demandColor(f.properties.demand_daily || 0, maxDemanda),
                weight:      1,
                fillOpacity: 0.3,
            }),
        }
    );

    if (document.getElementById('showOptimizationLayer')?.checked) {
        state.optimizationLayer.addTo(state.map);
    }
}

export function toggleOptimizationLayer() {
    renderOptimizationLayer();
    if (state.optimizationLayer) {
        optimizationSelection.enableSelection();
    } else {
        optimizationSelection.disableSelection();
    }
}

// ---------------------------------------------------------------------------
// SELEÇÃO INTERATIVA DE HEXÁGONOS
// ---------------------------------------------------------------------------

/**
 * Sub-módulo para seleção interativa de hexágonos no heatmap.
 * Permite selecionar múltiplos hexágonos e ver a soma de demanda.
 */
export const optimizationSelection = {
    /** @type {Set<number>} */
    selectedPolygons: new Set(),

    /** @type {HTMLElement|null} */
    tooltipDiv: null,

    /** @type {Function|null} */
    _mousemoveHandler: null,

    /** @type {Map<L.Layer, Object>} */
    _layerClickHandlers: new Map(),

    enableSelection() {
        if (!state.optimizationLayer) return;
        this.selectedPolygons.clear();
        this._removeTooltip();
        this._createTooltip();
        this._removeLayerEvents();

        state.optimizationLayer.eachLayer(layer => {
            const clickHandler = (e) => {
                const id = L.stamp(layer);
                if (this.selectedPolygons.has(id)) {
                    this.selectedPolygons.delete(id);
                    layer.setStyle({ weight: 1, fillOpacity: 0.3 });
                } else {
                    this.selectedPolygons.add(id);
                    layer.setStyle({ weight: 3, fillOpacity: 0.6 });
                }
                this._updateTooltipContent(e.originalEvent || window._lastMouseEvent);
            };
            const mousemoveHandler = (e) => {
                window._lastMouseEvent = e.originalEvent;
                this._updateTooltipContent(e.originalEvent);
            };
            layer.off('click').on('click', clickHandler);
            layer.off('mousemove').on('mousemove', mousemoveHandler);
            this._layerClickHandlers.set(layer, { clickHandler, mousemoveHandler });
        });

        if (this._mousemoveHandler) document.removeEventListener('mousemove', this._mousemoveHandler);
        this._mousemoveHandler = (e) => {
            window._lastMouseEvent = e;
            if (this.selectedPolygons.size > 0) {
                this._updateTooltipContent(e);
            } else {
                this._removeTooltip();
                this._resetStyles();
            }
        };
        document.addEventListener('mousemove', this._mousemoveHandler);
    },

    disableSelection() {
        this.selectedPolygons.clear();
        this._removeTooltip();
        this._removeLayerEvents();
        if (this._mousemoveHandler) {
            document.removeEventListener('mousemove', this._mousemoveHandler);
            this._mousemoveHandler = null;
        }
        this._resetStyles();
    },

    clearSelection(e) {
        if (e) e.stopPropagation();
        this.selectedPolygons.clear();
        this._removeTooltip();
        this._resetStyles();
    },

    _createTooltip() {
        this.tooltipDiv = document.createElement('div');
        Object.assign(this.tooltipDiv.style, {
            position: 'fixed', background: '#fff', border: '1px solid #333',
            padding: '6px 12px', borderRadius: '6px', boxShadow: '0 2px 8px #0002',
            pointerEvents: 'none', zIndex: 99999, display: 'none',
        });
        this.tooltipDiv.setAttribute('role', 'tooltip');
        this.tooltipDiv.setAttribute('aria-live', 'polite');
        document.body.appendChild(this.tooltipDiv);
    },

    _updateTooltipContent(mouseEvent) {
        if (!this.tooltipDiv) this._createTooltip();
        if (this.selectedPolygons.size === 0) {
            this.tooltipDiv.style.display = 'none';
            return;
        }
        if (!mouseEvent && window._lastMouseEvent) mouseEvent = window._lastMouseEvent;

        let soma = 0, count = 0;
        state.optimizationLayer?.eachLayer(layer => {
            if (this.selectedPolygons.has(L.stamp(layer))) {
                soma += Math.round(Number(layer.feature?.properties?.demand_daily) || 0);
                count++;
            }
        });

        this.tooltipDiv.innerHTML = `
            <button style="position:absolute;top:2px;right:6px;background:none;border:none;font-size:1.2em;cursor:pointer;"
                onclick="PolygonManager.optimizationSelection.clearSelection(event)">&times;</button>
            <b>Selecionados:</b> ${count}<br>
            <b>Soma demanda diária:</b> ${soma}
        `;
        this.tooltipDiv.style.display = 'block';
        if (mouseEvent) {
            this.tooltipDiv.style.left = `${mouseEvent.clientX + 16}px`;
            this.tooltipDiv.style.top  = `${mouseEvent.clientY + 16}px`;
        }
    },

    _removeTooltip() {
        if (this.tooltipDiv) { this.tooltipDiv.remove(); this.tooltipDiv = null; }
    },

    _removeLayerEvents() {
        if (!state.optimizationLayer) return;
        state.optimizationLayer.eachLayer(layer => {
            const h = this._layerClickHandlers.get(layer);
            if (h) { layer.off('click', h.clickHandler); layer.off('mousemove', h.mousemoveHandler); }
        });
        this._layerClickHandlers.clear();
    },

    _resetStyles() {
        state.optimizationLayer?.eachLayer(layer => layer.setStyle({ weight: 1, fillOpacity: 0.3 }));
    },
};

// ---------------------------------------------------------------------------
// PRIORIDADE DE TERRITÓRIO
// ---------------------------------------------------------------------------

/**
 * Calcula a prioridade de um território dentro da sua delivery station.
 * Menor attainment = maior prioridade (número menor).
 *
 * @param {string} regionName
 * @param {string} deliveryStation
 * @returns {number}
 */
export function calculatePriority(regionName, deliveryStation) {
    const polygons = state.polygonsData?.features.filter(
        f => f.properties.delivery_station === deliveryStation
    ) ?? [];

    const sorted = polygons.map(f => {
        const region   = f.properties.territory_id;
        const expected = f.properties.n_slots || 0;
        const active   = state.allMarkersData.filter(p => p.territory_id === region && p.status === 'Active').length;
        const onboard  = state.allMarkersData.filter(p => p.territory_id === region &&
            (p.status === 'Onboarding' || p.status === 'BG Checks')).length;
        const attainment = expected > 0 ? (active + onboard) / expected : 0;
        return { cluster: region, attainment, n_slots: expected };
    }).sort((a, b) => a.attainment - b.attainment || b.n_slots - a.n_slots);

    const idx = sorted.findIndex(f => f.cluster === regionName);
    return idx >= 0 ? idx + 1 : polygons.length;
}

// ---------------------------------------------------------------------------
// HELPERS INTERNOS
// ---------------------------------------------------------------------------

/**
 * Atualiza os popups dos polígonos de território com métricas atuais.
 */
function _updatePolygonPopups() {
    if (!state.polygonLayer || !state.allMarkersData) return;

    state.polygonLayer.eachLayer(layer => {
        const props    = layer.feature.properties;
        const regionId = props.territory_id;
        const partners = state.allMarkersData.filter(p => p.bucket_ade === regionId);
        const active   = partners.filter(p => p.status === 'Active').length;
        const onboard  = partners.filter(p => p.status === 'Onboarding' || p.status === 'BG Checks').length;
        const expected = props.n_slots   || 0;
        const attainment = props.attainment || 0;
        const accuracy   = props.accuracy   || 0;
        const priority   = calculatePriority(regionId, props.delivery_station);

        layer.bindPopup(`
            <div style="min-width:200px;">
                <h6><b>${regionId}</b></h6>
                <p><b>Parceiros Esperados:</b> ${expected}</p>
                <p><b>Parceiros Ativos:</b> ${active}</p>
                <p><b>Parceiros em Onboarding:</b> ${onboard}</p>
                <p><b>Attainment:</b> ${attainment.toFixed(1)}%</p>
                <p><b>Acuracidade:</b> ${accuracy.toFixed(1)}%</p>
                <p><b>Prioridade:</b> ${priority}</p>
            </div>
        `);
    });
}

/**
 * Converte demanda em cor RGB (vermelho → verde).
 * @param {number} demanda
 * @param {number} maxDemanda
 * @returns {string}
 */
function _demandColor(demanda, maxDemanda) {
    if (maxDemanda === 0) return '#e74c3c';
    const t = Math.max(0, Math.min(1, demanda / maxDemanda));
    const r = Math.round(231 + (46  - 231) * t);
    const g = Math.round(76  + (204 - 76)  * t);
    const b = Math.round(60  + (113 - 60)  * t);
    return `rgb(${r},${g},${b})`;
}

/**
 * @param {string} id
 * @returns {string[]}
 */
function _getMultiSelect(id) {
    const el = document.getElementById(id);
    if (!el) return ['all'];
    return Array.from(el.selectedOptions).map(o => o.value);
}
