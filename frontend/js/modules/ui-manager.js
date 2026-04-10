/**
 * ui-manager.js
 * =============
 * Gerencia toda a interface do usuario:
 * buscas, filtros, autocomplete, popups de marcadores e painel de estatisticas.
 */

import { state }         from '../state.js';
import { PartnerStatus } from '../models.js';
import { COST_PER_SUPPLY_RUN, PERFORMANCE_GOALS } from '../config.js';
import { applyFilters }  from './data-manager.js';

// ---------------------------------------------------------------------------
// PERIODO
// ---------------------------------------------------------------------------

export function updatePeriodInfo(period) {
    const el = document.getElementById('periodInfo');
    if (el) el.textContent = period
        ? `Ultima Atualizacao: ${period}`
        : 'Periodo dos dados nao especificado.';
}

// ---------------------------------------------------------------------------
// FILTROS
// ---------------------------------------------------------------------------

export function populateFilters() {
    const stations = [...new Set(state.allMarkersData.map(m => m.delivery_station).filter(Boolean))].sort();
    const stationFilter     = document.getElementById('stationFilter');
    const initiativesFilter = document.getElementById('initiativesFilter');
    const statusFilter      = document.getElementById('statusFilter');
    const bucketsFilter     = document.getElementById('bucket_ade');

    if (stationFilter) {
        stationFilter.innerHTML = '<option value="all" selected>Todos</option>';
        stations.forEach(s => stationFilter.innerHTML += `<option value="${s}">${s}</option>`);
    }
    if (bucketsFilter) bucketsFilter.innerHTML = '<option value="all" selected>Todos</option>';

    const initiativesSet = new Set();
    let hasNull = false;
    state.allMarkersData.forEach(m => {
        const i = m.hub_delivey_initiatives;
        if (!i || i === 'N/A') hasNull = true;
        else initiativesSet.add(i);
    });
    if (initiativesFilter) {
        initiativesFilter.innerHTML = '<option value="all" selected>Todos</option>';
        [...initiativesSet].sort().forEach(i =>
            initiativesFilter.innerHTML += `<option value="${i}">${i}</option>`
        );
        if (hasNull) initiativesFilter.innerHTML += '<option value="null">Nao alocado</option>';
    }

    function updateBuckets() {
        const selStations = Array.from(stationFilter?.selectedOptions ?? []).map(o => o.value);
        const selStatus   = Array.from(statusFilter?.selectedOptions  ?? []).map(o => o.value);
        let data = state.allMarkersData;
        if (!selStations.includes('all')) data = data.filter(m => selStations.includes(m.delivery_station));
        if (!selStatus.includes('all'))   data = data.filter(m => selStatus.includes(m.status));
        const buckets = [...new Set(data.map(m => m.bucket_ade).filter(Boolean))].sort();
        if (bucketsFilter) {
            bucketsFilter.innerHTML = '<option value="all" selected>Todos</option>';
            buckets.forEach(b => bucketsFilter.innerHTML += `<option value="${b}">${b}</option>`);
        }
    }
    stationFilter?.addEventListener('change', updateBuckets);
    statusFilter?.addEventListener('change', updateBuckets);
    updateBuckets();
}

// ---------------------------------------------------------------------------
// AUTOCOMPLETE
// ---------------------------------------------------------------------------

