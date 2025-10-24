/* FrontEnd/script.js */

// --- GLOBAL STATE & CONSTANTS ---
const AppState = {
    map: L.map('map').setView([-14.235, -51.925], 5), // Centro do Brasil
    period: [],
    allMarkersData: [],
    currentFilteredData: [],
    markerObjects: [],
    circleObjects: [],
    highlightedMarkers: [],
    tempMarker: null,
    legendControl: null,
    routingControl: null,
    polygonsData: null,
    polygonLayer: null,
    jurisdictionData: null,
    jurisdictionLayer: null,
    highlightIcon: L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
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
            fetch('https://joaovidaamazonlog.github.io/atlas/data/dados_mapa.json').then(res => res.json()),
            fetch('https://joaovidaamazonlog.github.io/atlas/data/clusters_output.geojson').then(res => res.json()),
            fetch('https://joaovidaamazonlog.github.io/atlas/data/jurisdiction.geojson').then(res => res.json())
        ]).then(([partnerData, polygonData, jurisdictionData]) => {
            AppState.allMarkersData = partnerData.allMarkerData;
            AppState.period = partnerData.period;
            AppState.polygonsData = polygonData;
            AppState.jurisdictionData = jurisdictionData;

            UIManager.updatePeriodInfo(AppState.period);
            this.associatePartnersToPolygons();

            UIManager.populateFilters();
            UIManager.setupAutocomplete();
            this.applyFilters();

            console.log("Todos os dados foram carregados e inicializados.");
        }).catch(error => {
            alert('Não foi possível carregar os arquivos de dados iniciais: ' + error.message);
            console.error(error);
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
        const statusFilter = document.getElementById('statusFilter').value;
        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
        const initiativesFilter = document.getElementById('initiativesFilter').value;
        const jurisdictionFilter = document.getElementById('jurisdictionFilter').value;
        const stationAllSelected = selectedStations.includes('all');

        AppState.currentFilteredData = AppState.allMarkersData.filter(marker => {
            const statusMatch = statusFilter === 'all' || marker.status === statusFilter;
            const stationMatch = stationAllSelected || selectedStations.includes(marker.delivery_station);
            const initiativesMatch = initiativesFilter === 'all' || marker.hub_delivey_initiatives === initiativesFilter;
            const jurisdictionMatch = jurisdictionFilter === 'all' || marker.jurisdiction_type === jurisdictionFilter;
            return statusMatch && stationMatch && initiativesMatch && jurisdictionMatch;
        });

        MapManager.createMarkers(AppState.currentFilteredData, true);
        PolygonManager.updateFilteredPolygons();
        PolygonManager.updateFilteredJurisdiction();
        UIManager.updateActiveStatsTab();
    },

    resetFilters: function() {
        document.getElementById('statusFilter').value = 'all';
        document.getElementById('initiativesFilter').value = 'all';
        document.getElementById('jurisdictionFilter').value = 'all';
        const stationFilter = document.getElementById('stationFilter');
        Array.from(stationFilter.options).forEach(opt => opt.selected = (opt.value === 'all'));
        this.applyFilters();
    }
};

