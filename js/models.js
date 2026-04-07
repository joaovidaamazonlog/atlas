/**
 * models.js
 * =========
 * Modelos de dados centrais da aplicação frontend.
 * Cada classe representa um tipo de dado com validação,
 * valores padrão e métodos utilitários.
 *
 * Espelha a estrutura do backend Python (models.py),
 * garantindo consistência entre frontend e backend.
 */

// ---------------------------------------------------------------------------
// OTIMIZAÇÃO
// ---------------------------------------------------------------------------

/**
 * Dados de sugestão de otimização para um parceiro.
 */
export class OptimizationData {
    /**
     * @param {number} radiusSuggestion - Raio sugerido em metros
     * @param {number} capSuggestion    - Capacidade sugerida em pacotes/dia
     */
    constructor(radiusSuggestion = 1500, capSuggestion = 42) {
        /** @type {number} */ this.radius_suggestion = radiusSuggestion;
        /** @type {number} */ this.cap_suggestion    = capSuggestion;
    }

    static default() {
        return new OptimizationData(1500, 42);
    }

    static zero() {
        return new OptimizationData(0, 0);
    }
}

// ---------------------------------------------------------------------------
// PARCEIRO
// ---------------------------------------------------------------------------

/**
 * Status possíveis de um parceiro.
 * @enum {string}
 */
export const PartnerStatus = Object.freeze({
    ACTIVE:     'Active',
    INACTIVE:   'Inactive',
    ONBOARDING: 'Onboarding',
    BG_CHECKS:  'BG Checks',
    PROSPECT:   'Prospect',
    EXITED:     'Exited',
    NEW:        'New',         // slot ideal sem parceiro (oportunidade)
});

/**
 * Representa um parceiro logístico ou uma oportunidade de slot.
 */
export class Partner {
    /**
     * @param {Object} raw - Objeto bruto vindo da API
     */
    constructor(raw = {}) {
        /** @type {string}           */ this.salesforce_id          = raw.salesforce_id          ?? '';
        /** @type {string}           */ this.store_id               = raw.store_id               ?? '';
        /** @type {string}           */ this.name                   = raw.name                   ?? '';
        /** @type {string}           */ this.status                 = raw.status                 ?? PartnerStatus.ACTIVE;
        /** @type {number}           */ this.lat                    = raw.lat                    ?? 0;
        /** @type {number}           */ this.lon                    = raw.lon                    ?? 0;
        /** @type {string}           */ this.delivery_station       = raw.delivery_station       ?? '';
        /** @type {string}           */ this.bucket_ade             = raw.bucket_ade             ?? '';
        /** @type {string}           */ this.regiao                 = raw.regiao                 ?? '';
        /** @type {number}           */ this.radius                 = raw.radius                 ?? 0;
        /** @type {number}           */ this.capacity               = raw.capacity               ?? 0;
        /** @type {string}           */ this.launch_date            = raw.launch_date            ?? '';
        /** @type {string}           */ this.telefone               = raw.telefone               ?? '';
        /** @type {string}           */ this.hub_delivey_initiatives = raw.hub_delivey_initiatives ?? '';
        /** @type {string}           */ this.HCP_host_partner       = raw.HCP_host_partner       ?? '';
        /** @type {string}           */ this.HCP_rate_card          = raw.HCP_rate_card          ?? '';
        /** @type {string}           */ this.supply_run             = raw.supply_run             ?? '';
        /** @type {string}           */ this.decision               = raw.decision               ?? '';
        /** @type {string}           */ this.tooltip                = raw.tooltip                ?? '';
        /** @type {string[]|string}  */ this.ceps                   = raw.ceps                   ?? [];
        /** @type {OptimizationData} */ this.optimization           = raw.optimization
            ? new OptimizationData(raw.optimization.radius_suggestion, raw.optimization.cap_suggestion)
            : OptimizationData.default();
        /** @type {Object|null}      */ this.main_store_data        = raw.main_store_data        ?? null;
        /** @type {Object|null}      */ this.overlap_data           = raw.overlap_data           ?? null;
        /** @type {number}           */ this.ADV                    = raw.ADV                    ?? 0;
        /** @type {string}           */ this.slot_id                = raw.slot_id                ?? '';
    }

