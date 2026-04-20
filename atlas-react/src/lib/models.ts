/**
 * models.ts
 * =========
 * Classes de dados centrais da aplicação frontend.
 * Migração fiel de frontend/js/models.js para TypeScript.
 *
 * Cada classe representa um tipo de dado com validação,
 * valores padrão e métodos utilitários.
 */

import type {
  Partner as IPartner,
  DeliveryStation as IDeliveryStation,
  FilterState as IFilterState,
  RouteStop as IRouteStop,
  HcpGroups as IHcpGroups,
  HcpMove as IHcpMove,
  ProspectCompany as IProspectCompany,
  HighlightCriteria as IHighlightCriteria,
  OptimizationData as IOptimizationData,
  PartnerStatus,
  AdvOpportunity,
} from '../store/types';

// ---------------------------------------------------------------------------
// OTIMIZAÇÃO
// ---------------------------------------------------------------------------

export class OptimizationData implements IOptimizationData {
  radius_suggestion: number;
  cap_suggestion: number;

  constructor(radiusSuggestion = 1500, capSuggestion = 42) {
    this.radius_suggestion = radiusSuggestion;
    this.cap_suggestion = capSuggestion;
  }

  static default(): OptimizationData {
    return new OptimizationData(1500, 42);
  }

  static zero(): OptimizationData {
    return new OptimizationData(0, 0);
  }
}

// ---------------------------------------------------------------------------
// PARCEIRO
// ---------------------------------------------------------------------------

/** Status possíveis de um parceiro */
export const PARTNER_STATUS = Object.freeze({
  ACTIVE: 'Active' as PartnerStatus,
  INACTIVE: 'Inactive' as PartnerStatus,
  ONBOARDING: 'Onboarding' as PartnerStatus,
  BG_CHECKS: 'BG Checks' as PartnerStatus,
  PROSPECT: 'Prospect' as PartnerStatus,
  EXITED: 'Exited' as PartnerStatus,
  NEW: 'New' as PartnerStatus, // slot ideal sem parceiro (oportunidade)
});

type RawPartner = Partial<IPartner> & {
  optimization?: { radius_suggestion: number; cap_suggestion: number };
  radius_suggestion?: number;
  cap_suggestion?: number;
};

type SlotFeature = {
  geometry: { coordinates: [number, number] };
  properties: {
    delivery_station: string;
    radius_s: number;
    capacity_day: number;
    territory_id: string;
    ceps?: string[];
    slot_id: string;
  };
};

export class Partner implements IPartner {
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

  constructor(raw: RawPartner = {}) {
    this.salesforce_id = raw.salesforce_id ?? '';
    this.store_id = raw.store_id ?? null;
    this.name = raw.name ?? '';
    this.status = (raw.status ?? PARTNER_STATUS.ACTIVE) as PartnerStatus;
    this.lat = raw.lat ?? null;
    this.lon = raw.lon ?? null;
    this.zip_code = raw.zip_code ?? null;
    this.city = raw.city ?? null;
    this.state = raw.state ?? null;
    this.delivery_station = raw.delivery_station ?? '';
    this.supply_run = raw.supply_run ?? null;
    this.radius = raw.radius ?? 0;
    this.capacity = raw.capacity ?? 0;
    this.bucket = raw.bucket ?? null;
    this.jurisdiction_type = raw.jurisdiction_type ?? null;
    this.hub_delivey_initiatives = raw.hub_delivey_initiatives ?? null;
    this.HCP_rate_card = raw.HCP_rate_card ?? null;
    this.HCP_host_partner = raw.HCP_host_partner ?? null;
    this.launch_date = raw.launch_date ?? null;
    this.exited_date = raw.exited_date ?? null;
    this.telefone = raw.telefone ?? null;
    this.owner_id = raw.owner_id ?? null;
    this.decision_status = raw.decision_status ?? null;
    this.lead_source = raw.lead_source ?? null;
    this.tooltip = raw.tooltip ?? '';

    // Campos injetados pelo data-manager via optimization_data.geojson
    this.bucket_ade = raw.bucket_ade ?? raw.bucket ?? '';
    this.regiao = raw.regiao ?? '';
    this.decision = raw.decision ?? '';
    this.reason = raw.reason ?? '';

    if (raw.optimization) {
      this.optimization = new OptimizationData(
        raw.optimization.radius_suggestion,
        raw.optimization.cap_suggestion,
      );
    } else if (raw.radius_suggestion != null) {
      this.optimization = new OptimizationData(raw.radius_suggestion, raw.cap_suggestion);
    } else {
      this.optimization = OptimizationData.default();
    }

    // Campos de slots ideais
    this.ceps = (raw.ceps as string[]) ?? [];
    this.slot_id = raw.slot_id ?? '';
    this.adv_opportunity = (raw as any).adv_opportunity ?? null;
  }

  get isActive(): boolean {
    return this.status === PARTNER_STATUS.ACTIVE;
  }

  get isNew(): boolean {
    return this.status === PARTNER_STATUS.NEW;
  }

  get isInactive(): boolean {
    return this.status === PARTNER_STATUS.INACTIVE || this.status === PARTNER_STATUS.EXITED;
  }

  get isOnboarding(): boolean {
    return this.status === PARTNER_STATUS.ONBOARDING;
  }

  get hasCoords(): boolean {
    return this.lat !== 0 && this.lon !== 0;
  }