// --- MODULE: MapManager ---
const MapManager = {
    initialize: function() {
        L.tileLayer('http://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}', {
            maxZoom: 20,
            subdomains: ['mt0', 'mt1', 'mt2', 'mt3']
        }).addTo(AppState.map);

        AppState.map.createPane('polygonsPane');
        AppState.map.getPane('polygonsPane').style.zIndex = 200;
        AppState.map.getPane('polygonsPane').style.pointerEvents = 'none';
    },

    createMarkers: function(dataToRender, fitToMarkers = false) {
        this.clearMarkers();
        dataToRender.forEach(data => {
            const marker = L.circleMarker([data.lat, data.lon], { radius: 7, color: 'white', weight: 1.5, fillOpacity: 0.9 });
            marker.markerData = data;
            marker.on('click', this.onMarkerClick);
            AppState.markerObjects.push(marker);
            marker.addTo(AppState.map);

            const circle = L.circle([data.lat, data.lon], { radius: data.radius, fillOpacity: 0.05, weight: 1, interactive: false });
            circle.markerData = data;
            AppState.circleObjects.push(circle);
            if (document.getElementById('showRadii').checked) {
                circle.addTo(AppState.map);
            }
        });

        this.restyleMarkers();
        if (fitToMarkers && AppState.markerObjects.length > 0) {
            const group = new L.featureGroup(AppState.markerObjects);
            AppState.map.fitBounds(group.getBounds().pad(0.1));
        }
    },

    clearMarkers: function() {
        AppState.markerObjects.forEach(m => AppState.map.removeLayer(m));
        AppState.circleObjects.forEach(c => AppState.map.removeLayer(c));
        AppState.markerObjects = [];
        AppState.circleObjects = [];
    },

    onMarkerClick: function(e) {
        const marker = e.target;
        AppState.map.setView(marker.getLatLng(), 15);
        const initialPopupContent = `
            ${marker.markerData.popup}
                <hr class="my-2">
                <button class="btn btn-info btn-sm btn-block" onclick="showComparisonInPopup(event, '${marker.markerData.store_id}')">
                    <i class="fas fa-chart-bar"></i> Mostrar Métricas e Comparações
                </button>
                <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event, '${marker.markerData.store_id}', '${marker.markerData.name.replace(/'/g, "\\'")}')">
                    <i class="fas fa-route"></i> Rota a Partir Daqui
                </button>
            `;
        const popupContent = UIManager.getMarkerPopupContent(marker.markerData);
        marker.bindPopup(popupContent).openPopup();
    },

    restyleMarkers: function() {
        const styleField = document.querySelector('input[name="categoryStyle"]:checked').value;
        const colorMap = this.generateColorMap(AppState.currentFilteredData, styleField);

        AppState.markerObjects.forEach(marker => {
            const categoryValue = marker.markerData[styleField] || 'N/A';
            const newColor = colorMap[categoryValue] || '#808080';
            marker.setStyle({ fillColor: newColor });
            const circle = AppState.circleObjects.find(c => c.markerData.store_id === marker.markerData.store_id);
            if (circle) circle.setStyle({ color: newColor });
        });

        this.createLegend(colorMap);
    },

    generateColorMap: function(data, field) {
        const uniqueValues = [...new Set(data.map(item => item[field] || 'N/A'))].sort();
        const palette = ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00', '#ffff33', '#a65628', '#f781bf', '#999999'];
        const colorMap = {};
        uniqueValues.forEach((val, idx) => colorMap[val] = palette[idx % palette.length]);
        return colorMap;
    },

    createLegend: function(colorMap) {
        if (AppState.legendControl) AppState.map.removeControl(AppState.legendControl);
        AppState.legendControl = L.control({ position: 'bottomright' });
        AppState.legendControl.onAdd = function() {
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML += '<h5>Legenda</h5>';
            for (const key in colorMap) {
                div.innerHTML += `<i style="background:${colorMap[key]}"></i> ${key}<br>`;
            }
            return div;
        };
        AppState.legendControl.addTo(AppState.map);
    },

    toggleRadii: function() {
        const show = document.getElementById('showRadii').checked;
        AppState.circleObjects.forEach(c => show ? c.addTo(AppState.map) : AppState.map.removeLayer(c));
    }
};

// --- MODULE: PolygonManager ---
const PolygonManager = {
    updateFilteredPolygons: function() {
        if (AppState.polygonLayer) {
            AppState.map.removeLayer(AppState.polygonLayer);
            AppState.polygonLayer = null;
        }
        if (!AppState.polygonsData) return;

        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
        const filteredFeatures = selectedStations.includes('all')
            ? AppState.polygonsData.features
            : AppState.polygonsData.features.filter(f => selectedStations.includes(f.properties.delivery_station));

        AppState.polygonLayer = L.geoJSON({ type: "FeatureCollection", features: filteredFeatures }, {
            pane: 'polygonsPane',
            style: f => ({ color: f.properties.cor || '#3388ff', weight: 2, opacity: 0.8, fillOpacity: 0.2 })
        });

        this.updatePolygonPopups();
        if (document.getElementById('showPolygons').checked) {
            AppState.polygonLayer.addTo(AppState.map);
        }
    },

    updatePolygonPopups: function() {
        if (!AppState.polygonLayer || !AppState.allMarkersData) return;
        AppState.polygonLayer.eachLayer(layer => {
            const props = layer.feature.properties;
            const regionname = props.cluster;
            const partnersInRegion = AppState.allMarkersData.filter(p => p.regiao === regionname);
            const activePartners = partnersInRegion.filter(p => p.status === 'Active').length;
            const onboardingPartners = partnersInRegion.filter(p => p.status === 'Onboarding' || p.status === 'BG Checks').length;
            const expected = props.num_points || 0;
            const attainment = expected > 0 ? ((activePartners + onboardingPartners) / expected) * 100 : 0;
            const priority = this.calculatePriority(regionname, props.delivery_station);
            const avgADV = partnersInRegion.length > 0 ? (partnersInRegion.reduce((sum, p) => sum + (p.ADV || 0), 0) / partnersInRegion.length).toFixed(1) : 0;

            const popupContent = `
                <div style="min-width: 200px;">
                    <h6><b>Região:</b> ${regionname}</h6>
                    <p><b>Parceiros Esperados:</b> ${expected}</p>
                    <p><b>Parceiros Ativos:</b> ${activePartners}</p>
                    <p><b>Parceiros em Onboarding:</b> ${onboardingPartners}</p>
                    <p><b>Attainment:</b> ${attainment.toFixed(1)}%</p>
                    <p><b>Prioridade:</b> ${priority}</p>
                    <p><b>ADV Médio:</b> ${avgADV}</p>
                </div>`;
            layer.bindPopup(popupContent);
        });
    },

    calculatePriority: function(regionName, deliveryStation) {
        const polygonsSameStation = AppState.polygonsData.features.filter(f => f.properties.delivery_station === deliveryStation);
        const sorted = polygonsSameStation.map(f => {
            const region = f.properties.cluster;
            const expected = f.properties.num_points || 0;
            const active = AppState.allMarkersData.filter(p => p.regiao === region && p.status === 'Active').length;
            const onboarding = AppState.allMarkersData.filter(p => p.regiao === region && (p.status === 'Onboarding' || p.status === 'BG Checks')).length;
            const attainment = expected > 0 ? (active + onboarding) / expected : 0;
            return { cluster: region, attainment, num_points: expected };
        }).sort((a, b) => a.attainment - b.attainment || b.num_points - a.num_points);

        const idx = sorted.findIndex(f => f.cluster === regionName);
        return idx >= 0 ? idx + 1 : polygonsSameStation.length;
    },

    updateFilteredJurisdiction: function() {
        if (AppState.jurisdictionLayer) {
            AppState.map.removeLayer(AppState.jurisdictionLayer);
            AppState.jurisdictionLayer = null;
        }
        if (!AppState.jurisdictionData) return;

        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
        const filteredFeatures = selectedStations.includes('all')
            ? AppState.jurisdictionData.features
            : AppState.jurisdictionData.features.filter(f => selectedStations.includes(f.properties.delivery_station));

        AppState.jurisdictionLayer = L.geoJSON({ type: "FeatureCollection", features: filteredFeatures }, {
            pane: 'polygonsPane',
            style: f => ({ color: f.properties.cor || '#6E00B3', weight: 2, opacity: 0.8, fillOpacity: 0.2 }),
            onEachFeature: (features, layer) => layer.bindPopup(features.properties.delivery_station)
        });

        if (document.getElementById('showJurisdictions').checked) {
            AppState.jurisdictionLayer.addTo(AppState.map);
        }
    },

    togglePolygons: function() {
        this.updateFilteredPolygons();
    },

    toggleJurisdictons: function(){
        this.updateFilteredJurisdiction();
    }
};