    /** @returns {boolean} */
    get isActive()     { return this.status === PartnerStatus.ACTIVE; }
    get isNew()        { return this.status === PartnerStatus.NEW; }
    get isInactive()   { return this.status === PartnerStatus.INACTIVE || this.status === PartnerStatus.EXITED; }
    get isOnboarding() { return this.status === PartnerStatus.ONBOARDING; }
    get hasCoords()    { return this.lat !== 0 && this.lon !== 0; }

    /**
     * Cria um Partner a partir de um slot ideal (oportunidade sem parceiro).
     * @param {Object} slotFeature - Feature GeoJSON do tipo IDEAL_SLOT
     * @returns {Partner}
     */
    static fromSlot(slotFeature) {
        const p = slotFeature.properties;
        return new Partner({
            status:           PartnerStatus.NEW,
            delivery_station: p.delivery_station,
            radius:           p.radius_s,
            capacity:         p.capacity_day,
            lat:              slotFeature.geometry.coordinates[1],
            lon:              slotFeature.geometry.coordinates[0],
            bucket_ade:       p.territory_id,
            ceps:             p.ceps ?? [],
            slot_id:          p.slot_id,
        });
    }
}

// ---------------------------------------------------------------------------
// DELIVERY STATION
// ---------------------------------------------------------------------------

/**
 * Representa uma base de distribuição (Delivery Station).
 */
export class DeliveryStation {
    /**
     * @param {Object} raw
     */
    constructor(raw = {}) {
        /** @type {string} */ this.nome = raw.nome ?? '';
        /** @type {number} */ this.lat  = raw.lat  ?? 0;
        /** @type {number} */ this.lon  = raw.lon  ?? 0;
    }
}

// ---------------------------------------------------------------------------
// FILTRO
// ---------------------------------------------------------------------------

/**
 * Estado dos filtros ativos na UI.
 */
export class FilterState {
    constructor() {
        /** @type {string[]|'all'} */ this.selectedStatuses  = 'all';
        /** @type {string[]|'all'} */ this.selectedStations  = 'all';
        /** @type {string[]|'all'} */ this.selectedBuckets   = 'all';
        /** @type {string}         */ this.initiativesFilter = 'all';
        /** @type {string}         */ this.jurisdictionFilter = 'all';
    }

    /** @returns {boolean} */
    get isDefault() {
        return (
            this.selectedStatuses  === 'all' &&
            this.selectedStations  === 'all' &&
            this.selectedBuckets   === 'all' &&
            this.initiativesFilter === 'all' &&
            this.jurisdictionFilter === 'all'
        );
    }
}

// ---------------------------------------------------------------------------
// ROTA / PARADA
// ---------------------------------------------------------------------------

/**
 * Representa uma parada em uma rota.
 */
export class RouteStop {
    /**
     * @param {string} storeId
     * @param {string} name
     * @param {number} lat
     * @param {number} lon
     */
    constructor(storeId, name, lat, lon) {
        /** @type {string} */ this.store_id = storeId;
        /** @type {string} */ this.name     = name;
        /** @type {number} */ this.lat      = lat;
        /** @type {number} */ this.lon      = lon;
    }
}

// ---------------------------------------------------------------------------
// HCP
// ---------------------------------------------------------------------------

/**
 * Grupos de parceiros para o sistema HCP.
 */
export class HcpGroups {
    /**
     * @param {Partner[]} hosts
     * @param {Partner[]} pickups
     * @param {Partner[]} heros
     * @param {Partner[]} all
     */
    constructor(hosts = [], pickups = [], heros = [], all = []) {
        /** @type {Partner[]} */ this.hosts   = hosts;
        /** @type {Partner[]} */ this.pickups = pickups;
        /** @type {Partner[]} */ this.heros   = heros;
        /** @type {Partner[]} */ this.all     = all;
    }
}