export function setupAutocomplete() {
    const searchInput      = document.getElementById('search-input');
    const fromInput        = document.getElementById('routeFromInput');
    const toInput          = document.getElementById('routeToInput');
    const resultsContainer = document.getElementById('autocomplete-results');

    function _showResults(inputEl, items) {
        resultsContainer.innerHTML = '';
        const rect = inputEl.getBoundingClientRect();
        resultsContainer.style.top   = `${rect.bottom + window.scrollY}px`;
        resultsContainer.style.left  = `${rect.left   + window.scrollX}px`;
        resultsContainer.style.width = `${rect.width}px`;
        items.forEach(({ html, onClick }) => {
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action py-1';
            item.innerHTML = html;
            item.onclick = e => { e.preventDefault(); onClick(); resultsContainer.style.display = 'none'; };
            resultsContainer.appendChild(item);
        });
        resultsContainer.style.display = items.length ? 'block' : 'none';
    }

    function createAutocomplete(inputEl, onSelect, { allowAddressSearch = false } = {}) {
        inputEl.addEventListener('input', () => {
            const query = inputEl.value.trim();
            if (query.length < 2) { resultsContainer.style.display = 'none'; return; }
            const q = query.toLowerCase();
            const options = [
                ...state.allMarkersData.map(p => ({
                    type: 'partner', name: p.name, salesforce_id: p.salesforce_id, lat: p.lat, lon: p.lon,
                })),
                ...state.deliveryStations.map(ds => ({
                    type: 'station', name: ds.nome, store_id: ds.nome, lat: ds.lat, lon: ds.lon,
                })),
            ];
            const filtered = options.filter(o =>
                (o.name && o.name.toLowerCase().includes(q)) ||
                (o.salesforce_id && o.salesforce_id.toLowerCase().includes(q))
            ).slice(0, 5);

            const items = filtered.map(opt => ({
                html: opt.type === 'station'
                    ? `<i class="fas fa-home mr-1"></i> ${opt.name} (Delivery Station)`
                    : `${opt.name} (${opt.salesforce_id})`,
                onClick: () => onSelect(opt),
            }));

            // Quando não há match de parceiro e o input é o de busca geral,
            // oferece a opção de geocodificar o texto como endereço
            if (allowAddressSearch && filtered.length === 0) {
                items.push({
                    html: `<i class="fas fa-map-marker-alt mr-1"></i> Buscar endereço: <em>${query}</em>`,
                    onClick: () => { inputEl.value = query; searchLocation(query); },
                });
            }

            _showResults(inputEl, items);
        });

        // Enter no campo de busca geral aciona searchLocation diretamente
        if (allowAddressSearch) {
            inputEl.addEventListener('keydown', e => {
                if (e.key === 'Enter') {
                    resultsContainer.style.display = 'none';
                    searchLocation(inputEl.value.trim());
                }
            });
        }
    }

    createAutocomplete(searchInput, p => {
        searchInput.value = p.name;
        searchLocation(p.salesforce_id);
    }, { allowAddressSearch: true });

    createAutocomplete(fromInput, p => {
        fromInput.value = p.name;
        document.getElementById('routeFromId').value = p.salesforce_id;
    });
    createAutocomplete(toInput, p => {
        toInput.value = p.name;
        document.getElementById('routeToId').value = p.salesforce_id;
    });

    document.addEventListener('click', e => {
        if (!resultsContainer.contains(e.target) &&
            e.target !== fromInput && e.target !== toInput && e.target !== searchInput) {
            resultsContainer.style.display = 'none';
        }
    });
}

// ---------------------------------------------------------------------------
// BUSCA GERAL: PARCEIROS E ENDERECOS
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} GeocodeResult
 * @property {string} address - Endereço original passado como input
 * @property {number|null} lat - Latitude, ou null em caso de erro
 * @property {number|null} lng - Longitude, ou null em caso de erro
 * @property {string} [error] - Mensagem de erro (presente apenas em caso de falha)
 */

/**
 * Busca as coordenadas de um único endereço via Nominatim (OpenStreetMap).
 * @param {string} address
 * @returns {Promise<GeocodeResult>}
 */