// --- MODULE: UIManager ---
const UIManager = {
    toggleMenu: function() {
        const menu = document.getElementById("menuOptions");
        menu.style.display = (menu.style.display === "block") ? "none" : "block";
    },

    togglePanelContent: function(headerElement) {
        const content = headerElement.nextElementSibling;
        const icon = headerElement.querySelector('i.fas.fa-chevron-down, i.fas.fa-chevron-up');
        content.classList.toggle('collapsed');
        if (icon) {
            icon.classList.toggle('fa-chevron-down');
            icon.classList.toggle('fa-chevron-up');
        }
    },

    updatePeriodInfo: function(period) {
        document.getElementById('periodInfo').textContent = (period.start && period.end)
            ? `Período dos Dados: ${period.start} a ${period.end}`
            : "Período dos dados não especificado.";
    },

    populateFilters: function() {
        const initiatives = [...new Set(AppState.allMarkersData.map(m => m.hub_delivey_initiatives).filter(Boolean))].sort();
        const stations = [...new Set(AppState.allMarkersData.map(m => m.delivery_station).filter(Boolean))].sort();
        const initiativesFilter = document.getElementById('initiativesFilter');
        const stationFilter = document.getElementById('stationFilter');
        initiatives.forEach(p => initiativesFilter.innerHTML += `<option value="${p}">${p}</option>`);
        stations.forEach(s => stationFilter.innerHTML += `<option value="${s}">${s}</option>`);
    },

    setupAutocomplete: function() {
        const fromInput = document.getElementById('routeFromInput');
        const toInput = document.getElementById('routeToInput');
        const searchInput = document.getElementById('search-input');
        const resultsContainer = document.getElementById('autocomplete-results');

        const createAutocomplete = (inputElement, onSelect) => {
            inputElement.addEventListener('input', () => {
                const query = inputElement.value.toLowerCase();
                if (query.length < 2) {
                    resultsContainer.style.display = 'none';
                    return;
                }
                const filtered = AppState.allMarkersData.filter(p => (p.name && p.name.toLowerCase().includes(query)) || (p.store_id && p.store_id.toLowerCase().includes(query))).slice(0, 5);
                resultsContainer.innerHTML = '';
                if (filtered.length > 0) {
                    filtered.forEach(partner => {
                        const item = document.createElement('a');
                        item.href = '#';
                        item.className = 'list-group-item list-group-item-action py-1';
                        item.innerText = `${partner.name} (${partner.store_id})`;
                        item.onclick = e => { e.preventDefault(); onSelect(partner); resultsContainer.style.display = 'none'; };
                        resultsContainer.appendChild(item);
                    });
                    const rect = inputElement.getBoundingClientRect();
                    resultsContainer.style.top = `${rect.bottom + window.scrollY}px`;
                    resultsContainer.style.left = `${rect.left + window.scrollX}px`;
                    resultsContainer.style.width = `${rect.width}px`;
                    resultsContainer.style.display = 'block';
                } else {
                    resultsContainer.style.display = 'none';
                }
            });
        };

        createAutocomplete(searchInput, partner => {
            searchInput.value = '';
            this.searchPartner(partner.store_id);
        });
        createAutocomplete(fromInput, partner => {
            fromInput.value = partner.name;
            document.getElementById('routeFromId').value = partner.store_id;
        });
        createAutocomplete(toInput, partner => {
            toInput.value = partner.name;
            document.getElementById('routeToId').value = partner.store_id;
        });

        document.addEventListener('click', e => {
            if (!resultsContainer.contains(e.target) && e.target !== fromInput && e.target !== toInput && e.target !== searchInput) {
                resultsContainer.style.display = 'none';
            }
        });
    },

    searchPartner: function(partnerId) {

        const searchTerm = partnerId || document.getElementById('search-input').value.toLowerCase();
        if (!searchTerm) return;
        const foundData = AppState.allMarkersData.find(data => 
            (data.store_id && data.store_id.toLowerCase() === searchTerm) ||
            (data.name && data.name.toLowerCase().includes(searchTerm))
        );

        if (foundData) {
            const markerOnMap = AppState.markerObjects.find(m => m.markerData.store_id === foundData.store_id);
            if (markerOnMap) {
                MapManager.onMarkerClick({ target: markerOnMap });
            } else {
                AppState.map.setView([foundData.lat, foundData.lon], 15);
                alert("Parceiro encontrado, mas não está visível com os filtros atuais.");
            }
        } else {
            alert("Parceiro não encontrado.");
        }

        if(!partnerId) document.getElementById('search-input').value = '';
    },

    getMarkerPopupContent: function(data) {
        return `
            ${data.popup}
            <hr class="my-2">
            <button class="btn btn-info btn-sm btn-block" onclick="UIManager.showComparisonInPopup(event, '${data.store_id}')">
                <i class="fas fa-chart-bar"></i> Mostrar Métricas e Comparações
            </button>
            <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event, '${data.store_id}', '${data.name.replace(/'/g, "\\'")}')">
                <i class="fas fa-route"></i> Rota a Partir Daqui
            </button>
        `;
    },

    showComparisonInPopup: function(event, storeId) {
        event.stopPropagation();
        const marker = AppState.markerObjects.find(m => m.markerData.store_id === storeId);
        if (!marker) return;
        const data = marker.markerData;
        const mainStoreData = marker.markerData.main_store_data;
        const overlaps = marker.markerData.overlap_data || [];
        const station = data.delivery_station;
        const partnersInStation = AppState.allMarkersData.filter(p => p.delivery_station === station && p.status === 'Active');
        const stationADV = partnersInStation.length > 0 ? partnersInStation.reduce((sum, p) => sum + p.ADV, 0) / partnersInStation.length : 0;

        let tableHtml = '<div class="table-responsive"><table class="comparison-table">';
        tableHtml += '<tr><th>Métrica</th><th class="main-store">Loja Atual</th>';
        overlaps.slice(0, 4).forEach(o => tableHtml += `<th>Overlap ${o.overlap_id}<br><small>${o.store_id}</small></th>`);
        tableHtml += '</tr>';

        const metrics = [
            { name: 'Raio (m)', key: 'radius', higher_is_better: true },
            { name: 'Total de Pacotes Alocados', key: 'total_packages_allocated', higher_is_better: true },
            { name: 'ADV', key: 'ADV', higher_is_better: true },
            { name: 'Capacidade', key: 'partner_capacity', higher_is_better: true },
            { name: 'Pacotes Elegíveis', key: 'eligible_packages', higher_is_better: true },
            { name: 'Dias de Trabalho', key: 'working_days', higher_is_better: true },
            { name: 'Dias Capacidade Atingida (%)', key: 'capped_days', higher_is_better: false },
            { name: 'Overlaps', key: 'overlapping_count', higher_is_better: false }
        ];

        metrics.forEach(metric => {
            const mainValue = mainStoreData[metric.key] ?? 'N/A';
            tableHtml += `<tr><td><b>${metric.name}</b></td><td class="main-store">${mainValue}</td>`;
            overlaps.slice(0, 4).forEach(overlap => {
                const overlapValue = overlap[metric.key] ?? 'N/A';
                let className = '';
                if (mainValue !== 'N/A' && overlapValue !== 'N/A') {
                    const isBetter = metric.higher_is_better ? (parseFloat(overlapValue) > parseFloat(mainValue)) : (parseFloat(overlapValue) < parseFloat(mainValue));
                    const isWorse = metric.higher_is_better ? (parseFloat(overlapValue) < parseFloat(mainValue)) : (parseFloat(overlapValue) > parseFloat(mainValue));
                    if (isBetter) className = 'better-value';
                    if (isWorse) className = 'worse-value';
                }
                tableHtml += `<td class="${className}">${overlapValue}</td>`;
            });
            tableHtml += '</tr>';
        });
        tableHtml += '</table></div>';

        const popupContent = `
            <h6><strong>${data.name}</strong></h6>
            <p><strong>ADV:</strong> ${(data.ADV).toFixed(0)} (Média Estação: ${(stationADV).toFixed(0)})</p>
            <hr>
            <div>
                <p><strong>DCR:</strong> ${(data.main_store_data.dcr * 100).toFixed(1)}% | <strong>DEA:</strong> ${(data.main_store_data.dea * 100).toFixed(1)}% | <strong>EAD:</strong> ${(data.main_store_data.ead * 100).toFixed(1)}%</p>
            </div>
            <hr>
            <h6><strong>Comparativo Com Parceiros Próximos</strong></h6>
        `;

        const fullPopupContent = `${popupContent}${tableHtml}`;
        marker.setPopupContent(fullPopupContent);
        if (!marker.isPopupOpen()) marker.openPopup();
    },

    // --- Stats Panel Logic ---
    formatNumber(num) {
        return new Intl.NumberFormat('pt-BR', { useGrouping: true }).format(num);
    },

    updateActiveStatsTab: function() {
        const activeTabEl = document.querySelector('#stats-inner-panel .nav-link.active');
        if (activeTabEl) {
            const activeTab = activeTabEl.getAttribute('href').substring(1);
            this.updateStats(activeTab);
        }
    },

    updateStats: function(activeTab) {
        if (activeTab === 'Performance') this.updatePerformanceStats();
        else if (activeTab === 'Expansion') this.updateExpansionStats();
        else if (activeTab === 'Routes') this.updateRoutesStats();
    },

    createCard: function(title, value, goal, container) {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `<h3>${title}</h3><p class="metric-value">${value}</p>`;
        if (goal > 0) {
            card.classList.add(parseFloat(value) >= goal ? 'positive' : 'negative');
        }
        container.appendChild(card);
    },

    updatePerformanceStats: function() {
        const data = AppState.currentFilteredData;
        const container = document.getElementById('performance-cards');
        container.innerHTML = '';

        const working_days =  Math.round(Math.abs((new Date(AppState.period.start) - new Date(AppState.period.end)) / (24 * 60 * 60 * 1000))) + 1;
        const activePartners = data.filter(p => p.status === 'Active').length;
        const advOverall = activePartners > 0 ? data.filter(p => p.status === 'Active').reduce((sum, p) => sum + (p.ADV || 0), 0) / activePartners : 0;
        const dispatchedPackages = this.formatNumber(data.reduce((sum, p) => sum + (p.main_store_data?.dispatched_packages || 0), 0))
        const deliveredPackages = this.formatNumber(data.reduce((sum, p) => sum + (p.main_store_data?.delivered_packages || 0), 0))
        const mean = (arr) => arr.length > 0 ? arr.reduce((sum, v) => sum + v, 0) / arr.length : 0;
        const eadMean = mean(data.filter(p => p.status === 'Active').map(p => p.main_store_data?.ead ?? 0));
        const deaMean = mean(data.filter(p => p.status === 'Active').map(p => p.main_store_data?.dea ?? 0));
        const dcrMean = mean(data.filter(p => p.status === 'Active').map(p => p.main_store_data?.dcr ?? 0));
        const fddsMean = mean(data.filter(p => p.status === 'Active').map(p => p.main_store_data?.fdds ?? 0));
        const ftdsMean = mean(data.filter(p => p.status === 'Active').map(p => p.main_store_data?.ftds ?? 0));

        const goals = { activePartners: 600, advOverall: 40, dispatchedPackages:activePartners*40*working_days, deliveredPackages:(activePartners*40*0.985) , dea: 98.5, ead: 98.5, dcr: 96, fdds: 97.0, ftds: 98.5};

        this.createCard('Parceiros Ativos', activePartners, goals.activePartners, container);
        this.createCard('ADV Médio', advOverall.toFixed(0), goals.advOverall, container);
        this.createCard('Dispatched Packages', dispatchedPackages, goals.dispatchedPackages, container);
        this.createCard('Delivered Packages', deliveredPackages, goals.deliveredPackages, container);
        this.createCard('EAD', `${(eadMean.toFixed(1)*100)}%`, goals.ead, container);
        this.createCard('DEA', `${(deaMean.toFixed(1)*100)}%`, goals.dea, container);
        this.createCard('DCR', `${(dcrMean.toFixed(1)*100)}%`, goals.dcr, container);
        this.createCard('FDDS', `${(fddsMean.toFixed(1)*100)}%`, goals.fdds, container);
        this.createCard('FTDS', `${(ftdsMean.toFixed(1)*100)}%`, goals.ftds, container);

        const tableData = data.map(p => ({...p, ...p.main_store_data}));
        new Tabulator("#performance-table", {
            data: tableData, layout: "fitColumns", height: "400px", placeholder: "Nenhum dado para exibir com os filtros atuais.",
            columns: [
                { title: "Store ID", field: "store_id"}, 
                { title: "Store Name", field: "name", width: 200},
                { title: "D. Station", field: "delivery_station" }, 
                { title: "ADV", field: "ADV" },
                { title: "Dispatched Packages", field: "dispatched_packages"},
                { title: "Delivered Packages", field: "delivered_packages"},
                { title: "DEA", field: "dea"},
                { title: "EAD", field: "ead"},
                { title: "DCR", field: "dcr"},
                { title: "FDDS", field: "fdds"},
                { title: "FTDS", field: "ftds"},
            ],
        });
    },

    updateExpansionStats: function() {
        const container = document.getElementById('expansion-cards');
        container.innerHTML = '';

        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
        const stationAllSelected = selectedStations.includes('all');

        const filteredPolygons = stationAllSelected
            ? AppState.polygonsData.features
            : AppState.polygonsData.features.filter(poly => selectedStations.includes(poly.properties.delivery_station));

        const data = AppState.currentFilteredData;
        const polygonStats = filteredPolygons.map(poly => {
            const region = poly.properties.cluster;
            const partnersInRegion = data.filter(p => p.regiao === region);
            const active = partnersInRegion.filter(p => p.status === 'Active').length;
            const onboarding = partnersInRegion.filter(p => p.status === 'Onboarding' || p.status === 'BG Checks').length;
            const expected = poly.properties.num_points || 0;
            const attainment = expected > 0 ? (active + onboarding) / expected : 0;
            return {
                polygon: region,
                delivery_station: poly.properties.delivery_station,
                active_partners: active,
                onboarding_partners: onboarding,
                total_expected: expected,
                attainment: (attainment * 100).toFixed(1) + '%',
                priority: 0
            };
        });

        const stationsInView = [...new Set(polygonStats.map(p => p.delivery_station))];
        stationsInView.forEach(station => {
            const stationPolygons = polygonStats.filter(p => p.delivery_station === station);
            stationPolygons.sort((a, b) => parseFloat(a.attainment) - parseFloat(b.attainment) || b.total_expected - a.total_expected);
            stationPolygons.forEach((poly, index) => poly.priority = index + 1);
        });

        const totalExpected = filteredPolygons.reduce((sum, poly) => sum + (poly.properties.num_points || 0), 0);
        const totalActive = data.filter(p => p.status === 'Active').length;
        const totalOnboarding = data.filter(p => p.status === 'Onboarding' || p.status === 'BG Checks').length;
        const overallAttainment = totalExpected > 0 ? ((totalActive + totalOnboarding) / totalExpected) * 100 : 0;

        this.createCard('Total Esperado', totalExpected, 0, container);
        this.createCard('Parceiros Ativos', totalActive, 85, container);
        this.createCard('Parceiros Onboarding', totalOnboarding, 25, container);
        this.createCard('Attainment Geral', overallAttainment.toFixed(1) + '%', 80, container);

        new Tabulator("#expansion-table", {
            data: polygonStats,
            layout: "fitColumns",
            height: "400px",
            placeholder: "Nenhum dado para exibir com os filtros atuais.",
            columns: [
                { title: "Polígono", field: "polygon" },
                { title: "D. Station", field: "delivery_station" },
                { title: "Ativos", field: "active_partners" },
                { title: "Onboarding", field: "onboarding_partners" },
                { title: "Esperado", field: "total_expected" },
                { title: "Attainment", field: "attainment" },
                { title: "Prioridade", field: "priority" },
            ],
        });
    },


    updateRoutesStats: function() {
        const container = document.getElementById('routes-cards');
        container.innerHTML = '';

        const supplyRuns = [...new Set(AppState.currentFilteredData.map(p => p.supply_run).filter(Boolean))];
        const routesData = supplyRuns.map(run => {
            const partnersInRoute = AppState.currentFilteredData.filter(p => p.supply_run === run);
            const station = partnersInRoute[0]?.delivery_station;
            const activePartners = partnersInRoute.filter(p => p.status === 'Active').length;
            const onboardingPartners = partnersInRoute.filter(p => p.status === 'Onboarding').length;
            const totalPackages = partnersInRoute.reduce((sum, p) => sum + (p.main_store_data?.dispatched_packages || 0), 0);
            const workingDays = Math.max(1, ...partnersInRoute.map(p => p.main_store_data?.working_days || 0));
            const spr = totalPackages / workingDays;
            const costPerRun = AppState.COST_PER_SUPPLY_RUN[station] || AppState.COST_PER_SUPPLY_RUN.DEFAULT;
            const totalCost = costPerRun * workingDays;
            const cpp = totalPackages > 0 ? totalCost / totalPackages : 0;
            const hcpHostPartners = partnersInRoute.filter(p => p.hub_delivey_initiatives === 'HCP Host Partner').length;
            const hcpPickupPartners = partnersInRoute.filter(p => p.hub_delivey_initiatives === 'HCP Pick Up Partner').length;
            return { route: run, delivery_station: station, active_partners: activePartners, onboarding_partners: onboardingPartners, spr: spr.toFixed(0), cpp: cpp.toFixed(2), hcpHostPartners: hcpHostPartners, hcpPickupPartners: hcpPickupPartners };
        });

        const hcpHostPartners = AppState.currentFilteredData.filter(p => p.hub_delivey_initiatives === 'HCP Host Partner' && p.status === 'Active' && p.HCP_rate_card === 'Tier 1').length;
        const hcpPickupPartners = AppState.currentFilteredData.filter(p => p.hub_delivey_initiatives === 'HCP Pick Up Partner' && p.status === 'Active' && p.HCP_rate_card === 'Tier 1').length;
        const goalHCPHostPartner = AppState.currentFilteredData.filter(p => p.status === 'Active').length * 0.12;
        const goalHCPPickupPartner = goalHCPHostPartner * 4;
        const avgSpr = routesData.length > 0 ? routesData.reduce((sum, r) => sum + parseFloat(r.spr), 0) / routesData.length : 0;
        const avgCpp = routesData.length > 0 ? routesData.reduce((sum, r) => sum + parseFloat(r.cpp), 0) / routesData.length : 0;
        const avgHCPPickupPerHost = hcpHostPartners === 0 ? 0 : (hcpPickupPartners/hcpHostPartners).toFixed(0);

        this.createCard('Total de Rotas', supplyRuns.length, 0, container);
        this.createCard('SPR Médio', avgSpr.toFixed(0), 480, container);
        this.createCard('CPP Médio', `R$ ${avgCpp.toFixed(2)}`, 2.5, container);
        this.createCard('HCP Host Partners', hcpHostPartners, goalHCPHostPartner.toFixed(0), container);
        this.createCard('HCP Pick-up Partners', hcpPickupPartners, goalHCPPickupPartner.toFixed(0), container);
        this.createCard('Média Pick-up por HCP Host Partner', avgHCPPickupPerHost, 4, container)

        new Tabulator("#routes-table", {
            data: routesData, layout: "fitColumns", height: "400px", placeholder: "Nenhum dado para exibir com os filtros atuais.",
            columns: [
                { title: "Rota", field: "route" },
                { title: "D. Station", field: "delivery_station" },
                { title: "Ativos", field: "active_partners" },
                { title: "Onboarding", field: "onboarding_partners" },
                { title: "HCP Host Partners", field: "hcpHostPartners" },
                { title: "HCP Pick-up Partners", field: "hcpPickupPartners" },
                { title: "SPR", field: "spr" },
                { title: "CPP", field: "cpp", formatter:c=>`R$ ${c.getValue()}` },
            ],
        });
    }
};