  /** Cria um Partner a partir de um slot ideal (oportunidade sem parceiro). */
  static fromSlot(slotFeature: SlotFeature): Partner {
    const p = slotFeature.properties;
    return new Partner({
      status: PARTNER_STATUS.NEW,
      delivery_station: p.delivery_station,
      radius: p.radius_s,
      capacity: p.capacity_day,
      lat: slotFeature.geometry.coordinates[1],
      lon: slotFeature.geometry.coordinates[0],
      bucket_ade: p.territory_id,
      ceps: p.ceps ?? [],
      slot_id: p.slot_id,
    });
  }
}

// ---------------------------------------------------------------------------
// DELIVERY STATION
// ---------------------------------------------------------------------------

export class DeliveryStation implements IDeliveryStation {
  nome: string;
  lat: number;
  lon: number;

  constructor(raw: Partial<IDeliveryStation> = {}) {
    this.nome = raw.nome ?? '';
    this.lat = raw.lat ?? 0;
    this.lon = raw.lon ?? 0;
  }
}

// ---------------------------------------------------------------------------
// FILTRO
// ---------------------------------------------------------------------------

export class FilterState implements IFilterState {
  selectedStatuses: string[] | 'all';
  selectedStations: string[] | 'all';
  selectedBuckets: string[] | 'all';
  initiativesFilter: string;
  jurisdictionFilter: string;

  constructor() {
    this.selectedStatuses = 'all';
    this.selectedStations = 'all';
    this.selectedBuckets = 'all';
    this.initiativesFilter = 'all';
    this.jurisdictionFilter = 'all';
  }

  get isDefault(): boolean {
    return (
      this.selectedStatuses === 'all' &&
      this.selectedStations === 'all' &&
      this.selectedBuckets === 'all' &&
      this.initiativesFilter === 'all' &&
      this.jurisdictionFilter === 'all'
    );
  }
}

// ---------------------------------------------------------------------------
// ROTA / PARADA
// ---------------------------------------------------------------------------

export class RouteStop implements IRouteStop {
  store_id: string;
  name: string;
  lat: number;
  lon: number;

  constructor(storeId: string, name: string, lat: number, lon: number) {
    this.store_id = storeId;
    this.name = name;
    this.lat = lat;
    this.lon = lon;
  }
}

// ---------------------------------------------------------------------------
// HCP
// ---------------------------------------------------------------------------

export class HcpGroups implements IHcpGroups {
  hosts: Partner[];
  pickups: Partner[];
  heros: Partner[];
  all: Partner[];

  constructor(
    hosts: Partner[] = [],
    pickups: Partner[] = [],
    heros: Partner[] = [],
    all: Partner[] = [],
  ) {
    this.hosts = hosts;
    this.pickups = pickups;
    this.heros = heros;
    this.all = all;
  }
}

export class HcpMove implements IHcpMove {
  pickup: Partner;
  from: string;
  to: string;
  type: 'move';

  constructor(pickup: Partner, from: string, to: string) {
    this.pickup = pickup;
    this.from = from;
    this.to = to;
    this.type = 'move';
  }
}

// ---------------------------------------------------------------------------
// GMAPS / PROSPECÇÃO
// ---------------------------------------------------------------------------

export class ProspectCompany implements IProspectCompany {
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

  constructor(raw: Partial<IProspectCompany> = {}) {
    this.nome = raw.nome ?? 'N/A';
    this.endereco = raw.endereco ?? 'N/A';
    this.telefone_1 = raw.telefone_1 ?? null;
    this.telefone_2 = raw.telefone_2 ?? null;
    this.telefone = raw.telefone ?? null;
    this.site = raw.site ?? 'N/A';
    this.google_maps_link = raw.google_maps_link ?? 'N/A';
    this.cep = raw.cep ?? '';
    this.tipo = raw.tipo ?? 'outros';
    this._fonte = raw._fonte ?? '';
    this.lat = raw.lat ?? null;
    this.lon = raw.lon ?? null;

    // Se lat/lon não vieram no JSON, extrair do google_maps_link
    if ((this.lat === null || this.lon === null) && this.google_maps_link !== 'N/A') {
      const m = this.google_maps_link.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
      if (m) {
        this.lat = parseFloat(m[1]);
        this.lon = parseFloat(m[2]);
      }
    }
  }

  /** Primeiro telefone disponível */
  get primaryPhone(): string | null {
    return this.telefone_1 || this.telefone || null;
  }

  get secondaryPhone(): string | null {
    return this.telefone_2 || null;
  }

  get hasSite(): boolean {
    return this.site !== 'N/A' && !!this.site;
  }

  get hasMapsLink(): boolean {
    return this.google_maps_link !== 'N/A' && !!this.google_maps_link;
  }

  /** Empresa tem coordenadas geográficas */
  get isGeolocated(): boolean {
    return this.lat !== null && this.lon !== null;
  }
}

// ---------------------------------------------------------------------------
// CRITÉRIO DE HIGHLIGHT
// ---------------------------------------------------------------------------

export class HighlightCriteria implements IHighlightCriteria {
  eligibleOp: 'gt' | 'lt';
  eligibleVal: number;
  allocatedOp: 'gt' | 'lt';
  allocatedVal: number;
  statusHighlight: string;
  overlappingOp: 'gt' | 'lt' | 'eq';
  overlappingVal: number;

  constructor() {
    this.eligibleOp = 'gt';
    this.eligibleVal = 0;
    this.allocatedOp = 'gt';
    this.allocatedVal = 0;
    this.statusHighlight = 'all';
    this.overlappingOp = 'gt';
    this.overlappingVal = 0;
  }
}