async function geocodeAddress(address) {
    const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(address)}`;
    const res  = await fetch(url, { headers: { 'Accept-Language': 'pt-BR', 'User-Agent': 'ATLAS/1.0' } });
    const data = await res.json();
    if (!data.length) throw new Error('Endereço não encontrado');
    return { address, lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
}

/**
 * Geocodifica uma lista de endereços via Nominatim respeitando o rate limit de 1 req/s.
 * Endereços que falharem retornam lat/lng como null sem interromper os demais.
 * @param {string[]} addresses
 * @returns {Promise<GeocodeResult[]>}
 */
export async function geocodeBatch(addresses) {
    const results = [];
    for (const address of addresses) {
        try {
            results.push(await geocodeAddress(address));
        } catch (err) {
            results.push({ address, lat: null, lng: null, error: err.message ?? 'Erro desconhecido' });
        }
        // Nominatim exige no máximo 1 req/s
        await new Promise(r => setTimeout(r, 1100));
    }
    return results;
}

/**
 * Busca geral: tenta encontrar um parceiro pelo ID/nome; se não achar,
 * trata o termo como endereço e faz geocodificação para navegar no mapa.
 * @param {string} [partnerId] - salesforce_id ou termo de busca livre
 */
export async function searchLocation(partnerId) {
    const inputEl = document.getElementById('search-input');
    const term = partnerId || inputEl?.value?.trim();
    if (!term) return;

    // 1. Tenta encontrar parceiro
    const found = state.allMarkersData.find(d =>
        d.salesforce_id === term ||
        d.name?.toLowerCase().includes(term.toLowerCase())
    );

    if (found) {
        const marker = state.markerObjects.find(m => m.markerData?.salesforce_id === found.salesforce_id);
        if (marker) {
            state.map.setView(marker.getLatLng(), 15);
            marker.fire('click');
        } else {
            state.map.setView([found.lat, found.lon], 15);
            alert('Parceiro encontrado, mas nao esta visivel com os filtros atuais.');
        }
        if (!partnerId && inputEl) inputEl.value = '';
        return;
    }

    // 2. Trata como endereço e geocodifica via geocodeBatch
    const [result] = await geocodeBatch([term]);
    if (result?.lat && result?.lng) {
        state.map.setView([result.lat, result.lng], 16);

        // Remove pin anterior de busca, se existir
        if (state._searchPin) {
            state._searchPin.remove();
            state._searchPin = null;
        }
        // Cria pin temporário — fechar o popup remove o pin do mapa
        state._searchPin = L.marker([result.lat, result.lng])
            .addTo(state.map)
            .bindPopup(`<b>📍 ${term}</b>`)
            .openPopup();
        state._searchPin.on('popupclose', () => {
            state._searchPin.remove();
            state._searchPin = null;
        });
    } else {
        alert('Nenhum parceiro ou endereco encontrado para: ' + term);
    }
    if (!partnerId && inputEl) inputEl.value = '';
}



// ---------------------------------------------------------------------------
// POPUPS DE MARCADORES
// ---------------------------------------------------------------------------

/**
 * Retorna o HTML do popup correto para um parceiro com base no seu status.
 * @param {import('../models.js').Partner} data
 * @returns {string|null}
 */
export function getPopupContent(data) {
    if (data.optimization_decision === 'Optimization suggested' && data.status === PartnerStatus.ACTIVE) {
        return _popupOptimization(data);
    }
    const handlers = {
        [PartnerStatus.ACTIVE]:     _popupActive,
        [PartnerStatus.INACTIVE]:   _popupInactive,
        [PartnerStatus.EXITED]:     _popupInactive,
        [PartnerStatus.ONBOARDING]: _popupOnboarding,
        [PartnerStatus.BG_CHECKS]:  _popupVetting,
        [PartnerStatus.PROSPECT]:   _popupProspect,
        [PartnerStatus.NEW]:        _popupNewPartner,
    };
    const fn = handlers[data.status];
    return fn ? fn(data) : null;
}

function _row(label, value) {
    return `<tr><td style="width:40%"><b>${label}:</b></td><td style="width:60%">${value}</td></tr>`;
}
function _table(rows) {
    return `<table style="width:100%"><tbody>${rows}</tbody></table>`;
}
function _sfLink(id) {
    return `<a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${id}/view" target="_blank">View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i></a><br>`;
}
function _waLink(tel) {
    return `Enviar mensagem <a href="https://wa.me/${tel}" target="_blank"><i class="fa fa-whatsapp" style="font-size:24px"></i></a>`;
}

function _popupActive(data) {
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station)+_row('Launch Date',data.launch_date)+_row('HCP Initiatives',data.hub_delivey_initiatives)+_row('HCP Host Partner',data.HCP_host_partner)+_row('HCP Rate Card',data.HCP_rate_card)+_row('Radius',data.radius+' m')+_row('Capacity',data.capacity+' pkgs'))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}${_waLink(data.telefone)}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            <button class="btn btn-info btn-sm btn-block" onclick="UIManager.requestAssistence(event,'${data.store_id}',5)"><i class="fas fa-phone"></i> Solicitar Resgate</button>
            <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event,'${data.salesforce_id}','${data.name.replace(/'/g,"\\'")}')"><i class="fas fa-route"></i> Rota a Partir Daqui</button>
        </div>
    </div>`;
}

function _popupInactive(data) {
    if (data.status === PartnerStatus.EXITED) {
        data.optimization.cap_suggestion    = data.capacity;
        data.optimization.radius_suggestion = data.radius;
    }
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}${_waLink(data.telefone)}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            ${_table(_row('Decisao',data.decision)+_row('Capacidade Sugerida',data.optimization.cap_suggestion+' pkgs')+_row('Raio Sugerido',data.optimization.radius_suggestion+' m'))}
        </div>
    </div>`;
}

function _popupOnboarding(data) {
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station)+_row('Launch Date',data.launch_date)+_row('HCP Initiatives',data.hub_delivey_initiatives)+_row('HCP Host Partner',data.HCP_host_partner)+_row('HCP Rate Card',data.HCP_rate_card))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}${_waLink(data.telefone)}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            ${_table(_row('Capacidade Sugerida',data.optimization.cap_suggestion+' pkgs')+_row('Raio Sugerido',data.optimization.radius_suggestion+' m'))}
            <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event,'${data.salesforce_id}','${data.name.replace(/'/g,"\\'")}')"><i class="fas fa-route"></i> Rota a Partir Daqui</button>
        </div>
    </div>`;
}

function _popupVetting(data) {
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station)+_row('Launch Date',data.launch_date))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}${_waLink(data.telefone)}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            ${_table(_row('Capacidade Sugerida',data.optimization.cap_suggestion+' pkgs')+_row('Raio Sugerido',data.optimization.radius_suggestion+' m'))}
        </div>
    </div>`;
}