// --- MODULE: HighlightManager ---
const HighlightManager = {
    highlightStores: function() {
        const criteria = {
            eligibleOp: document.getElementById('eligiblePackagesOp').value,
            eligibleVal: parseFloat(document.getElementById('eligiblePackagesVal').value) || 0,
            allocatedOp: document.getElementById('allocatedCurrentOp').value,
            allocatedVal: parseFloat(document.getElementById('allocatedCurrentVal').value) || 0,
            statusHighlight: document.getElementById('statusHighlightFilter').value,
            overlappingOp: document.getElementById('overlappingOp').value,
            overlappingVal: parseFloat(document.getElementById('overlappingVal').value) || 0
        };

        this.resetHighlight();

        AppState.markerObjects.forEach((marker, index) => {
            if (this.matchesCriteria(marker.markerData, criteria)) {
                if (!marker.options.icon) {
                    const newMarker = L.marker(marker.getLatLng(), { icon: AppState.highlightIcon });
                    newMarker.markerData = marker.markerData;
                    AppState.map.removeLayer(marker);
                    newMarker.addTo(AppState.map);
                    AppState.markerObjects[index] = newMarker;
                    AppState.highlightedMarkers.push(newMarker);
                }
            }
        });

        UIManager.updateActiveStatsTab();

        if (AppState.highlightedMarkers.length > 0) {
            const group = new L.featureGroup(AppState.highlightedMarkers);
            AppState.map.fitBounds(group.getBounds().pad(0.1));
        }
    },

    matchesCriteria: function(data, criteria) {
        const { eligibleOp, eligibleVal, allocatedOp, allocatedVal, statusHighlight, overlappingOp, overlappingVal } = criteria;
        const eligible_packages = parseFloat(data.eligible_packages) || 0;
        const allocated_current = parseFloat(data.ADV) || 0;
        const overlapping_count = parseFloat(data.overlapping_count) || 0;

        const statusMatch = statusHighlight === 'all' || data.status === statusHighlight;
        const eligibleMatch = (eligibleVal <= 0) || (eligibleOp === 'gt' ? eligible_packages > eligibleVal : eligible_packages < eligibleVal);
        const allocatedMatch = (allocatedVal <= 0) || (allocatedOp === 'gt' ? allocated_current > allocatedVal : allocated_current < allocatedVal);
        let overlappingMatch = true;
        if (overlappingVal > 0 || overlappingOp === 'eq') {
            if (overlappingOp === 'gt') overlappingMatch = overlapping_count > overlappingVal;
            else if (overlappingOp === 'lt') overlappingMatch = overlapping_count < overlappingVal;
            else overlappingMatch = Math.abs(overlapping_count - overlappingVal) < 0.001;
        }

        return statusMatch && eligibleMatch && allocatedMatch && overlappingMatch;
    },

    resetHighlight: function() {
        DataManager.applyFilters();
    }
};

