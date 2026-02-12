/* FrontEnd/script.js */

// Inicialização do Web Worker para processamento de dados off-thread
const dataWorker = new Worker('data-worker.js');

// --- GLOBAL STATE & CONSTANTS ---
const AppState = {
    map: L.map('map').setView([-14.235, -51.925], 5), // Centro do Brasil
    period: [],
    allMarkersData: [],
    currentFilteredData: [],
    markerObjects: [],
    circleObjects: [],
    hcpSuggestionCache: {},
    highlightedMarkers: [],
    tempMarker: null,
    legendControl: null,
    routingControl: null,
    polygonsData: null,
    polygonLayer: null,
    deliveryStations: [],
    jurisdictionData: null,
    jurisdictionLayer: null,
    optimizationData: null,
    optimizationLayer: null,
    sortPlanningData: null,
    highlightIcon: L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    }),
    houseIcon : L.icon({
        iconUrl: 'icons/warehouse.png',
        iconSize: [18, 18],
        iconAnchor: [16, 32],
        popupAnchor: [0, -32]
    }),
    COST_PER_SUPPLY_RUN: {
        DSP2: 590, DSP3: 560, DSP4: 600, DSP5: 780, DBH5: 850, DRJ3: 680,
        DGO2: 670, DBS5: 550, DES2: 1065, DPE4: 700, DPB3: 750, DCE3: 820,
        DSA8: 750, DPR2: 1080, DRS5: 1060, DEFAULT: 600
    }
};

AppState.hcpSuggestionCache = AppState.hcpSuggestionCache || {};
AppState.hcpUsedStores = AppState.hcpUsedStores || {};
AppState.hcpSuggestionsActive = AppState.hcpSuggestionsActive || false; 

// --- MODULE: DataManager ---
const DataManager = {
    loadAllDataAndInitialize: function() {
        Promise.all([
            fetch('https://joaovidaamazonlog.github.io/atlas/data/dados_mapa.json').then(res => res.json()),
            fetch('https://joaovidaamazonlog.github.io/atlas/data/clusters_output_filled.geojson').then(res => res.json()),
            fetch('https://joaovidaamazonlog.github.io/atlas/data/jurisdiction.geojson').then(res => res.json()),
            fetch('https://joaovidaamazonlog.github.io/atlas/data/optimization_data.geojson').then(res => res.json()).catch(() => null)
        ]).then(([partnerData, polygonData, jurisdictionData, optData]) => {
            AppState.allMarkersData = partnerData.allMarkerData;
            AppState.period = partnerData.period;
            AppState.deliveryStations = partnerData.deliveryStations;
            AppState.polygonsData = polygonData;
            AppState.jurisdictionData = jurisdictionData;
            AppState.optimizationData = optData;

            UIManager.updatePeriodInfo(AppState.period);
            this.associatePartnersToPolygons();
            UIManager.populateFilters();
            UIManager.setupAutocomplete();
            
            // Configurar o escutador de mensagens do Worker antes da primeira filtragem
            dataWorker.onmessage = (e) => {
                if (e.data.action === 'filterResult') {
                    AppState.currentFilteredData = e.data.filtered;
                    
                    // Ações que precisam obrigatoriamente rodar na Main Thread (Manipulação de DOM/Mapa)
                    MapManager.createMarkersDeliveryStations();
                    MapManager.createMarkers(AppState.currentFilteredData, true);
                    PolygonManager.updateFilteredPolygons();
                    PolygonManager.updateFilteredJurisdiction();
                    UIManager.updateActiveStatsTab();
                    
                    console.log(`Filtragem concluída via Worker: ${AppState.currentFilteredData.length} itens.`);
                }
            };

            this.applyFilters();
            this.opportunities();
            this.optimizationDataAggregate();

            console.log("Todos os dados foram carregados e inicializados.");
        }).catch(error => {
            alert('Não foi possível carregar os arquivos de dados iniciais: ' + error.message);
            console.error(error);
        });
    },

    opportunities: function(){
        if(!AppState.optimizationData) return null;
        const newPartners = AppState.optimizationData.features.filter(f =>
            (f.geometry.type === "Point") && (f.properties.status === "New")
        )
        newPartners.forEach(p => {
            const DS = {
                ...p.properties,
                delivery_station: p.properties.station_code,
                radius: p.properties.radius_suggestion
            };
            delete DS.station_code;
            delete DS.radius_suggestion
            AppState.allMarkersData.push(DS);
        })
    },

    optimizationDataAggregate: function() {
        if (!AppState.optimizationData) return null;
        AppState.allMarkersData.filter(p => p.status === "Active").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
                partner.cluster = optimizationInfo.properties.cluster;
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "Inactive").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
                partner.cluster = optimizationInfo.properties.cluster;
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "Onboarding").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
                partner.cluster = optimizationInfo.properties.cluster;
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "BG Checks").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.salesforce_id === partner.salesforce_id)
            if (optimizationInfo) {
                partner.cluster = optimizationInfo.properties.cluster;
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "Prospect").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.salesforce_id === partner.salesforce_id)
            if (optimizationInfo) {
                partner.delivery_station = optimizationInfo.properties.station_code
                partner.cluster = optimizationInfo.properties.cluster;
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
    },

    associatePartnersToPolygons: function() {
        if (!AppState.polygonsData || !AppState.allMarkersData) return;
        let associatedCount = 0;
        AppState.allMarkersData.forEach(partner => {
            const partnerPoint = turf.point([partner.lon, partner.lat]);
            for (const polygonFeature of AppState.polygonsData.features) {
                if (turf.booleanPointInPolygon(partnerPoint, polygonFeature)) {
                    partner.regiao = polygonFeature.properties.cluster;
                    associatedCount++;
                    break;
                }
            }
            if (!partner.regiao) {
                partner.regiao = "Fora das Regiões";
            }
        });
        console.log(`${associatedCount} parceiros associados a polígonos de ${AppState.allMarkersData.length} total`);
    },

    applyFilters: function() {
        // Coleta os valores dos filtros da UI (Main Thread)
        const filters = {
            allMarkersData: AppState.allMarkersData,
            selectedStatuses: Array.from(document.getElementById('statusFilter').selectedOptions).map(opt => opt.value),
            selectedStations: Array.from(document.getElementById('stationFilter').selectedOptions).map(opt => opt.value),
            initiativesFilter: document.getElementById('initiativesFilter').value,
            supplyRun: document.getElementById('supplyRun').value,
            jurisdictionFilter: document.getElementById('jurisdictionFilter').value
        };

        // Envia os dados para o Worker. A UI continua livre para interação!
        dataWorker.postMessage({ action: 'filter', filters });
    },

    resetFilters: function() {
        document.getElementById('statusFilter').value = 'all';
        document.getElementById('initiativesFilter').value = 'all';
        document.getElementById('jurisdictionFilter').value = 'all';
        document.getElementById('supplyRun').value = 'all';
        const stationFilter = document.getElementById('stationFilter');
        Array.from(stationFilter.options).forEach(opt => opt.selected = (opt.value === 'all'));

        this.applyFilters();
    },
};
