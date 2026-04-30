/**
 * types.ts
 * ========
 * Interfaces TypeScript centrais da aplicação.
 * Usadas pelo Store Zustand e pelos componentes React.
 * Espelha os modelos de frontend/js/models.js com tipagem estrita.
 */

// ---------------------------------------------------------------------------
// OTIMIZAÇÃO / CAP OPPORTUNITY
// ---------------------------------------------------------------------------

export interface AdvOpportunity {
  suggested_lat: number;
  suggested_lon: number;
  suggested_cap: number;
  suggested_radius: number;
  estimated_adv_gain: number;
  distance_from_current: number;
}

export interface CapOpportunityState {
  selectedPartnerId: string | null;
}

export interface HexSelectionState {
  selectedHexIds: string[];
  totalDemandDaily: number;
  totalDemandResidual: number;
}

export interface OptimizationData {
  radius_suggestion: number;
  cap_suggestion: number;
}

// ---------------------------------------------------------------------------
// HEX COVERAGE MODEL
// ---------------------------------------------------------------------------

/**
 * Represents a single partner's allocation share for a heatmap hex.
 * Appears in heatmap feature properties as entries in `covering_partners`.
 */
export interface CoveringPartner {
  salesforce_id: string;
  packages_allocated: number;
  share: number;
}

/**
 * Represents a single hex entry in a partner's coverage list.
 * Stored in `dados_mapa.json` as `partner.hex_coverage`.
 */
export interface HexCoverageEntry {
  hex_id: string;
  packages_allocated: number;
}

// ---------------------------------------------------------------------------
// PARCEIRO
// ---------------------------------------------------------------------------

export type PartnerStatus =
  | 'Active'
  | 'Inactive'
  | 'Onboarding'
  | 'BG Checks'
  | 'Prospect'
  | 'Exited'
  | 'New';

export interface Partner {
  salesforce_id: string;
  store_id: string | null;
  name: string;
  status: PartnerStatus;
  lat: number | null;
  lon: number | null;
  zip_code: string | null;
  city: string | null;
  state: string | null;
  delivery_station: string;
  supply_run: string | null;
  radius: number;
  capacity: number;
  bucket: string | null;
  bucket_ade: string;
  jurisdiction_type: string | null;
  hub_delivey_initiatives: string | null;
  HCP_rate_card: string | null;
  HCP_host_partner: string | null;
  launch_date: string | null;
  exited_date: string | null;
  telefone: string | null;
  owner_id: string | null;
  decision_status: string | null;
  lead_source: string | null;
  tooltip: string;
  regiao: string;
  decision: string;
  reason: string;
  optimization: OptimizationData;
  ceps: string[];
  slot_id: string;
  adv_opportunity: AdvOpportunity | null;
  hex_coverage?: HexCoverageEntry[];
}

// ---------------------------------------------------------------------------
// DELIVERY STATION
// ---------------------------------------------------------------------------

export interface DeliveryStation {
  nome: string;
  lat: number;
  lon: number;
}

// ---------------------------------------------------------------------------
// FILTRO
// ---------------------------------------------------------------------------

export interface FilterState {
  selectedStatuses: string[] | 'all';
  selectedStations: string[] | 'all';
  selectedBuckets: string[] | 'all';
  initiativesFilter: string;
  jurisdictionFilter: string;
}

// ---------------------------------------------------------------------------
// ESTILIZAÇÃO DO MAPA
// ---------------------------------------------------------------------------

export interface StyleConfig {
  /** Campo para cor de preenchimento dos marcadores */
  primaryField: string;
  /** Campo para cor de borda dos marcadores */
  secondaryField: string;
  showRadii: boolean;
  showPolygons: boolean;
  showJurisdictions: boolean;
  showOptimizationLayer: boolean;
  showHeatmap: boolean;
  /** Exibe a camada de Geointeligência (territórios + supply ideal) */
  showGeoIntelligence: boolean;
  /** Campo para colorir os polígonos de território: 'default' | 'delivery_station' | 'attainment' */
  polygonColorField: string;
  /** Exibe o layer que colore cada hex pelo % DSP (Fase 6 — deliveries). */
  showDspShareLayer: boolean;
}

// ---------------------------------------------------------------------------
// ROTA / PARADA
// ---------------------------------------------------------------------------

export interface RouteStop {
  store_id: string;
  name: string;
  lat: number;
  lon: number;
}

// ---------------------------------------------------------------------------
// HCP
// ---------------------------------------------------------------------------