function _popupProspect(data) {
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            ${_table(_row('Decisao',data.reason)+_row('Capacidade Sugerida',data.optimization.cap_suggestion+' pkgs')+_row('Raio Sugerido',data.optimization.radius_suggestion+' m'))}
        </div>
    </div>`;
}

function _popupNewPartner(data) {
    if (!state._slotPopupData) state._slotPopupData = {};
    // Usar slot_id como chave — garante que searchNearbyFromState encontra o slot correto
    const slotKey = (data.slot_id || ('slot_'+data.bucket_ade+'_'+(data.lat||'')+'_'+(data.lon||''))).replace(/[^a-zA-Z0-9_]/g,'_');
    state._slotPopupData[slotKey] = Array.isArray(data.ceps) ? data.ceps : [];
    const cepsDisplay = Array.isArray(data.ceps) ? data.ceps.join(', ') : data.ceps;
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">New Partner</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Delivery Station',data.delivery_station)+_row('Bucket',data.bucket_ade))}
            <hr class="my-2">
            <div style="max-height:220px;overflow-y:auto;">
                ${_table(_row('Ceps Alvo',cepsDisplay)+_row('Volume maximo',data.capacity+' pkgs')+_row('Raio Sugerido',data.radius+' m'))}
            </div>
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            <button class="btn btn-success btn-sm btn-block" onclick="GmapsScraper.searchNearbyFromState(event,'${data.bucket_ade}','${slotKey}')">🏪 Ver Empresas Candidatas</button>
        </div>
    </div>`;
}

