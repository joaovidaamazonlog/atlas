/**
 * map-manager.js
 * ==============
 * Gerencia o mapa Leaflet, marcadores de parceiros,
 * círculos de raio, estilos dinâmicos e legenda.
 *
 * Responsabilidades
 * -----------------
 * - Inicialização do mapa e tile layer
 * - Criação e remoção de marcadores (circleMarker)
 * - Estilização dinâmica por campo (borda/preenchimento)
 * - Geração de legenda
 * - Popups de marcadores (delegado ao UIManager)
 */

import { state }          from '../state.js';
import { MAP_CONFIG, COLOR_PALETTES } from '../config.js';
import { PartnerStatus }  from '../models.js';
import { getPopupContent } from './ui-manager.js';

// ---------------------------------------------------------------------------
// INICIALIZAÇÃO
// ---------------------------------------------------------------------------

/**
 * Inicializa o mapa Leaflet e configura o pane de polígonos.
 * Deve ser chamado uma única vez no bootstrap.
 */
export function initialize() {
    const map = L.map('map').setView(MAP_CONFIG.center, MAP_CONFIG.zoom);

    L.tileLayer(MAP_CONFIG.tileUrl, {
        maxZoom:    MAP_CONFIG.maxZoom,
        subdomains: MAP_CONFIG.subdomains,
    }).addTo(map);

    map.createPane('polygonsPane');
    map.getPane('polygonsPane').style.zIndex       = 200;
    map.getPane('polygonsPane').style.pointerEvents = 'none';

    state.map = map;

    // Ícones globais
    state.highlightIcon = L.icon({
        iconUrl:    'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
        shadowUrl:  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize:   [25, 41], iconAnchor: [12, 41],
        popupAnchor:[1, -34], shadowSize: [41, 41],
    });

    state.houseIcon = L.icon({
        iconUrl:   'icons/warehouse.png',
        iconSize:  [18, 18], iconAnchor: [16, 32], popupAnchor: [0, -32],
    });
}

// ---------------------------------------------------------------------------
// DELIVERY STATIONS
// ---------------------------------------------------------------------------

/**
 * Cria marcadores fixos para as delivery stations.
 * Chamado após cada filtragem (idempotente — não duplica).
 */
export function createMarkersDeliveryStations() {
    state.deliveryStations.forEach(ds => {
        const marker = L.marker([ds.lat, ds.lon], { icon: state.houseIcon });
        marker.bindPopup(`<b>${ds.nome}</b>`);
        marker.addTo(state.map);
    });
}

// ---------------------------------------------------------------------------
// MARCADORES DE PARCEIROS
// ---------------------------------------------------------------------------

/**
 * Cria circleMarkers para todos os parceiros filtrados.
 *
 * @param {import('../models.js').Partner[]} data       - Dados a renderizar
 * @param {boolean}                          fitBounds  - Ajustar zoom ao grupo
 */
export function createMarkers(data, fitBounds = false) {
    clearMarkers();

    data.forEach(partner => {
        const marker = L.circleMarker(
            [partner.lat, partner.lon],
            { radius: 7, color: 'orange', weight: 1.5, fillOpacity: 0.9 }
        );

        marker.markerData = partner;
        marker.on('click', _onMarkerClick);

        if (partner.tooltip) {
            marker.bindTooltip(partner.tooltip, {
                direction: 'top', sticky: true, className: 'custom-tooltip',
            });
        }

        state.markerObjects.push(marker);
        marker.addTo(state.map);

        // Círculo de raio
        const circle = L.circle(
            [partner.lat, partner.lon],
            { radius: partner.radius, fillOpacity: 0.05, weight: 1, interactive: false }
        );
        circle.markerData = partner;
        state.circleObjects.push(circle);

        if (document.getElementById('showRadii')?.checked) {
            circle.addTo(state.map);
        }
    });

    restyleMarkers();

    if (fitBounds && state.markerObjects.length > 0) {
        const group = new L.featureGroup(state.markerObjects);
        state.map.fitBounds(group.getBounds().pad(0.1));
    }
}

/**
 * Remove todos os marcadores e círculos do mapa.
 */
export function clearMarkers() {
    state.markerObjects.forEach(m => state.map.removeLayer(m));
    state.circleObjects.forEach(c => state.map.removeLayer(c));
    state.markerObjects = [];
    state.circleObjects = [];
}

// ---------------------------------------------------------------------------
// ESTILIZAÇÃO
// ---------------------------------------------------------------------------

/**
 * Reaplica estilos de borda e preenchimento com base nos campos selecionados na UI.
 */