// --- MODULE: RouteManager ---
const RouteManager = {
    generateRoute: function() {
        const fromId = document.getElementById('routeFromId').value;
        const toId = document.getElementById('routeToId').value;
        if (!fromId || !toId) { alert("Selecione origem e destino."); return; }
        const fromData = AppState.allMarkersData.find(m => m.store_id === fromId);
        const toData = AppState.allMarkersData.find(m => m.store_id === toId);
        if (!fromData || !toData) { alert("Parceiro inválido."); return; }
        this.clearRoute();
        AppState.routingControl = L.Routing.control({
            waypoints: [L.latLng(fromData.lat, fromData.lon), L.latLng(toData.lat, toData.lon)],
            routeWhileDragging: true,
            router: L.Routing.osrmv1({ serviceUrl: 'https://router.project-osrm.org/route/v1' }),
            createMarker: () => null,
            lineOptions: { styles: [{color: 'blue', opacity: 0.8, weight: 5}] }
        }).addTo(AppState.map);
    },

    clearRoute: function() {
        if (AppState.routingControl) {
            AppState.map.removeControl(AppState.routingControl);
            AppState.routingControl = null;
        }
        document.getElementById('routeFromInput').value = "";
        document.getElementById('routeToInput').value = "";
        document.getElementById('routeFromId').value = "";
        document.getElementById('routeToId').value = "";
    },

    startRouteFromHere: function(event, storeId, storeName) {
        event.stopPropagation();
        document.getElementById('routeFromId').value = storeId;
        document.getElementById('routeFromInput').value = storeName;
        $('#controlTabs a[href="#route-content"]').tab('show');
        document.getElementById('routeToInput').focus();
        AppState.map.closePopup();
    }
};