function _popupOptimization(data) {
    return `<div style="width:300px;font-size:12px;">
        <div class="partner-header"><h5 style="font-weight:bold;">${data.name}</h5></div>
        <div class="partner-info" id="partnerInfo">
            ${_table(_row('Store ID',data.store_id)+_row('Status',data.status)+_row('Carteira',data.bucket_ade)+_row('Delivery Station',data.delivery_station)+_row('Launch Date',data.launch_date)+_row('HCP Initiatives',data.hub_delivey_initiatives)+_row('Radius',data.radius+' m')+_row('Capacity',data.capacity+' pkgs'))}
            <hr class="my-2">${_sfLink(data.salesforce_id)}${_waLink(data.telefone)}
        </div>
        <div id="optimizationInfo" style="display:none;padding:10px;">
            <h5>Otimizacao de Raio</h5>${_table(_row('Raio Sugerido',data.optimization.radius_suggestion+' m'))}
            <hr><h5>Otimizacao de Capacidade</h5>${_table(_row('Capacidade Sugerida',data.optimization.cap_suggestion+' pkgs'))}
        </div>
        <hr class="my-2">
        <div class="partner-actions">
            <button class="btn btn-warning btn-sm btn-block mb-1" id="toggleOptBtn" onclick="MapManager.toggleOptimizationBtn()">🚀 Otimizacao Disponivel</button>
            <button class="btn btn-info btn-sm btn-block" onclick="UIManager.requestAssistence(event,'${data.store_id}',5)"><i class="fas fa-phone"></i> Solicitar Resgate</button>
            <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event,'${data.salesforce_id}','${data.name.replace(/'/g,"\\'")}')"><i class="fas fa-route"></i> Rota a Partir Daqui</button>
        </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// PAINEL DE STATS
// ---------------------------------------------------------------------------

export function togglePanelContent(headerElement) {
    const content = headerElement.nextElementSibling;
    const icon = headerElement.querySelector('i.fas.fa-chevron-down, i.fas.fa-chevron-up');
    content?.classList.toggle('collapsed');
    if (icon) { icon.classList.toggle('fa-chevron-down'); icon.classList.toggle('fa-chevron-up'); }
}

export function updateActiveStatsTab() {
    const el = document.querySelector('#stats-inner-panel .nav-link.active');
    if (el) updateStats(el.getAttribute('href').substring(1));
}

export function updateStats(tab) {
    if (tab === 'Performance') updatePerformanceStats();
    else if (tab === 'Expansion') updateExpansionStats();
    else if (tab === 'Routes') updateRoutesStats();
}

function _createCard(title, value, goal, container) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `<h3>${title}</h3><p class="metric-value">${value}</p>`;
    if (goal > 0) card.classList.add(parseFloat(value) >= goal ? 'positive' : 'negative');
    container.appendChild(card);
}

function _mean(arr) { return arr.length > 0 ? arr.reduce((s, v) => s + v, 0) / arr.length : 0; }

export function updatePerformanceStats() {
    const data = state.currentFilteredData;
    const container = document.getElementById('performance-cards');
    if (!container) return;
    container.innerHTML = '';
    const active = data.filter(p => p.status === 'Active');
    const n = active.length;
    const adv = n > 0 ? active.reduce((s, p) => s + (p.ADV || 0), 0) / n : 0;
    _createCard('Parceiros Ativos', n, PERFORMANCE_GOALS.activePartners, container);
    _createCard('ADV Medio', adv.toFixed(0), PERFORMANCE_GOALS.advOverall, container);
    _createCard('EAD', (_mean(active.map(p => p.main_store_data?.ead ?? 0)) * 100).toFixed(1) + '%', PERFORMANCE_GOALS.ead, container);
    _createCard('DEA', (_mean(active.map(p => p.main_store_data?.dea ?? 0)) * 100).toFixed(1) + '%', PERFORMANCE_GOALS.dea, container);
    _createCard('DCR', (_mean(active.map(p => p.main_store_data?.dcr ?? 0)) * 100).toFixed(1) + '%', PERFORMANCE_GOALS.dcr, container);
    new Tabulator('#performance-table', {
        data: data.map(p => ({...p})), layout: 'fitColumns', height: '400px',
        columns: [
            { title: 'Store ID', field: 'store_id' },
            { title: 'Store Name', field: 'name', width: 200 },
            { title: 'D. Station', field: 'delivery_station' },
            { title: 'Bucket', field: 'bucket_ade' },
            { title: 'Status', field: 'status' },
        ],
    });
}

export function updateExpansionStats() {
    const container = document.getElementById('expansion-cards');
    if (!container || !state.polygonsData) return;
    container.innerHTML = '';
    const selStations = Array.from(document.getElementById('stationFilter')?.selectedOptions ?? []).map(o => o.value);
    const polys = selStations.includes('all') ? state.polygonsData.features
        : state.polygonsData.features.filter(p => selStations.includes(p.properties.delivery_station));
    const data = state.currentFilteredData;
    const totalActive  = data.filter(p => p.status === 'Active').length;
    const totalOnboard = data.filter(p => p.status === 'Onboarding' || p.status === 'BG Checks').length;
    const totalExpected = polys.reduce((s, p) => s + (p.properties.num_points || 0), 0);
    const attainment = totalExpected > 0 ? ((totalActive + totalOnboard) / totalExpected) * 100 : 0;
    _createCard('Total Esperado', totalExpected, 0, container);
    _createCard('Parceiros Ativos', totalActive, 85, container);
    _createCard('Parceiros Onboarding', totalOnboard, 25, container);
    _createCard('Attainment Geral', attainment.toFixed(1) + '%', 80, container);
}

export function updateRoutesStats() {
    const container = document.getElementById('routes-cards');
    if (!container) return;
    container.innerHTML = '';
    const runs = [...new Set(state.currentFilteredData.map(p => p.supply_run).filter(Boolean))];
    const hcpHosts   = state.currentFilteredData.filter(p => p.hub_delivey_initiatives === 'HCP Host Partner'   && p.status === 'Active' && p.HCP_rate_card === 'Tier 1').length;
    const hcpPickups = state.currentFilteredData.filter(p => p.hub_delivey_initiatives === 'HCP Pick Up Partner' && p.status === 'Active' && p.HCP_rate_card === 'Tier 1').length;
    const activeCount = state.currentFilteredData.filter(p => p.status === 'Active').length;
    _createCard('Total de Rotas', runs.length, 0, container);
    _createCard('HCP Host Partners', hcpHosts, (activeCount * 0.12).toFixed(0), container);
    _createCard('HCP Pick-up Partners', hcpPickups, (activeCount * 0.48).toFixed(0), container);
}

// ---------------------------------------------------------------------------
// ANALISE DE AREA
// ---------------------------------------------------------------------------

const NO_GO_REASONS = [
    'Sem oportunidade próxima',
    'Fora de jurisdição',
    'Não avaliado por falta de coordenadas',
];

export function populateAreaAnalysisFilters() {
    // Inclui todos os prospects — com ou sem decision — para capturar todos os estados
    const prospects = state.allMarkersData.filter(m => m.status === 'Prospect');
    const states = [...new Set(prospects.map(m => m.state).filter(Boolean))].sort();
    const sel = document.getElementById('areaStateFilter');
    if (!sel) return;
    sel.innerHTML = '<option value="all" selected>Todos</option>';
    states.forEach(s => sel.innerHTML += `<option value="${s}">${s}</option>`);
}

/**
 * Retorna o overview global de prospects (sem filtros, sempre estático).
 */
function _getGlobalOverview() {
    const allProspects = state.allMarkersData.filter(m => m.status === 'Prospect');
    const noCoords     = allProspects.filter(m => !m.hasCoords).length;
    const evaluated    = allProspects.filter(m => m.decision);
    const go   = evaluated.filter(p => p.decision === 'Go').length;
    const nogo = evaluated.filter(p => p.decision === 'No Go').length;
    const rate = evaluated.length > 0 ? ((go / evaluated.length) * 100).toFixed(1) : '0.0';

    // Motivos de No Go — calculados sobre TODOS os avaliados (sem filtro)
    const nogoReasonCounts = {};
    NO_GO_REASONS.forEach(r => {
        nogoReasonCounts[r] = evaluated.filter(p => p.decision === 'No Go' && p.reason === r).length;
    });

    return { total: evaluated.length, go, nogo, rate, noCoords, nogoReasonCounts };
}

/**
 * Agrupa prospects avaliados por estado, retornando stats por UF.
 */
function _getStatsByState(prospects) {
    const byState = {};
    prospects.forEach(p => {
        const uf = p.state || 'N/A';
        if (!byState[uf]) byState[uf] = { go: 0, nogo: 0 };
        if (p.decision === 'Go') byState[uf].go++;
        else byState[uf].nogo++;
    });
    return byState;
}

function _renderStateDetail(prospects) {
    const byState = _getStatsByState(prospects);
    const rows = Object.entries(byState)
        .sort((a, b) => (b[1].go + b[1].nogo) - (a[1].go + a[1].nogo))
        .map(([uf, s]) => {
            const total = s.go + s.nogo;
            const rate  = total > 0 ? ((s.go / total) * 100).toFixed(0) : '0';
            return `<tr>
              <td style="padding:3px 6px;font-weight:600">${uf}</td>
              <td style="padding:3px 6px;text-align:center">${total}</td>
              <td style="padding:3px 6px;text-align:center;color:#28a745">${s.go}</td>
              <td style="padding:3px 6px;text-align:center;color:#dc3545">${s.nogo}</td>
              <td style="padding:3px 6px;text-align:center">${rate}%</td>
            </tr>`;
        }).join('');

    return `
      <div id="state-detail-section" style="margin-top:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <b style="font-size:12px">Detalhamento por Estado</b>
          <button onclick="document.getElementById('state-detail-section').remove()"
                  style="border:none;background:none;font-size:1em;cursor:pointer;color:#666">&times;</button>
        </div>
        <div style="max-height:220px;overflow-y:auto;">
          <table style="width:100%;font-size:12px;border-collapse:collapse;">
            <thead>
              <tr style="background:#f5f5f5;border-bottom:1px solid #ddd">
                <th style="padding:4px 6px;text-align:left">UF</th>
                <th style="padding:4px 6px;text-align:center">Total</th>
                <th style="padding:4px 6px;text-align:center;color:#28a745">Go</th>
                <th style="padding:4px 6px;text-align:center;color:#dc3545">No Go</th>
                <th style="padding:4px 6px;text-align:center">Aprov.</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
}