export interface HcpState {
  suggestionCache: Record<string, unknown>;
  usedStores: Record<string, Set<string>>;
  suggestionsActive: boolean;
}

export interface HcpGroups {
  hosts: Partner[];
  pickups: Partner[];
  heros: Partner[];
  all: Partner[];
}

export interface HcpMove {
  pickup: Partner;
  from: string;
  to: string;
  type: 'move';
}

// ---------------------------------------------------------------------------
// PROSPECÇÃO
// ---------------------------------------------------------------------------

export interface ProspectCompany {
  nome: string;
  endereco: string;
  telefone_1: string | null;
  telefone_2: string | null;
  /** @deprecated campo legado Google Maps */
  telefone: string | null;
  site: string;
  google_maps_link: string;
  cep: string;
  tipo: string;
  _fonte: string;
  lat: number | null;
  lon: number | null;
  isMatch: boolean | null;
  contactada: boolean;
  territory_id?: string;
  gridDisk?: number | null;
  matched_slot?: string | null;
}

export interface ProspectCluster {
  centroid: { lat: number; lon: number };
  count: number;
  match_count: number;
  priority: number;
  intensity: number;
  company_indices: number[];
}

export interface ProspectState {
  companies: ProspectCompany[];
  clusters: ProspectCluster[];
  isLoading: boolean;
  error: string | null;
  selectedStation: string | null;
  selectedBucket: string | null;
  /** Keys of pinned companies (serializable array, convert to Set when needed) */
  pinnedKeys: string[];
}

// ---------------------------------------------------------------------------
// RECRUITABLE AREA ANALYSIS
// ---------------------------------------------------------------------------

export type ReasonCode =
  | 'INSUFFICIENT_RESIDUAL_DEMAND'
  | 'NO_HEATMAP_COVERAGE'
  | 'INSUFFICIENT_TOTAL_DEMAND'
  | 'NO_HISTORICAL_DATA';  // área satélite sem histórico de pacotes

export interface EvaluatorResult {
  totalDemand: number;
  residualDemand: number;
  minAdv: number;
  gap: number;
  viable: boolean;
  reason: ReasonCode | null;
  selectedCells: GeoJSON.Feature[];
  residualCells: GeoJSON.Feature[];
  /**
   * Preenchido quando o ponto central está fora de qualquer jurisdição e
   * hexágonos de múltiplas bases foram encontrados no raio.
   * Indica a base vencedora (maior nº de hexes; desempate por demanda residual).
   * A análise usa apenas os hexágonos dessa base.
   */
  outOfJurisdictionStation?: string;
  /**
   * DS dominante (canônica OU satélite) escolhida pelo evaluator.
   * Definido sempre que `selectedCells` não é vazio e há dados de jurisdição.
   * Pode ser um código satélite (ex: "XBA1") — satélites não são mais
   * colapsados na canônica.
   */
  recommendedStation?: string;
  /**
   * Canônica da DS recomendada, quando `recommendedStation` é satélite.
   * Para canônicas puras, fica `undefined`. Usado apenas para renderização
   * do badge "Anexo de …" na UI.
   */
  canonicalBase?: string;
  /**
   * Outras bases presentes no raio além de `recommendedStation`. Quando
   * definido e não vazio, indica disputa de fronteira — a análise usou
   * apenas os hexes de `recommendedStation`, mas o painel deve avisar
   * que o raio tocou as bases listadas aqui.
   */
  competingStations?: string[];
}

export type EvaluatorError =
  | { type: 'MISSING_HEATMAP' }
  | { type: 'MISSING_CENTER' }
  | { type: 'INVALID_PARAMS'; field: string };

export interface RecruitableAnalysisParams {
  centerLat: string;
  centerLon: string;
  radiusMeters: number;
  minAdv: number;
  selectedLeadId: string | null;
}

export interface RecruitableAnalysisState {
  params: RecruitableAnalysisParams;
  result: EvaluatorResult | null;
  error: string | null;
  isStale: boolean;
}

// ---------------------------------------------------------------------------
// CRITÉRIO DE HIGHLIGHT
// ---------------------------------------------------------------------------

export interface HighlightCriteria {
  eligibleOp: 'gt' | 'lt';
  eligibleVal: number;
  allocatedOp: 'gt' | 'lt';
  allocatedVal: number;
  statusHighlight: string;
  overlappingOp: 'gt' | 'lt' | 'eq';
  overlappingVal: number;
}

