/**
 * state.js
 * ========
 * Estado global reativo da aplicação via Proxy.
 *
 * Qualquer módulo pode subscrever mudanças de estado sem acoplamento
 * direto entre módulos — elimina o problema atual onde DataManager
 * chama MapManager, PolygonManager e UIManager diretamente.
 *
 * Uso
 * ---
 *   import { state, subscribe } from '../state.js';
 *
 *   // Reagir a mudanças
 *   subscribe('currentFilteredData', (data) => MapManager.createMarkers(data));
 *
 *   // Mudar estado (dispara subscribers automaticamente)
 *   state.currentFilteredData = filtered;
 */

import { Partner, DeliveryStation, FilterState } from './models.js';

// ---------------------------------------------------------------------------
// ESTADO BRUTO
// ---------------------------------------------------------------------------

/** @type {Object} */
const _raw = {
    // Mapa Leaflet (inicializado em map-manager.js)
    /** @type {L.Map|null} */
    map: null,

    // Dados carregados
    /** @type {Partner[]} */
    allMarkersData: [],

    /** @type {Partner[]} */
    currentFilteredData: [],

    /** @type {DeliveryStation[]} */
    deliveryStations: [],

    /** @type {Object|null} GeoJSON de territórios */
    polygonsData: null,

    /** @type {Object|null} GeoJSON de jurisdição */
    jurisdictionData: null,

    /** @type {Object|null} GeoJSON de otimização */
    optimizationData: null,

    /** @type {Object[]|null} Features IDEAL_SLOT */
    idealSupplyData: null,

    /** @type {Object|null} GeoJSON de heatmap */
    heatmapData: null,

    /** @type {string|Object} Período dos dados */
    period: '',

    // Camadas do mapa
    /** @type {L.Layer|null} */
    polygonLayer: null,

    /** @type {L.Layer|null} */
    jurisdictionLayer: null,

    /** @type {L.Layer|null} */
    optimizationLayer: null,

    /** @type {L.Control|null} */
    legendControl: null,

    /** @type {L.Routing.Control|null} */
    routingControl: null,

    // Marcadores
    /** @type {L.CircleMarker[]} */
    markerObjects: [],

    /** @type {L.Circle[]} */
    circleObjects: [],

    /** @type {L.Marker[]} */
    highlightedMarkers: [],

    // HCP
    /** @type {Object} cache por station_code */
    hcpSuggestionCache: {},

    /** @type {Object} Set de store_ids usados por station */
    hcpUsedStores: {},

    /** @type {boolean} */
    hcpSuggestionsActive: false,

    // Slot popup data (CEPs armazenados para evitar serialização no onclick)
    /** @type {Object.<string, string[]>} */
    _slotPopupData: {},
};

// ---------------------------------------------------------------------------
// SISTEMA DE SUBSCRIBERS
// ---------------------------------------------------------------------------

/** @type {Object.<string, Function[]>} */
const _subscribers = {};

// ---------------------------------------------------------------------------
// PROXY REATIVO
// ---------------------------------------------------------------------------

/**
 * Estado global reativo.
 * Atribuir qualquer propriedade dispara os subscribers registrados.
 * @type {typeof _raw}
 */
export const state = new Proxy(_raw, {
    set(target, key, value) {
        target[key] = value;
        const fns = _subscribers[key];
        if (fns) fns.forEach(fn => fn(value));
        return true;
    },
    get(target, key) {
        return target[key];
    },
});

// ---------------------------------------------------------------------------
// API PÚBLICA
// ---------------------------------------------------------------------------

/**
 * Registra um callback para ser chamado quando a propriedade mudar.
 *
 * @param {string}   key - Nome da propriedade do estado
 * @param {Function} fn  - Callback recebe o novo valor como argumento
 */
export function subscribe(key, fn) {
    if (!_subscribers[key]) _subscribers[key] = [];
    _subscribers[key].push(fn);
}

/**
 * Remove um callback previamente registrado.
 *
 * @param {string}   key
 * @param {Function} fn
 */
export function unsubscribe(key, fn) {
    if (!_subscribers[key]) return;
    _subscribers[key] = _subscribers[key].filter(f => f !== fn);
}

/**
 * Reseta o estado para os valores iniciais.
 * Útil para testes ou reinicialização da aplicação.
 */
export function resetState() {
    Object.keys(_raw).forEach(key => {
        const initial = _raw[key];
        if (Array.isArray(initial)) {
            state[key] = [];
        } else if (initial !== null && typeof initial === 'object') {
            state[key] = {};
        } else {
            state[key] = initial;
        }
    });
}