function _renderStatsPopup(filteredProspects, { state: stateFilter, decision: decisionFilter }) {
    closeStatsPopup();

    const overview = _getGlobalOverview();
    const hasFilter = stateFilter !== 'all' || decisionFilter !== 'all';

    // Motivos de No Go do overview (sempre sobre todos os dados)
    const overviewReasonRows = NO_GO_REASONS.map(r => {
        const count = overview.nogoReasonCounts[r] ?? 0;
        const pct   = overview.nogo > 0 ? ((count / overview.nogo) * 100).toFixed(1) : '0.0';
        return `<tr>
          <td style="padding:2px 4px">${r}</td>
          <td style="padding:2px 4px;text-align:center">${count}</td>
          <td style="padding:2px 4px;text-align:center">${pct}%</td>
        </tr>`;
    }).join('');

    // Contagens do filtro ativo (apenas para exibição secundária)
    const fTotal = filteredProspects.length;
    const fGo    = filteredProspects.filter(p => p.decision === 'Go').length;
    const fNoGo  = filteredProspects.filter(p => p.decision === 'No Go').length;
    const fRate  = fTotal > 0 ? ((fGo / fTotal) * 100).toFixed(1) : '0.0';

    const stateLabel    = stateFilter    === 'all' ? 'Todos' : stateFilter;
    const decisionLabel = decisionFilter === 'all' ? 'Todos' : decisionFilter;

    const html = `
      <div id="stats-area-popup" style="
        position:fixed; top:80px; right:20px; z-index:9999;
        background:#fff; padding:16px; border-radius:8px;
        box-shadow:0 2px 12px rgba(0,0,0,0.2); min-width:340px; max-width:440px;
        font-size:13px; max-height:90vh; overflow-y:auto;">

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <b style="font-size:14px">Análise de Área — Prospects</b>
          <button onclick="UIManager.closeStatsPopup()"
                  style="border:none;background:none;font-size:1.4em;cursor:pointer;">&times;</button>
        </div>

        <!-- OVERVIEW GLOBAL (sempre estático, independente de filtros) -->
        <div style="background:#f8f9fa;border-radius:6px;padding:10px;margin-bottom:10px;">
          <div style="font-size:11px;color:#666;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">Overview Geral</div>
          <div style="display:flex;gap:8px;justify-content:space-between;">
            <div style="text-align:center;flex:1">
              <div style="font-size:20px;font-weight:700">${overview.total}</div>
              <div style="font-size:10px;color:#666">Total avaliados</div>
            </div>
            <div style="text-align:center;flex:1">
              <div style="font-size:20px;font-weight:700;color:#28a745">${overview.go}</div>
              <div style="font-size:10px;color:#666">Go</div>
            </div>
            <div style="text-align:center;flex:1">
              <div style="font-size:20px;font-weight:700;color:#dc3545">${overview.nogo}</div>
              <div style="font-size:10px;color:#666">No Go</div>
            </div>
            <div style="text-align:center;flex:1">
              <div style="font-size:20px;font-weight:700;color:#007bff">${overview.rate}%</div>
              <div style="font-size:10px;color:#666">Aprovação</div>
            </div>
          </div>

          ${overview.noCoords > 0 ? `
          <div style="margin-top:8px;padding:6px 8px;background:#fff8e1;border-radius:4px;border-left:3px solid #f9a825;font-size:11px;color:#555;line-height:1.5;">
            ⚠️ <b>${overview.noCoords}</b> lead(s) sem lat/lon — não avaliados pela Fase 3
          </div>` : ''}

          <!-- Motivos de No Go — sempre visíveis no overview -->
          ${overview.nogo > 0 ? `
          <div style="margin-top:10px;">
            <b style="font-size:11px;color:#555">Detalhamento de No Go:</b>
            <table style="width:100%;margin-top:4px;font-size:11px;border-collapse:collapse;">
              <thead><tr style="background:#f0f0f0">
                <th style="padding:3px 4px;text-align:left">Motivo</th>
                <th style="padding:3px 4px;text-align:center">#</th>
                <th style="padding:3px 4px;text-align:center">% No Go</th>
              </tr></thead>
              <tbody>${overviewReasonRows}</tbody>
            </table>
          </div>` : ''}
        </div>

        ${hasFilter ? `
        <!-- RESULTADO DO FILTRO (contagens apenas, sem repetir tabela de motivos) -->
        <div style="border-top:1px solid #eee;padding-top:10px;margin-bottom:8px;">
          <div style="font-size:11px;color:#666;margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">
            Filtro: Estado = <b>${stateLabel}</b> | Decisão = <b>${decisionLabel}</b>
          </div>
          ${fTotal === 0
            ? '<p class="text-muted" style="font-size:12px">Nenhum prospect encontrado.</p>'
            : `<div style="display:flex;gap:8px;justify-content:space-between;">
                <div style="text-align:center;flex:1">
                  <div style="font-size:18px;font-weight:700">${fTotal}</div>
                  <div style="font-size:10px;color:#666">Total</div>
                </div>
                <div style="text-align:center;flex:1">
                  <div style="font-size:18px;font-weight:700;color:#28a745">${fGo}</div>
                  <div style="font-size:10px;color:#666">Go</div>
                </div>
                <div style="text-align:center;flex:1">
                  <div style="font-size:18px;font-weight:700;color:#dc3545">${fNoGo}</div>
                  <div style="font-size:10px;color:#666">No Go</div>
                </div>
                <div style="text-align:center;flex:1">
                  <div style="font-size:18px;font-weight:700;color:#007bff">${fRate}%</div>
                  <div style="font-size:10px;color:#666">Aprovação</div>
                </div>
              </div>`
          }
        </div>` : ''}

        <!-- BOTÃO DETALHAMENTO POR ESTADO -->
        <div id="state-detail-container"></div>
        <button onclick="UIManager.showStateDetail()"
                style="width:100%;margin-top:8px;padding:6px;border:1px solid #007bff;
                       background:#fff;color:#007bff;border-radius:4px;cursor:pointer;font-size:12px;">
          <i class="fas fa-table"></i> Ver detalhamento por Estado
        </button>
      </div>`;

    document.body.insertAdjacentHTML('beforeend', html);

    // Guarda os prospects filtrados para uso no detalhamento
    window._areaAnalysisProspects = filteredProspects;
}

