/**
 * config.ts
 * =========
 * Constantes e configurações centralizadas da aplicação.
 * Migração fiel de frontend/js/config.js para TypeScript.
 * Nenhum módulo deve ter valores hardcoded — tudo vem daqui.
 */

/** URLs base dos dados estáticos hospedados no GitHub Pages */
const BASE_URL = 'https://joaovidaamazonlog.github.io/atlas/output_data';
const BASE_URL_CFG = 'https://joaovidaamazonlog.github.io/atlas/config';

export interface DataUrls {
  partners: string;
  territories: string;
  jurisdiction: string;
  optimization: string;
  heatmap: string;
  executiveReport: string;
}

export const DATA_URLS: Readonly<DataUrls> = Object.freeze({
  partners: `${BASE_URL}/dados_mapa.json`,
  territories: `${BASE_URL}/territories.geojson`,
  jurisdiction: `${BASE_URL_CFG}/jurisdiction.geojson`,
  optimization: `${BASE_URL}/optimization_data.geojson`,
  heatmap: `${BASE_URL}/heatmap.geojson`,
  executiveReport: `${BASE_URL}/relatorio_executivo.json`,
});

/** Configuração inicial do mapa Leaflet */
export interface MapConfig {
  center: [number, number];
  zoom: number;
  tileUrl: string;
  subdomains: string[];
  maxZoom: number;
}

export const MAP_CONFIG: Readonly<MapConfig> = Object.freeze({
  center: [-14.235, -51.925] as [number, number],
  zoom: 5,
  tileUrl: 'http://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
  subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
  maxZoom: 20,
});

/** Custo por supply run por delivery station (R$) */
export interface CostPerSupplyRun {
  DSP2: number;
  DSP3: number;
  DSP4: number;
  DSP5: number;
  DBH5: number;
  DRJ3: number;
  DGO2: number;
  DBS5: number;
  DES2: number;
  DPE4: number;
  DPB3: number;
  DCE3: number;
  DSA8: number;
  DPR2: number;
  DRS5: number;
  DEFAULT: number;
}

export const COST_PER_SUPPLY_RUN: Readonly<CostPerSupplyRun> = Object.freeze({
  DSP2: 590,
  DSP3: 560,
  DSP4: 600,
  DSP5: 780,
  DBH5: 850,
  DRJ3: 680,
  DGO2: 670,
  DBS5: 550,
  DES2: 1065,
  DPE4: 700,
  DPB3: 750,
  DCE3: 820,
  DSA8: 750,
  DPR2: 1080,
  DRS5: 1060,
  DEFAULT: 600,
});

/** Parâmetros do sistema HCP (Host/Pickup) */
export interface HcpConfig {
  maxPickupsPerHost: number;
  maxDistanceM: number;
  maxDurationS: number;
  minPickupsForNewHost: number;
  clusterDensityKm: number;
  minClusterMembers: number;
  maxClusterMembers: number;
}

export const HCP_CONFIG: Readonly<HcpConfig> = Object.freeze({
  maxPickupsPerHost: 5,
  maxDistanceM: 6000,
  maxDurationS: 900,
  minPickupsForNewHost: 3,
  clusterDensityKm: 2.5,
  minClusterMembers: 4,
  maxClusterMembers: 6,
});

/** URL base da API de prospecção.
 * Em desenvolvimento usa o proxy do Vite (/api-proxy) para contornar CORS.
 * Em produção (build) usa a URL real da API.
 */
export const API_BASE_URL =
  import.meta.env.DEV ? '/api-proxy' : 'https://api-cnpj-br.vercel.app';

/** URL base da API de Geointeligência.
 * Em desenvolvimento usa o proxy do Vite (/geo-intelligence) para contornar CORS.
 * Em produção usa a URL real configurada via VITE_GEO_INTELLIGENCE_API_URL.
 */
export const GEO_INTELLIGENCE_API_BASE_URL: string =
  import.meta.env.DEV
    ? ''  // usa proxy do Vite: /geo-intelligence/* → http://localhost:8001/geo-intelligence/*
    : ((import.meta.env.VITE_GEO_INTELLIGENCE_API_URL as string | undefined) ?? 'http://localhost:8001');

/** Paletas de cores para marcadores */
export interface ColorPalettes {
  border: string[];
  fill: string[];
  hcpHost: string;
  hcpPickup: string;
}

export const COLOR_PALETTES: Readonly<ColorPalettes> = Object.freeze({
  border: [
    '#FF1493',
    '#FF9800',
    '#009688',
    '#3F51B5',
    '#E91E63',
    '#8BC34A',
    '#FFC107',
    '#00BCD4',
    '#9C27B0',
    '#CDDC39',
  ],
  fill: [
    '#e41a1c',
    '#377eb8',
    '#4daf4a',
    '#984ea3',
    '#ff7f00',
    '#ffff33',
    '#a65628',
    '#f781bf',
    '#999999',
    '#66c2a5',
    '#fc8d62',
    '#8da0cb',
    '#e78ac3',
    '#a6d854',
    '#ffd92f',
  ],
  hcpHost: '#8000FF',
  hcpPickup: '#FF1493',
});

/** Metas do painel de performance */
export interface PerformanceGoals {
  activePartners: number;
  advOverall: number;
  dea: number;
  ead: number;
  dcr: number;
  fdds: number;
  ftds: number;
  /** 12% dos ativos devem ser HCP Host */
  hcpHostRatio: number;
  hcpPickupPerHost: number;
  sprMedio: number;
}

export const PERFORMANCE_GOALS: Readonly<PerformanceGoals> = Object.freeze({
  activePartners: 600,
  advOverall: 40,
  dea: 98.5,
  ead: 98.5,
  dcr: 96,
  fdds: 97.0,
  ftds: 98.5,
  hcpHostRatio: 0.12,
  hcpPickupPerHost: 4,
  sprMedio: 480,
});
