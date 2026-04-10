/**
 * main.js
 * =======
 * Ponto de entrada da aplicacao.
 * Inicializa modulos, registra subscribers reativos e event listeners.
 * Nao contem logica de negocio — apenas wiring.
 */

import { state, subscribe }          from './state.js';
import { loadAll, applyFilters, resetFilters } from './modules/data-manager.js';
import { initialize, createMarkers, createMarkersDeliveryStations, restyleMarkers, toggleRadii, toggleOptimizationBtn } from './modules/map-manager.js';
import { updateFilteredPolygons, updateFilteredJurisdiction, togglePolygons, toggleJurisdictions, toggleOptimizationLayer, optimizationSelection } from './modules/polygon-manager.js';
import { updatePeriodInfo, populateFilters, setupAutocomplete, searchLocation, updateActiveStatsTab, updateStats, togglePanelContent, requestAssistence, populateAreaAnalysisFilters, analyseArea, closeStatsPopup } from './modules/ui-manager.js';
import { generateRoute, startRouteFromHere, addStop, renderStopsList, moveStopUp, moveStopDown, removeStop, clearRoute, hcpSuggestHostClusters, resetHcpSuggestions } from './modules/route-manager.js';
import { searchNearbyFromState, searchNearby } from './modules/gmaps-scraper.js';
import * as ManagementDashboard from './modules/management-dashboard.js';

// ---------------------------------------------------------------------------
// REATIVIDADE — subscribers do estado global
// ---------------------------------------------------------------------------

subscribe('currentFilteredData', (data) => {
    createMarkersDeliveryStations();
    createMarkers(data, true);
    updateFilteredPolygons();
    updateFilteredJurisdiction();
    updateActiveStatsTab();
    console.log(`[main] Filtragem concluida: ${data.length} itens.`);
});

subscribe('period', (period) => {
    updatePeriodInfo(period);
});

subscribe('allMarkersData', () => {
    populateFilters();
    setupAutocomplete();
    populateAreaAnalysisFilters();
});

// ---------------------------------------------------------------------------
// NAMESPACES GLOBAIS
// Necessario para que os atributos onclick no HTML possam chamar os modulos.
// ---------------------------------------------------------------------------

window.MapManager = { initialize, createMarkers, restyleMarkers, toggleRadii, toggleOptimizationBtn };
window.PolygonManager = { updateFilteredPolygons, updateFilteredJurisdiction, togglePolygons, toggleJurisdictions, toggleOptimizationLayer, optimizationSelection };
window.UIManager = { searchLocation, updateStats, togglePanelContent, requestAssistence, analyseArea, closeStatsPopup };
window.RouteManager = { generateRoute, startRouteFromHere, addStop, renderStopsList, moveStopUp, moveStopDown, removeStop, clearRoute, hcpSuggestHostClusters, resetHcpSuggestions };
window.GmapsScraper = { searchNearbyFromState, searchNearby };
window.DataManager  = { applyFilters, resetFilters };
window.ManagementDashboard = ManagementDashboard;

// ---------------------------------------------------------------------------
// BOOTSTRAP
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    initialize();
    loadAll();

    // Panel toggles
    document.querySelectorAll('.panel-header').forEach(header => {
        header.addEventListener('click', () => togglePanelContent(header));
    });

    // Controles principais
    document.getElementById('search-btn')?.addEventListener('click', () => searchLocation());
    document.querySelector('.form-search')?.addEventListener('submit', e => { e.preventDefault(); searchLocation(); });
    document.querySelectorAll('input[name="categoryStyle"]').forEach(r => r.addEventListener('change', () => restyleMarkers()));
    document.getElementById('showRadii')?.addEventListener('change', () => toggleRadii());
    document.getElementById('showPolygons')?.addEventListener('change', () => togglePolygons());
    document.getElementById('showJurisdictions')?.addEventListener('change', () => toggleJurisdictions());
    document.getElementById('showOptimizationLayer')?.addEventListener('change', () => toggleOptimizationLayer());

    // Filtros
    document.querySelector('#filter-content button.btn-primary')?.addEventListener('click', () => applyFilters());
    document.querySelector('#filter-content button.btn-secondary')?.addEventListener('click', () => resetFilters());

    // Highlight
    document.getElementById('highlight-btn')?.addEventListener('click', () => HighlightManager.highlightStores());
    document.getElementById('highlight-btn-clear')?.addEventListener('click', () => HighlightManager.resetHighlight());

    // Painel de stats
    const statsPanel = document.getElementById('stats-panel');
    document.getElementById('stats-toggle-button')?.addEventListener('click', () => {
        statsPanel?.classList.toggle('open');
        if (statsPanel?.classList.contains('open')) ManagementDashboard.init();
    });
    document.getElementById('close-stats-panel')?.addEventListener('click', () => statsPanel?.classList.remove('open'));

    // Fechar Stats Popup ao trocar de aba
    document.querySelectorAll('#controlTabs a[data-toggle="tab"]').forEach(tab => {
        tab.addEventListener('shown.bs.tab', e => {
            const target = e.target.getAttribute('href');
            if (target !== '#highlight-content') closeStatsPopup();
        });
    });

    // Botao HCP
    document.getElementById('stationFilter')?.addEventListener('change', function() {
        const sel = Array.from(this.selectedOptions).map(o => o.value);
        const btn = document.getElementById('suggest-routes-btn');
        if (btn) btn.style.display = (sel.length === 1 && sel[0] !== 'all') ? 'block' : 'none';
    });

    // Fechar popups ao clicar fora
    document.addEventListener('click', e => {
        if (!e.ctrlKey && state.selectedGrids) {
            state.selectedGrids = [];
            state.map?.closePopup();
        }
    });
});