export function showStateDetail() {
    const container = document.getElementById('state-detail-container');
    if (!container) return;
    // Toggle: se já está aberto, fecha
    if (container.innerHTML.trim()) {
        container.innerHTML = '';
        return;
    }
    const prospects = window._areaAnalysisProspects
        ?? state.allMarkersData.filter(m => m.status === 'Prospect' && m.decision);
    container.innerHTML = _renderStateDetail(prospects);
}

export function analyseArea() {
    const selState    = document.getElementById('areaStateFilter')?.value ?? 'all';
    const selDecision = document.getElementById('areaDecisionFilter')?.value ?? 'all';

    // Prospects avaliados para o filtro (afeta mapa e contagens secundárias)
    let filteredProspects = state.allMarkersData.filter(m => m.status === 'Prospect' && m.decision);
    if (selState    !== 'all') filteredProspects = filteredProspects.filter(m => m.state    === selState);
    if (selDecision !== 'all') filteredProspects = filteredProspects.filter(m => m.decision === selDecision);

    _applyProspectMapFilter(selState, selDecision);
    // Overview sempre usa allMarkersData — _renderStatsPopup chama _getGlobalOverview internamente
    _renderStatsPopup(filteredProspects, { state: selState, decision: selDecision });
}

/**
 * Aplica filtro de prospects no mapa, ignorando os filtros gerais da UI.
 * Ajusta o zoom para mostrar todos os marcadores resultantes.
 */
