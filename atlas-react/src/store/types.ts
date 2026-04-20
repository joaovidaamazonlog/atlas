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
  | 'INSUFFICIENT_TOTAL_DEMAND';

export interface EvaluatorResult {
  totalDemand: number;
  residualDemand: number;
  minAdv: number;
  gap: number;
  viable: boolean;
  reason: ReasonCode | null;
  selectedCells: GeoJSON.Feature[];
  residualCells: GeoJSON.Feature[];
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
