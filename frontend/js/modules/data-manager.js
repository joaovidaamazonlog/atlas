/**
 * data-manager.js
 * ===============
 * Responsável por carregar, parsear e agregar todos os dados da aplicação.
 *
 * Responsabilidades
 * -----------------
 * - Fetch paralelo dos arquivos de dados estáticos
 * - Construção dos objetos Partner a partir dos dados brutos (campos de
 *   otimização já embutidos pelo backend no dados_mapa.json)
 * - Associação de parceiros a polígonos (regiao)
 * - Injeção de slots ideais como marcadores "New"
 * - Comunicação com o Web Worker para filtragem off-thread
 */

import { state, subscribe }    from '../state.js';
import { Partner } from '../models.js';
import { DATA_URLS }           from '../config.js';

// ---------------------------------------------------------------------------
// WEB WORKER
// ---------------------------------------------------------------------------

const dataWorker = new Worker('./data-worker.js');

dataWorker.onmessage = (e) => {
    if (e.data.action === 'filterResult') {
        state.currentFilteredData = e.data.filtered;
    }
};

// ---------------------------------------------------------------------------
// CARREGAMENTO PRINCIPAL
// ---------------------------------------------------------------------------

/**
 * Carrega todos os arquivos de dados em paralelo e inicializa o estado.
 * @returns {Promise<void>}
 */
export async function loadAll() {
    try {
        const [partnerData, polygonData, jurisdictionData, optData, heatmapData] =
            await Promise.all([
                fetch(DATA_URLS.partners).then(r => r.json()),
                fetch(DATA_URLS.territories).then(r => r.json()),
                fetch(DATA_URLS.jurisdiction).then(r => r.json()),
                fetch(DATA_URLS.optimization).then(r => r.json()),
                fetch(DATA_URLS.heatmap).then(r => r.json()).catch(() => null),
            ]);

        // Construir objetos Partner — campos de otimização já vêm embutidos
        state.allMarkersData = partnerData.allMarkerData
            .filter(p => p.lat !== null || p.lon !== null)
            .map(p => new Partner(p));

        state.period           = partnerData.period;
        state.deliveryStations = partnerData.deliveryStations;
        state.polygonsData     = polygonData;
        state.jurisdictionData = jurisdictionData;
        state.optimizationData = optData;
        // optimization_data.geojson agora contém apenas TERRITORY_HEX e IDEAL_SLOT
        state.idealSupplyData  = optData.features.filter(f => f.properties.type === 'IDEAL_SLOT');
        state.heatmapData      = heatmapData;

        _associatePartnersToPolygons();
        _injectOpportunitySlots();

        applyFilters();

        console.log(`[DataManager] ${state.allMarkersData.length} parceiros carregados.`);

    } catch (err) {
        alert('Não foi possível carregar os arquivos de dados: ' + err.message);
        console.error('[DataManager] Erro no carregamento:', err);
    }
}

// ---------------------------------------------------------------------------
// FILTROS
// ---------------------------------------------------------------------------

export function applyFilters() {
    const get = id => document.getElementById(id);

    const filters = {
        allMarkersData:    state.allMarkersData,
        selectedStatuses:  _getMultiSelect('statusFilter'),
        selectedStations:  _getMultiSelect('stationFilter'),
        selectedBuckets:   _getMultiSelect('bucket_ade'),
        initiativesFilter: get('initiativesFilter')?.value ?? 'all',
        jurisdictionFilter: get('jurisdictionFilter')?.value ?? 'all',
    };

    if (filters.selectedStatuses.includes('all')) filters.selectedStatuses = 'all';
    if (filters.selectedStations.includes('all')) filters.selectedStations = 'all';
    if (filters.selectedBuckets.includes('all'))  filters.selectedBuckets  = 'all';

    dataWorker.postMessage({ action: 'filter', filters });
}

export function resetFilters() {
    const set = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
    };

    set('statusFilter', 'all');
    set('initiativesFilter', 'all');
    set('jurisdictionFilter', 'all');
    set('bucket_ade', 'all');

    const stationFilter = document.getElementById('stationFilter');
    if (stationFilter) {
        Array.from(stationFilter.options).forEach(opt => {
            opt.selected = opt.value === 'all';
        });
    }

    applyFilters();
}

// ---------------------------------------------------------------------------
// PIPELINE INTERNO
// ---------------------------------------------------------------------------

function _associatePartnersToPolygons() {
    if (!state.polygonsData || !state.allMarkersData.length) return;

    let count = 0;
    state.allMarkersData.forEach(partner => {
        if (!partner.hasCoords) return;
        const pt = turf.point([partner.lon, partner.lat]);
        for (const feature of state.polygonsData.features) {
            if (turf.booleanPointInPolygon(pt, feature)) {
                partner.regiao = feature.properties.cluster;
                count++;
                break;
            }
        }
        if (!partner.regiao) partner.regiao = 'Fora das Regiões';
    });

    console.log(`[DataManager] ${count} parceiros associados a polígonos.`);
}

function _injectOpportunitySlots() {
    if (!state.idealSupplyData?.length) return;

    const slots = state.idealSupplyData.map(f => Partner.fromSlot(f));
    state.allMarkersData = [...state.allMarkersData, ...slots];

    console.log(`[DataManager] ${slots.length} slots de oportunidade injetados.`);
}

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function _getMultiSelect(id) {
    const el = document.getElementById(id);
    if (!el) return ['all'];
    return Array.from(el.selectedOptions).map(o => o.value);
}