function _applyProspectMapFilter(stateFilter, decisionFilter) {
    let data = state.allMarkersData.filter(m => m.status === 'Prospect' && m.hasCoords);
    if (stateFilter    !== 'all') data = data.filter(m => m.state    === stateFilter);
    if (decisionFilter !== 'all') data = data.filter(m => m.decision === decisionFilter);
    // Usa o namespace global exposto pelo main.js para evitar dependência circular
    window.MapManager?.createMarkers(data, /* fitBounds= */ true);
}

export function closeStatsPopup() {
    document.getElementById('stats-area-popup')?.remove();
    window._areaAnalysisProspects = null;
}

export function computeFilteredProspects(data, stateFilter, decisionFilter) {
    let filtered = data.filter(m => m.status === 'Prospect' && m.decision);
    if (stateFilter    !== 'all') filtered = filtered.filter(m => m.state    === stateFilter);
    if (decisionFilter !== 'all') filtered = filtered.filter(m => m.decision === decisionFilter);
    return filtered;
}

export function computeStats(prospects) {
    const total   = prospects.length;
    const goCount = prospects.filter(p => p.decision === 'Go').length;
    const approvalRate = total > 0 ? (goCount / total) * 100 : 0;
    const reasonCounts = {};
    NO_GO_REASONS.forEach(r => {
        reasonCounts[r] = prospects.filter(p => p.decision === 'No Go' && p.reason === r).length;
    });
    return { total, goCount, approvalRate, reasonCounts };
}

// ---------------------------------------------------------------------------
// SOLICITACAO DE RESGATE
// ---------------------------------------------------------------------------

export async function requestAssistence(event, storeId, radius = 5) {
    event.stopPropagation();
    const marker = state.markerObjects.find(m => m.markerData?.store_id === storeId);
    if (!marker) return;
    const center = [marker.getLatLng().lng, marker.getLatLng().lat];
    const region = turf.circle(center, radius, { steps: 32, units: 'kilometers' });
    const nearby = state.allMarkersData.filter(p => {
        const pt = turf.point([p.lon, p.lat]);
        return p.status === 'Active' && p.store_id !== storeId && turf.booleanPointInPolygon(pt, region);
    });
    const coords = [...nearby.map(p => [p.lon, p.lat]), [marker.getLatLng().lng, marker.getLatLng().lat]];
    const res = await fetch(`https://router.project-osrm.org/table/v1/driving/${coords.map(c => c.join(',')).join(';')}?annotations=distance`);
    if (!res.ok) return;
    const osrm = await res.json();
    const sorted = nearby.map((p, i) => ({
        partner: p,
        distance: (osrm.distances[i][coords.length - 1] / 1000).toFixed(2),
    })).sort((a, b) => parseFloat(a.distance) - parseFloat(b.distance)).slice(0, 10);

    let html = `<div style="display:flex;justify-content:space-between;align-items:center;"><b>Sugestoes para resgate</b><button onclick="document.getElementById('assistence-suggestions-popup').remove()" style="border:none;background:none;font-size:1.3em;">&times;</button></div><div style="overflow-y:auto;max-height:750px;padding-top:8px;">`;
    sorted.forEach(({ partner, distance }) => {
        const bonus = parseFloat(distance) <= 2 ? 30 : parseFloat(distance) <= 5 ? 40 : 50;
        html += `<p><b>${partner.name}</b><br><b>Distancia:</b> ${distance} km<br><b>Bonus sugerido:</b> R$ ${bonus}</p><a href="https://wa.me/${partner.telefone}" target="_blank"><i class="fa fa-whatsapp" style="font-size:24px"></i></a><hr class="my-2">`;
    });
    html += '</div>';
    let popup = document.getElementById('assistence-suggestions-popup') || document.createElement('div');
    popup.id = 'assistence-suggestions-popup';
    popup.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;max-width:420px;box-shadow:0 2px 8px #0003;';
    popup.innerHTML = html;
    document.body.appendChild(popup);
}
