/**
 * config.js
 * =========
 * Constantes e configurações centralizadas da aplicação.
 * Nenhum módulo deve ter valores hardcoded — tudo vem daqui.
 */

/** URLs base dos dados estáticos hospedados no GitHub Pages */
const BASE_URL      = 'https://joaovidaamazonlog.github.io/atlas/output_data';
const BASE_URL_CFG  = 'https://joaovidaamazonlog.github.io/atlas/config';

export const DATA_URLS = Object.freeze({
    partners:        `${BASE_URL}/dados_mapa.json`,
    territories:     `${BASE_URL}/territories.geojson`,
    jurisdiction:    `${BASE_URL_CFG}/jurisdiction.geojson`,
    optimization:    `${BASE_URL}/optimization_data.geojson`,
    heatmap:         `${BASE_URL}/heatmap.geojson`,
    gmapsResults:    `${BASE_URL}/gmaps_results.json`,
    executiveReport: `${BASE_URL}/relatorio_executivo.json`,
});

/** Configuração inicial do mapa Leaflet */
export const MAP_CONFIG = Object.freeze({
    center:     [-14.235, -51.925],
    zoom:       5,
    tileUrl:    'http://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
    subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
    maxZoom:    20,
});

/** Custo por supply run por delivery station (R$) */
export const COST_PER_SUPPLY_RUN = Object.freeze({
    DSP2: 590, DSP3: 560, DSP4: 600, DSP5: 780, DBH5: 850, DRJ3: 680,
    DGO2: 670, DBS5: 550, DES2: 1065, DPE4: 700, DPB3: 750, DCE3: 820,
    DSA8: 750, DPR2: 1080, DRS5: 1060, DEFAULT: 600,
});

/** Parâmetros do sistema HCP (Host/Pickup) */
export const HCP_CONFIG = Object.freeze({
    maxPickupsPerHost:   5,
    maxDistanceM:        6000,
    maxDurationS:        900,
    minPickupsForNewHost: 3,
    clusterDensityKm:    2.5,
    minClusterMembers:   4,
    maxClusterMembers:   6,
});

/** URL da API de prospecção (Receita Federal) */
export const CNPJ_API_URL = 'https://api-cnpj-br.vercel.app/api/buscar';

/** Paletas de cores para marcadores */
export const COLOR_PALETTES = Object.freeze({
    border: [
        '#FF1493', '#FF9800', '#009688', '#3F51B5', '#E91E63',
        '#8BC34A', '#FFC107', '#00BCD4', '#9C27B0', '#CDDC39',
    ],
    fill: [
        '#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00',
        '#ffff33', '#a65628', '#f781bf', '#999999', '#66c2a5',
        '#fc8d62', '#8da0cb', '#e78ac3', '#a6d854', '#ffd92f',
    ],
    hcpHost:   '#8000FF',
    hcpPickup: '#FF1493',
});

/** Metas do painel de performance */
export const PERFORMANCE_GOALS = Object.freeze({
    activePartners:  600,
    advOverall:      40,
    dea:             98.5,
    ead:             98.5,
    dcr:             96,
    fdds:            97.0,
    ftds:            98.5,
    hcpHostRatio:    0.12,   // 12% dos ativos devem ser HCP Host
    hcpPickupPerHost: 4,
    sprMedio:        480,
});
