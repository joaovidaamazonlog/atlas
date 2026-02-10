/* FrontEnd/script.js */

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
            this.applyFilters();
            this.optimizationDataAggregate();

            console.log("Todos os dados foram carregados e inicializados.");
        }).catch(error => {
            alert('Não foi possível carregar os arquivos de dados iniciais: ' + error.message);
            console.error(error);
        });
    },

    optimizationDataAggregateActive: function() {
        if (!AppState.optimizationData) return null;
        AppState.allMarkersData.filter(p => p.status === "Active").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
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
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "BG Checks").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
                partner.decision = optimizationInfo.properties.decision;
                partner.optimization = {
                    "radius_suggestion": optimizationInfo.properties.radius_suggestion,
                    "cap_suggestion": optimizationInfo.properties.cap_suggestion
                };
            }
        });
        AppState.allMarkersData.filter(p => p.status === "Prospect").forEach(partner => {
            const optimizationInfo = AppState.optimizationData.features.find(f => f.properties.store_id === partner.store_id)
            if (optimizationInfo) {
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
        const statusFilter = document.getElementById('statusFilter');
        const selectedStatuses = Array.from(statusFilter.selectedOptions).map(opt => opt.value);
        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
        const initiativesFilter = document.getElementById('initiativesFilter').value;
        const supplyRun = document.getElementById('supplyRun').value;
        const jurisdictionFilter = document.getElementById('jurisdictionFilter').value;
        const stationAllSelected = selectedStations.includes('all');
        const statusAllSelected = selectedStatuses.includes('all');

        AppState.currentFilteredData = AppState.allMarkersData.filter(marker => {
            const statusMatch = statusAllSelected || selectedStatuses.includes(marker.status);
            const stationMatch = stationAllSelected || selectedStations.includes(marker.delivery_station);
            let initiativesMatch = true;
            if (initiativesFilter !== 'all') {
                if (initiativesFilter === 'null') {
                    initiativesMatch = (
                        marker.hub_delivey_initiatives === null ||
                        marker.hub_delivey_initiatives === undefined ||
                        marker.hub_delivey_initiatives === '' ||
                        marker.hub_delivey_initiatives === 'N/A'
                    );
                } else {
                    initiativesMatch = marker.hub_delivey_initiatives === initiativesFilter;
                }
            }
            const jurisdictionMatch = jurisdictionFilter === 'all' || marker.jurisdiction_type === jurisdictionFilter;
            const supplyRunMatch = supplyRun === 'all' || marker.supply_run === supplyRun;
            return statusMatch && stationMatch && initiativesMatch && jurisdictionMatch && supplyRunMatch;
        });

        MapManager.createMarkersDeliveryStations();
        MapManager.createMarkers(AppState.currentFilteredData, true);
        PolygonManager.updateFilteredPolygons();
        PolygonManager.updateFilteredJurisdiction();
        UIManager.updateActiveStatsTab();
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

    createMarkersDeliveryStations: function() {
        AppState.deliveryStations.forEach(ds => {
            const marker = L.marker([ds.lat, ds.lon], { icon: AppState.houseIcon });
            marker.bindPopup(`<b>${ds.nome}</b>`);
            marker.addTo(AppState.map);
        });
    },

    createMarkers: function(dataToRender, fitToMarkers = false) {
        this.clearMarkers();
        dataToRender.forEach(data => {
            const marker = L.circleMarker([data.lat, data.lon], { radius: 7, color: 'orange', weight: 1.5, fillOpacity: 0.9 });
            marker.markerData = data;
            marker.on('click', this.onMarkerClick);
            
            if (data.tooltip) {
                marker.bindTooltip(data.tooltip, { direction: 'top', sticky: true, className: 'custom-tooltip' });
            }
            
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
        const data = marker.markerData;

        AppState.map.setView(marker.getLatLng(), 15);

        // Caso especial para otimização
        if (data.decision !== "Optimization suggested" && data.status === "Active") {
            marker.bindPopup(UIManager.getMarkerPopupContentOptimization(data)).openPopup();
            return;
        }

        const STATUS_HANDLERS = new Map([
            ['Inactive', UIManager.getMarkerPopupContentInactive],
            ['Exited', UIManager.getMarkerPopupContentInactive],
            ['Onboarding', UIManager.getMarkerPopupContentOnboarding],
            ['BG Checks', UIManager.getMarkerPopupContentVetting],
            ['Prospect', UIManager.getMarkerPopupContentProspect],
            ['Active', UIManager.getMarkerPopupContentActive]
        ]);

        // Busca handler pelo status
        const handler = STATUS_HANDLERS.get(data.status);
        if (handler) {
            marker.bindPopup(handler(data)).openPopup();
        }
    },

    toggleOptimizationBtn: function() {
        const partnerInfo = document.getElementById('partnerInfo');
        const optimizationInfo = document.getElementById('optimizationInfo');
        const toggleBtn = document.getElementById('toggleOptBtn');
        
        if (partnerInfo.style.display !== 'none') {
            // Mostrar otimização
            partnerInfo.style.display = 'none';
            optimizationInfo.style.display = 'block';
            toggleBtn.innerHTML = '⬅️ Voltar';
            toggleBtn.classList.remove('btn-warning');
            toggleBtn.classList.add('btn-secondary');
        } else {
            // Mostrar informações do parceiro
            partnerInfo.style.display = 'block';
            optimizationInfo.style.display = 'none';
            toggleBtn.innerHTML = '🚀 Otimização Disponível';
            toggleBtn.classList.remove('btn-secondary');
            toggleBtn.classList.add('btn-warning');
        }
    },

    restyleMarkers: function() {
        const primary = document.getElementById('primaryStyle').value;
        const secondary = document.getElementById('secondaryStyle').value;

        // Gera mapa de cores para o parâmetro da borda
        const borderColorMap = this.generateColorMap(AppState.currentFilteredData, primary, null, true);

        // Gera mapa de cores para o parâmetro do preenchimento
        let fillColorMap = {};
        if (secondary && secondary !== primary) {
            fillColorMap = this.generateColorMap(AppState.currentFilteredData, secondary);
        }

        AppState.markerObjects.forEach(marker => {
            const borderKey = marker.markerData[primary] || 'N/A';
            const borderColor = borderColorMap[borderKey] || '#FF1493';
            let borderWeight = 3;

            let fillColor = '#fff';
            if (secondary && secondary !== primary) {
                const fillKey = marker.markerData[secondary] || 'N/A';
                fillColor = fillColorMap[fillKey] || '#808080';
            }

            marker.setStyle({
                fillColor: fillColor,
                color: borderColor,
                weight: borderWeight,
                fillOpacity: 0.9
            });

            const circle = AppState.circleObjects.find(c => c.markerData.store_id === marker.markerData.store_id);
            if (circle) circle.setStyle({ color: borderColor });
        });

        this.createLegend(fillColorMap, borderColorMap, primary, secondary);
    },

    generateColorMap: function(data, field, _unused = null, isBorder = false) {
        const keys = data.map(item => item[field] || 'N/A');
        const uniqueKeys = [...new Set(keys)].sort();
        
        const palette = isBorder
            ? ['#FF1493', '#FF9800', '#009688', '#3F51B5', '#E91E63', '#8BC34A', '#FFC107', '#00BCD4', '#9C27B0', '#CDDC39']
            : [
                '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00',
                '#ffff33', '#a65628', '#f781bf', '#999999', '#66c2a5',
                '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f'
            ];
        const colorMap = {};
        uniqueKeys.forEach((val, idx) => colorMap[val] = palette[idx % palette.length]);
        return colorMap;
    },

    createLegend: function(fillColorMap, borderColorMap, primary, secondary) {
        if (AppState.legendControl) AppState.map.removeControl(AppState.legendControl);
        AppState.legendControl = L.control({ position: 'bottomright' });
        AppState.legendControl.onAdd = function() {
            const div = L.DomUtil.create('div', 'info legend');
            div.innerHTML += '<h5>Legenda</h5>';
            div.innerHTML += `<b>Borda (${primary}):</b><br>`;
            for (const key in borderColorMap) {
                div.innerHTML += `<i style="background:#fff;border:3.5px solid ${borderColorMap[key]}"></i> ${key}<br>`;
            }
            if (secondary && fillColorMap && Object.keys(fillColorMap).length > 0) {
                div.innerHTML += `<hr style="margin:4px 0;"><b>Preenchimento (${secondary}):</b><br>`;
                for (const key in fillColorMap) {
                    div.innerHTML += `<i style="background:${fillColorMap[key]};border:1.5px solid #222"></i> ${key}<br>`;
                }
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
    updateFilteredPolygons: function () {
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

    optimizationSelection: {
        selectedPolygons: new Set(),
        tooltipDiv: null,
        _mousemoveHandler: null,
        _layerClickHandlers: new Map(),

        enableSelection() {
            if (!AppState.optimizationLayer) return;
            this.selectedPolygons.clear();

            // Remove tooltip se já existir
            this._removeTooltip();

            // Cria tooltip
            this.tooltipDiv = document.createElement('div');
            this.tooltipDiv.setAttribute('role', 'tooltip');
            this.tooltipDiv.setAttribute('aria-live', 'polite');
            this.tooltipDiv.style.position = 'fixed';
            this.tooltipDiv.style.background = '#fff';
            this.tooltipDiv.style.border = '1px solid #333';
            this.tooltipDiv.style.padding = '6px 12px';
            this.tooltipDiv.style.borderRadius = '6px';
            this.tooltipDiv.style.boxShadow = '0 2px 8px #0002';
            this.tooltipDiv.style.pointerEvents = 'none';
            this.tooltipDiv.style.zIndex = 99999;
            this.tooltipDiv.style.display = 'none';
            // Botão de fechar para acessibilidade
            const closeBtn = document.createElement('button');
            closeBtn.innerHTML = '&times;';
            closeBtn.style.position = 'absolute';
            closeBtn.style.top = '2px';
            closeBtn.style.right = '6px';
            closeBtn.style.background = 'none';
            closeBtn.style.border = 'none';
            closeBtn.style.fontSize = '1.2em';
            closeBtn.style.cursor = 'pointer';
            closeBtn.setAttribute('aria-label', 'Fechar tooltip');
            closeBtn.onclick = (e) => {
                e.stopPropagation();
                this.selectedPolygons.clear();
                this._removeTooltip();
                this._resetPolygonStyles();
            };
            this.tooltipDiv.appendChild(closeBtn);
            document.body.appendChild(this.tooltipDiv);

            // Remove event listeners antigos
            this._removeLayerEvents();

            // Adiciona evento de seleção aos polígonos
            AppState.optimizationLayer.eachLayer(layer => {
                const clickHandler = (e) => {
                    const id = L.stamp(layer);
                    if (this.selectedPolygons.has(id)) {
                        this.selectedPolygons.delete(id);
                        layer.setStyle({ weight: 1, fillOpacity: 0.3 });
                    } else {
                        this.selectedPolygons.add(id);
                        layer.setStyle({ weight: 3, fillOpacity: 0.6 });
                    }
                    // Use e.originalEvent ou, se não existir, use o último mousemove
                    this.updateTooltip(e.originalEvent || window._lastMouseEvent);
                };
                const mousemoveHandler = (e) => {
                    window._lastMouseEvent = e.originalEvent;
                    this.updateTooltip(e.originalEvent);
                };
                layer.off('click').on('click', clickHandler);
                layer.off('mousemove').on('mousemove', mousemoveHandler);
                this._layerClickHandlers.set(layer, { clickHandler, mousemoveHandler });
            });

            // Evento global para esconder tooltip quando não houver seleção
            if (this._mousemoveHandler) document.removeEventListener('mousemove', this._mousemoveHandler);
            this._mousemoveHandler = (e) => {
                window._lastMouseEvent = e;
                if (this.selectedPolygons.size > 0) {
                    this.updateTooltip(e);
                } else {
                    this._removeTooltip();
                    this._resetPolygonStyles();
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
            this._resetPolygonStyles();
        },

        updateTooltip(mouseEvent) {
            // Se o tooltip foi removido, recria
            if (!this.tooltipDiv) {
                this.tooltipDiv = document.createElement('div');
                this.tooltipDiv.setAttribute('role', 'tooltip');
                this.tooltipDiv.setAttribute('aria-live', 'polite');
                this.tooltipDiv.style.position = 'fixed';
                this.tooltipDiv.style.background = '#fff';
                this.tooltipDiv.style.border = '1px solid #333';
                this.tooltipDiv.style.padding = '6px 12px';
                this.tooltipDiv.style.borderRadius = '6px';
                this.tooltipDiv.style.boxShadow = '0 2px 8px #0002';
                this.tooltipDiv.style.pointerEvents = 'none';
                this.tooltipDiv.style.zIndex = 99999;
                this.tooltipDiv.style.display = 'none';
                // Botão de fechar
                const closeBtn = document.createElement('button');
                closeBtn.innerHTML = '&times;';
                closeBtn.style.position = 'absolute';
                closeBtn.style.top = '2px';
                closeBtn.style.right = '6px';
                closeBtn.style.background = 'none';
                closeBtn.style.border = 'none';
                closeBtn.style.fontSize = '1.2em';
                closeBtn.style.cursor = 'pointer';
                closeBtn.setAttribute('aria-label', 'Fechar tooltip');
                closeBtn.onclick = (e) => {
                    e.stopPropagation();
                    this.selectedPolygons.clear();
                    this._removeTooltip();
                    this._resetPolygonStyles();
                };
                this.tooltipDiv.appendChild(closeBtn);
                document.body.appendChild(this.tooltipDiv);
            }
            if (this.selectedPolygons.size === 0) {
                this.tooltipDiv.style.display = 'none';
                return;
            }
            // Fallback para último evento de mouse conhecido
            if (!mouseEvent && window._lastMouseEvent) mouseEvent = window._lastMouseEvent;
            // Soma demanda total dos selecionados
            let soma = 0;
            let count = 0;
            AppState.optimizationLayer.eachLayer(layer => {
                if (this.selectedPolygons.has(L.stamp(layer))) {
                    soma += layer.feature.properties['demanda_total'] || 0;
                    count++;
                }
            });
            // Atualiza conteúdo, mantendo o botão de fechar
            this.tooltipDiv.innerHTML = `<button style="position:absolute;top:2px;right:6px;background:none;border:none;font-size:1.2em;cursor:pointer;" aria-label="Fechar tooltip" onclick="PolygonManager.optimizationSelection.clearSelection(event)">&times;</button>
                <b>Selecionados:</b> ${count}<br><b>Soma demanda total:</b> ${soma}`;
            this.tooltipDiv.style.display = 'block';
            if (mouseEvent) {
                this.tooltipDiv.style.left = (mouseEvent.clientX + 16) + 'px';
                this.tooltipDiv.style.top = (mouseEvent.clientY + 16) + 'px';
            }
        },

        clearSelection(e) {
            if (e) e.stopPropagation();
            this.selectedPolygons.clear();
            this._removeTooltip();
            this._resetPolygonStyles();
        },

        _removeTooltip() {
            if (this.tooltipDiv) {
                this.tooltipDiv.remove();
                this.tooltipDiv = null;
            }
        },

        _removeLayerEvents() {
            if (!AppState.optimizationLayer) return;
            AppState.optimizationLayer.eachLayer(layer => {
                const handlers = this._layerClickHandlers.get(layer);
                if (handlers) {
                    layer.off('click', handlers.clickHandler);
                    layer.off('mousemove', handlers.mousemoveHandler);
                }
            });
            this._layerClickHandlers.clear();
        },

        _resetPolygonStyles() {
            if (!AppState.optimizationLayer) return;
            AppState.optimizationLayer.eachLayer(layer => {
                layer.setStyle({ weight: 1, fillOpacity: 0.3 });
            });
        }
    },

    updatePolygonPopups: function () {
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

    calculatePriority: function (regionName, deliveryStation) {
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

    updateFilteredJurisdiction: function () {
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

    renderOptimizationLayer: function () {
        if (AppState.optimizationLayer) {
            AppState.map.removeLayer(AppState.optimizationLayer);
            AppState.optimizationLayer = null;
        }

        if (!AppState.optimizationData) {
            console.error("Dados de otimização não encontrados em AppState.");
            return;
        }

        const stationFilter = document.getElementById('stationFilter');
        const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);

        const filteredFeatures = selectedStations.includes('all')
            ? AppState.optimizationData.features.filter(f => f.geometry.type === 'Polygon')
            : AppState.optimizationData.features.filter(f => (selectedStations.includes(f.properties.delivery_station) && f.geometry.type === 'Polygon'));

        const maxDemanda = Math.max(...filteredFeatures.map(f => f.properties['demanda_total'] || 0));
        function getColor(demanda) {
            if (maxDemanda === 0) return '#e74c3c';
            const t = Math.max(0, Math.min(1, demanda / maxDemanda));
            const r = Math.round(231 + (46 - 231) * t);
            const g = Math.round(76 + (204 - 76) * t);
            const b = Math.round(60 + (113 - 60) * t);
            return `rgb(${r},${g},${b})`;
        }

        AppState.optimizationLayer = L.geoJSON({ type: "FeatureCollection", features: filteredFeatures }, {
            pane: 'polygonsPane',
            style: f => ({
                color: getColor(f.properties['demanda_total']),
                weight: 1,
                fillOpacity: 0.3
            }),
        });

        if (document.getElementById('showOptimizationLayer').checked) {
            AppState.optimizationLayer.addTo(AppState.map);
        }
    },

    togglePolygons: function () {
        this.updateFilteredPolygons();
    },

    toggleJurisdictons: function () {
        this.updateFilteredJurisdiction();
    },

    toggleOptimizationLayer: function () {
        this.renderOptimizationLayer();
        if (AppState.optimizationLayer) {
            PolygonManager.optimizationSelection.enableSelection();
        } else {
            PolygonManager.optimizationSelection.disableSelection();
        }
    },

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
        document.getElementById('periodInfo').textContent = period
            ? `Última Atualização: ${period}`
            : "Período dos dados não especificado.";
    },

    populateFilters: function() {
        const stations = [...new Set(AppState.allMarkersData.map(m => m.delivery_station).filter(Boolean))].sort();
        const supplyRunsFilter = document.getElementById('supplyRun');
        const stationFilter = document.getElementById('stationFilter');
        const initiativesFilter = document.getElementById('initiativesFilter');

        stationFilter.innerHTML = '';
        supplyRunsFilter.innerHTML = '';
        initiativesFilter.innerHTML = '';

        stationFilter.innerHTML += `<option value="all" selected>Todos</option>`;
        stations.forEach(s => stationFilter.innerHTML += `<option value="${s}">${s}</option>`);
        supplyRunsFilter.innerHTML += `<option value="all">Todos</option>`;

        // Preencher iniciativas dinamicamente
        const initiativesRaw = AppState.allMarkersData.map(m => m.hub_delivey_initiatives);
        const initiativesSet = new Set();
        let hasNullInitiative = false;
        initiativesRaw.forEach(i => {
            if (i === null || i === undefined || i === '' || i === 'N/A') {
                hasNullInitiative = true;
            } else {
                initiativesSet.add(i);
            }
        });
        const initiatives = Array.from(initiativesSet).sort();
        initiativesFilter.innerHTML += `<option value="all" selected>Todos</option>`;
        initiatives.forEach(i => initiativesFilter.innerHTML += `<option value="${i}">${i}</option>`);
        if (hasNullInitiative) {
            initiativesFilter.innerHTML += `<option value="null">Não alocado</option>`;
        }

        // Função para atualizar supply runs dinamicamente
        function updateSupplyRunsOptions() {
            const selectedStations = Array.from(stationFilter.selectedOptions).map(opt => opt.value);
            let filteredSupplyRuns;
            if (selectedStations.includes('all')) {
                filteredSupplyRuns = [...new Set(AppState.allMarkersData.map(m => m.supply_run).filter(Boolean))];
            } else {
                filteredSupplyRuns = [...new Set(
                    AppState.allMarkersData
                        .filter(m => selectedStations.includes(m.delivery_station))
                        .map(m => m.supply_run)
                        .filter(Boolean)
                )];
            }
            supplyRunsFilter.innerHTML = `<option value="all">Todos</option>`;
            filteredSupplyRuns.forEach(s => supplyRunsFilter.innerHTML += `<option value="${s}">${s}</option>`);
        }

        // Atualiza supply runs ao mudar a seleção de Delivery Station
        stationFilter.addEventListener('change', updateSupplyRunsOptions);

        updateSupplyRunsOptions();
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
                const allOptions = [
                    ...AppState.allMarkersData.map(p => ({
                        type: 'partner',
                        name: p.name,
                        store_id: p.store_id,
                        lat: p.lat,
                        lon: p.lon
                    })),
                    ...AppState.deliveryStations.map(ds => ({
                        type: 'station',
                        name: ds.nome,
                        store_id: ds.nome,
                        lat: ds.lat,
                        lon: ds.lon
                    }))
                ];
                const filtered = allOptions.filter(opt =>
                    (opt.name && opt.name.toLowerCase().includes(query)) ||
                    (opt.store_id && opt.store_id.toLowerCase().includes(query))
                ).slice(0, 5);
                resultsContainer.innerHTML = '';
                if (filtered.length > 0) {
                    filtered.forEach(opt => {
                        const item = document.createElement('a');
                        item.href = '#';
                        item.className = 'list-group-item list-group-item-action py-1';
                        item.innerHTML = opt.type === 'station'
                            ? `<i class="fas fa-home mr-1"></i> ${opt.name} (Delivery Station)`
                            : `${opt.name} (${opt.store_id})`;
                        item.onclick = e => { e.preventDefault(); onSelect(opt); resultsContainer.style.display = 'none'; };
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
            searchInput.value = partner.name;
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

        if (!foundData) {
            const ds = AppState.deliveryStations.find(ds =>
                ds.nome.toLowerCase() === searchTerm);
            if (ds) {
                AppState.map.setView([ds.lat, ds.lon], 13);
                return;
            }else {
                alert("Parceiro ou Delivery Station não encontrado.");
                return;
                }
        } 

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

    getMarkerPopupContentActive: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Launch Date:</b></td>
                                <td style="width:60%">${data.launch_date}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Initiatives:</b></td>
                                <td style="width:60%">${data.hub_delivey_initiatives}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Host Partner:</b></td>
                                <td style="width:60%">${data.HCP_host_partner}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Rate Card:</b></td>
                                <td style="width:60%">${data.HCP_rate_card}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Radius:</b></td>
                                <td style="width:60%">${data.radius} m</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Capacity:</b></td>
                                <td style="width:60%">${data.capacity} pkgs</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                    <br>
                    Enviar mensagem 
                    <a href="https://wa.me/${data.telefone}" target="_blank">
                        <i class="fa fa-whatsapp" style="font-size:24px"></i>
                    </a>
                </div>
                <hr class="my-2">
                
                <!-- Div para Botões de Ação -->
                <div class="partner-actions">
                    <button class="btn btn-info btn-sm btn-block" onclick="UIManager.requestAssistence(event, '${data.store_id}', radius=5)">
                        <i class="fas fa-phone"></i> Solicitar Resgate
                    </button>
                    <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event, '${data.store_id}', '${data.name.replace(/'/g, "\\'")}')">
                        <i class="fas fa-route"></i> Rota a Partir Daqui
                    </button>
                </div>
            </div>
        `;
    },
    
    getMarkerPopupContentInactive: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                    <br>
                    Enviar mensagem 
                    <a href="https://wa.me/${data.telefone}" target="_blank">
                        <i class="fa fa-whatsapp" style="font-size:24px"></i>
                    </a>
                </div>
                <hr class="my-2">

                <!-- Div para sugestões de cap, raio e decisão -->
                <div class="partner-actions">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Decisão:</b></td>
                                <td style="width:60%">${data.decision}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Capacidade Sugerida:</b></td>
                                <td style="width:60%">${data.cap_suggestion} pkgs</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Raio Sugerido:</b></td>
                                <td style="width:60%">${data.radius_suggestion} m</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    },

    getMarkerPopupContentOnboarding: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Launch Date:</b></td>
                                <td style="width:60%">${data.launch_date}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Initiatives:</b></td>
                                <td style="width:60%">${data.hub_delivey_initiatives}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Host Partner:</b></td>
                                <td style="width:60%">${data.HCP_host_partner}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Rate Card:</b></td>
                                <td style="width:60%">${data.HCP_rate_card}</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                    <br>
                    Enviar mensagem 
                    <a href="https://wa.me/${data.telefone}" target="_blank">
                        <i class="fa fa-whatsapp" style="font-size:24px"></i>
                    </a>
                </div>

                <hr class="my-2">

                <div class="partner-actions">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Capacidade Sugerida:</b></td>
                                <td style="width:60%">${data.cap_suggestion} pkgs</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Raio Sugerido:</b></td>
                                <td style="width:60%">${data.radius_suggestion} m</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Div para Botões de Ação -->
                <div class="partner-actions">
                    <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event, '${data.store_id}', '${data.name.replace(/'/g, "\\'")}')">
                        <i class="fas fa-route"></i> Rota a Partir Daqui
                    </button>
                </div>
            </div>
        `;
    },

    getMarkerPopupContentVetting: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Launch Date:</b></td>
                                <td style="width:60%">${data.launch_date}</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                    <br>
                    Enviar mensagem 
                    <a href="https://wa.me/${data.telefone}" target="_blank">
                        <i class="fa fa-whatsapp" style="font-size:24px"></i>
                    </a>
                </div>

                <hr class="my-2">

                <div class="partner-actions">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Capacidade Sugerida:</b></td>
                                <td style="width:60%">${data.cap_suggestion} pkgs</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Raio Sugerido:</b></td>
                                <td style="width:60%">${data.radius_suggestion} m</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    },

    getMarkerPopupContentProspect: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                </div>
                <hr class="my-2">

                <!-- Div para sugestões de cap, raio e decisão -->
                <div class="partner-actions">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Decisão:</b></td>
                                <td style="width:60%">${data.decision}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Capacidade Sugerida:</b></td>
                                <td style="width:60%">${data.cap_suggestion} pkgs</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Raio Sugerido:</b></td>
                                <td style="width:60%">${data.radius_suggestion} m</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    },

    getMarkerPopupContentOptimization: function(data) {
        return `
            <div style="width: 300px; max-height: auto; font-size: 12px;">
                <!-- Div para o Nome do Parceiro -->
                <div class="partner-header">
                    <h5 style="font-weight: bold;">${data.name}</h5>
                </div>
                <div class="partner-info" id="partnerInfo">
                    <table style="width:100%">
                        <tbody>
                            <tr>
                                <td style="width:40%"><b>Store ID:</b></td>
                                <td style="width:60%">${data.store_id}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Status:</b></td>
                                <td style="width:60%">${data.status}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Delivery Station:</b></td>
                                <td style="width:60%">${data.delivery_station}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Launch Date:</b></td>
                                <td style="width:60%">${data.launch_date}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Initiatives:</b></td>
                                <td style="width:60%">${data.hub_delivey_initiatives}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Host Partner:</b></td>
                                <td style="width:60%">${data.HCP_host_partner}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>HCP Rate Card:</b></td>
                                <td style="width:60%">${data.HCP_rate_card}</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Radius:</b></td>
                                <td style="width:60%">${data.radius} m</td>
                            </tr>
                            <tr>
                                <td style="width:40%"><b>Capacity:</b></td>
                                <td style="width:60%">${data.capacity} pkgs</td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <hr class="my-2">

                    <a href="https://dsp-portal.lightning.force.com/lightning/r/Account/${data.salesforce_id}/view" target="_blank">
                        View in Salesforce <i class="fab fa-salesforce" style="font-size:24px"></i>
                    </a>
                    <br>
                    Enviar mensagem 
                    <a href="https://wa.me/${data.telefone}" target="_blank">
                        <i class="fa fa-whatsapp" style="font-size:24px"></i>
                    </a>
                </div>

                <!-- Div para Otimização (oculta inicialmente) -->
                <div class="opt-slide-content" id="optimizationInfo" style="display: none; padding: 10px; height: auto; min-width: 100%;">
                    <h5 style="font-weight:bold;">Otimização de Raio</h5>
                    <table style="width:100%; font-size:12px;">
                        <tbody>
                            <tr>
                                <td><b>Raio Sugerido:</b></td>
                                <td>${data.optimization.radius_suggestion} m</td>
                            </tr>
                        </tbody>
                    </table>
                    <hr>
                    <h5 style="font-weight:bold;">Otimização de Capacidade</h5>
                    <table style="width:100%; font-size:12px;">
                        <tbody>
                            <tr>
                                <td><b>Capacidade Sugerida:</b></td>
                                <td>${data.optimization.cap_suggestion} pkgs</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                
                <hr class="my-2">
                
                <!-- Div para Botões de Ação -->
                <div class="partner-actions">
                    <button class="btn btn-warning btn-sm btn-block mb-1" id="toggleOptBtn" onclick="MapManager.toggleOptimizationBtn()">
                        🚀 Otimização Disponível
                    </button>
                    <button class="btn btn-info btn-sm btn-block" onclick="UIManager.requestAssistence(event, '${data.store_id}', radius=5)">
                        <i class="fas fa-phone"></i> Solicitar Resgate
                    </button>
                    <button class="btn btn-primary btn-sm btn-block" onclick="RouteManager.startRouteFromHere(event, '${data.store_id}', '${data.name.replace(/'/g, "\\'")}')">
                        <i class="fas fa-route"></i> Rota a Partir Daqui
                    </button>
                </div>
            </div>
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
    },

    async requestAssistence(event, storeId, radius = 5) {
        event.stopPropagation();

        const marker = AppState.markerObjects.find(m => m.markerData.store_id === storeId);
        if (!marker) return;
        
        const data = marker.markerData;
        const center = [marker.getLatLng().lng, marker.getLatLng().lat];
        const region = turf.circle(center, radius, { steps: 32, units: "kilometers" });
        const activePartners = AppState.allMarkersData.filter(p => {
            const point = turf.point([p.lon, p.lat]);
            return p.status === 'Active' && p.store_id !== storeId && turf.booleanPointInPolygon(point, region);
        });

        const allCoordinates = activePartners.map(p => [p.lon, p.lat]);
        allCoordinates.push([marker.getLatLng().lng, marker.getLatLng().lat]);
        const osrmUrl = `https://router.project-osrm.org/table/v1/driving/${allCoordinates.map(coord => coord.join(',')).join(';')}?annotations=distance`;
        const response = await fetch(osrmUrl);
        
        if (!response.ok) {
            console.error('Erro ao consultar OSRM:', response.statusText);
            return;
        }

        const dataOSRM = await response.json();
        const distances = {};

        activePartners.forEach((partner, index) => {
            const distanceInMeters = dataOSRM.distances[index][allCoordinates.length - 1];
            const distanceInKm = (distanceInMeters / 1000).toFixed(2);
            distances[partner.store_id] = { partner, distance: distanceInKm };
        });

        const sortedPartners = Object.values(distances)
            .sort((a, b) => parseFloat(a.distance) - parseFloat(b.distance))
            .slice(0, 10);

        const bonus_value = sortedPartners.map(({ distance }) => {
            if (distance <= 2) {
                return 30;
            } else if (distance <= 5) {
                return 40;
            } else {
                return 50;
            }
        });

        let html = `
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <b>Sugestões para resgate</b>
                <button onclick="document.getElementById('assistence-suggestions-popup').remove()" style="border:none;background:none;font-size:1.3em;line-height:1;">&times;</button>
            </div>
            <div style="overflow-y:auto;max-height:750px;padding-top:8px;">
        `;

        sortedPartners.forEach(({ partner, distance }, index) => {
            html += `<p><b>${partner.name}</b>
                    <br><b>Distância:</b> ${distance} km
                    <br><b>Bônus sugerido:</b> R$ ${bonus_value[index]}</p>
                    <br><a href="https://wa.me/${partner.telefone}" target="_blank"><i class="fa fa-whatsapp" style="font-size:24px"></i></a>
                    <hr class="my-2">`;
        });

        html += `</div>`;

        let popup_assistence = document.getElementById('assistence-suggestions-popup') || document.createElement('div');
        popup_assistence.id = 'assistence-suggestions-popup';
        popup_assistence.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;max-width:420px;box-shadow:0 2px 8px #0003;';
        popup_assistence.innerHTML = html;
        document.body.appendChild(popup_assistence);
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
}

// --- MODULE: RouteManager ---
const RouteManager = {
    vehicleMarker: null,
    vehicleAnimation: null,
    stops: [],
    generateRoute: function() {
        // Verifica se já existe uma rota e remove
        if (AppState.routingControl) {
            AppState.map.removeControl(AppState.routingControl);
            AppState.routingControl = null;
        }
        if (this.vehicleMarker) {
            AppState.map.removeLayer(this.vehicleMarker);
            this.vehicleMarker = null;
        }
        if (this.vehicleAnimation) {
            clearInterval(this.vehicleAnimation);
            this.vehicleAnimation = null;
        }

        const fromId = document.getElementById('routeFromId').value;
        const toId = document.getElementById('routeToId').value;

        let fromData = AppState.allMarkersData.find(m => m.store_id === fromId);
        if (!fromData) fromData = AppState.deliveryStations.find(ds => ds.nome === fromId || ds.store_id === fromId);

        let toData = AppState.allMarkersData.find(m => m.store_id === toId);
        if (!toData) toData = AppState.deliveryStations.find(ds => ds.nome === toId || ds.store_id === toId);

        if (!fromData || !toData) { alert("Parceiro ou Delivery Station inválido."); return; }

        // Se houver paradas, otimiza a ordem (TSP)
        let stopsOrder = this.stops;
        if (this.stops.length > 1) {
            // Permutação de todas as ordens possíveis
            function permute(arr) {
                if (arr.length <= 1) return [arr];
                let result = [];
                for (let i = 0; i < arr.length; i++) {
                    let rest = permute(arr.slice(0, i).concat(arr.slice(i + 1)));
                    rest.forEach(r => result.push([arr[i]].concat(r)));
                }
                return result;
            }
            function totalDistance(order) {
                let dist = 0;
                let prev = fromData;
                order.forEach(stop => {
                    dist += L.latLng(prev.lat, prev.lon).distanceTo(L.latLng(stop.lat, stop.lon));
                    prev = stop;
                });
                dist += L.latLng(prev.lat, prev.lon).distanceTo(L.latLng(toData.lat, toData.lon));
                return dist;
            }

            const allOrders = permute(this.stops);
            let minDist = Infinity;
            allOrders.forEach(order => {
                const d = totalDistance(order);
                if (d < minDist) {
                    minDist = d;
                    stopsOrder = order;
                }
            });
            // Atualiza a ordem das paradas para refletir a melhor rota
            this.stops = stopsOrder;
            this.renderStopsList();
        }

        const waypoints = [
            L.latLng(fromData.lat, fromData.lon),
            ...stopsOrder.map(s => L.latLng(s.lat, s.lon)),
            L.latLng(toData.lat, toData.lon)
        ];
        AppState.routingControl = L.Routing.control({
            waypoints: waypoints,
            routeWhileDragging: false,
            router: L.Routing.osrmv1({ serviceUrl: 'https://router.project-osrm.org/route/v1' }),
            createMarker: (i, wp) => L.marker(wp.latLng),
            lineOptions: { styles: [{color: 'blue', opacity: 0.8, weight: 5}] }
        }).addTo(AppState.map);
    },

    startRouteFromHere: function(event, storeId, storeName) {
        event.stopPropagation();
        document.getElementById('routeFromId').value = storeId;
        document.getElementById('routeFromInput').value = storeName;
        $('#controlTabs a[href="#route-content"]').tab('show');
        document.getElementById('routeToInput').focus();
        AppState.map.closePopup();
    },

    addStop: function() {
        // Abre autocomplete para selecionar parada
        const NewStop = document.createElement('input');
        NewStop.id = 'inputNewStop';
        NewStop.type = 'text';
        NewStop.className = 'form-control form-control-sm mb-1';
        NewStop.placeholder = 'Pesquisar parada...';
        document.getElementById('stops-list').appendChild(NewStop);

        const self = this;

        // Autocomplete
        const createAutocomplete = (inputElement, onSelect) => {
            const resultsContainer = document.getElementById('autocomplete-results');
            inputElement.addEventListener('input', () => {
                const query = inputElement.value.toLowerCase();
                if (query.length < 2) {
                    resultsContainer.style.display = 'none';
                    return;
                }
                const allOptions = [
                    ...AppState.allMarkersData.map(p => ({
                        type: 'partner',
                        name: p.name,
                        store_id: p.store_id,
                        lat: p.lat,
                        lon: p.lon
                    })),
                    ...AppState.deliveryStations.map(ds => ({
                        type: 'station',
                        name: ds.nome,
                        store_id: ds.nome, // ou ds.store_id se existir
                        lat: ds.lat,
                        lon: ds.lon
                    }))
                ];

                const filtered = allOptions.filter(opt =>
                    (opt.name && opt.name.toLowerCase().includes(query)) ||
                    (opt.store_id && opt.store_id.toLowerCase().includes(query))
                ).slice(0, 5);

                resultsContainer.innerHTML = '';
                if (filtered.length > 0) {
                    filtered.forEach(opt => {
                        const item = document.createElement('a');
                        item.href = '#';
                        item.className = 'list-group-item list-group-item-action py-1';
                        item.innerHTML = opt.type === 'station'
                            ? `<i class="fas fa-home mr-1"></i> ${opt.name} (Delivery Station)`
                            : `${opt.name} (${opt.store_id})`;
                        item.onclick = e => { e.preventDefault(); onSelect(opt); resultsContainer.style.display = 'none'; };
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

        createAutocomplete(NewStop, opt => {
            NewStop.value = opt.name;
            self.stops.push({ store_id: opt.store_id, name: opt.name, lat: opt.lat, lon: opt.lon });
            self.renderStopsList();
            NewStop.remove();
        });
        
    },

    renderStopsList: function() {
        const list = document.getElementById('stops-list');
        list.innerHTML = '';
        const fromId = document.getElementById('routeFromId').value;
        const toId = document.getElementById('routeToId').value;
        const fromData = AppState.allMarkersData.find(m => m.store_id === fromId);
        const toData = AppState.allMarkersData.find(m => m.store_id === toId);

        const routePoints = [];
        if (fromData) routePoints.push({ ...fromData, type: 'origem' });
        this.stops.forEach((stop, idx) => routePoints.push({ ...stop, type: 'parada', idx }));
        if (toData) routePoints.push({ ...toData, type: 'destino' });

        routePoints.forEach((point, idx) => {
            const div = document.createElement('div');
            div.className = 'stop-item d-flex align-items-center mb-1';

            let label = '';
            if (point.type === 'origem') label = `<span class="badge badge-primary mr-2">Origem</span>`;
            else if (point.type === 'destino') label = `<span class="badge badge-success mr-2">Destino</span>`;
            else label = `<span class="badge badge-info mr-2">Parada</span>`;

            div.innerHTML = `
                ${label}
                <span class="stop-name flex-grow-1">${point.name || point.store_id} (${point.store_id})</span>
                ${point.type === 'parada' ? `
                    <button class="btn btn-sm btn-light mx-1" onclick="RouteManager.moveStopUp(${point.idx})"><i class="fas fa-arrow-up"></i></button>
                    <button class="btn btn-sm btn-light mx-1" onclick="RouteManager.moveStopDown(${point.idx})"><i class="fas fa-arrow-down"></i></button>
                    <button class="btn btn-sm btn-danger mx-1" onclick="RouteManager.removeStop(${point.idx})"><i class="fas fa-times"></i></button>
                ` : ''}
            `;
            list.appendChild(div);
        });
    },

    moveStopUp: function(idx) {
        if (idx > 0) {
            [this.stops[idx - 1], this.stops[idx]] = [this.stops[idx], this.stops[idx - 1]];
            this.renderStopsList();
        }
    },

    moveStopDown: function(idx) {
        if (idx < this.stops.length - 1) {
            [this.stops[idx], this.stops[idx + 1]] = [this.stops[idx + 1], this.stops[idx]];
            this.renderStopsList();
        }
    },

    removeStop: function(idx) {
        this.stops.splice(idx, 1);
        this.renderStopsList();
    },

    clearRoute: function() {
        if (AppState.routingControl) {
            AppState.map.removeControl(AppState.routingControl);
            AppState.routingControl = null;
        }
        // Remove caminhão animado
        if (this.vehicleMarker) {
            AppState.map.removeLayer(this.vehicleMarker);
            this.vehicleMarker = null;
        }
        if (this.vehicleAnimation) {
            clearInterval(this.vehicleAnimation);
            this.vehicleAnimation = null;
        }
        document.getElementById('routeFromInput').value = "";
        document.getElementById('routeToInput').value = "";
        document.getElementById('routeFromId').value = "";
        document.getElementById('routeToId').value = "";
        this.stops = [];
        this.renderStopsList();
    },

    // --- HCP Host/Pick-up Suggestion System ---
    getCurrentHcpGroups: function() {
        const all = AppState.currentFilteredData.filter(p => p.status !== 'Exited');
        const hosts = all.filter(p => p.hub_delivey_initiatives === 'HCP Host Partner');
        const pickups = all.filter(p => p.hub_delivey_initiatives === 'HCP Pick Up Partner');
        const heros = all.filter(p => p.hub_delivey_initiatives === 'Hub Hero');
        return { hosts, pickups, heros, all };
    },

    async osrmTableMatrix(coords, sources = null, destinations = null) {
        if (!coords || coords.length === 0) throw new Error("coords empty");
        const coordStr = coords.map(c => `${c.lon},${c.lat}`).join(';');
        const params = new URLSearchParams();
        params.set('annotations', 'distance,duration');
        if (sources && sources.length > 0) params.set('sources', sources.join(';'));
        if (destinations && destinations.length > 0) params.set('destinations', destinations.join(';'));
        const url = `https://router.project-osrm.org/table/v1/driving/${coordStr}?${params.toString()}`;
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error(OSRM `table error ${res.status}`);
            const j = await res.json();
            return { distances: j.distances || null, durations: j.durations || null, raw: j };
        } catch (err) {
            console.error('osrmTableMatrix failed', err);
            throw err;
        }
    },

    extractOsrmResultFromMatrix(matrixDistances, matrixDurations, rowIndex, colIndex) {
        if (!matrixDistances || !matrixDurations) return null;
        const d = matrixDistances[rowIndex]?.[colIndex];
        const t = matrixDurations[rowIndex]?.[colIndex];
        if (d === null || t === null || d === undefined || t === undefined) return null;

        return { distance: d, duration: t };
    },

    async optimizeCurrentPickupsPhase1(groups) {
        // groups: { hosts, pickups, heros, all }
        const hosts = groups.hosts.map(h => ({ ...h, pickups: groups.pickups.filter(p => p.HCP_host_partner === h.name).slice() }));
        const pickups = groups.pickups.slice();
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        if (!AppState.hcpUsedStores[station]) AppState.hcpUsedStores[station] = new Set();
        const used = AppState.hcpUsedStores[station];

        const moves = []; // { pickup, from, to }

        if (pickups.length === 0 || hosts.length === 0) {
            return { hosts, pickups, moves };
        }

        // Build coords: pickups then hosts
        const coords = [];
        pickups.forEach(p => coords.push({ lat: p.lat, lon: p.lon }));
        const hostOffset = coords.length;
        hosts.forEach(h => coords.push({ lat: h.lat, lon: h.lon }));

        const sources = Array.from({ length: pickups.length }, (_, i) => i);
        const destinations = Array.from({ length: hosts.length }, (_, j) => hostOffset + j);

        let matrix;
        try {
            matrix = await this.osrmTableMatrix(coords, sources, destinations);
        } catch (err) {
            console.error('Phase1: osrmTableMatrix failed', err);
            return { hosts, pickups, moves };
        }

        // For each pickup, find nearest valid host (respecting capacity and used set)
        for (let i = 0; i < pickups.length; i++) {
            const pickup = pickups[i];
            // mark used pickups: if already used (e.g., by phase2 or prior), skip
            if (used.has(pickup.store_id)) continue;

            // Create array of host candidates with distance/duration
            const hostCandidates = [];
            for (let j = 0; j < hosts.length; j++) {
            const host = hosts[j];
            const res = this.extractOsrmResultFromMatrix(matrix.distances, matrix.durations, i, j);
            if (!res) continue;
            if (res.distance <= 6000 && res.duration <= 900) {
                // host has capacity?
                const cap = host.pickups ? host.pickups.length : 0;
                if (cap < 5) hostCandidates.push({ hostIdx: j, host, distance: res.distance, duration: res.duration });
            }
            }
            if (hostCandidates.length === 0) continue;
            // sort by distance asc
            hostCandidates.sort((a, b) => a.distance - b.distance);
            // choose first available (nearest)
            const chosen = hostCandidates[0];
            const chosenHost = chosen.host;
            // if different from current assigned host, suggest move
            if (pickup.HCP_host_partner !== chosenHost.name) {
            moves.push({ pickup, from: pickup.HCP_host_partner, to: chosenHost.name });
            }
            // add pickup to chosen host
            if (!chosenHost.pickups) chosenHost.pickups = [];
            // avoid duplicating in chosenHost.pickups
            if (!chosenHost.pickups.some(p => p.store_id === pickup.store_id) && chosenHost.pickups.length < 5) {
            chosenHost.pickups.push(pickup);
            used.add(pickup.store_id);
            }
        }

        return { hosts, pickups, moves };
    },
    
    async allocateHeroesToExistingHostsPhase2(groups, currentHosts) {
        // groups: { hosts, pickups, heros, all }
        // currentHosts: hosts state after phase1 (with pickups arrays updated)
        const hosts = currentHosts.map(h => ({ ...h, pickups: (h.pickups || []).slice() }));
        const heros = groups.heros.slice();
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        if (!AppState.hcpUsedStores[station]) AppState.hcpUsedStores[station] = new Set();
        const used = AppState.hcpUsedStores[station];

        const assignments = []; // { hero, host }

        if (heros.length === 0 || hosts.length === 0) return { hosts, assignments, remainingHeros: heros.slice() };

        // We'll compute matrix heroes x hosts (one call)
        const coords = [];
        heros.forEach(h => coords.push({ lat: h.lat, lon: h.lon }));
        const hostOffset = coords.length;
        hosts.forEach(h => coords.push({ lat: h.lat, lon: h.lon }));

        const sources = Array.from({ length: heros.length }, (_, i) => i);
        const destinations = Array.from({ length: hosts.length }, (_, j) => hostOffset + j);

        let matrix;
        try {
            matrix = await this.osrmTableMatrix(coords, sources, destinations);
        } catch (err) {
            console.error('Phase2: osrmTableMatrix failed', err);
            return { hosts, assignments, remainingHeros: heros.slice() };
        }

        // For each hero, attempt to assign to nearest host with capacity and within constraints
        const remainingHeros = [];
        for (let i = 0; i < heros.length; i++) {
            const hero = heros[i];
            if (used.has(hero.store_id)) continue; // already used
            // build candidates with distance/duration and capacity
            const candidates = [];
            for (let j = 0; j < hosts.length; j++) {
            const host = hosts[j];
            const cap = host.pickups ? host.pickups.length : 0;
            if (cap >= 5) continue;
            const res = this.extractOsrmResultFromMatrix(matrix.distances, matrix.durations, i, j);
            if (!res) continue;
            if (res.distance <= 6000 && res.duration <= 900) {
                candidates.push({ hostIdx: j, host, distance: res.distance, duration: res.duration });
            }
            }
            if (candidates.length === 0) {
            remainingHeros.push(hero);
            continue;
            }
            candidates.sort((a, b) => a.distance - b.distance);
            // choose nearest with available capacity
            let assigned = false;
            for (const cand of candidates) {
            const host = cand.host;
            if (!host.pickups) host.pickups = [];
            if (host.pickups.length < 5) {
                // assign hero -> pickup
                host.pickups.push(hero);
                assignments.push({ hero, host, distance: cand.distance, duration: cand.duration });
                used.add(hero.store_id);
                assigned = true;
                break;
            }
            }
            if (!assigned) remainingHeros.push(hero);
        }

        return { hosts, assignments, remainingHeros };
    },

    async clusterHeroesNewHostsPhase3(groups, currentHosts) {
        // groups: { hosts, pickups, heros, all } - heros should be those remaining after phase2
        // currentHosts: hosts after phase2
        const turf = window.turf;
        const hosts = currentHosts.map(h => ({ ...h, pickups: (h.pickups || []).slice() }));
        const heros = groups.heros.slice();
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        if (!AppState.hcpUsedStores[station]) AppState.hcpUsedStores[station] = new Set();
        const used = AppState.hcpUsedStores[station];

        const newHostSuggestions = []; // { hostCandidate, pickups: [p,...] }

        if (heros.length < 4) return { hosts, newHostSuggestions };

        // Determine k to try clusters ~5
        const k = Math.max(1, Math.ceil(heros.length / 5));
        const fc = turf.featureCollection(heros.map(h => turf.point([h.lon, h.lat], { store_id: h.store_id })));
        let clustered;
        try {
            clustered = turf.clustersKmeans(fc, { numberOfClusters: k });
        } catch (err) {
            console.error('Phase3: turf clustersKmeans failed', err);
            return { hosts, newHostSuggestions };
        }

        // group points
        const clusterMap = new Map();
        clustered.features.forEach(f => {
            const cid = f.properties.cluster;
            if (!clusterMap.has(cid)) clusterMap.set(cid, []);
            clusterMap.get(cid).push(f);
        });

        // process each cluster
        for (const [cid, features] of clusterMap.entries()) {
            let members = features.map(f => heros.find(h => h.store_id === f.properties.store_id)).filter(Boolean);
            if (members.length === 0) continue;

            // reduce >6 by removing farthest
            if (members.length > 6) {
            const fcTmp = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
            const centroidTmp = turf.centroid(fcTmp);
            members.sort((a, b) => {
                const da = turf.distance(centroidTmp, turf.point([a.lon, a.lat]), { units: 'kilometers' });
                const db = turf.distance(centroidTmp, turf.point([b.lon, b.lat]), { units: 'kilometers' });
                return db - da;
            });
            while (members.length > 6) members.shift(); // remove farthest
            }

            // density check: max distance to centroid <= 2.5 km
            const fc2 = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
            const centroid = turf.centroid(fc2);
            let maxDistKm = 0;
            members.forEach(m => {
            const d = turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' });
            if (d > maxDistKm) maxDistKm = d;
            });
            if (maxDistKm > 2.5) continue;
            if (members.length < 4) continue;

            // host candidate = nearest to centroid
            let hostCandidate = null;
            let hostDist = Infinity;
            members.forEach(m => {
            const d = turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' });
            if (d < hostDist) { hostDist = d; hostCandidate = m; }
            });
            if (!hostCandidate) continue;

            // skip if already used as host or suggested
            if (used.has(hostCandidate.store_id)) continue;

            // pickup candidates = members except host
            const pickupCandidates = members.filter(m => m.store_id !== hostCandidate.store_id);
            if (pickupCandidates.length === 0) continue;

            // build coords: pickups then host
            const coords = pickupCandidates.map(p => ({ lat: p.lat, lon: p.lon }));
            const hostIdx = coords.length;
            coords.push({ lat: hostCandidate.lat, lon: hostCandidate.lon });

            const sources = Array.from({ length: pickupCandidates.length }, (_, i) => i);
            const destinations = [hostIdx];

            let matrix;
            try {
            matrix = await this.osrmTableMatrix(coords, sources, destinations);
            } catch (err) {
            console.error('Phase3: osrmTableMatrix failed for cluster', cid, err);
            continue;
            }

            // validate pickups w/ matrix and avoid duplicates
            const validPickups = [];
            for (let r = 0; r < pickupCandidates.length; r++) {
            const p = pickupCandidates[r];
            if (used.has(p.store_id)) continue;
            const res = this.extractOsrmResultFromMatrix(matrix.distances, matrix.durations, r, 0);
            if (res && res.distance <= 6000 && res.duration <= 900) {
                validPickups.push({ p, distance: res.distance, duration: res.duration });
            }
            }

            // sort by distance and limit to 5
            validPickups.sort((a, b) => a.distance - b.distance);
            const finalPickups = validPickups.slice(0, 5).map(x => x.p);

            // host must have at least 3 pickups to be valid new host
            if (finalPickups.length < 3) continue;

            // mark used
            used.add(hostCandidate.store_id);
            finalPickups.forEach(fp => used.add(fp.store_id));

            // set original hdi and set new values (so legend updates)
            if (!hostCandidate._original_hdi) hostCandidate._original_hdi = hostCandidate.hub_delivery_initiatives;
            hostCandidate.hub_delivery_initiatives = 'New Host';
            finalPickups.forEach(fp => {
            if (!fp._original_hdi) fp._original_hdi = fp.hub_delivery_initiatives;
            fp.hub_delivery_initiatives = 'New PickUp';
            });

            // push suggestion
            newHostSuggestions.push({ hostCandidate, pickups: finalPickups });

            // update hosts list so further clusters/allocations see this host as taken (with pickups)
            hosts.push({ ...hostCandidate, pickups: finalPickups.slice() });
        } // end cluster loop

        return { hosts, newHostSuggestions };
    },

    _buildClustersCombinedFromPhases(movesPhase1, phase2Assignments, phase3Suggestions) {
        // returns array of objects { type: 'move'|'new-host'|'new-pickup', host, pickup, from, to }
        const combined = [];
        // Phase1 moves
        movesPhase1.forEach(m => {
            combined.push({ type: 'move', pickup: m.pickup, from: m.from, to: m.to, host: null });
        });
        // Phase2 assignments (hero->host)
        (phase2Assignments || []).forEach(a => {
            combined.push({ type: 'new-pickup', pickup: a.hero, host: a.host });
        });
        // Phase3 suggestions
        (phase3Suggestions || []).forEach(s => {
            // s: { hostCandidate, pickups }
            combined.push({ type: 'new-host', host: s.hostCandidate, pickup: null });
            s.pickups.forEach(p => combined.push({ type: 'new-pickup', host: s.hostCandidate, pickup: p }));
        });
        return combined;
    },

    buildHcpFullReportHtml(movesPhase1, phase2Assignments, phase3Suggestions) {
        let html = `<div style="display:flex;justify-content:space-between;align-items:center;"><b>Sugestões HCP</b><button onclick="document.getElementById('hcp-suggestions-popup')?.remove()" style="border:none;background:none;font-size:1.1em;">&times;</button></div><div style="max-height:700px;overflow:auto;padding-top:8px;">`;

        // Phase1 moves
        html += `<h4 style="margin-top:8px;">Mudanças sugeridas (Pickups atuais)</h4>`;
        if (!movesPhase1 || movesPhase1.length === 0) {
            html += `<div style="margin-left:12px;color:#666;">Nenhuma mudança sugerida para pickups atuais.</div>`;
        } else {
            html += `<ul>`;
            movesPhase1.forEach(m => {
            html += `<li><b>${m.pickup.name}</b> (${m.pickup.store_id}) — mover de <i>${m.from || 'N/A'}</i> para <i>${m.to}</i></li>`;
            });
            html += `</ul>`;
        }

        // Phase2 assignments
        html += `<h4 style="margin-top:8px;">Alocações em hosts existentes (Hero → Pickup)</h4>`;
        if (!phase2Assignments || phase2Assignments.length === 0) {
            html += `<div style="margin-left:12px;color:#666;">Nenhum herói alocado a hosts existentes.</div>`;
        } else {
            html += `<ul>`;
            phase2Assignments.forEach(a => {
            html += `<li><b>${a.hero.name}</b> (${a.hero.store_id}) → Host: <b>${a.host.name}</b> (${a.host.store_id})</li>`;
            });
            html += `</ul>`;
        }

        // Phase3 new hosts/pickups
        html += `<h4 style="margin-top:8px;">Novos Hosts sugeridos / Pickups (por cluster)</h4>`;
        if (!phase3Suggestions || phase3Suggestions.length === 0) {
            html += `<div style="margin-left:12px;color:#666;">Nenhum novo host sugerido por clusterização.</div>`;
        } else {
            phase3Suggestions.forEach((s, idx) => {
            html += `<div style="margin-left:6px;margin-bottom:8px;"><b>Cluster ${idx + 1} — Host sugerido: ${s.hostCandidate.name} (${s.hostCandidate.store_id})</b><ul>`;
            s.pickups.forEach(p => html += `<li>${p.name} (${p.store_id})</li>`);
            html += `</ul></div>`;
            });
        }

        html += `</div>`;
        return html;
    },

    async clusterForExpansion(groups, optimized) {
        const turf = window.turf;
        const hosts = optimized.optimizedHosts ? optimized.optimizedHosts.slice() : [];
        const heros = groups.heros.filter(h => !hosts.some(host => host.store_id === h.store_id) && !optimized.optimizedPickups.some(p => p.store_id === h.store_id));
        const suggestions = [];
        if (!heros || heros.length < 4) return suggestions;

        // used set for this station (prevent duplicates)
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        if (!AppState.hcpUsedStores[station]) AppState.hcpUsedStores[station] = new Set();
        const used = AppState.hcpUsedStores[station];

        // controle local para não sugerir o mesmo pickup/host mais de uma vez
        const suggestedHostIds = new Set();
        const suggestedPickupIds = new Set();

        let k = Math.max(1, Math.ceil(heros.length / 5));
        const fc = turf.featureCollection(heros.map(h => turf.point([h.lon, h.lat], { store_id: h.store_id })));

        let clustered;
        try {
            clustered = turf.clustersKmeans(fc, { numberOfClusters: k });
        } catch (err) {
            console.error('clusterForExpansion – KMEANS falhou', err);
            return suggestions;
        }

        // agrupa por cluster id
        const clusterMap = new Map();
        clustered.features.forEach(f => {
            const cid = f.properties.cluster;
            if (!clusterMap.has(cid)) clusterMap.set(cid, []);
            clusterMap.get(cid).push(f);
        });

        // processa cada cluster
        for (const [cid, features] of clusterMap.entries()) {
            let members = features.map(f => heros.find(h => h.store_id === f.properties.store_id)).filter(Boolean);
            if (members.length === 0) continue;

            // reduzir cluster > 6 removendo os mais distantes do centroid
            if (members.length > 6) {
            const fcTmp = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
            const centroidTmp = turf.centroid(fcTmp);
            members.sort((a, b) => {
                const da = turf.distance(centroidTmp, turf.point([a.lon, a.lat]), { units: 'kilometers' });
                const db = turf.distance(centroidTmp, turf.point([b.lon, b.lat]), { units: 'kilometers' });
                return db - da;
            });
            while (members.length > 6) {
                const removed = members.shift(); // remove mais distante
                // removed permanece hero
            }
            }

            // densidade — max distância ao centroid ≤ 2.5 km
            const fc2 = turf.featureCollection(members.map(m => turf.point([m.lon, m.lat])));
            const centroid = turf.centroid(fc2);
            let maxDistKm = 0;
            members.forEach(m => {
            const d = turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' });
            if (d > maxDistKm) maxDistKm = d;
            });
            if (maxDistKm > 2.5) continue;
            if (members.length < 4) continue;

            // escolher host candidato = mais próximo do centroid
            let hostCandidate = null;
            let hostDist = Infinity;
            members.forEach(m => {
            const d = turf.distance(centroid, turf.point([m.lon, m.lat]), { units: 'kilometers' });
            if (d < hostDist) { hostDist = d; hostCandidate = m; }
            });
            if (!hostCandidate) continue;

            // preparar pickups candidates (exceto host)
            const pickupCandidates = members.filter(m => m.store_id !== hostCandidate.store_id);

            // evitar sugerir host se já usado
            if (used.has(hostCandidate.store_id) || suggestedHostIds.has(hostCandidate.store_id)) {
            // host já sugerido/ocupado - não usá-lo como new-host
            continue;
            }

            if (pickupCandidates.length === 0) continue;

            // monta coords: pickups then host
            const coords = pickupCandidates.map(p => ({ lat: p.lat, lon: p.lon }));
            const hostIdx = coords.length;
            coords.push({ lat: hostCandidate.lat, lon: hostCandidate.lon });

            const sources = Array.from({ length: pickupCandidates.length }, (_, i) => i);
            const destinations = [hostIdx];

            let matrix;
            try {
            matrix = await this.osrmTableMatrix(coords, sources, destinations);
            } catch (err) {
            console.error('clusterForExpansion: osrm table falhou para cluster', cid, err);
            continue;
            }

            // validar pickups via matrix e evitar duplicatas
            const validPickups = [];
            for (let r = 0; r < pickupCandidates.length; r++) {
            const p = pickupCandidates[r];
            if (used.has(p.store_id) || suggestedPickupIds.has(p.store_id)) continue; // já usado
            const res = this.extractOsrmResultFromMatrix(matrix.distances, matrix.durations, r, 0);
            if (res && res.distance <= 6000 && res.duration <= 900) {
                validPickups.push(p);
            }
            }

            // limitar a 5 pickups (host + pickups <= 6)
            const finalPickups = validPickups.slice(0, 5);

            // regra: host deve ter ao menos 3 pickups; caso contrário, desqualifica
            if (finalPickups.length < 3) {
            // não cria host; membros permanecem hero
            continue;
            }

            // total participantes >= 4 (deveria ser) -> ok
            // marca os IDs como sugeridos (no conjunto local e no global used)
            suggestedHostIds.add(hostCandidate.store_id);
            used.add(hostCandidate.store_id);
            finalPickups.forEach(p => { suggestedPickupIds.add(p.store_id); used.add(p.store_id); });

            // salva original hub_delivery_initiatives antes de alterar
            if (!hostCandidate._original_hdi) hostCandidate._original_hdi = hostCandidate.hub_delivery_initiatives;
            hostCandidate.hub_delivery_initiatives = 'New Host';

            suggestions.push({ host: hostCandidate, pickup: null, type: 'new-host' });

            finalPickups.forEach(p => {
            if (!p._original_hdi) p._original_hdi = p.hub_delivery_initiatives;
            p.hub_delivery_initiatives = 'New PickUp';
            suggestions.push({ host: hostCandidate, pickup: p, type: 'new-pickup' });
            });

            // atualiza hosts para evitar uma cluster posterior usar este host como se estivesse livre
            hosts.push({ ...hostCandidate, pickups: finalPickups.slice() });
        } // fim loop clusters

        return suggestions;
    },

    applyHcpSuggestionsToMap: function (optimized, clusters) {
        // Monta sets com os ids sugeridos
        const suggestedHostIds = new Set(clusters.filter(c => c.type === 'new-host').map(c => c.host.store_id));
        const suggestedPickupIds = new Set(clusters.filter(c => c.type === 'new-pickup' && c.pickup).map(c => c.pickup.store_id));

        // Atualiza os dados (hub_delivery_initiatives) na fonte (currentFilteredData) para atualizar a legenda automaticamente
        AppState.currentFilteredData.forEach(item => {
            // salva original caso ainda não salvo
            if (!item._original_hdi) item._original_hdi = item.hub_delivery_initiatives;

            if (suggestedHostIds.has(item.store_id)) item.hub_delivery_initiatives = 'New Host';
            else if (suggestedPickupIds.has(item.store_id)) item.hub_delivery_initiatives = 'New PickUp';
            // se não está nas sugestões, mantemos o atributo (reset será feito em resetHcpSuggestions)
        });

        // Cores dos highlights
        const COLOR_HOST = '#8000FF'; // roxo
        const COLOR_PICK = '#FF1493'; // rosa

        // Itera sobre os marcadores já existentes e altera apenas visual/estados
        AppState.markerObjects.forEach(markerObj => {
            // markerObj pode ser L.CircleMarker, L.Marker, L.LayerGroup, etc.
            const data = markerObj?.markerData ?? null;
            if (!data || !data.store_id) return;

            const id = data.store_id;
            const isNewHost = suggestedHostIds.has(id);
            const isNewPickup = suggestedPickupIds.has(id);

            // REMOVE highlight anterior quando necessário
            if (!isNewHost && !isNewPickup) {
            // Se tiver highlight armazenado, remover e restaurar estilo original
            if (data._hcp_highlight) {
                try { AppState.map.removeLayer(data._hcp_highlight); } catch(e){}
                delete data._hcp_highlight;
            }
            // Se for CircleMarker original e tiver estilo salvo, restaurar
            if (markerObj instanceof L.CircleMarker) {
                if (data._hcp_original_style) {
                markerObj.setStyle(data._hcp_original_style);
                delete data._hcp_original_style;
                }
            }
            return;
            }

            // Se precisa destacar (new host/pickup)
            const color = isNewHost ? COLOR_HOST : COLOR_PICK;

            // Se for CircleMarker (geralmente seus marcadores originais são circleMarker)
            if (markerObj instanceof L.CircleMarker) {
            // Salva estilo original se ainda não salvo
            if (!data._hcp_original_style) {
                data._hcp_original_style = {
                color: markerObj.options.color,
                fillColor: markerObj.options.fillColor,
                fillOpacity: markerObj.options.fillOpacity,
                weight: markerObj.options.weight,
                radius: markerObj.options.radius
                };
            }
            // Aplica novo estilo (mantém radius original)
            markerObj.setStyle({
                color: color,
                fillColor: color,
                fillOpacity: 0.9,
                weight: Math.max(2, (data._hcp_original_style?.weight || 1) + 2)
            });
            // remove highlight layer se existir (não precisamos de overlay para circleMarker)
            if (data._hcp_highlight) { try { AppState.map.removeLayer(data._hcp_highlight); } catch(e){}; delete data._hcp_highlight; }
            } else {
            // Para L.Marker ou L.LayerGroup: criamos/atualizamos um circleMarker de highlight por cima, sem tocar no ícone original.
            // Se já existe highlight, apenas atualiza a cor
            if (data._hcp_highlight && data._hcp_highlight instanceof L.CircleMarker) {
                data._hcp_highlight.setStyle({ color, fillColor: color });
            } else {
                // cria highlight (e salva em data para remoção posterior)
                const highlight = L.circleMarker([data.lat, data.lon], {
                radius: 18,
                color,
                fillColor: color,
                fillOpacity: 0.45,
                weight: 3,
                interactive: false, // para não interferir em eventos
                pane: 'overlayPane'
                });
                data._hcp_highlight = highlight;
                highlight.addTo(AppState.map);
            }
            }

            // OBS: mantemos markerObj.markerData atualizado (já atualizamos item.hub_delivery_initiatives acima)
        });

        try { MapManager.restyleMarkers(); } catch (e) { console.error('restyleMarkers falhou', e);}
    },

    hcpSuggestHostClusters: async function () {
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        if (!AppState.hcpSuggestionCache) AppState.hcpSuggestionCache = {};
        if (!AppState.hcpUsedStores) AppState.hcpUsedStores = {};
        if (!AppState.hcpUsedStores[station]) AppState.hcpUsedStores[station] = new Set();

        const btn = document.getElementById('suggest-routes-btn');

        // Toggle: if cache exists and not active -> show; if active -> hide
        const cache = AppState.hcpSuggestionCache[station];
        if (cache && !AppState.hcpSuggestionsActive) {
            // apply cached changes
            // ensure hub_delivery_initiatives are applied
            (cache.suggestedHosts || []).forEach(id => {
            const it = AppState.currentFilteredData.find(p => p.store_id === id);
            if (it) { if (!it._original_hdi) it._original_hdi = it.hub_delivery_initiatives; it.hub_delivery_initiatives = 'New Host'; }
            });
            (cache.suggestedPickups || []).forEach(id => {
            const it = AppState.currentFilteredData.find(p => p.store_id === id);
            if (it) { if (!it._original_hdi) it._original_hdi = it.hub_delivery_initiatives; it.hub_delivery_initiatives = 'New PickUp'; }
            });

            // apply visual using combined clusters
            this.applyHcpSuggestionsToMap(cache.optimized, cache.clustersCombined || []);

            // show report
            const html = this.buildHcpFullReportHtml(cache.movesPhase1 || [], cache.phase2Assignments || [], cache.phase3Suggestions || []);
            let p = document.getElementById('hcp-suggestions-popup') || document.createElement('div');
            p.id = 'hcp-suggestions-popup';
            p.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;max-width:420px;box-shadow:0 2px 8px #0003;';
            p.innerHTML = html;
            document.body.appendChild(p);

            AppState.hcpSuggestionsActive = true;
            if (btn) { btn.textContent = 'Ocultar Sugestões'; btn.classList.remove('btn-primary'); btn.classList.add('btn-warning'); btn.onclick = () => RouteManager.resetHcpSuggestions(); }
            return;
        }
        if (cache && AppState.hcpSuggestionsActive) {
            // hide (reset visual)
            this.resetHcpSuggestions();
            return;
        }

        // If no cache: compute phases sequentially
        // spinner
        const loading = document.createElement('div');
        loading.id = 'routes-loading';
        loading.style = 'position:fixed;top:0;left:0;width:100vw;height:100vh;background:rgba(0,0,0,0.3);z-index:99999;display:flex;align-items:center;justify-content:center;';
        loading.innerHTML = `<div style="background:#fff;padding:28px;border-radius:8px;"><i class="fas fa-spinner fa-spin mr-2"></i> Calculando sugestões HCP...</div>`;
        document.body.appendChild(loading);

        try {
            const groups = this.getCurrentHcpGroups();

            // Phase 1
            const phase1 = await this.optimizeCurrentPickupsPhase1(groups);
            // phase1.hosts contains updated hosts with pickups

            // Phase 2: allocate heroes to existing hosts
            // note: for phase2 we must recreate groups.heros as those not already used
            const remainingHerosAfterP1 = groups.heros.filter(h => !AppState.hcpUsedStores[station].has(h.store_id));
            const groupsPhase2 = { ...groups, heros: remainingHerosAfterP1 };
            const phase2 = await this.allocateHeroesToExistingHostsPhase2(groupsPhase2, phase1.hosts);

            // Phase 3: cluster remaining heroes (those still unassigned after phase2)
            const remainingHerosAfterP2 = phase2.remainingHeros.filter(h => !AppState.hcpUsedStores[station].has(h.store_id));
            const groupsPhase3 = { ...groups, heros: remainingHerosAfterP2 };
            const phase3 = await this.clusterHeroesNewHostsPhase3(groupsPhase3, phase2.hosts);

            // Build combined clusters for visual & cache
            const clustersCombined = this._buildClustersCombinedFromPhases(phase1.moves, phase2.assignments, phase3.newHostSuggestions);

            // Collect suggested lists for cache
            const suggestedHosts = [];
            const suggestedPickups = [];
            clustersCombined.forEach(c => {
            if (c.type === 'new-host' && c.host) suggestedHosts.push(c.host.store_id);
            if (c.type === 'new-pickup' && c.pickup) suggestedPickups.push(c.pickup.store_id);
            if (c.type === 'move' && c.pickup) {
                // moves not classified as pickup/host but we keep track
                // optionally we could add moved pickup to suggestedPickups
            }
            });

            // Save cache
            AppState.hcpSuggestionCache[station] = {
            optimized: { hosts: phase2.hosts }, // hosts after phase2 (phase3 added new hosts in memory but we saved separate)
            clustersCombined,
            movesPhase1: phase1.moves,
            phase2Assignments: phase2.assignments,
            phase3Suggestions: phase3.newHostSuggestions,
            suggestedHosts,
            suggestedPickups
            };

            // Apply visual modifications and show popup
            this.applyHcpSuggestionsToMap(AppState.hcpSuggestionCache[station].optimized, clustersCombined);

            const html = this.buildHcpFullReportHtml(phase1.moves, phase2.assignments, phase3.newHostSuggestions);
            let p = document.getElementById('hcp-suggestions-popup') || document.createElement('div');
            p.id = 'hcp-suggestions-popup';
            p.style = 'position:fixed;top:80px;right:20px;background:#fff;padding:20px;border-radius:8px;z-index:9999;max-width:420px;box-shadow:0 2px 8px #0003;';
            p.innerHTML = html;
            document.body.appendChild(p);

            AppState.hcpSuggestionsActive = true;
            if (btn) { btn.textContent = 'Ocultar Sugestões'; btn.classList.remove('btn-primary'); btn.classList.add('btn-warning'); btn.onclick = () => RouteManager.resetHcpSuggestions(); }

        } finally {
            document.getElementById('routes-loading')?.remove();
        }
    },

    resetHcpSuggestions: function () {
        const station = AppState.currentFilteredData[0]?.delivery_station || 'UNKNOWN';
        // Restaurar hub_delivery_initiatives originais para todos no filtro
        AppState.currentFilteredData.forEach(p => {
            if (p._original_hdi) {
            p.hub_delivery_initiatives = p._original_hdi;
            delete p._original_hdi;
            }
        });

        // limpa marcadores da camada (mantém tilelayer)
        AppState.map.eachLayer(layer => {
            if (!(layer instanceof L.TileLayer)) {
            AppState.map.removeLayer(layer);
            }
        });

        // Remove popup
        document.getElementById('hcp-suggestions-popup')?.remove();

        // botão volta ao estado "Mostrar / Sugerir"
        const btn = document.getElementById('suggest-routes-btn');
        if (btn) {
            btn.textContent = 'Sugerir HCP Initiatives';
            btn.classList.remove('btn-warning');
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-primary');
            btn.onclick = () => RouteManager.hcpSuggestHostClusters();
        }

        // Marca que sugestões estão inativas (mas cache permanece)
        AppState.hcpSuggestionsActive = false;

        // reconstrói marcadores padrão (reaplica filtros)
        DataManager.applyFilters();
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
    document.getElementById('showOptimizationLayer').addEventListener('change', () => PolygonManager.toggleOptimizationLayer());

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
    document.getElementById('stationFilter').addEventListener('change', function() {
        const selectedStations = Array.from(this.selectedOptions).map(opt => opt.value);
        document.getElementById('suggest-routes-btn').style.display = (selectedStations.length === 1 && selectedStations[0] !== 'all') ? 'block' : 'none';
    });
    document.addEventListener('click', function(e) {
        if (!e.ctrlKey && AppState.selectedGrids) {
            AppState.selectedGrids = [];
            AppState.map.closePopup();
        }
    });
});