// ---------------------------------------------------------------------------
// DELIVERIES / CANAL (IHS vs DSP) — Fase 6 do pipeline
// ---------------------------------------------------------------------------

/** Totais agregados por DS. Usado no card de share IHS vs DSP. */
export interface DeliveryStationTotals {
  total: number;
  ihs: number;
  dsp: number;
  other: number;
  ihs_share_pct: number;
  dsp_share_pct: number;
}

/** Entrada diária (1 por date) para uma DS. */
export interface DeliveryDailyEntry {
  date: string;
  ihs: number;
  dsp: number;
  total: number;
}

/** Série temporal diária por DS. */
export type DailyByStation = Record<string, DeliveryDailyEntry[]>;

/**
 * Estatísticas por parceiro (store_id) para a janela da base de pacotes.
 * Dois grupos: parceiros conhecidos (match em dados_mapa.json) e unknown
 * (store_id presente no CSV mas sem cadastro — sinalizados no Dashboard).
 */
export interface PartnerDeliveryStats {
  store_id: string;
  salesforce_id: string | null;
  name: string;
  nome_empresa: string;
  status: string | null;
  canal_dominante: string;
  delivery_station: string;
  bucket_ade: string | null;
  capacity: number;
  radius: number;
  total: number;
  daily_avg: number;
  cap_utilization_pct: number;
  share_ds_pct: number;
  share_ds_ihs_pct: number;
  share_territory_pct: number;
  trend_7d_pct: number;
  daily_series: { date: string; total: number }[];
  is_unknown: boolean;
  /**
   * True quando o parceiro Active/Onboarding está cadastrado com
   * `capacity == 0` OU `radius == 0`. Sinaliza configuração incompleta
   * no Salesforce — o dado é real (parceiro não tem cap ou raio setado)
   * e precisa de ação manual do time de ops. Alimenta o card de warning
   * próprio no Dashboard e isola o parceiro das métricas de performance
   * (cap_utilization, subutilizados).
   */
  cap_misconfigured: boolean;
  lat: number | null;
  lon: number | null;
}

/** Payload completo de `deliveries_summary.json`. */
export interface DeliverySummary {
  period: { date_min: string; date_max: string; days: number };
  station_totals: Record<string, DeliveryStationTotals>;
  territory_totals: Record<string, number>;
  daily_by_station: DailyByStation;
  partners: PartnerDeliveryStats[];
}

/** Parceiro em um hex (item do top_partners). */
export interface HexPartnerBreakdown {
  store_id: string;
  nome_empresa: string;
  count: number;
}

/** Breakdown de um hex por canal, com top_partners (máx 10). */
export interface HexDeliveryBreakdown {
  hex_id: string;
  total: number;
  ihs: number;
  dsp: number;
  dsp_share_pct: number;
  top_partners: HexPartnerBreakdown[];
  /** DS dominante do hex (presente quando a Fase 6 conseguiu resolver). */
  station_code?: string;
  /** Território (bucket_ade) dominante do hex, quando conhecido. */
  territory_id?: string;
}

/** Payload completo de `deliveries_by_hex.json`. */
export interface DeliveriesByHex {
  period: { date_min: string; date_max: string; days: number };
  hexes: HexDeliveryBreakdown[];
}

/** Linha individual do .jsonl.gz por DS (chaves curtas para economizar bytes). */
export interface PackageDelivery {
  tid: string;               // tracking_id
  sdt: string;               // scan_datetime_br
  rc: string;                // reason_code
  st: string;                // store_id
  ne: string;                // nome_empresa
  ch: string;                // canal_entrega
  hex: string;
  lat?: number;
  lon?: number;
}

/** Pin que o Dashboard solicita ao mapa para exibir um pacote específico. */
export interface PackagePin {
  lat: number;
  lon: number;
  tracking_id: string;
  scan_datetime_br: string;
  reason_code: string;
  partner_name: string;
  canal: string;
}

/** Thresholds ajustáveis por sliders na aba Insights. */
export interface InsightThresholds {
  /** % do cap abaixo do qual um parceiro é considerado subutilizado. */
  cap_utilization_pct_threshold: number;
  /** % de queda em 7d vs 7d anteriores para sinalizar queda súbita. */
  trend_drop_pct_threshold: number;
  /** % mínimo de share DSP num território com hub ativo para alertar. */
  dsp_dominance_share_pct_threshold: number;
  /** Volume diário mínimo para um hex órfão entrar na lista. */
  orphan_hex_min_daily_volume: number;
}