export function restyleMarkers() {
    const primaryEl   = document.getElementById('primaryStyle');
    const secondaryEl = document.getElementById('secondaryStyle');
    if (!primaryEl || !secondaryEl) return;

    const primary   = primaryEl.value;
    const secondary = secondaryEl.value;
    const primaryLabel   = primaryEl.selectedOptions[0]?.innerText ?? primary;
    const secondaryLabel = secondaryEl.selectedOptions[0]?.innerText ?? secondary;

    const borderColorMap = generateColorMap(state.currentFilteredData, primary, true);
    const fillColorMap   = secondary !== primary
        ? generateColorMap(state.currentFilteredData, secondary, false)
        : {};

    state.markerObjects.forEach(marker => {
        const borderKey   = marker.markerData[primary]   || 'N/A';
        const borderColor = borderColorMap[borderKey]    || COLOR_PALETTES.border[0];

        let fillColor = '#fff';
        if (secondary !== primary) {
            const fillKey = marker.markerData[secondary] || 'N/A';
            fillColor = fillColorMap[fillKey] || '#808080';
        }

        marker.setStyle({ fillColor, color: borderColor, weight: 3, fillOpacity: 0.9 });

        // Sincronizar cor do círculo de raio
        const circle = state.circleObjects.find(
            c => c.markerData?.salesforce_id === marker.markerData?.salesforce_id
        );
        if (circle) circle.setStyle({ color: borderColor });
    });

    _createLegend(fillColorMap, borderColorMap, primaryLabel, secondaryLabel);
}

/**
 * Gera um mapa {valor → cor} para um campo dos dados.
 *
 * @param {Object[]} data
 * @param {string}   field
 * @param {boolean}  isBorder
 * @returns {Object.<string, string>}
 */
export function generateColorMap(data, field, isBorder = false) {
    const palette = isBorder ? COLOR_PALETTES.border : COLOR_PALETTES.fill;
    const uniqueKeys = [...new Set(data.map(item => item[field] || 'N/A'))].sort();
    const colorMap = {};
    uniqueKeys.forEach((val, idx) => {
        colorMap[val] = palette[idx % palette.length];
    });
    return colorMap;
}

// ---------------------------------------------------------------------------
// TOGGLE RAIOS
// ---------------------------------------------------------------------------

/**
 * Mostra ou oculta os círculos de raio dos parceiros.
 */
export function toggleRadii() {
    const show = document.getElementById('showRadii')?.checked;
    state.circleObjects.forEach(c =>
        show ? c.addTo(state.map) : state.map.removeLayer(c)
    );
}

// ---------------------------------------------------------------------------
// TOGGLE PAINEL DE OTIMIZAÇÃO NO POPUP
// ---------------------------------------------------------------------------

/**
 * Alterna entre a view de informações do parceiro e a view de otimização no popup.
 */
export function toggleOptimizationBtn() {
    const partnerInfo    = document.getElementById('partnerInfo');
    const optimizationInfo = document.getElementById('optimizationInfo');
    const toggleBtn      = document.getElementById('toggleOptBtn');
    if (!partnerInfo || !optimizationInfo || !toggleBtn) return;

    const showingPartner = partnerInfo.style.display !== 'none';
    partnerInfo.style.display      = showingPartner ? 'none'  : 'block';
    optimizationInfo.style.display = showingPartner ? 'block' : 'none';
    toggleBtn.innerHTML = showingPartner ? '⬅️ Voltar' : '🚀 Otimização Disponível';
    toggleBtn.classList.toggle('btn-warning',   !showingPartner);
    toggleBtn.classList.toggle('btn-secondary',  showingPartner);
}

// ---------------------------------------------------------------------------
// HANDLERS INTERNOS
// ---------------------------------------------------------------------------

/**
 * Handler de clique em marcador — delega o conteúdo do popup ao UIManager.
 * @param {L.LeafletMouseEvent} e
 */
function _onMarkerClick(e) {
    const marker = e.target;
    const data   = marker.markerData;

    state.map.setView(marker.getLatLng(), 15);

    const html = getPopupContent(data);
    if (html) marker.bindPopup(html).openPopup();
}

/**
 * Cria ou atualiza o controle de legenda no mapa.
 *
 * @param {Object} fillColorMap
 * @param {Object} borderColorMap
 * @param {string} primaryLabel
 * @param {string} secondaryLabel
 */
function _createLegend(fillColorMap, borderColorMap, primaryLabel, secondaryLabel) {
    if (state.legendControl) state.map.removeControl(state.legendControl);

    state.legendControl = L.control({ position: 'bottomright' });
    state.legendControl.onAdd = () => {
        const div = L.DomUtil.create('div', 'info legend');
        div.innerHTML = '<h5>Legenda</h5>';
        div.innerHTML += `<b>Borda (${primaryLabel}):</b><br>`;
        for (const [key, color] of Object.entries(borderColorMap)) {
            div.innerHTML += `<i style="background:#fff;border:3.5px solid ${color}"></i> ${key}<br>`;
        }
        if (Object.keys(fillColorMap).length > 0) {
            div.innerHTML += `<hr style="margin:4px 0;"><b>Preenchimento (${secondaryLabel}):</b><br>`;
            for (const [key, color] of Object.entries(fillColorMap)) {
                div.innerHTML += `<i style="background:${color};border:1.5px solid #222"></i> ${key}<br>`;
            }
        }
        return div;
    };
    state.legendControl.addTo(state.map);
}