// --- INITIALIZATION & EVENT LISTENERS ---

document.addEventListener('DOMContentLoaded', () => {
    MapManager.initialize();
    DataManager.loadAllDataAndInitialize();

    // Panel Toggles
    document.querySelectorAll('.panel-header').forEach(header => {
        header.addEventListener('click', () => UIManager.togglePanelContent(header));
    });

    // Main Controls
    document.getElementById('search-btn').addEventListener('click', () => UIManager.searchPartner());
    document.querySelector('.form-search').addEventListener('submit', e => { e.preventDefault(); UIManager.searchPartner(); });
    document.querySelectorAll('input[name="categoryStyle"]').forEach(radio => radio.addEventListener('change', () => MapManager.restyleMarkers()));
    document.getElementById('showRadii').addEventListener('change', () => MapManager.toggleRadii());
    document.getElementById('showPolygons').addEventListener('change', () => PolygonManager.togglePolygons());
    document.getElementById('showJurisdictions').addEventListener('change', () => PolygonManager.toggleJurisdictons());

    // Filter Tab
    document.querySelector('#filter-content button.btn-primary').addEventListener('click', () => DataManager.applyFilters());
    document.querySelector('#filter-content button.btn-secondary').addEventListener('click	', () => DataManager.resetFilters());

    // Highlight Tab
    document.getElementById('highlight-btn').addEventListener('click', () => HighlightManager.highlightStores());
    document.getElementById('highlight-btn-clear').addEventListener('click', () => HighlightManager.resetHighlight());

    // Stats Panel
    const statsPanel = document.getElementById('stats-panel');
    document.getElementById('stats-toggle-button').addEventListener('click', () => {
        statsPanel.classList.toggle('open');
        if (statsPanel.classList.contains('open')) {
            UIManager.updateActiveStatsTab();
        }
    });
    document.getElementById('close-stats-panel').addEventListener('click', () => statsPanel.classList.remove('open'));
    $('#stats-inner-panel a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
        const activeTab = $(e.target).attr('href').replace('#', '');
        UIManager.updateStats(activeTab);
    });
});