/**
 * Sugestão de movimento HCP (pickup mudando de host).
 */
export class HcpMove {
    /**
     * @param {Partner} pickup
     * @param {string}  from  - Nome do host atual
     * @param {string}  to    - Nome do host sugerido
     */
    constructor(pickup, from, to) {
        /** @type {Partner} */ this.pickup = pickup;
        /** @type {string}  */ this.from   = from;
        /** @type {string}  */ this.to     = to;
        /** @type {'move'}  */ this.type   = 'move';
    }
}

// ---------------------------------------------------------------------------
// GMAPS / PROSPECÇÃO
// ---------------------------------------------------------------------------

/**
 * Empresa candidata a parceiro encontrada via Google Maps ou Receita Federal.
 */
export class ProspectCompany {
    /**
     * @param {Object} raw
     */
    constructor(raw = {}) {
        /** @type {string}      */ this.nome             = raw.nome             ?? 'N/A';
        /** @type {string}      */ this.endereco         = raw.endereco         ?? 'N/A';
        /** @type {string|null} */ this.telefone_1       = raw.telefone_1       ?? null;
        /** @type {string|null} */ this.telefone_2       = raw.telefone_2       ?? null;
        /** @type {string|null} */ this.telefone         = raw.telefone         ?? null; // legado Google Maps
        /** @type {string}      */ this.site             = raw.site             ?? 'N/A';
        /** @type {string}      */ this.google_maps_link = raw.google_maps_link ?? 'N/A';
        /** @type {string}      */ this.cep              = raw.cep              ?? '';
        /** @type {string}      */ this.tipo             = raw.tipo             ?? 'outros';
        /** @type {string}      */ this._fonte           = raw._fonte           ?? '';
        /** @type {number|null} */ this.lat              = raw.lat              ?? null;
        /** @type {number|null} */ this.lon              = raw.lon              ?? null;

        // Se lat/lon não vieram no JSON, extrair do google_maps_link
        // O link sempre contém !3d<lat>!4d<lon> quando é um lugar específico
        if ((this.lat === null || this.lon === null) && this.google_maps_link !== 'N/A') {
            const m = this.google_maps_link.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
            if (m) {
                this.lat = parseFloat(m[1]);
                this.lon = parseFloat(m[2]);
            }
        }
    }

    /** @returns {string|null} Primeiro telefone disponível */
    get primaryPhone() {
        return this.telefone_1 || this.telefone || null;
    }

    /** @returns {string|null} */
    get secondaryPhone() {
        return this.telefone_2 || null;
    }

    /** @returns {boolean} */
    get hasSite() {
        return this.site !== 'N/A' && !!this.site;
    }

    /** @returns {boolean} */
    get hasMapsLink() {
        return this.google_maps_link !== 'N/A' && !!this.google_maps_link;
    }

    /** @returns {boolean} Empresa tem coordenadas geográficas */
    get isGeolocated() {
        return this.lat !== null && this.lon !== null;
    }
}

// ---------------------------------------------------------------------------
// CRITÉRIO DE HIGHLIGHT
// ---------------------------------------------------------------------------

/**
 * Critérios para highlight de marcadores no mapa.
 */
export class HighlightCriteria {
    constructor() {
        /** @type {'gt'|'lt'} */ this.eligibleOp    = 'gt';
        /** @type {number}    */ this.eligibleVal   = 0;
        /** @type {'gt'|'lt'} */ this.allocatedOp   = 'gt';
        /** @type {number}    */ this.allocatedVal  = 0;
        /** @type {string}    */ this.statusHighlight = 'all';
        /** @type {'gt'|'lt'|'eq'} */ this.overlappingOp  = 'gt';
        /** @type {number}    */ this.overlappingVal = 0;
    }
}
