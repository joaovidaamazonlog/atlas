
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

// --- MODULE: DataManager ---
const DataManager = {
    loadAllDataAndInitialize: function() {
        Promise.all([
            fetch('data/dados_mapa.json').then(res => res.json()),
            fetch('data/clusters_output_filled.geojson').then(res => res.json()),
            fetch('data/jurisdiction.geojson').then(res => res.json()),
            fetch('data/optimization_layers.geojson').then(res => res.json()).catch(() => null)
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
            this.applyFilters();
        }).catch(error => {
            console.error('Erro ao carregar dados:', error);
        });
    },

    associatePartnersToPolygons: function() {
        if (!AppState.polygonsData || !AppState.allMarkersData) return;
        AppState.allMarkersData.forEach(partner => {
            const partnerPoint = turf.point([partner.lon, partner.lat]);
            for (const polygonFeature of AppState.polygonsData.features) {
                if (turf.booleanPointInPolygon(partnerPoint, polygonFeature)) {
                    partner.regiao = polygonFeature.properties.cluster;
                    break;
                }
            }
            if (!partner.regiao) partner.regiao = "Fora das Regiões";
        });
    },

    applyFilters: function() {
        // Lógica de filtro simplificada para brevidade
        AppState.currentFilteredData = AppState.allMarkersData;
        MapManager.createMarkers(AppState.currentFilteredData, true);
    }
};

// --- MODULE: MapManager ---
const MapManager = {
    initialize: function() {
        L.tileLayer('http://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
            maxZoom: 20,
            subdomains: ['mt0', 'mt1', 'mt2', 'mt3']
        }).addTo(AppState.map);
    },

    createMarkers: function(dataToRender, fitToMarkers = false) {
        this.clearMarkers();
        dataToRender.forEach(data => {
            const marker = L.circleMarker([data.lat, data.lon], { radius: 7, color: 'white', weight: 1.5, fillOpacity: 0.9 });
            marker.markerData = data;
            marker.on('click', this.onMarkerClick);
            AppState.markerObjects.push(marker);
            marker.addTo(AppState.map);
        });
        if (fitToMarkers && AppState.markerObjects.length > 0) {
            const group = new L.featureGroup(AppState.markerObjects);
            AppState.map.fitBounds(group.getBounds().pad(0.1));
        }
    },

    clearMarkers: function() {
        AppState.markerObjects.forEach(m => AppState.map.removeLayer(m));
        AppState.markerObjects = [];
    },

    onMarkerClick: function(e) {
        const marker = e.target;
        const data = marker.markerData;
        AppState.map.setView(marker.getLatLng(), 15);
        
        const optimizationHtml = data.optimization ? `
            <div class="opt-slide-content" style="display:none; padding: 10px; min-width: 100%;">
                <h5 style="font-weight:bold;">Otimização de Raio</h5>
                <table style="width:100%; font-size:11px;">
                    <tr><td><b>Raio 1km:</b></td><td>${data.optimization.vol_1000m} pkgs</td></tr>
                    <tr><td><b>Raio 750m:</b></td><td>${data.optimization.vol_750m} pkgs</td></tr>
                    <tr><td><b>Raio 500m:</b></td><td>${data.optimization.vol_500m} pkgs</td></tr>
                    <tr><td><b>Raio 300m:</b></td><td>${data.optimization.vol_300m} pkgs</td></tr>
                </table>
                <hr>
                <div style="background:#f0f0f0; padding:5px; border-radius:4px; font-size:11px;">
                    <b>Recomendação:</b><br>
                    ${data.optimization.vol_500m >= 45 ? '<span style="color:green">✅ Elegível para redução (500m)</span>' : '<span style="color:orange">⚠️ Manter raio atual</span>'}
                </div>
                <button class="btn btn-secondary btn-sm btn-block mt-2" onclick="MapManager.togglePopupSlide(this, false)">⬅️ Voltar</button>
            </div>
        ` : '';

        const popupContent = `
            <div class="popup-container" style="width:250px; overflow:hidden; position:relative;">
                <div class="popup-wrapper" style="display:flex; transition: transform 0.3s ease; width: 200%;">
                    <div class="main-popup-content" style="min-width:50%; padding:5px;">
                        ${data.popup}
                        <hr class="my-2">
                        ${data.optimization ? '<button class="btn btn-warning btn-sm btn-block mb-1" onclick="MapManager.togglePopupSlide(this, true)">🚀 Ver Otimização</button>' : ''}
                    </div>
                    ${optimizationHtml}
                </div>
            </div>
        `;
        marker.bindPopup(popupContent).openPopup();
    },

    togglePopupSlide: function(btn, showOpt) {
        const wrapper = btn.closest('.popup-wrapper');
        const optContent = wrapper.querySelector('.opt-slide-content');
        if (showOpt) {
            optContent.style.display = 'block';
            wrapper.style.transform = 'translateX(-50%)';
        } else {
            wrapper.style.transform = 'translateX(0)';
            setTimeout(() => { optContent.style.display = 'none'; }, 300);
        }
    },

    toggleOptimizationLayer: function(type) {
        if (AppState.optimizationLayer) {
            AppState.map.removeLayer(AppState.optimizationLayer);
            AppState.optimizationLayer = null;
            if (type === 'none') return;
        }

        if (!AppState.optimizationData) return;

        AppState.optimizationLayer = L.geoJSON(AppState.optimizationData, {
            filter: (f) => f.properties.type === type,
            style: (f) => {
                if (type === 'gap_opportunity') {
                    return { color: "#ff4444", weight: 2, fillOpacity: 0.4 };
                }
            },
            pointToLayer: (f, latlng) => {
                if (type === 'heatmap_point') {
                    return L.circleMarker(latlng, {
                        radius: Math.sqrt(f.properties.intensity) * 2,
                        fillColor: "#ffae00",
                        color: "#000",
                        weight: 1,
                        opacity: 1,
                        fillOpacity: 0.6
                    });
                }
            }
        }).addTo(AppState.map);
    }
};

// --- MODULE: UIManager ---
const UIManager = {
    updatePeriodInfo: function(period) {
        const el = document.getElementById('periodInfo');
        if (el) el.innerText = period;
    },
    populateFilters: function() {
        // Implementação de filtros
    }
};

// Inicialização
MapManager.initialize();
DataManager.loadAllDataAndInitialize();
